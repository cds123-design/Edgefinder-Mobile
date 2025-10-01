# edgefinder_v9b.py
# Fixed: add us2 region, use real soccer league keys, show diagnostics when empty,
#        keep DK-only moneyline, 3-day window, dark UI with light Run button.

import os
from datetime import datetime, timedelta
import requests
import pandas as pd
import streamlit as st

APP_TITLE = "📱 EdgeFinder — Mobile (DK)"
# IMPORTANT: include us2; DK shows up here a lot.
REGIONS = "us,us2,uk,eu,au"
MARKET = "h2h"
ODDS_FORMAT = "decimal"
DAYS_FROM = 3
BOOKMAKER_KEY = "draftkings"

# Core US leagues + Euro hoops + specific soccer leagues (so we don’t miss returns)
SPORT_KEYS = [
    "americanfootball_nfl",
    "baseball_mlb",
    "basketball_nba",
    "icehockey_nhl",
    # Soccer (major comps that DK commonly lists):
    "soccer_uefa_champions_league",
    "soccer_uefa_europa_league",
    "soccer_usa_mls",
    "soccer_england_premier_league",
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    # Euro/World basketball:
    "basketball_euroleague",
    "basketball_eurocup",
    "basketball_fiba",
    # Table Tennis – TT Elite Series
    "table_tennis_tt_elite_series"
]

SPORT_ICON = {
    "americanfootball_nfl": "🏈 NFL",
    "baseball_mlb": "⚾ MLB",
    "basketball_nba": "🏀 NBA",
    "icehockey_nhl": "🏒 NHL",
    "soccer_uefa_champions_league": "⚽ UCL",
    "soccer_uefa_europa_league": "⚽ UEL",
    "soccer_usa_mls": "⚽ MLS",
    "soccer_england_premier_league": "⚽ EPL",
    "soccer_italy_serie_a": "⚽ Serie A",
    "soccer_spain_la_liga": "⚽ La Liga",
    "soccer_germany_bundesliga": "⚽ Bundesliga",
    "soccer_france_ligue_one": "⚽ Ligue 1",
    "basketball_euroleague": "🏀 EuroLeague",
    "basketball_eurocup": "🏀 EuroCup",
    "basketball_fiba": "🏀 FIBA",
    "table_tennis_tt_elite_series": "🏓 TT Elite",
}

HOME_ADV_PP = 3.0
CAP_FLOOR = 4.0
CAP_CEIL  = 96.0
NEUTRAL_EDGE_PP = 0.01

st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="centered")
st.markdown("""
<style>
.block-container { padding-top:.75rem; padding-bottom:3rem; }
body, .stApp { background:#0f1117; color:#e9eef6; }
.card { background:#12161f; border:1px solid #1f2633; border-radius:18px;
        padding:16px 16px 14px; margin-bottom:14px; box-shadow:0 4px 16px rgba(0,0,0,.35); }
.badge{border-radius:999px;padding:6px 12px;font-weight:700}
.badge.play{background:#19c37d;color:#00140b}
.badge.neutral{background:#ffd166;color:#2e2300}
.badge.pass{background:#ff4d4f;color:#2e0000}
.hline{border-top:1px solid rgba(255,255,255,.08);margin:10px 0}
.small{font-size:.9rem;opacity:.95}
.sport{font-weight:700;letter-spacing:.25px;margin-bottom:6px}
.title{font-size:1.05rem;font-weight:800;margin-bottom:8px}
.kv{margin-bottom:6px}.kv b{color:#dbe6f6}
.row-ok{background:linear-gradient(90deg,#0e4429 0%,#003d2f 100%);color:#eafff4}
.row-mid{background:linear-gradient(90deg,#3f2e00 0%,#342600 100%);color:#fff4d6}
.row-bad{background:linear-gradient(90deg,#3d0c0c 0%,#360000 100%);color:#ffeaea}
/* Light primary buttons on dark bg */
div[data-testid="stButton"] > button {
  background:#ffffff !important; color:#0f67ff !important;
  border:1px solid #e6e8ec !important; border-radius:10px !important; font-weight:800 !important;
}
</style>
""", unsafe_allow_html=True)

