# ================================================
# FILE: strategies/backtest.py
# PURPOSE: Backtest MA+RSI strategy on historical data
#          UPDATED: Trailing stop, wider stop loss,
#          higher profit target for realistic results
# ================================================

import pandas as pd
import yfinance as yf
from strategies.indicators import calculate_ma20, calculate_rsi

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Import central settings ───────────────────────
try:
    from config.strategy_settings import (
        STOP_LOSS_PCT,
        TARGET_PROFIT_PCT,
        USE_TRAILING_STOP,
        TRAILING_STOP_PCT,
        MAX_POSITION_PCT,
        BROKERAGE_PCT,
    )
except ImportError:
    # Fallback defaults if settings file not found
    STOP_LOSS_PCT     = 0.06
    TARGET_PROFIT_PCT = 0.15
    USE_TRAILING_STOP = True
    TRAILING_STOP_PCT = 0.04
    MAX_POSITION_PCT  = 0.10
    BROKERAGE_PCT     = 0.001

STARTING_CAPITAL = 100000


def fetch_historical_data(symbol, period="1y"):
    """Fetch historical data for backtesting."""
    data = yf.download(
        tickers=symbol, period=period,
        interval="1d", progress=False
    )
    data.columns = [col[0] for col in data.columns]
    return data


def run_backtest(symbol, stock_name, period="1y"):
    """
    Run MA+RSI backtest with trailing stop logic.
    """

    data = fetch_historical_data(symbol, period)
    if data.empty:
        return None, None

    data = calculate_ma20(data)
    data = calculate_rsi(data)
    data = data.dropna()

    capital      = STARTING_CAPITAL
    position     = None
    trades       = []
    equity_curve = []

    for date, row in data.iterrows():
        price = float(row['Close'])
        ma20  = float(row['MA20'])
        rsi   = float(row['RSI'])

        # Signal
        if price > ma20 and rsi < 70:
            signal = "BUY"
        elif price < ma20 and rsi > 30:
            signal = "SELL"
        else:
            signal = "HOLD"

        # ── BUY ──────────────────────────────────
        if signal == "BUY" and position is None:
            spend    = min(capital * MAX_POSITION_PCT, capital)
            quantity = int(spend // price)
            if quantity > 0:
                brok      = round(quantity * price * BROKERAGE_PCT, 2)
                buy_value = round(quantity * price + brok, 2)
                capital  -= buy_value
                position  = {
                    "buy_date":  date,
                    "buy_price": price,
                    "quantity":  quantity,
                    "buy_value": buy_value,
                    "peak_price":price,   # for trailing stop
                }

        # ── CHECK EXITS ───────────────────────────
        elif position is not None:
            buy_price  = position['buy_price']
            quantity   = position['quantity']
            buy_value  = position['buy_value']
            change_pct = (price - buy_price) / buy_price

            # Update peak price for trailing stop
            if price > position['peak_price']:
                position['peak_price'] = price

            peak_price    = position['peak_price']
            trail_pct     = (price - peak_price) / peak_price  # negative = dropped from peak

            exit_reason = None

            # Hard stop loss
            if change_pct <= -STOP_LOSS_PCT:
                exit_reason = "STOP LOSS"

            # Trailing stop — only activates after some profit
            elif USE_TRAILING_STOP and trail_pct <= -TRAILING_STOP_PCT and change_pct > 0:
                exit_reason = "TRAILING STOP"

            # Profit target
            elif change_pct >= TARGET_PROFIT_PCT:
                exit_reason = "TARGET HIT"

            # Signal turned sell
            elif signal == "SELL":
                exit_reason = "SIGNAL"

            # ── SELL ─────────────────────────────
            if exit_reason:
                brok       = round(quantity * price * BROKERAGE_PCT, 2)
                sell_value = round(quantity * price - brok, 2)
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
                    "P&L":         pnl,
                    "P&L %":       pnl_pct,
                    "Exit Reason": exit_reason,
                    "Result":      "WIN 🟢" if pnl >= 0 else "LOSS 🔴"
                })
                position = None

        # Equity tracking
        if position is not None:
            current_value = capital + (position['quantity'] * price)
        else:
            current_value = capital

        equity_curve.append({"Date": date, "Equity": round(current_value, 2)})

    # Performance summary
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("Date")

    if trades_df.empty:
        summary = {
            "Stock": stock_name, "Period": period,
            "Total Trades": 0, "Win Rate": "0%",
            "Total P&L": "₹0", "Total Return": "0%",
            "Best Trade": "N/A", "Worst Trade": "N/A",
            "Max Drawdown": "N/A",
            "Final Capital": f"₹{round(capital, 2):,}",
        }
        return summary, equity_df, trades_df

    wins     = trades_df[trades_df['P&L'] >= 0]
    win_rate = round((len(wins) / len(trades_df)) * 100, 2)
    total_pnl= round(trades_df['P&L'].sum(), 2)
    total_ret= round(((capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100, 2)
    best     = trades_df.loc[trades_df['P&L'].idxmax()]
    worst    = trades_df.loc[trades_df['P&L'].idxmin()]

    equity_df['Peak']     = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = ((equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak']) * 100
    max_dd = round(equity_df['Drawdown'].min(), 2)

    summary = {
        "Stock":         stock_name,
        "Period":        period,
        "Total Trades":  len(trades_df),
        "Win Rate":      f"{win_rate}%",
        "Total P&L":     f"₹{total_pnl:,}",
        "Total Return":  f"{total_ret}%",
        "Best Trade":    f"₹{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":   f"₹{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":  f"{max_dd}%",
        "Final Capital": f"₹{round(capital, 2):,}",
    }

    return summary, equity_df, trades_df
