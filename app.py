# -*- coding: utf-8 -*-
"""
canli_mac.py — Streamlit Canlı Maç Paneli + Gelişmiş Filtreler + Gol Animasyonu + Tahmin Motoru
Veri: fotmob.com (resmî olmayan JSON ucu)
"""

import math
import re
import time
from datetime import datetime, timezone
import requests
import streamlit as st

# ------------------------------------------------------------------ Ayarlar
st.set_page_config(
    page_title="Canlı Maç + İstatistik + Tahmin · FotMob",
    page_icon="⚽",
    layout="wide",
)

BASE = "https://www.fotmob.com/api/data/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.fotmob.com/",
    "Origin": "https://www.fotmob.com",
}

MIN_RE = re.compile(r"(\d+)\s*(?:\+\s*(\d+))?")

# ------------------------------------------------------------ Çeviri Tabloları
STAT_TR = {
    "ball possession": "Topla oynama", "possession": "Topla oynama",
    "expected goals (xg)": "Gol beklentisi (xG)", "expected goals": "Gol beklentisi",
    "xg": "Gol beklentisi (xG)", "expected assists (xa)": "Asist beklentisi (xA)",
    "xg on target (xgot)": "Kaleyi bulan xG (xGOT)",
    "big chances": "Büyük fırsat", "big chances created": "Yaratılan büyük fırsat",
    "big chances missed": "Kaçırılan büyük fırsat",
    "goals": "Gol", "assists": "Asist", "corners": "Korner", "fouls": "Faul",
    "offsides": "Ofsayt", "yellow cards": "Sarı kart", "red cards": "Kırmızı kart",
    "total shots": "Toplam şut", "shots": "Şut",
    "shots on target": "İsabetli şut", "shots off target": "İsabetsiz şut",
    "blocked shots": "Bloklanan şut",
    "shots inside the box": "Ceza sahası içinden şut",
    "shots outside the box": "Ceza sahası dışından şut",
    "hit woodwork": "Direkten dönen", "shot accuracy": "Şut isabet oranı",
    "passes": "Pas", "total passes": "Toplam pas",
    "accurate passes": "İsabetli pas", "pass accuracy": "Pas isabet oranı",
    "total long balls": "Toplam uzun top", "long balls": "Uzun top",
    "accurate long balls": "İsabetli uzun top",
    "total crosses": "Toplam orta", "crosses": "Orta",
    "accurate crosses": "İsabetli orta", "cross accuracy": "Orta isabet oranı",
    "corner kicks": "Korner", "corners": "Korner",
    "saves": "Kurtarış", "fouls": "Faul"
}

GROUP_TR = {
    "top stats": "ÖNE ÇIKANLAR", "shots": "ŞUTLAR",
    "expected goals": "GOL BEKLENTİSİ", "passes": "PASLAR",
    "duels": "İKİLİ MÜCADELELER", "defending": "SAVUNMA",
    "discipline": "DİSİPLİN", "goalkeeping": "KALECİ", "physical": "FİZİKSEL", "other": "DİĞER",
}

LEAGUE_TR = {
    "premier league": "İngiltere Premier Lig", "efl championship": "İngiltere Championship",
    "championship": "İngiltere Championship", "laliga": "İspanya La Liga",
    "la liga": "İspanya La Liga", "serie a": "İtalya Serie A",
    "bundesliga": "Almanya Bundesliga", "ligue 1": "Fransa Ligue 1",
    "eredivisie": "Hollanda Eredivisie", "süper lig": "Türkiye Süper Lig",
    "super lig": "Türkiye Süper Lig", "uefa champions league": "Şampiyonlar Ligi",
}

TEAM_TR = {
    "bayern munich": "Bayern Münih", "inter": "Inter", "ac milan": "Milan",
    "atletico madrid": "Atlético Madrid", "tottenham hotspur": "Tottenham",
}

def tr_stat(title):
    if not title: return title
    key = re.sub(r"\s+", " ", title.strip().lower())
    return STAT_TR.get(key, title.strip())

def tr_group(name):
    if not name: return ""
    key = re.sub(r"\s+", " ", name.strip().lower())
    return GROUP_TR.get(key, name.upper())

def tr_league(name, ccode=""):
    raw = (name or "").strip()
    return LEAGUE_TR.get(raw.lower(), raw)

def tr_team(name):
    return TEAM_TR.get((name or "").strip().lower(), name)

