# -*- coding: utf-8 -*-
"""
canli_mac.py — Streamlit Sıkılaştırılmış Kompakt Masaüstü Görünümü + xG Filtresi + Skor Tıklama
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

ALLOWED_STATS = {
    "ball possession", "possession", "expected goals (xg)", "expected goals", "xg",
    "total shots", "shots", "shots on target", "corners", "corner kicks",
    "fouls", "yellow cards", "red cards", "big chances"
}

STAT_TR = {
    "ball possession": "Topla oynama", "possession": "Topla oynama",
    "expected goals (xg)": "Gol beklentisi (xG)", "expected goals": "Gol beklentisi",
    "xg": "Gol beklentisi (xG)", "big chances": "Büyük fırsat",
    "goals": "Gol", "assists": "Asist", "corners": "Korner", "fouls": "Faul",
    "yellow cards": "Sarı kart", "red cards": "Kırmızı kart",
    "total shots": "Toplam şut", "shots": "Şut", "shots on target": "İsabetli şut",
}

GROUP_TR = {
    "top stats": "ÖNE ÇIKANLAR", "shots": "ŞUTLAR",
    "expected goals": "GOL BEKLENTİSİ", "discipline": "DİSİPLİN"
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

@st.cache_data(ttl=3)
def get_json(path, **params):
    try:
        r = requests.get(BASE + path, headers=HEADERS, params=params, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

def minute_state(st_dict):
    if st_dict.get("cancelled"): return ("cancel", 0, 0, None)
    if st_dict.get("finished"): return ("ft", 0, 0, None)
    reason = ((st_dict.get("reason") or {}).get("short") or "").upper()
    if reason in ("HT", "BT", "HALF"): return ("ht", 0, 0, None)

    lt = st_dict.get("liveTime") or {}
    short = str(lt.get("short") or "").replace("\u2019", "'")
    m = MIN_RE.search(short)
    base = int(m.group(1)) if m else None
    extra = int(m.group(2) or 0) if m else 0
    if base is None:
        mt = lt.get("maxTime")
        if isinstance(mt, (int, float)): base = int(mt)
    if base is None:
        return ("min", 0, 0, None) if st_dict.get("started") else ("pre", 0, 0, None)
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

def fetch_matches(date_str, only_live=True):
    seen, leagues = {}, 0
    data = get_json("matches", date=date_str)
    for lg in (data.get("leagues") or []):
        leagues += 1
        lname = tr_league(lg.get("name"), lg.get("ccode"))
        for m in (lg.get("matches") or []):
            mid = m.get("id")
            if mid in seen: continue
            st_dict = m.get("status") or {}
            state = minute_state(st_dict)
            
            if only_live and state[0] not in ("min", "ht", "live"):
                continue
                
            home = m.get("home") or {}
            away = m.get("away") or {}
            seen[mid] = {
                "id": mid, "league": lname,
                "home": tr_team(home.get("name") or "?"),
                "away": tr_team(away.get("name") or "?"),
                "hs": home.get("score"), "as": away.get("score"),
                "state": state, "kickoff": kickoff_text(st_dict.get("utcTime")),
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
            t_en = str(s.get("title") or s.get("key") or "").lower()
            if t_en not in ALLOWED_STATS: continue

            hv = av = None
            vals = s.get("stats")
            if isinstance(vals, list) and len(vals) >= 2:
                hv, av = vals[0], vals[1]
            elif "home" in s or "away" in s:
                hv, av = s.get("home"), s.get("away")
            if t_en and (hv is not None or av is not None):
                out.append({"group": tr_group(g_en), "title": tr_stat(str(s.get("title") or s.get("key"))),
                            "en": t_en, "home": hv, "away": av})
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

# ------------------------------------------------------------------ CSS Sıkılaştırılmış Kompakt Tasarım
st.markdown("""
<style>
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 0rem !important;
    }
    div[data-testid="column"] {
        padding: 0px 2px !important;
    }
    .score-btn button {
        background-color: #eb5757 !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 3px !important;
        border: none !important;
        padding: 0px 6px !important;
        height: 22px !important;
        min-height: 22px !important;
        font-size: 12px !important;
    }
    .score-btn button:hover {
        background-color: #d64545 !important;
    }
    p, span, div, label {
        font-size: 12px !important;
        margin-bottom: 0px !important;
        padding-bottom: 0px !important;
    }
    hr {
        margin: 2px 0px !important;
        border-color: #262730 !important;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ ÜST FİLTRE PANELİ
st.markdown("### ⚽ Canlı Maç Paneli")

if "date_val" not in st.session_state: st.session_state.date_val = datetime.now().strftime("%Y%m%d")
if "only_live_val" not in st.session_state: st.session_state.only_live_val = True
if "c_min" not in st.session_state: st.session_state.c_min = 0
if "c_max" not in st.session_state: st.session_state.c_max = 0
if "xg_val" not in st.session_state: st.session_state.xg_val = 0.0

with st.container():
    c1, c2, c3, c4, c5 = st.columns([1, 0.8, 1.2, 1.2, 0.8])
    with c1:
        date_input = st.text_input("Tarih", st.session_state.date_val)
    with c2:
        only_live = st.checkbox("Sadece canlı", st.session_state.only_live_val)
    with c3:
        cc1, cc2 = st.columns(2)
        with cc1:
            f_corner_min = st.number_input("Korner min", min_value=0, value=st.session_state.c_min)
        with cc2:
            f_corner_max = st.number_input("Korner max", min_value=0, value=st.session_state.c_max)
    with c4:
        f_xg = st.number_input("Gol beklentisi (≥ xG)", min_value=0.0, value=st.session_state.xg_val, step=0.1)
    with c5:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🧹 Temizle", use_container_width=True):
            st.session_state.date_val = datetime.now().strftime("%Y%m%d")
            st.session_state.only_live_val = True
            st.session_state.c_min = 0
            st.session_state.c_max = 0
            st.session_state.xg_val = 0.0
            st.rerun()

st.markdown("---")

matches, leagues_count = fetch_matches(date_input, only_live=only_live)

if not matches:
    st.info("Canlı maç bulunamadı. 'Sadece canlı' işaretini kaldırabilir veya tarihi değiştirebilirsiniz.")
else:
    if "selected_match_id" not in st.session_state:
        st.session_state.selected_match_id = matches[0]["id"] if matches else None

    col_left, col_right = st.columns([2.5, 1])

    with col_left:
        # Sütun Başlıkları (Kompakt)
        h1, h2, h3, h4, h5, h6, h7, h8, h9 = st.columns([2.2, 0.6, 2, 1.0, 2, 0.7, 0.7, 0.7, 1.2])
        h1.markdown("**Lig**")
        h2.markdown("**Dk**")
        h3.markdown("**Ev Sahibi**")
        h4.markdown("**Skor**")
        h5.markdown("**Deplasman**")
        h6.markdown("**Korner**")
        h7.markdown("**xG ev**")
        h8.markdown("**xG dep**")
        h9.markdown("**Sinyal**")
        st.markdown("<hr style='margin: 1px 0 4px 0;'>", unsafe_allow_html=True)

        for m in matches:
            mid = m["id"]
            status = minute_text(m["state"])
            hs = m["hs"] if m["hs"] is not None else 0
            as_ = m["as"] if m["as"] is not None else 0
            score_text = f"{hs} - {as_}"

            cached_data = get_json("matchDetails", matchId=mid)
            flat_rows = flatten_stats(cached_data) if cached_data else []
            met = metrics(flat_rows)
            predict_res = predict(cached_data, hs, as_) if cached_data else None

            if f_corner_min > 0 and (met["corner"] or 0) < f_corner_min: continue
            if f_corner_max > 0 and (met["corner"] or 0) > f_corner_max: continue
            if f_xg > 0 and (met["xg_max"] or 0) < f_xg: continue

            # Sıkılaştırılmış Satır Yerleşimi
            r1, r2, r3, r4, r5, r6, r7, r8, r9 = st.columns([2.2, 0.6, 2, 1.0, 2, 0.7, 0.7, 0.7, 1.2])
            
            r1.write(m["league"][:18])
            r2.write(status)
            r3.write(m["home"])
            
            with r4:
                st.markdown("<div class='score-btn'>", unsafe_allow_html=True)
                if st.button(score_text, key=f"score_{mid}"):
                    st.session_state.selected_match_id = mid
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            r5.write(m["away"])
            r6.write(str(met["corner"]) if met["corner"] is not None else "-")
            r7.write(fmt_val(met["xg_h"]))
            r8.write(fmt_val(met["xg_a"]))
            r9.write(predict_res["signal"] if predict_res else "-")
            
            st.markdown("<hr style='margin: 1px 0;'>", unsafe_allow_html=True)

    with col_right:
        st.markdown("**📊 İstatistikler & Tahmin**")
        active_id = st.session_state.get("selected_match_id")
        
        if active_id:
            match_detail = fetch_match(active_id)
            r_match = next((x for x in matches if x["id"] == active_id), {})
            
            h_name = r_match.get("home", "—")
            a_name = r_match.get("away", "—")
            h_score = r_match.get("hs") if r_match.get("hs") is not None else 0
            a_score = r_match.get("as") if r_match.get("as") is not None else 0

            st.markdown(f"**{h_name}** <span style='color:#eb5757;'>{h_score} - {a_score}</span> **{a_name}**", unsafe_allow_html=True)
            st.caption(f"{match_detail.get('league')} · {minute_text(match_detail.get('state'))}")

            predict_res = predict(match_detail, h_score, a_score)
            if predict_res:
                st.info(f"**Sinyal:** {predict_res['signal']}")
                st.write(f"⚽ **Gol (10dk):** %{predict_res['p_goal']*100:.0f} | 🚩 **Korner:** %{predict_res['p_corner']*100:.0f}")
                st.write(f"📈 **Projeksiyon:** ~{predict_res['xg_proj']:.1f} Gol · ~{predict_res['corn_proj']:.0f} Korner")
            
            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown("**Öne Çıkanlar**")
            stats_rows = match_detail.get("rows", [])
            if stats_rows:
                for row in stats_rows:
                    hv = fmt_val(row.get('home'))
                    av = fmt_val(row.get('away'))
                    st.write(f"**{hv}** | {row.get('title')} | **{av}**")
            else:
                st.warning("İstatistik henüz yok.")