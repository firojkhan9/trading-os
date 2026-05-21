# ================================================
# FILE: strategies/macd_strategy.py
# PURPOSE: MACD Strategy
#          Moving Average Convergence Divergence
#          Measures momentum and trend direction
#
# HOW MACD WORKS:
#   MACD Line   = EMA12 - EMA26  (fast - slow)
#   Signal Line = EMA9 of MACD   (smoothed MACD)
#   Histogram   = MACD - Signal  (gap between them)
#
#   BUY  -> MACD crosses ABOVE Signal Line
#   SELL -> MACD crosses BELOW Signal Line
# ================================================

import pandas as pd

# Strategy Settings
MACD_FAST   = 12   # Fast EMA period
MACD_SLOW   = 26   # Slow EMA period
MACD_SIGNAL = 9    # Signal line smoothing period

# Why these numbers?
# 12, 26, 9 are the universally accepted default settings
# Used by traders worldwide for decades


def calculate_macd(data):
    """
    Calculate MACD indicator.

    Adds these columns to the dataframe:
    - EMA12       : 12-day exponential moving average
    - EMA26       : 26-day exponential moving average
    - MACD        : EMA12 - EMA26 (momentum line)
    - MACD_Signal : 9-day EMA of MACD (trigger line)
    - MACD_Hist   : MACD - Signal (histogram bars)
    """

    # Step 1: Calculate fast and slow EMAs
    data['EMA12'] = data['Close'].ewm(
        span=MACD_FAST, adjust=False
    ).mean().round(4)

    data['EMA26'] = data['Close'].ewm(
        span=MACD_SLOW, adjust=False
    ).mean().round(4)

    # Step 2: MACD Line
    # When MACD is positive -> fast EMA above slow EMA -> uptrend
    # When MACD is negative -> fast EMA below slow EMA -> downtrend
    data['MACD'] = (data['EMA12'] - data['EMA26']).round(4)

    # Step 3: Signal Line
    # A smoothed version of MACD
    # Crossovers between MACD and Signal = trade signals
    data['MACD_Signal'] = data['MACD'].ewm(
        span=MACD_SIGNAL, adjust=False
    ).mean().round(4)

    # Step 4: Histogram
    # Positive histogram = MACD above Signal = bullish momentum
    # Negative histogram = MACD below Signal = bearish momentum
    # Growing histogram  = momentum increasing
    # Shrinking histogram = momentum weakening (early warning!)
    data['MACD_Hist'] = (data['MACD'] - data['MACD_Signal']).round(4)

    return data


def get_macd_signal(data):
    """
    Generate MACD crossover signals for each row.

    BUY  = MACD crosses ABOVE Signal Line
    SELL = MACD crosses BELOW Signal Line
    HOLD = No crossover today
    """

    # Previous day values for crossover detection
    data['Prev_MACD']   = data['MACD'].shift(1)
    data['Prev_Signal'] = data['MACD_Signal'].shift(1)

    # Current values
    macd   = data['MACD']
    signal = data['MACD_Signal']
    prev_m = data['Prev_MACD']
    prev_s = data['Prev_Signal']

    # Default = HOLD
    data['MACD_Crossover'] = 'HOLD 🟡'

    # BUY: MACD was below signal yesterday, now above
    buy_condition = (
        (prev_m <= prev_s) &
        (macd > signal)
    )

    # SELL: MACD was above signal yesterday, now below
    sell_condition = (
        (prev_m >= prev_s) &
        (macd < signal)
    )

    data.loc[buy_condition,  'MACD_Crossover'] = 'BUY 🟢'
    data.loc[sell_condition, 'MACD_Crossover'] = 'SELL 🔴'

    # Momentum direction
    # Even when no crossover, tell us the momentum
    data['MACD_Momentum'] = 'NEUTRAL'
    data.loc[macd > signal, 'MACD_Momentum'] = 'BULLISH 📈'
    data.loc[macd < signal, 'MACD_Momentum'] = 'BEARISH 📉'

    # Histogram direction
    # Is momentum growing or shrinking?
    data['Prev_Hist'] = data['MACD_Hist'].shift(1)
    data['MACD_Hist_Dir'] = 'FLAT'
    data.loc[data['MACD_Hist'] > data['Prev_Hist'], 'MACD_Hist_Dir'] = 'GROWING 📶'
    data.loc[data['MACD_Hist'] < data['Prev_Hist'], 'MACD_Hist_Dir'] = 'SHRINKING 📉'

    # Clean up helper columns
    data = data.drop(['Prev_MACD', 'Prev_Signal', 'Prev_Hist'], axis=1)

    return data


