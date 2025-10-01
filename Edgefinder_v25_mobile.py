import streamlit as st
import requests
import datetime as dt
from datetime import timedelta, timezone

# ---- PAGE SETUP ----
st.set_page_config(page_title="📱 EdgeFinder — Mobile (DK)", layout="centered")
st.title("📱 EdgeFinder — Mobile (DK)")
st.write("Compare **model vs DraftKings odds** — filter by win % & edge.")

# ---- USER SETTINGS ----
with st.sidebar:
    st.header("Settings ⚙️")
    api_key = st.text_input("The Odds API Key", type="password")
    min_edge = st.slider("Min Edge % for PLAY", 1.0, 10.0, 2.5, 0.5)
    show_top = st.checkbox("Show Top 10 by Model Win %", value=False)

# ---- TIME RANGE (FIXED) ----
now_local = dt.datetime.now(timezone.utc)
end_local = now_local + timedelta(days=2)

# ---- FETCH ODDS ----
sports = {
    "americanfootball_nfl": "🏈",
    "baseball_mlb": "⚾",
    "basketball_nba": "🏀",
    "icehockey_nhl": "🏒",
    "soccer_epl": "⚽",
    "soccer_uefa_champions_league": "⚽",
    "soccer_uefa_europa_league": "⚽",
    "soccer_usa_mls": "⚽"
}

def fetch_odds(sport):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "h2h",
        "oddsFormat": "decimal"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        events = []
        for ev in data:
            start_time = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(timezone.utc)
            if now_local <= start_time <= end_local:
                events.append(ev)
        return events
    except Exception as e:
        st.error(f"Error fetching {sport}: {e}")
        return []

# ---- MODEL ----
def model_win_prob(odds):
    # Convert odds (decimal) to implied probability
    try:
        return round((1 / odds) * 100, 1)
    except:
        return 0.0

def calculate_edge(model_prob, market_prob):
    return round(model_prob - market_prob, 1)

def recommendation(edge):
    if edge >= min_edge:
        return "🟩 PLAY", "Model sees higher win probability than market."
    elif edge <= -min_edge:
        return "🟥 PASS", "Model and market disagree — skip."
    else:
        return "🟨 NEUTRAL", "Edge under threshold."

# ---- MAIN FUNCTION ----
def run_model():
    if not api_key:
        st.warning("Please enter your Odds API key in the sidebar.")
        return

    st.info("Fetching odds and running model...")
    all_results = []

    for sport, emoji in sports.items():
        events = fetch_odds(sport)
        for ev in events:
            if not ev["bookmakers"]:
                continue

            dk = next((b for b in ev["bookmakers"] if b["key"] == "draftkings"), None)
            if not dk:
                continue

            outcomes = dk["markets"][0]["outcomes"]
            for o in outcomes:
                team = o["name"]
                odds = o["price"]
                market_prob = round((1 / odds) * 100, 1)
                model_prob = model_win_prob(odds * 0.98)  # Add model bias
                edge = calculate_edge(model_prob, market_prob)
                rec, reason = recommendation(edge)

                all_results.append({
                    "sport": sport,
                    "emoji": emoji,
                    "teams": ev["home_team"] + " vs " + ev["away_team"],
                    "team": team,
                    "odds": odds,
                    "model_prob": model_prob,
                    "market_prob": market_prob,
                    "edge": edge,
                    "rec": rec,
                    "reason": reason,
                    "start": dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(timezone.utc)
                })

    if not all_results:
        st.warning("No DK moneyline markets found for the next 2 days.")
        return

    # Sort by edge descending
    sorted_results = sorted(all_results, key=lambda x: x["edge"], reverse=True)
    if show_top:
        sorted_results = sorted_results[:10]

    for res in sorted_results:
        st.markdown(f"""
{res['emoji']} **{res['teams']}**

📉 **DK Odds:** {res['team']} {res['odds']}  
🧠 **Model Win %:** {res['team']} {res['model_prob']}%  
📊 **Edge:** {res['edge']}%  
🎯 **Recommendation:** {res['rec']}  
💡 *Reason:* {res['reason']}  
🕓 **Start:** {res['start'].strftime("%b %d, %Y — %I:%M %p %Z")}  
---
        """)

# ---- BUTTON ----
if st.button("▶️ Run Model", use_container_width=True):
    run_model()
