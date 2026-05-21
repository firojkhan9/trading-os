# ================================================
# FILE: strategies/watchlist_manager.py
# PURPOSE: Dynamic Watchlist Management
#          Load stocks from CSV instead of
#          hardcoding them in app.py
#
# WHY THIS MATTERS:
#   Hardcoded watchlists require code changes
#   every time you want to add/remove a stock.
#   A CSV-based watchlist lets you:
#   - Add stocks without touching code
#   - Tag stocks by sector and industry
#   - Set priority levels
#   - Enable/disable stocks easily
#   - Add personal notes
#
# WATCHLIST CSV FORMAT:
#   Symbol | Name | Sector | Industry | Active | Priority | Notes
# ================================================

import pandas as pd
import os
import sys

# ── Path fix ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Watchlist file location ───────────────────────
# Lives at repo root, easy to edit in Excel or any editor
WATCHLIST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "watchlist.csv"
)

# ── Default watchlist ─────────────────────────────
# Used to CREATE the CSV on first run if it doesn't exist
# This is your starting 10 stocks with sector tags
DEFAULT_WATCHLIST = [
    {
        "Symbol":   "RELIANCE.NS",
        "Name":     "RELIANCE",
        "Sector":   "Energy",
        "Industry": "Oil & Gas",
        "Active":   True,
        "Priority": 1,
        "Notes":    "Largest Indian company by market cap",
    },
    {
        "Symbol":   "TCS.NS",
        "Name":     "TCS",
        "Sector":   "Technology",
        "Industry": "IT Services",
        "Active":   True,
        "Priority": 1,
        "Notes":    "Largest IT company in India",
    },
    {
        "Symbol":   "HDFCBANK.NS",
        "Name":     "HDFCBANK",
        "Sector":   "Finance",
        "Industry": "Private Banks",
        "Active":   True,
        "Priority": 1,
        "Notes":    "Largest private sector bank",
    },
    {
        "Symbol":   "INFY.NS",
        "Name":     "INFY",
        "Sector":   "Technology",
        "Industry": "IT Services",
        "Active":   True,
        "Priority": 1,
        "Notes":    "Second largest IT company",
    },
    {
        "Symbol":   "ICICIBANK.NS",
        "Name":     "ICICIBANK",
        "Sector":   "Finance",
        "Industry": "Private Banks",
        "Active":   True,
        "Priority": 1,
        "Notes":    "Second largest private sector bank",
    },
    {
        "Symbol":   "HINDUNILVR.NS",
        "Name":     "HINDUNILVR",
        "Sector":   "FMCG",
        "Industry": "Consumer Goods",
        "Active":   True,
        "Priority": 2,
        "Notes":    "Largest FMCG company",
    },
    {
        "Symbol":   "SBIN.NS",
        "Name":     "SBIN",
        "Sector":   "Finance",
        "Industry": "Public Banks",
        "Active":   True,
        "Priority": 2,
        "Notes":    "Largest public sector bank",
    },
    {
        "Symbol":   "BHARTIARTL.NS",
        "Name":     "BHARTIARTL",
        "Sector":   "Telecom",
        "Industry": "Telecom Services",
        "Active":   True,
        "Priority": 2,
        "Notes":    "Largest telecom company",
    },
    {
        "Symbol":   "ITC.NS",
        "Name":     "ITC",
        "Sector":   "FMCG",
        "Industry": "Diversified FMCG",
        "Active":   True,
        "Priority": 2,
        "Notes":    "Diversified conglomerate",
    },
    {
        "Symbol":   "KOTAKBANK.NS",
        "Name":     "KOTAKBANK",
        "Sector":   "Finance",
        "Industry": "Private Banks",
        "Active":   True,
        "Priority": 2,
        "Notes":    "Premium private sector bank",
    },
]


def initialize_watchlist():
    """
    Create the watchlist CSV if it doesn't exist yet.
    Called once on first run.
    After that, you can edit the CSV directly.
    """
    if not os.path.exists(WATCHLIST_FILE):
        df = pd.DataFrame(DEFAULT_WATCHLIST)
        df.to_csv(WATCHLIST_FILE, index=False)
        print(f"✅ Created watchlist at: {WATCHLIST_FILE}")
    return load_watchlist()


