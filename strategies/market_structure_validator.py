# ================================================
# FILE: strategies/market_structure_validator.py
# PURPOSE: Market Structure Validation + Supply/Demand Zones
#          Milestone 38C — Modules 4 & 5 of the Volume
#          Compression Pullback Strategy (VCPS) intraday spec.
#
# WHAT THIS DOES:
#   Takes the eligible stock list from M38B (Stock Selection
#   Filter) and validates each one's PRICE STRUCTURE before it's
#   allowed anywhere near an entry decision (that's M38D).
#
#   For each stock this module answers three questions:
#     1. STRUCTURE  — Is this stock trending (UPTREND/DOWNTREND)
#                      or just going sideways (RANGE)?
#                      Only UPTREND/DOWNTREND stocks survive —
#                      RANGE is rejected outright (per spec).
#     2. BOS/CHOCH   — Has price just confirmed the trend
#                      continuing (Break of Structure) or is it
#                      warning of a reversal (Change of Character)?
#     3. ZONES       — Where is the nearest Demand zone (support
#                      cluster, for longs) and Supply zone
#                      (resistance cluster, for shorts)? How close
#                      is price to it right now?
#
# WHY THIS MATTERS:
#   Module 8 (entry logic, upcoming M38D) needs a stock to be
#   BOTH trending AND near a supply/demand zone before it will
#   even look for a compression/pullback entry. This module is
#   the gate that produces that "is this stock even in play"
#   answer — with full reasons logged either way, same as every
#   other engine in this project.
#
# REUSES (does not duplicate):
#   strategies/market_structure.py:
#     - classify_trend_structure()   -> trend_state, HH/HL/LH/LL counts
#     - detect_swing_highs/lows()    -> raw swing points
#     - detect_support_zones()       -> clustered support (-> Demand)
#     - detect_resistance_zones()    -> clustered resistance (-> Supply)
#
# HOW IT CONNECTS:
#   strategies/stock_selection_filter.py -> get_eligible_intraday_stocks()
#                                            feeds the stock universe in
#   Upcoming M38D (intraday entry logic) will call
#   get_intraday_trade_candidates() to get the final validated list
#   with structure + zones attached, ready for compression/pullback
#   entry detection.
# ================================================

import pandas as pd
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from strategies.market_structure import (
    classify_trend_structure,
    detect_swing_highs,
    detect_swing_lows,
    detect_support_zones,
    detect_resistance_zones,
    SWING_LOOKBACK,
)
from strategies.stock_selection_filter import get_eligible_intraday_stocks

try:
    from config.settings import SCANNER_MAX_WORKERS
except ImportError:
    SCANNER_MAX_WORKERS = 10

# ── Settings ──────────────────────────────────────
ZONE_BUFFER_PCT = 0.5    # % band width around a swing price to form a zone_low/zone_high range
DATA_PERIOD     = "3mo"  # enough history for swing + trend structure on daily candles


# ════════════════════════════════════════════════
# STRUCTURE TYPE — collapse trend_state to the
# 3-way UPTREND / DOWNTREND / RANGE the spec requires
# ════════════════════════════════════════════════

def _collapse_structure_type(trend_state: str) -> str:
    """
    market_structure.py returns 5 granular states.
    The VCPS spec only wants 3: UPTREND, DOWNTREND, RANGE.
    STRONG UPTREND and UPTREND both collapse to UPTREND, etc.
    """
    state = str(trend_state).upper()
    if "UPTREND" in state:
        return "UPTREND"
    if "DOWNTREND" in state:
        return "DOWNTREND"
    return "RANGE"


# ════════════════════════════════════════════════
# BOS / CHOCH DETECTION
# Break of Structure (trend continuation confirmation)
# Change of Character (early reversal warning)
# ════════════════════════════════════════════════

