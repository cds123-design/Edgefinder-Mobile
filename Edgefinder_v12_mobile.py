# edgefinder_v9.py
# EdgeFinder — Mobile (DK-only) • Today+Tomorrow • Play/Pass • One row per game
# Streamlit 1.30+ required

import os
import math
import time
import json
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd
import streamlit as st

# -----------------------------
# --------- CONSTANTS ----------
# -----------------------------
APP_TITLE = "📱 EdgeFinder — Mobile (DK)"
TZ = timezone.utc  # we’ll display local later, but sort in UTC

# Sports keys to pull from The Odds API (DK moneyline only)
SPORT_KEYS = [
    # US major
    "baseball_mlb",
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    # Soccer (The Odds API aggregates many leagues under this)
    "soccer",
    # Euro & world basketball (The Odds API uses basketball_euroleague etc.)
    "basketball_euroleague",
    "basketball_eurocup",
    "basketball_fiba",
]

BOOKMAKER_TARGET = "DraftKings"
REGION = "us"
MARKET = "h2h"           # moneyline
ODDS_FORMAT = "decimal"  # you asked for decimals only
DAYS_FROM = 2            # today + tomorrow window

# Mobile-friendly sport names / emojis
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

# -----------------------------
# --------- HELPERS -----------
# -----------------------------
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

def implied_prob_from_decimal(d: float) -> float:
    """Decimal odds -> implied probability (0..1)."""
    try:
        return 1.0 / float(d) if d and d > 0 else None
    except Exception:
        return None

def find_dk_market(outcomes_block: list[str|dict]) -> dict | None:
    """
    Given a list of bookmaker blocks, return DraftKings H2H market with outcomes.
    Structure per The Odds API (v4):
      bookmakers: [{key,name,markets:[{key:'h2h',outcomes:[{name,price}, ...]}]}]
    """
    if not outcomes_block:
        return None
    for b in outcomes_block:
        try:
            name = b.get("title") or b.get("name") or ""
            if name.lower().startswith("draftkings") or "draftkings" in name.lower():
                for m in b.get("markets", []):
                    if m.get("key") == "h2h":
                        return m
        except Exception:
            continue
    return None

