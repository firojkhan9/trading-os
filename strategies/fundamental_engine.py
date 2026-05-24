# ================================================
# FILE: strategies/fundamental_engine.py
# PURPOSE: Fundamental Intelligence Layer
#          Fetches key financial health metrics
#          for any NSE stock via yfinance (free)
#          and scores the company 0-100
#
# MILESTONE 22 — Fundamental Intelligence Layer
#
# WHY FUNDAMENTALS MATTER:
#   Technical analysis tells you WHEN to buy.
#   Fundamental analysis tells you WHAT is worth buying.
#   A stock with strong technicals AND strong fundamentals
#   = much higher conviction trade.
#
# METRICS WE SCORE:
#   1. Valuation   — Is the stock cheap or expensive?
#                    (P/E Ratio, P/B Ratio)
#   2. Profitability — Is the business profitable?
#                    (ROE, Profit Margin)
#   3. Growth      — Is revenue/earnings growing?
#                    (Revenue Growth, Earnings Growth)
#   4. Financial Health — Is the balance sheet strong?
#                    (Debt/Equity, Current Ratio)
#   5. Size / Quality — Large cap = more stable
#                    (Market Cap)
#
# SCORING:
#   Each metric scored 0-100 based on benchmarks
#   for Indian large-cap stocks.
#   Final score = weighted average of all metrics.
#
# DATA SOURCE:
#   yfinance — free, no API key needed.
#   Data refreshes from Yahoo Finance.
#   May have slight delays vs real-time.
# ================================================

import yfinance as yf
import pandas as pd
from datetime import datetime


# ── Indian Large-Cap Benchmarks ───────────────────
# These are reference values for scoring.
# A stock scoring well on these = financially healthy.
# Source: typical NSE Nifty 50 ranges.

BENCHMARKS = {
    # Valuation — lower P/E is generally cheaper
    # Indian large caps typically 15-25x P/E
    "pe_ratio": {
        "excellent": 15,   # Cheap — score 90+
        "good":      25,   # Fair — score 70
        "neutral":   35,   # Slightly expensive — score 50
        "poor":      50,   # Expensive — score 30
        # Above 50 = very expensive — score 10
    },

    # P/B Ratio — price vs book value
    # Below 1 = trading below assets (rare for good cos)
    # 1-3 = reasonable, >5 = expensive
    "pb_ratio": {
        "excellent": 1.5,
        "good":      3.0,
        "neutral":   5.0,
        "poor":      8.0,
    },

    # Return on Equity — how well it uses your money
    # 15%+ is good for Indian companies
    "roe": {
        "excellent": 20,   # 20%+ ROE = excellent
        "good":      15,
        "neutral":   10,
        "poor":       5,
    },

    # Profit Margin — how much profit per ₹ revenue
    # Varies by sector but generally 10%+ is good
    "profit_margin": {
        "excellent": 20,
        "good":      12,
        "neutral":    6,
        "poor":       2,
    },

    # Debt to Equity — lower is safer
    # 0 = no debt (ideal), <1 = manageable, >2 = risky
    "debt_equity": {
        "excellent": 0.3,  # Very low debt
        "good":      0.8,
        "neutral":   1.5,
        "poor":      2.5,
        # Above 2.5 = high debt risk
    },

    # Current Ratio — can it pay short-term bills?
    # >2 = very comfortable, 1-2 = fine, <1 = worry
    "current_ratio": {
        "excellent": 2.0,
        "good":      1.5,
        "neutral":   1.0,
        "poor":      0.7,
    },

    # Revenue Growth % (year over year)
    "revenue_growth": {
        "excellent": 20,   # 20%+ growth = great
        "good":      12,
        "neutral":    5,
        "poor":       0,
        # Negative = declining revenue
    },

    # Earnings Growth % (year over year)
    "earnings_growth": {
        "excellent": 25,
        "good":      15,
        "neutral":    5,
        "poor":       0,
    },
}


