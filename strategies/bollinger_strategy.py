# ================================================
# FILE: strategies/bollinger_strategy.py
# PURPOSE: Bollinger Bands Strategy
#          Uses price deviation from MA20
#          IMPROVED: RSI confirmation filter added
#          to reduce false signals
# ================================================

import pandas as pd

# ── Strategy Settings ─────────────────────────────
BB_PERIOD      = 20   # Moving average period (20 days)
BB_STD_DEV     = 2    # Number of standard deviations
RSI_PERIOD     = 14   # RSI period for confirmation
RSI_OVERSOLD   = 35   # RSI below this = oversold = confirm BUY
RSI_OVERBOUGHT = 65   # RSI above this = overbought = confirm SELL


def calculate_rsi(data, period=14):
    """
    Calculate RSI for confirmation filter.
    Same logic as indicators.py.
    """
    delta    = data['Close'].diff()
    gain     = delta.where(delta > 0, 0)
    loss     = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs       = avg_gain / avg_loss
    data['BB_RSI'] = (100 - (100 / (1 + rs))).round(2)
    return data


def calculate_bollinger_bands(data):
    """
    Calculate Bollinger Bands for a stock.

    Adds these columns to the dataframe:
    - BB_Middle : 20-day moving average
    - BB_Upper  : Middle + (2 x standard deviation)
    - BB_Lower  : Middle - (2 x standard deviation)
    - BB_Width  : How wide the bands are (volatility)
    - BB_Pct    : Where price sits within bands (0=lower, 1=upper)
    - BB_RSI    : RSI for confirmation
    """

    # ── Middle Band = 20-day moving average ───────
    data['BB_Middle'] = data['Close'].rolling(window=BB_PERIOD).mean().round(2)

    # ── Standard deviation of price ───────────────
    rolling_std = data['Close'].rolling(window=BB_PERIOD).std()

    # ── Upper and Lower Bands ─────────────────────
    data['BB_Upper'] = (data['BB_Middle'] + (BB_STD_DEV * rolling_std)).round(2)
    data['BB_Lower'] = (data['BB_Middle'] - (BB_STD_DEV * rolling_std)).round(2)

    # ── Band Width ────────────────────────────────
    # Wider = more volatile | Narrower = calm market
    data['BB_Width'] = (
        (data['BB_Upper'] - data['BB_Lower']) / data['BB_Middle'] * 100
    ).round(3)

    # ── %B Indicator ──────────────────────────────
    # 0.0 = price at lower band
    # 0.5 = price at middle band
    # 1.0 = price at upper band
    data['BB_Pct'] = (
        (data['Close'] - data['BB_Lower']) /
        (data['BB_Upper'] - data['BB_Lower'])
    ).round(3)

    # ── Add RSI for confirmation ───────────────────
    data = calculate_rsi(data, RSI_PERIOD)

    return data


def get_bollinger_signal(row):
    """
    Generate trading signal using Bollinger Bands
    WITH RSI confirmation filter.

    BUY     = price at lower band AND RSI oversold
    SELL    = price at upper band AND RSI overbought
    WATCH   = band touched but RSI not confirming yet
    CAUTION = upper band touched but RSI not confirming
    HOLD    = price within bands
    """

    # Skip rows where indicators not yet calculated
    if pd.isna(row['BB_Upper']) or pd.isna(row['BB_RSI']):
        return "WAIT"

    price = row['Close']
    upper = row['BB_Upper']
    lower = row['BB_Lower']
    rsi   = row['BB_RSI']

    # ── BUY: band touch + RSI confirmation ────────
    if price <= lower and rsi <= RSI_OVERSOLD:
        return "BUY 🟢"

    # ── SELL: band touch + RSI confirmation ───────
    elif price >= upper and rsi >= RSI_OVERBOUGHT:
        return "SELL 🔴"

    # ── Weak signals (band touch without RSI) ─────
    elif price <= lower:
        return "WATCH 🟡"      # Lower band touched, RSI not confirming yet

    elif price >= upper:
        return "CAUTION 🟠"    # Upper band touched, RSI not confirming yet

    # ── Hold ──────────────────────────────────────
    else:
        return "HOLD ⚪"


def analyze_bollinger(data):
    """
    Run full Bollinger Bands analysis on stock data.
    Returns enriched dataframe with all indicators and signals.
    """
    data = calculate_bollinger_bands(data)
    data['BB_Signal'] = data.apply(get_bollinger_signal, axis=1)
    return data


def get_bollinger_summary(data):
    """
    Get latest Bollinger Bands summary for dashboard.
    Returns a clean dictionary.
    """
    latest = data.iloc[-1]

    upper  = round(float(latest['BB_Upper']), 2)
    lower  = round(float(latest['BB_Lower']), 2)
    middle = round(float(latest['BB_Middle']), 2)
    width  = round(float(latest['BB_Width']), 2)
    bb_pct = round(float(latest['BB_Pct']), 3)
    rsi    = round(float(latest['BB_RSI']), 2)
    signal = latest['BB_Signal']

    # ── Squeeze Detection ─────────────────────────
    # Bands much narrower than usual = big move coming soon
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
    Backtest Bollinger Bands + RSI confirmation strategy.
    Only trades when BOTH band touch AND RSI confirm.
    Returns summary, equity curve, and trade list.
    """
    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    brokerage    = 0.001  # 0.1% per trade
    stop_loss    = 0.03   # 3% stop loss
    target       = 0.06   # 6% profit target
    max_position = 0.10   # Max 10% of capital per trade

    for date, row in data.iterrows():

        # Skip rows without indicator values
        if pd.isna(row['BB_Upper']) or pd.isna(row['BB_RSI']):
            equity_curve.append({
                "Date":   date,
                "Equity": round(capital, 2)
            })
            continue

        price  = float(row['Close'])
        signal = row['BB_Signal']

        # ── BUY: confirmed signal only ─────────────
        if signal == 'BUY 🟢' and position is None:
            spend    = capital * max_position
            quantity = int(spend // price)

            if quantity > 0:
                cost     = round(quantity * price * (1 + brokerage), 2)
                capital -= cost
                position = {
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

            # Stop loss hit
            if change_pct <= -stop_loss:
                exit_reason = "STOP LOSS"

            # Profit target hit
            elif change_pct >= target:
                exit_reason = "TARGET HIT"

            # Price hit upper band with RSI confirmation
            elif signal == 'SELL 🔴':
                exit_reason = "UPPER BAND + RSI"

            # Price crossed back above middle band with some profit
            # This is a good safe exit even before upper band
            elif float(row['Close']) >= float(row['BB_Middle']) and change_pct > 0.02:
                exit_reason = "MIDDLE BAND EXIT"

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

        # ── Track equity every day ────────────────
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
    equity_df['Drawdown'] = (
        (equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak'] * 100
    )
    max_dd = round(equity_df['Drawdown'].min(), 2)

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