def analyze_macd(data):
    """
    Run full MACD analysis on stock data.
    Returns enriched dataframe with all MACD values and signals.
    """
    data = calculate_macd(data)
    data = get_macd_signal(data)
    return data


def get_macd_summary(data):
    """
    Get latest MACD summary for dashboard.
    Returns a clean dictionary.
    """
    latest = data.iloc[-1]

    macd      = round(float(latest['MACD']), 4)
    signal    = round(float(latest['MACD_Signal']), 4)
    hist      = round(float(latest['MACD_Hist']), 4)
    crossover = latest['MACD_Crossover']
    momentum  = latest['MACD_Momentum']
    hist_dir  = latest['MACD_Hist_Dir']

    # Days since last crossover
    cross_signals = data[data['MACD_Crossover'] != 'HOLD 🟡']
    days_since    = 0
    if not cross_signals.empty:
        last_cross_idx = cross_signals.index[-1]
        days_since     = len(data) - data.index.get_loc(last_cross_idx) - 1

    return {
        "MACD Line":       f"{macd}",
        "Signal Line":     f"{signal}",
        "Histogram":       f"{hist}",
        "Signal":          crossover,
        "Momentum":        momentum,
        "Histogram Trend": hist_dir,
        "Days Since Cross":days_since,
    }


def run_macd_backtest(data, starting_capital=100000):
    """
    Backtest MACD crossover strategy.
    Simulates trades based on MACD/Signal crossovers.
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

        # Skip rows where MACD not yet calculated
        if pd.isna(row['MACD']) or pd.isna(row['MACD_Signal']):
            equity_curve.append({
                "Date":   date,
                "Equity": round(capital, 2)
            })
            continue

        price     = float(row['Close'])
        crossover = row['MACD_Crossover']
        momentum  = row['MACD_Momentum']

        # BUY on bullish crossover
        if crossover == 'BUY 🟢' and position is None:
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

        # Check exits
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

            # MACD bearish crossover = trend reversed
            elif crossover == 'SELL 🔴':
                exit_reason = "MACD CROSSOVER"

            # Momentum turned bearish with a small loss
            elif momentum == 'BEARISH 📉' and change_pct < -0.01:
                exit_reason = "BEARISH MOMENTUM"

            # Execute sell
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

        # Track equity every day
        if position is not None:
            total = capital + (position['quantity'] * price)
        else:
            total = capital

        equity_curve.append({
            "Date":   date,
            "Equity": round(total, 2)
        })

    # Performance Summary
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("Date")

    if trades_df.empty:
        return {
            "Total Trades":  0,
            "Win Rate":      "0%",
            "Total P&L":     "0",
            "Total Return":  "0%",
            "Best Trade":    "N/A",
            "Worst Trade":   "N/A",
            "Max Drawdown":  "N/A",
            "Final Capital": f"{round(capital):,}",
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
        "Total P&L":     f"{total_pnl:,}",
        "Total Return":  f"{total_ret}%",
        "Best Trade":    f"{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":   f"{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":  f"{max_dd}%",
        "Final Capital": f"{round(capital):,}",
    }

    return summary, equity_df, trades_df