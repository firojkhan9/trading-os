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
    zone_key = "demand_zone" if entry_direction == "LONG" else "supply_zone"
    dist_key = "distance_to_demand_pct" if entry_direction == "LONG" else "distance_to_supply_pct"

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