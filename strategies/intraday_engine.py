# ================================================
# FILE: strategies/intraday_engine.py
# PURPOSE: Intraday Entry Logic Engine — Milestone 38E
#          Module 8 of the Volume Compression Pullback
#          Strategy (VCPS) intraday specification.
#
# WHAT THIS DOES:
#   The final gate before a trade idea becomes a BUY/SELL signal.
#   Chains everything built so far:
#     M38A  Sector Strength         -> top 3 sectors only
#     M38B  Stock Selection         -> F&O + liquidity eligible
#     M38C  Market Structure        -> trending + near a Demand/Supply zone
#     M38D  Direction + Compression -> market gate + exhaustion pullback
#     M38E  Entry Logic (this file) -> breakout trigger -> BUY/SELL
#
# LONG SETUP (per spec):
#   Market Regime = BULLISH
#   Sector Rank <= 3        (already guaranteed — M38C only sees top-3-sector stocks)
#   Structure = UPTREND
#   Volume Compression = True
#   Volatility Compression = True
#   Price near Demand Zone
#   Entry Trigger: break ABOVE the high of the compression candle
#
# SHORT SETUP — exact mirror using Supply zone and breaking below the low.
#
# WHY THE "COMPRESSION CANDLE" IS data.iloc[-2]:
#   Compression is measured on the most recently CLOSED 5-min bar.
#   By the time this engine is called again (next poll), a new bar
#   has formed. So on every call we treat the second-to-last bar as
#   "the compression candle flagged last cycle" and check whether the
#   newest bar has broken its high/low. This keeps the engine fully
#   stateless — no need to remember what happened on the previous
#   poll, consistent with every other engine in this project
#   (candlestick_engine.py, market_structure.py, etc. are all
#   stateless, called fresh each time).
#
# REUSES (does not duplicate):
#   strategies/market_structure_validator.py -> get_intraday_trade_candidates()
#                                                (chains M38A -> B -> C)
#                                             -> validate_market_structure(), _fetch_data()
#   strategies/intraday_direction.py         -> get_intraday_direction_analysis()
#                                                (Module 1 gate)
#                                             -> batch_compression_check(),
#                                                detect_volume_compression(),
#                                                detect_volatility_compression()
#                                                (Modules 6 + 7)
#                                             -> _fetch_intraday_data()
#                                                (5-min OHLCV fetch)
#
# HOW IT CONNECTS:
#   app.py Tab 2          -> scan_intraday_entries() for the dashboard button
#   Upcoming M38F (stop loss + target engine) will consume the
#   long_signals / short_signals lists this module returns — each
#   signal already carries the compression candle high/low and the
#   demand/supply zone needed to calculate stops.
# ================================================

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from strategies.market_structure_validator import (
    get_intraday_trade_candidates,
    validate_market_structure,
    DATA_PERIOD,
    _fetch_data,
)
from strategies.intraday_direction import (
    get_intraday_direction_analysis,
    batch_compression_check,
    detect_volume_compression,
    detect_volatility_compression,
    _fetch_intraday_data,
)

try:
    from config.settings import SCANNER_MAX_WORKERS
except ImportError:
    SCANNER_MAX_WORKERS = 10

import pandas as pd

# ── M38F: Risk Management Settings (Module 9 + 10) ────────
ATR_STOP_PERIOD     = 14    # 5-min bars used for the ATR stop component
ATR_STOP_MULTIPLIER = 1.5   # ATR Stop = entry -/+ (ATR x multiplier)
EMA_TRAIL_PERIOD    = 10    # Target 3 — dynamic trailing exit reference (10 EMA)
RISK_REWARD_TARGET1 = 2.0   # Target 1 = entry +/- (risk_per_share x 2R)


# ════════════════════════════════════════════════
# ENTRY TRIGGER — breakout of the compression candle
# ════════════════════════════════════════════════

