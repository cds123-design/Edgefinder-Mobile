# edgefinder_mobile_dark.py
# Mobile-first, dark theme • DK-only • Today+Tomorrow • One card per game
# Shows BOTH teams (and Draw for soccer) • Model Win %, DK odds, Edge, Reason
# PLAY / NEUTRAL / PASS (color-coded) • Sorted by Model Win % • Top-10 toggle

import os
from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import streamlit as st

APP_TITLE = "📱 EdgeFinder — Mobile (DK)"
REGION = "us"
MARKET = "h2h"
ODDS_FORMAT = "decimal"
DAYS_FROM = 2  # today + tomorrow
BOOKMAKER = "draftkings"  # key match against API "bookmakers[].key"
SPORT_KEYS = [
    "baseball_mlb",
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "soccer",                   # aggregated soccer feed (has Draw)
    "basketball_euroleague",
    "basketball_eurocup",
    "basketball_fiba"
]

SPORT_ICON = {
    "americanfootball_nfl": "🏈 NFL",
    "baseball_mlb": "⚾ MLB",
    "basketball_nba": "🏀 NBA",
    "icehockey_nhl": "🏒 NHL",
    "soccer": "⚽ Soccer",
    "basketball_euroleague": "🏀 EuroLeague",
    "basketball_eurocup": "🏀 EuroCup",
    "basketball_fiba": "🏀 FIBA",
}

# --- SIMPLE, TRANSPARENT MODEL SETTINGS ---
HOME_ADV_PP = 3.0   # percentage points added to the HOME team’s model win %
CAP_FLOOR = 4.0     # min model % (avoid 0/100 extremes)
CAP_CEIL  = 96.0    # max model %
NEUTRAL_EDGE_PP = 0.01  # treat tiny +/- as neutral if |edge| < this (%)

# ---------------- UI & THEME ----------------
st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="centered")
st.markdown("""
<style>
.block-container { padding-top: .75rem; padding-bottom: 3rem; }
body, .stApp { background: #0e1117; color: #e9eef6; }
.card { background: #12161f; border:1px solid #1f2633; border-radius:18px; padding:16px 16px 14px; margin-bottom:14px; box-shadow:0 4px 16px rgba(0,0,0,.35);}
.badge { border-radius: 999px; padding:6px 12px; font-weight: 700; }
.badge.play { background:#19c37d; color:#00140b; }
.badge.neutral { background:#ffd166; color:#2e2300; }
.badge.pass { background:#ff4d4f; color:#2e0000; }
.meta { opacity:.9; font-size:.93rem; }
.hline { border-top:1px solid rgba(255,255,255,.08); margin:10px 0; }
.small { font-size:.9rem; opacity:.95; }
.sport { font-weight:700; letter-spacing:.25px; margin-bottom:6px; }
.title { font-size:1.05rem; font-weight:800; margin-bottom:8px; }
.kv { margin-bottom:6px; }
.kv b { color:#dbe6f6; }
.row-ok { background: linear-gradient(90deg, #0e4429 0%, #003d2f 100%); color:#eafff4; }
.row-mid { background: linear-gradient(90deg, #3f2e00 0%, #342600 100%); color:#fff4d6; }
.row-bad { background: linear-gradient(90deg, #3d0c0c 0%, #360000 100%); color:#ffeaea; }
</style>
""", unsafe_allow_html=True)

st.title(APP_TITLE)

with st.sidebar:
    st.subheader("Settings")
    api_key = st.text_input("The Odds API Key", type="password", value=os.getenv("THE_ODDS_API_KEY", ""))
    edge_threshold = st.slider("Min edge % for PLAY", 0.0, 20.0, 3.0, 0.25)
    top10_toggle = st.checkbox("Show Top 10 by Model Win %", value=False)
    search = st.text_input("Filter by team", placeholder="e.g., Arsenal, Napoli, Rams…")
    st.caption("DK odds • Decimal • Today + Tomorrow • One card per game")

colA, colB = st.columns(2)
run_click = colA.button("▶️ Run Model", use_container_width=True)
ref_click = colB.button("🔄 Refresh", use_container_width=True)

