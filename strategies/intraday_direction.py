# ================================================
# FILE: strategies/intraday_direction.py
# PURPOSE: Intraday Direction & Compression Engine — Milestone 38D
#          Modules 1, 6, 7 of the Volume Compression Pullback
#          Strategy (VCPS) intraday specification.
#
# WHAT THIS DOES:
#   MODULE 1 — Market Direction Filter
#     Gates ALL intraday entries. Uses 5-minute NIFTY data:
#       BULLISH = price > VWAP AND price > 20 EMA AND breadth > 1
#       BEARISH = price < VWAP AND price < 20 EMA AND breadth < 1
#       else    = NEUTRAL — no trades allowed at all
#
#   MODULE 6 — Volume Compression Detection
#     Identifies exhaustion pullbacks on a single stock's 5-min bars:
#       current volume < 50% of 20-bar average
#       AND current volume in the bottom 10th percentile of last 20 bars
#
#   MODULE 7 — Volatility Compression
#     ATR contracting AND Bollinger Band width contracting:
#       current ATR14 < 80% of its 20-bar average
#       AND current BB width < its 20-bar average
#
# WHY NIFTYBEES.NS INSTEAD OF ^NSEI:
#   yfinance always returns 0/NaN volume for index tickers (^NSEI,
#   ^NSEBANK) — VWAP is mathematically impossible without volume.
#   NIFTYBEES.NS (the NIFTY 50 ETF) tracks the index almost exactly
#   and has real traded volume. This is the same fallback pattern
#   engine/execution_loop.py already uses for its Tier-2 regime check.
#
# WHY BREADTH IS A PROXY:
#   NSE's real advance/decline feed needs cookie-based scraping that
#   is unreliable from cloud IPs (see institutional_flow.py's 4-source
#   fallback chain for the same problem). Instead we use your own
#   watchlist: how many stocks are up vs down today. Small watchlists
#   will be noisier than the real market-wide number — that's a known
#   limitation, not a bug.
#
# REUSES (does not duplicate):
#   strategies/market_structure.py:
#     - _calculate_atr()       -> ATR14 series
#     - _calculate_bb_width()  -> Bollinger Band width series
#
# HOW IT CONNECTS:
#   app.py Tab 2            -> get_intraday_direction_analysis(), get_compression_analysis()
#   Upcoming M38E (entry logic) will call:
#     - get_market_regime_only()   as the master BULLISH/BEARISH/NEUTRAL gate
#     - batch_compression_check()  on the M38C validated candidate list
# ================================================

import pandas as pd
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from strategies.market_structure import _calculate_atr, _calculate_bb_width

try:
    from config.settings import SCANNER_MAX_WORKERS
except ImportError:
    SCANNER_MAX_WORKERS = 10

# ── Proxies (see header note) ─────────────────────
NIFTY_PROXY_SYMBOL     = "NIFTYBEES.NS"
BANKNIFTY_PROXY_SYMBOL = "BANKBEES.NS"

# ── Intraday data settings ────────────────────────
INTRADAY_PERIOD   = "5d"    # yfinance 5-min data allows up to 60d; 5d is plenty
INTRADAY_INTERVAL = "5m"

# ── Module 1 settings ─────────────────────────────
DIRECTION_EMA_PERIOD = 20

# ── Module 6 settings ──────────────────────────────
VOLUME_COMPRESSION_RATIO      = 0.50   # current vol must be < 50% of 20-bar avg
VOLUME_COMPRESSION_PERCENTILE = 10     # AND in the bottom 10th percentile
COMPRESSION_LOOKBACK          = 20

# ── Module 7 settings ──────────────────────────────
ATR_PERIOD           = 14
ATR_COMPRESSION_RATIO = 0.80   # current ATR must be < 80% of its 20-bar avg
BB_PERIOD            = 20

# ── Minimum bar counts (avoid NaN-tainted readings) ──
MIN_BARS_VOLUME_CHECK     = 21   # 20-bar rolling + 1
MIN_BARS_VOLATILITY_CHECK = 45   # ATR14 warm-up + 20-bar rolling avg + buffer


