# ================================================
# FILE: strategies/indicators.py
# PURPOSE: Calculate technical indicators
#          MA20 and RSI for any stock data
# ================================================

import pandas as pd

def calculate_ma20(data):
    """
    Moving Average of last 20 days.
    Tells us the trend direction.
    """
    # Calculate 20-day rolling average of closing price
    data['MA20'] = data['Close'].rolling(window=20).mean().round(2)
    return data


def calculate_rsi(data, period=14):
    """
    RSI - Relative Strength Index.
    Tells us if stock is overbought or oversold.
    Period = 14 days is the standard setting.
    """
    # Calculate daily price change
    delta = data['Close'].diff()

    # Separate gains and losses
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # Calculate average gain and loss over 14 days
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    # Calculate RS (Relative Strength)
    rs = avg_gain / avg_loss

    # Calculate RSI from RS
    data['RSI'] = (100 - (100 / (1 + rs))).round(2)

    return data


def get_signal(row):
    """
    Generate a simple signal based on
    MA20 and RSI values.
    Returns: BUY, SELL, or HOLD
    """
    # Skip if indicators not yet calculated
    if pd.isna(row['MA20']) or pd.isna(row['RSI']):
        return "WAIT"

    price = row['Close']
    ma20  = row['MA20']
    rsi   = row['RSI']

    # BUY signal conditions:
    # Price is above MA20 (uptrend) AND RSI is not overbought
    if price > ma20 and rsi < 70:
        return "BUY 🟢"

    # SELL signal conditions:
    # Price is below MA20 (downtrend) AND RSI is not oversold
    elif price < ma20 and rsi > 30:
        return "SELL 🔴"

    # Everything else — stay out
    else:
        return "HOLD 🟡"


def analyze_stock(data):
    """
    Run all indicators on a stock's data
    and return the enriched dataframe.
    """
    data = calculate_ma20(data)
    data = calculate_rsi(data)

    # Apply signal to each row
    data['Signal'] = data.apply(get_signal, axis=1)

    return data