@st.cache_data(ttl=1)
def get_json(path, **params):
    try:
        r = requests.get(BASE + path, headers=HEADERS, params=params, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

def minute_state(st):
    if st.get("cancelled"): return ("cancel", 0, 0, None)
    if st.get("finished"): return ("ft", 0, 0, None)
    reason = ((st.get("reason") or {}).get("short") or "").upper()
    if reason in ("HT", "BT", "HALF"): return ("ht", 0, 0, None)

    lt = st.get("liveTime") or {}
    short = str(lt.get("short") or "").replace("\u2019", "'")
    m = MIN_RE.search(short)
    base = int(m.group(1)) if m else None
    extra = int(m.group(2) or 0) if m else 0
    if base is None:
        mt = lt.get("maxTime")
        if isinstance(mt, (int, float)): base = int(mt)
    if base is None:
        return ("min", 0, 0, None) if st.get("started") else ("pre", 0, 0, None)
    return ("min", base, extra, time.time())

def minute_text(state):
    kind, base, extra, _ = state
    if kind == "ft": return "MS"
    if kind == "ht": return "İY"
    if kind == "cancel": return "İptal"
    if kind == "pre": return "—"
    if base <= 0: return "CANLI"
    if extra: return f"{base}+{extra}'"
    return f"{base}'"

def kickoff_text(utc):
    if not utc: return "-"
    try:
        dt = datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%H:%M")
    except Exception:
        return "-"

def to_num(v):
    if v is None or isinstance(v, bool): return None
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, str):
        s = v.strip().replace("%", "").replace(",", ".")
        s = re.sub(r"[^\d.\-]", "", s)
        try:
            return float(s) if s not in ("", "-", ".") else None
        except ValueError:
            return None
    return None

def fmt_val(v, digits=2):
    if v is None: return "-"
    n = to_num(v)
    if n is None: return str(v)
    return f"{n:.{digits}f}" if n != int(n) else str(int(n))

def fetch_matches(date_str):
    seen, leagues = {}, 0
    data = get_json("matches", date=date_str)
    for lg in (data.get("leagues") or []):
        leagues += 1
        lname = tr_league(lg.get("name"), lg.get("ccode"))
        for m in (lg.get("matches") or []):
            mid = m.get("id")
            if mid in seen: continue
            st = m.get("status") or {}
            state = minute_state(st)
            home = m.get("home") or {}
            away = m.get("away") or {}
            seen[mid] = {
                "id": mid, "league": lname,
                "home": tr_team(home.get("name") or "?"),
                "away": tr_team(away.get("name") or "?"),
                "hs": home.get("score"), "as": away.get("score"),
                "state": state, "kickoff": kickoff_text(st.get("utcTime")),
                "ts": m.get("timeTS") or 0,
            }
    rows = list(seen.values())
    order = {"min": 0, "ht": 0, "live": 0, "pre": 1, "ft": 2, "cancel": 3}
    rows.sort(key=lambda r: (order.get(r["state"][0], 9), r["ts"], r["league"]))
    return rows, leagues

def flatten_stats(md):
    content = md.get("content") or {}
    stats = content.get("stats") or {}
    periods = stats.get("Periods") or {}
    block = periods.get("All") or periods.get("all")
    groups = block.get("stats") if isinstance(block, dict) else block

    out = []
    for g in groups or []:
        if not isinstance(g, dict): continue
        g_en = g.get("title") or g.get("key") or ""
        items = g.get("stats")
        if not isinstance(items, list): continue
        for s in items:
            if not isinstance(s, dict): continue
            t_en = s.get("title") or s.get("key")
            hv = av = None
            vals = s.get("stats")
            if isinstance(vals, list) and len(vals) >= 2:
                hv, av = vals[0], vals[1]
            elif "home" in s or "away" in s:
                hv, av = s.get("home"), s.get("away")
            if t_en and (hv is not None or av is not None):
                out.append({"group": tr_group(g_en), "title": tr_stat(str(t_en)),
                            "en": str(t_en).lower(), "home": hv, "away": av})
    return out

def fetch_match(match_id):
    md = get_json("matchDetails", matchId=match_id)
    header = md.get("header") or {}
    general = md.get("general") or {}
    status = header.get("status") or {}
    return {
        "teams": header.get("teams") or [],
        "league": tr_league(general.get("leagueName"), general.get("countryCode", "")[:3]),
        "state": minute_state(status),
        "rows": flatten_stats(md),
    }

