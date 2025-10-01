import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta, timezone

# =========================
# App Config / Theme
# =========================
st.set_page_config(page_title="EdgeFinder v8 — Winner Mode", page_icon="🏆", layout="wide")

st.markdown("""
<style>
body, .stApp { background-color: #0e1117; color: #ffffff; }
.card { background-color:#1b1e24; padding:1rem; border-radius:12px; margin-bottom:1rem; border:1px solid #2a2f39; }
.play { color:#12B886; font-weight:800; }
.caution { color:#FFD43B; font-weight:800; }
.pass { color:#FA5252; font-weight:800; }
.statline { color:#66ccff; font-size:0.92rem; }
.reason { color:#cfd5df; font-size:0.92rem; }
.dim { color:#9aa0a6; font-size:0.88rem; }
h1,h2,h3,h4 { color:#eaf1fb; }
hr { border-color: #2a2f39; }
.bigbtn button { width:100%; height:3rem; font-weight:800; font-size:1.05rem; }
.badge { display:inline-block; padding:.25rem .5rem; background:#2a2f39; border-radius:8px; margin-left:.4rem; font-size:.8rem; color:#cfd5df;}
</style>
""", unsafe_allow_html=True)

st.title("🏆 EdgeFinder v8 — Winner Mode (Dark Theme)")

# =========================
# Constants / Keys
# =========================
ODDS_API_KEY = "0ad4039785b38ae45104ee6eba0e90e4"   # DK via The Odds API (your key)
ODDS_BASE = "https://api.the-odds-api.com/v4/sports"
BOOK = "draftkings"
REGIONS = "us"
MARKET = "h2h"
ODDS_FMT = "decimal"

# SofaScore (unofficial JSON endpoints used read-only)
SOFA_BASE = "https://api.sofascore.com/api/v1"

LOCAL_TZ = datetime.now().astimezone().tzinfo  # use device/stream timezone

SPORT_KEYS = [
    # Soccer (3-way)
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    # US Majors (2-way)
    "americanfootball_nfl",
    "basketball_nba",
    "icehockey_nhl",
    "baseball_mlb",
    # Euro/World hoops (2-way)
    "basketball_euroleague",
    "basketball_eurocup",
    "basketball_spain_liga_acb",
    "basketball_italy_lega_a",
    "basketball_germany_bbl",
    "basketball_france_lnb",
    # Table Tennis
    "table-tennis_tt-elite-series",
]

# =========================
# Sidebar Controls
# =========================
st.sidebar.header("⚙️ Filters & Modes")
parlay_mode = st.sidebar.toggle("🎯 Parlay Builder Mode (Model ≥ 70% & Edge ≥ 0, Top 10)", value=False)
top10_mode = st.sidebar.toggle("🏆 Show Top 10 Confidence Picks", value=False)
min_model_prob = st.sidebar.slider("🎚 Minimum Model Win Chance (%)", 50, 90, 70)
search_term = st.sidebar.text_input("🔍 Search Team or Matchup", "")
st.sidebar.markdown(f"🕒 **Last Updated:** {datetime.now().strftime('%b %d, %Y %I:%M %p')}")
st.sidebar.caption("Winner-first. PLAY = high model win % and fair (non-negative) edge.")

# =========================
# Utilities
# =========================
def to_local(iso_s: str):
    try:
        dt = datetime.fromisoformat(iso_s.replace("Z","+00:00")).astimezone(LOCAL_TZ)
        return dt
    except Exception:
        return None

def implied_from_decimal(odds):
    try:
        odds = float(odds)
        return 1.0/odds if odds > 0 else 0.0
    except:
        return 0.0

def normalize(parts: dict):
    s = sum(v for v in parts.values() if v is not None)
    if s <= 0:
        return {k: 0.0 for k in parts}
    return {k: (v/s if v is not None else 0.0) for k,v in parts.items()}

