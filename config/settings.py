# ================================================
# FILE: config/settings.py
# PURPOSE: Central settings for entire Trading OS
#          Works on both laptop and cloud
# ================================================

import os

# ── Detect if running on cloud or locally ────────
# On cloud there is no D: drive
# This automatically detects which environment

# Base directory — where all files live
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Folder paths ──────────────────────────────────
DATA_DIR      = os.path.join(BASE_DIR, "data")
LOGS_DIR      = os.path.join(BASE_DIR, "logs")
STRATEGIES_DIR= os.path.join(BASE_DIR, "strategies")
PORTFOLIO_DIR = os.path.join(BASE_DIR, "portfolio")
CONFIG_DIR    = os.path.join(BASE_DIR, "config")

# ── File paths ────────────────────────────────────
SIGNAL_LOG_FILE    = os.path.join(LOGS_DIR, "signal_log.csv")
TRADES_FILE        = os.path.join(LOGS_DIR, "paper_trades.csv")
PORTFOLIO_FILE     = os.path.join(LOGS_DIR, "paper_portfolio.csv")

# ── Trading settings ──────────────────────────────
STARTING_CAPITAL   = 100000   # ₹1,00,000
MAX_POSITION_PCT   = 0.10     # 10% max per stock
MAX_OPEN_POSITIONS = 5        # Max 5 stocks at once
STOP_LOSS_PCT      = 0.03     # 3% stop loss
TARGET_PROFIT_PCT  = 0.06     # 6% profit target
BROKERAGE_PCT      = 0.001    # 0.1% brokerage

# ── Watchlist ─────────────────────────────────────
WATCHLIST = {
    "RELIANCE":   "RELIANCE.NS",
    "TCS":        "TCS.NS",
    "HDFCBANK":   "HDFCBANK.NS",
    "INFY":       "INFY.NS",
    "ICICIBANK":  "ICICIBANK.NS",
    "HINDUNILVR": "HINDUNILVR.NS",
    "SBIN":       "SBIN.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "ITC":        "ITC.NS",
    "KOTAKBANK":  "KOTAKBANK.NS",
}

# ── Create folders if they don't exist ───────────
# This runs automatically when settings.py is imported
for folder in [DATA_DIR, LOGS_DIR]:
    os.makedirs(folder, exist_ok=True)