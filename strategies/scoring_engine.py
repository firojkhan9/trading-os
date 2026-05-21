# ================================================
# FILE: strategies/scoring_engine.py
# PURPOSE: Combined Intelligence Scoring Engine
#          Produces a single composite score
#          for each stock on a scale of 0-100
#
# WHY THIS MATTERS:
#   Instead of getting 4 separate BUY/SELL signals
#   that may conflict, you get ONE clear score:
#
#   Score 80-100 = Strong Buy opportunity
#   Score 60-79  = Moderate Buy opportunity
#   Score 40-59  = Neutral / Hold
#   Score 20-39  = Weak / Avoid
#   Score 0-19   = Strong Avoid
#
# HOW IT WORKS:
#   We score 6 dimensions independently (0-100 each)
#   then combine with weights:
#
#   1. Trend Score      (25%) — MA + EMA direction
#   2. Momentum Score   (25%) — RSI + MACD
#   3. Volatility Score (15%) — Bollinger Bands position
#   4. Signal Score     (20%) — Combined strategy votes
#   5. Regime Score     (10%) — Is market favorable?
#   6. RS Score         (5%)  — Beating NIFTY?
#
# OUTPUT:
#   Composite Score: 0-100
#   Action: STRONG BUY / BUY / HOLD / AVOID / STRONG AVOID
#   Confidence: HIGH / MEDIUM / LOW
#   Suggested Position Size: 0-10%
#   Explanation: Why this score was given
# ================================================

import pandas as pd


# ── Score Weights ─────────────────────────────────
# Must sum to 1.0
WEIGHTS = {
    "trend":      0.25,   # Trend direction and strength
    "momentum":   0.25,   # RSI and MACD momentum
    "volatility": 0.15,   # Bollinger Bands position
    "signal":     0.20,   # Combined strategy votes
    "regime":     0.10,   # Market regime favorability
    "rs":         0.05,   # Relative strength vs NIFTY
}

# ── Score thresholds ──────────────────────────────
STRONG_BUY_THRESHOLD  = 70
BUY_THRESHOLD         = 55
HOLD_THRESHOLD        = 40
AVOID_THRESHOLD       = 25


def calculate_trend_score(latest_close, ma20, ema9, ema21):
    """
    Score the trend direction and strength.
    Returns 0-100.

    Strong uptrend  = high score
    Strong downtrend = low score
    Sideways = 50
    """
    score = 50  # Start neutral

    # Price vs MA20
    if ma20 and ma20 > 0:
        pct_above_ma20 = ((latest_close - ma20) / ma20) * 100
        if pct_above_ma20 > 3:
            score += 20     # Well above MA20
        elif pct_above_ma20 > 0:
            score += 10     # Just above MA20
        elif pct_above_ma20 > -3:
            score -= 10     # Just below MA20
        else:
            score -= 20     # Well below MA20

    # EMA crossover direction
    if ema9 and ema21:
        ema_gap = ((ema9 - ema21) / ema21) * 100
        if ema_gap > 1:
            score += 15     # Fast EMA well above slow = strong uptrend
        elif ema_gap > 0:
            score += 8      # Fast EMA slightly above slow
        elif ema_gap > -1:
            score -= 8      # Fast EMA slightly below slow
        else:
            score -= 15     # Fast EMA well below slow = strong downtrend

    # Clamp to 0-100
    return max(0, min(100, round(score)))


def calculate_momentum_score(rsi, macd, macd_signal, macd_hist):
    """
    Score the momentum using RSI and MACD.
    Returns 0-100.

    Oversold RSI + bullish MACD = high score
    Overbought RSI + bearish MACD = low score
    """
    score = 50  # Start neutral

    # RSI scoring
    if rsi is not None:
        if 40 <= rsi <= 60:
            score += 0      # Neutral zone
        elif 30 <= rsi < 40:
            score += 15     # Approaching oversold — good entry
        elif rsi < 30:
            score += 20     # Oversold — strong buy signal
        elif 60 < rsi <= 70:
            score -= 10     # Approaching overbought
        elif rsi > 70:
            score -= 20     # Overbought — risky entry

    # MACD scoring
    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            score += 15     # MACD above signal = bullish
        else:
            score -= 15     # MACD below signal = bearish

    # MACD histogram direction
    if macd_hist is not None:
        if macd_hist > 0:
            score += 10     # Positive histogram = building momentum
        else:
            score -= 10     # Negative histogram = losing momentum

    return max(0, min(100, round(score)))