# =========================
# SofaScore: search & form (soccer priority; safe fallback)
# =========================
def sofa_search_team_id(name: str, sport_hint: str = "soccer"):
    """
    Returns SofaScore team id by fuzzy name search.
    We bias to 'soccer' hits for soccer sports; for others, we return None (for now).
    """
    if not name:
        return None
    try:
        r = requests.get(f"{SOFA_BASE}/search/all", params={"q": name}, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json() or {}
        teams = data.get("teams", [])
        # pick first reasonable match
        for t in teams:
            # Basic name match heuristic
            tname = (t.get("name") or "").lower()
            if name.lower() in tname or tname in name.lower():
                # optionally filter by sport_hint if present in response
                # (Sofa doesn't always include sport field on search results)
                return t.get("id")
        # Fallback: take the first team
        if teams:
            return teams[0].get("id")
        return None
    except Exception:
        return None

def sofa_team_form_score(team_id: int, last_n: int = 10):
    """
    Returns recency-weighted form score in [0,1] using last N finished games.
    We weight recent games higher (linear decay).
    If anything fails, returns None to signal fallback.
    """
    try:
        r = requests.get(f"{SOFA_BASE}/team/{team_id}/events/last/{last_n}", timeout=10)
        if r.status_code != 200:
            return None
        js = r.json() or {}
        events = js.get("events", [])
        if not events:
            return None

        # Build win=1, draw=0.5, loss=0 for each event from the team's perspective
        scores = []
        for idx, ev in enumerate(events):
            if ev.get("status", {}).get("type") not in ("finished","ap"){
                # Sometimes "ap" (after penalties) or "finished"
                pass
            home = ev.get("homeTeam",{}).get("name","")
            away = ev.get("awayTeam",{}).get("name","")
            hs = ev.get("homeScore",{}).get("current")
            as_ = ev.get("awayScore",{}).get("current")
            if hs is None or as_ is None:
                continue
            # determine if our team is home or away
            team_is_home = str(ev.get("homeTeam",{}).get("id")) == str(team_id)
            # outcome for our team
            if hs == as_:
                res = 0.5
            else:
                our = hs if team_is_home else as_
                opp = as_ if team_is_home else hs
                res = 1.0 if our > opp else 0.0
            scores.append(res)

        if not scores:
            return None

        # Recency weights: most recent gets weight 1.0, older linearly down to 0.5
        n = len(scores)
        weights = np.linspace(1.0, 0.5, n)
        scores = np.array(scores, dtype=float)
        val = float(np.average(scores, weights=weights))
        return max(0.0, min(1.0, val))
    except Exception:
        return None

def sofa_soccer_draw_hint(home_id: int, away_id: int):
    """
    Optional: return a tiny base draw propensity based on both teams' recent draw rates.
    If unavailable, return None.
    """
    try:
        def draw_rate(tid):
            r = requests.get(f"{SOFA_BASE}/team/{tid}/events/last/10", timeout=10)
            if r.status_code != 200:
                return None
            evs = (r.json() or {}).get("events",[])
            if not evs: return None
            d = 0; c=0
            for ev in evs:
                hs = ev.get("homeScore",{}).get("current")
                as_ = ev.get("awayScore",{}).get("current")
                if hs is None or as_ is None: 
                    continue
                c+=1
                if hs==as_: d+=1
            return (d/c) if c>0 else None

        hr = draw_rate(home_id)
        ar = draw_rate(away_id)
        if hr is None or ar is None:
            return None
        # Combine softly
        return max(0.0, min(1.0, (hr+ar)/2 * 0.8))
    except Exception:
        return None

# =========================
# (Stubs) Injuries / Red cards — left as add-ons
# =========================
def injury_factor_placeholder(team_id: int):
    """
    Returns injury/suspension factor in [0,1]. 1.0 = fully healthy.
    Stubbed to 1.0 now; replace with SofaScore injuries endpoint when stable.
    """
    return 1.0

def redcard_adjustment_placeholder(event_hint: dict):
    """
    If you wire SofaScore event incidents, return (-0.3, +0.3) for carded vs opponent.
    For now, return (0,0).
    """
    return 0.0, 0.0

# =========================
# Model: combine Form (Sofa) + Home/Away + Market
# =========================
def compute_model_probs(home_name, away_name, implied, is_soccer=True):
    """
    implied: dict keys 'home','away','draw?' in [0..1] normalized.
    Returns normalized dict of model probs for offered outcomes.
    """
    # 1) Try SofaScore team IDs (soccer prioritized)
    home_id = sofa_search_team_id(home_name, "soccer" if is_soccer else "")
    away_id = sofa_search_team_id(away_name, "soccer" if is_soccer else "")

    # 2) Form scores (0..1) with fallback to market
    form_home = sofa_team_form_score(home_id) if home_id else None
    form_away = sofa_team_form_score(away_id) if away_id else None

    # Fallbacks: if form missing, use market as baseline
    if form_home is None: form_home = implied.get("home", 0.5)
    if form_away is None: form_away = implied.get("away", 0.5)

    # 3) Home advantage (mild; soccer smaller than US leagues)
    home_boost = 0.06 if not is_soccer else 0.04
    adj_home = min(1.0, max(0.0, form_home + home_boost))
    adj_away = min(1.0, max(0.0, form_away - (home_boost*0.5)))  # away slight penalty

    # 4) Injuries (stubbed to 1.0 for now)
    inj_home = injury_factor_placeholder(home_id or 0)
    inj_away = injury_factor_placeholder(away_id or 0)
    adj_home *= inj_home
    adj_away *= inj_away

    # 5) Draw base (soccer only) — optional hint
    draw_base = None
    if is_soccer and home_id and away_id:
        draw_base = sofa_soccer_draw_hint(home_id, away_id)

    # 6) Compose raw
    raw = {"home": adj_home, "away": adj_away}
    if is_soccer and "draw" in implied:
        # include draw if market offered it; use small baseline tied to market/draw_base
        raw["draw"] = max(0.0, (draw_base if draw_base is not None else implied.get("draw", 0.0))*0.9)

    # 7) Normalize to probabilities
    model = normalize(raw)
    return model

# =========================
# Odds pull (DK, today+tomorrow)
# =========================
def fetch_board(sport_key: str):
    url = f"{ODDS_BASE}/{sport_key}/odds"
    params = dict(
        apiKey=ODDS_API_KEY, regions=REGIONS, markets=MARKET,
        bookmakers=BOOK, oddsFormat=ODDS_FMT, dateFormat="iso"
    )
    r = requests.get(url, params=params, timeout=25)
    if r.status_code != 200:
        return []
    return r.json()

def game_within_2_days(iso_time: str):
    dt = to_local(iso_time)
    if not dt: return False, None
    now = datetime.now(LOCAL_TZ)
    return (now <= dt <= now + timedelta(days=2)), dt

# =========================
# UI: Run Model button
# =========================
st.markdown("<div class='bigbtn'>", unsafe_allow_html=True)
run = st.button("🚀 Run Model (Fetch Live DraftKings Odds)")
st.markdown("</div>", unsafe_allow_html=True)

if not run:
    st.warning("Click **Run Model** to fetch live DK odds and compute predictions.")
    st.stop()

with st.spinner("Fetching DK odds & SofaScore form…"):
    cards = []

    for sport_key in SPORT_KEYS:
        is_soccer = sport_key.startswith("soccer_")
        try:
            board = fetch_board(sport_key)
        except Exception:
            board = []

        for g in board:
            ok, start_local = game_within_2_days(g.get("commence_time",""))
            if not ok: 
                continue

            home_team = g.get("home_team","")
            away_team = g.get("away_team","")

            # Find DK market
            dk = next((b for b in g.get("bookmakers",[]) if b.get("key")==BOOK), None)
            if not dk: 
                continue
            mkt = next((m for m in dk.get("markets",[]) if m.get("key")==MARKET), None)
            if not mkt:
                continue

            # Outcomes & prices
            prices = {"home":None,"away":None,"draw":None}
            for o in mkt.get("outcomes",[]):
                name = (o.get("name") or "").strip()
                price = o.get("price")
                if name.lower() == home_team.lower():
                    prices["home"] = float(price)
                elif name.lower() == away_team.lower():
                    prices["away"] = float(price)
                elif name.lower() == "draw":
                    prices["draw"] = float(price)

            if prices["home"] is None or prices["away"] is None:
                continue
            if not is_soccer:
                prices.pop("draw", None)  # remove for 2-way

            # Market implied (normalized)
            implied = {k: implied_from_decimal(v) for k,v in prices.items()}
            implied = normalize(implied)

            # --- MODEL: form + H/A + (stub injuries) + small draw base ---
            model = compute_model_probs(home_team, away_team, implied, is_soccer=is_soccer)

            # Determine model pick (max prob among offered outcomes)
            pick_key = max(model, key=lambda k: model[k])
            pick_team = home_team if pick_key=="home" else (away_team if pick_key=="away" else "Draw")
            pick_prob = model[pick_key]
            pick_market = implied.get(pick_key, 0.0)
            pick_odds = prices.get(pick_key, None)

            # Edge
            edge = (pick_prob - pick_market) * 100.0

            # Labels (winner-first)
            if pick_prob*100 >= min_model_prob:
                if edge >= 0:
                    label, color = "PLAY", "play"
                else:
                    label, color = "CAUTION", "caution"
            else:
                label, color = "PASS", "pass"

            # DK favorite (lowest odds)
            fav_key = min(prices, key=lambda k: prices[k] if prices[k] else 1e9)
            fav_name = home_team if fav_key=="home" else (away_team if fav_key=="away" else "Draw")
            fav_odds = prices[fav_key]

            cards.append({
                "Sport": sport_key.replace("_"," ").title(),
                "Matchup": f"{home_team} vs {away_team}",
                "ModelPick": pick_team,
                "ModelProb": pick_prob*100,
                "MarketProb": pick_market*100,
                "Edge": edge,
                "DKOdds": pick_odds if pick_odds is not None else np.nan,
                "DK Favorite": f"{fav_name} ({fav_odds:.2f})",
                "Start": start_local.strftime("%b %d, %Y — %I:%M %p"),
                "_blob": f"{sport_key} {home_team} {away_team} {pick_team} {fav_name}"
            })

# Apply search
df = pd.DataFrame(cards)
if search_term.strip():
    needle = search_term.strip().lower()
    df = df[df["_blob"].str.lower().str.contains(needle)]

# Modes: Parlay / Top10 / Normal
if parlay_mode:
    # auto: Model ≥ 70 & Edge ≥ 0, then take Top 10 by ModelProb
    df = df[(df["ModelProb"] >= 70) & (df["Edge"] >= 0)]
    df = df.sort_values("ModelProb", ascending=False).head(10)
elif top10_mode:
    df = df.sort_values("ModelProb", ascending=False).head(10)
else:
    # filter by minimum model % then sort by model win %
    df = df[df["ModelProb"] >= min_model_prob].sort_values("ModelProb", ascending=False)

# Render
if df.empty:
    st.error("No qualifying games right now. Try lowering the win % filter, turning off Parlay Mode, or running later when DK posts more markets.")
else:
    # Header badge line
    if parlay_mode:
        st.subheader("🎯 Parlay Builder — High-Confidence Shortlist")
    elif top10_mode:
        st.subheader("🏆 Top 10 Confidence Picks (All Sports)")
    else:
        st.subheader("📊 All Games (sorted by Model Win %)")

    for _, r in df.iterrows():
        st.markdown(f"""
        <div class='card'>
          <h3>🏆 MODEL PICK: {r.ModelPick}</h3>
          <p>💡 Win Probability: {r.ModelProb:.1f}%</p>
          <h4 class='{ 'play' if r.Edge >= 0 and r.ModelProb >= min_model_prob else ('caution' if r.ModelProb >= min_model_prob else 'pass') }'>
            { 'PLAY' if r.Edge >= 0 and r.ModelProb >= min_model_prob else ('CAUTION' if r.ModelProb >= min_model_prob else 'PASS') }
          </h4>
          <hr>
          <p class='dim'>Sport: {r.Sport} <span class='badge'>DK Favorite: {r['DK Favorite']}</span></p>
          <p>Matchup: {r.Matchup}</p>
          <p>DK Odds (pick): {r.DKOdds:.2f}</p>
          <p class='statline'>Model {r.ModelProb:.1f}% &nbsp;|&nbsp; Market {r.MarketProb:.1f}% &nbsp;|&nbsp; Edge {r.Edge:+.2f}%</p>
          <p class='reason'>
            Reason: Model expects <b>{r.ModelPick}</b> to win {r.ModelProb:.1f}% of the time vs market {r.MarketProb:.1f}%.
          </p>
          <p class='dim'>🕒 Start: {r.Start}</p>
        </div>
        """, unsafe_allow_html=True)

    # Parlay summary
    if parlay_mode and not df.empty:
        avg_prob = float(df["ModelProb"].mean())/100.0
        combined = float(np.prod(df["ModelProb"]/100.0))
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='card'>
          <h3>🎯 PARLAY BUILDER SUMMARY</h3>
          <p>Legs: {len(df)}</p>
          <p>Average Win %: {avg_prob*100:.1f}%</p>
          <p>Estimated Parlay Hit Chance: {combined*100:.2f}%</p>
          <p class='reason'>(Product of model win probabilities for legs shown)</p>
        </div>
        """, unsafe_allow_html=True)
