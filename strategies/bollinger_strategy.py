# ================================================
# FILE: strategies/bollinger_strategy.py
# PURPOSE: Bollinger Bands Strategy
#          Uses price deviation from MA20
#          to find overbought/oversold conditions
# ================================================

import pandas as pd

# ── Strategy Settings ─────────────────────────────
BB_PERIOD   = 20    # Moving average period (20 days)
BB_STD_DEV  = 2     # Number of standard deviations
#
# Standard deviation measures how much price
# is "jumping around" vs its average.
# 2 standard deviations captures ~95% of price moves
# so anything outside the bands is truly unusual.


def calculate_bollinger_bands(data):
    """
    Calculate Bollinger Bands for a stock.

    Adds 3 new columns to the dataframe:
    - BB_Middle : 20-day moving average
    - BB_Upper  : Middle + (2 x standard deviation)
    - BB_Lower  : Middle - (2 x standard deviation)
    - BB_Width  : How wide the bands are (volatility indicator)
    - BB_Pct    : Where price sits within the bands (0=lower, 1=upper)
    """

    # ── Middle Band = simple 20-day moving average ─
    data['BB_Middle'] = data['Close'].rolling(window=BB_PERIOD).mean().round(2)

    # ── Standard deviation of price over 20 days ──
    rolling_std = data['Close'].rolling(window=BB_PERIOD).std()

    # ── Upper and Lower Bands ─────────────────────
    data['BB_Upper'] = (data['BB_Middle'] + (BB_STD_DEV * rolling_std)).round(2)
    data['BB_Lower'] = (data['BB_Middle'] - (BB_STD_DEV * rolling_std)).round(2)

    # ── Band Width ────────────────────────────────
    # How far apart are the bands?
    # Wider = more volatile market
    # Narrower = calm market (often precedes a big move)
    data['BB_Width'] = (
        (data['BB_Upper'] - data['BB_Lower']) / data['BB_Middle'] * 100
    ).round(3)

    # ── %B Indicator ──────────────────────────────
    # Where is the price within the bands?
    # 0.0 = price is at lower band
    # 0.5 = price is at middle band
    # 1.0 = price is at upper band
    # >1.0 = price is above upper band (very overbought)
    # <0.0 = price is below lower band (very oversold)
    data['BB_Pct'] = (
        (data['Close'] - data['BB_Lower']) /
        (data['BB_Upper'] - data['BB_Lower'])
    ).round(3)

    return data


def get_bollinger_signal(row):
    """
    Generate a trading signal based on
    Bollinger Bands position.

    Returns: BUY, SELL, or HOLD
    """

    # Skip rows where bands not yet calculated
    if pd.isna(row['BB_Upper']) or pd.isna(row['BB_Lower']):
        return "WAIT"

    price  = row['Close']
    upper  = row['BB_Upper']
    lower  = row['BB_Lower']
    middle = row['BB_Middle']
    bb_pct = row['BB_Pct']

    # ── BUY Signal ────────────────────────────────
    # Price has touched or gone below the lower band
    # This means price is unusually low = potential bounce
    if price <= lower:
        return "BUY 🟢"

    # ── SELL Signal ───────────────────────────────
    # Price has touched or gone above the upper band
    # This means price is unusually high = potential pullback
    elif price >= upper:
        return "SELL 🔴"

    # ── HOLD ─────────────────────────────────────
    else:
        return "HOLD 🟡"


def analyze_bollinger(data):
    """
    Run Bollinger Bands on stock data.
    Returns enriched dataframe with signals.
    """
    data = calculate_bollinger_bands(data)
    data['BB_Signal'] = data.apply(get_bollinger_signal, axis=1)
    return data


