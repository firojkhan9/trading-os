# ================================================
# FILE: logs/signal_logger.py
# PURPOSE: Record every trading signal to CSV
#          so we have a full audit trail
# ================================================

import pandas as pd
import os
from datetime import datetime

# ── Where we save the signal log ─────────────────
LOG_FILE = "logs/signal_log.csv"

def log_signal(stock_name, close, ma20, rsi, signal):
    """
    Save one signal entry to our log file.
    Called every time we analyze a stock.
    """

    # Create a new log entry as a dictionary
    entry = {
        "Timestamp":  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Stock":      stock_name,
        "Close":      round(float(close), 2),
        "MA20":       round(float(ma20), 2),
        "RSI":        round(float(rsi), 2),
        "Signal":     signal,
    }

    # Convert to a single-row dataframe
    entry_df = pd.DataFrame([entry])

    # If log file exists — append to it
    # If not — create it with headers
    if os.path.exists(LOG_FILE):
        entry_df.to_csv(LOG_FILE, mode='a', header=False, index=False)
    else:
        entry_df.to_csv(LOG_FILE, mode='w', header=True, index=False)

    return entry


def load_signal_log():
    """
    Load the full signal history from CSV.
    Returns empty dataframe if no log exists yet.
    """
    if os.path.exists(LOG_FILE):
        return pd.read_csv(LOG_FILE)
    else:
        return pd.DataFrame(columns=[
            "Timestamp", "Stock", "Close", "MA20", "RSI", "Signal"
        ])


def get_latest_signals():
    """
    Get only the most recent signal per stock.
    Useful for dashboard summary view.
    """
    df = load_signal_log()

    if df.empty:
        return df

    # Keep only the last signal for each stock
    latest = df.sort_values('Timestamp').groupby('Stock').last().reset_index()
    return latest