def _check_breakout_trigger(symbol: str, direction: str, data=None) -> dict:
    """
    direction: "LONG" or "SHORT"

    Treats the second-to-last 5-min bar as the compression candle
    and checks whether the latest bar has broken its high (LONG)
    or low (SHORT). Fetches fresh 5-min data if not supplied.
    """
    result = {
        "triggered":               False,
        "compression_candle_high": None,
        "compression_candle_low":  None,
        "trigger_price":           None,
        "latest_close":            None,
        "latest_high":             None,
        "latest_low":              None,
        "reason":                  "",
        "data_available":          False,
    }

    if data is None:
        data = _fetch_intraday_data(symbol)

    if data is None or len(data) < 2:
        result["reason"] = "Insufficient 5-min data for breakout check"
        return result

    try:
        compression_candle = data.iloc[-2]
        latest_candle      = data.iloc[-1]

        comp_high    = round(float(compression_candle["High"]), 2)
        comp_low     = round(float(compression_candle["Low"]),  2)
        latest_high  = round(float(latest_candle["High"]),  2)
        latest_low   = round(float(latest_candle["Low"]),   2)
        latest_close = round(float(latest_candle["Close"]), 2)

        if direction == "LONG":
            triggered     = latest_high > comp_high
            trigger_price = comp_high
            reason = (
                f"{'✅ Broke above' if triggered else 'Waiting to break above'} "
                f"compression candle high ₹{comp_high} — latest high ₹{latest_high}"
            )
        else:   # SHORT
            triggered     = latest_low < comp_low
            trigger_price = comp_low
            reason = (
                f"{'✅ Broke below' if triggered else 'Waiting to break below'} "
                f"compression candle low ₹{comp_low} — latest low ₹{latest_low}"
            )

        result.update({
            "triggered":               triggered,
            "compression_candle_high": comp_high,
            "compression_candle_low":  comp_low,
            "trigger_price":           trigger_price,
            "latest_close":            latest_close,
            "latest_high":             latest_high,
            "latest_low":              latest_low,
            "reason":                  reason,
            "data_available":          True,
        })

    except Exception as e:
        result["reason"] = f"Breakout check error: {e}"

    return result


# ════════════════════════════════════════════════
# M38F — RISK MANAGEMENT ENGINE (Module 9 + 10)
# Stop Loss Engine + Target Engine
# ════════════════════════════════════════════════

def calculate_stop_loss(
    direction: str,
    entry_price: float,
    zone: dict,
    compression_candle_high,
    compression_candle_low,
    atr_value,
) -> dict:
    """
    Module 9 — Stop Loss Engine.

    LONG:  Stop = max(Demand Zone Low, Compression Candle Low, ATR Stop)
           -> the HIGHEST of the three (closest to entry) is the tightest,
              most protective stop, per spec.
    SHORT: Stop = min(Supply Zone High, Compression Candle High, ATR Stop)
           -> the LOWEST of the three is the tightest stop.

    zone: the entry-side zone (demand_zone for LONG, supply_zone for SHORT)
    atr_value: current ATR on 5-min bars, or None if unavailable

    Returns None if no candidate stop could be built, or if the computed
    stop lands on the wrong side of entry (invalid setup — reject).
    """
    candidates = {}

    if direction == "LONG":
        if zone and zone.get("zone_low") is not None:
            candidates["Demand Zone Low"] = round(float(zone["zone_low"]), 2)
        if compression_candle_low is not None:
            candidates["Compression Candle Low"] = round(float(compression_candle_low), 2)
        if atr_value is not None:
            candidates["ATR Stop"] = round(entry_price - (atr_value * ATR_STOP_MULTIPLIER), 2)

        if not candidates:
            return None

        stop_basis = max(candidates, key=candidates.get)
        stop_price = candidates[stop_basis]
        risk_per_share = round(entry_price - stop_price, 2)

    else:   # SHORT
        if zone and zone.get("zone_high") is not None:
            candidates["Supply Zone High"] = round(float(zone["zone_high"]), 2)
        if compression_candle_high is not None:
            candidates["Compression Candle High"] = round(float(compression_candle_high), 2)
        if atr_value is not None:
            candidates["ATR Stop"] = round(entry_price + (atr_value * ATR_STOP_MULTIPLIER), 2)

        if not candidates:
            return None

        stop_basis = min(candidates, key=candidates.get)
        stop_price = candidates[stop_basis]
        risk_per_share = round(stop_price - entry_price, 2)

    if risk_per_share <= 0:
        return None   # Stop landed on the wrong side of entry — invalid, reject

    return {
        "stop_price":      stop_price,
        "risk_per_share":  risk_per_share,
        "stop_basis":      stop_basis,
        "stop_candidates": candidates,
    }


