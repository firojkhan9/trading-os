# ================================================
# FILE: strategies/institutional_flow.py
# PURPOSE: FII/DII Institutional Flow Intelligence
#          Fetches daily FII/DII data from NSE
#          and produces an institutional sentiment
#          score (0-100) for use in the composite
#          scoring engine.
#
# MILESTONE 36 — FII/DII Intelligence Layer
#
# DATA SOURCE:
#   NSE India public CSV — no API key, no login.
#   URL refreshes each trading day.
#
# WHY FII/DII MATTERS:
#   FII (Foreign Institutional Investors) are the
#   biggest market movers. When they buy heavily,
#   markets usually rise. When they sell, markets fall.
#   DII (Domestic Institutionals) often buy when FIIs
#   sell — they are the "stabilizers".
#
#   Net FII buying + DII buying = very bullish.
#   FII selling + DII can't absorb = very bearish.
#
# HOW WE USE IT:
#   - Net FII flow (₹ crores) → directional signal
#   - Net DII flow → confirmation or divergence
#   - 5-day rolling trend → sustained or one-day move
#   - Combined score 0-100 feeds composite engine
# ================================================

import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import json

# ── Cache path ────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR         = os.path.join(BASE_DIR, "logs")
FII_CACHE_FILE   = os.path.join(LOGS_DIR, "fii_dii_cache.json")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── NSE FII/DII data URLs ─────────────────────────
# NSE publishes monthly participant-wise trading data.
# Primary: cash market FII/DII activity
FII_DII_URL = (
    "https://www.nseindia.com/api/fiidiiTradeReact"
)

# Fallback: NSE monthly CSV (publicly available)
FII_CSV_URL = (
    "https://archives.nseindia.com/content/fo/fii_stats_{date}.xls"
)

# Cache TTL: 6 hours (data updates once per trading day)
CACHE_TTL_HOURS = 6


# ════════════════════════════════════════════════
# DATA FETCHER
# NSE blocks simple requests without headers.
# We use browser-like headers to avoid 403s.
# ════════════════════════════════════════════════

