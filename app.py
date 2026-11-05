# -*- coding: utf-8 -*-
"""
Maçkolik Canlı Maç Takip Paneli (Canlı ve Dakika Eşitlenmiş, Yanıp Sönen Gol Efektli)
"""
import datetime
import json
import re
import unicodedata
import streamlit as st
import cloudscraper

# Sayfa yapılandırması
st.set_page_config(
    page_title="Maçkolik Anlık Canlı Maçlar",
    page_icon="⚽",
    layout="wide"
)

# Her 5 saniyede bir otomatik yenileme (Anlık senkronizasyon için)
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

def parse_matches(j):
    data = j.get("data") or j
    comps = data.get("competitions") or {}
    events = []
    _find_matches(data, events)
    rows = []
    for e in events:
        state = e.get("state")
        
        # YALNIZCA canlı oynanan maçları al (Pre, post, ft gibi bitmiş/başlamamışları ele)
        if state != "in":
            continue

        comp = comps.get(e.get("competitionId"), {})
        s = e.get("score") or {}
        
        # Maç dakikası veya durumu (örn: 39', İY)
        dk = e.get("statusBoxContent") or "CANLI"

        try:
            gol = int(s.get("home") or 0) + int(s.get("away") or 0)
        except ValueError:
            gol = 0

        numeric_id = e.get("rbId") or re.sub(r"\D", "", str(e.get("id", ""))) or None
        
        rows.append({
            "sort": e.get("sortOrder", 9999),
            "lig": f"{comp.get('country',{}).get('name','')}-{comp.get('name','')}".strip("-"),
            "ev": e.get("homeTeam", {}).get("name", ""),
            "skor": f"{s.get('home','0')}-{s.get('away','0')}",
            "gol": gol,
            "dep": e.get("awayTeam", {}).get("name", ""),
            "durum": str(dk),
            "numeric_id": str(numeric_id),
        })
    rows.sort(key=lambda m: m["sort"])
    return rows

# Streamlit Arayüzü
st.title("⚽ Maçkolik Canlı Maç Takip Paneli")

# Gol anında yeşil yanıp sönme efekti için CSS
st.markdown("""
<style>
@keyframes blink-green {
    0% { background-color: rgba(46, 204, 113, 0.9); }
    50% { background-color: rgba(46, 204, 113, 0.2); }
    100% { background-color: rgba(46, 204, 113, 0.9); }
}
.goal-flash {
    animation: blink-green 1s ease-in-out infinite;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Kontrol Paneli")
    if st.button("Verileri Şimdi Yenile"):
        st.cache_data.clear()
        st.rerun()

payload = fetch_scores()
rows = parse_matches(payload)

if not rows:
    st.warning("Şu anda canlı oynanan maç bulunamadı.")
else:
    st.caption(f"Son Güncelleme: {datetime.datetime.now().strftime('%H:%M:%S')} | Aktif Canlı Maç Sayısı: {len(rows)}")

    # Gol takibi için session_state
    if "prev_scores" not in st.session_state:
        st.session_state.prev_scores = {}

    table_html = """
    <style>
    table { width: 100%; border-collapse: collapse; font-family: sans-serif; color: #fff; }
    th { background-color: #26304a; padding: 10px; text-align: left; }
    td { padding: 10px; border-bottom: 1px solid #2c3e50; }
    tr:hover { background-color: #1c2230; }
    .live-badge { background-color: #27ae60; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
    </style>
    <table>
        <tr>
            <th>Lig</th>
            <th>Dakika</th>
            <th>Ev Sahibi</th>
            <th>Skor</th>
            <th>Deplasman</th>
        </tr>
    """

    for m in rows:
        m_id = m["numeric_id"]
        current_score = m["skor"]
        
        is_goal = False
        if m_id in st.session_state.prev_scores:
            if st.session_state.prev_scores[m_id] != current_score:
                is_goal = True
        
        st.session_state.prev_scores[m_id] = current_score
        
        row_class = "goal-flash" if is_goal else ""
        
        table_html += f"""
        <tr class="{row_class}">
            <td>{m['lig']}</td>
            <td><span class="live-badge">{m['durum']}</span></td>
            <td><b>{m['ev']}</b></td>
            <td><h3 style="margin:0; color: #f1c40f;">{m['skor']}</h3></td>
            <td><b>{m['dep']}</b></td>
        </tr>
        """

    table_html += "</table>"
    st.markdown(table_html, unsafe_allow_html=True)