def _detect_bos_choch(data, structure_type, swing_highs, swing_lows):
    """
    BOS   — price breaks the most recent swing point IN the
            direction of the prevailing trend. Confirms the
            trend is continuing.
    CHOCH — price breaks the most recent swing point AGAINST
            the prevailing trend. Early warning the trend may
            be reversing — should block new entries in the old
            direction even if structure_type hasn't flipped yet.

    Returns dict: {
      bos_detected, bos_direction,
      choch_detected, choch_direction,
    }
    """
    result = {
        "bos_detected":    False,
        "bos_direction":   None,
        "choch_detected":  False,
        "choch_direction": None,
    }

    if data is None or len(data) < 2:
        return result

    latest_close = float(data["Close"].iloc[-1])
    recent_high  = swing_highs[0]["price"] if swing_highs else None
    recent_low   = swing_lows[0]["price"]  if swing_lows  else None

    if structure_type == "UPTREND":
        if recent_high is not None and latest_close > recent_high:
            result["bos_detected"]  = True
            result["bos_direction"] = "BULLISH"
        if recent_low is not None and latest_close < recent_low:
            result["choch_detected"]  = True
            result["choch_direction"] = "BEARISH"

    elif structure_type == "DOWNTREND":
        if recent_low is not None and latest_close < recent_low:
            result["bos_detected"]  = True
            result["bos_direction"] = "BEARISH"
        if recent_high is not None and latest_close > recent_high:
            result["choch_detected"]  = True
            result["choch_direction"] = "BULLISH"

    # RANGE — BOS/CHOCH not meaningful without a trend to break

    return result


# ════════════════════════════════════════════════
# SUPPLY / DEMAND ZONE BUILDER
# Converts a single support/resistance price point into
# a zone_low/zone_high band with a strength score.
# ════════════════════════════════════════════════

def _build_zone(price_point: dict, buffer_pct: float = ZONE_BUFFER_PCT) -> dict:
    """
    A raw support/resistance zone from market_structure.py has a
    single 'price'. Real supply/demand zones are a BAND, not a
    single price — this adds a small buffer around it so the
    zone has a zone_low and zone_high, as the spec requires.
    """
    price = price_point["price"]
    buf   = price * (buffer_pct / 100)

    return {
        "zone_low":      round(price - buf, 2),
        "zone_high":     round(price + buf, 2),
        "zone_mid":      price,
        "zone_strength": price_point.get("strength", 0),
        "touches":       price_point.get("touches", 1),
    }


def _find_nearest_zones(data, latest_close):
    """
    Find the nearest Demand zone (below price) and Supply zone
    (above price) using the existing support/resistance detection.
    Returns (demand_zone_dict_or_None, supply_zone_dict_or_None)
    """
    support_zones    = detect_support_zones(data)
    resistance_zones = detect_resistance_zones(data)

    demand_zone = None
    below = [z for z in support_zones if z["price"] <= latest_close]
    if below:
        nearest = min(below, key=lambda z: latest_close - z["price"])
        demand_zone = _build_zone(nearest)

    supply_zone = None
    above = [z for z in resistance_zones if z["price"] >= latest_close]
    if above:
        nearest = min(above, key=lambda z: z["price"] - latest_close)
        supply_zone = _build_zone(nearest)

    return demand_zone, supply_zone


# ════════════════════════════════════════════════
# MASTER VALIDATOR — one stock at a time
# ════════════════════════════════════════════════