def team_pair(rows, *need, exclude=()):
    for r in rows:
        k = r.get("en") or ""
        if all(n in k for n in need) and not any(e in k for e in exclude):
            return to_num(r["home"]), to_num(r["away"])
    return None, None

def metrics(rows):
    ch, ca = team_pair(rows, "corner")
    xh, xa = team_pair(rows, "expected goal", exclude=("on target", "per shot", "average"))
    ph, pa = team_pair(rows, "possession")
    return {
        "corner": (ch or 0) + (ca or 0) if (ch is not None or ca is not None) else None,
        "xg_h": xh, "xg_a": xa,
        "xg_max": max([v for v in (xh, xa) if v is not None], default=None),
        "poss": max(ph, pa) if ph is not None and pa is not None else None,
    }

def predict(data, hs, as_):
    rows = data.get("rows") or []
    if not rows: return None
    state = data.get("state") or ("pre", 0, 0, None)
    
    xh, xa = team_pair(rows, "expected goal", exclude=("on target", "per shot", "average"))
    sh, sa = team_pair(rows, "shots on target")
    ch, ca = team_pair(rows, "corner")
    yh, ya = team_pair(rows, "yellow")
    rh, ra = team_pair(rows, "red card")

    m = 45.0 if state[0] == "ht" else (90.0 if state[0] == "ft" else float(state[1]))
    if m <= 0: m = 1.0
    remaining = max(0.0, 95.0 - m)
    win = min(10.0, remaining)

    xg_tot = (xh or 0) + (xa or 0)
    corn_tot = (ch or 0) + (ca or 0)
    p_goal = 1 - math.exp(-(xg_tot / max(m, 8.0)) * win)
    p_corner = 1 - math.exp(-(corn_tot / max(m, 8.0)) * win)

    sig = []
    if p_goal >= 0.38: sig.append("Gol")
    elif p_goal >= 0.22: sig.append("Gol?")
    if p_corner >= 0.55: sig.append("Korner")
    if rh or ra: sig.append("Kart")

    return {
        "p_goal": p_goal,
        "p_corner": p_corner,
        "xg_proj": (hs or 0) + (as_ or 0) + (xg_tot / max(m, 8.0)) * remaining,
        "corn_proj": corn_tot + (corn_tot / max(m, 8.0)) * remaining,
        "signal": " · ".join(sig) or "-"
    }

