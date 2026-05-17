# ============================================
# FILE: data/fetch_stock.py
# PURPOSE: Download real stock data from NSE
#          and save it to a CSV file
# ============================================

import yfinance as yf
import pandas as pd
from datetime import datetime

# The stock we want to fetch
# .NS means National Stock Exchange (India)
STOCK = "RELIANCE.NS"

print("Fetching data for Reliance Industries...")
print("Please wait...\n")

# Download last 30 days of daily price data
data = yf.download(
    tickers=STOCK,
    period="30d",      # Last 30 days
    interval="1d",     # Daily prices
    progress=False     # Hide download bar
)

# Show the last 5 trading days
print("Last 5 trading days:")
print(data[['Open', 'High', 'Low', 'Close', 'Volume']].tail(5).round(2))

# ── NEW: Save data to a CSV file ──────────────────────────

# Create a filename with today's date
# Example: RELIANCE_2025-05-17.csv
today = datetime.today().strftime('%Y-%m-%d')
filename = f"data/RELIANCE_{today}.csv"

# Save the data
data.to_csv(filename)

print(f"\n✅ Data saved to: {filename}")
print("Check your data folder — you'll see the file there!")