def calculate_targets(
    direction: str,
    entry_price: float,
    stop_price: float,
    risk_per_share: float,
    opposite_zone: dict,
) -> dict:
    """
    Module 10 — Target Engine.

    Target 1: 2R — twice the risk_per_share distance from entry.
    Target 2: nearest edge of the OPPOSITE zone
              (Supply Zone for LONG, Demand Zone for SHORT).
              None if no opposite zone was found nearby.
    Target 3 (EMA Trail) is handled separately by get_ema_trail_info() —
    it's a dynamic rule, not a fixed price.
    """
    if direction == "LONG":
        target_1 = round(entry_price + (risk_per_share * RISK_REWARD_TARGET1), 2)
        target_2 = None
        if opposite_zone and opposite_zone.get("zone_low") is not None:
            target_2 = round(float(opposite_zone["zone_low"]), 2)   # nearest Supply edge
    else:   # SHORT
        target_1 = round(entry_price - (risk_per_share * RISK_REWARD_TARGET1), 2)
        target_2 = None
        if opposite_zone and opposite_zone.get("zone_high") is not None:
            target_2 = round(float(opposite_zone["zone_high"]), 2)  # nearest Demand edge

    target_2_rr = None
    if target_2 is not None and risk_per_share > 0:
        target_2_rr = round(abs(target_2 - entry_price) / risk_per_share, 2)

    return {
        "target_1":    target_1,
        "target_1_rr": RISK_REWARD_TARGET1,
        "target_2":    target_2,
        "target_2_rr": target_2_rr,
    }


def get_ema_trail_info(data, period: int = EMA_TRAIL_PERIOD) -> dict:
    """
    Module 10 — Target 3: EMA Trail Exit.

    Not a fixed price — a dynamic trailing rule. Per the original spec,
    the remaining position exits when price closes above/below the 10 EMA
    and breaks the high/low of that candle. This returns the CURRENT 10 EMA
    value as a live reference point; the actual exit trigger is re-checked
    every cycle (same stateless pattern as the rest of this engine).
    """
    if data is None or len(data) < period:
        return {"ema_trail_value": None, "ema_trail_period": period, "available": False}
    try:
        ema = data["Close"].ewm(span=period, adjust=False).mean()
        latest = float(ema.iloc[-1])
        return {
            "ema_trail_value": round(latest, 2),
            "ema_trail_period": period,
            "available": True,
        }
    except Exception:
        return {"ema_trail_value": None, "ema_trail_period": period, "available": False}


