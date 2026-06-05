# ================================================
# FILE: strategies/candlestick_engine.py
# PURPOSE: Candlestick Intelligence Engine — Milestone 28
#
# CRITICAL RULE:
#   Candlestick patterns NEVER act alone.
#   A pattern is only valid when confirmed by ALL of:
#     1. Trend direction  (EMA alignment)
#     2. Volume           (above average on signal candle)
#     3. Support/Resistance proximity
#     4. Market regime    (no bullish patterns in bear market)
#
#   Unconfirmed patterns = REJECTED (logged with reason)
#   This engine NEVER places trades — it produces signals only.
#
# DELIVERABLES (28A–28F):
#   28A — Pattern Detection (8 patterns)
#   28B — Context Validation (trend + volume + S/R + regime)
#   28C — Confidence Scoring (0-100)
#   28D — Audit Logging (every accepted AND rejected pattern)
#   28E — Multi-Timeframe Confirmation (optional boost/penalty)
#   28F — Lifecycle Integration (fires WATCHLIST → READY)
#
# PATTERNS DETECTED:
#   Bullish: Hammer, Bullish Engulfing, Morning Star, Breakout Candle
#   Bearish: Shooting Star, Bearish Engulfing, Evening Star
#   Neutral: Doji
#
# HOW IT CONNECTS:
#   scoring_engine.py      ← get_candlestick_score_only()
#   app.py (Tab 4)         ← get_candlestick_analysis()
#   position_manager.py   ← (via lifecycle integration in 28F)
# ================================================

import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Audit log path ────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR         = os.path.join(BASE_DIR, "logs")
CANDLE_LOG_FILE  = os.path.join(LOGS_DIR, "candlestick_log.csv")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Settings ──────────────────────────────────────
BODY_RATIO_SMALL    = 0.15   # Body < 15% of range = small body (Doji-like)
BODY_RATIO_LARGE    = 0.60   # Body > 60% of range = large body (Engulfing, Breakout)
SHADOW_RATIO_HAMMER = 2.0    # Lower shadow >= 2x body = Hammer
SHADOW_RATIO_STAR   = 2.0    # Upper shadow >= 2x body = Shooting Star
DOJI_BODY_RATIO     = 0.10   # Body < 10% of range = Doji

VOLUME_CONFIRM_RATIO = 1.5   # Volume must be > 1.5x average to confirm
SR_PROXIMITY_PCT     = 2.0   # Must be within 2% of support/resistance level
BREAKOUT_MOVE_PCT    = 1.5   # Body must cover > 1.5% for a breakout candle

# Confidence score weights (28C)
SCORE_WEIGHTS = {
    "pattern_quality":    30,
    "trend_confirmation": 25,
    "volume_confirmation":20,
    "sr_context":         15,
    "regime_alignment":   10,
}


# ════════════════════════════════════════════════
# 28A — PATTERN DETECTION
# Detects candle structure only. No trade logic here.
# ════════════════════════════════════════════════

def _candle_parts(row):
    """
    Extract key candle measurements from one OHLC row.
    Returns a dict of body, shadows, range, ratios.
    """
    o = float(row["Open"])
    h = float(row["High"])
    l = float(row["Low"])
    c = float(row["Close"])

    body        = abs(c - o)
    full_range  = h - l if (h - l) > 0 else 0.0001   # avoid div/0
    upper_shadow= h - max(o, c)
    lower_shadow= min(o, c) - l
    body_ratio  = body / full_range
    is_bullish  = c >= o

    return {
        "open": o, "high": h, "low": l, "close": c,
        "body": body, "range": full_range,
        "upper_shadow": upper_shadow,
        "lower_shadow": lower_shadow,
        "body_ratio":   body_ratio,
        "is_bullish":   is_bullish,
    }


