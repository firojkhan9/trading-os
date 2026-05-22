# ================================================
# FILE: strategies/bollinger_strategy.py
# PURPOSE: Bollinger Bands Strategy
#          UPDATED: Trailing stop, wider stop loss,
#          higher profit target, RSI confirmation
# ================================================

import pandas as pd

BB_PERIOD      = 20
BB_STD_DEV     = 2
RSI_PERIOD     = 14
RSI_OVERSOLD   = 35
RSI_OVERBOUGHT = 65

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


def calculate_rsi(data, period=14):
    delta    = data['Close'].diff()
    gain     = delta.where(delta > 0, 0)
    loss     = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs       = avg_gain / avg_loss
    data['BB_RSI'] = (100 - (100 / (1 + rs))).round(2)
    return data


def calculate_bollinger_bands(data):
    data['BB_Middle'] = data['Close'].rolling(window=BB_PERIOD).mean().round(2)
    rolling_std       = data['Close'].rolling(window=BB_PERIOD).std()
    data['BB_Upper']  = (data['BB_Middle'] + (BB_STD_DEV * rolling_std)).round(2)
    data['BB_Lower']  = (data['BB_Middle'] - (BB_STD_DEV * rolling_std)).round(2)
    data['BB_Width']  = ((data['BB_Upper'] - data['BB_Lower']) / data['BB_Middle'] * 100).round(3)
    data['BB_Pct']    = ((data['Close'] - data['BB_Lower']) / (data['BB_Upper'] - data['BB_Lower'])).round(3)
    data = calculate_rsi(data, RSI_PERIOD)
    return data


def get_bollinger_signal(row):
    if pd.isna(row['BB_Upper']) or pd.isna(row['BB_RSI']):
        return "WAIT"

    price = row['Close']
    upper = row['BB_Upper']
    lower = row['BB_Lower']
    rsi   = row['BB_RSI']

    if price <= lower and rsi <= RSI_OVERSOLD:
        return "BUY 🟢"
    elif price >= upper and rsi >= RSI_OVERBOUGHT:
        return "SELL 🔴"
    elif price <= lower:
        return "WATCH 🟡"
    elif price >= upper:
        return "CAUTION 🟠"
    else:
        return "HOLD ⚪"


def analyze_bollinger(data):
    data = calculate_bollinger_bands(data)
    data['BB_Signal'] = data.apply(get_bollinger_signal, axis=1)
    return data


def get_bollinger_summary(data):
    latest = data.iloc[-1]

    upper  = round(float(latest['BB_Upper']), 2)
    lower  = round(float(latest['BB_Lower']), 2)
    middle = round(float(latest['BB_Middle']), 2)
    width  = round(float(latest['BB_Width']), 2)
    bb_pct = round(float(latest['BB_Pct']), 3)
    rsi    = round(float(latest['BB_RSI']), 2)
    signal = latest['BB_Signal']

    recent_width = data['BB_Width'].tail(20).mean()
    squeeze = "🔥 SQUEEZE!" if width < (recent_width * 0.75) else "Normal"

    if bb_pct >= 1.0:
        position = "Above Upper Band ⚠️"
    elif bb_pct >= 0.8:
        position = "Near Upper Band 🔴"
    elif bb_pct >= 0.5:
        position = "Upper Half 🟡"
    elif bb_pct >= 0.2:
        position = "Lower Half 🟡"
    elif bb_pct >= 0.0:
        position = "Near Lower Band 🟢"
    else:
        position = "Below Lower Band ⚠️"

    return {
        "Upper Band":  f"₹{upper}",
        "Middle Band": f"₹{middle}",
        "Lower Band":  f"₹{lower}",
        "Band Width":  f"{width}%",
        "RSI":         f"{rsi}",
        "Signal":      signal,
        "Position":    position,
        "Squeeze":     squeeze,
    }


def run_bollinger_backtest(data, starting_capital=100000):
    """
    Bollinger Bands backtest with trailing stop.
    """
    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    for date, row in data.iterrows():
        if pd.isna(row['BB_Upper']) or pd.isna(row['BB_RSI']):
            equity_curve.append({"Date": date, "Equity": round(capital, 2)})
            continue

        price  = float(row['Close'])
        signal = row['BB_Signal']

        # ── BUY on confirmed signal ───────────────
        if signal == 'BUY 🟢' and position is None:
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
            elif signal == 'SELL 🔴':
                exit_reason = "UPPER BAND + RSI"
            elif float(row['Close']) >= float(row['BB_Middle']) and change_pct > 0.03:
                exit_reason = "MIDDLE BAND EXIT"

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
