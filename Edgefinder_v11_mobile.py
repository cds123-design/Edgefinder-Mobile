# edgefinder_v8_mobile.py
# EdgeFinder v8 — Mobile (DK only)
# -------------------------------------------------------------
# One row/card per game • DraftKings odds (decimal) • Market vs Model •
# Color-coded PLAY/PASS • Filter + Top-10 • Today + Tomorrow
#
# DATA: The Odds API (https://the-odds-api.com/)
#   Endpoint: /v4/sports, /v4/sports/{sport_key}/odds
#   Params: bookmakers=DraftKings, oddsFormat=decimal
#
# MODEL (transparent, tweakable):
#   Starts from market_implied% = 100 / decimal_odds
#   + home_advantage (sport specific, small)
#   + favorite_bump for short-priced favs (<=1.55)
#   - away_tax (tiny)
#   Capped to [5%, 95%]. Edge = model% - market%.
#
# NOTE: This is a pragmatic baseline so you can scan parlays quickly on mobile.
#       You can raise/lower the edge threshold from the sidebar.

import os
import math
import time
import requests
from datetime import datetime, timedelta, timezone

import streamlit as st
from dateutil import parser as dtparser  # streamlit cloud has python-dateutil

# ---------------------- UI THEME / PAGE ----------------------
st.set_page_config(
    page_title="EdgeFinder v8 — Mobile (DK)",
    page_icon="🎯",
    layout="centered",
)

# Inline CSS to make mobile cards look great (dark mode)
st.markdown("""
<style>
/* Dark container look */
.block-container { padding-top: 1rem; padding-bottom: 4rem; }

/* Big section header */
h1, h2, h3 { color: #e9eef6; }

/* Cards */
.ef-card {
  background: #12161f;
  color: #e9eef6;
  border: 1px solid #1f2633;
  border-radius: 18px;
  padding: 18px 18px 14px 18px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.35);
  margin-bottom: 16px;
}

/* Badge */
.badge {
  float: right;
  font-weight: 800;
  border-radius: 12px;
  padding: 6px 12px;
  font-size: 0.95rem;
}
.badge-play  { background: #14ae5c; color: #07130d; }
.badge-pass  { background: #ff5f5f; color: #2a0b0b; }

/* Subtle label rows */
.ef-label { color:#9fb3c8; font-weight:600; }
.ef-row   { margin: 6px 0; }

/* Mono metrics */
.metric { font-variant-numeric: tabular-nums; }

/* Search input spacing */
div[data-testid="stTextInput"] > div { margin-bottom: 0; }
</style>
""", unsafe_allow_html=True)

# ---------------------- SIDEBAR ----------------------
st.sidebar.header("Settings")
api_key = st.sidebar.text_input("The Odds API Key", value=os.getenv("THE_ODDS_API_KEY", ""), type="password")

edge_threshold = st.sidebar.slider("Min edge % for PLAY", min_value=0.0, max_value=20.0, value=3.0, step=0.5)
top10_only = st.sidebar.checkbox("Show Top 10 by model win %", value=False)
days_ahead = 2  # fixed as requested: today + tomorrow

st.sidebar.caption("• DraftKings odds only • Decimal\n• Today + Tomorrow\n• One card per game")

# ---------------------- CONSTANTS ----------------------
ODDS_BASE = "https://api.the-odds-api.com/v4"
BOOKMAKER = "DraftKings"
ODDS_FMT  = "decimal"

# which sports to try to include from the /v4/sports catalog
WANTED_TITLES_KEYWORDS = {
    "NFL": ["NFL"],
    "NBA": ["NBA"],
    "MLB": ["MLB"],
    "NHL": ["NHL"],
    "SOCCER": ["Soccer", "EPL", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "UEFA", "Champions League"],
    "EU_BASKET": ["EuroLeague", "Eurocup", "LNB", "ACB", "Serie A Basket", "BBL", "VTB", "Basketball Champions League"],
    "LATAM_BASKET": ["Liga Nacional", "BSN", "LUB", "NBB"],
    "WORLD_BASKET": ["Basketball"],  # wide net; later filtered to avoid NBA dup
    "TT_ELITE": ["TT Elite", "Table Tennis"],
}

# home advantage (percentage points) by sport
HOME_ADV = {
    "NFL": 2.0,
    "NBA": 3.0,
    "MLB": 2.0,
    "NHL": 2.0,
    "SOCCER": 3.0,
    "EU_BASKET": 3.0,
    "LATAM_BASKET": 3.0,
    "WORLD_BASKET": 3.0,
    "TT_ELITE": 1.0,
}

# tiny away tax (in percentage points)
AWAY_TAX = 0.5

# favorite bump for short prices (decimal <= 1.55)
SHORT_PRICE = 1.55
FAV_BUMP_PP = 2.0  # percentage points

# ---------------------- HELPERS ----------------------
def to_local(iso_str):
    try:
        dt = dtparser.isoparse(iso_str)
        # Convert to local (Streamlit server tz may be UTC; we'll show local offset-ish):
        return dt.astimezone().strftime("%b %d, %Y — %I:%M %p %Z")
    except Exception:
        return iso_str

