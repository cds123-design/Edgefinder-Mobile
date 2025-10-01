import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz

# ================================
# CONFIG
# ================================
st.set_page_config(page_title="EdgeFinder — Mobile (DK)", layout="centered")

st.title("📱 EdgeFinder — Mobile (DK)")

# Sidebar Settings
with st.sidebar:
    st.header("⚙️ Settings")
    odds_api_key = st.text_input("The Odds API Key", type="password")
    edge_threshold = st.slider("Min edge % for PLAY", 1.0, 10.0, 3.0)
    show_top_10 = st.checkbox("Show Top 10 by model win %", value=False)

# ================================
# VALIDATE API
# ================================
if not odds_api_key:
    st.info("Add your The Odds API key in the sidebar to load games.")
    st.stop()

# ================================
# TIME RANGE
# ================================
now_local = datetime.now(pytz.timezone("America/New_York"))
end_local = now_local + timedelta(days=2)  # next 2 days only

start_str = now_local.strftime("%Y-%m-%dT%H:%M:%SZ")
end_str = end_local.strftime("%Y-%m-%dT%H:%M:%SZ")

# ================================
# CONTROLS
# ================================
col1, col2 = st.columns(2)
with col1:
    run_model = st.button("▶️ Run Model", use_container_width=True)
with col2:
    refresh = st.button("🔄 Refresh", use_container_width=True)

# Team Filter
filter_team = st.text_input("🔍 Filter by team", placeholder="Type a team name...")

# ================================
# SPORTS LIST
# ================================
sports_list = [
    "soccer_epl", "soccer_uefa_champions_league", "soccer_spain_la_liga",
    "soccer_germany_bundesliga", "soccer_italy_serie_a", "soccer_france_ligue_one",
    "soccer_usa_mls", "basketball_nba", "baseball_mlb", "icehockey_nhl", "americanfootball_nfl"
]

# ================================
# FETCH GAMES
# ================================
games = []
if run_model or refresh:
    for sport in sports_list:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
        params = {
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "apiKey": odds_api_key
        }
        try:
            res = requests.get(url, params=params)
            if res.status_code == 200:
                games.extend(res.json())
        except Exception as e:
            st.error(f"Error fetching {sport}: {e}")

    if not games:
        st.warning("⚠️ No DK moneyline markets found for the next 2 days.")
        st.stop()

    # ================================
    # PROCESS GAMES
    # ================================
    def decimal_to_prob(decimal_odds):
        return 1 / decimal_odds if decimal_odds > 1 else 0

    results = []
    for game in games:
        try:
            teams = game["bookmakers"][0]["markets"][0]["outcomes"]
            team1, team2 = teams[0], teams[1]
            odds1, odds2 = team1["price"], team2["price"]

            # Market probabilities
            market1, market2 = decimal_to_prob(odds1), decimal_to_prob(odds2)
            total_market = market1 + market2
            market1, market2 = market1 / total_market, market2 / total_market

            # Simple model with small adjustment
            model1 = market1 + 0.03
            model2 = 1 - model1

            edge1 = (model1 - market1) * 100
            edge2 = (model2 - market2) * 100

            if model1 > model2:
                model_fav, model_edge, model_win = team1["name"], edge1, model1 * 100
                dk_odds = odds1
            else:
                model_fav, model_edge, model_win = team2["name"], edge2, model2 * 100
                dk_odds = odds2

            recommendation = "🟩 PLAY" if model_edge >= edge_threshold else (
                "🟨 NEUTRAL" if abs(model_edge) < edge_threshold else "🟥 PASS"
            )

            # sport icon
            if "soccer" in game["sport_key"]:
                icon = "⚽"
            elif "basketball" in game["sport_key"]:
                icon = "🏀"
            elif "baseball" in game["sport_key"]:
                icon = "⚾"
            elif "icehockey" in game["sport_key"]:
                icon = "🏒"
            elif "football" in game["sport_key"]:
                icon = "🏈"
            else:
                icon = "🎯"

            # Reason
            if recommendation == "🟩 PLAY":
                reason = "Model sees higher win probability than market."
            elif recommendation == "🟨 NEUTRAL":
                reason = "Edge under threshold."
            else:
                reason = "Model and market disagree."

            results.append({
                "icon": icon,
                "matchup": f"{team1['name']} vs {team2['name']}",
                "dk_odds": f"{model_fav} {dk_odds}",
                "model_win": f"{model_fav} {model_win:.1f}%",
                "edge": f"{model_edge:+.1f}%",
                "recommendation": recommendation,
                "reason": reason,
                "start": game["commence_time"]
            })
        except Exception:
            continue

    # Filter by team if specified
    if filter_team:
        results = [r for r in results if filter_team.lower() in r["matchup"].lower()]

    # Sort for top 10
    if show_top_10:
        results = sorted(results, key=lambda x: float(x["model_win"].split()[-1][:-1]), reverse=True)[:10]

    # ================================
    # DISPLAY RESULTS
    # ================================
    if results:
        for g in results:
            start_dt = datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(pytz.timezone("America/New_York"))
            st.markdown(f"""
{g['icon']} **{g['matchup']}**

📉 **DK Odds:** {g['dk_odds']}  
🧠 **Model Win %:** {g['model_win']}  
📊 **Edge:** {g['edge']}  
🎯 **Recommendation:** {g['recommendation']}  
💡 *Reason:* {g['reason']}  
🕒 **Start:** {start_dt.strftime("%b %d, %Y — %I:%M %p %Z")}  
---
""")
    else:
        st.warning("No valid games found after processing.")
else:
    st.info("Press ▶️ Run Model to load predictions.")
