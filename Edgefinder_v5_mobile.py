# EdgeFinder v5 — Mobile Edition (DK-only, 2-day window)
# One row per matchup • Vertical cards • Color-coded Play/Pass
# Search bar • Local timestamps • Supports major leagues + TT Elite

import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# -------------------- Config --------------------
API_KEY   = "0ad4039785b38ae45104ee6eba0e90e4"  # The Odds API key you provided
BASE      = "https://api.the-odds-api.com/v4/sports"
BOOKMAKER = "draftkings"
MARKET    = "h2h"          # moneyline / 3-way for soccer
REGIONS   = "us"
ODDS_FMT  = "decimal"
LOCAL_TZ  = "America/Toronto"   # display times

SPORTS = {
    # Soccer (3-way with potential Draw)
    "⚽ EPL": "soccer_epl",
    "⚽ La Liga": "soccer_spain_la_liga",
    "⚽ Serie A": "soccer_italy_serie_a",
    "⚽ Bundesliga": "soccer_germany_bundesliga",
    "⚽ Ligue 1": "soccer_france_ligue_one",
    "⚽ UCL": "soccer_uefa_champs_league",
    "⚽ UEL": "soccer_uefa_europa_league",
    # Major US sports (2-way)
    "🏀 NBA": "basketball_nba",
    "🏈 NFL": "americanfootball_nfl",
    "🏒 NHL": "icehockey_nhl",
    "⚾ MLB": "baseball_mlb",
    # Euro/LatAm/World hoops (2-way)
    "🏀 EuroLeague": "basketball_euroleague",
    "🏀 EuroCup": "basketball_eurocup",
    "🏀 Spain ACB": "basketball_spain_liga_acb",
    "🏀 Italy Lega A": "basketball_italy_lega_a",
    "🏀 Germany BBL": "basketball_germany_bbl",
    "🏀 France LNB": "basketball_france_lnb",
    # Table Tennis
    "🏓 TT Elite Series": "table-tennis_tt-elite-series",
}

SOCCER_PREFIX = "soccer_"

# -------------------- Page / Styles --------------------
st.set_page_config(page_title="EdgeFinder v5 — Mobile", layout="centered")

st.markdown("""
<style>
:root { --bg:#0f1116; --card:#161a22; --soft:#222735; --txt:#e8eaed; --muted:#9aa0a6; }
html, body, [class*="main"] { background:var(--bg); color:var(--txt); }
.block-container { padding-top: 1rem; padding-bottom: 3rem; }
.card { background:var(--card); border:1px solid var(--soft); border-radius:14px; padding:14px; margin-bottom:12px; }
.badge { padding:6px 10px; border-radius:8px; font-weight:800; color:#fff; }
.play { background:#12B886; }
.neutral { background:#FFD43B; color:#111; }
.pass { background:#FA5252; }
.hrow { display:flex; justify-content:space-between; align-items:center; }
.league { font-size:14px; color:#b6beca; }
.match { font-size:18px; font-weight:800; color:#fff; margin:6px 0 4px; }
.kv { font-size:14px; color:#e6e9ee; }
.meta { font-size:12px; color:#9aa0a6; margin-top:4px; }
.note { font-size:12px; color:#b6beca; }
.updated { color:#9aa0a6; font-size:12px; margin-bottom:8px; }
</style>
""", unsafe_allow_html=True)