def validate_market_structure(stock_name: str, data) -> dict:
    """
    Full Module 4 + 5 pipeline for a single stock.

    Returns a result dict with structure_type, BOS/CHOCH flags,
    nearest demand/supply zones, distance to each, and whether
    the stock is currently valid for a long or short setup.
    """
    result = {
        "stock_name":             stock_name,
        "structure_type":         "RANGE",
        "trend_state":            "UNKNOWN",
        "hh_count": 0, "hl_count": 0, "lh_count": 0, "ll_count": 0,
        "bos_detected":           False,
        "bos_direction":          None,
        "choch_detected":         False,
        "choch_direction":        None,
        "demand_zone":            None,
        "supply_zone":            None,
        "distance_to_demand_pct": None,
        "distance_to_supply_pct": None,
        "valid_for_long":         False,
        "valid_for_short":        False,
        "rejection_reason":       "",
        "data_available":         False,
    }

    if data is None or len(data) < 30:
        result["rejection_reason"] = "Insufficient price history for structure analysis"
        return result

    try:
        trend = classify_trend_structure(data, lookback=SWING_LOOKBACK)
        structure_type = _collapse_structure_type(trend["trend_state"])

        swing_highs = detect_swing_highs(data, lookback=SWING_LOOKBACK)
        swing_lows  = detect_swing_lows(data, lookback=SWING_LOOKBACK)

        bos_choch = _detect_bos_choch(data, structure_type, swing_highs, swing_lows)

        latest_close = float(data["Close"].iloc[-1])
        demand_zone, supply_zone = _find_nearest_zones(data, latest_close)

        dist_to_demand = None
        if demand_zone:
            dist_to_demand = round(
                (latest_close - demand_zone["zone_mid"]) / latest_close * 100, 2
            )

        dist_to_supply = None
        if supply_zone:
            dist_to_supply = round(
                (supply_zone["zone_mid"] - latest_close) / latest_close * 100, 2
            )

        # ── Valid for long: UPTREND + demand zone in play + no fresh bearish CHOCH ──
        valid_long = (
            structure_type == "UPTREND"
            and demand_zone is not None
            and not bos_choch["choch_detected"]
        )

        # ── Valid for short: DOWNTREND + supply zone in play + no fresh bullish CHOCH ──
        valid_short = (
            structure_type == "DOWNTREND"
            and supply_zone is not None
            and not bos_choch["choch_detected"]
        )

        reason = ""
        if structure_type == "RANGE":
            reason = "Structure is RANGE — no clear trend, rejected per spec (only UPTREND/DOWNTREND trade)"
        elif bos_choch["choch_detected"]:
            reason = (
                f"CHOCH detected ({bos_choch['choch_direction']}) — "
                f"trend may be reversing, blocking new "
                f"{'long' if structure_type == 'UPTREND' else 'short'} entries"
            )
        elif structure_type == "UPTREND" and demand_zone is None:
            reason = "UPTREND but no demand zone found nearby — nothing to anchor an entry to"
        elif structure_type == "DOWNTREND" and supply_zone is None:
            reason = "DOWNTREND but no supply zone found nearby — nothing to anchor an entry to"

        result.update({
            "structure_type":         structure_type,
            "trend_state":            trend["trend_state"],
            "hh_count":               trend["hh_count"],
            "hl_count":               trend["hl_count"],
            "lh_count":               trend["lh_count"],
            "ll_count":               trend["ll_count"],
            "bos_detected":           bos_choch["bos_detected"],
            "bos_direction":          bos_choch["bos_direction"],
            "choch_detected":         bos_choch["choch_detected"],
            "choch_direction":        bos_choch["choch_direction"],
            "demand_zone":            demand_zone,
            "supply_zone":            supply_zone,
            "distance_to_demand_pct": dist_to_demand,
            "distance_to_supply_pct": dist_to_supply,
            "valid_for_long":         valid_long,
            "valid_for_short":        valid_short,
            "rejection_reason":       reason,
            "data_available":         True,
        })

    except Exception as e:
        result["rejection_reason"] = f"Structure validation error: {e}"

    return result


# ════════════════════════════════════════════════
# BATCH VALIDATION — runs across the M38B eligible list
# ════════════════════════════════════════════════

def _fetch_data(symbol, period=DATA_PERIOD):
    try:
        data = yf.download(
            tickers=symbol, period=period,
            interval="1d", progress=False,
            auto_adjust=True,
        )
        if data.empty:
            return None
        data.columns = [col[0] for col in data.columns]
        data = data.dropna(subset=["Close"])
        data = data[data["Close"] > 0]
        if len(data) < 30:
            return None
        return data
    except Exception:
        return None