# --------------- HELPERS ---------------
def implied_from_decimal(dec):
    try:
        dec = float(dec)
        return 1.0 / dec if dec > 0 else None
    except Exception:
        return None

def normalize_probs(items):
    vals = [v for v in items if v is not None]
    s = sum(vals)
    if s <= 0: 
        return items
    return [ (v / s if v is not None else None) for v in items ]

def cap_pct(pct):
    return max(CAP_FLOOR/100.0, min(CAP_CEIL/100.0, pct))

def to_local_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z","+00:00")).astimezone()
        return dt.strftime("%b %d, %Y — %I:%M %p")
    except:
        return iso_str

def fetch_sport(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": REGION,
        "markets": MARKET,
        "oddsFormat": ODDS_FORMAT,
        "bookmakers": BOOKMAKER,
        "dateFormat": "iso",
        "daysFrom": DAYS_FROM
    }
    r = requests.get(url, params=params, timeout=25)
    if r.status_code == 422:
        return []
    r.raise_for_status()
    return r.json()

def pick_label(edge_pct, thresh):
    if edge_pct is None:
        return "PASS"
    if abs(edge_pct) < NEUTRAL_EDGE_PP:
        return "NEUTRAL"
    if edge_pct >= thresh:
        return "PLAY"
    return "PASS"

def row_css(label):
    if label == "PLAY": return "row-ok"
    if label == "NEUTRAL": return "row-mid"
    return "row-bad"

# --- baseline winner-first model: start from market, small home bump, soft caps
def model_prob_from_market(market_prob, is_home):
    if market_prob is None:
        return None
    bump = (HOME_ADV_PP/100.0) if is_home else 0.0
    return cap_pct(market_prob + bump)

# --------------- RUN GUARD ---------------
if not api_key:
    st.info("Add your **The Odds API** key in the sidebar, then press **Run Model**.")
    st.stop()

if not (run_click or ref_click):
    st.info("Press **Run Model** to fetch DK odds and compute plays.")
    st.stop()

# --------------- FETCH + BUILD ---------------
with st.spinner("Fetching DK odds and computing plays…"):
    rows = []
    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc + timedelta(days=DAYS_FROM)

    for sk in SPORT_KEYS:
        try:
            data = fetch_sport(sk)
        except Exception:
            continue

        for ev in data:
            try:
                commence = ev.get("commence_time")
                if not commence:
                    continue
                dt = datetime.fromisoformat(commence.replace("Z","+00:00"))
                if not (now_utc <= dt <= end_utc):
                    continue

                home = ev.get("home_team") or ""
                # derive away
                teams_list = ev.get("teams", [])
                away = [t for t in teams_list if t != home]
                away = away[0] if away else ""

                # find DK market
                dk = None
                for b in ev.get("bookmakers", []):
                    if b.get("key") == BOOKMAKER:
                        for m in b.get("markets", []):
                            if m.get("key") == MARKET:
                                dk = m
                                break
                if not dk:
                    continue

                # map outcomes/prices
                price_home = price_away = price_draw = None
                for oc in dk.get("outcomes", []):
                    nm = (oc.get("name") or "").strip()
                    pr = oc.get("price")
                    if pr is None:
                        continue
                    pr = float(pr)
                    if nm.lower() == home.lower():
                        price_home = pr
                    elif nm.lower() == away.lower():
                        price_away = pr
                    elif nm.lower() == "draw":
                        price_draw = pr

                # need at least home & away prices
                if price_home is None or price_away is None:
                    continue

                # market implied and normalize (include draw if present for soccer)
                p_home_mkt = implied_from_decimal(price_home)
                p_away_mkt = implied_from_decimal(price_away)
                p_draw_mkt = implied_from_decimal(price_draw) if price_draw else None

                probs = [p_home_mkt, p_away_mkt, p_draw_mkt]
                p_home_norm, p_away_norm, p_draw_norm = normalize_probs(probs)

                # model probs (winner-first)
                m_home = model_prob_from_market(p_home_norm, is_home=True)
                m_away = model_prob_from_market(p_away_norm, is_home=False)
                m_draw = p_draw_norm if p_draw_norm is not None else None  # neutral for draw

                # pick = argmax(model)
                candidates = [
                    ("Draw", m_draw, p_draw_norm, price_draw),
                    (home, m_home, p_home_norm, price_home),
                    (away, m_away, p_away_norm, price_away),
                ]
                candidates = [c for c in candidates if c[1] is not None and c[3] is not None]
                if not candidates:
                    continue
                pick_name, pick_model_p, pick_market_p, pick_price = max(candidates, key=lambda x: x[1])

                edge_pct = (pick_model_p - pick_market_p) * 100.0 if pick_market_p is not None else None
                label = pick_label(edge_pct, edge_threshold)

                # DK odds line — show BOTH teams (and Draw when present)
                if price_draw:
                    dk_line = f"{home} {price_home:.2f} | Draw {price_draw:.2f} | {away} {price_away:.2f}"
                else:
                    dk_line = f"{home} {price_home:.2f} | {away} {price_away:.2f}"

                # reason (concise)
                reason = (
                    f"Model projects **{pick_name}** {pick_model_p*100:.1f}% vs market {pick_market_p*100:.1f}% "
                    f"(Edge {edge_pct:+.2f}%). Small home boost applied."
                    if pick_name in (home, away) else
                    f"Draw considered (soccer). Best outcome by model at {pick_model_p*100:.1f}% vs market {pick_market_p*100:.1f}% "
                    f"(Edge {edge_pct:+.2f}%)."
                )

                rows.append({
                    "sport_key": sk,
                    "sport": SPORT_ICON.get(sk, sk),
                    "matchup": f"{home} vs {away}",
                    "dk_line": dk_line,
                    "pick": pick_name,
                    "pick_model_pct": pick_model_p*100.0,
                    "market_pct": pick_market_p*100.0 if pick_market_p is not None else None,
                    "edge_pct": edge_pct,
                    "start_local": to_local_time(commence),
                    "label": label
                })
            except Exception:
                continue

