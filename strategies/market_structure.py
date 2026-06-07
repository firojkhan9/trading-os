# ================================================
# FILE: strategies/market_structure.py
# PURPOSE: Market Structure Engine — Milestone 29
#
# WHAT IS MARKET STRUCTURE?
#   Technical indicators (RSI, MACD, EMA) tell you the
#   momentum and direction of price movement.
#   Market Structure tells you WHERE price is in its journey:
#     - Is it making higher highs (uptrend building)?
#     - Is it near a support that has held before?
#     - Has it just broken above a resistance with volume?
#     - Is it in a tight range before a big move?
#
#   Think of it like reading a map vs a speedometer.
#   Indicators = speedometer (how fast, which direction)
#   Structure   = map (where are you, what is ahead)
#
# WHAT WE DETECT:
#   1.  Swing Highs          — local price peaks
#   2.  Swing Lows           — local price troughs
#   3.  Support Zones        — floors price bounced from
#   4.  Resistance Zones     — ceilings price struggled to break
#   5.  Breakout Detection   — price closed above resistance + volume
#   6.  Breakdown Detection  — price closed below support
#   7.  Consolidation        — ATR + BB width both compressing
#   8.  Volatility Squeeze   — extreme compression before expansion
#   9.  Higher High / Higher Low (HH/HL) — bullish structure
#  10.  Lower High / Lower Low (LH/LL)  — bearish structure
#  11.  Trend Classification — Strong Uptrend to Strong Downtrend
#
# MARKET STRUCTURE SCORE (0-100):
#   HH/HL Trend Quality         30%
#   Support Strength            10%
#   Resistance Breakout         20%
#   Volume Confirmation         10%
#   Volatility Compression      10%
#   Trend Persistence           10%
#   Consolidation Breakout Bias 10%
#
# HOW IT CONNECTS:
#   scoring_engine.py      ← get_market_structure_score_only()
#   app.py Tab 4           ← get_market_structure_analysis()
#   performance_scanner.py ← get_market_structure_score_only() per stock
#
# INPUTS:
#   OHLCV DataFrame — minimum 60 candles recommended
#   Columns needed: Open, High, Low, Close, Volume
# ================================================

import pandas as pd
import numpy as np
from datetime import datetime


# ── Settings ──────────────────────────────────────
SWING_LOOKBACK      = 5    # Bars left AND right to confirm a swing point
SR_ZONE_TOLERANCE   = 0.02 # 2% — levels within 2% are treated as the same zone
BREAKOUT_VOL_RATIO  = 1.5  # Volume must be > 1.5x average to confirm breakout
ATR_PERIOD          = 14   # ATR lookback period
BB_PERIOD           = 20   # Bollinger Bands period for squeeze detection
SQUEEZE_PERCENTILE  = 25   # BB width below 25th percentile = squeeze
MIN_SWING_POINTS    = 2    # Need at least 2 swing points for structure analysis
CONSOLIDATION_DAYS  = 10   # Days to measure for consolidation detection


# ════════════════════════════════════════════════
# HELPER: ATR CALCULATION
# Average True Range — measures day-to-day volatility
# ════════════════════════════════════════════════

def _calculate_atr(data, period=ATR_PERIOD):
    """
    Average True Range.
    True Range = max of:
      (High - Low),
      abs(High - prev_Close),
      abs(Low  - prev_Close)

    ATR = rolling average of True Range over N days.
    Rising ATR = increasing volatility.
    Falling ATR = decreasing volatility (consolidation or calm).
    """
    high  = data["High"]
    low   = data["Low"]
    close = data["Close"]

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    return atr


def _calculate_bb_width(data, period=BB_PERIOD):
    """
    Bollinger Band Width = (Upper - Lower) / Middle × 100
    Narrow width = low volatility (potential squeeze).
    Wide width   = high volatility (trend in motion).
    """
    close  = data["Close"]
    middle = close.rolling(window=period).mean()
    std    = close.rolling(window=period).std()
    upper  = middle + (2 * std)
    lower  = middle - (2 * std)
    width  = ((upper - lower) / middle * 100).round(4)
    return width


# ════════════════════════════════════════════════
# 1. SWING HIGH DETECTION
# A swing high is a local peak — higher than N bars
# on either side of it.
# ════════════════════════════════════════════════

def detect_swing_highs(data, lookback=SWING_LOOKBACK):
    """
    Detect swing high points in the data.

    A bar is a swing high if its High is greater than
    the Highs of the N bars before it AND the N bars after it.

    Why N bars on each side?
    Using both sides confirms the bar is a TRUE local peak,
    not just noise. The higher N, the more significant the swing.

    Returns:
      list of dicts: [{price, date, index}, ...]
      Sorted newest first.
    """
    highs   = data["High"].values
    dates   = data.index
    swings  = []

    # We need lookback bars on each side, so start/end accordingly
    for i in range(lookback, len(highs) - lookback):
        current = highs[i]
        left    = highs[i - lookback: i]
        right   = highs[i + 1: i + lookback + 1]

        if current > max(left) and current > max(right):
            swings.append({
                "price": round(float(current), 2),
                "date":  str(dates[i])[:10],
                "index": i,
            })

    return list(reversed(swings))   # newest first


