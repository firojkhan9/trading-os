# ================================================
# FILE: strategies/volume_engine.py
# PURPOSE: Volume Intelligence Engine — Milestone 27
#
# WHY VOLUME MATTERS:
#   Price tells you WHAT is happening.
#   Volume tells you HOW MUCH the market believes it.
#
#   A BUY signal with high volume = strong conviction
#   A BUY signal with low volume  = weak, possibly fake
#
# WHAT WE CALCULATE:
#   1. Volume Ratio    — today vs 20-day average
#   2. Volume Trend    — is volume rising or falling over 5 days?
#   3. OBV             — On-Balance Volume (accumulation vs distribution)
#   4. OBV Trend       — is OBV rising (smart money buying)?
#   5. CMF             — Chaikin Money Flow (net buying pressure)
#   6. Breakout Check  — did price move significantly AND volume confirm?
#   7. Volume Score    — 0-100 composite from all the above
#
# THE GOLDEN RULE (from master prompt):
#   Any BUY signal with volume < average volume
#   gets confidence reduced by 20%.
#   Enforced via get_volume_confidence_penalty().
#
# HOW IT CONNECTS:
#   scoring_engine.py      <- calls get_volume_score_only()
#   app.py (Tab 4)         <- calls get_volume_analysis() for full display
#   performance_scanner.py <- calls get_volume_score_only() for scan
#   execution_loop.py      <- already calls scoring_engine, gets it automatically
# ================================================

import pandas as pd
import numpy as np


# ── Settings ──────────────────────────────────────
VOLUME_MA_PERIOD    = 20    # Days for average volume baseline
VOLUME_SPIKE_RATIO  = 2.0   # >2x average = significant spike
VOLUME_HIGH_RATIO   = 1.5   # >1.5x = above average (good confirmation)
VOLUME_LOW_RATIO    = 0.7   # <0.7x = low volume (weak signal)
CMF_PERIOD          = 20    # Chaikin Money Flow lookback
OBV_TREND_DAYS      = 5     # Days to measure OBV trend direction
BREAKOUT_PCT        = 1.5   # Price move > 1.5% = significant move


# ════════════════════════════════════════════════
# INDICATOR CALCULATIONS
# ════════════════════════════════════════════════

def calculate_volume_ma(data, period=VOLUME_MA_PERIOD):
    """
    Rolling average volume over N days.
    This is our baseline for what is 'normal' volume for this stock.
    """
    data = data.copy()
    data['Volume_MA'] = data['Volume'].rolling(window=period).mean().round(0)
    return data


def calculate_volume_ratio(data):
    """
    Today's volume as a ratio of the 20-day average.

    Ratio = 1.0 -> exactly average
    Ratio = 2.0 -> double the average (spike)
    Ratio = 0.5 -> half the average (very quiet)

    Normalises volume across stocks — 2x means the same
    for RELIANCE as for ITC.
    """
    data = data.copy()
    if 'Volume_MA' not in data.columns:
        data = calculate_volume_ma(data)

    data['Volume_Ratio'] = (data['Volume'] / data['Volume_MA']).round(3)
    data['Volume_Ratio'] = data['Volume_Ratio'].replace(
        [float('inf'), float('-inf')], None
    )
    return data


def calculate_obv(data):
    """
    On-Balance Volume (OBV) — Granville's classic indicator.

    If close > yesterday: ADD today's volume to OBV
    If close < yesterday: SUBTRACT today's volume from OBV
    If same: OBV unchanged

    Rising OBV = smart money accumulating
    Falling OBV = smart money distributing
    """
    data   = data.copy()
    obv    = [0]
    closes = data['Close'].tolist()
    vols   = data['Volume'].tolist()

    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + vols[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - vols[i])
        else:
            obv.append(obv[-1])

    data['OBV']    = obv
    data['OBV_MA'] = data['OBV'].rolling(window=OBV_TREND_DAYS).mean()

    data['OBV_Direction'] = 0
    data.loc[data['OBV'] > data['OBV_MA'], 'OBV_Direction'] =  1
    data.loc[data['OBV'] < data['OBV_MA'], 'OBV_Direction'] = -1

    return data


