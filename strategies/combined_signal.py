# ================================================
# FILE: strategies/combined_signal.py
# PURPOSE: Combine signals from all 4 strategies
#          into one unified BUY/SELL decision
#
# METHODOLOGY:
#   Each strategy gets a VOTE:
#     BUY  =  +1 vote
#     SELL =  -1 vote
#     HOLD =   0 votes
#
#   Votes are WEIGHTED by strategy composite score
#   from backtesting (better performing = more weight)
#
#   Final score > threshold  → STRONG BUY
#   Final score > 0          → WEAK BUY
#   Final score < threshold  → STRONG SELL
#   Final score < 0          → WEAK SELL
#   Final score = 0          → NEUTRAL
# ================================================

import pandas as pd


# ── Default weights ───────────────────────────────
# Used when no backtest scores are available
# All strategies start equal
DEFAULT_WEIGHTS = {
    "MA + RSI":       1.0,
    "EMA Crossover":  1.0,
    "Bollinger Bands":1.0,
    "MACD":           1.0,
}


def get_individual_votes(
    ma_signal,
    ema_signal,
    bb_signal,
    macd_signal
):
    """
    Convert each strategy signal to a numeric vote.

    BUY signals  → +1
    SELL signals → -1
    Everything else → 0
    """

    def signal_to_vote(signal):
        s = str(signal).upper()
        if "BUY"  in s: return  1
        if "SELL" in s: return -1
        return 0

    votes = {
        "MA + RSI":        signal_to_vote(ma_signal),
        "EMA Crossover":   signal_to_vote(ema_signal),
        "Bollinger Bands": signal_to_vote(bb_signal),
        "MACD":            signal_to_vote(macd_signal),
    }

    return votes


def calculate_combined_score(votes, weights=None):
    """
    Multiply each vote by its weight and sum up.
    Returns a score between -4 and +4 (with equal weights).

    Positive score = overall bullish consensus
    Negative score = overall bearish consensus
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    score = 0
    for strategy, vote in votes.items():
        w      = weights.get(strategy, 1.0)
        score += vote * w

    return round(score, 3)


def get_combined_signal(score, weights=None):
    """
    Convert numeric score to a human-readable signal.

    Thresholds:
    >= +1.5  → STRONG BUY  🟢🟢
    >= +0.5  → BUY         🟢
    <= -1.5  → STRONG SELL 🔴🔴
    <= -0.5  → SELL        🔴
    else     → NEUTRAL     ⚪
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Max possible score = sum of all weights
    max_score = sum(weights.values())

    # Thresholds as % of max score
    strong_threshold = max_score * 0.375   # 37.5% of strategies agree strongly
    weak_threshold   = max_score * 0.125   # At least one strategy agrees

    if score >= strong_threshold:
        return "STRONG BUY 🟢🟢"
    elif score >= weak_threshold:
        return "BUY 🟢"
    elif score <= -strong_threshold:
        return "STRONG SELL 🔴🔴"
    elif score <= -weak_threshold:
        return "SELL 🔴"
    else:
        return "NEUTRAL ⚪"


def get_signal_confidence(votes):
    """
    Calculate how much the strategies agree with each other.

    All 4 agree = 100% confidence
    3 agree     = 75%
    2 agree     = 50%
    1 or split  = 25%
    """
    buy_count  = sum(1 for v in votes.values() if v ==  1)
    sell_count = sum(1 for v in votes.values() if v == -1)
    hold_count = sum(1 for v in votes.values() if v ==  0)

    majority = max(buy_count, sell_count, hold_count)
    confidence = round((majority / len(votes)) * 100)

    return confidence, buy_count, sell_count, hold_count


def build_combined_summary(
    ma_signal,
    ema_signal,
    bb_signal,
    macd_signal,
    weights=None
):
    """
    Master function — takes all 4 signals and returns
    a complete combined analysis dictionary.

    Called by app.py to display on the dashboard.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Step 1: Get individual votes
    votes = get_individual_votes(
        ma_signal, ema_signal, bb_signal, macd_signal
    )

    # Step 2: Calculate weighted score
    score = calculate_combined_score(votes, weights)

    # Step 3: Get final signal
    final_signal = get_combined_signal(score, weights)

    # Step 4: Calculate confidence
    confidence, buys, sells, holds = get_signal_confidence(votes)

    # Step 5: Build readable vote summary
    vote_labels = {
        "MA + RSI":        ma_signal,
        "EMA Crossover":   ema_signal,
        "Bollinger Bands": bb_signal,
        "MACD":            macd_signal,
    }

    return {
        "Final Signal":   final_signal,
        "Score":          score,
        "Confidence":     f"{confidence}%",
        "Strategies Buy": buys,
        "Strategies Sell":sells,
        "Strategies Hold":holds,
        "Votes":          votes,
        "Signals":        vote_labels,
        "Weights":        weights,
    }
