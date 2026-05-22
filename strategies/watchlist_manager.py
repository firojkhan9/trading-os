# ================================================
# FILE: strategies/watchlist_manager.py
# PURPOSE: Dynamic Watchlist Management
#          Supports both CSV file AND Google Sheets
#
# PRIORITY ORDER:
#   1. Google Sheets (if URL set) — best option
#   2. watchlist.csv at repo root — fallback
#   3. Built-in default list — last resort
#
# GOOGLE SHEET FORMAT (same as CSV):
#   Symbol | Name | Sector | Industry | Active | Priority | Notes
#
# HOW TO SET UP GOOGLE SHEETS:
#   Step 1: Create Google Sheet with above columns
#   Step 2: File > Share > Publish to web > CSV > Copy URL
#   Step 3: Paste URL in WATCHLIST_SHEET_URL below
#   Step 4: git push — done forever
# ================================================

import pandas as pd
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Google Sheet URL ──────────────────────────────
# Paste your published CSV URL here (one-time setup)
# Leave empty "" to use watchlist.csv file instead
WATCHLIST_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRGZnRvmuMoW2V70JIhiVxeZh1-Fc0sFteRwvv6WTV61RvgtYA3Ug6N8a2ONH1CTw5Dre5dGNa_ZtoO/pub?gid=0&single=true&output=csv"
# Example:
# "https://docs.google.com/spreadsheets/d/e/YOUR_ID/pub?output=csv"

# ── Local CSV fallback ────────────────────────────
WATCHLIST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "watchlist.csv"
)

# ── Default watchlist ─────────────────────────────
DEFAULT_WATCHLIST = [
    {"Symbol": "RELIANCE.NS",  "Name": "RELIANCE",   "Sector": "Energy",     "Industry": "Oil & Gas",        "Active": True, "Priority": 1, "Notes": "Largest Indian company"},
    {"Symbol": "TCS.NS",       "Name": "TCS",         "Sector": "Technology", "Industry": "IT Services",      "Active": True, "Priority": 1, "Notes": "Largest IT company"},
    {"Symbol": "HDFCBANK.NS",  "Name": "HDFCBANK",    "Sector": "Finance",    "Industry": "Private Banks",    "Active": True, "Priority": 1, "Notes": "Largest private bank"},
    {"Symbol": "INFY.NS",      "Name": "INFY",        "Sector": "Technology", "Industry": "IT Services",      "Active": True, "Priority": 1, "Notes": "Second largest IT"},
    {"Symbol": "ICICIBANK.NS", "Name": "ICICIBANK",   "Sector": "Finance",    "Industry": "Private Banks",    "Active": True, "Priority": 1, "Notes": "Second largest private bank"},
    {"Symbol": "HINDUNILVR.NS","Name": "HINDUNILVR",  "Sector": "FMCG",       "Industry": "Consumer Goods",   "Active": True, "Priority": 2, "Notes": "Largest FMCG"},
    {"Symbol": "SBIN.NS",      "Name": "SBIN",        "Sector": "Finance",    "Industry": "Public Banks",     "Active": True, "Priority": 2, "Notes": "Largest public bank"},
    {"Symbol": "BHARTIARTL.NS","Name": "BHARTIARTL",  "Sector": "Telecom",    "Industry": "Telecom Services", "Active": True, "Priority": 2, "Notes": "Largest telecom"},
    {"Symbol": "ITC.NS",       "Name": "ITC",         "Sector": "FMCG",       "Industry": "Diversified FMCG", "Active": True, "Priority": 2, "Notes": "Diversified conglomerate"},
    {"Symbol": "KOTAKBANK.NS", "Name": "KOTAKBANK",   "Sector": "Finance",    "Industry": "Private Banks",    "Active": True, "Priority": 2, "Notes": "Premium private bank"},
]


def load_from_google_sheet():
    """Load watchlist from Google Sheets CSV URL."""
    try:
        df = pd.read_csv(WATCHLIST_SHEET_URL)
        required = ["Symbol", "Name", "Sector", "Industry", "Active", "Priority"]
        for col in required:
            if col not in df.columns:
                return None
        print("✅ Watchlist loaded from Google Sheet")
        return df
    except Exception as e:
        print(f"⚠️ Could not load watchlist from Google Sheet: {e}")
        return None