def implied_from_decimal(dec):
    try:
        return max(0.0, min(100.0, 100.0 / float(dec)))
    except Exception:
        return None

def cap_pct(p):
    return float(max(5.0, min(95.0, p)))

def best_outcome_from_dk(bookmakers):
    """Return lowest-odds (fav) outcome from DK book for h2h market.
       Also return full outcome list (team/price/home/away/draw flags if possible)."""
    dk = None
    for b in bookmakers:
        if b.get("key","").lower() == BOOKMAKER.lower():
            dk = b
            break
    if not dk:
        return None, []

    # find h2h market
    market = None
    for m in dk.get("markets", []):
        if m.get("key") == "h2h":
            market = m
            break
    if not market:
        return None, []

    outcomes = market.get("outcomes", [])
    # attach role if provided
    for oc in outcomes:
        # odds api sometimes includes "name" or "price". If draw, name can be "Draw"
        oc["price"] = oc.get("price")
    # sort by price (decimal) ascending = favorite first
    try:
        sorted_outcomes = sorted(outcomes, key=lambda x: float(x.get("price", 999)))
    except Exception:
        sorted_outcomes = outcomes

    fav = sorted_outcomes[0] if sorted_outcomes else None
    return fav, sorted_outcomes

def classify_sport_title(title):
    t = (title or "").lower()
    if "nfl" in t: return "NFL"
    if "nba" in t: return "NBA"
    if "mlb" in t: return "MLB"
    if "nhl" in t: return "NHL"
    if "soccer" in t or "premier league" in t or "la liga" in t or "serie a" in t or "bundesliga" in t or "ligue" in t:
        return "SOCCER"
    if "euro" in t or "champions league" in t or "basket" in t:
        # try keep out NBA which we already bucket
        if "nba" in t:
            return "NBA"
        return "EU_BASKET"
    if "tt elite" in t or "table tennis" in t:
        return "TT_ELITE"
    # fallback – world basket
    if "basket" in t:
        return "WORLD_BASKET"
    return None

def model_adjusted_win_prob(market_implied, is_home_fav, is_away, sport_bucket, fav_price=None):
    """Simple transparent adjustments -> returns capped percentage"""
    p = market_implied

    # home advantage (small)
    p += HOME_ADV.get(sport_bucket, 2.0) if is_home_fav else 0.0

    # away tax
    p -= AWAY_TAX if is_away else 0.0

    # short-price favorite bump
    if fav_price is not None and fav_price <= SHORT_PRICE:
        p += FAV_BUMP_PP

    return cap_pct(p)

def pick_reason_line(model_pct, market_pct, edge_pct, team):
    return f"Model projects **{team}** to win **{model_pct:.1f}%** vs market **{market_pct:.1f}%** (**Edge +{edge_pct:.2f}%**)."

