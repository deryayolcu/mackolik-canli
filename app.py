# -*- coding: utf-8 -*-
"""
canli_mac.py — Streamlit Canlı Maç Paneli + İstatistik Filtresi + Tahmin Motoru
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
    "long ball accuracy": "Uzun top isabet oranı",
    "total crosses": "Toplam orta", "crosses": "Orta",
    "accurate crosses": "İsabetli orta", "cross accuracy": "Orta isabet oranı",
    "final third entries": "Son bölgeye giriş", "throw-ins": "Taç atışı",
    "touches in opposition box": "Rakip ceza sahasında topla buluşma",
    "duels": "İkili mücadele", "duels won": "Kazanılan ikili mücadele",
    "ground duels won": "Yerde kazanılan mücadele",
    "aerial duels won": "Havada kazanılan mücadele",
    "dribbles succeeded": "Başarılı çalım",
    "dribble success rate": "Çalım başarı oranı",
    "tackles": "Müdahale", "tackles won": "Kazanılan müdahale",
    "interceptions": "Pas arası", "blocks": "Blok",
    "clearances": "Uzaklaştırma", "recoveries": "Top kazanma",
    "possession lost": "Top kaybı", "saves": "Kurtarış",
    "goalkeeper saves": "Kaleci kurtarışı", "big saves": "Kritik kurtarış",
    "sprints": "Sprint", "touches": "Topla buluşma",
    "total distance": "Toplam mesafe", "distance covered": "Koşulan mesafe",
}

GROUP_TR = {
    "top stats": "ÖNE ÇIKANLAR", "shots": "ŞUTLAR",
    "expected goals": "GOL BEKLENTİSİ", "passes": "PASLAR",
    "duels": "İKİLİ MÜCADELELER", "defending": "SAVUNMA",
    "defensive": "SAVUNMA", "discipline": "DİSİPLİN",
    "goalkeeping": "KALECI", "physical": "FİZİKSEL", "other": "DİĞER",
}

PHRASES = [(re.compile(p, re.I), r) for p, r in [
    (r"\bexpected goals\b", "Gol beklentisi"),
    (r"\bexpected assists\b", "Asist beklentisi"),
    (r"\bbig chances created\b", "Yaratılan büyük fırsat"),
    (r"\bbig chances missed\b", "Kaçırılan büyük fırsat"),
    (r"\bbig chances\b", "Büyük fırsat"),
    (r"\bshots on target\b", "İsabetli şut"),
    (r"\bshots off target\b", "İsabetsiz şut"),
    (r"\bblocked shots\b", "Bloklanan şut"),
    (r"\btotal shots\b", "Toplam şut"),
    (r"\bshots inside (the )?box\b", "Ceza sahası içinden şut"),
    (r"\bshots outside (the )?box\b", "Ceza sahası dışından şut"),
    (r"\bshots\b", "Şut"), (r"\bhit woodwork\b", "Direkten dönen"),
    (r"\baccurate passes\b", "İsabetli pas"),
    (r"\btotal passes\b", "Toplam pas"),
    (r"\bpass accuracy\b", "Pas isabet oranı"),
    (r"\baccurate long balls\b", "İsabetli uzun top"),
    (r"\blong balls\b", "Uzun top"),
    (r"\baccurate crosses\b", "İsabetli orta"),
    (r"\bcrosses\b", "Orta"), (r"\bpasses\b", "Pas"),
    (r"\bduels won\b", "Kazanılan ikili mücadele"),
    (r"\bground duels\b", "Yerde ikili mücadele"),
    (r"\baerial duels\b", "Havada ikili mücadele"),
    (r"\bduels\b", "İkili mücadele"),
    (r"\bdribbles succeeded\b", "Başarılı çalım"),
    (r"\btackles won\b", "Kazanılan müdahale"),
    (r"\btackles\b", "Müdahale"), (r"\binterceptions\b", "Pas arası"),
    (r"\bclearances\b", "Uzaklaştırma"), (r"\brecoveries\b", "Top kazanma"),
    (r"\bpossession lost\b", "Top kaybı"),
    (r"\bpossession\b", "Topla oynama"),
    (r"\bcorners?\b", "Korner"),
    (r"\byellow cards\b", "Sarı kart"), (r"\bred cards\b", "Kırmızı kart"),
    (r"\bfouls\b", "Faul"), (r"\boffsides\b", "Ofsayt"),
    (r"\bsaves\b", "Kurtarış"), (r"\bsprints\b", "Sprint"),
    (r"\btouches\b", "Topla buluşma"),
]]

LEAGUE_TR = {
    "premier league": "İngiltere Premier Lig", "efl championship": "İngiltere Championship",
    "championship": "İngiltere Championship", "laliga": "İspanya La Liga",
    "la liga": "İspanya La Liga", "serie a": "İtalya Serie A",
    "bundesliga": "Almanya Bundesliga", "ligue 1": "Fransa Ligue 1",
    "eredivisie": "Hollanda Eredivisie", "süper lig": "Türkiye Süper Lig",
    "super lig": "Türkiye Süper Lig", "uefa champions league": "Şampiyonlar Ligi",
    "champions league": "Şampiyonlar Ligi", "europa league": "Avrupa Ligi",
}

COUNTRY_TR = {
    "ENG": "İngiltere", "ESP": "İspanya", "ITA": "İtalya", "GER": "Almanya",
    "FRA": "Fransa", "NED": "Hollanda", "POR": "Portekiz", "TUR": "Türkiye",
}

TEAM_TR = {
    "bayern munich": "Bayern Münih", "inter": "Inter", "ac milan": "Milan",
    "atletico madrid": "Atlético Madrid", "tottenham hotspur": "Tottenham",
}


def tr_stat(title):
    if not title: return title
    key = re.sub(r"\s+", " ", title.strip().lower())
    if key in STAT_TR: return STAT_TR[key]
    out = title.strip()
    for pat, rep in PHRASES:
        out = pat.sub(rep, out)
    return out


def tr_group(name):
    if not name: return ""
    key = re.sub(r"\s+", " ", name.strip().lower())
    return GROUP_TR.get(key, tr_stat(name).upper())


def tr_league(name, ccode=""):
    raw = (name or "").strip()
    low = raw.lower()
    if low in LEAGUE_TR: return LEAGUE_TR[low]
    cc = COUNTRY_TR.get((ccode or "").upper())
    return f"{cc} {raw}" if cc else raw


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
    if isinstance(v, str) and "%" in v: return v
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


def _share(a, b):
    a, b = a or 0.0, b or 0.0
    return 0.5 if (a + b) == 0 else a / (a + b)


def predict(data, hs, as_):
    rows = data.get("rows") or []
    if not rows: return None
    state = data.get("state") or ("pre", 0, 0, None)
    
    xh, xa = team_pair(rows, "expected goal", exclude=("on target", "per shot", "average"))
    sh, sa = team_pair(rows, "shots on target")
    tsh, tsa = team_pair(rows, "total shots")
    ph, pa = team_pair(rows, "possession")
    ch, ca = team_pair(rows, "corner")
    yh, ya = team_pair(rows, "yellow")
    rh, ra = team_pair(rows, "red card")
    if sh is None and tsh is not None: sh, sa = tsh, tsa

    m = 45.0 if state[0] == "ht" else (90.0 if state[0] == "ft" else float(state[1]))
    if m <= 0: m = 1.0
    remaining = max(0.0, 95.0 - m)
    win = min(10.0, remaining)

    xg_tot = (xh or 0) + (xa or 0)
    corn_tot = (ch or 0) + (ca or 0)
    yel_tot = (yh or 0) + (ya or 0)
    red_tot = (rh or 0) + (ra or 0)

    p_goal = 1 - math.exp(-(xg_tot / max(m, 8.0)) * win)
    p_corner = 1 - math.exp(-(corn_tot / max(m, 8.0)) * win)
    p_red = min(0.35, 1 - math.exp(-(0.0011 * remaining * (1 + 0.22 * yel_tot))))

    s_xg, s_sot = _share(xh, xa), _share(sh, sa)
    s_pos, s_cor = _share(ph, pa), _share(ch, ca)
    eff_h = 100 * (0.35 * s_xg + 0.25 * s_sot + 0.18 * s_pos + 0.22 * s_cor)
    if all(v is None for v in (xh, xa, sh, sa, ph, pa, ch, ca)): eff_h = 50.0
    eff_a = 100 - eff_h

    hs, as_ = hs or 0, as_ or 0
    sd = hs - as_
    d = (eff_h - 50.0) / 100.0
    p_h = min(0.92, max(0.05, 0.36 + 0.90 * d + 0.14 * sd))
    p_a = min(0.92, max(0.05, 0.36 - 0.90 * d - 0.14 * sd))
    p_d = max(0.02, 1 - p_h - p_a)
    tot = p_h + p_d + p_a
    p_h, p_d, p_a = p_h / tot, p_d / tot, p_a / tot

    lean = "Ev sahibi daha etkili" if eff_h - eff_a > 8 else ("Deplasman daha etkili" if eff_a - eff_h > 8 else "Dengeli maç")
    sig = []
    if p_goal >= 0.38: sig.append("Gol")
    elif p_goal >= 0.22: sig.append("Gol?")
    if p_corner >= 0.55: sig.append("Korner")
    if p_red >= 0.16 or red_tot: sig.append("Kart")

    return {
        "eff_h": eff_h, "eff_a": eff_a, "lean": lean,
        "p_goal": p_goal, "p_corner": p_corner, "p_red": p_red,
        "xg_proj": (hs + as_) + (xg_tot / max(m, 8.0)) * remaining,
        "corn_proj": corn_tot + (corn_tot / max(m, 8.0)) * remaining,
        "p_h": p_h, "p_d": p_d, "p_a": p_a,
        "signal": " · ".join(sig) or "-",
    }


# ------------------------------------------------------------------ Arayüz
st.title("⚽ Canlı Maç Paneli + İstatistik + Tahmin")

# Sidebar Ayarları
st.sidebar.header("Kontroller ve Filtreler")
date_input = st.sidebar.text_input("Tarih (YYYYMMDD)", datetime.now().strftime("%Y%m%d"))
only_live = st.sidebar.checkbox("Sadece Canlı Maçlar", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("Filtreleme")
f_min_corner = st.sidebar.number_input("Min Korner", min_value=0, max_value=30, value=0)
f_xg = st.sidebar.number_input("Min xG", min_value=0.0, max_value=10.0, value=0.0, step=0.1)

# Maçları Çek
matches, leagues_count = fetch_matches(date_input)

if not matches:
    st.warning("Seçilen tarihte maç bulunamadı veya 'Sadece Canlı' filtresi aktif. Tarihi kontrol edin.")
else:
    # Filtreleme Uygula
    filtered_matches = []
    for m in matches:
        if only_live and m["state"][0] not in ("min", "ht", "live"):
            continue
        
        # İstatistik bazlı filtreler için detay çekmek gerekir ancak performans için temel filtreler:
        filtered_matches.append(m)

    st.sidebar.info(f"Toplam {len(matches)} maçtan {len(filtered_matches)} tanesi listeleniyor.")

    # Maç Seçim Listesi (Selectbox)
    match_options = {f"{m['league']} | {m['home']} {m['hs'] if m['hs'] is not None else '-'} - {m['as'] if m['as'] is not None else '-'} {m['away']} ({minute_text(m['state'])})": m['id'] for m in filtered_matches}
    
    if match_options:
        selected_label = st.selectbox("İncelenecek Maçı Seçin:", list(match_options.keys()))
        selected_id = match_options[selected_label]

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("📊 Maç İstatistikleri")
            match_detail = fetch_match(selected_id)
            
            # Üst Skor Paneli
            teams = match_detail.get("teams", [])
            if len(teams) >= 2:
                h_name, a_name = teams[0].get("name"), teams[1].get("name")
                h_score, a_score = teams[0].get("score", 0), teams[1].get("score", 0)
            else:
                r_match = next((x for x in matches if x["id"] == selected_id), {})
                h_name, a_name = r_match.get("home", ""), r_match.get("away", "")
                h_score, a_score = r_match.get("hs", 0), r_match.get("as", 0)

            st.markdown(f"### **{h_name}** `{h_score} - {a_score}` **{a_name}**")
            st.caption(f"Lig: {match_detail.get('league')} | Durum: {minute_text(match_detail.get('state'))}")

            stats_rows = match_detail.get("rows", [])
            if stats_rows:
                last_group = None
                for row in stats_rows:
                    g = row.get("group") or ""
                    if g and g != last_group:
                        last_group = g
                        st.markdown(f"**--- {g} ---**")
                    
                    hv, av = row.get("home"), row.get("away")
                    st.text(f"{fmt_val(hv)} | {row.get('title')} | {fmt_val(av)}")
            else:
                st.info("Bu maç için henüz istatistik yayınlanmadı.")

        with col2:
            st.subheader("🔮 Tahmin Motoru")
            pred = predict(match_detail, h_score, a_score)
            if pred:
                st.metric("Ev Sahibi Etkinlik", f"%{pred['eff_h']:.1f}")
                st.metric("Deplasman Etkinlik", f"%{pred['eff_a']:.1f}")
                st.write(f"**Durum:** {pred['lean']}")
                st.markdown("---")
                st.write(f"⚽ **Gol İhtimali (10dk):** %{pred['p_goal']*100:.1f}")
                st.write(f"🚩 **Korner İhtimali (10dk):** %{pred['p_corner']*100:.1f}")
                st.write(f"🚨 **Kırmızı Kart:** %{pred['p_red']*100:.1f}")
                st.markdown("---")
                st.write(f"📈 **Maç Sonu Projeksiyonu:**")
                st.write(f"• Toplam Gol: ~{pred['xg_proj']:.1f}")
                st.write(f"• Toplam Korner: ~{pred['corn_proj']:.0f}")
                st.write(f"🎯 **Sinyaller:** `{pred['signal']}`")
            else:
                st.info("Tahmin için yeterli veri yok.")
    else:
        st.warning("Filtrelere uygun maç bulunamadı.")