def calculate_volatility_score(bb_pct, bb_signal):
    """
    Score the Bollinger Bands position.
    Returns 0-100.

    Near lower band = good entry = high score
    Near upper band = risky entry = low score
    Middle = neutral
    """
    score = 50  # Start neutral

    if bb_pct is not None:
        if bb_pct <= 0.1:
            score += 35     # At or below lower band — oversold
        elif bb_pct <= 0.2:
            score += 20     # Near lower band
        elif bb_pct <= 0.4:
            score += 10     # Lower half
        elif bb_pct <= 0.6:
            score += 0      # Middle — neutral
        elif bb_pct <= 0.8:
            score -= 10     # Upper half
        elif bb_pct <= 0.9:
            score -= 20     # Near upper band
        else:
            score -= 35     # At or above upper band — overbought

    # RSI confirmation from BB signal
    if "BUY" in str(bb_signal):
        score += 10
    elif "SELL" in str(bb_signal):
        score -= 10
    elif "WATCH" in str(bb_signal):
        score += 5

    return max(0, min(100, round(score)))


def calculate_signal_score(combined_votes, combined_score):
    """
    Score based on the combined strategy voting.
    Returns 0-100.

    All 4 strategies agree on BUY = 100
    3 agree on BUY = 75
    2 agree = 50
    Split = 25
    All agree on SELL = 0
    """
    buy_count  = combined_votes.get("buy",  0)
    sell_count = combined_votes.get("sell", 0)
    total      = 4  # total strategies

    # Base score from vote ratio
    score = ((buy_count - sell_count) / total) * 50 + 50

    # Boost based on weighted combined score
    # combined_score is typically -4 to +4
    normalized = (combined_score / 4) * 20
    score += normalized

    return max(0, min(100, round(score)))


def calculate_regime_score(regime):
    """
    Score based on current market regime.
    Returns 0-100.

    Bull market = high score (favorable for buying)
    Bear market = low score (unfavorable)
    """
    regime_scores = {
        "BULL 🐂":       90,
        "WEAK BULL 📈":  65,
        "SIDEWAYS ↔️":   50,
        "WEAK BEAR 📉":  30,
        "BEAR 🐻":       10,
        "UNKNOWN ❓":    50,   # Neutral if unknown
    }

    # Match regime string
    for key, value in regime_scores.items():
        if key in str(regime):
            return value

    return 50  # Default neutral


def calculate_rs_score_normalized(rs_score):
    """
    Convert relative strength score to 0-100.
    RS > 5%  = strong outperformer = high score
    RS < -5% = strong underperformer = low score
    """
    if rs_score is None:
        return 50  # Neutral if unknown

    # Map RS score (-10 to +10) to 0-100
    # RS of +10 = 100, RS of 0 = 50, RS of -10 = 0
    normalized = (rs_score / 10) * 50 + 50
    return max(0, min(100, round(normalized)))


