# ================================================
# FILE: strategies/stock_selection_filter.py
# PURPOSE: Stock Selection Filter — Milestone 38B
#          Module 3 of the Volume Compression Pullback
#          Strategy (VCPS) intraday specification.
#
# WHAT THIS DOES:
#   Takes the watchlist (restricted to the top sectors from
#   M38A) and filters it down to stocks that are actually
#   SAFE and LIQUID enough to trade intraday.
#
#   A stock only qualifies if ALL of these are true:
#     1. F&O eligible          — better liquidity, margin flexibility
#     2. Volume > 1.5x 20-day average volume
#     3. ATR% above minimum    — enough daily range to profit from
#     4. Price > ₹100          — avoids penny-stock noise
#     5. Daily traded value    — above a minimum ₹ crore floor
#
#   Everything that fails is logged with the exact reason —
#   consistent with the project's "explain every NO-TRADE" rule.
#
# HOW IT CONNECTS:
#   strategies/sector_strength.py  → get_top_sectors() to restrict
#                                    the universe to today's leaders
#   config/fo_universe.py          → F&O eligibility check
#   strategies/watchlist_manager.py→ load_watchlist() for Symbol/Sector
#   Upcoming M38C (intraday entry logic) will call
#   get_eligible_intraday_stocks() to get its trading universe.
# ================================================

import pandas as pd
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from strategies.watchlist_manager import load_watchlist
from strategies.sector_strength import get_top_sectors
from config.fo_universe import get_fo_universe

try:
    from config.settings import SCANNER_MAX_WORKERS
except ImportError:
    SCANNER_MAX_WORKERS = 10

# ── Filter thresholds ─────────────────────────────
# Conservative defaults for intraday safety.
# Tune later once you have live results to learn from.
MIN_PRICE           = 100.0   # ₹ — avoids illiquid penny stocks
MIN_VOLUME_RATIO    = 1.5     # today's volume vs 20-day average
MIN_ATR_PCT         = 1.0     # ATR14 as % of price — needs real daily range
MIN_TRADED_VALUE_CR = 5.0     # ₹ crore — today's Price × Volume
ATR_PERIOD          = 14
VOLUME_MA_PERIOD    = 20


def _fetch_stock_data(symbol, period="3mo"):
    """Fetch OHLCV data for one stock. Returns None on any failure."""
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
        if len(data) < ATR_PERIOD + 5:
            return None
        return data
    except Exception:
        return None


def _calculate_atr_pct(data, period=ATR_PERIOD):
    """Average True Range as a % of the latest close."""
    try:
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
        latest_atr   = float(atr.iloc[-1])
        latest_close = float(close.iloc[-1])

        if latest_close <= 0 or pd.isna(latest_atr):
            return None
        return round((latest_atr / latest_close) * 100, 2)
    except Exception:
        return None


def _run_all_checks(stock_name, data, fo_universe, require_fo=True):
    """Run all 5 eligibility checks on one stock."""
    checks  = {}
    reasons = []

    latest_close = float(data["Close"].iloc[-1])
    latest_vol   = float(data["Volume"].iloc[-1])
    vol_ma       = data["Volume"].rolling(window=VOLUME_MA_PERIOD).mean()
    avg_vol      = float(vol_ma.iloc[-1]) if not pd.isna(vol_ma.iloc[-1]) else None

    vol_ratio       = round(latest_vol / avg_vol, 2) if avg_vol and avg_vol > 0 else None
    atr_pct         = _calculate_atr_pct(data)
    traded_value_cr = round((latest_close * latest_vol) / 1e7, 2)   # ₹ in crores

    # 1. F&O eligibility
    fo_ok = (stock_name.strip().upper() in fo_universe) if require_fo else True
    checks["fo_eligible"] = fo_ok
    if not fo_ok:
        reasons.append("Not in F&O universe")

    # 2. Volume expansion
    vol_ok = vol_ratio is not None and vol_ratio >= MIN_VOLUME_RATIO
    checks["volume_ok"] = vol_ok
    if not vol_ok:
        reasons.append(
            f"Volume {vol_ratio}x avg — below {MIN_VOLUME_RATIO}x threshold"
            if vol_ratio is not None else "Volume data unavailable"
        )

    # 3. ATR threshold
    atr_ok = atr_pct is not None and atr_pct >= MIN_ATR_PCT
    checks["atr_ok"] = atr_ok
    if not atr_ok:
        reasons.append(
            f"ATR {atr_pct}% — below {MIN_ATR_PCT}% threshold"
            if atr_pct is not None else "ATR data unavailable"
        )

    # 4. Price floor
    price_ok = latest_close > MIN_PRICE
    checks["price_ok"] = price_ok
    if not price_ok:
        reasons.append(f"Price ₹{latest_close:.0f} — below ₹{MIN_PRICE:.0f} floor")

    # 5. Traded value floor
    value_ok = traded_value_cr >= MIN_TRADED_VALUE_CR
    checks["value_ok"] = value_ok
    if not value_ok:
        reasons.append(f"Traded value ₹{traded_value_cr} Cr — below ₹{MIN_TRADED_VALUE_CR} Cr threshold")

    passed = all(checks.values())
    metrics = {
        "price":           round(latest_close, 2),
        "volume_ratio":    vol_ratio,
        "atr_pct":         atr_pct,
        "traded_value_cr": traded_value_cr,
    }
    return passed, checks, reasons, metrics