def _nse_session() -> requests.Session:
    """Create a session that looks like a browser to NSE."""
    session = requests.Session()
    session.headers.update({
        "User-Agent":      (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/",
    })
    # Visit homepage first to get cookies (NSE requires this)
    try:
        session.get("https://www.nseindia.com", timeout=5)
    except Exception:
        pass
    return session


def fetch_fii_dii_data(days: int = 10) -> pd.DataFrame:
    """
    Fetch FII/DII daily cash market data from NSE.

    Returns a DataFrame with columns:
      Date, FII_Net, DII_Net, FII_Buy, FII_Sell, DII_Buy, DII_Sell

    All values in ₹ Crores.
    Returns empty DataFrame on failure — never crashes.
    """
    # ── Check cache first ──────────────────────────
    cached = _load_cache()
    if cached is not None:
        return cached

    # ── Fetch from NSE API ─────────────────────────
    try:
        session = _nse_session()
        response = session.get(FII_DII_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        rows = []
        for item in data:
            try:
                date_str = str(item.get("date", ""))
                fii_buy  = _parse_cr(item.get("fiiBuySell", {}).get("buyValue", 0))
                fii_sell = _parse_cr(item.get("fiiBuySell", {}).get("sellValue", 0))
                dii_buy  = _parse_cr(item.get("diiBuySell", {}).get("buyValue", 0))
                dii_sell = _parse_cr(item.get("diiBuySell", {}).get("sellValue", 0))

                rows.append({
                    "Date":     date_str,
                    "FII_Buy":  fii_buy,
                    "FII_Sell": fii_sell,
                    "FII_Net":  round(fii_buy - fii_sell, 2),
                    "DII_Buy":  dii_buy,
                    "DII_Sell": dii_sell,
                    "DII_Net":  round(dii_buy - dii_sell, 2),
                })
            except Exception:
                continue

        if rows:
            df = pd.DataFrame(rows)
            df = df.sort_values("Date", ascending=False).head(days).reset_index(drop=True)
            _save_cache(df)
            return df

    except Exception as e:
        print(f"⚠️ NSE FII/DII API fetch failed: {e}")

    # ── Fallback: return synthetic neutral data ────
    # So the rest of the system never crashes
    return _get_neutral_df()


def _parse_cr(value) -> float:
    """Parse a crore value safely."""
    try:
        return round(float(str(value).replace(",", "").replace("₹", "")), 2)
    except Exception:
        return 0.0


def _load_cache() -> pd.DataFrame | None:
    """Load cached FII/DII data if fresh enough."""
    try:
        if not os.path.exists(FII_CACHE_FILE):
            return None
        with open(FII_CACHE_FILE, "r") as f:
            cache = json.load(f)
        cached_at = datetime.strptime(cache["cached_at"], '%Y-%m-%d %H:%M:%S')
        age_hours = (datetime.now() - cached_at).total_seconds() / 3600
        if age_hours > CACHE_TTL_HOURS:
            return None
        return pd.DataFrame(cache["data"])
    except Exception:
        return None


def _save_cache(df: pd.DataFrame):
    """Save FII/DII data to local cache."""
    try:
        cache = {
            "cached_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "data":      df.to_dict(orient="records"),
        }
        with open(FII_CACHE_FILE, "w") as f:
            json.dump(cache, f, default=str)
    except Exception as e:
        print(f"⚠️ FII cache save failed: {e}")


def _get_neutral_df() -> pd.DataFrame:
    """Return a neutral placeholder when data is unavailable."""
    today = datetime.now().strftime('%Y-%m-%d')
    return pd.DataFrame([{
        "Date":     today,
        "FII_Buy":  0.0,
        "FII_Sell": 0.0,
        "FII_Net":  0.0,
        "DII_Buy":  0.0,
        "DII_Sell": 0.0,
        "DII_Net":  0.0,
    }])


# ════════════════════════════════════════════════
# SCORING ENGINE
# Converts raw FII/DII flows to 0-100 score
# ════════════════════════════════════════════════

def calculate_fii_dii_score(df: pd.DataFrame) -> dict:
    """
    Build a 0-100 institutional sentiment score.

    SCORING LOGIC (total = 100 points):

    Latest Day FII Net Flow (40 pts):
      > +2000 Cr  → +40  (very strong buying)
      > +500 Cr   → +25
      > 0         → +10  (mild positive)
      0 to -500   → -5
      < -500 Cr   → -20
      < -2000 Cr  → -40  (heavy selling)

    5-Day FII Trend (30 pts):
      All 5 days positive    → +30
      3-4 days positive      → +20
      2 days positive        → +10
      Mostly negative        → -10
      All negative           → -20

    DII Confirmation (20 pts):
      DII also buying (Net > 500)  → +20 (strong domestic support)
      DII flat                     → +5
      DII selling                  → -10

    FII+DII Combined (10 pts):
      Both positive → +10
      Mixed         → 0
      Both negative → -10

    Base = 50. Final = base + adjustments, clamped 0-100.
    """
    if df.empty:
        return _neutral_score()

    base = 50

    # ── Latest day FII ─────────────────────────────
    latest_fii = float(df["FII_Net"].iloc[0]) if len(df) > 0 else 0
    if latest_fii > 2000:
        base += 40
    elif latest_fii > 500:
        base += 25
    elif latest_fii > 0:
        base += 10
    elif latest_fii > -500:
        base -= 5
    elif latest_fii > -2000:
        base -= 20
    else:
        base -= 40

    # ── 5-day FII trend ────────────────────────────
    recent = df.head(5)
    positive_days = (recent["FII_Net"] > 0).sum()
    if positive_days == 5:
        base += 30
    elif positive_days >= 3:
        base += 20
    elif positive_days == 2:
        base += 10
    elif positive_days == 1:
        base -= 10
    else:
        base -= 20

    # ── DII confirmation ───────────────────────────
    latest_dii = float(df["DII_Net"].iloc[0]) if len(df) > 0 else 0
    if latest_dii > 500:
        base += 20
    elif latest_dii > 0:
        base += 5
    else:
        base -= 10

    # ── Combined FII + DII ─────────────────────────
    if latest_fii > 0 and latest_dii > 0:
        base += 10
    elif latest_fii < 0 and latest_dii < 0:
        base -= 10

    score = max(0, min(100, round(base)))

    # ── Label ──────────────────────────────────────
    if score >= 75:
        label = "STRONG INSTITUTIONAL BUYING 🟢🟢"
    elif score >= 60:
        label = "INSTITUTIONAL BUYING 🟢"
    elif score >= 45:
        label = "NEUTRAL ⚪"
    elif score >= 30:
        label = "INSTITUTIONAL SELLING 🔴"
    else:
        label = "HEAVY INSTITUTIONAL SELLING 🔴🔴"

    # ── 5-day summary stats ─────────────────────────
    fii_5d_total = round(df.head(5)["FII_Net"].sum(), 2) if len(df) >= 5 else round(df["FII_Net"].sum(), 2)
    dii_5d_total = round(df.head(5)["DII_Net"].sum(), 2) if len(df) >= 5 else round(df["DII_Net"].sum(), 2)

    return {
        "score":           score,
        "label":           label,
        "latest_fii_net":  round(latest_fii, 2),
        "latest_dii_net":  round(latest_dii, 2),
        "fii_5d_total":    fii_5d_total,
        "dii_5d_total":    dii_5d_total,
        "positive_fii_days": int(positive_days),
        "data_available":  True,
        "fetched_at":      datetime.now().strftime('%d %b %Y %H:%M'),
    }


def _neutral_score() -> dict:
    return {
        "score":             50,
        "label":             "NEUTRAL ⚪ (data unavailable)",
        "latest_fii_net":    0,
        "latest_dii_net":    0,
        "fii_5d_total":      0,
        "dii_5d_total":      0,
        "positive_fii_days": 0,
        "data_available":    False,
        "fetched_at":        datetime.now().strftime('%d %b %Y %H:%M'),
    }


# ════════════════════════════════════════════════
# MASTER FUNCTION — called by app.py and scoring_engine
# ════════════════════════════════════════════════

def get_fii_dii_analysis(days: int = 10) -> dict:
    """
    Full FII/DII analysis for dashboard display.
    Returns score dict + raw data DataFrame.
    Call this from app.py Market Regime tab.
    """
    df    = fetch_fii_dii_data(days)
    score = calculate_fii_dii_score(df)
    score["raw_data"] = df
    return score


def get_fii_dii_score_only() -> int:
    """
    Lightweight version — returns int 0-100.
    Called by scoring_engine.py as 12th dimension.
    Returns 50 (neutral) on any failure.
    """
    try:
        df    = fetch_fii_dii_data(days=5)
        score = calculate_fii_dii_score(df)
        return score["score"]
    except Exception:
        return 50