# ================================================
# FILE: strategies/combined_backtest.py
# PURPOSE: Backtest the Combined Signal Engine
#          UPDATED: Trailing stop, wider stop loss,
#          higher profit target, smarter entries
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

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.strategy_settings import (
        STOP_LOSS_PCT, TARGET_PROFIT_PCT,
        USE_TRAILING_STOP, TRAILING_STOP_PCT,
        MAX_POSITION_PCT, WEAK_POSITION_PCT,
        BROKERAGE_PCT, STRONG_BUY_VOTES, WEAK_BUY_VOTES,
    )
except ImportError:
    STOP_LOSS_PCT     = 0.06
    TARGET_PROFIT_PCT = 0.15
    USE_TRAILING_STOP = True
    TRAILING_STOP_PCT = 0.04
    MAX_POSITION_PCT  = 0.10
    WEAK_POSITION_PCT = 0.05
    BROKERAGE_PCT     = 0.001
    STRONG_BUY_VOTES  = 3
    WEAK_BUY_VOTES    = 2


def prepare_combined_data(raw_data):
    """Run all 4 strategies and generate daily combined signal."""
    df = raw_data.copy()
    df = calculate_ma20(df)
    df = calculate_rsi(df)
    df = calculate_ema_signals(df)
    df = analyze_bollinger(df)
    df = analyze_macd(df)

    combined_signals = []
    combined_scores  = []
    buy_counts       = []
    sell_counts      = []

    for _, row in df.iterrows():
        ma_signal   = row.get('Signal',        'HOLD')
        ema_signal  = row.get('EMA_Signal',     'HOLD 🟡')
        bb_signal   = row.get('BB_Signal',      'HOLD ⚪')
        macd_signal = row.get('MACD_Crossover', 'HOLD 🟡')

        votes        = get_individual_votes(ma_signal, ema_signal, bb_signal, macd_signal)
        score        = calculate_combined_score(votes, DEFAULT_WEIGHTS)
        final_signal = get_combined_signal(score, DEFAULT_WEIGHTS)

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
    Backtest Combined Signal with trailing stop.

    Entry:
      3+ strategies agree BUY → full MAX_POSITION_PCT
      2  strategies agree BUY → WEAK_POSITION_PCT

    Exit:
      Hard stop loss at STOP_LOSS_PCT
      Trailing stop at TRAILING_STOP_PCT from peak
      Profit target at TARGET_PROFIT_PCT
      Combined turns SELL → exit
      Combined turns NEUTRAL with profit > 1% → lock in
    """
    try:
        data = prepare_combined_data(raw_data)
    except Exception as e:
        return {
            "Total Trades": 0, "Win Rate": "0%",
            "Total P&L": "₹0", "Total Return": "0%",
            "Best Trade": "N/A", "Worst Trade": "N/A",
            "Max Drawdown": "N/A",
            "Final Capital": f"₹{starting_capital:,}",
            "Note": f"Error: {str(e)}",
        }, pd.DataFrame(), pd.DataFrame()

    data = data.dropna(subset=['MA20', 'RSI', 'EMA9', 'EMA21'])

    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    for date, row in data.iterrows():
        price     = float(row['Close'])
        signal    = row['Combined_Signal']
        buy_votes = int(row['Buy_Votes'])

        # ── ENTRY ─────────────────────────────────
        if position is None:

            # Strong consensus — 3+ agree
            if "STRONG BUY" in signal or buy_votes >= STRONG_BUY_VOTES:
                spend    = capital * MAX_POSITION_PCT
                quantity = int(spend // price)
                if quantity > 0:
                    cost     = round(quantity * price * (1 + BROKERAGE_PCT), 2)
                    capital -= cost
                    position = {
                        "buy_date":   date,
                        "buy_price":  price,
                        "quantity":   quantity,
                        "cost":       cost,
                        "peak_price": price,
                        "entry_type": "STRONG BUY",
                        "buy_votes":  buy_votes,
                    }

            # Normal consensus — exactly 2 agree
            elif "BUY" in signal and buy_votes >= WEAK_BUY_VOTES:
                spend    = capital * WEAK_POSITION_PCT
                quantity = int(spend // price)
                if quantity > 0:
                    cost     = round(quantity * price * (1 + BROKERAGE_PCT), 2)
                    capital -= cost
                    position = {
                        "buy_date":   date,
                        "buy_price":  price,
                        "quantity":   quantity,
                        "cost":       cost,
                        "peak_price": price,
                        "entry_type": "BUY",
                        "buy_votes":  buy_votes,
                    }

        # ── EXIT ──────────────────────────────────
        elif position is not None:
            buy_price  = position['buy_price']
            quantity   = position['quantity']
            cost       = position['cost']
            entry_type = position['entry_type']
            change_pct = (price - buy_price) / buy_price

            # Update trailing stop peak
            if price > position['peak_price']:
                position['peak_price'] = price

            peak_price = position['peak_price']
            trail_pct  = (price - peak_price) / peak_price

            exit_reason = None

            # Hard stop — always respected
            if change_pct <= -STOP_LOSS_PCT:
                exit_reason = "STOP LOSS"

            # Trailing stop — only when profitable
            elif USE_TRAILING_STOP and trail_pct <= -TRAILING_STOP_PCT and change_pct > 0:
                exit_reason = "TRAILING STOP"

            # Profit target
            elif change_pct >= TARGET_PROFIT_PCT:
                exit_reason = "TARGET HIT"

            # Combined signal turned bearish
            elif "SELL" in signal:
                exit_reason = f"COMBINED SELL ({int(row['Sell_Votes'])} strategies)"

            # Signal went neutral but we have profit — lock in
            elif "NEUTRAL" in signal and change_pct > 0.01:
                exit_reason = "NEUTRAL EXIT (profit locked)"

            if exit_reason:
                proceeds = round(quantity * price * (1 - BROKERAGE_PCT), 2)
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

        # Equity tracking
        if position is not None:
            total = capital + (position['quantity'] * price)
        else:
            total = capital

        equity_curve.append({
            "Date":            date,
            "Equity":          round(total, 2),
            "Combined_Signal": signal,
        })

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("Date")

    if trades_df.empty:
        return {
            "Total Trades": 0, "Win Rate": "0%",
            "Total P&L": "₹0", "Total Return": "0%",
            "Best Trade": "N/A", "Worst Trade": "N/A",
            "Max Drawdown": "N/A",
            "Final Capital": f"₹{round(capital):,}",
            "Note": "No trades — signals never reached BUY threshold",
        }, equity_df, trades_df

    wins      = trades_df[trades_df['P&L'] >= 0]
    losses    = trades_df[trades_df['P&L'] < 0]
    win_rate  = round((len(wins) / len(trades_df)) * 100, 2)
    total_pnl = round(trades_df['P&L'].sum(), 2)
    total_ret = round(((capital - starting_capital) / starting_capital) * 100, 2)
    best      = trades_df.loc[trades_df['P&L'].idxmax()]
    worst     = trades_df.loc[trades_df['P&L'].idxmin()]

    equity_df['Peak']     = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = ((equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak'] * 100)
    max_dd = round(equity_df['Drawdown'].min(), 2)

    strong_buys = len(trades_df[trades_df['Entry Type'] == 'STRONG BUY'])
    weak_buys   = len(trades_df[trades_df['Entry Type'] == 'BUY'])

    return {
        "Total Trades":       len(trades_df),
        "Win Rate":           f"{win_rate}%",
        "Winning Trades":     len(wins),
        "Losing Trades":      len(losses),
        "Total P&L":          f"₹{total_pnl:,}",
        "Total Return":       f"{total_ret}%",
        "Best Trade":         f"₹{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":        f"₹{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":       f"{max_dd}%",
        "Final Capital":      f"₹{round(capital):,}",
        "Strong Buy Entries": strong_buys,
        "Weak Buy Entries":   weak_buys,
    }, equity_df, trades_df