df = pd.DataFrame(rows)
if df.empty:
    st.warning("No DK moneyline markets found for the next two days.")
    st.stop()

# filter by search
q = st.text_input("🔎 Filter by team", value="", placeholder="Type a team name…")
if q.strip():
    needle = q.lower().strip()
    df = df[df["matchup"].str.lower().str.contains(needle) | df["pick"].str.lower().str.contains(needle)]

# top-10 toggle by model win %
df = df.sort_values(by=["pick_model_pct", "edge_pct"], ascending=[False, False])
if top10_toggle:
    df = df.head(10)

st.caption(f"Updated: {datetime.now().astimezone().strftime('%b %d, %Y — %I:%M %p %Z')}")
st.success(f"Found {len(df)} games")

# render cards
for _, r in df.iterrows():
    badge_cls = "play" if r["label"]=="PLAY" else ("neutral" if r["label"]=="NEUTRAL" else "pass")
    row_cls = "row-ok" if r["label"]=="PLAY" else ("row-mid" if r["label"]=="NEUTRAL" else "row-bad")
    card = f"""
    <div class="card {row_cls}">
      <div class="sport">{r['sport']}</div>
      <div class="title">{r['matchup']}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin:4px 0 8px;">
        <div class="badge {badge_cls}">{r['label']}</div>
        <div class="small">Start: {r['start_local']}</div>
      </div>

      <div class="kv"><b>DK Odds:</b> {r['dk_line']}</div>
      <div class="kv"><b>Model Win %:</b> {r['pick_model_pct']:.1f}%</div>
      <div class="kv"><b>Market Win %:</b> { (r['market_pct'] if r['market_pct'] is not None else 0):.1f}%</div>
      <div class="kv"><b>Edge:</b> {r['edge_pct']:+.2f}%</div>

      <div class="hline"></div>
      <div class="small">🧠 {r['reason'] if 'reason' in r and r['reason'] else ''}</div>
    </div>
    """
    # ensure reason exists even if key missing
    if 'reason' not in r or not r['reason']:
        reason_fallback = f"Model selects **{r['pick']}** based on higher win probability."
        card = card.replace("<div class=\"small\">🧠 </div>", f"<div class=\"small\">🧠 {reason_fallback}</div>")
    st.markdown(card, unsafe_allow_html=True)

st.caption("• DK odds only (decimal) • Today + Tomorrow • One card per game • PLAY/NEUTRAL/PASS")