st.title("🎯 EdgeFinder — Mobile (DK)")
now_local = datetime.now(ZoneInfo(LOCAL_TZ))
st.markdown(f'<div class="updated">Updated: {now_local:%b %d, %Y — %I:%M %p %Z}</div>', unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Filters")
    leagues = st.multiselect("Leagues", list(SPORTS.keys()), default=list(SPORTS.keys()))
    play_thr = st.slider("Play threshold (Edge ≥ %)", 1.0, 12.0, 5.0, 0.5)
    neutral_band = st.slider("Neutral band (±%)", 0.0, 6.0, 3.0, 0.5,
                             help="|Edge| ≤ band → Neutral; else Pass unless ≥ Play threshold")
    top_only = st.toggle("Show Top Plays Only", value=False)
    search = st.text_input("Search teams/league/matchup", "")
    run = st.button("Run Model")

# -------------------- Helpers --------------------
def fetch_odds_board(sport_key: str):
    url = f"{BASE}/{sport_key}/odds"
    params = dict(
        apiKey=API_KEY, regions=REGIONS, markets=MARKET,
        bookmakers=BOOKMAKER, oddsFormat=ODDS_FMT, dateFormat="iso"
    )
    r = requests.get(url, params=params, timeout=25)
    if r.status_code != 200:
        return []
    return r.json()

def within_2_days(commence_iso: str):
    try:
        t_utc = datetime.fromisoformat(commence_iso.replace("Z","+00:00"))
    except Exception:
        return False, None
    now_utc = datetime.now(timezone.utc)
    return (now_utc <= t_utc <= now_utc + timedelta(days=2)), t_utc.astimezone(ZoneInfo(LOCAL_TZ))

def implied_from_decimal(odds):
    try:
        odds = float(odds)
        return 1.0/odds if odds > 0 else 0.0
    except: return 0.0

def normalize(d: dict):
    s = sum(d.values())
    return {k:(v/s if s>0 else 0.0) for k,v in d.items()}

def model_probs_from_market(implied: dict, soccer: bool):
    """
    Simple baseline: start from market-implied probs, apply small home nudge, renormalize.
    (You can swap in your heavier model here later.)
    """
    p = normalize(implied.copy())
    nudge = 0.03 if soccer else 0.04
    if "home" in p and "away" in p:
        p["home"] = max(0.0, p["home"] + nudge)
        p["away"] = max(0.0, p["away"] - nudge)
    return normalize(p)

def build_row(label, game, soccer, play_thr, neutral_band):
    ok, start_local = within_2_days(game.get("commence_time",""))
    if not ok: return None

    home = game.get("home_team","")
    away = game.get("away_team","")

    # DraftKings market
    dk = next((b for b in game.get("bookmakers",[]) if b.get("key")==BOOKMAKER), None)
    if not dk: return None
    mkt = next((m for m in dk.get("markets",[]) if m.get("key")==MARKET), None)
    if not mkt: return None

    prices = {"home":None,"away":None,"draw":None}
    for o in mkt.get("outcomes",[]):
        name = (o.get("name") or "").strip().lower()
        price = o.get("price")
        if name == home.lower(): prices["home"] = float(price)
        elif name == away.lower(): prices["away"] = float(price)
        elif name == "draw":      prices["draw"] = float(price)

    if prices["home"] is None or prices["away"] is None:
        return None
    if not soccer:
        prices.pop("draw", None)

    implied = {k: implied_from_decimal(v) for k,v in prices.items() if v}
    implied = normalize(implied)
    model  = model_probs_from_market(implied, soccer)

    # Market favorite (lowest odds)
    fav_key = min(prices, key=lambda k: prices[k] if prices[k] else 1e9)
    fav_name = home if fav_key=="home" else (away if fav_key=="away" else "Draw")
    fav_odds = prices[fav_key]

    # Model favorite (between home/away only)
    model_fav = home if model.get("home",0) >= model.get("away",0) else away

    # Edge = model - implied (pick the best offered outcome)
    edges = {k: (model.get(k,0)-implied.get(k,0))*100 for k in implied.keys()}
    pick_key = max(edges, key=lambda k: edges[k])
    pick_team = {"home":home,"away":away,"draw":"Draw"}[pick_key]
    pick_odds = prices[pick_key]
    pick_edge = round(edges[pick_key], 2)

    # Recommendation
    if pick_edge >= play_thr:
        rec, css = "PLAY", "play"
    elif abs(pick_edge) <= neutral_band:
        rec, css = "NEUTRAL", "neutral"
    else:
        rec, css = "PASS", "pass"

    return {
        "League": label,
        "Matchup": f"{home} vs {away}",
        "DK Favorite": f"{fav_name} ({fav_odds:.2f})",
        "Model Favorite": model_fav,
        "Pick": f"{pick_team} ({pick_odds:.2f})",
        "Edge %": pick_edge,
        "Recommendation": rec,
        "Class": css,
        "Start": start_local.strftime("%b %d, %Y — %I:%M %p %Z"),
        "_blob": f"{label} {home} {away} {fav_name} {model_fav} {pick_team}"
    }

def render_card(r: dict):
    st.markdown(f"""
    <div class="card">
      <div class="hrow">
        <div class="league">{r['League']}</div>
        <div class="badge {r['Class']}">{r['Recommendation']}</div>
      </div>
      <div class="match">{r['Matchup']}</div>
      <div class="kv"><b>DK Favorite:</b> {r['DK Favorite']}</div>
      <div class="kv"><b>Model Favorite:</b> {r['Model Favorite']}</div>
      <div class="kv"><b>Pick:</b> {r['Pick']} &nbsp;•&nbsp; <b>Edge:</b> {r['Edge %']:.1f}%</div>
      <div class="meta">Start: {r['Start']}</div>
    </div>
    """, unsafe_allow_html=True)

# -------------------- Run --------------------
if run:
    results = []
    for label in leagues:
        sport_key = SPORTS[label]
        soccer = sport_key.startswith(SOCCER_PREFIX)
        try:
            board = fetch_odds_board(sport_key)
        except Exception:
            board = []
        for g in board:
            row = build_row(label, g, soccer, play_thr, neutral_band)
            if not row:
                continue
            if top_only and row["Recommendation"] != "PLAY":
                continue
            if search and search.strip().lower() not in row["_blob"].lower():
                continue
            results.append(row)

    if not results:
        st.info("No games found for the next 2 days (or DraftKings odds not posted yet).")
    else:
        # best edges first
        results = sorted(results, key=lambda x: x["Edge %"], reverse=True)
        for r in results:
            render_card(r)
else:
    st.info("Pick leagues, set thresholds, then press **Run Model**. We’ll fetch DraftKings odds and compute edges.")