def attach_risk_management(signal: dict) -> dict:
    """
    Master function — combines Module 9 (Stop Loss) + Module 10 (Target).
    Takes one triggered signal dict from scan_intraday_entries()'s
    long_signals / short_signals and returns it enriched with:

      stop_price, risk_per_share, stop_basis,
      target_1, target_1_rr, target_2, target_2_rr,
      ema_trail_value, ema_trail_period,
      risk_management_available, risk_management_reason

    signal["zone"] must be the entry-side zone (already set by
    scan_intraday_entries) and signal["opposite_zone"] the zone on the
    other side — both carried through from M38C's structure validation
    so no extra daily-data fetch is needed here.
    """
    enriched = dict(signal)
    enriched.update({
        "stop_price": None, "risk_per_share": None, "stop_basis": None,
        "target_1": None, "target_1_rr": None, "target_2": None, "target_2_rr": None,
        "ema_trail_value": None, "ema_trail_period": EMA_TRAIL_PERIOD,
        "risk_management_available": False,
        "risk_management_reason": "",
    })

    direction   = "LONG" if signal.get("signal") == "BUY" else "SHORT"
    entry_price = signal.get("entry_price")
    symbol      = signal.get("symbol")
    zone        = signal.get("zone")
    opp_zone    = signal.get("opposite_zone")

    if entry_price is None or symbol is None:
        enriched["risk_management_reason"] = (
            "Missing entry price or symbol — cannot compute risk levels"
        )
        return enriched

    # 5-min data for the ATR stop component and EMA trail reference
    intraday_data = None
    try:
        intraday_data = _fetch_intraday_data(symbol)
    except Exception:
        pass

    atr_value = None
    if intraday_data is not None:
        try:
            from strategies.market_structure import _calculate_atr
            atr_series = _calculate_atr(intraday_data, period=ATR_STOP_PERIOD)
            latest_atr = atr_series.iloc[-1]
            if not pd.isna(latest_atr):
                atr_value = round(float(latest_atr), 2)
        except Exception:
            pass

    stop_result = calculate_stop_loss(
        direction=direction,
        entry_price=entry_price,
        zone=zone,
        compression_candle_high=signal.get("compression_candle_high"),
        compression_candle_low=signal.get("compression_candle_low"),
        atr_value=atr_value,
    )

    if stop_result is None:
        enriched["risk_management_reason"] = (
            "Could not compute a valid stop loss — no zone, compression candle, "
            "or ATR data available, or the stop landed on the wrong side of entry"
        )
        return enriched

    target_result = calculate_targets(
        direction=direction,
        entry_price=entry_price,
        stop_price=stop_result["stop_price"],
        risk_per_share=stop_result["risk_per_share"],
        opposite_zone=opp_zone,
    )

    ema_info = get_ema_trail_info(intraday_data) if intraday_data is not None else {
        "ema_trail_value": None, "ema_trail_period": EMA_TRAIL_PERIOD, "available": False,
    }

    t2_note = (
        f" | Target 2 ₹{target_result['target_2']} ({target_result['target_2_rr']}R)"
        if target_result["target_2"] is not None else " | No Target 2 zone found nearby"
    )

    enriched.update({
        "stop_price":       stop_result["stop_price"],
        "risk_per_share":   stop_result["risk_per_share"],
        "stop_basis":       stop_result["stop_basis"],
        "target_1":         target_result["target_1"],
        "target_1_rr":      target_result["target_1_rr"],
        "target_2":         target_result["target_2"],
        "target_2_rr":      target_result["target_2_rr"],
        "ema_trail_value":  ema_info.get("ema_trail_value"),
        "ema_trail_period": ema_info.get("ema_trail_period", EMA_TRAIL_PERIOD),
        "risk_management_available": True,
        "risk_management_reason": (
            f"Stop via {stop_result['stop_basis']} (₹{stop_result['stop_price']}) | "
            f"Risk ₹{stop_result['risk_per_share']}/share | "
            f"Target 1 (2R) ₹{target_result['target_1']}" + t2_note
        ),
    })
    return enriched



# ════════════════════════════════════════════════
# MODULE 8 — MASTER ENTRY LOGIC
# Chains M38A -> B -> C -> D -> breakout trigger
# ════════════════════════════════════════════════

