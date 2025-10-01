import streamlit as st
import requests
import datetime as dt

st.set_page_config(page_title="EdgeFinder — Mobile (DK)", layout="centered")

# --- HEADER ---
st.markdown("""
<h1 style='text-align: center;'>📱 EdgeFinder — Mobile (DK)</h1>
<p style='text-align:center; font-size:16px;'>Compare <b>model vs DraftKings odds</b> — filter by win % & edge.</p>
""", unsafe_allow_html=True)

# --- SETTINGS ---
api_key = st.text_input("🔑 Enter your Odds API key", type="password")
min_edge = st.slider("📈 Minimum edge %", 0.0, 10.0, 1.5)
show_top10 = st.checkbox("Show Top 10 by Model Win %", value=True)

# --- DATE RANGE (Today + Tomorrow only) ---
now_local = dt.datetime.now()
end_local = now_local + dt.timedelta(days=2)

sports = [
    "americanfootball_nfl", "baseball_mlb", "basketball_nba", "icehockey_nhl",
    "soccer_epl", "soccer_uefa_champions_league", "soccer_spain_la_liga",
    "soccer_italy_serie_a", "soccer_germany_bundesliga", "soccer_france_ligue_one"
]

# --- RUN MODEL ---
if st.button("▶️ Run Model"):
    if not api_key:
        st.warning("Please enter your API key.")
    else:
        st.info("Fetching odds and running model...")

        all_games = []
        for sport in sports:
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            params = {
                "apiKey": api_key,
                "regions": "us",
                "markets": "h2h",
                "oddsFormat": "decimal"
            }
            try:
                res = requests.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    for ev in data:
                        start_time = dt.datetime.fromisoformat(ev['commence_time'].replace("Z", "+00:00"))
                        if now_local <= start_time <= end_local:
                            game = {"sport": sport, "teams": ev["teams"], "commence": start_time}
                            if "bookmakers" in ev and ev["bookmakers"]:
                                dk = next((b for b in ev["bookmakers"] if b["key"] == "draftkings"), None)
                                if dk:
                                    outcomes = dk["markets"][0]["outcomes"]
                                    for o in outcomes:
                                        game[o["name"]] = o["price"]
                            all_games.append(game)
            except Exception as e:
                st.error(f"Error fetching {sport}: {e}")

        if not all_games:
            st.warning("⚠️ No DK markets found for the next 2 days.")
        else:
            results = []
            for g in all_games:
                try:
                    if len(g["teams"]) < 2: 
                        continue
                    t1, t2 = g["teams"]
                    odds1, odds2 = g.get(t1, 0), g.get(t2, 0)
                    if not odds1 or not odds2:
                        continue
                    
                    implied1, implied2 = 100 / odds1, 100 / odds2
                    total_implied = implied1 + implied2
                    market1, market2 = implied1 / total_implied, implied2 / total_implied

                    # Simple model prediction
                    model1 = min(max(market1 + 0.03, 0), 1)
                    model2 = min(max(market2 - 0.03, 0), 1)

                    favorite = t1 if model1 > model2 else t2
                    market_fav = t1 if market1 > market2 else t2

                    edge = (max(model1, model2) - max(market1, market2)) * 100
                    rec = "🟩 PLAY" if edge >= min_edge else ("🟨 NEUTRAL" if edge > 0 else "🟥 PASS")
                    reason = (
                        "Model sees higher win probability than market." if rec == "🟩 PLAY" else
                        "Edge under threshold." if rec == "🟨 NEUTRAL" else
                        "Model and market disagree."
                    )

                    results.append({
                        "match": f"{t1} vs {t2}",
                        "market_fav": market_fav,
                        "model_fav": favorite,
                        "odds": f"{favorite} {g.get(favorite, '')}",
                        "model_win": round(max(model1, model2) * 100, 1),
                        "edge": round(edge, 1),
                        "rec": rec,
                        "reason": reason,
                        "time": g["commence"].strftime("%b %d, %Y — %I:%M %p")
                    })
                except Exception:
                    continue

            if show_top10:
                results = sorted(results, key=lambda x: x["model_win"], reverse=True)[:10]

            for r in results:
                st.markdown(f"""
                ⚽ **{r['match']}**
                \n📉 **DK Odds:** {r['odds']}
                \n🧠 **Model Favorite:** {r['model_fav']}
                \n🏪 **Market Favorite:** {r['market_fav']}
                \n📊 **Model Win %:** {r['model_win']}%
                \n📈 **Edge:** {r['edge']}%
                \n🎯 **Recommendation:** {r['rec']}
                \n💡 *Reason:* {r['reason']}
                \n🕒 **Start:** {r['time']}
                """)
