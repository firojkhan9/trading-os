# ================================================
# FILE: config/strategy_settings.py
# PURPOSE: Expose settings to all strategy files
#          Reads from Google Sheets via settings_loader
#          Falls back to safe defaults automatically
#
# HOW TO USE IN ANY STRATEGY FILE:
#   from config.strategy_settings import (
#       STOP_LOSS_PCT,
#       TARGET_PROFIT_PCT,
#       ...
#   )
#
# TO CHANGE SETTINGS:
#   Edit your Google Sheet — no code changes needed.
#   If no Google Sheet set up yet, edit DEFAULT_SETTINGS
#   in config/settings_loader.py
# ================================================

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings_loader import get_settings

# ── Load all settings at import time ─────────────
# This runs once when the module is first imported
_settings = get_settings()

# ── Expose as module-level variables ─────────────
# All strategy files import these directly
STOP_LOSS_PCT      = _settings["STOP_LOSS_PCT"]
TARGET_PROFIT_PCT  = _settings["TARGET_PROFIT_PCT"]
USE_TRAILING_STOP  = _settings["USE_TRAILING_STOP"]
TRAILING_STOP_PCT  = _settings["TRAILING_STOP_PCT"]
MAX_POSITION_PCT   = _settings["MAX_POSITION_PCT"]
WEAK_POSITION_PCT  = _settings["WEAK_POSITION_PCT"]
BROKERAGE_PCT      = _settings["BROKERAGE_PCT"]
STRONG_BUY_VOTES   = _settings["STRONG_BUY_VOTES"]
WEAK_BUY_VOTES     = _settings["WEAK_BUY_VOTES"]
MACD_MOMENTUM_EXIT = _settings["MACD_MOMENTUM_EXIT"]
STARTING_CAPITAL   = _settings["STARTING_CAPITAL"]
SETTINGS_SOURCE    = _settings["_source"]