# ════════════════════════════════════════════════
# DATA FETCHING
# ════════════════════════════════════════════════

def _fetch_intraday_data(symbol, period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL):
    """
    Fetch intraday OHLCV data. Returns None on any failure —
    callers must handle gracefully (never crash the engine).
    """
    try:
        data = yf.download(
            tickers=symbol, period=period, interval=interval,
            progress=False, auto_adjust=True,
        )
        if data.empty:
            return None
        data.columns = [col[0] for col in data.columns]
        data = data.dropna(subset=["Close"])
        data = data[data["Close"] > 0]
        if data.empty:
            return None
        return data
    except Exception:
        return None


def _calculate_vwap(data):
    """
    Volume Weighted Average Price, resetting every trading day.
    VWAP = cumulative(typical_price * volume) / cumulative(volume)
    within each calendar date — NOT a running total across days.
    """
    data = data.copy()
    typical_price = (data["High"] + data["Low"] + data["Close"]) / 3
    tp_vol   = typical_price * data["Volume"]
    date_key = data.index.date

    cum_tp_vol = tp_vol.groupby(date_key).cumsum()
    cum_vol    = data["Volume"].groupby(date_key).cumsum()

    data["VWAP"] = (cum_tp_vol / cum_vol.replace(0, pd.NA)).round(2)
    return data


# ════════════════════════════════════════════════
# MODULE 1 — MARKET DIRECTION FILTER
# ════════════════════════════════════════════════

def _calculate_market_breadth(watchlist_dict=None, max_workers=SCANNER_MAX_WORKERS):
    """
    Proxy market breadth from your own watchlist (see header note).
    Breadth Ratio = advancing_count / max(declining_count, 1)

    Uses each stock's latest daily change (today's close vs
    previous close) — fast (daily data, not intraday) and avoids
    hammering yfinance with dozens of 5-min downloads just to
    count up/down.
    """
    if watchlist_dict is None:
        try:
            from strategies.watchlist_manager import get_watchlist_dict
            watchlist_dict = get_watchlist_dict()
        except Exception:
            watchlist_dict = {}

    if not watchlist_dict:
        return {
            "breadth_ratio": None, "advancing": 0, "declining": 0,
            "breadth_available": False,
        }

    def _check_stock(symbol):
        try:
            data = yf.download(
                tickers=symbol, period="5d", interval="1d",
                progress=False, auto_adjust=True,
            )
            if data.empty:
                return None
            data.columns = [c[0] for c in data.columns]
            data = data.dropna(subset=["Close"])
            if len(data) < 2:
                return None
            change = float(data["Close"].iloc[-1]) - float(data["Close"].iloc[-2])
            return change > 0
        except Exception:
            return None

    advancing = 0
    declining = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_check_stock, sym): name
            for name, sym in watchlist_dict.items()
        }
        for future in as_completed(futures):
            try:
                is_up = future.result()
                if is_up is True:
                    advancing += 1
                elif is_up is False:
                    declining += 1
            except Exception:
                continue

    if advancing + declining == 0:
        return {
            "breadth_ratio": None, "advancing": 0, "declining": 0,
            "breadth_available": False,
        }

    ratio = round(advancing / max(declining, 1), 2)
    return {
        "breadth_ratio":      ratio,
        "advancing":          advancing,
        "declining":          declining,
        "breadth_available":  True,
    }