# ════════════════════════════════════════════════
# 2. SWING LOW DETECTION
# A swing low is a local trough — lower than N bars
# on either side of it.
# ════════════════════════════════════════════════

def detect_swing_lows(data, lookback=SWING_LOOKBACK):
    """
    Detect swing low points in the data.

    A bar is a swing low if its Low is less than
    the Lows of the N bars before it AND the N bars after it.

    Returns:
      list of dicts: [{price, date, index}, ...]
      Sorted newest first.
    """
    lows    = data["Low"].values
    dates   = data.index
    swings  = []

    for i in range(lookback, len(lows) - lookback):
        current = lows[i]
        left    = lows[i - lookback: i]
        right   = lows[i + 1: i + lookback + 1]

        if current < min(left) and current < min(right):
            swings.append({
                "price": round(float(current), 2),
                "date":  str(dates[i])[:10],
                "index": i,
            })

    return list(reversed(swings))   # newest first


# ════════════════════════════════════════════════
# 3. SUPPORT ZONE DETECTION
# Builds support zones from recent swing lows.
# Multiple touches at similar price = stronger support.
# ════════════════════════════════════════════════

def detect_support_zones(data, lookback=SWING_LOOKBACK, tolerance=SR_ZONE_TOLERANCE):
    """
    Identify key support zones from swing lows.

    LOGIC:
      1. Get all swing lows
      2. Group swing lows that are within 2% of each other
         (they represent the same support zone)
      3. Count touches per zone
      4. Return zones sorted by strength (most touches first)

    A support zone touched 3+ times is very reliable.
    A zone touched only once is weak.

    Returns list of dicts:
      [{price, strength, touches, date_first, date_last}, ...]
    """
    swing_lows = detect_swing_lows(data, lookback)
    if not swing_lows:
        return []

    zones = []

    for sl in swing_lows:
        price = sl["price"]
        merged = False

        for zone in zones:
            # Check if this swing low is within tolerance of an existing zone
            zone_price = zone["price"]
            if abs(price - zone_price) / zone_price <= tolerance:
                # Merge into existing zone (average the prices)
                zone["touches"]    += 1
                zone["price"]       = round(
                    (zone["price"] * (zone["touches"] - 1) + price) / zone["touches"], 2
                )
                zone["date_last"]   = sl["date"]
                merged = True
                break

        if not merged:
            zones.append({
                "price":      price,
                "touches":    1,
                "strength":   0,    # calculated below
                "date_first": sl["date"],
                "date_last":  sl["date"],
            })

    # Calculate strength score per zone (more touches = stronger)
    max_touches = max(z["touches"] for z in zones) if zones else 1
    for zone in zones:
        zone["strength"] = round(zone["touches"] / max_touches * 100)

    # Sort by strength descending
    zones.sort(key=lambda x: x["touches"], reverse=True)
    return zones


# ════════════════════════════════════════════════
# 4. RESISTANCE ZONE DETECTION
# Builds resistance zones from recent swing highs.
# ════════════════════════════════════════════════

def detect_resistance_zones(data, lookback=SWING_LOOKBACK, tolerance=SR_ZONE_TOLERANCE):
    """
    Identify key resistance zones from swing highs.

    Same logic as support, but using swing highs.
    Price repeatedly failing at the same level = strong resistance.

    Returns list of dicts:
      [{price, strength, touches, date_first, date_last}, ...]
    """
    swing_highs = detect_swing_highs(data, lookback)
    if not swing_highs:
        return []

    zones = []

    for sh in swing_highs:
        price  = sh["price"]
        merged = False

        for zone in zones:
            zone_price = zone["price"]
            if abs(price - zone_price) / zone_price <= tolerance:
                zone["touches"]  += 1
                zone["price"]     = round(
                    (zone["price"] * (zone["touches"] - 1) + price) / zone["touches"], 2
                )
                zone["date_last"] = sh["date"]
                merged = True
                break

        if not merged:
            zones.append({
                "price":      price,
                "touches":    1,
                "strength":   0,
                "date_first": sh["date"],
                "date_last":  sh["date"],
            })

    max_touches = max(z["touches"] for z in zones) if zones else 1
    for zone in zones:
        zone["strength"] = round(zone["touches"] / max_touches * 100)

    zones.sort(key=lambda x: x["touches"], reverse=True)
    return zones


