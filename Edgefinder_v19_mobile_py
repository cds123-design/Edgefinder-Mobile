import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz

# App title
st.markdown("🧠 **EdgeFinder — Mobile (DK)**", unsafe_allow_html=True)

# Sidebar settings
st.sidebar.header("⚙️ Settings")
api_key = st.sidebar.text_input("The Odds API Key", type="password")

min_edge = st.sidebar.slider("Min edge % for PLAY", 0.0, 10.0, 3.0, step=0.5)
show_top10 = st.sidebar.checkbox("Show Top 10 by model win %", value=False)

st.sidebar.caption("• DraftKings odds only  \n• Decimal format  \n• Today + Tomorrow  \n• One card per game")

# Main run buttons
if st.button("▶️ Run Model", use_container_width=True):
    if not api_key:
        st.error("Please enter your API key in the sidebar.")
    else:
        with st.spinner("Fetching latest games..."):
            try:
                # Fetching upcoming events
                now_local = datetime.now(pytz.timezone("America/New_York"))
                end_local = now_local + timedelta(days=3)
                url = f"https://api.the-odds-api.com/v4/sports/?apiKey={api_key}"
                res = requests.get(url)

                if res.status_code != 200:
                    st.error("❌ Failed to fetch games. Check API key or quota.")
                else:
                    # Placeholder: Replace with odds retrieval & model logic
                    games = [
                        {
                            "sport": "Soccer",
                            "teams": "Arsenal vs Manchester United",
                            "odds": "Arsenal 1.16",
                            "model_win": 68,
                            "edge": 18.5,
                            "recommendation": "PLAY",
                            "reason": "Model sees higher win probability than market.",
                            "start": "Oct 02, 2025 — 10:00 AM EDT"
                        },
                        {
                            "sport": "Soccer",
                            "teams": "Roma vs Napoli",
                            "odds": "Napoli 1.75",
                            "model_win": 51,
                            "edge": -6.7,
                            "recommendation": "PASS",
                            "reason": "Model and market disagree.",
                            "start": "Oct 02, 2025 — 1:00 PM EDT"
                        },
                        {
                            "sport": "Table Tennis",
                            "teams": "Kuznetsov vs Petrov",
                            "odds": "Petrov 1.60",
                            "model_win": 65,
                            "edge": 4.1,
                            "recommendation": "NEUTRAL",
                            "reason": "Edge under threshold.",
                            "start": "Oct 02, 2025 — 3:00 PM EDT"
                        }
                    ]

                    # Sort & filter
                    if show_top10:
                        games = sorted(games, key=lambda g: g["model_win"], reverse=True)[:10]

                    for g in games:
                        rec_color = "🟩" if g["recommendation"] == "PLAY" else ("🟥" if g["recommendation"] == "PASS" else "🟨")
                        st.markdown(f"""
### ⚽ {g["teams"]}
📉 **DK Odds:** {g["odds"]}  
🧠 **Model Win %:** {g["model_win"]}%  
📊 **Edge:** {g["edge"]:+.1f}%  
🎯 **Recommendation:** {rec_color} {g["recommendation"]}  
💡 *Reason:* {g["reason"]}  
🕒 **Start:** {g["start"]}
""", unsafe_allow_html=True)

            except Exception as e:
                st.error(f"An error occurred: {e}")
else:
    st.info("Press ▶️ **Run Model** to start.")
