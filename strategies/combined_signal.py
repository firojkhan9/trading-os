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
    macd_signal,
    ema_trend=None,
    macd_momentum=None,
):
    """
    Convert each strategy signal to a numeric VOTE STRENGTH.

    Fresh BUY crossover      → +1.0
    Confirmed bullish trend  → +0.5   (no fresh crossover today, but
                                        the underlying trend/momentum
                                        is clearly bullish)
    Neutral / no opinion     →  0.0
    Confirmed bearish trend  → -0.5
    Fresh SELL crossover     → -1.0

    EMA and MACD only fire a full ±1.0 on the exact day their lines
    cross — every other day they sit at HOLD even during a strong,
    obvious trend. ema_trend / macd_momentum (optional) let the
    caller supply the underlying trend/momentum state so those two
    strategies can still contribute a SOFT ±0.5 vote on non-crossover
    days instead of contributing nothing. This is real evidence
    (computed from EMA9 vs EMA21 / MACD vs Signal), not noise — a
    sideways or undecided trend still yields exactly 0.

    Passing None (the default) for either argument preserves the
    exact previous behaviour — pure crossover-only voting — for any
    caller that doesn't supply trend context.

    IMPORTANT: these are VOTE STRENGTHS, not vote counts. Downstream
    code must never collapse a fractional value back into a full
    vote (e.g. never do `if v > 0: count += 1`). Sum the strengths
    directly instead — see get_signal_confidence() below.
    """

    def signal_to_vote(signal):
        s = str(signal).upper()
        if "BUY"  in s: return  1.0
        if "SELL" in s: return -1.0
        return 0.0

    votes = {
        "MA + RSI":        signal_to_vote(ma_signal),
        "EMA Crossover":   signal_to_vote(ema_signal),
        "Bollinger Bands": signal_to_vote(bb_signal),
        "MACD":            signal_to_vote(macd_signal),
    }

    if votes["EMA Crossover"] == 0 and ema_trend:
        trend_upper = str(ema_trend).upper()
        if "UPTREND" in trend_upper:
            votes["EMA Crossover"] = 0.5
        elif "DOWNTREND" in trend_upper:
            votes["EMA Crossover"] = -0.5

    if votes["MACD"] == 0 and macd_momentum:
        momentum_upper = str(macd_momentum).upper()
        if "BULLISH" in momentum_upper:
            votes["MACD"] = 0.5
        elif "BEARISH" in momentum_upper:
            votes["MACD"] = -0.5

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
    Calculate how much the strategies agree with each other, using
    VOTE STRENGTH (weighted evidence) — NOT a vote count.

    buy_strength  = sum of every positive vote value. A fresh +1.0
                     crossover counts fully; a soft +0.5 trend
                     confirmation counts as HALF a vote. It is never
                     rounded or collapsed back into a whole vote —
                     doing that (e.g. `if v > 0: count += 1`) would
                     turn weighted evidence back into a plain count
                     and defeat the entire purpose of soft voting.
    sell_strength = sum of the absolute value of every negative vote.
    hold_count    = number of strategies sitting at EXACTLY 0 (a
                     genuine count is correct here — a strategy is
                     either offering some directional evidence or it
                     isn't; there's no such thing as "half neutral").

    Returns the same 4-tuple shape as before so every existing
    caller keeps working — buy/sell are now floats instead of ints.
    """
    buy_strength  = sum(max(v, 0) for v in votes.values())
    sell_strength = sum(abs(min(v, 0)) for v in votes.values())
    hold_count    = sum(1 for v in votes.values() if v == 0)

    total      = len(votes)
    majority   = max(buy_strength, sell_strength, hold_count)
    confidence = round((majority / total) * 100)

    return confidence, buy_strength, sell_strength, hold_count


def build_combined_summary(
    ma_signal,
    ema_signal,
    bb_signal,
    macd_signal,
    weights=None,
    ema_trend=None,
    macd_momentum=None,
):
    """
    Master function — takes all 4 signals and returns
    a complete combined analysis dictionary.

    Called by app.py to display on the dashboard, and by the
    execution loop to drive BUY decisions.

    ema_trend / macd_momentum: optional soft-vote context — see
    get_individual_votes() for details. Any caller that omits them
    gets the exact previous crossover-only behaviour.

    "Strategies Buy" / "Strategies Sell" in the returned dict are
    VOTE STRENGTHS (floats, weighted evidence, 0-4) — NOT vote
    counts. Every consumer of this dict downstream (scoring_engine,
    orchestrator, decision_engine) must treat them as continuous
    strength and must never round/collapse them back into an
    integer count.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Step 1: Get individual vote strengths
    votes = get_individual_votes(
        ma_signal, ema_signal, bb_signal, macd_signal,
        ema_trend=ema_trend, macd_momentum=macd_momentum,
    )

    # Step 2: Calculate weighted score
    score = calculate_combined_score(votes, weights)

    # Step 3: Get final signal
    final_signal = get_combined_signal(score, weights)

    # Step 4: Calculate confidence + vote strengths (not counts)
    confidence, buy_strength, sell_strength, hold_count = get_signal_confidence(votes)

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
        "Strategies Buy": buy_strength,
        "Strategies Sell":sell_strength,
        "Strategies Hold":hold_count,
        "Votes":          votes,
        "Signals":        vote_labels,
        "Weights":        weights,
    }
