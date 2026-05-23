# ================================================
# FILE: strategies/explainability_engine.py
# PURPOSE: Explain every signal in plain English
#          Show WHY a signal was generated
#          Show HOW RARE the current signal is
#          Show WHAT RISK factors exist
#
# MILESTONE 21 — Explainability Engine
#
# OUTPUTS:
#   - Full plain English explanation of signal
#   - Signal rarity (how often this occurred in 6mo)
#   - Last time this signal occurred
#   - Risk factors and cautions
#   - Entry guidance with price levels
#   - Comparison of live signal vs backtest behavior
# ================================================

import pandas as pd
from datetime import datetime

from strategies.indicators import calculate_ma20, calculate_rsi, analyze_stock
from strategies.ema_strategy import calculate_ema_signals
from strategies.bollinger_strategy import analyze_bollinger
from strategies.macd_strategy import analyze_macd
from strategies.combined_signal import (
    get_individual_votes,
    calculate_combined_score,
    get_combined_signal,
    DEFAULT_WEIGHTS
)


def build_full_signal_history(data):
    """
    Run all 4 strategies on historical data
    and generate combined signal for every single day.
    This is used to measure signal rarity.
    """
    df = data.copy()

    # Run all strategies
    df = calculate_ma20(df)
    df = calculate_rsi(df)
    df = calculate_ema_signals(df)
    df = analyze_bollinger(df)
    df = analyze_macd(df)

    signals      = []
    scores       = []
    buy_votes    = []
    sell_votes   = []

    for _, row in df.iterrows():
        try:
            ma_signal   = row.get('Signal',        'HOLD')
            ema_signal  = row.get('EMA_Signal',     'HOLD 🟡')
            bb_signal   = row.get('BB_Signal',      'HOLD ⚪')
            macd_signal = row.get('MACD_Crossover', 'HOLD 🟡')

            votes  = get_individual_votes(ma_signal, ema_signal, bb_signal, macd_signal)
            score  = calculate_combined_score(votes, DEFAULT_WEIGHTS)
            signal = get_combined_signal(score, DEFAULT_WEIGHTS)

            buy_count  = sum(1 for v in votes.values() if v ==  1)
            sell_count = sum(1 for v in votes.values() if v == -1)

            signals.append(signal)
            scores.append(score)
            buy_votes.append(buy_count)
            sell_votes.append(sell_count)
        except Exception:
            signals.append('NEUTRAL ⚪')
            scores.append(0)
            buy_votes.append(0)
            sell_votes.append(0)

    df['Combined_Signal'] = signals
    df['Combined_Score']  = scores
    df['Buy_Votes']       = buy_votes
    df['Sell_Votes']      = sell_votes

    return df


def calculate_signal_rarity(hist_df, current_signal, current_buy_votes):
    """
    Calculate how rare the current signal is
    based on 6 months of historical data.

    Returns:
      rarity_pct     : % of days this signal occurred
      rarity_label   : VERY RARE / RARE / OCCASIONAL / COMMON
      occurrences    : number of times it occurred
      total_days     : total trading days analyzed
      last_occurrence: date of last similar signal
      days_since_last: days since last similar signal
    """
    if hist_df.empty:
        return {
            "rarity_pct":      0,
            "rarity_label":    "UNKNOWN",
            "occurrences":     0,
            "total_days":      0,
            "last_occurrence": "N/A",
            "days_since_last": "N/A",
        }

    total_days = len(hist_df)

    # Find days where signal matched current signal type
    # Match by signal category not exact string
    def signal_category(sig):
        s = str(sig).upper()
        if "STRONG BUY"  in s: return "STRONG BUY"
        if "STRONG SELL" in s: return "STRONG SELL"
        if "BUY"         in s: return "BUY"
        if "SELL"        in s: return "SELL"
        return "NEUTRAL"

    current_category = signal_category(current_signal)

    # Find matching days (exclude today — last row)
    hist_except_today = hist_df.iloc[:-1]
    matching = hist_except_today[
        hist_except_today['Combined_Signal'].apply(signal_category) == current_category
    ]

    occurrences = len(matching)
    rarity_pct  = round((occurrences / max(total_days - 1, 1)) * 100, 1)

    # Also find days where buy_votes >= current buy_votes
    high_conviction = hist_except_today[
        hist_except_today['Buy_Votes'] >= current_buy_votes
    ]
    high_conviction_count = len(high_conviction)
    high_conviction_pct   = round((high_conviction_count / max(total_days - 1, 1)) * 100, 1)

    # Rarity label
    if rarity_pct <= 5:
        rarity_label = "VERY RARE 🔥"
    elif rarity_pct <= 15:
        rarity_label = "RARE ⭐"
    elif rarity_pct <= 30:
        rarity_label = "OCCASIONAL 🔔"
    else:
        rarity_label = "COMMON 📊"

    # Last occurrence date
    last_occurrence = "Never in this period"
    days_since_last = total_days

    if not matching.empty:
        last_date       = matching.index[-1]
        last_occurrence = last_date.strftime('%d %b %Y')
        days_since_last = (hist_df.index[-1] - last_date).days

    return {
        "rarity_pct":             rarity_pct,
        "rarity_label":           rarity_label,
        "occurrences":            occurrences,
        "total_days":             total_days,
        "last_occurrence":        last_occurrence,
        "days_since_last":        days_since_last,
        "high_conviction_count":  high_conviction_count,
        "high_conviction_pct":    high_conviction_pct,
    }