def calculate_cmf(data, period=CMF_PERIOD):
    """
    Chaikin Money Flow (CMF) — net buying vs selling pressure.

    Money Flow Multiplier = ((Close-Low)-(High-Close)) / (High-Low)
    Money Flow Volume     = MFM * Volume
    CMF = Sum(MFV, N days) / Sum(Volume, N days)

    CMF > +0.20 = strong buying pressure
    CMF < -0.20 = strong selling pressure
    """
    data  = data.copy()
    high  = data['High']
    low   = data['Low']
    close = data['Close']
    vol   = data['Volume']

    hl_range = (high - low).replace(0, float('nan'))
    mfm = ((close - low) - (high - close)) / hl_range
    mfv = mfm * vol

    data['CMF'] = (
        mfv.rolling(window=period).sum() /
        vol.rolling(window=period).sum()
    ).round(4)

    return data


def calculate_volume_trend(data, days=5):
    """
    Is volume trending up or down over the last N days?
    Compares recent N-day average vs prior N-day average.

    Returns: 'RISING', 'FALLING', or 'FLAT'
    """
    recent_vol = data['Volume'].tail(days).mean()
    prior_vol  = data['Volume'].iloc[-(days * 2):-days].mean()

    if prior_vol and prior_vol > 0:
        change_pct = ((recent_vol - prior_vol) / prior_vol) * 100
        if change_pct > 10:
            return 'RISING 📈'
        elif change_pct < -10:
            return 'FALLING 📉'
    return 'FLAT ↔️'


def detect_volume_breakout(data):
    """
    Did price AND volume both move significantly today?

    True breakout = price > BREAKOUT_PCT move + volume >= average
    Fake breakout = price moved but volume was absent

    Returns a descriptive string.
    """
    if 'Volume_Ratio' not in data.columns:
        data = calculate_volume_ratio(data)

    latest = data.iloc[-1]
    prev   = data.iloc[-2]

    try:
        vol_ratio  = float(latest['Volume_Ratio']) if latest['Volume_Ratio'] is not None else 1.0
        price_move = ((float(latest['Close']) - float(prev['Close'])) / float(prev['Close'])) * 100
    except Exception:
        return 'NORMAL 📊'

    volume_above = vol_ratio >= 1.0
    big_move     = abs(price_move) >= BREAKOUT_PCT

    if big_move and volume_above and price_move > 0:
        return 'CONFIRMED BREAKOUT 🚀'
    elif big_move and volume_above and price_move < 0:
        return 'CONFIRMED BREAKDOWN 🔻'
    elif big_move and not volume_above:
        return 'WEAK MOVE ⚠️'
    elif vol_ratio >= VOLUME_SPIKE_RATIO and not big_move:
        return 'HIGH VOLUME ↔️'
    else:
        return 'NORMAL 📊'


# ════════════════════════════════════════════════
# FULL VOLUME ANALYSIS — runs all indicators
# ════════════════════════════════════════════════

def analyse_volume(data):
    """
    Run all volume indicators on OHLCV dataframe.
    Returns enriched dataframe. Never crashes.
    """
    data = data.copy()
    data = data[data['Volume'] > 0].copy()

    if len(data) < VOLUME_MA_PERIOD + 5:
        for col in ['Volume_MA', 'Volume_Ratio', 'OBV', 'OBV_Direction', 'CMF']:
            data[col] = None
        return data

    data = calculate_volume_ma(data)
    data = calculate_volume_ratio(data)
    data = calculate_obv(data)
    data = calculate_cmf(data)
    return data


# ════════════════════════════════════════════════
# VOLUME SCORE — 0-100
# ════════════════════════════════════════════════

def calculate_volume_score(data):
    """
    Build a 0-100 volume score from all indicators.

    Scoring:
      Volume Ratio:
        >= 2.0x  +25  (strong conviction)
        >= 1.5x  +15  (above average)
        >= 1.0x  +5   (average)
        >= 0.7x  -10  (below average)
        <  0.7x  -30  (very low — weak signal)

      OBV Direction:
        Rising   +15  (accumulation)
        Falling  -15  (distribution)

      CMF:
        >= +0.20 +20  (strong buying)
        >= +0.05 +10  (mild buying)
        <= -0.20 -20  (strong selling)
        <= -0.05 -10  (mild selling)

      Volume Trend (5-day):
        Rising   +5
        Falling  -5
    """
    try:
        enriched = analyse_volume(data)
        if enriched.empty or len(enriched) < 2:
            return 50

        latest = enriched.iloc[-1]
        score  = 50

        # Volume Ratio
        try:
            vr = latest.get('Volume_Ratio')
            if vr is not None and not pd.isna(vr):
                vr = float(vr)
                if vr >= VOLUME_SPIKE_RATIO:   score += 25
                elif vr >= VOLUME_HIGH_RATIO:  score += 15
                elif vr >= 1.0:                score += 5
                elif vr >= VOLUME_LOW_RATIO:   score -= 10
                else:                          score -= 30
        except Exception:
            pass

        # OBV Direction
        try:
            od = latest.get('OBV_Direction')
            if od is not None and not pd.isna(od):
                od = int(float(od))
                if od == 1:   score += 15
                elif od == -1: score -= 15
        except Exception:
            pass

        # CMF
        try:
            cmf = latest.get('CMF')
            if cmf is not None and not pd.isna(cmf):
                cmf = float(cmf)
                if cmf >= 0.20:    score += 20
                elif cmf >= 0.05:  score += 10
                elif cmf <= -0.20: score -= 20
                elif cmf <= -0.05: score -= 10
        except Exception:
            pass

        # Volume Trend
        trend = calculate_volume_trend(enriched)
        if 'RISING'  in trend: score += 5
        elif 'FALLING' in trend: score -= 5

        return max(0, min(100, round(score)))

    except Exception:
        return 50


