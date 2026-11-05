# -*- coding: utf-8 -*-
"""
Maçkolik Anlık Canlı Maç ve İstatistik Takip Aracı (Gerçek Zamanlı Senkronize)
"""

import datetime
import json
import re
import time
import unicodedata
import streamlit as st
from bs4 import BeautifulSoup
import cloudscraper

# Sayfa yapılandırması
st.set_page_config(
    page_title="Maçkolik Anlık Canlı Takip",
    page_icon="⚽",
    layout="wide"
)

# Sayfayı arka planda otomatik yenile (Her 5 saniyede bir anlık senkronizasyon için)
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, key="mackolik_live_refresh")
except ImportError:
    pass

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

# Önbellek KULLANILMIYOR (Her yenilemede doğrudan Maçkolik'ten taze veri çekilir)
def fetch_scores():
    try:
        response = scraper.get(
            BASE,
            params={"sports[]": "Soccer", "matchDate": datetime.date.today().strftime("%Y-%m-%d")},
            headers={"Referer": "https://www.mackolik.com/canli-sonuclar"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
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

def parse_matches(payload, show_all=False):
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

        # Biten maçları filtrele
        if not show_all:
            if state in {"post", "ft", "ended", "fin", "finished", "ms"}:
                continue
            if any(word in status for word in ("mac sonu", "finished", "full time", "ms")):
                continue
            if state in {"pre"} or "baslamadi" in status:
                continue

        competition_id = event.get("competitionId")
        competition = competitions.get(competition_id, {}) if isinstance(competitions, dict) else {}
        
        # Doğrudan Maçkolik JSON skor nesnesini al
        score = event.get("score") or {}
        home_score = score.get("home", "0")
        away_score = score.get("away", "0")
        
        try:
            goals = int(home_score or 0) + int(away_score or 0)
        except (ValueError, TypeError):
            goals = 0

        rb_id = event.get("rbId")
        numeric_id = str(rb_id) if rb_id else re.sub(r"\D", "", str(event.get("id", "")))

        # Canlı durum / dakika bilgisi
        durum_metin = event.get("statusBoxContent") or ("İY" if state == "ht" else "CANLI")

        unique[match_id] = {
            "id": match_id,
            "numeric_id": numeric_id,
            "slug": event.get("matchSlug") or "mac",
            "sort": event.get("sortOrder", 9999),
            "lig": "{} - {}".format(
                (competition.get("country") or {}).get("name", ""),
                competition.get("name", ""),
            ).strip(" -"),
            "ev": (event.get("homeTeam") or {}).get("name", ""),
            "skor": f"{home_score} - {away_score}",  # Anlık güncel skor
            "gol": goals,
            "dep": (event.get("awayTeam") or {}).get("name", ""),
            "durum": str(durum_metin),
        }
    
    return sorted(unique.values(), key=lambda row: row.get("sort", 9999))

STAT_LABELS = {
    "corners": ("korner", "kose vurus", "corner"),
    "shots_on": ("isabetli sut", "kaleyi bulan sut", "shots on target"),
    "shots": ("toplam sut", "sut", "shots"),
    "fouls": ("faul", "fouls"),
    "possession": ("topla oynama", "topa sahip olma", "possession"),
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
    order = ("shots_on", "corners", "yellow_cards", "red_cards", "possession", "fouls", "shots")
    for key in order:
        if any(norm(alias) in label for alias in STAT_LABELS[key]):
            return key
    return None

def parse_stats_html(html):
    soup = BeautifulSoup(html, "html.parser")
    stats = {}
    for row in soup.find_all(["tr", "li", "div"]):
        cells = row.find_all(["td", "th", "span"], recursive=False)
        if len(cells) < 2:
            continue
        texts = [c.get_text(" ", strip=True) for c in cells if c.get_text(" ", strip=True)]
        if len(texts) < 2:
            continue
        label_index = next((i for i, t in enumerate(texts) if classify_stat(t) is not None), None)
        if label_index is None:
            continue
        key = classify_stat(texts[label_index])
        values = [number_from_text(t) for i, t in enumerate(texts) if i != label_index and number_from_text(t) is not None]
        if key and len(values) >= 2:
            stats[key] = (values[0], values[1])
    return stats

# İstatistik önbellek süresi 3 saniyeye düşürüldü
@st.cache_data(ttl=3)
def fetch_match_stats_cached(match_id, slug):
    url = f"https://arsiv.mackolik.com/AjaxHandlers/MatchHandler.aspx?command=rbStats&id={match_id}"
    try:
        res = scraper.get(url, headers={
            "Referer": f"https://arsiv.mackolik.com/Mac/{match_id}/{slug or 'mac'}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
        }, timeout=5)
        if res.status_code == 200:
            return parse_stats_html(res.text)
    except Exception:
        pass
    return {}

st.title("⚽ Maçkolik Canlı Maç ve İstatistik Takibi (Anlık)")

with st.sidebar:
    show_all = st.checkbox("Tüm Maçları Göster (Başlamamış/Biten)", value=False)
    if st.button("Verileri Şimdi Yenile"):
        st.cache_data.clear()
        st.rerun()

# Doğrudan canlı skor verisini taze çek
payload = fetch_scores()
matches = parse_matches(payload, show_all=show_all)

if not matches:
    st.warning("Şu anda canlı maç bulunamadı.")
else:
    table_data = []
    for m in matches:
        stats = fetch_match_stats_cached(m["numeric_id"], m["slug"])
        
        def fmt(k):
            v = stats.get(k)
            if not v or len(v) != 2: return "-"
            l, r = v
            return f"{l:g}% - {r:g}%" if k == "possession" else f"{l:g} - {r:g} ({l+r:g})"

        table_data.append({
            "Lig": m["lig"],
            "Durum": m["durum"],
            "Ev Sahibi": m["ev"],
            "Skor": m["skor"],  # Güncel skor
            "Deplasman": m["dep"],
            "Korner": fmt("corners"),
            "Şut": fmt("shots"),
            "İsabetli Şut": fmt("shots_on"),
            "Faul": fmt("fouls"),
            "Topla Oynama": fmt("possession"),
            "Sarı": fmt("yellow_cards"),
            "Kırmızı": fmt("red_cards"),
        })

    st.caption(f"Son Senkronizasyon: {datetime.datetime.now().strftime('%H:%M:%S')} (Her 5 saniyede bir otomatik güncellenir)")
    st.dataframe(table_data, width="stretch")