def get_intraday_direction_analysis(watchlist_dict=None):
    """
    Master function — Module 1.
    Full market direction analysis for the dashboard AND the
    upcoming entry engine (M38E).

    Returns a dict with market_regime = "BULLISH" / "BEARISH" / "NEUTRAL".
    NEUTRAL means: do not place any new intraday trades right now.
    """
    result = {
        "market_regime":   "NEUTRAL",
        "nifty_price":      None,
        "nifty_vwap":       None,
        "nifty_ema20":      None,
        "above_vwap":       None,
        "above_ema20":      None,
        "breadth_ratio":    None,
        "advancing":        0,
        "declining":        0,
        "reasons":          [],
        "summary":          "Insufficient data for market direction analysis.",
        "data_available":   False,
        "fetched_at":       datetime.now().strftime('%d %b %Y %H:%M'),
    }

    nifty_data = _fetch_intraday_data(NIFTY_PROXY_SYMBOL)
    if nifty_data is None or len(nifty_data) < DIRECTION_EMA_PERIOD:
        result["reasons"] = [
            "Could not fetch NIFTY (proxy) 5-min data — defaulting to NEUTRAL. "
            "No trades allowed until data is available."
        ]
        result["summary"] = result["reasons"][0]
        return result

    try:
        nifty_data = _calculate_vwap(nifty_data)
        ema20 = nifty_data["Close"].ewm(span=DIRECTION_EMA_PERIOD, adjust=False).mean()

        latest_close = float(nifty_data["Close"].iloc[-1])
        latest_vwap  = float(nifty_data["VWAP"].iloc[-1])
        latest_ema20 = float(ema20.iloc[-1])

        above_vwap = latest_close > latest_vwap
        above_ema  = latest_close > latest_ema20

        result.update({
            "nifty_price":    round(latest_close, 2),
            "nifty_vwap":     round(latest_vwap, 2),
            "nifty_ema20":    round(latest_ema20, 2),
            "above_vwap":     above_vwap,
            "above_ema20":    above_ema,
            "data_available": True,
        })

        breadth = _calculate_market_breadth(watchlist_dict)
        result.update(breadth)
        breadth_ratio    = breadth.get("breadth_ratio")
        breadth_available= breadth.get("breadth_available", False)

        if not breadth_available:
            result["market_regime"] = "NEUTRAL"
            result["reasons"] = [
                "VWAP/EMA read fine, but breadth data unavailable — "
                "staying NEUTRAL out of caution (breadth is a required condition)."
            ]

        elif above_vwap and above_ema and breadth_ratio > 1:
            result["market_regime"] = "BULLISH"
            result["reasons"] = [
                f"NIFTY (proxy) above VWAP — ₹{latest_close} > ₹{latest_vwap}",
                f"NIFTY (proxy) above 20 EMA — ₹{latest_close} > ₹{latest_ema20}",
                f"Breadth {breadth_ratio}:1 — {breadth['advancing']} advancing vs "
                f"{breadth['declining']} declining in your watchlist",
            ]

        elif (not above_vwap) and (not above_ema) and breadth_ratio < 1:
            result["market_regime"] = "BEARISH"
            result["reasons"] = [
                f"NIFTY (proxy) below VWAP — ₹{latest_close} < ₹{latest_vwap}",
                f"NIFTY (proxy) below 20 EMA — ₹{latest_close} < ₹{latest_ema20}",
                f"Breadth {breadth_ratio}:1 — {breadth['declining']} declining vs "
                f"{breadth['advancing']} advancing in your watchlist",
            ]

        else:
            result["market_regime"] = "NEUTRAL"
            result["reasons"] = [
                "VWAP, 20 EMA and breadth do not all agree on one direction. "
                "Per spec, NEUTRAL blocks all new intraday trades."
            ]

        result["summary"] = (
            f"Market Direction: {result['market_regime']}. " +
            " | ".join(result["reasons"])
        )

    except Exception as e:
        result["reasons"] = [f"Direction analysis error: {e}"]
        result["summary"] = result["reasons"][0]

    return result


def get_market_regime_only(watchlist_dict=None) -> str:
    """
    Lightweight wrapper — returns just "BULLISH" / "BEARISH" / "NEUTRAL".
    Used by the upcoming Entry Logic engine (M38E) as the master gate.
    Never crashes — returns "NEUTRAL" (blocks trading) on any failure.
    """
    try:
        return get_intraday_direction_analysis(watchlist_dict)["market_regime"]
    except Exception:
        return "NEUTRAL"


# ════════════════════════════════════════════════
# MODULE 6 — VOLUME COMPRESSION DETECTION
# ════════════════════════════════════════════════

