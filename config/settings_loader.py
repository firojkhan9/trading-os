# ================================================
# FILE: config/settings_loader.py
# PURPOSE: Reads ALL settings from Google Sheets.
#          Supports both the old "Setting/Value" format
#          AND the new "Category/Parameter/Value" format.
#          Falls back to safe defaults if sheet unreachable.
# ================================================

import pandas as pd
import os

# ── PASTE YOUR GOOGLE SHEET URL HERE ──────────────
# This is the "Publish to web" CSV URL from Step 1
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQf-czW9ofaGEgrWjvR8tq-Wqyr6BaB7n-48NcwXYz-_z26yQdrurSrlGPG57Jbpgb_7UM5WvZ_U54x/pub?gid=0&single=true&output=csv"   # ← paste between the quotes

# ── Safe defaults (used when sheet is unreachable) ─
DEFAULT_SETTINGS = {
    # Risk
    "STOP_LOSS_PCT":         6,
    "TARGET_PROFIT_PCT":     15,
    "TRAILING_STOP_PCT":     4,
    "TRAIL_ACTIVATION_PCT":  6,
    "PARTIAL_EXIT_PCT":      8,
    # Position
    "MAX_POSITION_PCT":      10,
    "WEAK_POSITION_PCT":     5,
    "INTRADAY_MAX_PCT":      3.3,
    # Portfolio
    "TOTAL_CAPITAL":         600000,
    "DAILY_LOSS_HALT_PCT":   5,
    "MAX_DEPLOYMENT_PCT":    85,
    "COOLDOWN_DAYS":         3,
    "BROKERAGE_PCT":         0.1,
    # Scanner
    "SCANNER_MAX_WORKERS":   10,
    "ABSOLUTE_MIN_SCORE":    50,
    "FUNDAMENTAL_CACHE_TTL": 3,
    # Bucket minimums
    "LONGTERM_MIN_SCORE":    70,
    "SWING_MIN_SCORE":       60,
    "INTRADAY_MIN_SCORE":    55,
    # Bucket capital split
    "LONGTERM_CAPITAL_PCT":  60,
    "SWING_CAPITAL_PCT":     30,
    "INTRADAY_CAPITAL_PCT":  10,
    # Score weights
    "WEIGHT_TREND":            15,
    "WEIGHT_MOMENTUM":         11,
    "WEIGHT_VOLATILITY":        7,
    "WEIGHT_SIGNAL":            9,
    "WEIGHT_REGIME":           10,
    "WEIGHT_RS":                4,
    "WEIGHT_FUNDAMENTAL":       8,
    "WEIGHT_SENTIMENT":         6,
    "WEIGHT_VOLUME":            9,
    "WEIGHT_CANDLESTICK":       8,
    "WEIGHT_MARKET_STRUCTURE":  8,
    "WEIGHT_FII_DII":           5,
    # Legacy keys (kept for backward compatibility)
    "STRONG_BUY_VOTES":      3,
    "WEAK_BUY_VOTES":        2,
    "MACD_MOMENTUM_EXIT":    0.03,
    "USE_TRAILING_STOP":     True,
    "WEAK_POSITION_PCT":     0.05,
    "STARTING_CAPITAL":      100000,
}


def _parse_value(value_str):
    """Convert string to correct Python type."""
    v = str(value_str).strip()
    if v.lower() == "true":   return True
    if v.lower() == "false":  return False
    if v == "" or v == "nan": return None
    try:
        return int(v) if "." not in v else float(v)
    except ValueError:
        return v


def _load_new_format(df):
    """
    Parse Category/Parameter/Value format.
    This is the format used by trading_config.py.
    """
    settings = {}
    required = ["Category", "Parameter", "Value"]
    if not all(c in df.columns for c in required):
        return None

    for _, row in df.iterrows():
        key = str(row.get("Parameter", "")).strip()
        val = row.get("Value")
        if key and key != "nan":
            parsed = _parse_value(val)
            if parsed is not None:
                settings[key] = parsed

    return settings if settings else None


def _load_old_format(df):
    """
    Parse Setting/Value format (original settings_loader format).
    Kept for backward compatibility.
    """
    settings = {}
    if "Setting" not in df.columns or "Value" not in df.columns:
        return None

    for _, row in df.iterrows():
        key = str(row.get("Setting", "")).strip()
        val = row.get("Value")
        if key and key != "nan":
            parsed = _parse_value(val)
            if parsed is not None:
                settings[key] = parsed

    return settings if settings else None


def get_settings():
    """
    Load settings from Google Sheet.
    Tries new Category/Parameter/Value format first,
    then old Setting/Value format.
    Falls back to DEFAULT_SETTINGS if sheet unreachable.
    Returns a flat dictionary of parameter → value.
    """
    final = DEFAULT_SETTINGS.copy()
    source = "defaults"

    if not GOOGLE_SHEET_URL or not GOOGLE_SHEET_URL.strip():
        print("ℹ️ No Google Sheet URL set — using default settings")
        final["_source"] = source
        return final

    try:
        df = pd.read_csv(GOOGLE_SHEET_URL)

        # Try new format first
        sheet_settings = _load_new_format(df)

        # Fall back to old format
        if sheet_settings is None:
            sheet_settings = _load_old_format(df)

        if sheet_settings:
            final.update(sheet_settings)
            source = "Google Sheet"
            print(f"✅ Config loaded from Google Sheet ({len(sheet_settings)} values)")
        else:
            print("⚠️ Could not parse sheet — check column names. Using defaults.")

    except Exception as e:
        print(f"⚠️ Could not reach Google Sheet: {e}. Using defaults.")

    final["_source"] = source
    return final


# ── Convenience function — unchanged for backward compatibility ──
def get(key, fallback=None):
    """Get a single setting value."""
    settings = get_settings()
    return settings.get(key, fallback if fallback is not None else DEFAULT_SETTINGS.get(key))