def fetch_fundamentals(symbol):
    """
    Fetch fundamental data for a stock from yfinance.

    Returns a dictionary with all key metrics.
    Uses safe fallbacks — never crashes if data missing.

    symbol: Yahoo Finance symbol e.g. "RELIANCE.NS"
    """
    result = {
        # Identity
        "symbol":          symbol,
        "company_name":    "Unknown",
        "sector":          "Unknown",
        "industry":        "Unknown",

        # Valuation
        "pe_ratio":        None,
        "pb_ratio":        None,
        "market_cap":      None,
        "market_cap_cr":   None,   # In crores (₹)
        "enterprise_value":None,

        # Profitability
        "roe":             None,   # Return on Equity %
        "profit_margin":   None,   # Net Profit Margin %
        "operating_margin":None,
        "roa":             None,   # Return on Assets %

        # Growth
        "revenue_growth":  None,   # YoY %
        "earnings_growth": None,   # YoY %

        # Financial Health
        "debt_equity":     None,
        "current_ratio":   None,
        "quick_ratio":     None,

        # Dividends
        "dividend_yield":  None,

        # Data freshness
        "fetched_at":      datetime.now().strftime('%Y-%m-%d %H:%M'),
        "data_available":  False,
        "error":           None,
    }

    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.info

        if not info or len(info) < 5:
            result["error"] = "No data returned from yfinance"
            return result

        # ── Helper: safe get with None default ────────
        def safe_get(key, multiplier=1):
            val = info.get(key)
            if val is None or val == 0:
                return None
            try:
                return round(float(val) * multiplier, 2)
            except (TypeError, ValueError):
                return None

        # ── Identity ──────────────────────────────────
        result["company_name"] = info.get("longName", info.get("shortName", symbol))
        result["sector"]       = info.get("sector",   "Unknown")
        result["industry"]     = info.get("industry", "Unknown")

        # ── Valuation ─────────────────────────────────
        result["pe_ratio"]  = safe_get("trailingPE")
        result["pb_ratio"]  = safe_get("priceToBook")

        # Market cap — convert to crores (÷ 10,000,000)
        market_cap = info.get("marketCap")
        if market_cap:
            result["market_cap"]    = market_cap
            result["market_cap_cr"] = round(market_cap / 1e7, 0)  # In crores

        result["enterprise_value"] = safe_get("enterpriseValue")

        # ── Profitability ─────────────────────────────
        result["roe"]              = safe_get("returnOnEquity",  100)  # Convert to %
        result["profit_margin"]    = safe_get("profitMargins",   100)
        result["operating_margin"] = safe_get("operatingMargins",100)
        result["roa"]              = safe_get("returnOnAssets",  100)

        # ── Growth ────────────────────────────────────
        result["revenue_growth"]   = safe_get("revenueGrowth",  100)
        result["earnings_growth"]  = safe_get("earningsGrowth", 100)

        # ── Financial Health ──────────────────────────
        result["debt_equity"]      = safe_get("debtToEquity")
        # yfinance returns D/E as percentage (e.g. 45.6 means 0.456)
        # Normalize it
        if result["debt_equity"] is not None:
            result["debt_equity"] = round(result["debt_equity"] / 100, 2)

        result["current_ratio"]    = safe_get("currentRatio")
        result["quick_ratio"]      = safe_get("quickRatio")

        # ── Dividends ─────────────────────────────────
        result["dividend_yield"]   = safe_get("dividendYield", 100)

        result["data_available"]   = True

    except Exception as e:
        result["error"] = str(e)

    return result


def score_metric(value, benchmark, lower_is_better=False):
    """
    Score a single metric against benchmarks.
    Returns 0-100.

    lower_is_better: True for P/E, P/B, Debt/Equity
    (lower values = better score)
    """
    if value is None:
        return 50  # Neutral if data missing

    # For metrics where lower = better (valuation, debt)
    # Flip the logic: if value < excellent threshold → high score
    if lower_is_better:
        if value <= benchmark["excellent"]:
            return 95
        elif value <= benchmark["good"]:
            return 75
        elif value <= benchmark["neutral"]:
            return 55
        elif value <= benchmark["poor"]:
            return 30
        else:
            return 10

    # For metrics where higher = better (ROE, growth, margins)
    else:
        if value >= benchmark["excellent"]:
            return 95
        elif value >= benchmark["good"]:
            return 75
        elif value >= benchmark["neutral"]:
            return 55
        elif value >= benchmark["poor"]:
            return 30
        else:
            return 10


def calculate_valuation_score(pe, pb):
    """
    Score valuation — lower P/E and P/B = cheaper = better.
    Returns 0-100.
    Handles cases where P/E is negative (loss-making company).
    """
    # Negative P/E means company is losing money = very poor
    if pe is not None and pe < 0:
        pe_score = 5
    elif pe is None:
        pe_score = 50
    else:
        pe_score = score_metric(pe, BENCHMARKS["pe_ratio"], lower_is_better=True)

    pb_score = score_metric(pb, BENCHMARKS["pb_ratio"], lower_is_better=True)

    # Average of P/E and P/B scores
    # If one is missing, use the other
    scores = [s for s in [pe_score, pb_score] if s != 50 or (pe is None and pb is None)]
    if not scores:
        return 50
    return round(sum(scores) / len(scores))


