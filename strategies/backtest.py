# ================================================
# FILE: strategies/backtest.py
# PURPOSE: Test trading strategy on historical data
#          See how signals performed in the past
# ================================================

import pandas as pd
import yfinance as yf
from strategies.indicators import calculate_ma20, calculate_rsi

# ── Backtesting Configuration ─────────────────────
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    STARTING_CAPITAL,
    STOP_LOSS_PCT,
    TARGET_PROFIT_PCT,
    MAX_POSITION_PCT,
    BROKERAGE_PCT
)


def fetch_historical_data(symbol, period="1y"):
    """
    Fetch historical data for backtesting.
    Default: 1 year of daily data.
    """
    data = yf.download(
        tickers=symbol,
        period=period,
        interval="1d",
        progress=False
    )
    # Flatten multi-level columns
    data.columns = [col[0] for col in data.columns]
    return data


def run_backtest(symbol, stock_name, period="1y"):
    """
    Run full backtest on a stock.
    Simulates BUY/SELL signals day by day.
    Returns trades and performance summary.
    """

    # ── Step 1: Get historical data ───────────────
    data = fetch_historical_data(symbol, period)

    if data.empty:
        return None, None

    # ── Step 2: Calculate indicators ──────────────
    data = calculate_ma20(data)
    data = calculate_rsi(data)

    # Drop rows where indicators not yet calculated
    data = data.dropna()

    # ── Step 3: Simulate trades day by day ────────
    capital       = STARTING_CAPITAL
    position      = None   # Current open position
    trades        = []     # All completed trades
    equity_curve  = []     # Capital value each day

    for date, row in data.iterrows():
        price  = float(row['Close'])
        ma20   = float(row['MA20'])
        rsi    = float(row['RSI'])

        # ── Generate signal ───────────────────────
        if price > ma20 and rsi < 70:
            signal = "BUY"
        elif price < ma20 and rsi > 30:
            signal = "SELL"
        else:
            signal = "HOLD"

        # ── Execute BUY ───────────────────────────
        if signal == "BUY" and position is None:
            # Calculate position size
            spend    = min(capital * MAX_POSITION_PCT, capital)
            quantity = int(spend // price)

            if quantity > 0:
                # Deduct brokerage
                brokerage  = round(quantity * price * BROKERAGE_PCT, 2)
                buy_value  = round(quantity * price + brokerage, 2)
                capital   -= buy_value

                position = {
                    "buy_date":  date,
                    "buy_price": price,
                    "quantity":  quantity,
                    "buy_value": buy_value,
                }

        # ── Check stop loss and profit target ─────
        elif position is not None:
            buy_price    = position['buy_price']
            quantity     = position['quantity']
            buy_value    = position['buy_value']
            change_pct   = (price - buy_price) / buy_price

            # Determine if we should exit
            exit_reason = None

            if change_pct <= -STOP_LOSS_PCT:
                exit_reason = "STOP LOSS"

            elif change_pct >= TARGET_PROFIT_PCT:
                exit_reason = "TARGET HIT"

            elif signal == "SELL":
                exit_reason = "SIGNAL"

            # ── Execute SELL ──────────────────────
            if exit_reason:
                brokerage  = round(quantity * price * BROKERAGE_PCT, 2)
                sell_value = round(quantity * price - brokerage, 2)
                pnl        = round(sell_value - buy_value, 2)
                pnl_pct    = round((pnl / buy_value) * 100, 2)
                capital   += sell_value

                trades.append({
                    "Stock":       stock_name,
                    "Buy Date":    position['buy_date'].strftime('%Y-%m-%d'),
                    "Sell Date":   date.strftime('%Y-%m-%d'),
                    "Buy Price":   round(buy_price, 2),
                    "Sell Price":  round(price, 2),
                    "Quantity":    quantity,
                    "Buy Value":   round(buy_value, 2),
                    "Sell Value":  round(sell_value, 2),
                    "P&L":         pnl,
                    "P&L %":       pnl_pct,
                    "Exit Reason": exit_reason,
                    "Result":      "WIN 🟢" if pnl >= 0 else "LOSS 🔴"
                })

                # Reset position
                position = None

        # ── Track equity each day ─────────────────
        # If holding a position — include its current value
        if position is not None:
            current_value = capital + (position['quantity'] * price)
        else:
            current_value = capital

        equity_curve.append({
            "Date":   date,
            "Equity": round(current_value, 2)
        })

    # ── Step 4: Calculate performance summary ─────
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("Date")

    if trades_df.empty:
        summary = {
            "Stock":           stock_name,
            "Period":          period,
            "Total Trades":    0,
            "Win Rate":        "0%",
            "Total P&L":       "₹0",
            "Total Return":    "0%",
            "Best Trade":      "N/A",
            "Worst Trade":     "N/A",
            "Max Drawdown":    "N/A",
            "Final Capital":   f"₹{round(capital, 2):,}",
        }
        return summary, equity_df

    # Win rate
    wins      = trades_df[trades_df['P&L'] >= 0]
    win_rate  = round((len(wins) / len(trades_df)) * 100, 2)

    # Total P&L
    total_pnl = round(trades_df['P&L'].sum(), 2)
    total_ret = round(((capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100, 2)

    # Best and worst trades
    best  = trades_df.loc[trades_df['P&L'].idxmax()]
    worst = trades_df.loc[trades_df['P&L'].idxmin()]

    # Max drawdown
    equity_df['Peak']     = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = ((equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak']) * 100
    max_drawdown          = round(equity_df['Drawdown'].min(), 2)

    summary = {
        "Stock":         stock_name,
        "Period":        period,
        "Total Trades":  len(trades_df),
        "Win Rate":      f"{win_rate}%",
        "Total P&L":     f"₹{total_pnl:,}",
        "Total Return":  f"{total_ret}%",
        "Best Trade":    f"₹{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":   f"₹{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":  f"{max_drawdown}%",
        "Final Capital": f"₹{round(capital, 2):,}",
    }

    return summary, equity_df, trades_df