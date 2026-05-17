# ================================================
# FILE: data/debug.py
# PURPOSE: See exactly what yfinance returns
#          so we can fix the format issue
# ================================================

import yfinance as yf

# Download just one stock
data = yf.download(
    tickers="RELIANCE.NS",
    period="5d",
    interval="1d",
    progress=False
)

# Let's see exactly what we got
print("Data type:", type(data))
print("\nColumn names:", data.columns.tolist())
print("\nLast row:")
print(data.tail(1))
print("\nClose column:")
print(data['Close'])
print("\nType of Close:")
print(type(data['Close'].iloc[-1]))