def explain_individual_signals(latest_row, ema_latest, bb_latest, macd_latest):
    """
    Generate plain English explanation for each strategy signal.
    Returns a list of explanation strings.
    """
    reasons_buy  = []
    reasons_sell = []
    reasons_hold = []

    # ── MA + RSI ──────────────────────────────────
    try:
        close  = float(latest_row['Close'])
        ma20   = float(latest_row['MA20'])
        rsi    = float(latest_row['RSI'])
        signal = str(latest_row['Signal'])

        pct_above_ma = round(((close - ma20) / ma20) * 100, 2)

        if 'BUY' in signal:
            reasons_buy.append(
                f"📈 **MA+RSI:** Price ₹{close:.0f} is {abs(pct_above_ma)}% "
                f"{'above' if pct_above_ma > 0 else 'below'} MA20 ₹{ma20:.0f}. "
                f"RSI={rsi:.1f} — {'momentum building' if rsi < 60 else 'approaching overbought'}."
            )
        elif 'SELL' in signal:
            reasons_sell.append(
                f"📉 **MA+RSI:** Price below MA20. RSI={rsi:.1f} — "
                f"{'oversold bounce possible' if rsi < 30 else 'downtrend confirmed'}."
            )
        else:
            reasons_hold.append(
                f"⚪ **MA+RSI:** Mixed signals. Price {abs(pct_above_ma)}% "
                f"{'above' if pct_above_ma > 0 else 'below'} MA20. RSI={rsi:.1f}."
            )
    except Exception:
        pass

    # ── EMA Crossover ─────────────────────────────
    try:
        ema9   = float(ema_latest['EMA9'])
        ema21  = float(ema_latest['EMA21'])
        signal = str(ema_latest['EMA_Signal'])
        trend  = str(ema_latest['EMA_Trend'])
        gap    = round(((ema9 - ema21) / ema21) * 100, 2)

        if 'BUY' in signal:
            reasons_buy.append(
                f"⚡ **EMA Crossover:** Fast EMA(9) crossed ABOVE Slow EMA(21). "
                f"Gap={abs(gap)}% — fresh bullish crossover signal."
            )
        elif 'SELL' in signal:
            reasons_sell.append(
                f"⚡ **EMA Crossover:** Fast EMA(9) crossed BELOW Slow EMA(21). "
                f"Bearish crossover confirmed."
            )
        else:
            if 'UPTREND' in trend:
                reasons_hold.append(
                    f"⚡ **EMA:** In uptrend (EMA9 > EMA21 by {abs(gap)}%) "
                    f"but no fresh crossover today."
                )
            elif 'DOWNTREND' in trend:
                reasons_hold.append(
                    f"⚡ **EMA:** In downtrend (EMA9 < EMA21 by {abs(gap)}%) "
                    f"— no entry signal."
                )
            else:
                reasons_hold.append(f"⚡ **EMA:** Neutral — EMAs converging.")
    except Exception:
        pass

    # ── Bollinger Bands ───────────────────────────
    try:
        bb_signal  = str(bb_latest['BB_Signal'])
        bb_pct     = float(bb_latest['BB_Pct'])   if not pd.isna(bb_latest['BB_Pct'])   else 0.5
        bb_upper   = float(bb_latest['BB_Upper'])  if not pd.isna(bb_latest['BB_Upper']) else 0
        bb_lower   = float(bb_latest['BB_Lower'])  if not pd.isna(bb_latest['BB_Lower']) else 0
        bb_rsi     = float(bb_latest['BB_RSI'])    if not pd.isna(bb_latest['BB_RSI'])   else 50

        position_pct = round(bb_pct * 100, 0)

        if 'BUY' in bb_signal:
            reasons_buy.append(
                f"📉 **Bollinger Bands:** Price near/below lower band (₹{bb_lower:.0f}). "
                f"RSI={bb_rsi:.1f} confirms oversold. "
                f"Mean reversion setup — price likely to bounce."
            )
        elif 'WATCH' in bb_signal:
            reasons_hold.append(
                f"📉 **Bollinger:** Price near lower band but RSI={bb_rsi:.1f} "
                f"not yet confirming oversold. Watch for confirmation."
            )
        elif 'SELL' in bb_signal:
            reasons_sell.append(
                f"📉 **Bollinger Bands:** Price near/above upper band (₹{bb_upper:.0f}). "
                f"RSI={bb_rsi:.1f} confirms overbought. Pullback likely."
            )
        elif 'CAUTION' in bb_signal:
            reasons_hold.append(
                f"📉 **Bollinger:** Price near upper band — RSI={bb_rsi:.1f} "
                f"not yet confirming overbought. Use caution on new longs."
            )
        else:
            reasons_hold.append(
                f"📉 **Bollinger:** Price at {position_pct:.0f}% of band range — "
                f"{'upper half' if bb_pct > 0.5 else 'lower half'}, no extreme signal."
            )
    except Exception:
        pass

    # ── MACD ──────────────────────────────────────
    try:
        macd_val    = float(macd_latest['MACD'])          if not pd.isna(macd_latest['MACD'])          else 0
        macd_sig    = float(macd_latest['MACD_Signal'])   if not pd.isna(macd_latest['MACD_Signal'])   else 0
        macd_hist   = float(macd_latest['MACD_Hist'])     if not pd.isna(macd_latest['MACD_Hist'])     else 0
        crossover   = str(macd_latest['MACD_Crossover'])
        momentum    = str(macd_latest['MACD_Momentum'])
        hist_dir    = str(macd_latest['MACD_Hist_Dir'])

        if 'BUY' in crossover:
            reasons_buy.append(
                f"📊 **MACD:** Bullish crossover — MACD line crossed ABOVE signal line. "
                f"Histogram={macd_hist:.4f} and {hist_dir.lower()} — momentum building."
            )
        elif 'SELL' in crossover:
            reasons_sell.append(
                f"📊 **MACD:** Bearish crossover — MACD crossed BELOW signal line. "
                f"Momentum turning negative."
            )
        else:
            if 'BULLISH' in momentum:
                reasons_hold.append(
                    f"📊 **MACD:** Bullish momentum (MACD > Signal) but no fresh crossover. "
                    f"Histogram {hist_dir.lower()} — "
                    f"{'momentum increasing' if 'GROWING' in hist_dir else 'momentum slowing'}."
                )
            elif 'BEARISH' in momentum:
                reasons_hold.append(
                    f"📊 **MACD:** Bearish momentum (MACD < Signal). "
                    f"Histogram {hist_dir.lower()}."
                )
            else:
                reasons_hold.append(f"📊 **MACD:** Neutral — lines converging.")
    except Exception:
        pass

    return reasons_buy, reasons_sell, reasons_hold


