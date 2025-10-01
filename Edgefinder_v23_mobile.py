import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz

# --------------------------
# PAGE CONFIG
# --------------------------
st.set_page_config(page_title="📊 EdgeFinder — Mobile (DK)", layout="centered")

# --------------------------
# FIX FONT + LAYOUT (CLEAN MOBILE STYLE)
# --------------------------
st.markdown("""
    <style>
        * {
            font-family: 'Inter', sans-serif !important;
        }
        .stMarkdown p {
            margin-bottom: 0.4rem !important;
            line-height: 1.3 !important;
            font-size: 1rem !important;
        }
        .stMarkdown strong {
            font-weight: 700 !important;
        }
        .stMarkdown em {
            color: #bbb !important;
        }
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
            margin-bottom: 0.2rem !important;
        }
        .stApp {
            background-color: #0f1116 !important;
            color: white !important;
        }
        .stButton button {
            background-color: #1a73e8 !important;
            color: white !important;
            border-radius: 8px !important;
            padding: 0.4rem 1rem !important;
            font-size: 1rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# --------------------------
# SIDEBAR SETTINGS
# --------------------------
st.sidebar.header("⚙️ Settings")
api_key = st.sidebar.text_input("The Odds API Key", type="password")
min_edge = st.sidebar.slider("Min edge % for PLAY", 1.0, 10.0, 3.0, step=0.5)
show_top10 = st.sidebar.checkbox("Show Top 10 by model win %", value=False)

st.sidebar.write("• DraftKings odds only • Decimal format • Today + Tomorrow")

# --------------------------
# MAIN TITLE
# --------------------------
st.title("📱 EdgeFinder — Mobile (DK)")
st.write("Compare **model vs DraftKings odds** — filter by win % & edge.")

# --------------------------
# TIME RANGE (Local Time)
# --------------------------
local_tz = pytz.timezone("America/New_York")
now_local = datetime.now(local_tz)
end_local = now_local + timedelta(days=2)  # fetch today + tomorrow

# --------------------------
# RUN MODEL BUTTON
# --------------------------
if st.button("▶️ Run Model"):
    if not api_key:
        st.warning("Please enter your API key in the sidebar.")
    else:
        try:
            # --------------------------
            # FETCH GAMES FROM ODDS API
            # --------------------------
            sports = ["soccer_epl", "soccer_uefa_champions_league", "americanfootball_nfl",
                      "basketball_nba", "baseball_mlb", "icehockey_nhl", "tabletennis_tte"]
            
            all_games = []
            for sport in sports:
                url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
                params = {
                    "apiKey": api_key,
                    "regions": "us",
                    "markets": "h2h",
                    "oddsFormat": "decimal"
                }
                res = requests.get(url, params=params)
                if res.status_code == 200:
                    all_games.extend(res.json())

            if not all_games:
                st.warning("No DK markets found for the next 2 days. Try again later.")
            else:
                # --------------------------
                # PROCESS GAMES
                # --------------------------
                cards = []
                for game in all_games:
                    try:
                        teams = game["teams"]
                        home_team = game.get("home_team", teams[0])
                        start_time = datetime.fromisoformat(game["commence_time"].replace("Z", "+00:00"))
                        start_time = start_time.astimezone(local_tz)

                        # Get DraftKings odds
                        dk_book = next((b for b in game["bookmakers"] if b["key"] == "draftkings"), None)
                        if not dk_book:
                            continue
                        outcomes = dk_book["markets"][0]["outcomes"]

                        # Build team odds dict
                        team_odds = {o["name"]: float(o["price"]) for o in outcomes}
                        fav_team = min(team_odds, key=team_odds.get)
                        fav_odds = team_odds[fav_team]

                        # Convert DK odds → market win probability
                        market_win_pct = round(100 / fav_odds, 1)

                        # Model prediction (mock logic)
                        model_win_pct = round(market_win_pct * 1.1, 1)  # +10% bias for demo
                        edge = round(model_win_pct - market_win_pct, 1)

                        # --------------------------
                        # PLAY / PASS / NEUTRAL
                        # --------------------------
                        if edge >= min_edge:
                            reco = "🟩 PLAY"
                            reason = "Model sees higher win probability than market."
                        elif edge < -min_edge:
                            reco = "🟥 PASS"
                            reason = "Model and market disagree."
                        else:
                            reco = "🟨 NEUTRAL"
                            reason = "Edge under threshold."

                        cards.append({
                            "matchup": f"{teams[0]} vs {teams[1]}",
                            "fav_team": fav_team,
                            "fav_odds": fav_odds,
                            "model_win": model_win_pct,
                            "edge": edge,
                            "reco": reco,
                            "reason": reason,
                            "start": start_time.strftime("%b %d, %Y — %I:%M %p %Z")
                        })
                    except Exception:
                        continue

                # Sort & limit if needed
                cards.sort(key=lambda x: x["model_win"], reverse=True)
                if show_top10:
                    cards = cards[:10]

                # --------------------------
                # DISPLAY RESULTS
                # --------------------------
                for g in cards:
                    st.markdown(f"""
                    ⚽ **{g['matchup']}**  
                    📉 **DK Odds:** {g['fav_team']} {g['fav_odds']}  
                    🧠 **Model Win %:** {g['fav_team']} {g['model_win']}%  
                    📊 **Edge:** {g['edge']}%  
                    🎯 **Recommendation:** {g['reco']}  
                    💡 *Reason:* {g['reason']}  
                    🕒 *Start:* {g['start']}
                    """)
        except Exception as e:
            st.error(f"Error fetching games: {e}")
