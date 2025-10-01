import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

# ---------------------- CONFIG ----------------------
st.set_page_config(
    page_title="EdgeFinder v8 — Winner Mode",
    layout="wide",
    page_icon="🏆",
)

# Dark theme styling
st.markdown("""
<style>
body, .stApp { background-color: #0e1117; color: #ffffff; }
div[data-testid="stMetricValue"] { color: #00ff88; font-weight:700; }
h1, h2, h3, h4, h5, h6 { color: #fafafa; font-weight:700; }
hr { border-color: #333333; }
.card { background-color:#1b1e24; padding:1rem; border-radius:10px; margin-bottom:1rem; }
.play { color:#00ff88; font-weight:700; }
.caution { color:#ffcc00; font-weight:700; }
.pass { color:#ff6666; font-weight:700; }
.statline { color:#66ccff; font-size:0.9rem; }
.reason { color:#cccccc; font-size:0.9rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------- USER INPUTS ----------------------
st.sidebar.title("⚙️ Filters & Modes")

parlay_mode = st.sidebar.toggle("🎯 Parlay Builder Mode", value=False)
top10_mode = st.sidebar.toggle("🏆 Show Top 10 Confidence Picks", value=False)
min_model_prob = st.sidebar.slider("🎚 Minimum Model Win Chance (%)", 50, 90, 70)
search_term = st.sidebar.text_input("🔍 Search Team", "")

# Placeholder for last updated
st.sidebar.markdown(f"🕒 **Last Updated:** {datetime.now().strftime('%b %d, %Y %I:%M %p')}")

# ---------------------- DATA FETCH (SIMULATED) ----------------------
# NOTE: Replace this section with live API calls later (DK odds)
np.random.seed(8)
sports = ["Soccer", "NBA", "NFL", "NHL", "MLB", "EuroBasket", "LatAmBasket", "TT Elite"]
teams = ["Real Madrid", "Barcelona", "Arsenal", "Bayern Munich", "PSG",
         "Kansas City Chiefs", "Buffalo Bills", "Baltimore Ravens", "Boston Celtics",
         "Denver Nuggets", "LA Lakers", "Golden State Warriors",
         "Toronto Maple Leafs", "Colorado Avalanche", "Vegas Golden Knights",
         "Los Angeles Dodgers", "Atlanta Braves", "Houston Astros", "Napoli", "Inter Milan"]

games = []
for _ in range(50):
    home, away = np.random.choice(teams, 2, replace=False)
    sport = np.random.choice(sports)
    model_home = np.random.uniform(0.45, 0.90)
    model_away = 1 - model_home
    dk_home = np.random.uniform(1.2, 2.8)
    dk_away = np.random.uniform(1.2, 2.8)
    market_home = 1 / dk_home / (1 / dk_home + 1 / dk_away)
    market_away = 1 - market_home
    games.append({
        "sport": sport,
        "home": home,
        "away": away,
        "model_home": model_home,
        "model_away": model_away,
        "dk_home": dk_home,
        "dk_away": dk_away,
        "market_home": market_home,
        "market_away": market_away,
        "start": (datetime.now() + timedelta(hours=np.random.randint(1,72))).strftime("%b %d, %Y — %I:%M %p")
    })

df = pd.DataFrame(games)

# ---------------------- MODEL LOGIC ----------------------
rows = []
for _, g in df.iterrows():
    model_pick = "home" if g.model_home > g.model_away else "away"
    pick_team = g[model_pick]
    pick_prob = g[f"model_{model_pick}"]
    dk_odds = g[f"dk_{model_pick}"]
    market_prob = g[f"market_{model_pick}"]
    edge = round((pick_prob - market_prob) * 100, 2)

    # Label logic
    if pick_prob * 100 >= min_model_prob:
        if edge >= 0:
            label = "PLAY"
            color = "play"
        else:
            label = "CAUTION"
            color = "caution"
    else:
        label = "PASS"
        color = "pass"

    rows.append({
        "Sport": g.sport,
        "Matchup": f"{g.home} vs {g.away}",
        "ModelPick": pick_team,
        "ModelProb": pick_prob*100,
        "MarketProb": market_prob*100,
        "Edge": edge,
        "Label": label,
        "Color": color,
        "DKOdds": dk_odds,
        "Start": g.start
    })

out = pd.DataFrame(rows)

# Search filter
if search_term.strip():
    out = out[out["Matchup"].str.contains(search_term, case=False)]

# Parlay mode filters
if parlay_mode:
    out = out[(out["ModelProb"] >= 70) & (out["Edge"] >= 0)]
    out = out.sort_values("ModelProb", ascending=False).head(10)
elif top10_mode:
    out = out.sort_values("ModelProb", ascending=False).head(10)
else:
    out = out.sort_values("ModelProb", ascending=False)

# ---------------------- DISPLAY ----------------------
st.title("🏆 EdgeFinder v8 — Winner Mode (Dark Theme)")

if parlay_mode:
    st.subheader("🎯 Parlay Builder Mode — Active")
elif top10_mode:
    st.subheader("🏆 Top 10 Confidence Picks")
else:
    st.subheader("📊 All Games Sorted by Model Win %")

# Render cards
for _, r in out.iterrows():
    st.markdown(f"""
    <div class='card'>
    <h3>🏆 MODEL PICK: {r.ModelPick}</h3>
    <p>💡 Win Probability: {r.ModelProb:.1f}%</p>
    <h4 class='{r.Color}'>{r.Label}</h4>
    <hr>
    <p>Sport: {r.Sport}</p>
    <p>DK Favorite: {r.ModelPick} ({r.DKOdds:.2f})</p>
    <p class='statline'>Model {r.ModelProb:.1f}% | Market {r.MarketProb:.1f}% | Edge {r.Edge:+.2f}%</p>
    <p class='reason'>Reason: Model projects {r.ModelPick} to win {r.ModelProb:.1f}% vs market {r.MarketProb:.1f}%.</p>
    <p>🕒 Start: {r.Start}</p>
    </div>
    """, unsafe_allow_html=True)

# ---------------------- PARLAY SUMMARY ----------------------
if parlay_mode and not out.empty:
    avg_prob = out["ModelProb"].mean() / 100
    combined = np.prod(out["ModelProb"] / 100)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class='card'>
    <h3>🎯 PARLAY BUILDER SUMMARY</h3>
    <p>Legs: {len(out)}</p>
    <p>Average Win %: {avg_prob*100:.1f}%</p>
    <p>Estimated Parlay Hit Chance: {combined*100:.2f}%</p>
    <p class='reason'>(Calculated as product of all model win probabilities)</p>
    </div>
    """, unsafe_allow_html=True)
