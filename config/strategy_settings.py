# ================================================
# FILE: config/strategy_settings.py
# PURPOSE: Central settings for all backtest engines
#          Change numbers here — all strategies update
#
# WHY THESE NUMBERS:
#   Indian large caps move 1-3% on a normal day.
#   Old 3% stop loss was getting hit by daily noise.
#   Old 6% target was cutting winners too early.
#   Trailing stop lets winners run while protecting gains.
# ================================================

# ── Stop Loss ─────────────────────────────────────
# How much loss before we exit a trade
# 6% gives room for normal daily volatility
STOP_LOSS_PCT      = 0.06    # 6% hard stop loss

# ── Profit Target ─────────────────────────────────
# Lock in profit when stock rises this much
# 15% is realistic for Indian large caps in trending year
TARGET_PROFIT_PCT  = 0.15   # 15% profit target

# ── Trailing Stop ─────────────────────────────────
# Once stock is profitable, trail the stop behind it
# Example: stock rises 10%, trailing stop = 10% - 4% = 6% locked in
# This lets winners run while protecting gains
USE_TRAILING_STOP  = True
TRAILING_STOP_PCT  = 0.04   # Trail 4% below peak price

# ── Position Sizing ───────────────────────────────
MAX_POSITION_PCT   = 0.10   # Max 10% per trade (strong signal)
WEAK_POSITION_PCT  = 0.05   # 5% for weaker signals

# ── Brokerage ─────────────────────────────────────
BROKERAGE_PCT      = 0.001  # 0.1% per trade (Zerodha rates)

# ── Combined Signal thresholds ────────────────────
# How many strategies must agree before we enter
STRONG_BUY_VOTES   = 3      # 3-4 strategies agree = strong entry
WEAK_BUY_VOTES     = 2      # 2 strategies agree = normal entry

# ── MACD momentum exit threshold ──────────────────
# Only exit on bearish momentum if loss exceeds this
# Prevents exiting on normal pullbacks
MACD_MOMENTUM_EXIT = 0.03   # 3% loss before momentum exit triggers