st.title(APP_TITLE)

with st.sidebar:
    st.subheader("Settings")
    api_key = st.text_input("The Odds API Key", type="password", value=os.getenv("THE_ODDS_API_KEY", ""))
    edge_threshold = st.slider("Min edge % for PLAY", 0.0, 20.0, 3.0, 0.25)
    top10_toggle = st.checkbox("Show Top 10 by Model Win %", value=False)
    search = st.text_input("Filter by team", placeholder="e.g., Arsenal, Rams…")
    st.caption("DK odds • Decimal • Next 3 days • One card per game")

c1, c2 = st.columns(2)
run_click = c1.button("▶️ Run Model", use_container_width=True)
ref_click = c2.button("🔄 Refresh", use_container_width=True)

def implied_from_decimal(dec):
    try:
        dec = float(dec)
        return 1.0/dec if dec>0 else None
    except: return None

def normalize_probs(vals):
    nums = [v for v in vals if v is not None]
    s = sum(nums)
    if s<=0: return vals
    return [(v/s if v is not None else None) for v in vals]

def cap_pct(p): return max(CAP_FLOOR/100, min(CAP_CEIL/100, p))
def model_prob_from_market(mkt, is_home): 
    if mkt is None: return None
    bump = (HOME_ADV_PP/100.0) if is_home else 0.0
    return cap_pct(mkt + bump)

def to_local(iso_str):
    try:
        return datetime.fromisoformat(iso_str.replace("Z","+00:00")).astimezone()
    except:
        return None

def pick_label(edge_pct, thr):
    if edge_pct is None: return "PASS"
    if abs(edge_pct) < NEUTRAL_EDGE_PP: return "NEUTRAL"
    return "PLAY" if edge_pct >= thr else "PASS"

def row_css(label):
    return "row-ok" if label=="PLAY" else ("row-mid" if label=="NEUTRAL" else "row-bad")

