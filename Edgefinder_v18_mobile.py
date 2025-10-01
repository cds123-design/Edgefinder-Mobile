import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz

# ------------------ APP CONFIG ------------------
st.set_page_config(page_title="EdgeFinder — Mobile (DK)", page_icon="📱", layout="centered")
st.title("📱 EdgeFinder — Mobile (DK)")

# Sidebar Inputs
st.sidebar.header("Settings")
api_key = st.sidebar.text_input("The Odds API Key", type="password")
min_edge = st.sidebar.slider("Min edge % for PLAY", 1.0, 10.0, 3.0, step=0.5)
show_top10 = st.sidebar.checkbox("Show Top 10 by model win %")

# ------------------ HELPER FUNCTIONS ------------------
def get_implied_prob(decimal_odds):
    return 100 / decimal_odds if decimal_odds > 0 else 0

def get_model_prob(decimal_odds):
    # Placeholder: model gives slightly different prediction than market
    implied = get_implied_prob(decimal_odds)
    return implied + (5 - (decimal_odds * 2))  # Example tweak

def get_edge(model_prob, market_prob):
    return round(model_prob - market_prob, 2)

def get_recommendation(edge):
    if edge >= min_edge:
        return "🟩 PLAY", "Model sees higher win probability than market."
    elif edge <= -min_edge:
        return "🟥 PASS", "Model and market disagree."
    else:
        return "🟨 NEUTRAL", "Edge under threshold."

# ------------------ MAIN APP ------------------
if not api_key:
    st.warning("Please add your API key in the sidebar to load games.")
    st.stop()

st.markdown("Use the button below to run the model and fetch current DK markets.")
run_button = st.button("▶️ Run Model")

# Time range (next 2 days)
now_local = datetime.now(pytz.timezone("America/New_York"))
end_local = now_local + timedelta(days=2)

if run_button:
    try:
        url = f"https://api.the-odds-api.com/v4/sports/?apiKey={api_key}"
        sports = requests.get(url).json()

        games = []
        for sport in sports:
            sport_key = sport.get("key")
            if not sport_key:
                continue

            odds_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?regions=us&oddsFormat=decimal&markets=h2h&apiKey={api_key}"
            response = requests.get(odds_url)

            if response.status_code != 200:
                continue

            data = response.json()
            for event in data:
                match_name = event.get("home_team", "Team A") + " vs " + event.get("away_team", "Team B")
                start_time = event.get("commence_time", "")
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")).astimezone(pytz.timezone("America/New_York"))
                start_str = start_dt.strftime("%b %d, %Y — %I:%M %p %Z")

                bookmakers = event.get("bookmakers", [])
                dk = next((b for b in bookmakers if b["key"] == "draftkings"), None)
                if not dk:
                    continue

                markets = dk.get("markets", [])
                if not markets:
                    continue

                outcomes = markets[0].get("outcomes", [])
                if len(outcomes) < 2:
                    continue

                best_team = None
                best_edge = -999
                dk_odds_str = ""
                model_prob_str = ""
                edge_str = ""
                reason = ""
                pick_team = ""

                for o in outcomes:
                    team = o["name"]
                    dk_odds = o["price"]
                    market_prob = get_implied_prob(dk_odds)
                    model_prob = get_model_prob(dk_odds)
                    edge = get_edge(model_prob, market_prob)
                    rec, reason = get_recommendation(edge)

                    if model_prob > best_edge:
                        best_edge = model_prob
                        best_team = team
                        dk_odds_str = f"{team} {dk_odds}"
                        model_prob_str = f"{team} {round(model_prob, 1)}%"
                        edge_str = f"{edge:+.1f}%"
                        pick_team = team
                        pick_rec = rec
                        pick_reason = reason

                games.append({
                    "matchup": match_name,
                    "pick": pick_team,
                    "dk_odds": dk_odds_str,
                    "model_win": model_prob_str,
                    "edge": edge_str,
                    "rec": pick_rec,
                    "reason": pick_reason,
                    "start": start_str
                })

        if not games:
            st.warning("⚠️ No DK moneyline markets found. Try again later.")
            st.stop()

        # --- SEARCH BAR ---
        query = st.text_input("🔍 Filter by team", "")
        if query:
            games = [g for g in games if query.lower() in g["matchup"].lower()]

        # --- SORT ---
        games = sorted(games, key=lambda x: float(x["model_win"].split()[-1].replace("%", "")), reverse=True)
        if show_top10:
            games = games[:10]

        # --- DISPLAY ---
        for g in games:
            with st.container():
                st.markdown(f"""
                ### {g['matchup']}
                **DK Odds:** {g['dk_odds']}  
                **Model Win %:** {g['model_win']}  
                **Edge:** {g['edge']}  
                **Recommendation:** {g['rec']}  
                _Reason:_ {g['reason']}  
                🕒 **Start:** {g['start']}  
                ---
                """)
    except Exception as e:
        st.error(f"Error loading data: {e}")
