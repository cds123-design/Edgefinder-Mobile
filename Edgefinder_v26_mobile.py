# EdgeFinder — Mobile (DK) v9.2
# - Light theme, controlled mobile font sizes
# - DK-only moneyline, decimal odds
# - Today + Tomorrow
# - Cards with clear DK favorite, Model favorite, Edge, and Recommendation
# - Robust against malformed league responses (skips quietly)
# - Search bar, Top-10 toggle, edge threshold slider

import streamlit as st
import requests
import datetime as dt
from datetime import timedelta, timezone

# --------------------- PAGE SETUP ---------------------
st.set_page_config(page_title="EdgeFinder — Mobile (DK)", layout="centered")
st.markdown(
    """
    <style>
      /* Base mobile-friendly font scale */
      html, body {font-size: 16px;}
      @media (max-width: 420px){
        html, body {font-size: 15px;}
      }

      /* Tighten default Streamlit spacing */
      .block-container {padding-top: 1rem; padding-bottom: 3.5rem; max-width: 780px;}

      /* Button styling (light theme) */
      .stButton > button {
        background: #1f6feb !important;
        color: #fff !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        padding: 10px 16px !important;
        border: 0 !important;
      }

      /* Card layout */
      .ef-card{
        background: #ffffff;
        border: 1px solid #EAEAEA;
        border-radius: 14px;
        padding: 14px 16px;
        margin: 12px 0;
        box-shadow: 0 1px 2px rgba(0,0,0,.04);
      }
      .ef-title{
        font-size: 1.15rem; font-weight: 800; margin: 0 0 .35rem 0;
        letter-spacing: .1px;
      }
      .ef-line{ margin: .15rem 0; }
      .ef-mono{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
      .ef-muted{ color: #6b7280; }

      /* Recommendation badges */
      .ef-badge{
        display: inline-block; padding: 4px 10px; border-radius: 10px;
        font-weight: 800; font-size: .92rem; letter-spacing: .2px; color: #fff;
      }
      .ef-play{ background: #10b981; }   /* green */
      .ef-pass{ background: #ef4444; }   /* red   */
      .ef-neutral{ background: #f59e0b; }/* amber */

      /* Small meta row */
      .ef-meta{ margin-top: .25rem; font-size: .92rem; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📱 EdgeFinder — Mobile (DK)")
st.caption("Compare **model vs DraftKings odds** — filter by win % & edge.")

# --------------------- SIDEBAR ---------------------
with st.sidebar:
    st.header("Settings ⚙️")
    api_key = st.text_input("The Odds API Key", type="password")
    min_edge = st.slider("Min Edge % for PLAY", 0.5, 10.0, 2.5, 0.5)
    show_top = st.checkbox("Show Top 10 by Model Win %", value=False)

# Search bar (optional)
query = st.text_input("🔎 Filter by team (optional)", "")

# --------------------- TIME WINDOW ---------------------
local_tz = dt.datetime.now().astimezone().tzinfo
now_local = dt.datetime.now(tz=local_tz)
end_local = now_local + timedelta(days=2)  # Today + Tomorrow

# --------------------- SPORTS (DK moneyline only) -----
SPORTS = {
    "americanfootball_nfl": "🏈",
    "baseball_mlb": "⚾",
    "basketball_nba": "🏀",
    "icehockey_nhl": "🏒",
    "soccer_epl": "⚽",
    "soccer_uefa_champions_league": "⚽",
    "soccer_usa_mls": "⚽",
}

# --------------------- HELPERS ---------------------
def safe_parse_iso(ts: str):
    try:
        # Odds API uses ISO string with 'Z'
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(local_tz)
    except Exception:
        return None

def fetch_odds_for_sport(sport_key: str):
    """Fetch DK H2H (moneyline) odds; return list of valid events within window."""
    if not api_key:
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = dict(apiKey=api_key, regions="us", markets="h2h", oddsFormat="decimal")

    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()

        # If API returned an error message or non-list, skip
        if not isinstance(data, list):
            return []

        valid = []
        for ev in data:
            if not isinstance(ev, dict):
                continue
            ts = ev.get("commence_time")
            if not ts:
                continue
            start = safe_parse_iso(ts)
            if not start:
                continue
            if not (now_local <= start <= end_local):
                continue
            valid.append(ev)
        return valid

    except Exception:
        # Silent skip for this sport
        return []

def market_prob_from_decimal(decimal_odds: float) -> float:
    try:
        return round((1.0 / float(decimal_odds)) * 100.0, 1)
    except Exception:
        return 0.0

def model_prob_from_market(decimal_odds: float) -> float:
    # Simple baseline model: apply tiny vigorish adjustment
    try:
        return round((1.0 / (float(decimal_odds) * 0.98)) * 100.0, 1)
    except Exception:
        return 0.0

def edge_pct(model_prob: float, market_prob: float) -> float:
    return round(model_prob - market_prob, 1)

def classify(edge: float):
    if edge >= min_edge:
        return "PLAY", "ef-play", "Model sees higher win probability than market."
    if edge <= -min_edge:
        return "PASS", "ef-pass", "Model and market disagree — skip."
    return "NEUTRAL", "ef-neutral", "Edge under threshold."

# --------------------- RUN MODEL ---------------------
def run_model():
    all_rows = []

    for sport_key, emoji in SPORTS.items():
        events = fetch_odds_for_sport(sport_key)
        for ev in events:
            # Only consider DraftKings bookmaker
            bks = ev.get("bookmakers", [])
            dk = next((b for b in bks if b.get("key") == "draftkings"), None)
            if not dk:
                continue
            mkts = dk.get("markets", [])
            if not mkts:
                continue
            outcomes = mkts[0].get("outcomes", [])
            if not isinstance(outcomes, list) or not outcomes:
                continue

            start = safe_parse_iso(ev.get("commence_time", ""))
            if not start:
                continue

            home = ev.get("home_team", "?")
            away = ev.get("away_team", "?")
            matchup = f"{home} vs {away}"

            # Build per-outcome rows (home, away, and draw if present)
            for o in outcomes:
                if not isinstance(o, dict):
                    continue
                name = o.get("name")
                price = o.get("price")
                if not name or price is None:
                    continue

                market_p = market_prob_from_decimal(price)
                model_p = model_prob_from_market(price)
                edge = edge_pct(model_p, market_p)
                rec_label, rec_class, reason = classify(edge)

                # Optional search filter
                if query:
                    q = query.lower()
                    if q not in matchup.lower() and q not in str(name).lower():
                        continue

                all_rows.append(dict(
                    emoji=emoji,
                    matchup=matchup,
                    dk_team=name,
                    dk_odds=price,
                    model_win=model_p,
                    market_win=market_p,
                    edge=edge,
                    rec_label=rec_label,
                    rec_class=rec_class,
                    reason=reason,
                    start=start,
                    sport=sport_key
                ))

    if not all_rows:
        st.warning("No DK moneyline markets found for the next 2 days.")
        return

    # Sort by model win% (descending), then by edge
    all_rows.sort(key=lambda r: (r["model_win"], r["edge"]), reverse=True)
    if show_top:
        all_rows = all_rows[:10]

    # Render cards
    for r in all_rows:
        st.markdown(
            f"""
            <div class="ef-card">
              <div class="ef-title">{r["emoji"]} {r["matchup"]}</div>

              <div class="ef-line">📉 <b>DK Odds:</b> <span class="ef-mono">{r["dk_team"]} {r["dk_odds"]}</span></div>
              <div class="ef-line">🧠 <b>Model Win %:</b> <span class="ef-mono">{r["dk_team"]} {r["model_win"]}%</span></div>
              <div class="ef-line">📊 <b>Edge:</b> <span class="ef-mono">{r["edge"]}%</span></div>

              <div class="ef-line">
                🎯 <b>Recommendation:</b>
                <span class="ef-badge {r["rec_class"]}">{r["rec_label"]}</span>
              </div>

              <div class="ef-line ef-muted">💡 <i>Reason:</i> {r["reason"]}</div>
              <div class="ef-meta ef-muted">🕓 <b>Start:</b> {r["start"].strftime("%b %d, %Y — %I:%M %p %Z")}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

# --------------------- UI ---------------------
if st.button("▶️ Run Model", use_container_width=True):
    run_model()