def load_from_csv():
    """Load watchlist from local CSV file."""
    if not os.path.exists(WATCHLIST_FILE):
        initialize_watchlist()
    try:
        df = pd.read_csv(WATCHLIST_FILE)
        print("✅ Watchlist loaded from CSV file")
        return df
    except Exception as e:
        print(f"⚠️ Could not load watchlist CSV: {e}")
        return None


def initialize_watchlist():
    """Create default watchlist CSV if it doesn't exist."""
    if not os.path.exists(WATCHLIST_FILE):
        df = pd.DataFrame(DEFAULT_WATCHLIST)
        df.to_csv(WATCHLIST_FILE, index=False)
        print(f"✅ Created watchlist at: {WATCHLIST_FILE}")


def load_watchlist(active_only=True):
    """
    Load watchlist — tries Google Sheet first, then CSV, then defaults.
    Returns cleaned dataframe.
    """
    df = None

    # Priority 1: Google Sheet
    if WATCHLIST_SHEET_URL and WATCHLIST_SHEET_URL.strip():
        df = load_from_google_sheet()

    # Priority 2: Local CSV
    if df is None:
        df = load_from_csv()

    # Priority 3: Built-in defaults
    if df is None:
        print("⚠️ Using built-in default watchlist")
        df = pd.DataFrame(DEFAULT_WATCHLIST)

    # Clean up
    required = ["Symbol", "Name", "Sector", "Industry", "Active", "Priority"]
    for col in required:
        if col not in df.columns:
            df[col] = "Unknown" if col not in ["Active", "Priority"] else (True if col == "Active" else 1)

    df['Active'] = df['Active'].astype(str).str.lower().isin(['true', '1', 'yes'])

    if active_only:
        df = df[df['Active'] == True]

    df = df.sort_values('Priority', ascending=True).reset_index(drop=True)
    return df


def get_watchlist_dict(active_only=True):
    """Return {Name: Symbol} dict — drop-in for old hardcoded WATCHLIST."""
    df = load_watchlist(active_only)
    return dict(zip(df['Name'], df['Symbol']))


def get_sectors():
    """Return sorted list of unique sectors."""
    df = load_watchlist(active_only=False)
    return sorted(df['Sector'].unique().tolist())


def get_stocks_by_sector(sector, active_only=True):
    """Return stocks in a given sector."""
    df = load_watchlist(active_only)
    return df[df['Sector'] == sector]


def get_watchlist_summary():
    """Return summary stats about the watchlist."""
    all_df    = load_watchlist(active_only=False)
    active_df = load_watchlist(active_only=True)
    sector_counts = active_df.groupby('Sector')['Name'].count().to_dict()

    source = "Google Sheet" if (WATCHLIST_SHEET_URL and WATCHLIST_SHEET_URL.strip()) else "CSV file"

    return {
        "Total Stocks":  len(all_df),
        "Active Stocks": len(active_df),
        "Sectors":       len(active_df['Sector'].unique()),
        "By Sector":     sector_counts,
        "Source":        source,
    }


def add_stock(symbol, name, sector, industry, priority=3, notes=""):
    """Add a stock to watchlist.csv (local only)."""
    df = load_watchlist(active_only=False)
    if symbol in df['Symbol'].values:
        return False, f"{symbol} already exists"
    new_row = pd.DataFrame([{
        "Symbol": symbol, "Name": name, "Sector": sector,
        "Industry": industry, "Active": True,
        "Priority": priority, "Notes": notes,
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(WATCHLIST_FILE, index=False)
    return True, f"✅ Added {name} ({symbol})"


def remove_stock(symbol):
    """Deactivate a stock (sets Active=False)."""
    df = load_watchlist(active_only=False)
    if symbol not in df['Symbol'].values:
        return False, f"{symbol} not found"
    df.loc[df['Symbol'] == symbol, 'Active'] = False
    df.to_csv(WATCHLIST_FILE, index=False)
    return True, f"✅ Deactivated {symbol}"


def get_priority_stocks(priority=1):
    """Return only top priority stocks."""
    df = load_watchlist(active_only=True)
    return df[df['Priority'] <= priority]
