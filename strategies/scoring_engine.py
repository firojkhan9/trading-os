# ================================================
# FILE: strategies/scoring_engine.py
# PURPOSE: Combined Intelligence Scoring Engine
#          Produces a single composite score
#          for each stock on a scale of 0-100
#
# UPDATED:
#   Milestone 22 — Added Fundamental Score (8%)
#   Milestone 23 — Added Sentiment Score (7%)
#   Milestone 27 — Added Volume Score (10%) as 9th dimension
#                  Weights rebalanced across all 9 dimensions
#   Milestone 28 — Added Candlestick Score (8%) as 10th dimension
#                  Weights rebalanced: Signal -3%, Momentum -3%, Volatility -2%
#   Milestone 29 — Added Market Structure Score (8%) as 11th dimension
#                  Weights rebalanced: Trend -2%, Momentum -2%, Signal -2%,
#                  Volatility -1%, RS -1%
#
# HOW IT WORKS:
#   We score 11 dimensions independently (0-100 each)
#   then combine with weights:
#
#   1. Trend Score             (16%) — MA + EMA direction
#   2. Momentum Score          (12%) — RSI + MACD
#   3. Volatility Score        ( 7%) — Bollinger Bands position
#   4. Signal Score            (10%) — Combined strategy votes
#   5. Regime Score            (10%) — Is market favorable?
#   6. RS Score                ( 4%) — Beating NIFTY?
#   7. Fundamental Score       ( 8%) — Is the business healthy?
#   8. Sentiment Score         ( 7%) — What is news saying?
#   9. Volume Score            (10%) — Does volume confirm the move?
#  10. Candlestick Score       ( 8%) — Pattern + validation confidence
#  11. Market Structure Score  ( 8%) — HH/HL, S/R, breakout, squeeze
#
# OUTPUT:
#   Composite Score: 0-100
#   Action: STRONG BUY / BUY / HOLD / AVOID / STRONG AVOID
#   Confidence: HIGH / MEDIUM / LOW
#   Suggested Position Size: 0-10%
#   Explanation: Why this score was given
# ================================================

import pandas as pd


# ── Load weights from trading_config (Google Sheets controlled) ──
try:
    from config.trading_config import SCORING_WEIGHTS
    WEIGHTS = SCORING_WEIGHTS
except ImportError:
    # Hard fallback if trading_config not yet created
    WEIGHTS = {
    "trend":             0.15,
    "momentum":          0.11,
    "volatility":        0.07,
    "signal":            0.09,
    "regime":            0.10,
    "rs":                0.04,
    "fundamental":       0.08,
    "sentiment":         0.06,
    "volume":            0.09,
    "candlestick":       0.08,
    "market_structure":  0.08,
    "fii_dii":           0.05,   # M36 — Institutional flow (5%)
}
# Weights sum = 1.0 ✓

# ── Score thresholds ──────────────────────────────
STRONG_BUY_THRESHOLD  = 70
BUY_THRESHOLD         = 55
HOLD_THRESHOLD        = 40
AVOID_THRESHOLD       = 25


def calculate_trend_score(latest_close, ma20, ema9, ema21):
    """
    Score the trend direction and strength.
    Returns 0-100.
    Strong uptrend = high score | Strong downtrend = low score
    """
    score = 50  # Start neutral

    if ma20 and ma20 > 0:
        pct_above_ma20 = ((latest_close - ma20) / ma20) * 100
        if pct_above_ma20 > 3:
            score += 20
        elif pct_above_ma20 > 0:
            score += 10
        elif pct_above_ma20 > -3:
            score -= 10
        else:
            score -= 20

    if ema9 and ema21:
        ema_gap = ((ema9 - ema21) / ema21) * 100
        if ema_gap > 1:
            score += 15
        elif ema_gap > 0:
            score += 8
        elif ema_gap > -1:
            score -= 8
        else:
            score -= 15

    return max(0, min(100, round(score)))


def calculate_momentum_score(rsi, macd, macd_signal, macd_hist):
    """
    Score the momentum using RSI and MACD.
    Returns 0-100.
    Oversold RSI + bullish MACD = high score
    """
    score = 50

    if rsi is not None:
        if 40 <= rsi <= 60:
            score += 0
        elif 30 <= rsi < 40:
            score += 15
        elif rsi < 30:
            score += 20
        elif 60 < rsi <= 70:
            score -= 10
        elif rsi > 70:
            score -= 20

    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            score += 15
        else:
            score -= 15

    if macd_hist is not None:
        if macd_hist > 0:
            score += 10
        else:
            score -= 10

    return max(0, min(100, round(score)))