def pretty_dt_local(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return iso_str
    # Convert to user local; Streamlit handles tz display best as naive local string
    # We’ll just show in the browser’s local zone by omitting tz here
    return dt.astimezone().strftime("%b %d, %Y — %I:%M %p")

def model_win_prob(
    team_name: str,
    dk_prob: float,
    is_home: bool,
    home_adv: float = 0.03,
    floor: float = 0.04,
    ceiling: float = 0.96,
) -> float:
    """
    Simple, **transparent** baseline model:
      - start from DK implied probability
      - add a modest home boost (default 3 pp) if home
      - pull slightly away from extremes via a tiny prior (4% / 96% caps)
    """
    if dk_prob is None:
        return None
    base = dk_prob + (home_adv if is_home else 0.0)
    return clamp(base, floor, ceiling)

def play_pass_label(edge_pct: float, threshold: float) -> str:
    return "PLAY" if edge_pct is not None and edge_pct >= threshold else "PASS"

def reason_text(
    pick: str, model_p: float, market_p: float, edge_pct: float,
    dk_price: float, team_is_home: bool
) -> str:
    parts = []
    parts.append(f"Model projects **{pick}** to win **{model_p*100:.1f}%** vs market **{market_p*100:.1f}%**.")
    parts.append(f"DraftKings price **{dk_price:.2f}** → market **{market_p*100:.1f}%**.")
    parts.append(f"Edge **{edge_pct:.2f}%**.")
    if team_is_home:
        parts.append("Includes small home-court/ice/field boost.")
    return " ".join(parts)

def row_style(play_or_pass: str) -> str:
    # bg gradient chips
    if play_or_pass == "PLAY":
        return "background: linear-gradient(90deg, #0e4429 0%, #003d2f 100%); color:#eafff4;"
    return "background: linear-gradient(90deg, #3d0c0c 0%, #360000 100%); color:#ffeaea;"

# -----------------------------
# ---------- UI ---------------
# -----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="centered")

# Dark mobile-friendly container styles
st.markdown("""
<style>
/* Tighten cards on mobile */
.block-container { padding-top: 0.75rem; padding-bottom: 3rem; }
.card { border-radius: 18px; padding: 18px 16px; margin-bottom: 14px; border: 1px solid #222; }
.badge { border-radius: 999px; padding: 6px 12px; font-weight: 700; }
.badge.play { background: #19c37d; color: #00140b; }
.badge.pass { background: #ff4d4f; color: #2e0000; }
.meta { opacity: 0.9; font-size: 0.93rem; }
.hline { border-top: 1px solid rgba(255,255,255,0.08); margin: 12px 0; }
.small { font-size: 0.9rem; opacity: 0.95; }
.sport { font-weight: 700; letter-spacing: .2px; margin-bottom: 6px; }
.title { font-size: 1.05rem; font-weight: 800; margin-bottom: 8px; }
.kv { margin-bottom: 6px; }
</style>
""", unsafe_allow_html=True)

st.title(APP_TITLE)

with st.sidebar:
    st.subheader("Settings")
    api_key = st.text_input("The Odds API Key", type="password")
    threshold = st.slider("Min edge % for PLAY", 0.0, 20.0, 2.0, 0.25)
    top10_toggle = st.checkbox("Show Top 10 by model win %", value=False)
    search = st.text_input("Filter by team name", placeholder="e.g., Arsenal, Napoli, Rams...")

# Action buttons (top)
colA, colB = st.columns([1,1])
run_click = colA.button("▶️ Run Model", use_container_width=True)
refresh_click = colB.button("🔄 Refresh", use_container_width=True)

if not api_key:
    st.info("Add your **The Odds API** key in the sidebar, then press **Run Model**.")
    st.stop()

def fetch_odds_for_sport(sport_key: str) -> list[dict]:
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": REGION,
        "markets": MARKET,
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": "iso",
        "bookmakers": "draftkings",
        "daysFrom": DAYS_FROM,
    }
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def build_rows() -> pd.DataFrame:
    rows = []
    now_utc = datetime.now(TZ)
    end_utc = now_utc + timedelta(days=DAYS_FROM)

    for sk in SPORT_KEYS:
        try:
            data = fetch_odds_for_sport(sk)
        except Exception as e:
            # Don’t fail the whole run; keep going
            continue

        for ev in data:
            try:
                commence_iso = ev.get("commence_time")
                if not commence_iso:
                    continue
                dt = datetime.fromisoformat(commence_iso.replace("Z","+00:00"))
                if not (now_utc <= dt <= end_utc):
                    continue

                home = ev.get("home_team") or ""
                away = [t for t in ev.get("teams", []) if t != home]
                away = away[0] if away else ""

                bm = ev.get("bookmakers", [])
                dk_market = find_dk_market(bm)
                if not dk_market:
                    continue

                # Map outcomes
                dk_price_by_name = {}
                for oc in dk_market.get("outcomes", []):
                    nm = oc.get("name","")
                    price = oc.get("price")
                    if not price:
                        continue
                    dk_price_by_name[nm] = float(price)

                # We want the two team prices and (if soccer) a Draw
                price_home = dk_price_by_name.get(home)
                price_away = dk_price_by_name.get(away)
                price_draw = dk_price_by_name.get("Draw")  # soccer sometimes present, else None

                # Derive DK market probabilities
                p_home_mkt = implied_prob_from_decimal(price_home) if price_home else None
                p_away_mkt = implied_prob_from_decimal(price_away) if price_away else None
                p_draw_mkt = implied_prob_from_decimal(price_draw) if price_draw else None

                # Normalize in case all three exist (soccer)
                probs = [p for p in [p_home_mkt, p_away_mkt, p_draw_mkt] if p is not None]
                if probs:
                    s = sum(probs)
                    if s > 0:
                        if p_home_mkt is not None: p_home_mkt /= s
                        if p_away_mkt is not None: p_away_mkt /= s
                        if p_draw_mkt is not None: p_draw_mkt /= s

                # Model probabilities
                m_home = model_win_prob(home, p_home_mkt, True)
                m_away = model_win_prob(away, p_away_mkt, False)
                m_draw = clamp(p_draw_mkt, 0, 1) if p_draw_mkt is not None else None  # neutral draw

                # Pick = argmax of model
                cand = [
                    ("Draw", m_draw, price_draw, p_draw_mkt),
                    (home,  m_home, price_home, p_home_mkt),
                    (away,  m_away, price_away, p_away_mkt),
                ]
                cand = [c for c in cand if c[1] is not None and c[2] is not None]
                if not cand:
                    continue
                pick_name, pick_model_p, pick_dk_price, pick_market_p = max(cand, key=lambda x: x[1])

                edge_pct = (pick_model_p - pick_market_p) * 100.0 if pick_market_p is not None else None
                label = play_pass_label(edge_pct, threshold)

                # Reason
                team_is_home = (pick_name == home)
                why = reason_text(
                    pick_name, pick_model_p, pick_market_p, edge_pct,
                    pick_dk_price, team_is_home
                )

                rows.append({
                    "sport_key": sk,
                    "sport": SPORT_ICON.get(sk, sk),
                    "commence_utc": commence_iso,
                    "commence_local": pretty_dt_local(commence_iso),
                    "home": home,
                    "away": away,
                    "matchup": f"{home} vs {away}",
                    "dk_favorite": min(
                        [(home, price_home or 9999), (away, price_away or 9999), ("Draw", price_draw or 9999)],
                        key=lambda x: x[1]
                    )[0],
                    "dk_price_home": price_home,
                    "dk_price_away": price_away,
                    "dk_price_draw": price_draw,
                    "model_home_pct": m_home*100 if m_home is not None else None,
                    "model_away_pct": m_away*100 if m_away is not None else None,
                    "model_draw_pct": m_draw*100 if m_draw is not None else None,
                    "pick": pick_name,
                    "pick_model_pct": pick_model_p*100 if pick_model_p is not None else None,
                    "market_pct": pick_market_p*100 if pick_market_p is not None else None,
                    "edge_pct": edge_pct,
                    "label": label,
                    "reason": why,
                })
            except Exception:
                continue

    df = pd.DataFrame(rows)
    if not df.empty:
        # Sort by model confidence (descending)
        df = df.sort_values(by=["pick_model_pct", "edge_pct"], ascending=[False, False]).reset_index(drop=True)
    return df