# ---------------------- API CALLS ----------------------
def fetch_all_sports():
    params = {"apiKey": api_key, "all": "true"}
    r = requests.get(f"{ODDS_BASE}/sports", params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def within_days(commence_iso, days=2):
    try:
        t = dtparser.isoparse(commence_iso)
        now = datetime.now(timezone.utc)
        return now <= t <= now + timedelta(days=days)
    except Exception:
        return False

def fetch_odds_for_sport(sport_key):
    params = {
        "apiKey": api_key,
        "bookmakers": BOOKMAKER,
        "markets": "h2h",
        "oddsFormat": ODDS_FMT,
        "dateFormat": "iso"
    }
    r = requests.get(f"{ODDS_BASE}/sports/{sport_key}/odds", params=params, timeout=25)
    if r.status_code == 422:
        # sport not available with these params – just skip gracefully
        return []
    r.raise_for_status()
    return r.json()

# ---------------------- MAIN ----------------------
st.title("📱 All Games Sorted by Model Win %")

if not api_key:
    st.info("Add your **The Odds API** key in the sidebar to load games.")
    st.stop()

with st.status("Fetching sports / odds from DraftKings…", expanded=False):
    try:
        catalog = fetch_all_sports()
    except Exception as e:
        st.error(f"Failed to fetch sports list: {e}")
        st.stop()

    # filter catalog by titles we want (and active only)
    wanted = []
    for s in catalog:
        if not s.get("active"): 
            continue
        title = s.get("title","")
        bucket = classify_sport_title(title)
        if not bucket: 
            continue
        # only keep if it matches one of our high-level wanted families
        # we’ll rely on bucket names above to include NBA/MLB/NHL/NFL/SOCCER/basketball/etc.
        wanted.append({
            "key": s.get("key"),
            "title": title,
            "sport_bucket": bucket
        })

    # dedupe by key
    seen = set()
    wanted = [w for w in wanted if not (w["key"] in seen or seen.add(w["key"]))]

    # Collect events
    cards = []
    errors = []

    for w in wanted:
        try:
            events = fetch_odds_for_sport(w["key"])
        except Exception as e:
            errors.append(f"{w['title']}: {e}")
            continue

        for ev in events:
            # time filter: today + tomorrow
            if not within_days(ev.get("commence_time",""), days_ahead):
                continue

            home_team = ev.get("home_team")
            away_team = ev.get("away_team")
            title = ev.get("sport_title", w["title"])
            commence = ev.get("commence_time","")
            bookmakers = ev.get("bookmakers", [])
            fav, outcomes = best_outcome_from_dk(bookmakers)

            if not fav or not outcomes:
                continue

            # Determine DK favorite (lowest decimal)
            fav_name  = fav.get("name")
            fav_price = fav.get("price")

            # Market implied for the favorite
            market_pct = implied_from_decimal(fav_price)
            if market_pct is None:
                continue

            # Figure out if favorite is home/away
            is_home_fav = (fav_name == home_team)
            is_away_fav = (fav_name == away_team)

            # Model pct (apply small transparent adj)
            model_pct = model_adjusted_win_prob(
                market_implied=market_pct,
                is_home_fav=is_home_fav,
                is_away=is_away_fav,   # tax only if fav is away
                sport_bucket=w["sport_bucket"],
                fav_price=fav_price
            )

            edge_pct = model_pct - market_pct

            # PLAY / PASS decision
            recommendation = "PLAY" if edge_pct >= edge_threshold else "PASS"

            # Compose matchup line "Team A vs Team B"
            matchup = f"{home_team} vs {away_team}"

            # Reason
            reason = pick_reason_line(model_pct, market_pct, edge_pct, fav_name)

            # Compose card dict
            cards.append({
                "bucket": w["sport_bucket"],
                "title": title,
                "matchup": matchup,
                "fav_name": fav_name,
                "fav_price": fav_price,
                "market_pct": market_pct,
                "model_pct": model_pct,
                "edge_pct": edge_pct,
                "home_team": home_team,
                "away_team": away_team,
                "commence": commence,
                "recommendation": recommendation,
                "reason": reason
            })

# Sort by model win % desc
cards.sort(key=lambda x: x["model_pct"], reverse=True)

# ---------------------- FILTER BAR ----------------------
q = st.text_input("🔎 Filter by team name", value="", placeholder="Type a team (partial OK)")
if q.strip():
    ql = q.lower().strip()
    cards = [c for c in cards if ql in (c["home_team"] or "").lower() or ql in (c["away_team"] or "").lower() or ql in (c["fav_name"] or "").lower()]

if top10_only:
    cards = cards[:10]

# Header row: last updated
st.caption(f"Updated: {datetime.now().astimezone().strftime('%b %d, %Y — %I:%M %p %Z')}")

# ---------------------- RENDER CARDS ----------------------
SPORT_EMOJI = {
    "NFL":"🏈","NBA":"🏀","MLB":"⚾️","NHL":"🏒","SOCCER":"⚽️",
    "EU_BASKET":"🏀","LATAM_BASKET":"🏀","WORLD_BASKET":"🏀",
    "TT_ELITE":"🏓"
}

if not cards:
    st.info("No games found. (Check your API key quota, or try again later.)")
else:
    for c in cards:
        badge_class = "badge-play" if c["recommendation"] == "PLAY" else "badge-pass"
        badge_text  = "PLAY" if c["recommendation"] == "PLAY" else "PASS"
        sport_emoji = SPORT_EMOJI.get(c["bucket"], "🎯")

        st.markdown(f"""
<div class="ef-card">
  <div>
    <span style="font-weight:700;color:#9fb3c8">{sport_emoji} {c['title']}</span>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>

  <h3 style="margin:6px 0 2px 0;">{c['matchup']}</h3>

  <div class="ef-row"><span class="ef-label">DK Favorite:</span>
    <span class="metric"> {c['fav_name']} ({float(c['fav_price']):.2f})</span>
  </div>

  <div class="ef-row"><span class="ef-label">Model Favorite:</span>
    <span class="metric"> {c['fav_name']}</span>
  </div>

  <div class="ef-row">
    <span class="ef-label">Pick:</span>
    <span class="metric"> {c['fav_name']} ({float(c['fav_price']):.2f})</span>
    <span class="ef-label" style="margin-left:10px;">• Edge:</span>
    <span class="metric"> {c['edge_pct']:.2f}%</span>
  </div>

  <div class="ef-row" style="margin-top:6px;">
    <span class="ef-label">Model {c['model_pct']:.1f}%</span>
    <span class="ef-label" style="margin-left:10px;">| Market {c['market_pct']:.1f}%</span>
  </div>

  <div style="margin-top:8px;">{c['reason']}</div>

  <div style="margin-top:8px;color:#9fb3c8">
    <span>Start: {to_local(c['commence'])}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------- FOOTER / ERRORS ----------------------
# (Optional) surface any per-sport errors
# Not fatal, just informational for debugging in case a league was unavailable.
if 'errors' in locals() and errors:
    with st.expander("Debug: API fetch notes"):
        for e in errors:
            st.caption(f"• {e}")
