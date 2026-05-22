# ================================================
# FILE: strategies/ema_strategy.py
# PURPOSE: EMA Crossover Strategy
#          UPDATED: Trailing stop, wider stop loss,
#          higher profit target
# ================================================

import pandas as pd
import yfinance as yf

FAST_EMA_PERIOD = 9
SLOW_EMA_PERIOD = 21
SIGNAL_PERIOD   = 9

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.strategy_settings import (
        STOP_LOSS_PCT, TARGET_PROFIT_PCT,
        USE_TRAILING_STOP, TRAILING_STOP_PCT,
        MAX_POSITION_PCT, BROKERAGE_PCT,
    )
except ImportError:
    STOP_LOSS_PCT     = 0.06
    TARGET_PROFIT_PCT = 0.15
    USE_TRAILING_STOP = True
    TRAILING_STOP_PCT = 0.04
    MAX_POSITION_PCT  = 0.10
    BROKERAGE_PCT     = 0.001


def calculate_ema(data, period, column='Close'):
    data[f'EMA{period}'] = data[column].ewm(
        span=period, adjust=False
    ).mean().round(2)
    return data


def calculate_ema_signals(data):
    data = calculate_ema(data, FAST_EMA_PERIOD)
    data = calculate_ema(data, SLOW_EMA_PERIOD)

    data['Prev_Fast'] = data[f'EMA{FAST_EMA_PERIOD}'].shift(1)
    data['Prev_Slow'] = data[f'EMA{SLOW_EMA_PERIOD}'].shift(1)

    fast      = data[f'EMA{FAST_EMA_PERIOD}']
    slow      = data[f'EMA{SLOW_EMA_PERIOD}']
    prev_fast = data['Prev_Fast']
    prev_slow = data['Prev_Slow']

    data['EMA_Signal'] = 'HOLD 🟡'

    buy_condition  = (prev_fast <= prev_slow) & (fast > slow)
    sell_condition = (prev_fast >= prev_slow) & (fast < slow)

    data.loc[buy_condition,  'EMA_Signal'] = 'BUY 🟢'
    data.loc[sell_condition, 'EMA_Signal'] = 'SELL 🔴'

    data['EMA_Trend'] = 'NEUTRAL ↔️'
    data.loc[fast > slow, 'EMA_Trend'] = 'UPTREND 📈'
    data.loc[fast < slow, 'EMA_Trend'] = 'DOWNTREND 📉'

    data['EMA_Gap'] = ((fast - slow) / slow * 100).round(3)
    data = data.drop(['Prev_Fast', 'Prev_Slow'], axis=1)

    return data


def get_ema_summary(data):
    latest = data.iloc[-1]
    prev   = data.iloc[-2]

    fast_ema = round(float(latest[f'EMA{FAST_EMA_PERIOD}']), 2)
    slow_ema = round(float(latest[f'EMA{SLOW_EMA_PERIOD}']), 2)
    gap      = round(float(latest['EMA_Gap']), 3)
    signal   = latest['EMA_Signal']
    trend    = latest['EMA_Trend']

    signals       = data['EMA_Signal']
    cross_signals = signals[signals != 'HOLD 🟡']
    days_since    = 0

    if not cross_signals.empty:
        last_cross_idx = cross_signals.index[-1]
        days_since     = len(data) - data.index.get_loc(last_cross_idx) - 1

    return {
        "Fast EMA":         f"₹{fast_ema}",
        "Slow EMA":         f"₹{slow_ema}",
        "EMA Gap":          f"{gap}%",
        "Signal":           signal,
        "Trend":            trend,
        "Days Since Cross": days_since,
    }


def run_ema_backtest(data, starting_capital=100000):
    """
    EMA Crossover backtest with trailing stop.
    """
    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    for date, row in data.iterrows():
        price  = float(row['Close'])
        signal = row['EMA_Signal']
        trend  = row['EMA_Trend']

        # ── BUY on crossover ──────────────────────
        if signal == 'BUY 🟢' and position is None:
            spend    = capital * MAX_POSITION_PCT
            quantity = int(spend // price)
            if quantity > 0:
                cost      = round(quantity * price * (1 + BROKERAGE_PCT), 2)
                capital  -= cost
                position  = {
                    "buy_date":   date,
                    "buy_price":  price,
                    "quantity":   quantity,
                    "cost":       cost,
                    "peak_price": price,
                }

        elif position is not None:
            buy_price  = position['buy_price']
            quantity   = position['quantity']
            cost       = position['cost']
            change_pct = (price - buy_price) / buy_price

            # Update peak for trailing stop
            if price > position['peak_price']:
                position['peak_price'] = price

            peak_price = position['peak_price']
            trail_pct  = (price - peak_price) / peak_price

            exit_reason = None

            if change_pct <= -STOP_LOSS_PCT:
                exit_reason = "STOP LOSS"
            elif USE_TRAILING_STOP and trail_pct <= -TRAILING_STOP_PCT and change_pct > 0:
                exit_reason = "TRAILING STOP"
            elif change_pct >= TARGET_PROFIT_PCT:
                exit_reason = "TARGET HIT"
            elif signal == 'SELL 🔴':
                exit_reason = "EMA CROSSOVER"
            elif trend == 'DOWNTREND 📉' and change_pct < -STOP_LOSS_PCT / 2:
                exit_reason = "DOWNTREND EXIT"

            if exit_reason:
                proceeds = round(quantity * price * (1 - BROKERAGE_PCT), 2)
                pnl      = round(proceeds - cost, 2)
                pnl_pct  = round((pnl / cost) * 100, 2)
                capital += proceeds

                trades.append({
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

        if position is not None:
            total = capital + (position['quantity'] * price)
        else:
            total = capital

        equity_curve.append({"Date": date, "Equity": round(total, 2)})

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("Date")

    if trades_df.empty:
        return {
            "Total Trades": 0, "Win Rate": "0%",
            "Total P&L": "₹0", "Total Return": "0%",
            "Best Trade": "N/A", "Worst Trade": "N/A",
            "Max Drawdown": "N/A",
            "Final Capital": f"₹{round(capital):,}",
        }, equity_df, trades_df

    wins      = trades_df[trades_df['P&L'] >= 0]
    win_rate  = round((len(wins) / len(trades_df)) * 100, 2)
    total_pnl = round(trades_df['P&L'].sum(), 2)
    total_ret = round(((capital - starting_capital) / starting_capital) * 100, 2)
    best      = trades_df.loc[trades_df['P&L'].idxmax()]
    worst     = trades_df.loc[trades_df['P&L'].idxmin()]

    equity_df['Peak']     = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = ((equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak'] * 100)
    max_dd = round(equity_df['Drawdown'].min(), 2)

    return {
        "Total Trades":  len(trades_df),
        "Win Rate":      f"{win_rate}%",
        "Total P&L":     f"₹{total_pnl:,}",
        "Total Return":  f"{total_ret}%",
        "Best Trade":    f"₹{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":   f"₹{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":  f"{max_dd}%",
        "Final Capital": f"₹{round(capital):,}",
    }, equity_df, trades_df