def scan_intraday_entries(
    top_n_sectors: int = 3,
    require_fo: bool = True,
    active_only: bool = True,
    max_workers: int = SCANNER_MAX_WORKERS,
) -> dict:
    """
    Master function — Module 8 of the VCPS spec.

    Pipeline:
      1. Module 1   — Market Direction Filter (BULLISH/BEARISH/NEUTRAL gate)
      2. M38A->B->C — sector rank + liquidity + structure + zones
      3. Direction filter — only keep candidates matching regime
         (BULLISH -> valid_for_long, BEARISH -> valid_for_short)
      4. Modules 6+7 — volume + volatility compression
      5. Module 8    — breakout trigger of the compression candle

    Returns:
      {
        market_regime, direction_detail,
        long_signals:  [...]  — BUY signals, ready for M38F stop/target calc
        short_signals: [...]  — SELL signals
        watching:      [...]  — compressed but not yet triggered, or
                                 trending but not yet compressed
        structure_rejected, liquidity_rejected — carried through for audit
        reason, fetched_at, data_available,
      }
    """
    result = {
        "market_regime":      "NEUTRAL",
        "direction_detail":   {},
        "long_signals":       [],
        "short_signals":      [],
        "watching":           [],
        "structure_rejected": [],
        "liquidity_rejected": [],
        "reason":             "",
        "fetched_at":         datetime.now().strftime('%d %b %Y %H:%M'),
        "data_available":     False,
    }

    # ── Module 1 — master direction gate ──────────
    direction = get_intraday_direction_analysis()
    regime    = direction.get("market_regime", "NEUTRAL")
    result["market_regime"]    = regime
    result["direction_detail"] = direction

    if regime == "NEUTRAL":
        result["reason"] = (
            "Market Direction Filter (Module 1) = NEUTRAL — "
            "no intraday trades allowed at all, per spec."
        )
        result["data_available"] = True
        return result

    # ── M38A -> B -> C chain ───────────────────────
    structure_result = get_intraday_trade_candidates(
        top_n_sectors=top_n_sectors,
        require_fo=require_fo,
        active_only=active_only,
    )
    result["structure_rejected"] = structure_result.get("structure_rejected", [])
    result["liquidity_rejected"] = structure_result.get("liquidity_rejected", [])

    if not structure_result["data_available"] or not structure_result["candidates"]:
        result["reason"] = (
            "No structure-validated candidates today — "
            "check Sector Strength / Stock Selection / Structure Validation above."
        )
        result["data_available"] = True
        return result

    candidates = structure_result["candidates"]

    # ── Direction filter — only trade WITH the regime ─
    if regime == "BULLISH":
        directional = [c for c in candidates if c.get("valid_for_long")]
        need_desc   = "UPTREND + near a Demand zone"
    else:   # BEARISH
        directional = [c for c in candidates if c.get("valid_for_short")]
        need_desc   = "DOWNTREND + near a Supply zone"

    if not directional:
        result["reason"] = (
            f"Regime is {regime} but no candidate qualifies "
            f"({need_desc}) — waiting for a better setup."
        )
        result["data_available"] = True
        return result

    # ── Modules 6+7 — compression check ───────────
    compression_result    = batch_compression_check(directional, max_workers=max_workers)
    compressed_candidates = compression_result["compressed"]

    for nc in compression_result["not_compressed"]:
        nc["watch_reason"] = "Trending and near zone, but not exhausted (compressed) yet"
    result["watching"].extend(compression_result["not_compressed"])

    if not compressed_candidates:
        result["reason"] = (
            f"{len(directional)} candidate(s) trending in the right direction, "
            "but none showing volume+volatility compression right now."
        )
        result["data_available"] = True
        return result

    # ── Module 8 — breakout trigger ───────────────
    entry_direction = "LONG" if regime == "BULLISH" else "SHORT"

    def _worker(item):
        symbol  = item.get("symbol")
        trigger = _check_breakout_trigger(symbol, entry_direction)
        merged  = dict(item)
        merged["trigger"] = trigger
        return merged

    triggered_results = []
    not_triggered_yet = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, item): item for item in compressed_candidates}
        for future in as_completed(futures):
            try:
                merged = future.result()
            except Exception:
                continue

            trig = merged.get("trigger", {})
            if not trig.get("data_available"):
                merged["watch_reason"] = trig.get("reason", "Could not check breakout")
                not_triggered_yet.append(merged)
                continue

            if trig.get("triggered"):
                triggered_results.append(merged)
            else:
                merged["watch_reason"] = trig.get("reason", "Compressed — waiting for breakout")
                not_triggered_yet.append(merged)

    result["watching"].extend(not_triggered_yet)

    # ── Build the final signal dicts ──────────────
    zone_key          = "demand_zone" if entry_direction == "LONG" else "supply_zone"
    dist_key          = "distance_to_demand_pct" if entry_direction == "LONG" else "distance_to_supply_pct"
    opposite_zone_key = "supply_zone" if entry_direction == "LONG" else "demand_zone"

    for r in triggered_results:
        trig = r["trigger"]
        signal = {
            "stock":                   r.get("stock_name"),
            "symbol":                  r.get("symbol"),
            "sector":                  r.get("sector"),
            "signal":                  "BUY" if entry_direction == "LONG" else "SELL",
            "market_regime":           regime,
            "structure":               r.get("structure_type"),
            "trend_state":             r.get("trend_state"),
            "zone":                    r.get(zone_key),
            "opposite_zone":           r.get(opposite_zone_key),
            "distance_to_zone_pct":    r.get(dist_key),
            "compression_candle_high": trig.get("compression_candle_high"),
            "compression_candle_low":  trig.get("compression_candle_low"),
            "entry_price":             trig.get("trigger_price"),
            "latest_close":            trig.get("latest_close"),
            "volume_ratio":            r.get("volume_ratio"),
            "atr_pct":                 r.get("atr_pct"),
            "price":                   r.get("price"),
            "traded_value_cr":         r.get("traded_value_cr"),
            "bos_detected":            r.get("bos_detected"),
            "reason":                  trig.get("reason"),
        }

        # ── M38F — attach stop loss (Module 9) and targets (Module 10) ──
        signal = attach_risk_management(signal)

        if entry_direction == "LONG":
            result["long_signals"].append(signal)
        else:
            result["short_signals"].append(signal)

    if result["long_signals"] or result["short_signals"]:
        n = len(result["long_signals"]) + len(result["short_signals"])
        result["reason"] = f"{n} entry signal(s) triggered — see long_signals / short_signals."
    else:
        result["reason"] = (
            f"{len(compressed_candidates)} candidate(s) compressed and ready, "
            "but none have broken the compression candle high/low yet."
        )

    result["data_available"] = True
    return result