def load_watchlist(active_only=True):
    """
    Load the watchlist from CSV.
    Returns only active stocks by default.

    active_only=True  → only stocks where Active=True
    active_only=False → all stocks including disabled ones
    """
    # Create file if it doesn't exist
    if not os.path.exists(WATCHLIST_FILE):
        initialize_watchlist()

    try:
        df = pd.read_csv(WATCHLIST_FILE)

        # Ensure required columns exist
        required = ["Symbol", "Name", "Sector", "Industry", "Active", "Priority"]
        for col in required:
            if col not in df.columns:
                df[col] = "Unknown" if col not in ["Active", "Priority"] else (True if col == "Active" else 1)

        # Convert Active column to boolean
        df['Active'] = df['Active'].astype(str).str.lower().isin(['true', '1', 'yes'])

        # Filter to active only
        if active_only:
            df = df[df['Active'] == True]

        # Sort by priority
        df = df.sort_values('Priority', ascending=True).reset_index(drop=True)

        return df

    except Exception as e:
        print(f"Error loading watchlist: {e}")
        return pd.DataFrame(DEFAULT_WATCHLIST)


def get_watchlist_dict(active_only=True):
    """
    Return watchlist as a simple dictionary:
    { "RELIANCE": "RELIANCE.NS", ... }

    This is a drop-in replacement for the old
    hardcoded WATCHLIST dictionary in app.py.
    """
    df = load_watchlist(active_only)
    return dict(zip(df['Name'], df['Symbol']))


def get_sectors():
    """
    Return a list of all unique sectors in the watchlist.
    Used for sector filtering in the dashboard.
    """
    df = load_watchlist(active_only=False)
    return sorted(df['Sector'].unique().tolist())


def get_stocks_by_sector(sector, active_only=True):
    """
    Return all stocks in a given sector.
    Used for sector-level analysis.
    """
    df = load_watchlist(active_only)
    return df[df['Sector'] == sector]


def get_watchlist_summary():
    """
    Return a summary of the watchlist:
    - Total stocks
    - Active stocks
    - Sectors covered
    - Stocks per sector
    """
    all_df    = load_watchlist(active_only=False)
    active_df = load_watchlist(active_only=True)

    sector_counts = active_df.groupby('Sector')['Name'].count().to_dict()

    return {
        "Total Stocks":  len(all_df),
        "Active Stocks": len(active_df),
        "Sectors":       len(active_df['Sector'].unique()),
        "By Sector":     sector_counts,
    }


def add_stock(symbol, name, sector, industry, priority=3, notes=""):
    """
    Add a new stock to the watchlist CSV.
    Example:
        add_stock("WIPRO.NS", "WIPRO", "Technology", "IT Services")
    """
    df = load_watchlist(active_only=False)

    # Check if already exists
    if symbol in df['Symbol'].values:
        return False, f"{symbol} already exists in watchlist"

    new_row = pd.DataFrame([{
        "Symbol":   symbol,
        "Name":     name,
        "Sector":   sector,
        "Industry": industry,
        "Active":   True,
        "Priority": priority,
        "Notes":    notes,
    }])

    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(WATCHLIST_FILE, index=False)

    return True, f"✅ Added {name} ({symbol}) to watchlist"


def remove_stock(symbol):
    """
    Deactivate a stock (sets Active=False).
    We never delete — just disable.
    This preserves history.
    """
    df = load_watchlist(active_only=False)

    if symbol not in df['Symbol'].values:
        return False, f"{symbol} not found in watchlist"

    df.loc[df['Symbol'] == symbol, 'Active'] = False
    df.to_csv(WATCHLIST_FILE, index=False)

    return True, f"✅ Deactivated {symbol}"


def get_priority_stocks(priority=1):
    """
    Return only Priority 1 stocks (your top picks).
    Priority 1 = Core holdings — highest conviction
    Priority 2 = Secondary watchlist
    Priority 3 = Monitoring only
    """
    df = load_watchlist(active_only=True)
    return df[df['Priority'] <= priority]