def detect_volume_compression(data):
    """
    True when BOTH:
      current volume < 50% of the 20-bar average volume
      AND
      current volume is in the bottom 10th percentile of the last 20 bars

    data: 5-minute OHLCV DataFrame for a single stock.
    """
    result = {
        "volume_compression": False,
        "current_volume":     None,
        "avg_volume_20":      None,
        "volume_ratio":       None,
        "percentile_rank":    None,
        "reason":             "",
    }

    if data is None or len(data) < MIN_BARS_VOLUME_CHECK:
        result["reason"] = f"Need {MIN_BARS_VOLUME_CHECK}+ 5-min bars — insufficient data"
        return result

    try:
        vol      = data["Volume"]
        avg_20   = vol.rolling(window=COMPRESSION_LOOKBACK).mean()
        curr_vol = float(vol.iloc[-1])
        avg_vol  = float(avg_20.iloc[-1])

        if pd.isna(avg_vol) or avg_vol <= 0:
            result["reason"] = "No volume baseline available yet"
            return result

        ratio      = round(curr_vol / avg_vol, 3)
        below_half = ratio < VOLUME_COMPRESSION_RATIO

        recent_20  = vol.tail(COMPRESSION_LOOKBACK)
        percentile = round((recent_20 < curr_vol).sum() / len(recent_20) * 100, 1)
        bottom_10  = percentile <= VOLUME_COMPRESSION_PERCENTILE

        compressed = below_half and bottom_10

        result.update({
            "volume_compression": compressed,
            "current_volume":     int(curr_vol),
            "avg_volume_20":      round(avg_vol, 0),
            "volume_ratio":       ratio,
            "percentile_rank":    percentile,
            "reason": (
                f"Volume {ratio}x avg (need <{VOLUME_COMPRESSION_RATIO}x), "
                f"percentile {percentile}% (need <={VOLUME_COMPRESSION_PERCENTILE}%) — "
                f"{'CONFIRMED' if compressed else 'not compressed'}"
            ),
        })

    except Exception as e:
        result["reason"] = f"Volume compression check error: {e}"

    return result


# ════════════════════════════════════════════════
# MODULE 7 — VOLATILITY COMPRESSION
# ════════════════════════════════════════════════

def detect_volatility_compression(data):
    """
    True when BOTH:
      current ATR14 < 80% of its own 20-bar average
      AND
      current Bollinger Band width < its own 20-bar average

    Reuses _calculate_atr() and _calculate_bb_width() from
    market_structure.py — same formulas, just applied to 5-min bars
    instead of daily bars.
    """
    result = {
        "volatility_compression": False,
        "current_atr":            None,
        "avg_atr_20":             None,
        "atr_ratio":              None,
        "current_bb_width":       None,
        "avg_bb_width_20":        None,
        "bb_width_ratio":         None,
        "reason":                 "",
    }

    if data is None or len(data) < MIN_BARS_VOLATILITY_CHECK:
        result["reason"] = f"Need {MIN_BARS_VOLATILITY_CHECK}+ 5-min bars — insufficient data"
        return result

    try:
        atr        = _calculate_atr(data, period=ATR_PERIOD)
        atr_avg_20 = atr.rolling(window=COMPRESSION_LOOKBACK).mean()

        curr_atr = float(atr.iloc[-1])
        avg_atr  = float(atr_avg_20.iloc[-1])

        if pd.isna(curr_atr) or pd.isna(avg_atr) or avg_atr <= 0:
            result["reason"] = "ATR baseline not available yet"
            return result

        atr_ratio      = round(curr_atr / avg_atr, 3)
        atr_compressed = atr_ratio < ATR_COMPRESSION_RATIO

        bb_width        = _calculate_bb_width(data, period=BB_PERIOD)
        bb_width_avg_20 = bb_width.rolling(window=COMPRESSION_LOOKBACK).mean()

        curr_bb = float(bb_width.iloc[-1])
        avg_bb  = float(bb_width_avg_20.iloc[-1])

        if pd.isna(curr_bb) or pd.isna(avg_bb) or avg_bb <= 0:
            result["reason"] = "Bollinger Band width baseline not available yet"
            return result

        bb_ratio      = round(curr_bb / avg_bb, 3)
        bb_compressed = curr_bb < avg_bb

        compressed = atr_compressed and bb_compressed

        result.update({
            "volatility_compression": compressed,
            "current_atr":            round(curr_atr, 3),
            "avg_atr_20":             round(avg_atr, 3),
            "atr_ratio":              atr_ratio,
            "current_bb_width":       round(curr_bb, 3),
            "avg_bb_width_20":        round(avg_bb, 3),
            "bb_width_ratio":         bb_ratio,
            "reason": (
                f"ATR {atr_ratio}x avg (need <{ATR_COMPRESSION_RATIO}x), "
                f"BB width {bb_ratio}x avg (need <1.0x) — "
                f"{'CONFIRMED' if compressed else 'not compressed'}"
            ),
        })

    except Exception as e:
        result["reason"] = f"Volatility compression check error: {e}"

    return result