def validate_intraday_universe(
    eligible_stocks: list,
    max_workers: int = SCANNER_MAX_WORKERS,
) -> dict:
    """
    Run Module 4+5 structure validation across a list of
    already-eligible stocks (from M38B's get_eligible_intraday_stocks).

    eligible_stocks: list of dicts, each with at least
                      "stock" and "symbol" keys — same shape
                      as the "eligible" list M38B returns.

    Returns:
      {
        "validated": [...]   — passed structure + zone checks,
                                sorted by closest zone distance first
        "rejected":  [...]   — RANGE structure, CHOCH warning, or
                                no zone nearby — each with a reason
        "fetched_at": str,
        "data_available": bool,
      }
    """
    result = {
        "validated":      [],
        "rejected":       [],
        "fetched_at":     datetime.now().strftime('%d %b %Y %H:%M'),
        "data_available": False,
    }

    if not eligible_stocks:
        return result

    def _worker(item):
        stock_name = item["stock"]
        symbol     = item["symbol"]
        data = _fetch_data(symbol)
        sr   = validate_market_structure(stock_name, data)
        sr["symbol"] = symbol
        sr["sector"] = item.get("sector", "Unknown")
        # carry through M38B liquidity metrics for the next module
        sr["price"]           = item.get("price")
        sr["volume_ratio"]    = item.get("volume_ratio")
        sr["atr_pct"]         = item.get("atr_pct")
        sr["traded_value_cr"] = item.get("traded_value_cr")
        return sr

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, item): item for item in eligible_stocks}
        for future in as_completed(futures):
            try:
                sr = future.result()
            except Exception:
                continue

            if not sr["data_available"]:
                result["rejected"].append(sr)
                continue

            if sr["valid_for_long"] or sr["valid_for_short"]:
                result["validated"].append(sr)
            else:
                result["rejected"].append(sr)

    # Closest to an actionable zone first — most "ready" setups on top
    def _closest_distance(sr):
        candidates = [
            d for d in [sr.get("distance_to_demand_pct"), sr.get("distance_to_supply_pct")]
            if d is not None
        ]
        return min([abs(d) for d in candidates], default=999)

    result["validated"]      = sorted(result["validated"], key=_closest_distance)
    result["data_available"] = True
    return result


# ════════════════════════════════════════════════
# FULL PIPELINE — chains M38A -> M38B -> M38C
# One call gets you today's fully-validated intraday universe.
# ════════════════════════════════════════════════

def get_intraday_trade_candidates(
    top_n_sectors: int = 3,
    require_fo: bool = True,
    active_only: bool = True,
) -> dict:
    """
    Master convenience function — runs the entire M38A -> M38B -> M38C
    chain in one call:
      1. Rank sectors (M38A)          -> top N sectors
      2. Filter stocks (M38B)         -> F&O + liquidity eligible
      3. Validate structure (M38C)    -> trending + near a zone

    Returns the final candidate list M38D (entry logic) will consume.
    """
    selection = get_eligible_intraday_stocks(
        top_n_sectors=top_n_sectors,
        require_fo=require_fo,
        active_only=active_only,
    )

    if not selection["data_available"] or not selection["eligible"]:
        return {
            "candidates":         [],
            "structure_rejected": [],
            "top_sectors":        selection.get("top_sectors", []),
            "liquidity_rejected": selection.get("rejected", []),
            "fetched_at":         datetime.now().strftime('%d %b %Y %H:%M'),
            "data_available":     False,
        }

    structure_result = validate_intraday_universe(selection["eligible"])

    return {
        "candidates":         structure_result["validated"],
        "structure_rejected": structure_result["rejected"],
        "top_sectors":        selection["top_sectors"],
        "liquidity_rejected": selection["rejected"],
        "fetched_at":         structure_result["fetched_at"],
        "data_available":     structure_result["data_available"],
    }
