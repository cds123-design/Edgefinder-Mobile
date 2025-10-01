import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz

# Title
st.markdown("🧠 **EdgeFinder — Mobile (DK)**", unsafe_allow_html=True)

# Sidebar
st.sidebar.header("⚙️ Settings")
api_key = st.sidebar.text_input("The Odds API Key", type="password")
min_edge = st.sidebar.slider("Min edge % for PLAY", 0.0, 10.0, 3.0, step=0.5)
show_top10 = st.sidebar.checkbox("Show Top 10 by model win %", value=False)
st.sidebar.caption("• DraftKings odds only  \n• Decimal format  \n• Today + Tomorrow  \n• One card per game")

# Emoji mapper
SPORT_EMOJI = {
    "basketball_nba": "🏀",
    "americanfootball_nfl": "🏈",
    "baseball_mlb": "⚾",
    "icehockey_nhl": "🏒",
    "soccer_epl": "⚽",
    "soccer_uefa_champions_league": "⚽",
    "soccer_uefa_europa_league": "⚽",
    "soccer_usa_mls": "⚽",
    "soccer_spain_la_liga": "⚽",
    "soccer_italy_serie_a": "⚽",
    "soccer_germany_bundesliga": "⚽",
    "table_tennis": "🏓"
}

# Run model
if st.button("▶️ Run Model", use_container_width=True):
    if not api_key:
        st.error("Please enter your API key.")
    else:
        with st.spinner("Fetching latest games..."):
            try:
                now = datetime.now(pytz.timezone("America/New_York"))
                end = now + timedelta(days=3)
                sports = ["basketball_nba", "americanfootball_nfl", "baseball_mlb", "icehockey_nhl",
                          "soccer_epl", "soccer_usa_mls", "soccer_spain_la_liga", "soccer_italy_serie_a",
                          "soccer_germany_bundesliga", "table_tennis"]

                all_games = []

                for sport in sports:
                    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?regions=us&markets=h2h&oddsFormat=decimal&apiKey={api_key}"
                    res = requests.get(url)
                    if res.status_code == 200:
                        data = res.json()
                        for ev in data:
                            teams = ev.get("home_team", "Home") + " vs " + ev.get("away_team", "Away")
                            odds_data = ev["bookmakers"][0]["markets"][0]["outcomes"][0]
                            odds_team = odds_data["name"]
                            odds_val = odds_data["price"]

                            # model win estimation (mock)
                            model_win = round((1 / odds_val) * 100 + 10, 1)
                            market_win = round((1 / odds_val) * 100, 1)
                            edge = round(model_win - market_win, 2)

                            # Recommendation
                            if edge >= min_edge:
                                rec = "PLAY"
                                color = "🟩"
                                reason = "Model sees higher win probability than market."
                            elif edge < 0:
                                rec = "PASS"
                                color = "🟥"
                                reason = "Model and market disagree."
                            else:
                                rec = "NEUTRAL"
                                color = "🟨"
                                reason = "Edge under threshold."

                            start = ev.get("commence_time", "")
                            try:
                                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(pytz.timezone("America/New_York"))
                                start_fmt = start_dt.strftime("%b %d, %Y — %I:%M %p EDT")
                            except:
                                start_fmt = "TBD"

                            all_games.append({
                                "sport": sport,
                                "teams": teams,
                                "odds": f"{odds_team} {odds_val}",
                                "model_win": model_win,
                                "edge": edge,
                                "rec": rec,
                                "color": color,
                                "reason": reason,
                                "start": start_fmt
                            })

                if not all_games:
                    st.warning("No DK moneyline markets found for the next 3 days.")
                else:
                    if show_top10:
                        all_games = sorted(all_games, key=lambda g: g["model_win"], reverse=True)[:10]

                    for g in all_games:
                        emoji = SPORT_EMOJI.get(g["sport"], "🎯")
                        st.markdown(f"""
### {emoji} {g["teams"]}
📉 **DK Odds:** {g["odds"]}  
🧠 **Model Win %:** {g["model_win"]}%  
📊 **Edge:** {g["edge"]:+.1f}%  
🎯 **Recommendation:** {g["color"]} {g["rec"]}  
💡 *Reason:* {g["reason"]}  
🕒 **Start:** {g["start"]}
""", unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Error: {e}")
else:
    st.info("Press ▶️ **Run Model** to start.")
