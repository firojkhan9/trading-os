# ================================================
# FILE: config/trading_config.py
# PURPOSE: Single source of truth for ALL trading
#          parameters. Values come from Google Sheet
#          first, with safe hardcoded defaults as
#          fallback. Edit from the Settings tab in
#          the dashboard OR directly in Google Sheets.
#          Never need to touch code to change settings.
# ================================================

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Load from Google Sheets via settings_loader ──
try:
    from config.settings_loader import get_settings
    _sheet = get_settings()
except Exception:
    _sheet = {}


def _get(key, default, scale=1.0):
    """
    Get a value from sheet settings.
    scale: divide the sheet value by this
           e.g. sheet stores 6 (percent), we need 0.06
    """
    val = _sheet.get(key)
    if val is None:
        return default
    try:
        return round(float(val) / scale, 6)
    except (TypeError, ValueError):
        return default


def _get_raw(key, default):
    """Get integer/string value without scaling."""
    val = _sheet.get(key)
    if val is None:
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


# ════════════════════════════════════════════════
# RISK SETTINGS
# ════════════════════════════════════════════════

# Stop loss: 6% means sell if stock falls 6% from buy price
STOP_LOSS_PCT         = _get("STOP_LOSS_PCT",        0.06,  scale=100)

# Profit target: 15% means sell to take profit at +15%
TARGET_PROFIT_PCT     = _get("TARGET_PROFIT_PCT",    0.15,  scale=100)

# Trailing stop: once activated, stop trails 4% below peak
TRAILING_STOP_PCT     = _get("TRAILING_STOP_PCT",    0.04,  scale=100)

# Activate trailing stop when gain reaches this %
TRAIL_ACTIVATION_PCT  = _get("TRAIL_ACTIVATION_PCT", 0.06,  scale=100)

# Book 50% profit when gain reaches this %
PARTIAL_EXIT_PCT      = _get("PARTIAL_EXIT_PCT",     0.08,  scale=100)


# ════════════════════════════════════════════════
# POSITION SIZING
# ════════════════════════════════════════════════

# Max % of bucket capital per stock (10% = never put more than
# 10% of that bucket into one stock)
MAX_POSITION_PCT      = _get("MAX_POSITION_PCT",     0.10,  scale=100)

# Smaller size for weaker signals (2 strategy votes instead of 3+)
WEAK_POSITION_PCT     = _get("WEAK_POSITION_PCT",    0.05,  scale=100)

# Even smaller for intraday (more trades, smaller size each)
INTRADAY_MAX_PCT      = _get("INTRADAY_MAX_PCT",     0.033, scale=100)


# ════════════════════════════════════════════════
# PORTFOLIO SETTINGS
# ════════════════════════════════════════════════

# Total capital across all three buckets
TOTAL_CAPITAL         = _get("TOTAL_CAPITAL",        600000, scale=1)

# Halt ALL new buys if portfolio drops more than this % today
DAILY_LOSS_HALT_PCT   = _get("DAILY_LOSS_HALT_PCT",  5.0,   scale=1)

# Never deploy more than this % of total capital at once
MAX_DEPLOYMENT_PCT    = _get("MAX_DEPLOYMENT_PCT",   85.0,  scale=1)

# After stop loss, block re-entry for this many days
COOLDOWN_DAYS         = _get_raw("COOLDOWN_DAYS",    3)

# Brokerage per trade (0.1% = 0.001)
BROKERAGE_PCT         = _get("BROKERAGE_PCT",        0.001, scale=100)


# ════════════════════════════════════════════════
# SCANNER SETTINGS
# ════════════════════════════════════════════════

# How many stocks to fetch simultaneously
# Higher = faster but may hit yfinance rate limits
# Safe range: 8-12
SCANNER_MAX_WORKERS   = _get_raw("SCANNER_MAX_WORKERS",   10)

# Don't even analyse stocks scoring below this
ABSOLUTE_MIN_SCORE    = _get_raw("ABSOLUTE_MIN_SCORE",    50)

# How many days to reuse cached fundamental data
# Fundamentals don't change daily — cache saves ~60% scan time
FUNDAMENTAL_CACHE_TTL = _get_raw("FUNDAMENTAL_CACHE_TTL", 3)


