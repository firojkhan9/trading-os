# ================================================
# FILE: strategies/combined_backtest.py
# PURPOSE: Backtest the Combined Signal Engine
#          All 4 strategies vote together on
#          every day — trade only on consensus
#
# WHY THIS IS MORE REALISTIC:
#   Individual backtests test one strategy alone.
#   In real trading you see ALL signals together.
#   This backtest simulates exactly how you would
#   actually use the dashboard — buy when multiple
#   strategies agree, sell when they reverse.
#
# ENTRY RULES:
#   STRONG BUY  (3-4 strategies agree) → Enter full size
#   BUY         (2 strategies agree)   → Enter half size
#   NEUTRAL     → Do nothing
#   SELL/STRONG SELL                   → Exit if holding
#
# EXIT RULES:
#   Stop loss    : 3%
#   Target       : 6%
#   Signal exit  : Combined turns SELL or STRONG SELL
#   Weak exit    : Combined turns NEUTRAL with small profit
# ================================================

import pandas as pd

from strategies.indicators import calculate_ma20, calculate_rsi
from strategies.ema_strategy import calculate_ema_signals
from strategies.bollinger_strategy import analyze_bollinger
from strategies.macd_strategy import analyze_macd
from strategies.combined_signal import (
    get_individual_votes,
    calculate_combined_score,
    get_combined_signal,
    DEFAULT_WEIGHTS
)


def prepare_combined_data(raw_data):
    """
    Run all 4 strategies on the raw price data
    and generate a combined signal for each day.

    This is the key function — it merges all
    strategy signals into one dataframe.
    """

    # ── Step 1: Calculate all strategy signals ────
    df = raw_data.copy()

    # MA + RSI signals
    df = calculate_ma20(df)
    df = calculate_rsi(df)

    # EMA signals
    df = calculate_ema_signals(df)

    # Bollinger Bands signals
    df = analyze_bollinger(df)

    # MACD signals
    df = analyze_macd(df)

    # ── Step 2: Generate combined signal per day ──
    combined_signals = []
    combined_scores  = []
    buy_counts       = []
    sell_counts      = []

    for _, row in df.iterrows():

        # Get individual signals for this day
        ma_signal   = row.get('Signal',        'HOLD')
        ema_signal  = row.get('EMA_Signal',     'HOLD 🟡')
        bb_signal   = row.get('BB_Signal',      'HOLD ⚪')
        macd_signal = row.get('MACD_Crossover', 'HOLD 🟡')

        # Convert to votes
        votes = get_individual_votes(
            ma_signal, ema_signal, bb_signal, macd_signal
        )

        # Calculate weighted score
        score = calculate_combined_score(votes, DEFAULT_WEIGHTS)

        # Get final signal
        final_signal = get_combined_signal(score, DEFAULT_WEIGHTS)

        # Count buy and sell votes
        buy_count  = sum(1 for v in votes.values() if v ==  1)
        sell_count = sum(1 for v in votes.values() if v == -1)

        combined_signals.append(final_signal)
        combined_scores.append(score)
        buy_counts.append(buy_count)
        sell_counts.append(sell_count)

    df['Combined_Signal'] = combined_signals
    df['Combined_Score']  = combined_scores
    df['Buy_Votes']       = buy_counts
    df['Sell_Votes']      = sell_counts

    return df