def get_volume_score_only(data):
    """
    Lightweight wrapper — returns integer score 0-100.
    Called by scoring_engine.py and performance_scanner.py.
    Always returns 50 on any failure.
    """
    try:
        return calculate_volume_score(data)
    except Exception:
        return 50


# ════════════════════════════════════════════════
# THE GOLDEN RULE — Confidence Penalty
# ════════════════════════════════════════════════

def get_volume_confidence_penalty(data, combined_signal):
    """
    Golden Rule: BUY signal + volume below average = 20% confidence penalty.

    Returns:
      penalty        : float (0.0 = no penalty, 0.20 = 20% reduction)
      penalty_reason : plain English explanation
    """
    try:
        enriched = analyse_volume(data)
        if enriched.empty:
            return 0.0, ""

        latest = enriched.iloc[-1]
        vr     = latest.get('Volume_Ratio')
        if vr is None or pd.isna(vr):
            return 0.0, ""

        vol_ratio = float(vr)
        is_buy    = "BUY" in str(combined_signal).upper()

        if is_buy and vol_ratio < 1.0:
            return 0.20, (
                f"BUY signal detected but volume is only "
                f"{round(vol_ratio, 2)}x average — below the 1.0x threshold. "
                f"Confidence reduced by 20%. Wait for volume to confirm."
            )
        return 0.0, ""

    except Exception:
        return 0.0, ""


# ════════════════════════════════════════════════
# FULL ANALYSIS — called by app.py Tab 4
# ════════════════════════════════════════════════

def get_volume_analysis(data):
    """
    Full volume analysis dict for dashboard display.
    Returns all metrics, labels, score, and interpretation.
    """
    try:
        enriched = analyse_volume(data)
        if enriched.empty or len(enriched) < 2:
            return _empty_analysis()

        latest = enriched.iloc[-1]

        # Raw values
        curr_vol  = int(latest['Volume'])    if not pd.isna(latest['Volume'])    else 0
        vol_ma    = int(latest['Volume_MA']) if not pd.isna(latest['Volume_MA']) else 0

        vr_raw    = latest.get('Volume_Ratio')
        vol_ratio = round(float(vr_raw), 2) if vr_raw is not None and not pd.isna(vr_raw) else None

        cmf_raw   = latest.get('CMF')
        cmf       = round(float(cmf_raw), 4) if cmf_raw is not None and not pd.isna(cmf_raw) else None

        obv_raw   = latest.get('OBV')
        obv       = int(float(obv_raw)) if obv_raw is not None and not pd.isna(obv_raw) else None

        obv_dir_raw = latest.get('OBV_Direction')
        obv_dir   = int(float(obv_dir_raw)) if obv_dir_raw is not None and not pd.isna(obv_dir_raw) else 0

        # Labels
        if vol_ratio is not None:
            if vol_ratio >= VOLUME_SPIKE_RATIO:
                vol_label = f"SPIKE 🔥 ({vol_ratio}x avg)"
            elif vol_ratio >= VOLUME_HIGH_RATIO:
                vol_label = f"HIGH 📈 ({vol_ratio}x avg)"
            elif vol_ratio >= 1.0:
                vol_label = f"AVERAGE 📊 ({vol_ratio}x avg)"
            elif vol_ratio >= VOLUME_LOW_RATIO:
                vol_label = f"BELOW AVG 📉 ({vol_ratio}x avg)"
            else:
                vol_label = f"VERY LOW ⚠️ ({vol_ratio}x avg)"
        else:
            vol_label = "N/A"

        obv_label = (
            "RISING 📈 — Smart money buying"  if obv_dir ==  1 else
            "FALLING 📉 — Smart money selling" if obv_dir == -1 else
            "FLAT ↔️ — No clear direction"
        )

        if cmf is not None:
            if cmf >= 0.20:     cmf_label = f"STRONG BUYING 🟢 ({cmf})"
            elif cmf >= 0.05:   cmf_label = f"MILD BUYING 🟡 ({cmf})"
            elif cmf <= -0.20:  cmf_label = f"STRONG SELLING 🔴 ({cmf})"
            elif cmf <= -0.05:  cmf_label = f"MILD SELLING 🟠 ({cmf})"
            else:               cmf_label = f"NEUTRAL ⚪ ({cmf})"
        else:
            cmf_label = "N/A"

        vol_trend    = calculate_volume_trend(enriched)
        breakout_sig = detect_volume_breakout(enriched)
        vol_score    = calculate_volume_score(data)

        return {
            "volume_score":    vol_score,
            "current_volume":  curr_vol,
            "avg_volume":      vol_ma,
            "volume_ratio":    vol_ratio,
            "volume_label":    vol_label,
            "volume_trend":    vol_trend,
            "obv":             obv,
            "obv_label":       obv_label,
            "cmf":             cmf,
            "cmf_label":       cmf_label,
            "breakout_signal": breakout_sig,
            "interpretation":  _build_interpretation(vol_ratio, obv_dir, cmf, vol_trend, breakout_sig),
            "data_available":  True,
            "enriched_data":   enriched,
        }

    except Exception as e:
        result = _empty_analysis()
        result["error"] = str(e)
        return result