# ════════════════════════════════════════════════
# BUCKET SETTINGS
# ════════════════════════════════════════════════

# Minimum composite score to enter each bucket
BUCKET_MIN_SCORES = {
    "Long-Term": _get_raw("LONGTERM_MIN_SCORE", 70),
    "Swing":     _get_raw("SWING_MIN_SCORE",    60),
    "Intraday":  _get_raw("INTRADAY_MIN_SCORE", 55),
}

# Capital split across buckets (must add up to 100)
BUCKET_CAPITAL_PCT = {
    "Long-Term": _get_raw("LONGTERM_CAPITAL_PCT",  60),
    "Swing":     _get_raw("SWING_CAPITAL_PCT",     30),
    "Intraday":  _get_raw("INTRADAY_CAPITAL_PCT",  10),
}


# ════════════════════════════════════════════════
# SCORING ENGINE WEIGHTS
# All weights must sum to 100 (they are percentages)
# The engine normalises them automatically if they don't
# ════════════════════════════════════════════════

_raw_weights = {
    "trend":            _get_raw("WEIGHT_TREND",            16),
    "momentum":         _get_raw("WEIGHT_MOMENTUM",         12),
    "volatility":       _get_raw("WEIGHT_VOLATILITY",        7),
    "signal":           _get_raw("WEIGHT_SIGNAL",           10),
    "regime":           _get_raw("WEIGHT_REGIME",           10),
    "rs":               _get_raw("WEIGHT_RS",                4),
    "fundamental":      _get_raw("WEIGHT_FUNDAMENTAL",       8),
    "sentiment":        _get_raw("WEIGHT_SENTIMENT",         7),
    "volume":           _get_raw("WEIGHT_VOLUME",           10),
    "candlestick":      _get_raw("WEIGHT_CANDLESTICK",       8),
    "market_structure": _get_raw("WEIGHT_MARKET_STRUCTURE",  8),
}

# Auto-normalise so weights always sum to 1.0
# This means even if you change numbers in the sheet,
# the engine stays mathematically correct
_total_weight = sum(_raw_weights.values())

SCORING_WEIGHTS = {
    k: round(v / _total_weight, 6)
    for k, v in _raw_weights.items()
}


# ════════════════════════════════════════════════
# DERIVED / DISPLAY VALUES
# Useful for showing in the UI without calculation
# ════════════════════════════════════════════════

# Display-friendly versions (as %)
STOP_LOSS_DISPLAY     = round(STOP_LOSS_PCT     * 100, 1)
TARGET_DISPLAY        = round(TARGET_PROFIT_PCT * 100, 1)
TRAILING_DISPLAY      = round(TRAILING_STOP_PCT * 100, 1)
MAX_POSITION_DISPLAY  = round(MAX_POSITION_PCT  * 100, 1)

# Config source for display in dashboard
CONFIG_SOURCE = _sheet.get("_source", "defaults")


# ════════════════════════════════════════════════
# VALIDATION
# Check for obviously wrong values and warn
# (never crash — just print a warning)
# ════════════════════════════════════════════════

def validate_config():
    """
    Run sanity checks on the loaded config.
    Returns list of warning strings.
    """
    warnings = []

    if STOP_LOSS_PCT >= TARGET_PROFIT_PCT:
        warnings.append(
            f"⚠️ Stop loss ({STOP_LOSS_DISPLAY}%) >= target ({TARGET_DISPLAY}%) "
            f"— risk:reward is unfavourable"
        )

    weight_sum = sum(_raw_weights.values())
    if abs(weight_sum - 100) > 5:
        warnings.append(
            f"⚠️ Score weights sum to {weight_sum} instead of 100 "
            f"— auto-normalised but check your sheet"
        )

    bucket_sum = sum(BUCKET_CAPITAL_PCT.values())
    if abs(bucket_sum - 100) > 1:
        warnings.append(
            f"⚠️ Bucket capital % sums to {bucket_sum} instead of 100"
        )

    if TOTAL_CAPITAL < 10000:
        warnings.append(
            f"⚠️ Total capital is ₹{TOTAL_CAPITAL:,} — seems very low"
        )

    return warnings


# Run validation on import and print any warnings
_warnings = validate_config()
if _warnings:
    for w in _warnings:
        print(w)