def fetch_sport(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = dict(
        apiKey=api_key, regions=REGIONS, markets=MARKET, oddsFormat=ODDS_FORMAT,
        bookmakers=BOOKMAKER_KEY, dateFormat="iso"
    )
    r = requests.get(url, params=params, timeout=25)
    return r

if not api_key:
    st.info("Add your **The Odds API** key, then press **Run Model**.")
    st.stop()
if not (run_click or ref_click):
    st.info("Press **Run Model** to fetch DK odds and compute plays.")
    st.stop()

now_local = datetime.now().astimezone()
end_local = now_local + timedelta(days=DAYS_FROM)

diag = []      # diagnostics text lines
rows = []

with st.spinner("Fetching DK odds & computing…"):
    for sk in SPORT_KEYS:
        try:
            r = fetch_sport(sk)
            diag.append(f"{sk}: HTTP {r.status_code} • Remaining: {r.headers.get('x-requests-remaining','?')}")
            if r.status_code != 200:
                continue
            data = r.json()
            diag.append(f"  → {len(data)} events returned")

            for ev in data:
                ct = ev.get("commence_time")
                if not ct: 
                    continue
                start_dt = to_local(ct)
                if not start_dt or not (now_local <= start_dt <= end_local):
                    continue

                home = ev.get("home_team") or ""
                teams = ev.get("teams", [])
                away = [t for t in teams if t != home]
                away = away[0] if away else ""

                dk_mkt = None
                for bk in ev.get("bookmakers", []):
                    if bk.get("key") == BOOKMAKER_KEY:
                        for m in bk.get("markets", []):
                            if m.get("key") == MARKET:
                                dk_mkt = m; break
                if not dk_mkt: 
                    continue

                price_home = price_away = price_draw = None
                for oc in dk_mkt.get("outcomes", []):
                    nm = (oc.get("name") or "").strip()
                    pr = oc.get("price")
                    if pr is None: continue
                    pr = float(pr)
                    if nm.lower() == home.lower(): price_home = pr
                    elif nm.lower() == away.lower(): price_away = pr
                    elif nm.lower() == "draw": price_draw = pr

                if price_home is None or price_away is None:
                    continue

                p_home_m = implied_from_decimal(price_home)
                p_away_m = implied_from_decimal(price_away)
                p_draw_m = implied_from_decimal(price_draw) if price_draw else None
                p_home, p_away, p_draw = normalize_probs([p_home_m, p_away_m, p_draw_m])

                m_home = model_prob_from_market(p_home, is_home=True)
                m_away = model_prob_from_market(p_away, is_home=False)
                m_draw = p_draw if p_draw is not None else None

                cands = []
                if m_home is not None: cands.append((home, m_home, p_home, price_home))
                if m_away is not None: cands.append((away, m_away, p_away, price_away))
                if price_draw and m_draw is not None: cands.append(("Draw", m_draw, p_draw, price_draw))
                if not cands: 
                    continue

                pick_name, pick_model_p, pick_market_p, pick_price = max(cands, key=lambda x: x[1])
                edge_pct = (pick_model_p - pick_market_p) * 100.0 if pick_market_p is not None else None
                label = pick_label(edge_pct, edge_threshold)

                # Odds line — both teams; Draw separate if present
                dk_line = f"{home} {price_home:.2f} | "
                if price_draw: dk_line += f"Draw {price_draw:.2f} | "
                dk_line += f"{away} {price_away:.2f}"

                rows.append({
                    "sport_key": sk,
                    "sport": SPORT_ICON.get(sk, sk),
                    "matchup": f"{home} vs {away}",
                    "dk_line": dk_line,
                    "pick": pick_name,
                    "pick_model_pct": pick_model_p*100.0,
                    "market_pct": pick_market_p*100.0 if pick_market_p is not None else None,
                    "edge_pct": edge_pct,
                    "start_local": start_dt.strftime("%b %d, %Y — %I:%M %p"),
                    "label": label
                })
        except Exception as e:
            diag.append(f"{sk}: ERROR {type(e).__name__}")

df = pd.DataFrame(rows)
q = st.text_input("🔎 Filter by team", value="", placeholder="Type a team name…")
if q.strip():
    needle = q.lower().strip()
    df = df[df["matchup"].str.lower().str.contains(needle) | df["pick"].str.lower().str.contains(needle)]

if df.empty:
    st.warning("No DK moneyline markets found for the next 3 days. Try again later or widen filters.")
    with st.expander("Diagnostics"):
        st.write("\n".join(diag))
    st.stop()

df = df.sort_values(["pick_model_pct","edge_pct"], ascending=[False, False])
if top10_toggle: df = df.head(10)

st.caption(f"Updated: {datetime.now().astimezone().strftime('%b %d, %Y — %I:%M %p %Z')}")
st.success(f"Found {len(df)} DK games (regions: {REGIONS}; window: {DAYS_FROM} days)")

def badge_cls(x): return "play" if x=="PLAY" else ("neutral" if x=="NEUTRAL" else "pass")
def row_cls(x): return "row-ok" if x=="PLAY" else ("row-mid" if x=="NEUTRAL" else "row-bad")

for _, r in df.iterrows():
    mkt_disp = f"{r['market_pct']:.1f}%" if pd.notna(r['market_pct']) else "—"
    card = f"""
    <div class="card {row_cls(r['label'])}">
      <div class="sport">{r['sport']}</div>
      <div class="title">{r['matchup']}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin:4px 0 8px;">
        <div class="badge {badge_cls(r['label'])}">{r['label']}</div>
        <div class="small">Start: {r['start_local']}</div>
      </div>

      <div class="kv"><b>DK Odds:</b> {r['dk_line']}</div>
      <div class="kv"><b>Model Win %:</b> {r['pick_model_pct']:.1f}%</div>
      <div class="kv"><b>Market Win %:</b> {mkt_disp}</div>
      <div class="kv"><b>Edge:</b> {r['edge_pct']:+.2f}%</div>

      <div class="hline"></div>
      <div class="small">🧠 Model selects <b>{r['pick']}</b>. Edge = model − market (with small home boost).</div>
    </div>
    """
    st.markdown(card, unsafe_allow_html=True)

with st.expander("Diagnostics"):
    st.write("\n".join(diag))