def _empty_analysis():
    return {
        "volume_score":    50,
        "current_volume":  0,
        "avg_volume":      0,
        "volume_ratio":    None,
        "volume_label":    "N/A — insufficient data",
        "volume_trend":    "N/A",
        "obv":             None,
        "obv_label":       "N/A",
        "cmf":             None,
        "cmf_label":       "N/A",
        "breakout_signal": "N/A",
        "interpretation":  "Not enough data to analyse volume.",
        "data_available":  False,
        "enriched_data":   pd.DataFrame(),
    }


def _build_interpretation(vol_ratio, obv_dir, cmf, vol_trend, breakout_sig):
    """Plain English summary of what volume is saying."""
    lines = []

    if vol_ratio is not None:
        if vol_ratio >= VOLUME_SPIKE_RATIO:
            lines.append(
                f"Volume is {vol_ratio}x the 20-day average — a significant spike. "
                "This level of activity usually means institutional players are involved."
            )
        elif vol_ratio >= VOLUME_HIGH_RATIO:
            lines.append(
                f"Volume is {vol_ratio}x average — above normal. "
                "Good confirmation for any price signal today."
            )
        elif vol_ratio < VOLUME_LOW_RATIO:
            lines.append(
                f"Volume is only {vol_ratio}x average — well below normal. "
                "Any price signal today should be treated with caution. "
                "Low volume moves are often reversed quickly."
            )
        else:
            lines.append(
                f"Volume is close to the 20-day average ({vol_ratio}x) — nothing unusual."
            )

    if obv_dir == 1:
        lines.append(
            "OBV is rising — smart money is quietly accumulating. "
            "Bullish even if the price hasn't moved much yet."
        )
    elif obv_dir == -1:
        lines.append(
            "OBV is falling — institutions may be distributing (selling quietly). "
            "A warning even if price looks stable."
        )

    if cmf is not None:
        if cmf >= 0.20:
            lines.append(
                f"Chaikin Money Flow is strongly positive ({cmf}) — "
                "price consistently closes near highs. Strong buying pressure."
            )
        elif cmf <= -0.20:
            lines.append(
                f"Chaikin Money Flow is strongly negative ({cmf}) — "
                "price consistently closes near lows. Strong selling pressure."
            )

    if "CONFIRMED BREAKOUT" in str(breakout_sig):
        lines.append(
            "Today's price move is CONFIRMED by volume. "
            "This is the kind of breakout worth paying attention to."
        )
    elif "WEAK MOVE" in str(breakout_sig):
        lines.append(
            "Price moved today but volume did NOT confirm it. "
            "Low-conviction move — wait for volume to follow before acting."
        )

    return " ".join(lines) if lines else "Volume data within normal ranges — no strong signal."