def build_risk_levels(latest_close, regime):
    """
    Calculate specific price levels for stop loss and target.
    Uses settings from strategy_settings if available.
    """
    try:
        from config.strategy_settings import (
            STOP_LOSS_PCT, TARGET_PROFIT_PCT, TRAILING_STOP_PCT
        )
    except ImportError:
        STOP_LOSS_PCT     = 0.06
        TARGET_PROFIT_PCT = 0.15
        TRAILING_STOP_PCT = 0.04

    stop_price   = round(latest_close * (1 - STOP_LOSS_PCT), 2)
    target_price = round(latest_close * (1 + TARGET_PROFIT_PCT), 2)
    trail_price  = round(latest_close * (1 - TRAILING_STOP_PCT), 2)

    # Adjust position size based on regime
    if "BULL" in str(regime) and "WEAK" not in str(regime):
        position_pct = 10.0
    elif "WEAK BULL" in str(regime):
        position_pct = 7.0
    elif "SIDEWAYS" in str(regime):
        position_pct = 5.0
    elif "WEAK BEAR" in str(regime):
        position_pct = 3.0
    else:
        position_pct = 0.0

    return {
        "entry_price":    latest_close,
        "stop_price":     stop_price,
        "target_price":   target_price,
        "trail_price":    trail_price,
        "stop_pct":       round(STOP_LOSS_PCT * 100, 1),
        "target_pct":     round(TARGET_PROFIT_PCT * 100, 1),
        "trail_pct":      round(TRAILING_STOP_PCT * 100, 1),
        "position_pct":   position_pct,
        "risk_reward":    round(TARGET_PROFIT_PCT / STOP_LOSS_PCT, 1),
    }