# ════════════════════════════════════════════════
# 5. BREAKOUT DETECTION
# Price closed above resistance AND volume confirms it.
# A price move without volume = suspect (likely fake).
# ════════════════════════════════════════════════

def detect_breakout(data, lookback=SWING_LOOKBACK, vol_ratio=BREAKOUT_VOL_RATIO):
    """
    Detect if current price has broken above resistance.

    CONDITIONS (both must be true):
      1. Close > nearest resistance level
      2. Volume > 1.5x 20-day average volume

    WHAT IT MEANS:
      A genuine breakout is when price pushes through a ceiling
      that it previously failed to break, AND big volume confirms
      that serious buyers are behind the move.
      Without volume, the "breakout" may just be noise.

    Returns dict:
      {
        breakout: True/False,
        resistance_level: price,
        distance_pct: how far above resistance (%),
        volume_confirmed: True/False,
        vol_ratio: today's vol / 20d avg vol,
        strength: "STRONG" / "MODERATE" / "WEAK",
      }
    """
    if len(data) < 30:
        return {"breakout": False, "reason": "Insufficient data"}

    latest_close = float(data["Close"].iloc[-1])
    latest_vol   = float(data["Volume"].iloc[-1])
    avg_vol      = float(data["Volume"].tail(20).mean())
    current_vol_ratio = round(latest_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    # Get resistance zones
    resistance_zones = detect_resistance_zones(data, lookback)

    if not resistance_zones:
        return {"breakout": False, "reason": "No resistance zones found"}

    # Find nearest resistance BELOW current price (recently broken)
    broken_zones = [
        z for z in resistance_zones
        if z["price"] < latest_close
        and abs(latest_close - z["price"]) / z["price"] <= 0.05  # within 5%
    ]

    if not broken_zones:
        return {"breakout": False, "reason": "Price not above any recent resistance"}

    # Best broken zone = closest to current price
    nearest = min(broken_zones, key=lambda z: abs(latest_close - z["price"]))
    distance_pct = round((latest_close - nearest["price"]) / nearest["price"] * 100, 2)

    volume_confirmed = current_vol_ratio >= vol_ratio

    if volume_confirmed and distance_pct >= 1.0:
        strength = "STRONG 🚀"
    elif volume_confirmed:
        strength = "MODERATE ✅"
    elif distance_pct >= 1.0:
        strength = "WEAK (Low Volume) ⚠️"
    else:
        strength = "VERY WEAK ⚠️"

    return {
        "breakout":          True,
        "resistance_level":  nearest["price"],
        "resistance_touches":nearest["touches"],
        "distance_pct":      distance_pct,
        "volume_confirmed":  volume_confirmed,
        "vol_ratio":         current_vol_ratio,
        "strength":          strength,
        "reason":            (
            f"Price ₹{latest_close:.0f} broke above resistance ₹{nearest['price']:.0f} "
            f"(+{distance_pct}%) | Volume {current_vol_ratio}x average"
        ),
    }


# ════════════════════════════════════════════════
# 6. BREAKDOWN DETECTION
# Price closed below support — bearish structure break.
# ════════════════════════════════════════════════

def detect_breakdown(data, lookback=SWING_LOOKBACK):
    """
    Detect if current price has broken below support.

    CONDITIONS:
      1. Close < nearest support level
      2. Proximity check: support was just above current price

    WHAT IT MEANS:
      A breakdown means a floor that previously held is now broken.
      This often accelerates selling — previous buyers at that level
      are now sitting at a loss and may add to selling pressure.

    Returns dict:
      {
        breakdown: True/False,
        support_level: price,
        distance_pct: how far below support (%),
        strength: "STRONG" / "MODERATE",
      }
    """
    if len(data) < 30:
        return {"breakdown": False, "reason": "Insufficient data"}

    latest_close = float(data["Close"].iloc[-1])

    support_zones = detect_support_zones(data, lookback)

    if not support_zones:
        return {"breakdown": False, "reason": "No support zones found"}

    # Find nearest support ABOVE current price (recently broken)
    broken_zones = [
        z for z in support_zones
        if z["price"] > latest_close
        and abs(z["price"] - latest_close) / z["price"] <= 0.05
    ]

    if not broken_zones:
        return {"breakdown": False, "reason": "Price not below any recent support"}

    nearest      = min(broken_zones, key=lambda z: abs(latest_close - z["price"]))
    distance_pct = round((nearest["price"] - latest_close) / nearest["price"] * 100, 2)
    strength     = "STRONG 🔻" if nearest["touches"] >= 2 else "MODERATE 📉"

    return {
        "breakdown":       True,
        "support_level":   nearest["price"],
        "support_touches": nearest["touches"],
        "distance_pct":    distance_pct,
        "strength":        strength,
        "reason":          (
            f"Price ₹{latest_close:.0f} broke below support ₹{nearest['price']:.0f} "
            f"(-{distance_pct}%) | Support had {nearest['touches']} touch(es)"
        ),
    }


# ════════════════════════════════════════════════
# 7. CONSOLIDATION DETECTION
# Price is in a tight range — a coiled spring.
# ATR AND Bollinger Width both compressing = consolidation.
# ════════════════════════════════════════════════

def detect_consolidation(data, days=CONSOLIDATION_DAYS):
    """
    Detect if the stock is in a consolidation phase.

    A CONSOLIDATION happens when:
      - ATR is decreasing (volatility falling)
      - Bollinger Band Width is decreasing (range compressing)
      - Price range in last N days is tighter than usual

    WHY THIS MATTERS:
      Consolidations often precede big moves.
      After a period of compression, the spring releases.
      Combined with a breakout signal, this is powerful.

    Returns dict:
      {
        consolidation: True/False,
        compression_score: 0-100 (higher = more compressed),
        atr_falling: True/False,
        bb_width_falling: True/False,
        range_pct: price range as % of price (lower = tighter),
      }
    """
    if len(data) < days + ATR_PERIOD + 5:
        return {
            "consolidation":    False,
            "compression_score": 0,
            "reason": "Insufficient data",
        }

    atr_series = _calculate_atr(data, ATR_PERIOD)
    bb_width   = _calculate_bb_width(data, BB_PERIOD)

    # Compare recent N days vs prior N days
    atr_recent = atr_series.tail(days).mean()
    atr_prior  = atr_series.iloc[-(days * 2):-days].mean()

    bb_recent  = bb_width.tail(days).mean()
    bb_prior   = bb_width.iloc[-(days * 2):-days].mean()

    # Price range in last N days
    recent_data = data.tail(days)
    price_high  = float(recent_data["High"].max())
    price_low   = float(recent_data["Low"].min())
    price_mid   = float(recent_data["Close"].mean())
    range_pct   = round((price_high - price_low) / price_mid * 100, 2) if price_mid > 0 else 999

    # Is ATR falling?
    atr_falling = (atr_recent < atr_prior * 0.85) if (atr_prior and atr_prior > 0) else False

    # Is BB width falling?
    bb_falling  = (bb_recent < bb_prior * 0.85)   if (bb_prior  and bb_prior  > 0) else False

    # Compression score: higher = more compressed
    compression_score = 0
    if atr_falling:  compression_score += 40
    if bb_falling:   compression_score += 40
    if range_pct < 5: compression_score += 20
    elif range_pct < 8: compression_score += 10

    is_consolidating = atr_falling and bb_falling

    return {
        "consolidation":    is_consolidating,
        "compression_score": min(100, compression_score),
        "atr_falling":      atr_falling,
        "bb_width_falling": bb_falling,
        "range_pct":        range_pct,
        "atr_change_pct":   round(((atr_recent - atr_prior) / atr_prior * 100), 1) if atr_prior else 0,
        "bb_change_pct":    round(((bb_recent - bb_prior) / bb_prior * 100), 1) if bb_prior else 0,
    }


# ════════════════════════════════════════════════
# 8. VOLATILITY SQUEEZE DETECTION
# Extreme compression = coiled spring, big move coming.
# Uses BB Width percentile relative to last 50 days.
# ════════════════════════════════════════════════

def detect_volatility_squeeze(data, percentile=SQUEEZE_PERCENTILE):
    """
    Detect if the stock is in a volatility squeeze.

    A SQUEEZE is when the current Bollinger Band Width is at
    or below its Nth percentile over the last 50 days.

    Example: percentile=25 means BB Width is in the bottom 25%
    of its range — tighter than 75% of recent readings.

    WHY THIS MATTERS:
      Low volatility periods are followed by HIGH volatility periods.
      A squeeze is a warning that the stock is about to make a
      significant move. Direction is unknown — combine with trend.
      Squeeze + HH/HL structure + breakout = very high conviction.

    Returns dict:
      {
        squeeze_active: True/False,
        squeeze_strength: "EXTREME" / "STRONG" / "MODERATE" / "NONE",
        bb_width_current: float,
        bb_width_percentile: float (0-100),
      }
    """
    if len(data) < 55:
        return {
            "squeeze_active":      False,
            "squeeze_strength":    "NONE",
            "bb_width_percentile": 50,
        }

    bb_width     = _calculate_bb_width(data, BB_PERIOD).dropna()
    if len(bb_width) < 20:
        return {"squeeze_active": False, "squeeze_strength": "NONE"}

    current_width = float(bb_width.iloc[-1])
    hist_50       = bb_width.tail(50)
    pct_rank      = round(
        (hist_50 < current_width).sum() / len(hist_50) * 100, 1
    )

    squeeze_active = pct_rank <= percentile

    if pct_rank <= 10:
        strength = "EXTREME 🔥🔥"
    elif pct_rank <= 25:
        strength = "STRONG 🔥"
    elif pct_rank <= 40:
        strength = "MODERATE ⚡"
    else:
        strength = "NONE ↔️"

    return {
        "squeeze_active":      squeeze_active,
        "squeeze_strength":    strength,
        "bb_width_current":    round(current_width, 3),
        "bb_width_percentile": pct_rank,
        "interpretation":      (
            f"BB Width in bottom {pct_rank}% of last 50 days — "
            f"{'big move imminent' if squeeze_active else 'volatility normal'}"
        ),
    }


# ════════════════════════════════════════════════
# 9. HIGHER HIGH / HIGHER LOW DETECTION (Bullish)
# The most reliable definition of an uptrend.
# ════════════════════════════════════════════════

def detect_hh_hl(data, lookback=SWING_LOOKBACK):
    """
    Detect if the stock is making Higher Highs (HH) and
    Higher Lows (HL) — the textbook definition of an uptrend.

    LOGIC:
      Compare the last 3 swing highs: is each one higher than the previous?
      Compare the last 3 swing lows:  is each one higher than the previous?

      All HH + all HL = Strong Uptrend
      Some HH/HL     = Weak Uptrend or transition
      None           = Not in an uptrend

    COUNTS:
      hh_count = how many consecutive HHs (max 2 with 3 swing points)
      hl_count = how many consecutive HLs (max 2 with 3 swing points)

    Returns dict:
      {
        hh_count, hl_count, uptrend_strength, swing_highs, swing_lows
      }
    """
    swing_highs = detect_swing_highs(data, lookback)
    swing_lows  = detect_swing_lows(data, lookback)

    hh_count = 0
    hl_count = 0

    # Count consecutive HHs in recent swing highs (check last 3)
    recent_highs = [sh["price"] for sh in swing_highs[:4]]   # newest first
    for i in range(len(recent_highs) - 1):
        if recent_highs[i] > recent_highs[i + 1]:
            hh_count += 1
        else:
            break   # Stop at first non-HH

    # Count consecutive HLs in recent swing lows
    recent_lows = [sl["price"] for sl in swing_lows[:4]]    # newest first
    for i in range(len(recent_lows) - 1):
        if recent_lows[i] > recent_lows[i + 1]:
            hl_count += 1
        else:
            break

    # Uptrend strength
    total = hh_count + hl_count
    if total >= 4:
        strength = "STRONG UPTREND 🚀"
    elif total >= 2:
        strength = "UPTREND 📈"
    elif total >= 1:
        strength = "WEAK UPTREND ↗️"
    else:
        strength = "NO UPTREND —"

    return {
        "hh_count":        hh_count,
        "hl_count":        hl_count,
        "uptrend_strength":strength,
        "swing_highs":     swing_highs[:4],
        "swing_lows":      swing_lows[:4],
    }


# ════════════════════════════════════════════════
# 10. LOWER HIGH / LOWER LOW DETECTION (Bearish)
# The textbook definition of a downtrend.
# ════════════════════════════════════════════════

def detect_lh_ll(data, lookback=SWING_LOOKBACK):
    """
    Detect if the stock is making Lower Highs (LH) and
    Lower Lows (LL) — the textbook definition of a downtrend.

    LOGIC:
      Compare the last 3 swing highs: is each one lower than the previous?
      Compare the last 3 swing lows:  is each one lower than the previous?

    Returns dict:
      {
        lh_count, ll_count, downtrend_strength
      }
    """
    swing_highs = detect_swing_highs(data, lookback)
    swing_lows  = detect_swing_lows(data, lookback)

    lh_count = 0
    ll_count = 0

    recent_highs = [sh["price"] for sh in swing_highs[:4]]
    for i in range(len(recent_highs) - 1):
        if recent_highs[i] < recent_highs[i + 1]:
            lh_count += 1
        else:
            break

    recent_lows = [sl["price"] for sl in swing_lows[:4]]
    for i in range(len(recent_lows) - 1):
        if recent_lows[i] < recent_lows[i + 1]:
            ll_count += 1
        else:
            break

    total = lh_count + ll_count
    if total >= 4:
        strength = "STRONG DOWNTREND 🔻"
    elif total >= 2:
        strength = "DOWNTREND 📉"
    elif total >= 1:
        strength = "WEAK DOWNTREND ↘️"
    else:
        strength = "NO DOWNTREND —"

    return {
        "lh_count":          lh_count,
        "ll_count":          ll_count,
        "downtrend_strength":strength,
    }


# ════════════════════════════════════════════════
# 11. TREND STRUCTURE CLASSIFICATION
# Combines HH/HL + LH/LL + MA alignment
# ════════════════════════════════════════════════

def classify_trend_structure(data, lookback=SWING_LOOKBACK):
    """
    Classify the overall price structure as one of:
      Strong Uptrend, Uptrend, Sideways, Downtrend, Strong Downtrend

    USES THREE INPUTS:
      1. HH/HL count — swing point structure
      2. LH/LL count — opposite swing structure
      3. MA alignment — price vs EMA20 vs EMA50

    LOGIC:
      - Strong Uptrend:   2+ HH + 2+ HL AND price > EMA20 > EMA50
      - Uptrend:          at least 1 HH + 1 HL OR price > both EMAs
      - Sideways:         mixed or no clear structure
      - Downtrend:        at least 1 LH + 1 LL
      - Strong Downtrend: 2+ LH + 2+ LL AND price < EMA20 < EMA50

    Returns classification string + numeric score (0-100)
    """
    hh_hl = detect_hh_hl(data, lookback)
    lh_ll = detect_lh_ll(data, lookback)

    hh_count = hh_hl["hh_count"]
    hl_count = hh_hl["hl_count"]
    lh_count = lh_ll["lh_count"]
    ll_count = lh_ll["ll_count"]

    # MA alignment
    close  = data["Close"]
    ema20  = close.ewm(span=20, adjust=False).mean()
    ema50  = close.ewm(span=50, adjust=False).mean()
    latest = float(close.iloc[-1])
    e20    = float(ema20.iloc[-1])
    e50    = float(ema50.iloc[-1])

    ma_bullish = latest > e20 > e50
    ma_bearish = latest < e20 < e50

    # Structure score for uptrend (0-10 scale, then mapped)
    bull_score = (hh_count + hl_count) - (lh_count + ll_count)

    if bull_score >= 3 and ma_bullish:
        trend_state  = "STRONG UPTREND 🚀"
        trend_score  = 90
    elif bull_score >= 2 or (bull_score >= 1 and ma_bullish):
        trend_state  = "UPTREND 📈"
        trend_score  = 70
    elif bull_score <= -3 and ma_bearish:
        trend_state  = "STRONG DOWNTREND 🔻"
        trend_score  = 10
    elif bull_score <= -2 or (bull_score <= -1 and ma_bearish):
        trend_state  = "DOWNTREND 📉"
        trend_score  = 30
    else:
        trend_state  = "SIDEWAYS ↔️"
        trend_score  = 50

    return {
        "trend_state":  trend_state,
        "trend_score":  trend_score,
        "hh_count":     hh_count,
        "hl_count":     hl_count,
        "lh_count":     lh_count,
        "ll_count":     ll_count,
        "ma_bullish":   ma_bullish,
        "ma_bearish":   ma_bearish,
        "latest_close": round(latest, 2),
        "ema20":        round(e20, 2),
        "ema50":        round(e50, 2),
    }


# ════════════════════════════════════════════════
# MARKET STRUCTURE SCORE (0-100)
#
# Scoring weights from master prompt:
#   HH/HL Trend Quality         30%
#   Support Strength            10%
#   Resistance Breakout         20%
#   Volume Confirmation         10%
#   Volatility Compression      10%
#   Trend Persistence           10%
#   Consolidation Breakout Bias 10%
# ════════════════════════════════════════════════

def calculate_market_structure_score(
    trend,
    support_zones,
    resistance_zones,
    breakout,
    breakdown,
    consolidation,
    squeeze,
    hh_hl,
    lh_ll,
    data,
):
    """
    Build the composite Market Structure Score (0-100).

    This score tells the Composite Scoring Engine how
    strong or weak the price structure is at this moment.

    HIGH score (≥70) = strong bullish structure, good time to buy
    MID  score (40-70) = mixed or sideways, be selective
    LOW  score (≤40) = bearish structure, avoid new longs
    """
    score = 50   # Start at neutral

    # ── 1. HH/HL Trend Quality (30 pts) ──────────
    hh = hh_hl.get("hh_count", 0)
    hl = hh_hl.get("hl_count", 0)
    lh = lh_ll.get("lh_count", 0)
    ll = lh_ll.get("ll_count", 0)

    # Net bull points: HH+HL vs LH+LL
    bull_pts = (hh + hl) - (lh + ll)
    if   bull_pts >= 4: score += 30
    elif bull_pts >= 2: score += 20
    elif bull_pts >= 1: score += 10
    elif bull_pts == 0: score +=  0
    elif bull_pts == -1: score -= 10
    elif bull_pts == -2: score -= 20
    else:               score -= 30

    # ── 2. Support Strength (10 pts) ─────────────
    if support_zones:
        best_support = support_zones[0]
        latest_close = float(data["Close"].iloc[-1])
        support_price = best_support["price"]
        # Is price ABOVE support (not in breakdown)?
        if latest_close > support_price:
            touches = best_support.get("touches", 1)
            if   touches >= 3: score += 10
            elif touches == 2: score += 6
            else:              score += 3
        else:
            score -= 10   # Below support = structural damage

    # ── 3. Resistance Breakout (20 pts) ──────────
    if breakout.get("breakout"):
        if breakout.get("volume_confirmed"):
            score += 20
        else:
            score += 8    # Breakout but no volume = partial credit
    elif breakdown.get("breakdown"):
        score -= 20       # Breakdown is structurally bearish

    # ── 4. Volume Confirmation (10 pts) ──────────
    # Independent volume check using latest bar
    try:
        vol_ma = float(data["Volume"].tail(20).mean())
        curr_v = float(data["Volume"].iloc[-1])
        vr     = curr_v / vol_ma if vol_ma > 0 else 1.0
        if   vr >= 2.0: score += 10
        elif vr >= 1.5: score += 6
        elif vr >= 1.0: score += 2
        else:           score -= 5
    except Exception:
        pass

    # ── 5. Volatility Compression (10 pts) ───────
    # Squeeze = potential energy = bonus (direction unknown but energy is there)
    # But only positive if trend is also bullish
    squeeze_active = squeeze.get("squeeze_active", False)
    bb_pct         = squeeze.get("bb_width_percentile", 50)
    trend_bullish  = "UPTREND" in str(trend.get("trend_state", ""))

    if squeeze_active and trend_bullish:
        score += 10   # Compressed + uptrend = coiled spring in right direction
    elif squeeze_active:
        score += 3    # Compressed but direction unclear
    elif bb_pct >= 75:
        score -= 5    # Expanded volatility in late trend = risk

    # ── 6. Trend Persistence (10 pts) ────────────
    # Use MA alignment from trend classification
    if trend.get("ma_bullish"):
        score += 10
    elif trend.get("ma_bearish"):
        score -= 10

    # ── 7. Consolidation Breakout Bias (10 pts) ──
    # Consolidation followed by uptrend = very powerful
    # We check if both are true simultaneously
    consolidating = consolidation.get("consolidation", False)
    if consolidating and trend_bullish:
        score += 10   # Compressed + bullish = loaded spring
    elif consolidating and "DOWNTREND" in str(trend.get("trend_state", "")):
        score -= 5    # Consolidation in downtrend = possible bear flag

    return max(0, min(100, round(score)))


# ════════════════════════════════════════════════
# MASTER FUNCTION — called by app.py and scoring_engine
# ════════════════════════════════════════════════

def get_market_structure_analysis(stock_name, data):
    """
    Full market structure analysis pipeline.
    Runs all 11 functions and computes the structure score.

    Parameters:
      stock_name : e.g. "RELIANCE"
      data       : OHLCV DataFrame (60+ candles recommended)

    Returns a complete result dict with:
      - trend_state, trend_score
      - support, resistance zones
      - breakout, breakdown status
      - consolidation, squeeze status
      - HH/HL, LH/LL counts
      - market_structure_score (0-100)
      - plain English summary
    """
    result = {
        "stock_name":            stock_name,
        "trend_state":           "UNKNOWN",
        "trend_score":           50,
        "market_structure_score":50,
        "support_zones":         [],
        "resistance_zones":      [],
        "nearest_support":       None,
        "nearest_resistance":    None,
        "breakout":              {"breakout": False},
        "breakdown":             {"breakdown": False},
        "consolidation":         {"consolidation": False, "compression_score": 0},
        "squeeze":               {"squeeze_active": False, "squeeze_strength": "NONE"},
        "hh_count":              0,
        "hl_count":              0,
        "lh_count":              0,
        "ll_count":              0,
        "swing_highs":           [],
        "swing_lows":            [],
        "data_available":        False,
        "summary":               "Insufficient data for market structure analysis.",
    }

    try:
        if data is None or len(data) < 30:
            return result

        # Run all detectors
        trend        = classify_trend_structure(data)
        support_z    = detect_support_zones(data)
        resistance_z = detect_resistance_zones(data)
        breakout     = detect_breakout(data)
        breakdown    = detect_breakdown(data)
        consolidation= detect_consolidation(data)
        squeeze      = detect_volatility_squeeze(data)
        hh_hl        = detect_hh_hl(data)
        lh_ll        = detect_lh_ll(data)

        # Calculate composite score
        ms_score = calculate_market_structure_score(
            trend, support_z, resistance_z,
            breakout, breakdown, consolidation,
            squeeze, hh_hl, lh_ll, data
        )

        # Nearest support and resistance to current price
        latest_close = float(data["Close"].iloc[-1])
        nearest_sup = None
        nearest_res = None

        if support_z:
            below = [z for z in support_z if z["price"] <= latest_close]
            if below:
                nearest_sup = min(below, key=lambda z: latest_close - z["price"])

        if resistance_z:
            above = [z for z in resistance_z if z["price"] >= latest_close]
            if above:
                nearest_res = min(above, key=lambda z: z["price"] - latest_close)

        result.update({
            "stock_name":            stock_name,
            "trend_state":           trend["trend_state"],
            "trend_score":           trend["trend_score"],
            "market_structure_score":ms_score,
            "support_zones":         support_z[:3],     # Top 3 strongest
            "resistance_zones":      resistance_z[:3],
            "nearest_support":       nearest_sup,
            "nearest_resistance":    nearest_res,
            "breakout":              breakout,
            "breakdown":             breakdown,
            "consolidation":         consolidation,
            "squeeze":               squeeze,
            "hh_count":              hh_hl["hh_count"],
            "hl_count":              hh_hl["hl_count"],
            "lh_count":              lh_ll["lh_count"],
            "ll_count":              lh_ll["ll_count"],
            "swing_highs":           hh_hl["swing_highs"],
            "swing_lows":            hh_hl["swing_lows"],
            "ema20":                 trend["ema20"],
            "ema50":                 trend["ema50"],
            "data_available":        True,
            "summary":               _build_ms_summary(
                trend, breakout, breakdown,
                consolidation, squeeze, hh_hl, lh_ll, ms_score
            ),
        })

    except Exception as e:
        result["summary"] = f"Market structure analysis error: {e}"

    return result


def _build_ms_summary(trend, breakout, breakdown, consolidation, squeeze, hh_hl, lh_ll, score):
    """Plain English summary of the market structure."""
    lines = []

    trend_state = trend.get("trend_state", "UNKNOWN")

    if "STRONG UPTREND" in trend_state:
        lines.append(
            f"✅ **Strong Uptrend** — price making higher highs AND higher lows. "
            f"Price is above EMA20 and EMA50. Structure is solidly bullish."
        )
    elif "UPTREND" in trend_state:
        lines.append(
            f"📈 **Uptrend** — stock is making a series of higher swings. "
            f"Trend structure supports long positions."
        )
    elif "STRONG DOWNTREND" in trend_state:
        lines.append(
            f"🔻 **Strong Downtrend** — price making lower highs and lower lows. "
            f"Avoid new longs until structure improves."
        )
    elif "DOWNTREND" in trend_state:
        lines.append(
            f"📉 **Downtrend** — bearish swing structure. Exercise caution."
        )
    else:
        lines.append(
            f"↔️ **Sideways** — no clear directional structure. "
            f"Wait for a breakout from this range."
        )

    # HH/HL detail
    hh = hh_hl.get("hh_count", 0)
    hl = hh_hl.get("hl_count", 0)
    lh = lh_ll.get("lh_count", 0)
    ll = lh_ll.get("ll_count", 0)

    if hh or hl:
        lines.append(f"Swing structure: {hh} Higher High(s), {hl} Higher Low(s).")
    if lh or ll:
        lines.append(f"Bearish signals: {lh} Lower High(s), {ll} Lower Low(s).")

    # Breakout / Breakdown
    if breakout.get("breakout"):
        vol_note = "volume confirmed ✅" if breakout.get("volume_confirmed") else "⚠️ low volume"
        lines.append(
            f"🚀 **Breakout detected** above resistance ₹{breakout.get('resistance_level', '?')} "
            f"(+{breakout.get('distance_pct', 0)}%) — {vol_note}."
        )
    elif breakdown.get("breakdown"):
        lines.append(
            f"🔻 **Breakdown detected** below support ₹{breakdown.get('support_level', '?')} "
            f"(-{breakdown.get('distance_pct', 0)}%). Bearish structural damage."
        )

    # Squeeze
    if squeeze.get("squeeze_active"):
        lines.append(
            f"⚡ **Volatility Squeeze Active** — BB width in bottom "
            f"{squeeze.get('bb_width_percentile', '?')}% of recent range. "
            f"Big move likely soon."
        )

    # Consolidation
    if consolidation.get("consolidation"):
        lines.append(
            f"📦 **Consolidation phase** — ATR and Bollinger Width both compressing. "
            f"Compression score: {consolidation.get('compression_score', 0)}/100."
        )

    lines.append(f"**Market Structure Score: {score}/100**")

    return " ".join(lines)


def get_market_structure_score_only(data):
    """
    Lightweight wrapper — returns integer score 0-100.
    Called by scoring_engine.py.
    Returns neutral 50 on any failure.
    """
    try:
        result = get_market_structure_analysis("", data)
        return result["market_structure_score"]
    except Exception:
        return 50
