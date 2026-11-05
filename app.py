# -*- coding: utf-8 -*-
"""
canli_mac.py — Streamlit Canlı Maç Paneli + Alt Alta Liste ve Yan Yana İstatistikler
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

@st.cache_data(ttl=5)
def get_json(path, **params):
    try:
        r = requests.get(BASE + path, headers=HEADERS, params=params, timeout=10)
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

def predict(data, hs, as_):
    rows = data.get("rows") or []
    if not rows: return None
    state = data.get("state") or ("pre", 0, 0, None)
    
    xh, xa = team_pair(rows, "expected goal", exclude=("on target", "per shot", "average"))
    sh, sa = team_pair(rows, "shots on target")
    ch, ca = team_pair(rows, "corner")
    
    m = 45.0 if state[0] == "ht" else (90.0 if state[0] == "ft" else float(state[1]))
    if m <= 0: m = 1.0
    remaining = max(0.0, 95.0 - m)
    win = min(10.0, remaining)

    xg_tot = (xh or 0) + (xa or 0)
    corn_tot = (ch or 0) + (ca or 0)
    p_goal = 1 - math.exp(-(xg_tot / max(m, 8.0)) * win)
    p_corner = 1 - math.exp(-(corn_tot / max(m, 8.0)) * win)

    return {
        "p_goal": p_goal,
        "p_corner": p_corner,
        "xg_proj": (hs or 0) + (as_ or 0) + (xg_tot / max(m, 8.0)) * remaining,
        "corn_proj": corn_tot + (corn_tot / max(m, 8.0)) * remaining,
    }

# ------------------------------------------------------------------ Arayüz
st.title("⚽ Canlı Maçlar ve Canlı İstatistik Paneli")

# Sidebar - Arama ve Filtreler
st.sidebar.header("Filtreleme Seçenekleri")
date_input = st.sidebar.text_input("Tarih (YYYYMMDD)", datetime.now().strftime("%Y%m%d"))
only_live = st.sidebar.checkbox("Sadece Canlı Maçları Göster", value=True)
team_search = st.sidebar.text_input("Takım Ara (Filtrele)", "").strip().lower()

matches, leagues_count = fetch_matches(date_input)

if not matches:
    st.warning("Seçilen tarihte maç bulunamadı veya 'Sadece Canlı' filtresi aktif. Tarihi güncelleyin.")
else:
    # Filtreleme mantığı
    filtered_matches = []
    for m in matches:
        if only_live and m["state"][0] not in ("min", "ht", "live"):
            continue
        if team_search and team_search not in m["home"].lower() and team_search not in m["away"].lower():
            continue
        filtered_matches.append(m)

    # Ekranı iki ana sütuna bölelim: Sol taraf maç listesi (alt alta), sağ taraf seçilen maçın istatistikleri
    col_list, col_stats = st.columns([1.2, 1])

    with col_list:
        st.subheader(f"📋 Maçlar ({len(filtered_matches)})")
        
        if "selected_match_id" not in st.session_state:
            st.session_state.selected_match_id = filtered_matches[0]["id"] if filtered_matches else None

        if not filtered_matches:
            st.info("Kriterlere uygun maç bulunamadı.")
        else:
            # Alt alta sıralı maç butonları/kartları
            for m in filtered_matches:
                status_label = minute_text(m['state'])
                hs_val = m['hs'] if m['hs'] is not None else "-"
                as_val = m['as'] if m['as'] is not None else "-"
                
                # Seçili olan maçı görsel olarak vurgulamak için etiket belirleme
                is_selected = st.session_state.selected_match_id == m['id']
                prefix = "👉 " if is_selected else "⚽ "
                
                label = f"{prefix} [{status_label}] {m['league']} | {m['home']}  **{hs_val} - {as_val}**  {m['away']}"
                
                if st.button(label, key=f"btn_match_{m['id']}", use_container_width=True):
                    st.session_state.selected_match_id = m['id']
                    st.rerun()

    with col_stats:
        st.subheader("📊 Maç İstatistikleri & Tahmin")
        
        active_id = st.session_state.get("selected_match_id")
        if active_id:
            match_detail = fetch_match(active_id)
            r_match = next((x for x in matches if x["id"] == active_id), {})
            
            h_name = r_match.get("home", "Ev Sahibi")
            a_name = r_match.get("away", "Deplasman")
            h_score = r_match.get("hs", 0) if r_match.get("hs"] is not None else 0
            a_score = r_match.get("as", 0) if r_match.get("as"] is not None else 0

            st.markdown(f"### **{h_name}** `{h_score} - {a_score}` **{a_name}**")
            st.caption(f"Lig: {match_detail.get('league')} | Durum: {minute_text(match_detail.get('state'))}")

            # Sekmeler veya doğrudan alt alta görünüm
            tab_stat, tab_pred = st.tabs(["İstatistikler", "Tahminler"])

            with tab_stat:
                stats_rows = match_detail.get("rows", [])
                if stats_rows:
                    last_group = None
                    for row in stats_rows:
                        g = row.get("group") or ""
                        if g and g != last_group:
                            last_group = g
                            st.markdown(f"**📌 {g}**")
                        
                        # İstatistik değerlerini yan yana düzgün yazdırma
                        hv = fmt_val(row.get('home'))
                        av = fmt_val(row.get('away'))
                        title = row.get('title')
                        st.markdown(f"`{hv:>5}` &nbsp; **{title}** &nbsp; `{av:<5}`")
                else:
                    st.info("Bu maç için henüz istatistik yayınlanmadı.")

            with tab_pred:
                pred = predict(match_detail, h_score, a_score)
                if pred:
                    st.metric("Beklenen Toplam Gol (Maç Sonu)", f"~{pred['xg_proj']:.1f}")
                    st.metric("Beklenen Toplam Korner", f"~{pred['corn_proj']:.0f}")
                    st.write(f"⚽ **10dk İçinde Gol İhtimali:** %{pred['p_goal']*100:.1f}")
                    st.write(f"🚩 **10dk İçinde Korner İhtimali:** %{pred['p_corner']*100:.1f}")
                else:
                    st.info("Tahmin için yeterli veri yok.")
        else:
            st.info("İncelemek için sol listeden bir maça tıklayın.")