def run_combined_backtest(raw_data, starting_capital=100000):
    """
    Backtest the Combined Signal Engine.

    Entry:
      STRONG BUY (score >= 1.5) → full 10% position
      BUY        (score >= 0.5) → half 5% position

    Exit:
      Stop loss at 3%
      Target at 6%
      SELL or STRONG SELL signal
      NEUTRAL with profit > 1%  (lock in gains early)

    Returns:
      summary dict, equity_df, trades_df
    """

    # ── Prepare data with all signals ────────────
    try:
        data = prepare_combined_data(raw_data)
    except Exception as e:
        return {
            "Total Trades":  0,
            "Win Rate":      "0%",
            "Total P&L":     "₹0",
            "Total Return":  "0%",
            "Best Trade":    "N/A",
            "Worst Trade":   "N/A",
            "Max Drawdown":  "N/A",
            "Final Capital": f"₹{starting_capital:,}",
            "Note":          f"Error: {str(e)}",
        }, pd.DataFrame(), pd.DataFrame()

    # Drop rows where any core indicator is NaN
    data = data.dropna(subset=['MA20', 'RSI', 'EMA9', 'EMA21'])

    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    brokerage    = 0.001   # 0.1% per trade
    stop_loss    = 0.03    # 3% stop loss
    target       = 0.06    # 6% profit target

    for date, row in data.iterrows():

        price   = float(row['Close'])
        signal  = row['Combined_Signal']
        score   = float(row['Combined_Score'])
        buy_votes = int(row['Buy_Votes'])

        # ── ENTRY LOGIC ───────────────────────────
        if position is None:

            # Strong consensus — at least 3 strategies agree BUY
            if "STRONG BUY" in signal or buy_votes >= 3:
                max_position = 0.10   # Full 10% position
                spend        = capital * max_position
                quantity     = int(spend // price)

                if quantity > 0:
                    cost     = round(quantity * price * (1 + brokerage), 2)
                    capital -= cost
                    position = {
                        "buy_date":     date,
                        "buy_price":    price,
                        "quantity":     quantity,
                        "cost":         cost,
                        "entry_type":   "STRONG BUY",
                        "buy_votes":    buy_votes,
                    }

            # Weak consensus — exactly 2 strategies agree BUY
            elif "BUY" in signal and buy_votes == 2:
                max_position = 0.05   # Half 5% position (less conviction)
                spend        = capital * max_position
                quantity     = int(spend // price)

                if quantity > 0:
                    cost     = round(quantity * price * (1 + brokerage), 2)
                    capital -= cost
                    position = {
                        "buy_date":     date,
                        "buy_price":    price,
                        "quantity":     quantity,
                        "cost":         cost,
                        "entry_type":   "BUY",
                        "buy_votes":    buy_votes,
                    }

        # ── EXIT LOGIC ────────────────────────────
        elif position is not None:

            buy_price  = position['buy_price']
            quantity   = position['quantity']
            cost       = position['cost']
            entry_type = position['entry_type']
            change_pct = (price - buy_price) / buy_price

            exit_reason = None

            # Hard stop loss — always respected
            if change_pct <= -stop_loss:
                exit_reason = "STOP LOSS"

            # Hard target — always take profit
            elif change_pct >= target:
                exit_reason = "TARGET HIT"

            # Combined signal turned bearish — exit
            elif "SELL" in signal:
                exit_reason = f"COMBINED SELL ({int(row['Sell_Votes'])} strategies)"

            # Signal went neutral but we have a small profit
            # Lock in gains rather than waiting for reversal
            elif "NEUTRAL" in signal and change_pct > 0.01:
                exit_reason = "NEUTRAL EXIT (profit locked)"

            # ── Execute sell ──────────────────────
            if exit_reason:
                proceeds = round(quantity * price * (1 - brokerage), 2)
                pnl      = round(proceeds - cost, 2)
                pnl_pct  = round((pnl / cost) * 100, 2)
                capital += proceeds

                trades.append({
                    "Buy Date":    position['buy_date'].strftime('%Y-%m-%d'),
                    "Sell Date":   date.strftime('%Y-%m-%d'),
                    "Entry Type":  entry_type,
                    "Buy Votes":   position['buy_votes'],
                    "Buy Price":   round(buy_price, 2),
                    "Sell Price":  round(price, 2),
                    "Quantity":    quantity,
                    "P&L":         pnl,
                    "P&L %":       pnl_pct,
                    "Exit Reason": exit_reason,
                    "Result":      "WIN 🟢" if pnl >= 0 else "LOSS 🔴",
                })
                position = None

        # ── Track equity ──────────────────────────
        if position is not None:
            total = capital + (position['quantity'] * price)
        else:
            total = capital

        equity_curve.append({
            "Date":            date,
            "Equity":          round(total, 2),
            "Combined_Signal": signal,
        })

    # ── Performance Summary ───────────────────────
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("Date")

    if trades_df.empty:
        return {
            "Total Trades":  0,
            "Win Rate":      "0%",
            "Total P&L":     "₹0",
            "Total Return":  "0%",
            "Best Trade":    "N/A",
            "Worst Trade":   "N/A",
            "Max Drawdown":  "N/A",
            "Final Capital": f"₹{round(capital):,}",
            "Note":          "No trades — signals never reached BUY threshold",
        }, equity_df, trades_df

    wins      = trades_df[trades_df['P&L'] >= 0]
    losses    = trades_df[trades_df['P&L'] < 0]
    win_rate  = round((len(wins) / len(trades_df)) * 100, 2)
    total_pnl = round(trades_df['P&L'].sum(), 2)
    total_ret = round(((capital - starting_capital) / starting_capital) * 100, 2)

    equity_df['Peak']     = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = (
        (equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak'] * 100
    )
    max_dd = round(equity_df['Drawdown'].min(), 2)

    best  = trades_df.loc[trades_df['P&L'].idxmax()]
    worst = trades_df.loc[trades_df['P&L'].idxmin()]

    # Count entry types
    strong_buys = len(trades_df[trades_df['Entry Type'] == 'STRONG BUY'])
    weak_buys   = len(trades_df[trades_df['Entry Type'] == 'BUY'])

    summary = {
        "Total Trades":    len(trades_df),
        "Win Rate":        f"{win_rate}%",
        "Winning Trades":  len(wins),
        "Losing Trades":   len(losses),
        "Total P&L":       f"₹{total_pnl:,}",
        "Total Return":    f"{total_ret}%",
        "Best Trade":      f"₹{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":     f"₹{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":    f"{max_dd}%",
        "Final Capital":   f"₹{round(capital):,}",
        "Strong Buy Entries": strong_buys,
        "Weak Buy Entries":   weak_buys,
    }

    return summary, equity_df, trades_df
