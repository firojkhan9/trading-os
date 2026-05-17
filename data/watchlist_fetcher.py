# ================================================
# FILE: data/watchlist_fetcher.py
# PURPOSE: Fetch data for 10 Indian stocks at once
#          and save each to its own CSV file
# ================================================

import yfinance as yf
import pandas as pd
from datetime import datetime

# ── Our watchlist of 10 NSE stocks ──────────────
WATCHLIST = {
    "RELIANCE":     "RELIANCE.NS",
    "TCS":          "TCS.NS",
    "HDFCBANK":     "HDFCBANK.NS",
    "INFY":         "INFY.NS",
    "ICICIBANK":    "ICICIBANK.NS",
    "HINDUNILVR":   "HINDUNILVR.NS",
    "SBIN":         "SBIN.NS",
    "BHARTIARTL":   "BHARTIARTL.NS",
    "ITC":          "ITC.NS",
    "KOTAKBANK":    "KOTAKBANK.NS",
}

# Today's date for filenames
today = datetime.today().strftime('%Y-%m-%d')

# This will store one summary row per stock
summary = []

print("=" * 55)
print("📡 Trading OS — Watchlist Fetcher")
print("=" * 55)

# ── Loop through each stock one by one ──────────
for name, symbol in WATCHLIST.items():

    print(f"\n⏳ Fetching {name} ({symbol})...")

    try:
        # Download 30 days of daily data
        data = yf.download(
            tickers=symbol,
            period="30d",
            interval="1d",
            progress=False
        )

        # Skip if no data came back
        if data.empty:
            print(f"  ⚠️  No data for {name} — skipping")
            continue

        # ── NEW FIX: Flatten multi-level columns ──
        # yfinance now returns columns like ('Close', 'RELIANCE.NS')
        # We simplify them back to just 'Close', 'Open' etc.
        data.columns = [col[0] for col in data.columns]

        # Save individual stock CSV
        filename = f"data/{name}_{today}.csv"
        data.to_csv(filename)

        # Get latest close price
        latest_close = round(float(data['Close'].iloc[-1]), 2)

        # Get close price from 30 days ago
        oldest_close = round(float(data['Close'].iloc[0]), 2)

        # Calculate 30 day % change
        change_pct = round(((latest_close - oldest_close) / oldest_close) * 100, 2)

        # Get average daily volume
        avg_volume = int(data['Volume'].mean())

        # Add to summary table
        summary.append({
            "Stock":        name,
            "Latest Close": f"₹{latest_close}",
            "30D Change":   f"{change_pct}%",
            "Avg Volume":   f"{avg_volume:,}",
            "Data Points":  len(data),
        })

        print(f"  ✅ Done — ₹{latest_close} ({change_pct}% in 30 days)")

    except Exception as e:
        print(f"  ❌ Error fetching {name}: {e}")

# ── Print final summary table ────────────────────
print("\n")
print("=" * 55)
print("📊 Watchlist Summary")
print("=" * 55)

summary_df = pd.DataFrame(summary)
print(summary_df.to_string(index=False))

print("\n✅ All done! Check your data folder for CSV files.")