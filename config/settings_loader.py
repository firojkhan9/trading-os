# ================================================
# FILE: config/settings_loader.py
# PURPOSE: Load strategy settings from Google Sheets
#          Falls back to safe defaults if unreachable
#
# HOW IT WORKS:
#   1. You create a Google Sheet with settings
#   2. Publish it as CSV (File > Share > Publish to web)
#   3. Paste the CSV URL in GOOGLE_SHEET_URL below
#   4. The system reads it every 5 minutes
#   5. Change a number in the sheet → system picks it up
#
# FALLBACK:
#   If Google Sheet is unreachable for any reason,
#   the system uses the DEFAULT_SETTINGS below.
#   Your trading never stops due to a config error.
# ================================================

import pandas as pd
import os
import sys

# ── Safe default settings ─────────────────────────
# These are used if Google Sheet is unreachable
# Edit these as your baseline safe values
DEFAULT_SETTINGS = {
    "STOP_LOSS_PCT":      0.06,    # 6% hard stop loss
    "TARGET_PROFIT_PCT":  0.15,    # 15% profit target
    "USE_TRAILING_STOP":  True,    # Enable trailing stop
    "TRAILING_STOP_PCT":  0.04,    # 4% trail below peak
    "MAX_POSITION_PCT":   0.10,    # 10% max per trade
    "WEAK_POSITION_PCT":  0.05,    # 5% for weaker signals
    "BROKERAGE_PCT":      0.001,   # 0.1% brokerage
    "STRONG_BUY_VOTES":   3,       # Votes for strong entry
    "WEAK_BUY_VOTES":     2,       # Votes for normal entry
    "MACD_MOMENTUM_EXIT": 0.03,    # 3% MACD momentum exit
    "STARTING_CAPITAL":   100000,  # Paper trading capital
}

# ── Your Google Sheet CSV URL ─────────────────────
# SETUP INSTRUCTIONS (do this once):
#
# Step 1: Go to Google Sheets
# Step 2: Create a new sheet
# Step 3: Add these columns in Row 1:
#         Setting | Value | Description
# Step 4: Add your settings (copy from DEFAULT_SETTINGS above)
# Step 5: Go to File > Share > Publish to web
# Step 6: Choose "Sheet1" and "Comma-separated values (.csv)"
# Step 7: Click Publish and copy the URL
# Step 8: Paste it below replacing the placeholder

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQOe2wfjwRAJJO_yBoR0rCHd7UPQrAAVoHlsarjEAvT7LFM4Y0uKWFBWRmCIIbosy8d_5-kCUsbkj78/pub?gid=0&single=true&output=csv"
# Example URL format:
# "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/export?format=csv&gid=0"
# OR the "published to web" CSV URL which looks like:
# "https://docs.google.com/spreadsheets/d/e/YOUR_PUBLISHED_ID/pub?output=csv"


def load_settings_from_sheet(url):
    """
    Fetch settings from Google Sheet CSV URL.
    Returns a dictionary of settings or None if failed.
    """
    try:
        # Read the CSV directly from Google Sheets
        df = pd.read_csv(url)

        # Expecting columns: Setting, Value, Description
        if 'Setting' not in df.columns or 'Value' not in df.columns:
            print("⚠️ Google Sheet format incorrect. Expected columns: Setting, Value, Description")
            return None

        # Convert to dictionary
        settings = {}
        for _, row in df.iterrows():
            key   = str(row['Setting']).strip()
            value = str(row['Value']).strip()

            # Skip empty rows
            if not key or key == 'nan':
                continue

            # Convert to correct type
            try:
                # Boolean check first
                if value.lower() == 'true':
                    settings[key] = True
                elif value.lower() == 'false':
                    settings[key] = False
                # Integer check
                elif '.' not in value:
                    settings[key] = int(value)
                # Float
                else:
                    settings[key] = float(value)
            except ValueError:
                # Keep as string if conversion fails
                settings[key] = value

        return settings

    except Exception as e:
        print(f"⚠️ Could not load settings from Google Sheet: {e}")
        return None


def get_settings():
    """
    Master function — returns final settings dictionary.

    Priority:
    1. Google Sheet values (if URL set and reachable)
    2. DEFAULT_SETTINGS (always available as fallback)

    Individual settings from sheet OVERRIDE defaults.
    Settings not in sheet use the default value.
    This means you can control just a few settings
    from the sheet and let others use defaults.
    """

    # Start with defaults
    final_settings = DEFAULT_SETTINGS.copy()
    source         = "defaults"

    # Try to load from Google Sheet if URL is set
    if GOOGLE_SHEET_URL and GOOGLE_SHEET_URL.strip():
        sheet_settings = load_settings_from_sheet(GOOGLE_SHEET_URL)

        if sheet_settings:
            # Override defaults with sheet values
            for key, value in sheet_settings.items():
                if key in final_settings:
                    final_settings[key] = value

            source = "Google Sheet"
            print(f"✅ Settings loaded from Google Sheet ({len(sheet_settings)} values)")
        else:
            print("⚠️ Using default settings — Google Sheet unreachable")
    else:
        print("ℹ️ No Google Sheet URL set — using default settings")

    final_settings['_source'] = source
    return final_settings


# ── Convenience function ──────────────────────────
# Call this from any strategy file to get one setting
def get(key, fallback=None):
    """
    Get a single setting value.
    Example: get("STOP_LOSS_PCT") returns 0.06
    """
    settings = get_settings()
    return settings.get(key, fallback or DEFAULT_SETTINGS.get(key))