def get_bollinger_summary(data):
    """
    Get latest Bollinger Bands summary.
    Returns a clean dictionary for dashboard display.
    """
    latest = data.iloc[-1]

    price  = round(float(latest['Close']), 2)
    upper  = round(float(latest['BB_Upper']), 2)
    lower  = round(float(latest['BB_Lower']), 2)
    middle = round(float(latest['BB_Middle']), 2)
    width  = round(float(latest['BB_Width']), 2)
    bb_pct = round(float(latest['BB_Pct']), 3)
    signal = latest['BB_Signal']

    # ── Squeeze Detection ─────────────────────────
    # A "squeeze" is when bands get very narrow
    # It means a big price move is coming soon
    # We detect it by comparing current width to recent average
    recent_width = data['BB_Width'].tail(20).mean()
    squeeze = "🔥 SQUEEZE!" if width < (recent_width * 0.75) else "Normal"

    # ── Position description ──────────────────────
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
        "Upper Band":   f"₹{upper}",
        "Middle Band":  f"₹{middle}",
        "Lower Band":   f"₹{lower}",
        "Band Width":   f"{width}%",
        "Signal":       signal,
        "Position":     position,
        "Squeeze":      squeeze,
    }


def run_bollinger_backtest(data, starting_capital=100000):
    """
    Backtest Bollinger Bands strategy.
    Simulates trades based on band touch signals.
    Returns summary, equity curve, and trade list.
    """
    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    brokerage    = 0.001   # 0.1% per trade
    stop_loss    = 0.03    # 3% stop loss
    target       = 0.06    # 6% profit target
    max_position = 0.10    # Max 10% of capital per trade

    for date, row in data.iterrows():

        # Skip rows without indicator values
        if pd.isna(row['BB_Upper']):
            equity_curve.append({
                "Date":   date,
                "Equity": round(capital, 2)
            })
            continue

        price  = float(row['Close'])
        signal = row['BB_Signal']

        # ── BUY when price hits lower band ────────
        if signal == 'BUY 🟢' and position is None:
            spend    = capital * max_position
            quantity = int(spend // price)

            if quantity > 0:
                cost      = round(quantity * price * (1 + brokerage), 2)
                capital  -= cost
                position  = {
                    "buy_date":  date,
                    "buy_price": price,
                    "quantity":  quantity,
                    "cost":      cost
                }

        # ── Check exits ───────────────────────────
        elif position is not None:
            buy_price  = position['buy_price']
            quantity   = position['quantity']
            cost       = position['cost']
            change_pct = (price - buy_price) / buy_price

            exit_reason = None

            # Stop loss
            if change_pct <= -stop_loss:
                exit_reason = "STOP LOSS"

            # Target hit
            elif change_pct >= target:
                exit_reason = "TARGET HIT"

            # Price hit upper band — take profit
            elif signal == 'SELL 🔴':
                exit_reason = "UPPER BAND HIT"

            # ── Execute sell ──────────────────────
            if exit_reason:
                proceeds = round(quantity * price * (1 - brokerage), 2)
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

        # ── Track equity ──────────────────────────
        if position is not None:
            total = capital + (position['quantity'] * price)
        else:
            total = capital

        equity_curve.append({
            "Date":   date,
            "Equity": round(total, 2)
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
        }, equity_df, trades_df

    wins      = trades_df[trades_df['P&L'] >= 0]
    win_rate  = round((len(wins) / len(trades_df)) * 100, 2)
    total_pnl = round(trades_df['P&L'].sum(), 2)
    total_ret = round(((capital - starting_capital) / starting_capital) * 100, 2)

    equity_df['Peak']     = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = ((equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak'] * 100)
    max_dd    = round(equity_df['Drawdown'].min(), 2)

    best  = trades_df.loc[trades_df['P&L'].idxmax()]
    worst = trades_df.loc[trades_df['P&L'].idxmin()]

    summary = {
        "Total Trades":  len(trades_df),
        "Win Rate":      f"{win_rate}%",
        "Total P&L":     f"₹{total_pnl:,}",
        "Total Return":  f"{total_ret}%",
        "Best Trade":    f"₹{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":   f"₹{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":  f"{max_dd}%",
        "Final Capital": f"₹{round(capital):,}",
    }

    return summary, equity_df, trades_df