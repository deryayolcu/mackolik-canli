# -*- coding: utf-8 -*-
"""
Maçkolik Doğrudan Arşiv Canlı Maç Takip Paneli (Canlı ve Dakika Eşitlenmiş)
"""
import datetime
import re
import unicodedata
import streamlit as st
from bs4 import BeautifulSoup
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
        
        for tr in soup.find_all("tr"):
            classes = tr.get("class", [])
            # Lig başlığı tespiti
            if any(c in str(classes).lower() for c in ["comp", "league", "baslik", "header"]):
                comp_text = tr.get_text(" - ", strip=True)
                if comp_text:
                    current_league = comp_text
                continue
                
            row_id = tr.get("id")
            if row_id and row_id.startswith("row_"):
                match_id = row_id.replace("row_", "")
                
                status_td = tr.select_one("td.td_status")
                row_text = tr.get_text(" ", strip=True)
                
                # Biten maçları kesinlikle ele (MS içerenleri atla)
                if " MS " in row_text or "MS" == row_text.strip():
                    continue
                
                status_text = status_td.get_text(strip=True) if status_td else ""
                status_norm = norm(status_text)
                
                if any(w in status_norm for w in ["ms", "mac sonu", "ft", "fin", "bit", "ert"]):
                    continue
                
                # Dakika değerini çek (örn: 39' veya İY)
                minute_span = tr.select_one("span.sp_minute") or tr.select_one("td.td_status span")
                minute_val = minute_span.get_text(strip=True) if minute_span else status_text
                
                # Eğer saat formatı varsa (örn: 23:00 veya 22:45) henüz oynanmıyor/başlamamış demektir, ele
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
                    "dakika": f"{minute_val}'" if minute_val.isdigit() else minute_val,
                })
        return matches
    except Exception as e:
        return []

# Streamlit Arayüzü
st.title("⚽ Maçkolik Canlı Maç Takip Paneli (Anlık Arşiv)")

# Gol anında yanıp sönme efekti için CSS
st.markdown("""
<style>
@keyframes blink-green {
    0% { background-color: rgba(46, 204, 113, 0.8); }
    50% { background-color: rgba(46, 204, 113, 0.2); }
    100% { background-color: rgba(46, 204, 113, 0.8); }
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

matches = fetch_archive_live_matches()

if not matches:
    st.warning("Şu anda Maçkolik arşiv canlı sayfasında aktif oynanan maç bulunamadı.")
else:
    st.caption(f"Son Güncelleme: {datetime.datetime.now().strftime('%H:%M:%S')} | Aktif Canlı Maç Sayısı: {len(matches)}")

    # Gol takibi ve yanıp sönme mantığı için session_state kullanımı
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

    for m in matches:
        m_id = m["numeric_id"]
        current_score = m["skor"]
        
        # Gol kontrolü (Önceki skor ile şimdiki skor farklıysa yanıp sönme efekti ver)
        is_goal = False
        if m_id in st.session_state.prev_scores:
            if st.session_state.prev_scores[m_id] != current_score:
                is_goal = True
        
        st.session_state.prev_scores[m_id] = current_score
        
        row_class = "goal-flash" if is_goal else ""
        
        table_html += f"""
        <tr class="{row_class}">
            <td>{m['lig']}</td>
            <td><span class="live-badge">{m['dakika']}</span></td>
            <td><b>{m['ev']}</b></td>
            <td><h3 style="margin:0; color: #f1c40f;">{m['skor']}</h3></td>
            <td><b>{m['dep']}</b></td>
        </tr>
        """

    table_html += "</table>"
    st.markdown(table_html, unsafe_allow_html=True)