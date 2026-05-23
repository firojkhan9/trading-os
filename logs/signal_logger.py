# ================================================
# FILE: logs/signal_logger.py
# PURPOSE: Record every trading signal
#          PRIMARY: Supabase database (permanent)
#          FALLBACK: CSV file (local only)
#
# IMPORTANT:
#   Signal logging happens on every page load.
#   Supabase write is fast (~200ms) and reliable.
#   If Supabase fails, falls back to CSV silently.
# ================================================

import pandas as pd
import os
from datetime import datetime

# ── Supabase connection ───────────────────────────
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.supabase_client import get_client

# ── CSV fallback path ─────────────────────────────
try:
    from config.settings import SIGNAL_LOG_FILE
    LOG_FILE = SIGNAL_LOG_FILE
except Exception:
    LOG_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", "signal_log.csv"
    )

STARTING_CAPITAL = 100000


def log_signal(stock_name, close, ma20, rsi, signal):
    """
    Save one signal entry.
    Tries Supabase first, falls back to CSV.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    entry = {
        "Timestamp": timestamp,
        "Stock":     stock_name,
        "Close":     round(float(close), 2),
        "MA20":      round(float(ma20), 2),
        "RSI":       round(float(rsi), 2),
        "Signal":    signal,
    }

    # ── Try Supabase first ────────────────────────
    client = get_client()
    if client:
        try:
            client.table("signal_log").insert({
                "timestamp": timestamp,
                "stock":     stock_name,
                "close":     round(float(close), 2),
                "ma20":      round(float(ma20), 2),
                "rsi":       round(float(rsi), 2),
                "signal":    signal,
            }).execute()
            return entry
        except Exception as e:
            print(f"⚠️ Supabase signal log failed: {e} — falling back to CSV")

    # ── CSV fallback ──────────────────────────────
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        entry_df = pd.DataFrame([entry])
        if os.path.exists(LOG_FILE):
            entry_df.to_csv(LOG_FILE, mode='a', header=False, index=False)
        else:
            entry_df.to_csv(LOG_FILE, mode='w', header=True, index=False)
    except Exception as e:
        print(f"⚠️ CSV signal log also failed: {e}")

    return entry


def load_signal_log():
    """
    Load full signal history.
    Tries Supabase first, falls back to CSV.
    """
    client = get_client()

    # ── Try Supabase first ────────────────────────
    if client:
        try:
            response = (
                client.table("signal_log")
                .select("*")
                .order("timestamp", desc=True)
                .limit(500)   # Last 500 signals
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                # Rename columns to match old format
                df = df.rename(columns={
                    "timestamp": "Timestamp",
                    "stock":     "Stock",
                    "close":     "Close",
                    "ma20":      "MA20",
                    "rsi":       "RSI",
                    "signal":    "Signal",
                })
                # Keep only display columns
                cols = ["Timestamp", "Stock", "Close", "MA20", "RSI", "Signal"]
                df = df[[c for c in cols if c in df.columns]]
                return df
        except Exception as e:
            print(f"⚠️ Supabase signal load failed: {e} — falling back to CSV")

    # ── CSV fallback ──────────────────────────────
    if os.path.exists(LOG_FILE):
        try:
            return pd.read_csv(LOG_FILE)
        except Exception:
            pass

    return pd.DataFrame(columns=["Timestamp", "Stock", "Close", "MA20", "RSI", "Signal"])


def get_latest_signals():
    """Get most recent signal per stock."""
    df = load_signal_log()
    if df.empty:
        return df
    latest = df.sort_values('Timestamp').groupby('Stock').last().reset_index()
    return latest
