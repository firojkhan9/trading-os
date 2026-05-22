# ================================================
# FILE: strategies/macd_strategy.py
# PURPOSE: MACD Strategy
#          UPDATED: Trailing stop, wider stop loss,
#          higher profit target, smarter momentum exit
# ================================================

import pandas as pd

MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.strategy_settings import (
        STOP_LOSS_PCT, TARGET_PROFIT_PCT,
        USE_TRAILING_STOP, TRAILING_STOP_PCT,
        MAX_POSITION_PCT, BROKERAGE_PCT,
        MACD_MOMENTUM_EXIT,
    )
except ImportError:
    STOP_LOSS_PCT      = 0.06
    TARGET_PROFIT_PCT  = 0.15
    USE_TRAILING_STOP  = True
    TRAILING_STOP_PCT  = 0.04
    MAX_POSITION_PCT   = 0.10
    BROKERAGE_PCT      = 0.001
    MACD_MOMENTUM_EXIT = 0.03


def calculate_macd(data):
    data['EMA12']       = data['Close'].ewm(span=MACD_FAST,   adjust=False).mean().round(4)
    data['EMA26']       = data['Close'].ewm(span=MACD_SLOW,   adjust=False).mean().round(4)
    data['MACD']        = (data['EMA12'] - data['EMA26']).round(4)
    data['MACD_Signal'] = data['MACD'].ewm(span=MACD_SIGNAL,  adjust=False).mean().round(4)
    data['MACD_Hist']   = (data['MACD'] - data['MACD_Signal']).round(4)
    return data


def get_macd_signal(data):
    data['Prev_MACD']   = data['MACD'].shift(1)
    data['Prev_Signal'] = data['MACD_Signal'].shift(1)

    macd   = data['MACD']
    signal = data['MACD_Signal']
    prev_m = data['Prev_MACD']
    prev_s = data['Prev_Signal']

    data['MACD_Crossover'] = 'HOLD 🟡'
    data.loc[(prev_m <= prev_s) & (macd > signal), 'MACD_Crossover'] = 'BUY 🟢'
    data.loc[(prev_m >= prev_s) & (macd < signal), 'MACD_Crossover'] = 'SELL 🔴'

    data['MACD_Momentum'] = 'NEUTRAL'
    data.loc[macd > signal, 'MACD_Momentum'] = 'BULLISH 📈'
    data.loc[macd < signal, 'MACD_Momentum'] = 'BEARISH 📉'

    data['Prev_Hist']     = data['MACD_Hist'].shift(1)
    data['MACD_Hist_Dir'] = 'FLAT'
    data.loc[data['MACD_Hist'] > data['Prev_Hist'], 'MACD_Hist_Dir'] = 'GROWING 📶'
    data.loc[data['MACD_Hist'] < data['Prev_Hist'], 'MACD_Hist_Dir'] = 'SHRINKING 📉'

    data = data.drop(['Prev_MACD', 'Prev_Signal', 'Prev_Hist'], axis=1)
    return data


def analyze_macd(data):
    data = calculate_macd(data)
    data = get_macd_signal(data)
    return data


def get_macd_summary(data):
    latest    = data.iloc[-1]
    macd      = round(float(latest['MACD']), 4)
    signal    = round(float(latest['MACD_Signal']), 4)
    hist      = round(float(latest['MACD_Hist']), 4)
    crossover = latest['MACD_Crossover']
    momentum  = latest['MACD_Momentum']
    hist_dir  = latest['MACD_Hist_Dir']

    cross_signals = data[data['MACD_Crossover'] != 'HOLD 🟡']
    days_since    = 0
    if not cross_signals.empty:
        last_cross_idx = cross_signals.index[-1]
        days_since     = len(data) - data.index.get_loc(last_cross_idx) - 1

    return {
        "MACD Line":        f"{macd}",
        "Signal Line":      f"{signal}",
        "Histogram":        f"{hist}",
        "Signal":           crossover,
        "Momentum":         momentum,
        "Histogram Trend":  hist_dir,
        "Days Since Cross": days_since,
    }


def run_macd_backtest(data, starting_capital=100000):
    """
    MACD backtest with trailing stop.
    Smarter momentum exit — only exits after 3% loss
    not 1%, to avoid exiting normal pullbacks.
    """
    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    for date, row in data.iterrows():
        if pd.isna(row['MACD']) or pd.isna(row['MACD_Signal']):
            equity_curve.append({"Date": date, "Equity": round(capital, 2)})
            continue

        price     = float(row['Close'])
        crossover = row['MACD_Crossover']
        momentum  = row['MACD_Momentum']

        # ── BUY on bullish crossover ───────────────
        if crossover == 'BUY 🟢' and position is None:
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
                }

        elif position is not None:
            buy_price  = position['buy_price']
            quantity   = position['quantity']
            cost       = position['cost']
            change_pct = (price - buy_price) / buy_price

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
            elif crossover == 'SELL 🔴':
                exit_reason = "MACD CROSSOVER"
            # Only exit on bearish momentum after meaningful loss
            # Prevents exiting on normal 1-2% pullbacks
            elif momentum == 'BEARISH 📉' and change_pct < -MACD_MOMENTUM_EXIT:
                exit_reason = "BEARISH MOMENTUM"

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