# ════════════════════════════════════════════════
# CONVENIENCE — single stock check
# Useful for a "check this one stock" dashboard button
# without running the full watchlist scan.
# ════════════════════════════════════════════════

def check_single_stock_entry(stock_name: str, symbol: str, direction: str) -> dict:
    """
    Run the full Module 8 pipeline (structure + compression + breakout)
    on ONE already-known stock/symbol, skipping the sector/liquidity
    filters (M38A/M38B). Useful for spot-checking a stock you're
    already watching manually.

    direction: "LONG" or "SHORT"
    """
    result = {
        "stock":          stock_name,
        "symbol":         symbol,
        "direction":      direction,
        "structure_ok":   False,
        "compression_ok": False,
        "triggered":      False,
        "reason":         "",
        "data_available": False,
    }

    daily_data = _fetch_data(symbol, period=DATA_PERIOD)
    structure  = validate_market_structure(stock_name, daily_data)
    result["structure"] = structure

    if not structure["data_available"]:
        result["reason"] = structure.get("rejection_reason", "Structure data unavailable")
        return result

    valid = structure["valid_for_long"] if direction == "LONG" else structure["valid_for_short"]
    result["structure_ok"] = valid

    if not valid:
        result["reason"] = structure.get("rejection_reason", "Structure not aligned for this direction")
        result["data_available"] = True
        return result

    intraday_data = _fetch_intraday_data(symbol)
    if intraday_data is None:
        result["reason"] = "Could not fetch 5-min data"
        result["data_available"] = True
        return result

    vol_c  = detect_volume_compression(intraday_data)
    vlt_c  = detect_volatility_compression(intraday_data)
    compressed = vol_c["volume_compression"] and vlt_c["volatility_compression"]
    result["compression_ok"]    = compressed
    result["volume_detail"]     = vol_c
    result["volatility_detail"] = vlt_c

    if not compressed:
        result["reason"] = "Not compressed yet — " + vol_c.get("reason", "") + " | " + vlt_c.get("reason", "")
        result["data_available"] = True
        return result

    trigger = _check_breakout_trigger(symbol, direction, data=intraday_data)
    result["triggered"]      = trigger.get("triggered", False)
    result["trigger"]        = trigger
    result["reason"]         = trigger.get("reason", "")
    result["data_available"] = True

    return result