# -----------------------------
# ----------- RUN -------------
# -----------------------------
should_run = run_click or refresh_click
if not should_run:
    st.info("Set your key and threshold in the sidebar, then press **Run Model**.")
    st.stop()

with st.spinner("Fetching DK odds and running model…"):
    try:
        df = build_rows()
    except requests.HTTPError as e:
        st.error(f"HTTP error from The Odds API: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        st.stop()

if df.empty:
    st.warning("No DK moneyline markets found for the next two days.")
    st.stop()

# Filter by search
if search:
    s = search.lower().strip()
    df = df[df["matchup"].str.lower().str.contains(s) | df["pick"].str.lower().str.contains(s)]

# Top-10 toggle (by model win%)
if top10_toggle and not df.empty:
    df = df.head(10)

# --------------- CARDS ---------------
st.caption(f"Updated: {datetime.now().astimezone().strftime('%b %d, %Y — %I:%M %p %Z')}")
st.success(f"Found {len(df)} games")

for _, r in df.iterrows():
    badge_class = "play" if r["label"] == "PLAY" else "pass"
    dk_lines = []
    if pd.notna(r["dk_price_home"]):
        dk_lines.append(f"{r['home']} ({r['dk_price_home']:.2f})")
    if pd.notna(r["dk_price_away"]):
        dk_lines.append(f"{r['away']} ({r['dk_price_away']:.2f})")
    if pd.notna(r["dk_price_draw"]):
        dk_lines.append(f"Draw ({r['dk_price_draw']:.2f})")

    card = f"""
    <div class="card" style="{row_style(r['label'])}">
      <div class="sport">{r['sport']}</div>
      <div class="title">{r['matchup']}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin:6px 0 10px 0;">
        <div class="badge {badge_class}">{r['label']}</div>
        <div class="small">Start: {r['commence_local']}</div>
      </div>

      <div class="kv"><b>DK Favorite:</b> {r['dk_favorite']}</div>
      <div class="kv"><b>DK Odds:</b> {'  •  '.join(dk_lines) if dk_lines else '—'}</div>

      <div class="kv"><b>Model Favorite:</b> {r['pick']}</div>
      <div class="kv"><b>Model Win %:</b> {r['pick_model_pct']:.1f}%</div>
      <div class="kv"><b>Market Win %:</b> {r['market_pct']:.1f}%</div>
      <div class="kv"><b>Edge:</b> {r['edge_pct']:.2f}%</div>

      <div class="hline"></div>
      <div class="small">{r['reason']}</div>
    </div>
    """
    st.markdown(card, unsafe_allow_html=True)

st.caption("• DK odds only • Decimal • Today + Tomorrow • One row per game • Color-coded Play/Pass")

# -----------------------------
# ---- FOOTER / SAFETY --------
# -----------------------------
st.markdown(
    "<div class='small' style='opacity:.8;margin-top:10px;'>"
    "This is a simple, transparent baseline model that starts from market (DK) implied win % "
    "and applies a small home advantage and soft caps. It does not use injuries or lineups. "
    "Use at your own risk; gamble responsibly.</div>",
    unsafe_allow_html=True
)