def get_eligible_intraday_stocks(
    top_n_sectors=3,
    require_fo=True,
    active_only=True,
    max_workers=SCANNER_MAX_WORKERS,
):
    """
    Master function — Module 3 of the VCPS spec.

    Steps:
      1. Get today's top N sectors from the Sector Strength Engine
      2. Restrict the watchlist to stocks in those sectors
      3. Fetch data + run all 5 eligibility checks per stock
      4. Return eligible stocks + rejected stocks (with reasons)
    """
    result = {
        "eligible":       [],
        "rejected":       [],
        "top_sectors":    [],
        "fetched_at":     datetime.now().strftime('%d %b %Y %H:%M'),
        "data_available": False,
    }

    top_sectors = get_top_sectors(n=top_n_sectors, active_only=active_only)
    if not top_sectors:
        return result
    result["top_sectors"] = top_sectors

    watchlist_df = load_watchlist(active_only=active_only)
    if watchlist_df.empty:
        return result

    universe_df = watchlist_df[watchlist_df["Sector"].isin(top_sectors)]
    if universe_df.empty:
        return result

    fo_universe = get_fo_universe() if require_fo else set()

    def _worker(row):
        stock_name = row["Name"]
        symbol     = row["Symbol"]
        sector     = row["Sector"]
        data = _fetch_stock_data(symbol)
        if data is None:
            return {"stock": stock_name, "symbol": symbol, "sector": sector, "status": "NO_DATA"}
        passed, checks, reasons, metrics = _run_all_checks(stock_name, data, fo_universe, require_fo)
        return {
            "stock": stock_name, "symbol": symbol, "sector": sector,
            "status": "OK", "passed": passed,
            "checks": checks, "reasons": reasons, "metrics": metrics,
        }

    rows = universe_df.to_dict("records")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, row): row for row in rows}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception:
                continue

            if r["status"] == "NO_DATA":
                result["rejected"].append({
                    "stock": r["stock"], "symbol": r["symbol"], "sector": r["sector"],
                    "reasons": ["Could not fetch price data"],
                })
                continue

            if r["passed"]:
                entry = {"stock": r["stock"], "symbol": r["symbol"], "sector": r["sector"]}
                entry.update(r["metrics"])
                result["eligible"].append(entry)
            else:
                result["rejected"].append({
                    "stock": r["stock"], "symbol": r["symbol"], "sector": r["sector"],
                    "reasons": r["reasons"],
                })

    result["eligible"] = sorted(result["eligible"], key=lambda x: x.get("traded_value_cr", 0), reverse=True)
    result["data_available"] = True
    return result


def get_eligible_symbols(top_n_sectors=3, require_fo=True, active_only=True):
    """
    Lightweight wrapper — returns {stock_name: symbol} for stocks
    that passed every filter. This becomes the trading universe
    for the Intraday Entry Engine (M38C).
    """
    result = get_eligible_intraday_stocks(top_n_sectors, require_fo, active_only)
    return {e["stock"]: e["symbol"] for e in result["eligible"]}