def calculate_profitability_score(roe, profit_margin):
    """
    Score profitability — higher = better.
    Returns 0-100.
    """
    roe_score    = score_metric(roe,           BENCHMARKS["roe"])
    margin_score = score_metric(profit_margin, BENCHMARKS["profit_margin"])

    scores = []
    if roe is not None:           scores.append(roe_score)
    if profit_margin is not None: scores.append(margin_score)

    if not scores:
        return 50
    return round(sum(scores) / len(scores))


def calculate_growth_score(revenue_growth, earnings_growth):
    """
    Score growth — higher = better.
    Returns 0-100.
    """
    rev_score  = score_metric(revenue_growth,  BENCHMARKS["revenue_growth"])
    earn_score = score_metric(earnings_growth, BENCHMARKS["earnings_growth"])

    scores = []
    if revenue_growth  is not None: scores.append(rev_score)
    if earnings_growth is not None: scores.append(earn_score)

    if not scores:
        return 50
    return round(sum(scores) / len(scores))


def calculate_health_score(debt_equity, current_ratio):
    """
    Score financial health.
    Debt/Equity: lower = better.
    Current Ratio: higher = better.
    Returns 0-100.
    """
    debt_score    = score_metric(debt_equity,   BENCHMARKS["debt_equity"],   lower_is_better=True)
    current_score = score_metric(current_ratio, BENCHMARKS["current_ratio"])

    scores = []
    if debt_equity   is not None: scores.append(debt_score)
    if current_ratio is not None: scores.append(current_score)

    if not scores:
        return 50
    return round(sum(scores) / len(scores))


def calculate_size_score(market_cap_cr):
    """
    Score company size. Larger = more stable = slight bonus.
    This is not about being big — it's about survivability.

    market_cap_cr: Market cap in Indian Crores (₹)
    """
    if market_cap_cr is None:
        return 50

    if market_cap_cr >= 100000:    # ₹1 Lakh Crore+ = Mega cap
        return 90
    elif market_cap_cr >= 20000:   # ₹20,000 Cr+ = Large cap
        return 75
    elif market_cap_cr >= 5000:    # ₹5,000 Cr+ = Mid cap
        return 60
    elif market_cap_cr >= 500:     # ₹500 Cr+ = Small cap
        return 45
    else:
        return 30                  # Micro cap = higher risk


