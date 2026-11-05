# -*- coding: utf-8 -*-
"""
Maçkolik Anlık Canlı Maç ve İstatistik Takip Aracı (Kesintisiz Web Sürümü)
"""

import datetime
import json
import re
import unicodedata
from flask import Flask, jsonify, render_template_string
import cloudscraper
from bs4 import BeautifulSoup

app = Flask(__name__)

BASE = "https://www.mackolik.com/perform/p0/ajax/components/competition/livescores/json"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)
scraper.headers.update({
    "User-Agent": UA,
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
})

def norm(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold().replace("ı", "i").strip()

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

def parse_matches(payload):
    data = payload.get("data") or payload
    competitions = data.get("competitions") or {}
    found = []
    find_match_objects(data, found)

    unique = {}
    for event in found:
        match_id = str(event.get("id") or event.get("rbId") or "")
        if not match_id or match_id in unique:
            continue

        competition_id = event.get("competitionId")
        competition = competitions.get(competition_id, {}) if isinstance(competitions, dict) else {}
        score = event.get("score") or {}
        home_score = score.get("home", "-")
        away_score = score.get("away", "-")
        
        rb_id = event.get("rbId")
        numeric_id = str(rb_id) if rb_id else re.sub(r"\D", "", str(event.get("id", "")))

        unique[match_id] = {
            "id": match_id,
            "numeric_id": numeric_id,
            "slug": event.get("matchSlug") or "mac",
            "lig": "{} - {}".format(
                (competition.get("country") or {}).get("name", ""),
                competition.get("name", ""),
            ).strip(" -"),
            "saat": event.get("mstUtc", ""),
            "ev": (event.get("homeTeam") or {}).get("name", ""),
            "skor": f"{home_score}-{away_score}",
            "dep": (event.get("awayTeam") or {}).get("name", ""),
            "durum": str(event.get("statusBoxContent") or "CANLI"),
        }
    return list(unique.values())

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
    for key, aliases in STAT_LABELS.items():
        if any(norm(alias) in label for alias in aliases):
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

def fetch_match_stats(match_id, slug):
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

@app.route("/api/data")
def api_data():
    matches = parse_matches(fetch_scores())
    result = []
    for m in matches:
        stats = fetch_match_stats(m["numeric_id"], m["slug"])
        
        def fmt(k):
            v = stats.get(k)
            if not v or len(v) != 2: return "-"
            l, r = v
            return f"{l:g}% - {r:g}%" if k == "possession" else f"{l:g} - {r:g} ({l+r:g})"

        result.append({
            "lig": m["lig"],
            "durum": m["durum"],
            "ev": m["ev"],
            "skor": m["skor"],
            "dep": m["dep"],
            "korner": fmt("corners"),
            "sut": fmt("shots"),
            "isabetli": fmt("shots_on"),
            "faul": fmt("fouls"),
            "topa_sahip": fmt("possession"),
            "sari": fmt("yellow_cards"),
            "kirmizi": fmt("red_cards"),
        })
    return jsonify(result)

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Maçkolik Anlık Canlı Takip</title>
        <meta charset="utf-8">
        <style>
            body { background: #141821; color: #e8ecf4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; }
            h2 { color: #00ffcc; text-align: center; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; background: #1c2230; }
            th, td { padding: 10px; text-align: center; border-bottom: 1px solid #26304a; font-size: 14px; }
            th { background: #26304a; color: white; }
            tr:hover { background: #222b3d; }
            .live { color: #00ff88; font-weight: bold; }
        </style>
    </head>
    <body>
        <h2>⚽ Maçkolik Canlık Anlık Takip (Milisaniyelik Yenileme)</h2>
        <p id="status" style="text-align: center; color: #9fb3d1;">Veriler yükleniyor...</p>
        <table>
            <thead>
                <tr>
                    <th>Lig</th>
                    <th>Durum</th>
                    <th>Ev Sahibi</th>
                    <th>Skor</th>
                    <th>Deplasman</th>
                    <th>Korner</th>
                    <th>Şut</th>
                    <th>İsabetli Şut</th>
                    <th>Faul</th>
                    <th>Topla Oynama</th>
                    <th>Sarı</th>
                    <th>Kırmızı</th>
                </tr>
            </thead>
            <tbody id="match-table"></tbody>
        </table>

        <script>
            function updateData() {
                fetch('/api/data')
                    .then(response => response.json())
                    .then(data => {
                        let tbody = document.getElementById('match-table');
                        tbody.innerHTML = '';
                        data.forEach(m => {
                            let tr = document.createElement('tr');
                            tr.innerHTML = `
                                <td>${m.lig}</td>
                                <td class="live">${m.durum}</td>
                                <td><b>${m.ev}</b></td>
                                <td style="color: #ffcc00; font-weight: bold; font-size: 16px;">${m.skor}</td>
                                <td><b>${m.dep}</b></td>
                                <td>${m.korner}</td>
                                <td>${m.sut}</td>
                                <td>${m.isabetli}</td>
                                <td>${m.faul}</td>
                                <td>${m.topa_sahip}</td>
                                <td>${m.sari}</td>
                                <td>${m.kirmizi}</td>
                            `;
                            tbody.appendChild(tr);
                        });
                        document.getElementById('status').innerText = "Son Güncelleme: " + new Date().toLocaleTimeString() + " (Anlık Senkronize)";
                    }).catch(err => console.log(err));
            }

            // Her 2 saniyede bir arka planda sayfayı yenilemeden veriyi tazele
            setInterval(updateData, 2000);
            updateData();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)