def get_action_from_score(composite_score):
    """
    Convert composite score to action recommendation.
    """
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
    Never exceed 10% per position (our max setting).

    High score in bull market = full position
    Low score or bear market = no position
    """
    # Bear market = no new trades
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

    # Reduce size in weak/sideways markets
    if "WEAK" in str(regime):
        base_size *= 0.6
    elif "SIDEWAYS" in str(regime):
        base_size *= 0.7

    return round(base_size, 1)


def get_confidence(composite_score, individual_scores):
    """
    Determine confidence level based on how consistent
    the individual dimension scores are.

    If all dimensions agree = HIGH confidence
    If mixed = MEDIUM confidence
    If conflicting = LOW confidence
    """
    scores = list(individual_scores.values())
    avg    = sum(scores) / len(scores)

    # Standard deviation — how spread out are the scores?
    variance = sum((s - avg) ** 2 for s in scores) / len(scores)
    std_dev  = variance ** 0.5

    if std_dev < 12:
        return "HIGH 🟢"     # All dimensions agree
    elif std_dev < 22:
        return "MEDIUM 🟡"   # Some disagreement
    else:
        return "LOW 🔴"      # Highly conflicting signals


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
    rs_score=None
):
    """
    Master function — takes all indicator values
    and returns a complete scoring analysis.

    Called by app.py for each selected stock.
    This is the core of Milestone 20.
    """

    # ── Step 1: Calculate individual dimension scores ─
    trend_score      = calculate_trend_score(latest_close, ma20, ema9, ema21)
    momentum_score   = calculate_momentum_score(rsi, macd, macd_signal, macd_hist)
    volatility_score = calculate_volatility_score(bb_pct, bb_signal)
    signal_score     = calculate_signal_score(combined_votes, combined_weighted_score)
    regime_score     = calculate_regime_score(regime)
    rs_score_norm    = calculate_rs_score_normalized(rs_score)

    individual_scores = {
        "Trend":      trend_score,
        "Momentum":   momentum_score,
        "Volatility": volatility_score,
        "Signal":     signal_score,
        "Regime":     regime_score,
        "Rel. Strength": rs_score_norm,
    }

    # ── Step 2: Calculate weighted composite score ────
    composite = (
        trend_score      * WEIGHTS["trend"]      +
        momentum_score   * WEIGHTS["momentum"]   +
        volatility_score * WEIGHTS["volatility"] +
        signal_score     * WEIGHTS["signal"]     +
        regime_score     * WEIGHTS["regime"]     +
        rs_score_norm    * WEIGHTS["rs"]
    )
    composite = round(composite)

    # ── Step 3: Get action and position size ──────────
    action        = get_action_from_score(composite)
    position_size = get_position_size(composite, regime)
    confidence    = get_confidence(composite, individual_scores)

    # ── Step 4: Build explanation ─────────────────────
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
            "Trend Score":          f"{trend_score}/100     (weight: 25%)",
            "Momentum Score":       f"{momentum_score}/100  (weight: 25%)",
            "Volatility Score":     f"{volatility_score}/100 (weight: 15%)",
            "Signal Score":         f"{signal_score}/100    (weight: 20%)",
            "Regime Score":         f"{regime_score}/100    (weight: 10%)",
            "Rel. Strength Score":  f"{rs_score_norm}/100   (weight: 5%)",
        }
    }


def build_explanation(
    stock_name, score, action, individual_scores,
    regime, position_size, confidence
):
    """
    Build a plain English explanation of the score.
    This is the Explainability component.
    """
    lines = []

    # Opening line
    lines.append(f"**{stock_name}** scored **{score}/100** → {action}")
    lines.append("")

    # Regime context
    lines.append(f"📡 **Market Regime:** {regime}")

    # Strongest dimension
    best_dim   = max(individual_scores, key=individual_scores.get)
    worst_dim  = min(individual_scores, key=individual_scores.get)
    best_score = individual_scores[best_dim]
    worst_score= individual_scores[worst_dim]

    lines.append(f"✅ **Strongest factor:** {best_dim} ({best_score}/100)")
    lines.append(f"⚠️ **Weakest factor:** {worst_dim} ({worst_score}/100)")
    lines.append("")

    # Position guidance
    if position_size > 0:
        lines.append(f"💰 **Suggested position:** {position_size}% of capital")
    else:
        lines.append("🚫 **Suggested position:** Do not enter — conditions unfavorable")

    lines.append(f"🎯 **Confidence:** {confidence}")

    # Warning flags
    if score < HOLD_THRESHOLD:
        lines.append("")
        lines.append("⚠️ **Warning:** Score below threshold — avoid new entries")

    if "BEAR" in str(regime) and "WEAK" not in str(regime):
        lines.append("🐻 **Bear Market Warning:** Capital protection mode — no new longs")

    return "\n".join(lines)