# ════════════════════════════════════════════════
# COMBINED MODULE 6 + 7 — one stock at a time
# ════════════════════════════════════════════════

def get_compression_analysis(symbol, data=None):
    """
    Fetch (if needed) 5-min data for one stock and run both
    compression checks. This is what the dashboard button calls,
    and what the upcoming Entry Logic (M38E) will call per-candidate.

    Pass `data` directly if you already fetched it (e.g. inside a
    batch loop) to avoid a duplicate yfinance download.
    """
    if data is None:
        data = _fetch_intraday_data(symbol)

    if data is None:
        return {
            "symbol":                 symbol,
            "volume_compression":     False,
            "volatility_compression": False,
            "compression_confirmed":  False,
            "volume_detail":          {},
            "volatility_detail":      {},
            "data_available":         False,
            "reason":                 "Could not fetch 5-min intraday data",
        }

    vol_result   = detect_volume_compression(data)
    volat_result = detect_volatility_compression(data)
    confirmed    = vol_result["volume_compression"] and volat_result["volatility_compression"]

    return {
        "symbol":                 symbol,
        "volume_compression":     vol_result["volume_compression"],
        "volatility_compression": volat_result["volatility_compression"],
        "compression_confirmed":  confirmed,
        "volume_detail":          vol_result,
        "volatility_detail":      volat_result,
        "data_available":         True,
        "reason":                 "",
    }


# ════════════════════════════════════════════════
# BATCH VERSION — feeds off M38C's validated candidate list
# ════════════════════════════════════════════════

def batch_compression_check(candidates: list, max_workers=SCANNER_MAX_WORKERS) -> dict:
    """
    Run compression analysis across the M38C output
    (strategies.market_structure_validator.get_intraday_trade_candidates()
    -> "candidates" list, each dict has at least "stock_name"/"symbol").

    Returns:
      {
        "compressed":     [...] -- candidates with compression_confirmed=True,
                                    ready for M38E entry logic
        "not_compressed": [...] -- still trending/valid structure, just not
                                    exhausted yet — keep watching
        "fetched_at": str,
      }
    """
    result = {
        "compressed":     [],
        "not_compressed": [],
        "fetched_at":     datetime.now().strftime('%d %b %Y %H:%M'),
    }

    if not candidates:
        return result

    def _worker(item):
        symbol = item.get("symbol")
        cr     = get_compression_analysis(symbol)
        merged = dict(item)   # keep all M38C fields (structure, zones, etc.)
        merged.update({
            "volume_compression":     cr["volume_compression"],
            "volatility_compression": cr["volatility_compression"],
            "compression_confirmed":  cr["compression_confirmed"],
            "compression_data_available": cr["data_available"],
            # M38H needs the ratio detail (not just the boolean) to
            # grade HOW compressed a candidate is, not just whether.
            "volume_detail":          cr.get("volume_detail", {}),
            "volatility_detail":      cr.get("volatility_detail", {}),
        })
        return merged

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, item): item for item in candidates}
        for future in as_completed(futures):
            try:
                merged = future.result()
            except Exception:
                continue

            if merged.get("compression_confirmed"):
                result["compressed"].append(merged)
            else:
                result["not_compressed"].append(merged)

    return result