def calculate_volatility_score(bb_pct, bb_signal):
    """
    Score the Bollinger Bands position.
    Returns 0-100.
    Near lower band = good entry | Near upper band = risky
    """
    score = 50

    if bb_pct is not None:
        if bb_pct <= 0.1:
            score += 35
        elif bb_pct <= 0.2:
            score += 20
        elif bb_pct <= 0.4:
            score += 10
        elif bb_pct <= 0.6:
            score += 0
        elif bb_pct <= 0.8:
            score -= 10
        elif bb_pct <= 0.9:
            score -= 20
        else:
            score -= 35

    if "BUY" in str(bb_signal):
        score += 10
    elif "SELL" in str(bb_signal):
        score -= 10
    elif "WATCH" in str(bb_signal):
        score += 5

    return max(0, min(100, round(score)))


def calculate_signal_score(combined_votes, combined_score):
    """
    Score based on combined strategy voting.
    Returns 0-100.
    All 4 agree BUY = 100 | All agree SELL = 0
    """
    buy_count  = combined_votes.get("buy",  0)
    sell_count = combined_votes.get("sell", 0)
    total      = 4

    score      = ((buy_count - sell_count) / total) * 50 + 50
    normalized = (combined_score / 4) * 20
    score     += normalized

    return max(0, min(100, round(score)))


def calculate_regime_score(regime):
    """
    Score based on current market regime.
    Returns 0-100.
    Bull market = high | Bear market = low
    """
    regime_scores = {
        "BULL 🐂":       90,
        "WEAK BULL 📈":  65,
        "SIDEWAYS ↔️":   50,
        "WEAK BEAR 📉":  30,
        "BEAR 🐻":       10,
        "UNKNOWN ❓":    50,
    }

    for key, value in regime_scores.items():
        if key in str(regime):
            return value

    return 50


def calculate_rs_score_normalized(rs_score):
    """
    Convert relative strength to 0-100.
    RS > 5% = outperforming = high score
    """
    if rs_score is None:
        return 50
    normalized = (rs_score / 10) * 50 + 50
    return max(0, min(100, round(normalized)))


def get_action_from_score(composite_score):
    """Convert composite score to action recommendation."""
    if composite_score >= STRONG_BUY_THRESHOLD:
        return "STRONG BUY 🟢🟢"
    elif composite_score >= BUY_THRESHOLD:
        return "BUY 🟢"
    elif composite_score >= HOLD_THRESHOLD:
        return "HOLD / WATCH ⚪"
    elif composite_score >= AVOID_THRESHOLD:
        return "AVOID 🔴"
    else:
        return "STRONG AVOID 🔴🔴"


def get_position_size(composite_score, regime):
    """
    Suggest position size based on score and regime.
    Never exceed 10% per position.
    Bear market = no new trades.
    """
    if "BEAR" in str(regime) and "WEAK" not in str(regime):
        return 0

    if composite_score >= STRONG_BUY_THRESHOLD:
        base_size = 10.0
    elif composite_score >= BUY_THRESHOLD:
        base_size = 7.0
    elif composite_score >= HOLD_THRESHOLD:
        base_size = 3.0
    else:
        base_size = 0.0

    if "WEAK" in str(regime):
        base_size *= 0.6
    elif "SIDEWAYS" in str(regime):
        base_size *= 0.7

    return round(base_size, 1)


def get_confidence(composite_score, individual_scores):
    """
    Determine confidence level from consistency of dimensions.
    All agree = HIGH | Mixed = MEDIUM | Conflicting = LOW
    """
    scores   = list(individual_scores.values())
    avg      = sum(scores) / len(scores)
    variance = sum((s - avg) ** 2 for s in scores) / len(scores)
    std_dev  = variance ** 0.5

    if std_dev < 12:
        return "HIGH 🟢"
    elif std_dev < 22:
        return "MEDIUM 🟡"
    else:
        return "LOW 🔴"