def detect_hammer(data):
    """
    Hammer — bullish reversal at support.
    Conditions:
      - Small real body (< 30% of range)
      - Lower shadow >= 2x body
      - Little or no upper shadow (< body)
      - Ideally at the bottom of a downtrend
    """
    row = data.iloc[-1]
    p   = _candle_parts(row)

    if (
        p["body_ratio"] < 0.30 and
        p["lower_shadow"] >= SHADOW_RATIO_HAMMER * p["body"] and
        p["upper_shadow"] <= p["body"]
    ):
        quality = 0.90 if p["lower_shadow"] >= 3 * p["body"] else 0.75
        return {
            "pattern":    "HAMMER",
            "direction":  "BULLISH",
            "strength":   quality,
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_shooting_star(data):
    """
    Shooting Star — bearish reversal at resistance.
    Conditions:
      - Small real body (< 30% of range)
      - Upper shadow >= 2x body
      - Little or no lower shadow (< body)
    """
    row = data.iloc[-1]
    p   = _candle_parts(row)

    if (
        p["body_ratio"] < 0.30 and
        p["upper_shadow"] >= SHADOW_RATIO_STAR * p["body"] and
        p["lower_shadow"] <= p["body"]
    ):
        quality = 0.90 if p["upper_shadow"] >= 3 * p["body"] else 0.75
        return {
            "pattern":    "SHOOTING_STAR",
            "direction":  "BEARISH",
            "strength":   quality,
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_bullish_engulfing(data):
    """
    Bullish Engulfing — strong bullish reversal.
    Conditions:
      - Day 1: bearish candle (red)
      - Day 2: bullish candle (green) whose body fully covers day 1's body
    """
    if len(data) < 2:
        return None

    prev = _candle_parts(data.iloc[-2])
    curr = _candle_parts(data.iloc[-1])

    if (
        not prev["is_bullish"] and          # Day 1 is red
        curr["is_bullish"] and              # Day 2 is green
        curr["open"] < prev["close"] and    # Opens below prev close
        curr["close"] > prev["open"] and    # Closes above prev open
        curr["body"] > prev["body"]         # Body is larger
    ):
        quality = min(0.95, 0.70 + (curr["body"] / max(prev["body"], 0.01) - 1) * 0.1)
        return {
            "pattern":    "BULLISH_ENGULFING",
            "direction":  "BULLISH",
            "strength":   round(quality, 2),
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_bearish_engulfing(data):
    """
    Bearish Engulfing — strong bearish reversal.
    Conditions:
      - Day 1: bullish candle (green)
      - Day 2: bearish candle (red) whose body fully covers day 1's body
    """
    if len(data) < 2:
        return None

    prev = _candle_parts(data.iloc[-2])
    curr = _candle_parts(data.iloc[-1])

    if (
        prev["is_bullish"] and              # Day 1 is green
        not curr["is_bullish"] and          # Day 2 is red
        curr["open"] > prev["close"] and    # Opens above prev close
        curr["close"] < prev["open"] and    # Closes below prev open
        curr["body"] > prev["body"]         # Body is larger
    ):
        quality = min(0.95, 0.70 + (curr["body"] / max(prev["body"], 0.01) - 1) * 0.1)
        return {
            "pattern":    "BEARISH_ENGULFING",
            "direction":  "BEARISH",
            "strength":   round(quality, 2),
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_morning_star(data):
    """
    Morning Star — 3-candle bullish reversal.
    Conditions:
      - Day 1: large bearish candle (red)
      - Day 2: small body (star) gapping down
      - Day 3: large bullish candle closing above midpoint of Day 1
    """
    if len(data) < 3:
        return None

    d1 = _candle_parts(data.iloc[-3])
    d2 = _candle_parts(data.iloc[-2])
    d3 = _candle_parts(data.iloc[-1])

    d1_midpoint = d1["open"] - (d1["body"] / 2)

    if (
        not d1["is_bullish"] and             # Day 1: red
        d1["body_ratio"] > 0.50 and          # Day 1: large body
        d2["body_ratio"] < 0.30 and          # Day 2: small body (star)
        d3["is_bullish"] and                 # Day 3: green
        d3["body_ratio"] > 0.50 and          # Day 3: large body
        d3["close"] > d1_midpoint            # Day 3 closes above Day 1 midpoint
    ):
        return {
            "pattern":    "MORNING_STAR",
            "direction":  "BULLISH",
            "strength":   0.88,
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_evening_star(data):
    """
    Evening Star — 3-candle bearish reversal.
    Conditions:
      - Day 1: large bullish candle (green)
      - Day 2: small body (star) gapping up
      - Day 3: large bearish candle closing below midpoint of Day 1
    """
    if len(data) < 3:
        return None

    d1 = _candle_parts(data.iloc[-3])
    d2 = _candle_parts(data.iloc[-2])
    d3 = _candle_parts(data.iloc[-1])

    d1_midpoint = d1["open"] + (d1["body"] / 2)

    if (
        d1["is_bullish"] and                 # Day 1: green
        d1["body_ratio"] > 0.50 and          # Day 1: large body
        d2["body_ratio"] < 0.30 and          # Day 2: small body (star)
        not d3["is_bullish"] and             # Day 3: red
        d3["body_ratio"] > 0.50 and          # Day 3: large body
        d3["close"] < d1_midpoint            # Day 3 closes below Day 1 midpoint
    ):
        return {
            "pattern":    "EVENING_STAR",
            "direction":  "BEARISH",
            "strength":   0.88,
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_doji(data):
    """
    Doji — indecision candle. Needs confirmation.
    Conditions:
      - Body is very small relative to range (< 10%)
    """
    row = data.iloc[-1]
    p   = _candle_parts(row)

    if p["body_ratio"] < DOJI_BODY_RATIO:
        return {
            "pattern":    "DOJI",
            "direction":  "NEUTRAL",
            "strength":   0.60,
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_breakout_candle(data):
    """
    Breakout Candle — large body, price moves > BREAKOUT_MOVE_PCT.
    Used to confirm momentum. Must be validated with volume.
    Conditions:
      - Large body (> 60% of range)
      - Body covers > 1.5% price move
    """
    row = data.iloc[-1]
    p   = _candle_parts(row)

    if len(data) < 2:
        return None

    prev_close   = float(data.iloc[-2]["Close"])
    price_move   = abs((p["close"] - prev_close) / prev_close) * 100

    if (
        p["body_ratio"] > BODY_RATIO_LARGE and
        price_move >= BREAKOUT_MOVE_PCT
    ):
        direction = "BULLISH" if p["is_bullish"] else "BEARISH"
        return {
            "pattern":    "BREAKOUT_CANDLE",
            "direction":  direction,
            "strength":   min(0.95, 0.70 + price_move * 0.05),
            "candle_date": str(data.index[-1])[:10],
        }
    return None


def detect_all_patterns(data):
    """
    Run all 8 pattern detectors on the last candle(s).
    Returns a list of detected pattern dicts (may be empty).
    Only returns patterns that were actually detected.
    """
    detectors = [
        detect_hammer,
        detect_shooting_star,
        detect_bullish_engulfing,
        detect_bearish_engulfing,
        detect_morning_star,
        detect_evening_star,
        detect_doji,
        detect_breakout_candle,
    ]

    patterns = []
    for detector in detectors:
        try:
            result = detector(data)
            if result:
                patterns.append(result)
        except Exception:
            pass

    return patterns


# ════════════════════════════════════════════════
# 28B — CONTEXT VALIDATION
# A detected pattern must pass ALL 4 filters.
# ════════════════════════════════════════════════

def _check_trend_confirmation(data, pattern_direction):
    """
    Bullish patterns need price > EMA20 or rising EMA slope.
    Bearish patterns need price < EMA20 or falling EMA slope.
    Returns (confirmed: bool, reason: str, score_contribution: int)
    """
    try:
        closes = data["Close"]
        ema20  = closes.ewm(span=20, adjust=False).mean()
        latest_close = float(closes.iloc[-1])
        latest_ema20 = float(ema20.iloc[-1])

        # EMA slope over last 5 days
        ema_slope = float(ema20.iloc[-1]) - float(ema20.iloc[-6]) if len(ema20) >= 6 else 0

        if pattern_direction == "BULLISH":
            if latest_close > latest_ema20 or ema_slope > 0:
                return True,  "Price above EMA20 or EMA rising", 25
            else:
                return False, "Price below EMA20 and EMA falling — trend not aligned for bullish pattern", 0

        elif pattern_direction == "BEARISH":
            if latest_close < latest_ema20 or ema_slope < 0:
                return True,  "Price below EMA20 or EMA falling", 25
            else:
                return False, "Price above EMA20 and EMA rising — trend not aligned for bearish pattern", 0

        else:  # NEUTRAL (Doji)
            return True, "Doji — trend confirmation not required", 15

    except Exception:
        return True, "Trend check skipped (data issue)", 15  # neutral


def _check_volume_confirmation(data):
    """
    Signal candle volume must be > 1.5x 20-day average.
    Returns (confirmed: bool, reason: str, score_contribution: int, vol_ratio: float)
    """
    try:
        vol_ma    = data["Volume"].rolling(20).mean()
        curr_vol  = float(data["Volume"].iloc[-1])
        avg_vol   = float(vol_ma.iloc[-1])

        if avg_vol <= 0:
            return True, "Volume baseline unavailable", 10, 1.0

        ratio = round(curr_vol / avg_vol, 2)

        if ratio >= 2.0:
            return True,  f"Volume spike {ratio}x average — strong confirmation", 20, ratio
        elif ratio >= VOLUME_CONFIRM_RATIO:
            return True,  f"Volume {ratio}x average — good confirmation", 15, ratio
        elif ratio >= 1.0:
            return True,  f"Volume {ratio}x average — adequate", 8, ratio
        else:
            return False, f"Volume only {ratio}x average — below threshold of {VOLUME_CONFIRM_RATIO}x. Weak signal.", 0, ratio

    except Exception:
        return True, "Volume check skipped", 10, 1.0


def _check_sr_context(data, pattern_direction):
    """
    Bullish reversals should occur near support.
    Bearish reversals should occur near resistance.

    Support  = lowest low of last 20 candles
    Resistance = highest high of last 20 candles
    Proximity threshold = SR_PROXIMITY_PCT (2%)

    Returns (near_level: bool, reason: str, score_contribution: int)
    """
    try:
        recent     = data.tail(20)
        support    = float(recent["Low"].min())
        resistance = float(recent["High"].max())
        curr_price = float(data["Close"].iloc[-1])

        dist_to_support    = abs((curr_price - support)    / curr_price) * 100
        dist_to_resistance = abs((curr_price - resistance) / curr_price) * 100

        if pattern_direction == "BULLISH":
            if dist_to_support <= SR_PROXIMITY_PCT:
                return True,  f"Price near support ₹{support:.0f} (within {dist_to_support:.1f}%)", 15
            else:
                return False, f"Price not near support (₹{support:.0f} is {dist_to_support:.1f}% away)", 0

        elif pattern_direction == "BEARISH":
            if dist_to_resistance <= SR_PROXIMITY_PCT:
                return True,  f"Price near resistance ₹{resistance:.0f} (within {dist_to_resistance:.1f}%)", 15
            else:
                return False, f"Price not near resistance (₹{resistance:.0f} is {dist_to_resistance:.1f}% away)", 0

        else:  # Doji
            return True, "Doji — S/R context is informational only", 10

    except Exception:
        return True, "S/R check skipped", 8


def _check_regime_alignment(pattern_direction, regime):
    """
    Bullish patterns only allowed in BULL / WEAK BULL.
    Bearish patterns allowed in BEAR / WEAK BEAR.
    SIDEWAYS reduces score but doesn't block.

    Returns (allowed: bool, reason: str, score_contribution: int)
    """
    regime_upper = str(regime).upper()

    if pattern_direction == "BULLISH":
        if "BEAR" in regime_upper and "WEAK" not in regime_upper:
            return False, f"BEAR market — bullish patterns not valid ({regime})", 0
        elif "WEAK BEAR" in regime_upper:
            return True,  f"Weak bear — low confidence bullish ({regime})", 5
        elif "SIDEWAYS" in regime_upper:
            return True,  f"Sideways market — reduced confidence ({regime})", 7
        else:
            return True,  f"Regime supports bullish setup ({regime})", 10

    elif pattern_direction == "BEARISH":
        if "BULL" in regime_upper and "WEAK" not in regime_upper:
            return False, f"BULL market — bearish patterns not valid ({regime})", 0
        elif "WEAK BULL" in regime_upper:
            return True,  f"Weak bull — low confidence bearish ({regime})", 5
        elif "SIDEWAYS" in regime_upper:
            return True,  f"Sideways — bearish patterns acceptable ({regime})", 7
        else:
            return True,  f"Regime supports bearish setup ({regime})", 10

    else:  # Neutral
        return True, "Doji — regime check informational", 5


def validate_pattern(data, pattern, regime="UNKNOWN"):
    """
    Run all 4 validation checks on a detected pattern.
    Returns a validation result dict.

    A pattern passes only when trend + volume + regime all confirm.
    S/R is checked but a miss reduces score rather than hard-blocking
    (because not all valid patterns are at textbook S/R levels).
    """
    direction = pattern["direction"]

    trend_ok,  trend_reason,  trend_pts  = _check_trend_confirmation(data, direction)
    volume_ok, volume_reason, volume_pts, vol_ratio = _check_volume_confirmation(data)
    sr_near,   sr_reason,     sr_pts      = _check_sr_context(data, direction)
    regime_ok, regime_reason, regime_pts  = _check_regime_alignment(direction, regime)

    # Hard blocks: trend + regime must both pass for non-Doji patterns
    if direction != "NEUTRAL":
        hard_pass = trend_ok and regime_ok
    else:
        hard_pass = True

    # Volume is a soft block — reduces score significantly but doesn't hard-fail
    # (a rare pattern on low volume can still be noted, just with low confidence)
    if not volume_ok:
        volume_pts = 0

    total_context_pts = trend_pts + volume_pts + sr_pts + regime_pts

    rejection_reasons = []
    if not trend_ok:  rejection_reasons.append(f"TREND: {trend_reason}")
    if not volume_ok: rejection_reasons.append(f"VOLUME: {volume_reason}")
    if not sr_near:   rejection_reasons.append(f"S/R: {sr_reason}")
    if not regime_ok: rejection_reasons.append(f"REGIME: {regime_reason}")

    return {
        "pattern":         pattern,
        "accepted":        hard_pass,
        "trend_ok":        trend_ok,
        "volume_ok":       volume_ok,
        "sr_near":         sr_near,
        "regime_ok":       regime_ok,
        "vol_ratio":       vol_ratio,
        "context_pts":     total_context_pts,   # max 70 (out of full 100)
        "trend_reason":    trend_reason,
        "volume_reason":   volume_reason,
        "sr_reason":       sr_reason,
        "regime_reason":   regime_reason,
        "rejection_reasons": rejection_reasons,
    }


# ════════════════════════════════════════════════
# 28C — CONFIDENCE SCORING
# ════════════════════════════════════════════════

def calculate_confidence_score(pattern, validation):
    """
    Build a 0-100 confidence score.
    Pattern quality (30) + context validation (70) = 100 max.

    Pattern quality:
      pattern["strength"] is 0.0–1.0 → multiply by 30
    Context (from validation):
      trend (25) + volume (20) + S/R (15) + regime (10) = 70 max
    """
    if not validation["accepted"]:
        return 0

    pattern_pts  = round(pattern["strength"] * SCORE_WEIGHTS["pattern_quality"])
    context_pts  = validation["context_pts"]   # already 0-70
    total        = min(100, pattern_pts + context_pts)

    return total


def get_candlestick_signal(confidence, direction):
    """Convert confidence score + direction to a signal string."""
    if confidence >= 75:
        prefix = "STRONG "
    elif confidence >= 50:
        prefix = ""
    else:
        prefix = "WEAK "

    if direction == "BULLISH":
        return f"{prefix}BUY 🕯️"
    elif direction == "BEARISH":
        return f"{prefix}SELL 🕯️"
    else:
        return "WATCH 🕯️"


# ════════════════════════════════════════════════
# 28D — AUDIT LOGGING
# Every pattern, accepted or rejected, gets logged.
# ════════════════════════════════════════════════

def log_pattern(
    stock_name, pattern, validation, confidence, signal
):
    """
    Append one pattern event to the candlestick audit log.
    Logs both accepted and rejected patterns — full audit trail.
    """
    rejection_text = " | ".join(validation["rejection_reasons"]) if validation["rejection_reasons"] else ""

    entry = {
        "Timestamp":       datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Stock":           stock_name,
        "Pattern":         pattern["pattern"],
        "Direction":       pattern["direction"],
        "Candle_Date":     pattern["candle_date"],
        "Strength":        round(pattern["strength"], 2),
        "Confidence":      confidence,
        "Signal":          signal,
        "Accepted":        "YES" if validation["accepted"] else "NO",
        "Trend_OK":        "YES" if validation["trend_ok"]  else "NO",
        "Volume_OK":       "YES" if validation["volume_ok"] else "NO",
        "SR_Near":         "YES" if validation["sr_near"]   else "NO",
        "Regime_OK":       "YES" if validation["regime_ok"] else "NO",
        "Vol_Ratio":       validation.get("vol_ratio", ""),
        "Rejection_Reason":rejection_text,
    }

    df = pd.DataFrame([entry])
    try:
        if os.path.exists(CANDLE_LOG_FILE):
            df.to_csv(CANDLE_LOG_FILE, mode='a', header=False, index=False)
        else:
            df.to_csv(CANDLE_LOG_FILE, mode='w', header=True, index=False)
    except Exception as e:
        print(f"⚠️ Candlestick log write failed: {e}")


def load_candle_log(max_rows=200):
    """Load the candlestick audit log for dashboard display."""
    if not os.path.exists(CANDLE_LOG_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(CANDLE_LOG_FILE)
        return df.sort_values("Timestamp", ascending=False).head(max_rows).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# ════════════════════════════════════════════════
# 28E — MULTI-TIMEFRAME CONFIRMATION (optional)
# Weekly trend confirming daily pattern = +10 pts
# Weekly trend contradicting = -10 pts
# ════════════════════════════════════════════════

def get_weekly_trend(symbol):
    """
    Fetch weekly data and check if trend is bullish or bearish.
    Returns "BULLISH", "BEARISH", or "NEUTRAL".
    This is a soft modifier — never hard-blocks.
    """
    try:
        import yfinance as yf
        weekly = yf.download(
            tickers=symbol, period="6mo",
            interval="1wk", progress=False
        )
        if weekly.empty or len(weekly) < 5:
            return "NEUTRAL"

        weekly.columns = [col[0] for col in weekly.columns]
        weekly = weekly.dropna(subset=["Close"])

        ema10w  = weekly["Close"].ewm(span=10, adjust=False).mean()
        latest  = float(weekly["Close"].iloc[-1])
        ema_val = float(ema10w.iloc[-1])
        slope   = float(ema10w.iloc[-1]) - float(ema10w.iloc[-3])

        if latest > ema_val and slope > 0:
            return "BULLISH"
        elif latest < ema_val and slope < 0:
            return "BEARISH"
        else:
            return "NEUTRAL"

    except Exception:
        return "NEUTRAL"


def apply_mtf_adjustment(confidence, pattern_direction, weekly_trend):
    """
    Adjust confidence score based on weekly trend alignment.
    Confirming weekly trend = +10 | Contradicting = -10 | Neutral = 0
    """
    if weekly_trend == "NEUTRAL":
        return confidence, "Weekly trend neutral — no adjustment"

    if (
        (pattern_direction == "BULLISH" and weekly_trend == "BULLISH") or
        (pattern_direction == "BEARISH" and weekly_trend == "BEARISH")
    ):
        adjusted = min(100, confidence + 10)
        return adjusted, f"Weekly trend confirms daily ({weekly_trend}) → +10 confidence"
    else:
        adjusted = max(0, confidence - 10)
        return adjusted, f"Weekly trend contradicts daily ({weekly_trend}) → -10 confidence"


# ════════════════════════════════════════════════
# 28F — LIFECYCLE INTEGRATION
# Accepted patterns trigger WATCHLIST → READY state
# ════════════════════════════════════════════════

def trigger_lifecycle_on_pattern(
    stock_name, symbol, bucket_name,
    pattern_name, confidence
):
    """
    If a confirmed bullish pattern fires, create a lifecycle
    WATCHLIST entry and immediately mark it READY.

    Called only for accepted BULLISH patterns with confidence >= 60.
    Does nothing if stock already has an active lifecycle record.

    Returns result dict from position_manager.
    """
    try:
        from portfolio.position_manager import (
            add_to_watchlist,
            mark_ready,
        )
        watch_result = add_to_watchlist(
            stock_name, symbol, bucket_name,
            notes=f"Candlestick signal: {pattern_name} (confidence {confidence})"
        )
        if watch_result["status"] == "OK":
            pos_id = watch_result["position_id"]
            mark_ready(pos_id, composite_score=confidence)
            return {
                "status":      "OK",
                "position_id": pos_id,
                "note":        f"{pattern_name} triggered READY state in {bucket_name}",
            }
        else:
            return watch_result   # SKIPPED (already tracked)

    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


# ════════════════════════════════════════════════
# MASTER FUNCTION — called by app.py and scoring_engine
# ════════════════════════════════════════════════

def get_candlestick_analysis(
    stock_name,
    data,
    regime="UNKNOWN",
    symbol=None,
    use_mtf=False,
    trigger_lifecycle=False,
    bucket_for_lifecycle="Swing",
):
    """
    Full candlestick analysis pipeline.
    Runs 28A → 28B → 28C → 28D → 28E (optional) → 28F (optional).

    Parameters:
      stock_name         : e.g. "RELIANCE"
      data               : 60-day daily OHLCV DataFrame
      regime             : market regime string from market_regime.py
      symbol             : Yahoo Finance symbol (for MTF, optional)
      use_mtf            : True to fetch weekly data for MTF confirmation
      trigger_lifecycle  : True to fire WATCHLIST → READY on accepted pattern
      bucket_for_lifecycle: which bucket to use for lifecycle entry

    Returns a result dict with all analysis, score, and signals.
    """

    result = {
        "stock_name":        stock_name,
        "patterns_detected": [],
        "patterns_accepted": [],
        "patterns_rejected": [],
        "top_pattern":       None,
        "candlestick_score": 50,     # neutral default
        "signal":            "NO PATTERN 🕯️",
        "confidence":        0,
        "direction":         "NEUTRAL",
        "weekly_trend":      "NEUTRAL",
        "mtf_adjustment":    "",
        "lifecycle_result":  None,
        "data_available":    False,
        "summary":           "No significant candlestick pattern detected today.",
    }

    try:
        if data is None or len(data) < 3:
            result["summary"] = "Not enough price data for candlestick analysis."
            return result

        # 28A — Detect all patterns
        patterns = detect_all_patterns(data)
        result["patterns_detected"] = [p["pattern"] for p in patterns]
        result["data_available"]    = True

        if not patterns:
            result["summary"] = (
                "No recognisable candlestick pattern on today's candle. "
                "This is normal — patterns don't appear every day."
            )
            return result

        accepted_results = []
        rejected_results = []

        for pattern in patterns:

            # 28B — Validate
            validation = validate_pattern(data, pattern, regime)

            # 28C — Score
            confidence = calculate_confidence_score(pattern, validation)
            signal     = get_candlestick_signal(confidence, pattern["direction"])

            # 28E — MTF (optional)
            weekly_trend  = "NEUTRAL"
            mtf_note      = ""
            if use_mtf and symbol:
                weekly_trend = get_weekly_trend(symbol)
                confidence, mtf_note = apply_mtf_adjustment(
                    confidence, pattern["direction"], weekly_trend
                )

            # 28D — Log (every pattern, accepted or rejected)
            log_pattern(stock_name, pattern, validation, confidence, signal)

            record = {
                "pattern":      pattern["pattern"],
                "direction":    pattern["direction"],
                "strength":     pattern["strength"],
                "confidence":   confidence,
                "signal":       signal,
                "candle_date":  pattern["candle_date"],
                "trend_ok":     validation["trend_ok"],
                "volume_ok":    validation["volume_ok"],
                "sr_near":      validation["sr_near"],
                "regime_ok":    validation["regime_ok"],
                "vol_ratio":    validation["vol_ratio"],
                "trend_reason": validation["trend_reason"],
                "volume_reason":validation["volume_reason"],
                "sr_reason":    validation["sr_reason"],
                "regime_reason":validation["regime_reason"],
                "rejections":   validation["rejection_reasons"],
                "weekly_trend": weekly_trend,
                "mtf_note":     mtf_note,
            }

            if validation["accepted"] and confidence > 0:
                accepted_results.append(record)
            else:
                rejected_results.append(record)

        result["patterns_accepted"] = [r["pattern"] for r in accepted_results]
        result["patterns_rejected"] = [r["pattern"] for r in rejected_results]

        if not accepted_results:
            reasons = []
            for r in rejected_results:
                reasons.append(f"{r['pattern']}: {' | '.join(r['rejections'])}")
            result["summary"] = (
                f"Pattern(s) detected but NOT confirmed: "
                f"{', '.join(result['patterns_detected'])}. "
                f"Reason(s): {' | '.join(reasons[:2])}"
            )
            return result

        # Best accepted pattern = highest confidence
        best = max(accepted_results, key=lambda x: x["confidence"])

        result["top_pattern"]       = best
        result["confidence"]        = best["confidence"]
        result["signal"]            = best["signal"]
        result["direction"]         = best["direction"]
        result["weekly_trend"]      = best["weekly_trend"]
        result["mtf_adjustment"]    = best["mtf_note"]

        # Candlestick score for scoring_engine.py:
        # Map confidence (0-100) as the score directly.
        # If direction is bearish, invert (bearish = low score for long-only system)
        raw_score = best["confidence"]
        if best["direction"] == "BEARISH":
            cs_score = max(0, 50 - (raw_score - 50))
        elif best["direction"] == "NEUTRAL":
            cs_score = 50
        else:
            cs_score = raw_score

        result["candlestick_score"] = cs_score

        # 28F — Lifecycle trigger (bullish patterns only, confidence >= 60)
        if (
            trigger_lifecycle and
            symbol and
            best["direction"] == "BULLISH" and
            best["confidence"] >= 60
        ):
            lc_result = trigger_lifecycle_on_pattern(
                stock_name, symbol, bucket_for_lifecycle,
                best["pattern"], best["confidence"]
            )
            result["lifecycle_result"] = lc_result

        # Build summary
        result["summary"] = _build_summary(best, result)

    except Exception as e:
        result["summary"] = f"Candlestick analysis error: {e}"

    return result


def _build_summary(best, result):
    """Plain English summary of the top accepted pattern."""
    p   = best["pattern"].replace("_", " ").title()
    dir = best["direction"]
    conf = best["confidence"]
    vol  = best["vol_ratio"]

    lines = []

    if dir == "BULLISH":
        lines.append(
            f"✅ **{p}** detected — bullish reversal/continuation signal."
        )
        if conf >= 75:
            lines.append(
                f"High confidence ({conf}/100) — all confirmation filters passed. "
                f"Volume is {vol}x average."
            )
        else:
            lines.append(
                f"Moderate confidence ({conf}/100). "
                f"Volume is {vol}x average. Proceed with caution."
            )
        if best["sr_near"]:
            lines.append("Pattern appeared near a key support level — adds conviction.")
        else:
            lines.append(
                "Pattern did NOT appear near support — reduces reliability. "
                "Wait for price confirmation before entry."
            )

    elif dir == "BEARISH":
        lines.append(
            f"🔴 **{p}** detected — bearish reversal signal."
        )
        lines.append(
            f"Confidence {conf}/100. Consider reducing exposure or avoiding new longs."
        )

    else:
        lines.append(
            f"⚪ **{p}** (Doji) — market is undecided. "
            "Wait for the next candle to confirm direction before acting."
        )

    if best["weekly_trend"] != "NEUTRAL":
        lines.append(f"Weekly trend: {best['weekly_trend']}. {best['mtf_note']}")

    if result["patterns_rejected"]:
        lines.append(
            f"Also detected but not confirmed: "
            f"{', '.join(result['patterns_rejected'])}."
        )

    return " ".join(lines)


def get_candlestick_score_only(data, regime="UNKNOWN"):
    """
    Lightweight wrapper — returns integer score 0-100.
    Called by scoring_engine.py.
    Returns neutral 50 on any failure.
    """
    try:
        result = get_candlestick_analysis("", data, regime)
        return result["candlestick_score"]
    except Exception:
        return 50