def get_full_explanation(
    stock_name,
    data,
    analyzed,
    ema_data,
    bb_data,
    macd_data,
    combined,
    regime,
    composite_score=None,
):
    """
    Master function — generates complete explanation.
    Called by app.py for the Stock Score tab.

    Returns a dictionary with all explanation components.
    """

    latest_row   = analyzed.iloc[-1]
    ema_latest   = ema_data.iloc[-1]
    bb_latest    = bb_data.iloc[-1]
    macd_latest  = macd_data.iloc[-1]
    latest_close = round(float(latest_row['Close']), 2)

    final_signal = combined["Final Signal"]
    buy_votes    = combined["Strategies Buy"]
    sell_votes   = combined["Strategies Sell"]
    hold_votes   = combined["Strategies Hold"]

    # ── Signal history and rarity ─────────────────
    hist_df    = build_full_signal_history(data)
    rarity     = calculate_signal_rarity(hist_df, final_signal, buy_votes)

    # ── Individual signal explanations ────────────
    reasons_buy, reasons_sell, reasons_hold = explain_individual_signals(
        latest_row, ema_latest, bb_latest, macd_latest
    )

    # ── Risk levels ───────────────────────────────
    risk = build_risk_levels(latest_close, regime)

    # ── Signal history table ──────────────────────
    # Show last 30 days of combined signals
    recent_hist = hist_df.tail(30)[['Combined_Signal', 'Buy_Votes', 'Combined_Score']].copy()
    recent_hist.index = pd.to_datetime(recent_hist.index).strftime('%d %b %Y')
    recent_hist.columns = ['Signal', 'Buy Votes', 'Score']

    # ── Verdict ───────────────────────────────────
    def build_verdict(signal, rarity_info, regime, risk):
        lines = []

        # Opening
        if "STRONG BUY" in signal:
            lines.append("✅ **Strong setup** — all strategies aligned. High conviction entry.")
        elif "BUY" in signal:
            lines.append("🟢 **Reasonable setup** — majority of strategies agree. Proceed with normal position.")
        elif "NEUTRAL" in signal:
            lines.append("⚪ **No clear edge** — strategies conflicting. Best to wait for clearer signal.")
        elif "SELL" in signal:
            lines.append("🔴 **Avoid new entries** — strategies suggest downside risk.")

        # Rarity context
        occ = rarity_info["occurrences"]
        days = rarity_info["total_days"]
        days_since = rarity_info["days_since_last"]

        if occ == 0:
            lines.append(
                f"🔥 **Signal Rarity:** This signal has NOT occurred in the last {days} trading days. "
                f"Extremely rare setup — treat with high conviction but also verify manually."
            )
        elif rarity_info["rarity_pct"] <= 5:
            lines.append(
                f"⭐ **Signal Rarity:** This signal occurred only {occ} times in {days} days ({rarity_info['rarity_pct']}%). "
                f"Last seen {days_since} days ago. Rare and meaningful."
            )
        else:
            lines.append(
                f"📊 **Signal Frequency:** This signal occurred {occ} times in {days} days "
                f"({rarity_info['rarity_pct']}%). Last seen {days_since} days ago."
            )

        # Regime warning
        if "BEAR" in str(regime) and "WEAK" not in str(regime):
            lines.append("🐻 **Bear Market Warning:** Even strong signals carry higher risk in bear markets. Consider reducing position size or waiting.")
        elif "WEAK BEAR" in str(regime):
            lines.append("📉 **Weak Bear Warning:** Market weakening — use smaller position if entering.")

        # Risk-reward
        lines.append(
            f"📐 **Risk-Reward:** {risk['risk_reward']}:1 "
            f"(Risk {risk['stop_pct']}% → Reward {risk['target_pct']}%)"
        )

        return "\n\n".join(lines)

    verdict = build_verdict(final_signal, rarity, regime, risk)

    return {
        "stock_name":    stock_name,
        "final_signal":  final_signal,
        "buy_votes":     buy_votes,
        "sell_votes":    sell_votes,
        "hold_votes":    hold_votes,
        "composite_score": composite_score,
        "regime":        regime,
        "rarity":        rarity,
        "reasons_buy":   reasons_buy,
        "reasons_sell":  reasons_sell,
        "reasons_hold":  reasons_hold,
        "risk":          risk,
        "recent_history":recent_hist,
        "verdict":       verdict,
        "hist_df":       hist_df,
    }