def build_composite_score(
    stock_name,
    latest_close,
    ma20,
    rsi,
    ema9,
    ema21,
    macd,
    macd_signal,
    macd_hist,
    bb_pct,
    bb_signal,
    combined_votes,
    combined_weighted_score,
    regime,
    rs_score=None,
    fundamental_score=None,   # M22 — pass None for neutral 50
    sentiment_score=None,     # M23 — pass None for neutral 50
    volume_score=None,        # M27 — pass None for neutral 50
    candlestick_score=None,   # M28 — pass None for neutral 50
    market_structure_score=None,  # M29 — pass None for neutral 50
    fii_dii_score=None,           # M36 — pass None for neutral 50
):
    """
    Master scoring function.
    Takes all indicator values + fundamental + sentiment + volume + candlestick.
    Returns complete scoring analysis dict.

    All new parameters are optional (default neutral 50).
    Fully backward compatible with existing callers.
    """

    # ── Step 1: Calculate all dimension scores ────
    trend_score      = calculate_trend_score(latest_close, ma20, ema9, ema21)
    momentum_score   = calculate_momentum_score(rsi, macd, macd_signal, macd_hist)
    volatility_score = calculate_volatility_score(bb_pct, bb_signal)
    signal_score     = calculate_signal_score(combined_votes, combined_weighted_score)
    regime_score     = calculate_regime_score(regime)
    rs_score_norm    = calculate_rs_score_normalized(rs_score)

     # Optional dimensions — neutral 50 if not provided
    fund_score   = fundamental_score     if fundamental_score     is not None else 50
    sent_score   = sentiment_score       if sentiment_score       is not None else 50
    vol_score    = volume_score          if volume_score          is not None else 50
    candle_score = candlestick_score     if candlestick_score     is not None else 50
    ms_score     = market_structure_score if market_structure_score is not None else 50
    fii_score    = fii_dii_score         if fii_dii_score         is not None else 50

    individual_scores = {
        "Trend":            trend_score,
        "Momentum":         momentum_score,
        "Volatility":       volatility_score,
        "Signal":           signal_score,
        "Regime":           regime_score,
        "Rel. Strength":    rs_score_norm,
        "Fundamental":      fund_score,
        "Sentiment":        sent_score,
        "Volume":           vol_score,
        "Candlestick":      candle_score,
        "Mkt Structure":    ms_score,
        "FII/DII":          fii_score,
    }

    # ── Step 2: Weighted composite score ──────────
    composite = (
        trend_score      * WEIGHTS["trend"]            +
        momentum_score   * WEIGHTS["momentum"]         +
        volatility_score * WEIGHTS["volatility"]       +
        signal_score     * WEIGHTS["signal"]           +
        regime_score     * WEIGHTS["regime"]           +
        rs_score_norm    * WEIGHTS["rs"]               +
        fund_score       * WEIGHTS["fundamental"]      +
        sent_score       * WEIGHTS["sentiment"]        +
        vol_score        * WEIGHTS["volume"]           +
        candle_score     * WEIGHTS["candlestick"]      +
        ms_score         * WEIGHTS["market_structure"] +
        fii_score        * WEIGHTS["fii_dii"]
    )
    composite = round(composite)

    # ── Step 3: Action, position size, confidence ─
    action        = get_action_from_score(composite)
    position_size = get_position_size(composite, regime)
    confidence    = get_confidence(composite, individual_scores)

    # ── Step 4: Plain English explanation ─────────
    explanation = build_explanation(
        stock_name, composite, action, individual_scores,
        regime, position_size, confidence
    )

    return {
        "Stock":              stock_name,
        "Composite Score":    composite,
        "Action":             action,
        "Position Size":      f"{position_size}%",
        "Confidence":         confidence,
        "Regime":             regime,
        "Individual Scores":  individual_scores,
        "Explanation":        explanation,
        "Score Breakdown": {
            "Trend Score":            f"{trend_score}/100      (weight: 15%)",
            "Momentum Score":         f"{momentum_score}/100   (weight: 11%)",
            "Volatility Score":       f"{volatility_score}/100 (weight: 7%)",
            "Signal Score":           f"{signal_score}/100     (weight: 9%)",
            "Regime Score":           f"{regime_score}/100     (weight: 10%)",
            "Rel. Strength Score":    f"{rs_score_norm}/100    (weight: 4%)",
            "Fundamental Score":      f"{fund_score}/100       (weight: 8%)",
            "Sentiment Score":        f"{sent_score}/100       (weight: 6%)",
            "Volume Score":           f"{vol_score}/100        (weight: 9%)",
            "Candlestick Score":      f"{candle_score}/100     (weight: 8%)",
            "Mkt Structure Score":    f"{ms_score}/100         (weight: 8%)",
            "FII/DII Score":          f"{fii_score}/100        (weight: 5%)",
        }
    }


def build_explanation(
    stock_name, score, action, individual_scores,
    regime, position_size, confidence
):
    """Build a plain English explanation of the composite score."""
    lines = []

    lines.append(f"**{stock_name}** scored **{score}/100** → {action}")
    lines.append("")
    lines.append(f"📡 **Market Regime:** {regime}")

    best_dim    = max(individual_scores, key=individual_scores.get)
    worst_dim   = min(individual_scores, key=individual_scores.get)
    best_score  = individual_scores[best_dim]
    worst_score = individual_scores[worst_dim]

    lines.append(f"✅ **Strongest factor:** {best_dim} ({best_score}/100)")
    lines.append(f"⚠️ **Weakest factor:** {worst_dim} ({worst_score}/100)")
    lines.append("")

    if position_size > 0:
        lines.append(f"💰 **Suggested position:** {position_size}% of capital")
    else:
        lines.append("🚫 **Suggested position:** Do not enter — conditions unfavorable")

    lines.append(f"🎯 **Confidence:** {confidence}")

    if score < HOLD_THRESHOLD:
        lines.append("")
        lines.append("⚠️ **Warning:** Score below threshold — avoid new entries")

    if "BEAR" in str(regime) and "WEAK" not in str(regime):
        lines.append("🐻 **Bear Market Warning:** Capital protection mode — no new longs")

    return "\n".join(lines)
