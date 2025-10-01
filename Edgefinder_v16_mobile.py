# edgefinder_v9c.py
# Mobile-first dark UI • DK-only (moneyline) • 3-day window • Global DK regions (incl. us2)
# Run Model button (light), BOTH teams + Draw (soccer), Model %, Market %, Edge %, Reason
# PLAY / NEUTRAL / PASS • Sorted by Model Win % • Top-10 toggle • Search
# Robust market matching: accepts h2h / moneyline / match_winner / winner

import os
from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import streamlit as st

APP_TITLE = "📱 EdgeFinder — Mobile (DK)"
REGIONS = "us,us2,uk,eu,au"   # broader regions to catch DK globally
MARKETS_ACCEPTED = {"h2h", "moneyline", "match_winner", "winner"}
ODDS_FORMAT = "decimal"
DAYS_FROM = 3                 # today + next 3 days
BOOKMAKER_KEY = "draftkings"  # match by key in API

# Target sports/competitions
SPORT_KEYS = [
    "americanfootball_nfl",
    "baseball_mlb",
    "basketball_nba",
    "icehockey_nhl",
    # Soccer (major comps):
    "soccer_england_premier_league",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champions_league",
    "soccer_uefa_europa_league",
    "soccer_usa_mls",
    # Euro/World basketball:
    "basketball_euroleague",
    "basketball_eurocup",
    "basketball_fiba",
    # Table Tennis – TT Elite Series:
    "table_tennis_tt_elite_series",
]

SPORT_ICON = {
    "americanfootball_nfl": "🏈 NFL",
    "baseball_mlb": "⚾ MLB",
    "basketball_nba": "🏀 NBA",
    "icehockey_nhl": "🏒 NHL",
    "soccer_england_premier_league": "⚽ EPL",
    "soccer_spain_la_liga": "⚽ La Liga",
    "soccer_italy_serie_a": "⚽ Serie A",
    "soccer_germany_bundesliga": "⚽ Bundesliga",
    "soccer_france_ligue_one": "⚽ Ligue 1",
    "soccer_uefa_champions_league": "⚽ UCL",
    "soccer_uefa_europa_league": "⚽ UEL",
    "soccer_usa_mls": "⚽ MLS",
    "basketball_euroleague": "🏀 EuroLeague",
    "basketball_eurocup": "🏀 EuroCup",
    "basketball_fiba": "🏀 FIBA",
    "table_tennis_tt_elite_series": "🏓 TT Elite",
}

# Simple, transparent model knobs
HOME_ADV_PP = 3.0        # +pp to HOME model win %
CAP_FLOOR = 4.0          # min model %
CAP_CEIL  = 96.0         # max model %
NEUTRAL_EDGE_PP = 0.01   # tiny +/- treated as NEUTRAL

# ---------------- UI / THEME ----------------
st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="centered")
st.markdown("""
<style>
.block-container { padding-top:.75rem; padding-bottom:3rem; }
body, .stApp { background:#0f1117; color:#e9eef6; }
/* Cards */
.card { background:#12161f; border:1px solid #1f2633; border-radius:18px;
        padding:16px 16px 14px; margin-bottom:14px; box-shadow:0 4px 16px rgba(0,0,0,.35); }
.badge{border-radius:999px;padding:6px 12px;font-weight:700}
.badge.play{background:#19c37d;color:#00140b}
.badge.neutral{background:#ffd166;color:#2e2300}
.badge.pass{background:#ff4d4f;color:#2e0000}
.hline{border-top:1px solid rgba(255,255,255,.08);margin:10px 0}
.small{font-size:.9rem;opacity:.95}
.sport{font-weight:700;letter-spacing:.25px;margin-bottom:6px}
.title{font-size:1.05rem;font-weight:800;margin-bottom:8px}
.kv{margin-bottom:6px}.kv b{color:#dbe6f6}
.row-ok{background:linear-gradient(90deg,#0e4429 0%,#003d2f 100%);color:#eafff4}
.row-mid{background:linear-gradient(90deg,#3f2e00 0%,#342600 100%);color:#fff4d6}
.row-bad{background:linear-gradient(90deg,#3d0c0c 0%,#360000 100%);color:#ffeaea}
/* Light primary buttons on dark bg */
div[data-testid="stButton"] > button {
  background:#ffffff !important; color:#0f67ff !important;
  border:1px solid #e6e8ec !important; border-radius:10px !important; font-weight:800 !important;
}
</style>
""", unsafe_allow_html=True)

st.title(APP_TITLE)

with st.sidebar:
    st.subheader("Settings")
    api_key = st.text_input("The Odds API Key", type="password", value=os.getenv("THE_ODDS_API_KEY", ""))
    edge_threshold = st.slider("Min edge % for PLAY", 0.0, 20.0, 3.0, 0.25)
    top10_toggle = st.checkbox("Show Top 10 by Model Win %", value=False)
    search = st.text_input("Filter by team", placeholder="e.g., Arsenal, Napoli, Rams…")
    st.caption("DK odds • Decimal • Next 3 days • One card per game")

c1, c2 = st.columns(2)
run_click = c1.button("▶️ Run Model", use_container_width=True)
ref_click = c2.button("🔄 Refresh", use_container_width=True)

# ---------------- helpers ----------------
def implied_from_decimal(dec):
    try:
        dec = float(dec)
        return 1.0/dec if dec > 0 else None
    except:
        return None

def normalize_probs(vals):
    nums = [v for v in vals if v is not None]
    s = sum(nums)
    if s <= 0:
        return vals
    return [(v/s if v is not None else None) for v in vals]

def cap_pct(pct):
    return max(CAP_FLOOR/100.0, min(CAP_CEIL/100.0, pct))

def to_local_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z","+00:00")).astimezone()
        return dt, dt.strftime("%b %d, %Y — %I:%M %p")
    except:
        return None, iso_str

def pick_label(edge_pct, threshold):
    if edge_pct is None:
        return "PASS"
    if abs(edge_pct) < NEUTRAL_EDGE_PP:
        return "NEUTRAL"
    return "PLAY" if edge_pct >= threshold else "PASS"

def row_css(label):
    if label == "PLAY": return "row-ok"
    if label == "NEUTRAL": return "row-mid"
    return "row-bad"

def model_prob_from_market(market_prob, is_home):
    if market_prob is None:
        return None
    bump = (HOME_ADV_PP/100.0) if is_home else 0.0
    return cap_pct(market_prob + bump)

def fetch_sport(sport_key):
    # Note: no fixed 'markets' param; we fetch all markets then match allowed ones.
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "oddsFormat": ODDS_FORMAT,
        "bookmakers": BOOKMAKER_KEY,
        "dateFormat": "iso",
        "daysFrom": DAYS_FROM
    }
    r = requests.get(url, params=params, timeout=30)
    return r

def select_dk_market(bookmakers):
    """Return the first DK market whose key is in MARKETS_ACCEPTED."""
    for bk in bookmakers or []:
        if (bk.get("key") == BOOKMAKER_KEY) or (bk.get("title","").lower().startswith("draftkings")):
            for m in bk.get("markets", []):
                if m.get("key") in MARKETS_ACCEPTED:
                    return m
    return None

# -------------- run guard --------------
if not api_key:
    st.info("Add your **The Odds API** key in the sidebar, then press **Run Model**.")
    st.stop()
if not (run_click or ref_click):
    st.info("Press **Run Model** to fetch DK odds and compute plays.")
    st.stop()

# -------------- fetch + compute --------------
now_local = datetime.now().astimezone()
end_local = now_local + timedelta(days=DAYS