# ------------------------------------------------------------------ Arayüz ve Tasarım
st.markdown("""
<style>
    .goal-flash {
        background-color: #1e7d45 !important;
        color: white !important;
        padding: 5px;
        border-radius: 5px;
        transition: background-color 0.5s ease;
    }
    .score-text {
        color: #eb5757;
        font-weight: bold;
        font-size: 1.1em;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚽ Canlı Maç Paneli + İstatistik + Tahmin")

# Üst Filtreleme Paneli (İlk görseldeki gibi)
st.markdown("### FİLTRELEME")
f_col1, f_col2, f_col3, f_col4 = st.columns(4)

with f_col1:
    date_input = st.text_input("Tarih (YYYYMMDD)", datetime.now().strftime("%Y%m%d"))
with f_col2:
    only_live = st.checkbox("Sadece Canlı Maçlar", value=True)
with f_col3:
    min_corner = st.number_input("Min Korner", min_value=0, value=0)
with f_col4:
    min_xg = st.number_input("Min xG", min_value=0.0, value=0.0, step=0.1)

team_search = st.sidebar.text_input("Takım Ara", "").strip().lower()

matches, leagues_count = fetch_matches(date_input)

# Gol Kontrolü ve Flash Hafızası (Session State)
if "prev_scores" not in st.session_state:
    st.session_state.prev_scores = {}
if "flash_matches" not in st.session_state:
    st.session_state.flash_matches = {}

if not matches:
    st.warning("Seçilen tarihte maç bulunamadı veya 'Sadece Canlı' filtresi aktif.")
else:
    filtered_matches = []
    for m in matches:
        if only_live and m["state"][0] not in ("min", "ht", "live"):
            continue
        if team_search and team_search not in m["home"].lower() and team_search not in m["away"].lower():
            continue
        
        # Skor değişimi kontrolü (Gol oldu mu?)
        mid = m["id"]
        curr_score = (m["hs"], m["as"])
        if mid in st.session_state.prev_scores:
            old_score = st.session_state.prev_scores[mid]
            if curr_score != old_score and (curr_score[0] is not None and curr_score[1] is not None):
                # Gol bildirimi yakalandı! 2 saniye yeşil yanıp sönme aktifleşiyor
                st.session_state.flash_matches[mid] = time.time() + 2.0
        st.session_state.prev_scores[mid] = curr_score

        filtered_matches.append(m)

    # Ekran Düzeni: Sol taraf liste, sağ taraf detay/istatistik
    col_list, col_stats = st.columns([1.3, 1])

    with col_list:
        st.subheader(f"📋 Maçlar ({len(filtered_matches)})")
        
        if "selected_match_id" not in st.session_state:
            st.session_state.selected_match_id = filtered_matches[0]["id"] if filtered_matches else None

        for m in filtered_matches:
            mid = m["id"]
            status = minute_text(m['state'])
            hs = m['hs'] if m['hs'] is not None else 0
            as_ = m['as'] if m['as'] is not None else 0
            
            # Flash kontrolü (Gol olduysa yeşil arka plan)
            is_flashing = st.session_state.flash_matches.get(mid, 0) > time.time()
            card_class = "goal-flash" if is_flashing else ""
            
            # Sinyalleri ve istatistikleri çek
            cached_data = get_json("matchDetails", matchId=mid)
            flat_rows = flatten_stats(cached_data) if cached_data else []
            met = metrics(flat_rows)
            pred = predict(cached_data, hs, as_) if cached_data else None
            signal_txt = pred["signal"] if pred else "-"

            # Korner ve xG filtreleri
            if min_corner > 0 and (met["corner"] or 0) < min_corner:
                continue
            if min_xg > 0 and (met["xg_max"] or 0) < min_xg:
                continue

            btn_label = f"[{status}] {m['league']} | {m['home']}  <span class='score-text'>{hs} - {as_বহuans if False else as_}</span>  {m['away']} | Korner: {met['corner'] or '-'} | Sinyal: {signal_txt}"
            
            if st.button(f"[{status}] {m['league']} | {m['home']}  {hs} - {as_}  {m['away']} | 🚩{met['corner'] or '-'} | Sinyal: {signal_txt}", key=f"match_{mid}", use_container_width=True):
                st.session_state.selected_match_id = mid
                st.rerun()

    with col_stats:
        st.subheader("📊 Maç İstatistikleri & Tahmin Motoru")
        active_id = st.session_state.get("selected_match_id")
        
        if active_id:
            match_detail = fetch_match(active_id)
            r_match = next((x for x in matches if x["id"] == active_id), {})
            
            h_name = r_match.get("home", "Ev Sahibi")
            a_name = r_match.get("away", "Deplasman")
            h_score = r_match.get("hs") if r_match.get("hs") is not None else 0
            a_score = r_match.get("as") if r_match.get("as") is not None else 0

            st.markdown(f"### **{h_name}** <span style='color:#eb5757;'>{h_score} - {a_score}</span> **{a_name}**", unsafe_allow_html=True)
            st.caption(f"Lig: {match_detail.get('league')} | Durum: {minute_text(match_detail.get('state'))}")

            tab_stat, tab_pred = st.tabs(["İstatistikler", "Tahmin Motoru"])

            with tab_stat:
                stats_rows = match_detail.get("rows", [])
                if stats_rows:
                    last_group = None
                    for row in stats_rows:
                        g = row.get("group") or ""
                        if g and g != last_group:
                            last_group = g
                            st.markdown(f"**📌 {g}**")
                        hv = fmt_val(row.get('home'))
                        av = fmt_val(row.get('away'))
                        st.markdown(f"`{hv:>5}` &nbsp; **{row.get('title')}** &nbsp; `{av:<5}`")
                else:
                    st.info("Bu maç için henüz istatistik yayınlanmadı.")

            with tab_pred:
                pred = predict(match_detail, h_score, a_score)
                if pred:
                    st.metric("Beklenen Toplam Gol", f"~{pred['xg_proj']:.1f}")
                    st.metric("Beklenen Toplam Korner", f"~{pred['corn_proj']:.0f}")
                    st.write(f"⚽ **10dk İçinde Gol İhtimali:** %{pred['p_goal']*100:.1f}")
                    st.write(f"🚩 **10dk İçinde Korner İhtimali:** %{pred['p_corner']*100:.1f}")
                    st.write(f"🎯 **Sinyaller:** `{pred['signal']}`")
                else:
                    st.info("Tahmin için yeterli veri yok.")
        else:
            st.info("İncelemek için sol listeden bir maça tıklayın.")

# Otomatik sayfa yenileme (Anlık veri ve milisaniyelik takip için)
time.sleep(1)
st.rerun()