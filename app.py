# -*- coding: utf-8 -*-
"""
Maçkolik Canlı ve Biten Maç Takip Paneli (Streamlit Cloud Sürümü)
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
    page_title="Maçkolik Canlı & Biten Maçlar",
    page_icon="⚽",
    layout="wide"
)

# Sayfayı otomatik yenilemek için autorefresh (15 saniye)
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=15000, key="mackolik_refresh")
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
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en-US;q=0.7",
})

def fetch_scores():
    try:
        r = scraper.get(
            BASE,
            params={"sports[]": "Soccer", "matchDate": datetime.date.today().strftime("%Y-%m-%d")},
            headers={"Referer": "https://www.mackolik.com/canli-sonuclar"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def _find_matches(obj, out):
    if isinstance(obj, dict):
        if "homeTeam" in obj and "awayTeam" in obj and "matchName" in obj:
            out.append(obj)
        else:
            for v in obj.values():
                _find_matches(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _find_matches(v, out)

def parse_matches(j, include_finished=True):
    data = j.get("data") or j
    comps = data.get("competitions") or {}
    events = []
    _find_matches(data, events)
    rows = []
    for e in events:
        state = e.get("state")
        # Başlamamış maçları atla
        if state == "pre":
            continue
        # Biten maçlar istenmiyorsa atla
        if not include_finished and state in ["post", "ft", "ended"]:
            continue

        comp = comps.get(e.get("competitionId"), {})
        ms = e.get("mstUtc")
        saat = datetime.datetime.fromtimestamp(ms/1000, datetime.timezone.utc).astimezone().strftime("%H:%M") if ms else "?"
        s = e.get("score") or {}
        
        if state == "in":
            durum_label = "CANLI"
        elif state in ["post", "ft", "ended"]:
            durum_label = "MS"
        else:
            durum_label = str(state or "")

        dk = e.get("statusBoxContent") or ""
        try:
            gol = int(s.get("home") or 0) + int(s.get("away") or 0)
        except ValueError:
            gol = 0

        numeric_id = e.get("rbId") or re.sub(r"\D", "", e.get("id", "") or "") or None
        rows.append({
            "sort": e.get("sortOrder", 9999),
            "lig": f"{comp.get('country',{}).get('name','')}-{comp.get('name','')}".strip("-"),
            "saat": saat,
            "ev": e.get("homeTeam", {}).get("name", ""),
            "skor": f"{s.get('home','-')}-{s.get('away','-')}",
            "gol": gol,
            "dep": e.get("awayTeam", {}).get("name", ""),
            "durum": f"{durum_label} {dk}".strip(),
            "live": state == "in",
            "finished": state in ["post", "ft", "ended"],
            "slug": e.get("matchSlug") or "mac",
            "id": e.get("id", ""),
            "numeric_id": numeric_id,
        })
    rows.sort(key=lambda m: m["sort"])
    return rows

# Streamlit Arayüzü
st.title("⚽ Maçkolik Canlı ve Biten Maç Paneli")

with st.sidebar:
    st.header("Kontrol Paneli")
    include_finished = st.checkbox("Biten Maçları (MS) Göster", value=True)
    if st.button("Verileri Şimdi Yenile"):
        st.cache_data.clear()
        st.rerun()

payload = fetch_scores()
rows = parse_matches(payload, include_finished=include_finished)

if not rows:
    st.warning("Şu anda gösterilecek maç bulunamadı.")
else:
    live_count = sum(1 for m in rows if m["live"])
    finished_count = sum(1 for m in rows if m["finished"])
    st.caption(f"Son Güncelleme: {datetime.datetime.now().strftime('%H:%M:%S')} | Toplam: {len(rows)} maç ({live_count} Canlı, {finished_count} Biten)")

    table_data = []
    for m in rows:
        table_data.append({
            "Lig": m["lig"],
            "Saat": m["saat"],
            "Durum": m["durum"],
            "Ev Sahibi": m["ev"],
            "Skor": m["skor"],
            "Deplasman": m["dep"],
            "Toplam Gol": m["gol"],
        })

    st.dataframe(table_data, width="stretch")