def build_fundamental_score(fundamentals):
    """
    Build the composite fundamental score.
    Takes the fundamentals dict from fetch_fundamentals().
    Returns a complete scoring result.

    Weights:
    - Valuation    25% — Don't overpay
    - Profitability25% — Business is making money
    - Growth       20% — Business is growing
    - Health       20% — Balance sheet is strong
    - Size         10% — Company is stable
    """

    if not fundamentals["data_available"]:
        return {
            "Fundamental Score": 50,
            "Grade":             "N/A",
            "Data Available":    False,
            "Valuation Score":   50,
            "Profitability Score":50,
            "Growth Score":      50,
            "Health Score":      50,
            "Size Score":        50,
            "Summary":           "Fundamental data not available for this stock.",
            "Individual Scores": {},
            "Signals":           [],
            "Warnings":          [],
        }

    # ── Calculate dimension scores ─────────────────
    val_score   = calculate_valuation_score(
        fundamentals["pe_ratio"],
        fundamentals["pb_ratio"]
    )
    prof_score  = calculate_profitability_score(
        fundamentals["roe"],
        fundamentals["profit_margin"]
    )
    growth_score = calculate_growth_score(
        fundamentals["revenue_growth"],
        fundamentals["earnings_growth"]
    )
    health_score = calculate_health_score(
        fundamentals["debt_equity"],
        fundamentals["current_ratio"]
    )
    size_score   = calculate_size_score(fundamentals["market_cap_cr"])

    individual_scores = {
        "Valuation":     val_score,
        "Profitability": prof_score,
        "Growth":        growth_score,
        "Health":        health_score,
        "Size":          size_score,
    }

    # ── Composite score ────────────────────────────
    composite = round(
        val_score    * 0.25 +
        prof_score   * 0.25 +
        growth_score * 0.20 +
        health_score * 0.20 +
        size_score   * 0.10
    )

    # ── Letter grade ───────────────────────────────
    if composite >= 80:   grade = "A+ 🌟"
    elif composite >= 70: grade = "A  ✅"
    elif composite >= 60: grade = "B+ 🟢"
    elif composite >= 50: grade = "B  🟡"
    elif composite >= 40: grade = "C  🟠"
    elif composite >= 30: grade = "D  🔴"
    else:                 grade = "F  ❌"

    # ── Build insight signals ──────────────────────
    signals  = []  # Positive observations
    warnings = []  # Risk flags

    # Valuation signals
    pe = fundamentals["pe_ratio"]
    if pe is not None:
        if pe < 0:
            warnings.append("🔴 Negative P/E — company currently loss-making")
        elif pe < 15:
            signals.append(f"✅ P/E of {pe}x is attractively cheap vs market average")
        elif pe > 40:
            warnings.append(f"⚠️ P/E of {pe}x is expensive — priced for perfection")
        else:
            signals.append(f"🟡 P/E of {pe}x — fairly valued")

    # Profitability signals
    roe = fundamentals["roe"]
    if roe is not None:
        if roe >= 20:
            signals.append(f"✅ ROE of {roe}% — excellent use of shareholder capital")
        elif roe < 8:
            warnings.append(f"⚠️ ROE of {roe}% is low — management efficiency concern")

    margin = fundamentals["profit_margin"]
    if margin is not None:
        if margin >= 15:
            signals.append(f"✅ Profit margin {margin}% — highly profitable business")
        elif margin < 5:
            warnings.append(f"⚠️ Thin profit margin of {margin}% — vulnerable to cost shocks")

    # Growth signals
    rev_growth = fundamentals["revenue_growth"]
    if rev_growth is not None:
        if rev_growth >= 15:
            signals.append(f"✅ Revenue growing at {rev_growth}% YoY — strong business momentum")
        elif rev_growth < 0:
            warnings.append(f"🔴 Revenue declining {rev_growth}% YoY — business shrinking")

    earn_growth = fundamentals["earnings_growth"]
    if earn_growth is not None:
        if earn_growth >= 20:
            signals.append(f"✅ Earnings growing {earn_growth}% YoY — profits accelerating")
        elif earn_growth < 0:
            warnings.append(f"🔴 Earnings declining {earn_growth}% YoY — profitability under pressure")

    # Health signals
    de = fundamentals["debt_equity"]
    if de is not None:
        if de < 0.3:
            signals.append(f"✅ Very low debt/equity of {de} — strong balance sheet")
        elif de > 2:
            warnings.append(f"🔴 High debt/equity of {de} — significant leverage risk")

    cr = fundamentals["current_ratio"]
    if cr is not None:
        if cr < 1:
            warnings.append(f"🔴 Current ratio {cr} below 1 — short-term liquidity concern")
        elif cr >= 2:
            signals.append(f"✅ Current ratio {cr} — very comfortable liquidity position")

    # ── Summary sentence ──────────────────────────
    name = fundamentals.get("company_name", "This company")
    if composite >= 70:
        summary = (
            f"{name} is fundamentally strong. "
            f"The business shows healthy profitability and financial discipline. "
            f"Technical signals supported by fundamentals carry higher conviction."
        )
    elif composite >= 50:
        summary = (
            f"{name} shows average fundamentals. "
            f"Some strengths but also areas of concern. "
            f"Use fundamentals as a secondary filter — don't rely on them alone."
        )
    else:
        summary = (
            f"{name} has weak fundamentals. "
            f"Even if technicals look good, the underlying business has challenges. "
            f"Consider smaller position size or waiting for improvement."
        )

    return {
        "Fundamental Score":    composite,
        "Grade":                grade,
        "Data Available":       True,
        "Valuation Score":      val_score,
        "Profitability Score":  prof_score,
        "Growth Score":         growth_score,
        "Health Score":         health_score,
        "Size Score":           size_score,
        "Individual Scores":    individual_scores,
        "Signals":              signals,
        "Warnings":             warnings,
        "Summary":              summary,
    }


def get_fundamental_display(symbol, stock_name):
    """
    Master function — fetches fundamentals and scores them.
    Returns everything needed for the dashboard display.

    Call this from app.py.
    """
    fundamentals   = fetch_fundamentals(symbol)
    score_result   = build_fundamental_score(fundamentals)

    return {
        "fundamentals":  fundamentals,
        "score_result":  score_result,
        "stock_name":    stock_name,
        "symbol":        symbol,
    }


def get_fundamental_score_only(symbol):
    """
    Lightweight version — just returns the score integer (0-100).
    Used by scoring_engine.py to add fundamental dimension.
    """
    try:
        fundamentals = fetch_fundamentals(symbol)
        score_result = build_fundamental_score(fundamentals)
        return score_result["Fundamental Score"]
    except Exception:
        return 50  # Neutral fallback — never crash the main engine


def format_market_cap(market_cap_cr):
    """Format market cap in human-readable crores/lakh crore format."""
    if market_cap_cr is None:
        return "N/A"
    if market_cap_cr >= 100000:
        return f"₹{round(market_cap_cr / 100000, 2)} Lakh Cr"
    elif market_cap_cr >= 1000:
        return f"₹{round(market_cap_cr / 1000, 1)}K Cr"
    else:
        return f"₹{int(market_cap_cr)} Cr"
