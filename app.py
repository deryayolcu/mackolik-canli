# -*- coding: utf-8 -*-
"""
Maçkolik Doğrudan Arşiv Canlı Maç ve İstatistik Takip Aracı (Esnek Tarama Sürümü)
"""

import datetime
import json
import re
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

# Her 5 saniyede bir otomatik yenileme
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, key="mackolik_live_refresh")
except ImportError:
    pass

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
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en-US;q=0.7",
})

def norm(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold().replace("ı", "i").strip()

def fetch_archive_live_matches():
    url = "https://arsiv.mackolik.com/Canli-Sonuclar"
    headers = {
        "User-Agent": UA,
        "Referer": "https://arsiv.mackolik.com/",
    }
    try:
        res = scraper.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        matches = []
        current_league = "Genel Lig"
        
        # Tüm tablo satırlarını tara
        for tr in soup.find_all("tr"):
            classes = tr.get("class", [])
            # Lig başlığı tespiti
            if any(c in str(classes).lower() for c in ["comp", "league", "baslik", "header"]):
                comp_text = tr.get_text(" - ", strip=True)
                if comp_text:
                    current_league = comp_text
                continue
                
            row_id = tr.get("id")
            # row_ ile başlayan maç satırlarını yakala
            if row_id and row_id.startswith("row_"):
                match_id = row_id.replace("row_", "")
                
                status_td = tr.select_one("td.td_status")
                row_text = tr.get_text(" ", strip=True)
                
                # Eğer satırda MS (Maç Sonucu) geçiyorsa bitmiştir, atla
                if " MS " in row_text or "MS" == row_text.strip():
                    continue
                
                status_text = status_td.get_text(strip=True) if status_td else ""
                status_norm = norm(status_text)
                
                # Biten maçları ele
                if any(w in status_norm for w in ["ms", "mac sonu", "ft", "fin", "bit", "ert"]):
                    continue
                
                # Dakika değerini çek
                minute_span = tr.select_one("span.sp_minute") or tr.select_one("td.td_status span")
                minute_val = minute_span.get_text(strip=True) if minute_span else status_text
                
                # Eğer saat formatı varsa (örn: 23:00) henüz başlamamıştır, atla
                if not minute_val or re.search(r"\d{2}:\d{2}", minute_val):
                    continue

                # Skor tespiti
                score_match = re.search(r"(\d+)\s*[-–]\s*(\d+)", row_text)
                score_text = "0 - 0"
                if score_match:
                    score_text = f"{score_match.group(1)} - {score_match.group(2)}"
                
                # Takım isimleri tespiti
                teams = []
                for a in tr.find_all("a"):
                    txt = a.get_text(strip=True)
                    href = a.get("href", "")
                    if txt and len(txt) > 1 and not txt.isdigit() and ("Mac" in href or "Sahaya" in href or "takim" in href):
                        if txt not in teams:
                            teams.append(txt)
                
                if len(teams) >= 2:
                    home_team = teams[0]
                    away_team = teams[1]
                else:
                    # Alternatif hücre bazlı takım okuma
                    tds = tr.find_all("td")
                    team_candidates = []
                    for td in tds:
                        t = td.get_text(strip=True)
                        if len(t) > 2 and not t.isdigit() and "-" not in t:
                            team_candidates.append(t)
                    if len(team_candidates) >= 2:
                        home_team = team_candidates[0]
                        away_team = team_candidates[1]
                    else:
                        continue

                matches.append({
                    "numeric_id": match_id,
                    "slug": "mac",
                    "lig": current_league,
                    "ev": home_team,
                    "skor": score_text,
                    "dep": away_team,
                    "durum": f"{minute_val}'" if minute_val.isdigit() else minute_val,
                })
        return matches
    except Exception as e:
        return []

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
            soup = BeautifulSoup(res.text, "html.parser")
            stats = {}
            for row in soup.find_all(["tr", "li", "div"]):
                cells = row.find_all(["td", "th", "span"], recursive=False)
                if len(cells) < 2:
                    continue
                texts = [c.get_text(" ", strip=True) for c in cells if c.get_text(" ", strip=True)]
                if len(texts) < 2:
                    continue
                nums = []
                for t in texts:
                    m = re.search(r"(\d+(?:[.,]\d+)?)", t.replace("%", ""))
                    if m:
                        try:
                            nums.append(float(m.group(1).replace(",", ".")))
                        except:
                            pass
                if len(nums) >= 2:
                    joined_text = " ".join(texts).lower()
                    if "korner" in joined_text or "corner" in joined_text:
                        stats["corners"] = (nums[0], nums[1])
                    elif "isabetli" in joined_text:
                        stats["shots_on"] = (nums[0], nums[1])
                    elif "sut" in joined_text or "shot" in joined_text:
                        if "sut" not in stats:
                            stats["shots"] = (nums[0], nums[1])
                    elif "faul" in joined_text:
                        stats["fouls"] = (nums[0], nums[1])
                    elif "topla" in joined_text or "possession" in joined_text:
                        stats["possession"] = (nums[0], nums[1])
                    elif "sari" in joined_text:
                        stats["yellow_cards"] = (nums[0], nums[1])
                    elif "kirmizi" in joined_text:
                        stats["red_cards"] = (nums[0], nums[1])
            return stats
    except Exception:
        pass
    return {}

st.title("⚽ Maçkolik Arşiv Canlı Maç Takibi")

matches = fetch_archive_live_matches()

if not matches:
    st.warning("Şu anda Maçkolik arşiv canlı sayfasında aktif maç bulunamadı.")
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
            "Dakika": m["durum"],
            "Ev Sahibi": m["ev"],
            "Skor": m["skor"],
            "Deplasman": m["dep"],
            "Korner": fmt("corners"),
            "Şut": fmt("shots"),
            "İsabetli Şut": fmt("shots_on"),
            "Faul": fmt("fouls"),
            "Topla Oynama": fmt("possession"),
            "Sarı": fmt("yellow_cards"),
            "Kırmızı": fmt("red_cards"),
        })

    st.caption(f"Son Güncelleme: {datetime.datetime.now().strftime('%H:%M:%S')} (Esnek Tarama Aktif)")
    st.dataframe(table_data, width="stretch")