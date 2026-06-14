# ================================================
# FILE: config/strategy_settings.py
# PURPOSE: Backward compatibility layer.
#          All strategy files that do:
#            from config.strategy_settings import STOP_LOSS_PCT
#          will now get values from trading_config.py
#          which reads from Google Sheets.
#          No changes needed in strategy files.
# ================================================

from config.trading_config import (
    STOP_LOSS_PCT,
    TARGET_PROFIT_PCT,
    TRAILING_STOP_PCT,
    TRAIL_ACTIVATION_PCT,
    PARTIAL_EXIT_PCT,
    MAX_POSITION_PCT,
    WEAK_POSITION_PCT,
    INTRADAY_MAX_PCT,
    TOTAL_CAPITAL,
    DAILY_LOSS_HALT_PCT,
    MAX_DEPLOYMENT_PCT,
    COOLDOWN_DAYS,
    BROKERAGE_PCT,
    SCANNER_MAX_WORKERS,
    ABSOLUTE_MIN_SCORE,
    FUNDAMENTAL_CACHE_TTL,
    BUCKET_MIN_SCORES,
    BUCKET_CAPITAL_PCT,
    SCORING_WEIGHTS,
    CONFIG_SOURCE,
)

# ── Legacy names kept for backward compatibility ──
# Files that import these names will still work
USE_TRAILING_STOP  = True
STRONG_BUY_VOTES   = 3
WEAK_BUY_VOTES     = 2
MACD_MOMENTUM_EXIT = 0.03
STARTING_CAPITAL   = TOTAL_CAPITAL
SETTINGS_SOURCE    = CONFIG_SOURCE