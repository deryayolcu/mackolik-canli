# -*- coding: utf-8 -*-
"""
Maçkolik Canlı Maç ve İstatistik Takip Aracı (Streamlit - Online Sürüm)
"""

import datetime
import json
import re
import time
import unicodedata
import requests
import streamlit as st
from bs4 import BeautifulSoup
import cloudscraper

# Sayfa yapılandırması
st.set_page_config(
    page_title="Maçkolik Canlı İstatistik Takibi",
    page_icon="⚽",
    layout="wide"
)

BASE = "https://www.mackolik.com/perform/p0/ajax/components/competition/livescores/json"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

@st.cache_resource
def get_scraper():
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )

scraper = get_scraper()
scraper.headers.update({
    "User-Agent": UA,
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
})

def norm(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold().replace("ı", "i").strip()

def fetch_scores(date=None):
    date = date or datetime.date.today()
    try:
        response = scraper.get(
            BASE,
            params={"sports[]": "Soccer", "matchDate": date.strftime("%Y-%m-%d")},
            headers={"Referer": "https://www.mackolik.com/canli-sonuclar"},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Maç listesi alınırken hata oluştu: {e}")
        return {}

def find_match_objects(obj, out):
    if isinstance(obj, dict):
        if "homeTeam" in obj and "awayTeam" in obj and (
            "matchName" in obj or "score" in obj or "state" in obj
        ):
            out.append(obj)
        else:
            for value in obj.values():
                find_match_objects(value, out)
    elif isinstance(obj, list):
        for value in obj:
            find_match_objects(value, out)

def parse_matches(payload, show_all=True):
    data = payload.get("data") or payload
    competitions = data.get("competitions") or {}
    found = []
    find_match_objects(data, found)

    unique = {}
    for event in found:
        match_id = str(event.get("id") or event.get("rbId") or "")
        if not match_id or match_id in unique:
            continue

        state = norm(event.get("state", ""))
        status = norm(event.get("statusBoxContent", ""))

        if not show_all:
            if state in {"pre", "post", "ft", "ended", "fin", "finished"}:
                continue
            if any(word in status for word in ("baslamadi", "mac sonu", "finished", "full time")):
                continue

        competition_id = event.get("competitionId")
        competition = competitions.get(competition_id, {}) if isinstance(competitions, dict) else {}
        score = event.get("score") or {}
        home_score = score.get("home", "-")
        away_score = score.get("away", "-")
        try:
            goals = int(home_score or 0) + int(away_score or 0)
        except (ValueError, TypeError):
            goals = 0

        timestamp = event.get("mstUtc")
        try:
            kickoff = datetime.datetime.fromtimestamp(
                float(timestamp) / 1000, datetime.timezone.utc
            ).astimezone().strftime("%H:%M") if timestamp else "-"
        except (ValueError, TypeError, OSError):
            kickoff = "-"

        rb_id = event.get("rbId")
        numeric_id = str(rb_id) if rb_id else re.sub(r"\D", "", str(event.get("id", "")))

        unique[match_id] = {
            "id": match_id,
            "rb_id": str(rb_id) if rb_id is not None else None,
            "numeric_id": numeric_id,
            "slug": event.get("matchSlug") or "mac",
            "sort": event.get("sortOrder", 9999),
            "lig": "{} - {}".format(
                (competition.get("country") or {}).get("name", ""),
                competition.get("name", ""),
            ).strip(" -"),
            "saat": kickoff,
            "ev": (event.get("homeTeam") or {}).get("name", ""),
            "skor": f"{home_score}-{away_score}",
            "gol": goals,
            "dep": (event.get("awayTeam") or {}).get("name", ""),
            "durum": str(event.get("statusBoxContent") or "CANLI"),
        }

    return sorted(unique.values(), key=lambda row: row["sort"])

STAT_LABELS = {
    "corners": ("korner", "kose vurus", "corner"),
    "shots_on": ("isabetli sut", "kaleyi bulan sut", "shots on target"),
    "shots_off": ("isabetsiz sut", "kaleyi bulmayan sut", "shots off target"),
    "shots": ("toplam sut", "sut", "shots"),
    "fouls": ("faul", "fouls"),
    "possession": ("topla oynama", "topa sahip olma", "possession"),
    "offsides": ("ofsayt", "offsides"),
    "yellow_cards": ("sari kart", "yellow cards"),
    "red_cards": ("kirmizi kart", "red cards"),
}

def number_from_text(text):
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(text).replace("%", ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None

def classify_stat(label):
    label = norm(label)
    order = ("shots_on", "shots_off", "corners", "yellow_cards", "red_cards",
             "possession", "offsides", "fouls", "shots")
    for key in order:
        if any(norm(alias) in label for alias in STAT_LABELS[key]):
            if key == "shots" and ("isabetli" in label or "kaleyi bulan" in label):
                continue
            if key == "shots" and ("isabetsiz" in label or "kaleyi bulmayan" in label):
                continue
            return key
    return None

def parse_stats_html(html):
    soup = BeautifulSoup(html, "html.parser")
    stats = {}
    for row in soup.find_all(["tr", "li", "div"]):
        cells = row.find_all(["td", "th", "span"], recursive=False)
        if len(cells) < 2:
            continue
        texts = [cell.get_text(" ", strip=True) for cell in cells if cell.get_text(" ", strip=True)]
        if len(texts) < 2:
            continue
        label_index = next((i for i, text in enumerate(texts) if classify_stat(text) is not None), None)
        if label_index is None:
            continue
        key = classify_stat(texts[label_index])
        values = [number_from_text(t) for i, t in enumerate(texts) if i != label_index and number_from_text(t) is not None]
        if key and len(values) >= 2:
            stats[key] = (values[0], values[1])
    return stats

@st.cache_data(ttl=120)
def fetch_match_stats_cached(match_id, slug):
    endpoint = "https://arsiv.mackolik.com/AjaxHandlers/MatchHandler.aspx"
    url = f"{endpoint}?command=rbStats&id={match_id}"
    try:
        res = scraper.get(url, headers={
            "Referer": f"https://arsiv.mackolik.com/Mac/{match_id}/{slug or 'mac'}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
        }, timeout=15)
        if res.status_code == 200:
            return parse_stats_html(res.text)
    except Exception:
        pass
    return {}

# --- ARAYÜZ (Streamlit) ---
st.title("⚽ Maçkolik Canlı Maç ve İstatistik Takibi (Online)")

with st.sidebar:
    st.header("Ayarlar & Filtreler")
    show_all = st.checkbox("Tüm Maçları Göster (Başlamamış/Biten)", value=True)
    
    st.markdown("---")
    st.subheader("Minimum Filtreler")
    min_korner = st.number_input("En Az Korner", min_value=0, value=0)
    min_sut = st.number_input("En Az Şut", min_value=0, value=0)
    min_gol = st.number_input("En Az Gol", min_value=0, value=0)
    
    if st.button("Verileri Yenile"):
        st.cache_data.clear()
        st.rerun()

# Maçları çek
payload = fetch_scores()
matches = parse_matches(payload, show_all=show_all)

if not matches:
    st.warning("Şu anda gösterilecek maç bulunamadı.")
else:
    table_data = []
    for m in matches:
        stats = fetch_match_stats_cached(m["numeric_id"], m["slug"])
        
        # Değerleri formatla
        def get_stat_str(k):
            vals = stats.get(k)
            if not vals or len(vals) != 2:
                return "-"
            l, r = vals
            if k == "possession":
                return f"{l:g}% - {r:g}%"
            return f"{l:g} - {r:g} ({l+r:g})"

        corners_vals = stats.get("corners", (0, 0))
        total_corners = sum(corners_vals) if isinstance(corners_vals, tuple) else 0
        
        shots_vals = stats.get("shots", (0, 0))
        total_shots = sum(shots_vals) if isinstance(shots_vals, tuple) else 0

        # Filtreleme kontrolü
        if total_corners < min_korner: continue
        if total_shots < min_sut: continue
        if m["gol"] < min_gol: continue

        table_data.append({
            "Lig": m["lig"],
            "Saat": m["saat"],
            "Durum": m["durum"],
            "Ev Sahibi": m["ev"],
            "Skor": m["skor"],
            "Deplasman": m["dep"],
            "Korner": get_stat_str("corners"),
            "Şut": get_stat_str("shots"),
            "İsabetli Şut": get_stat_str("shots_on"),
            "Faul": get_stat_str("fouls"),
            "Topla Oynama": get_stat_str("possession"),
            "Sarı": get_stat_str("yellow_cards"),
            "Kırmızı": get_stat_str("red_cards"),
        })

    st.info(f"Toplam {len(table_data)} maç listeleniyor.")
    st.dataframe(table_data, use_container_width=True)