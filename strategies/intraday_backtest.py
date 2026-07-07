# ================================================
# FILE: strategies/intraday_backtest.py
# PURPOSE: VCPS Intraday Backtest Engine — Milestone 38K
#          Module 15 of the Volume Compression Pullback
#          Strategy (VCPS) intraday specification.
#
# WHAT THIS DOES:
#   Replays the M38E->G entry/exit logic (compression -> breakout
#   -> stop/target -> partial exit -> breakeven -> EMA trail ->
#   3:15 PM cutoff) bar-by-bar over HISTORICAL 5-minute data, using
#   the SAME functions the live engine uses — not a reimplementation.
#
# SCOPE LIMITATIONS (see chat message for full explanation):
#   1. yfinance caps 5-min history at ~60 days.
#   2. Sector performance is grouped by STATIC watchlist sector,
#      not a re-ranked historical sector score.
#   3. Regime-wise performance uses the DAILY regime engine
#      (market_regime.get_regime_history) as a proxy for the
#      intraday Module-1 regime, since no historical intraday
#      NIFTY feed exists.
#   4. Structure/zone validation DOES use real historical daily
#      data, truncated to strictly before each trading day —
#      no lookahead bias there.
#
# REUSES (does not duplicate):
#   strategies/market_structure_validator.py -> validate_market_structure()
#   strategies/intraday_direction.py         -> detect_volume_compression(),
#                                                detect_volatility_compression()
#   strategies/intraday_engine.py            -> calculate_stop_loss(),
#                                                calculate_targets(),
#                                                check_ema_trail_exit()
#   strategies/market_structure.py           -> _calculate_atr()
#   strategies/market_regime.py              -> get_full_regime_analysis(),
#                                                get_regime_history()
#
# HOW IT CONNECTS:
#   app.py Tab 6 (Backtesting) -> get_intraday_backtest_report()
# ================================================

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time as dtime
from concurrent.futures import ThreadPoolExecutor, as_completed

from strategies.market_structure_validator import validate_market_structure
from strategies.market_structure import _calculate_atr
from strategies.intraday_direction import (
    detect_volume_compression,
    detect_volatility_compression,
)
from strategies.intraday_engine import (
    calculate_stop_loss,
    calculate_targets,
    check_ema_trail_exit,
    ATR_STOP_PERIOD,
    MANDATORY_EXIT_HOUR,
    MANDATORY_EXIT_MINUTE,
)

try:
    from config.settings import SCANNER_MAX_WORKERS
except ImportError:
    SCANNER_MAX_WORKERS = 10

# ── Backtest settings ─────────────────────────────
BACKTEST_INTRADAY_PERIOD    = "60d"   # yfinance's real ceiling for 5-min data
BACKTEST_INTRADAY_INTERVAL  = "5m"
BACKTEST_DAILY_PERIOD       = "2y"    # for structure history + regime history
MIN_DAILY_BARS_FOR_STRUCTURE = 60     # matches market_structure_validator's needs
COMPRESSION_WINDOW_BUFFER   = 60      # bars fed to compression checks each step
NO_NEW_ENTRY_AFTER_HOUR     = 15      # no fresh compression candles after 3:00 PM
NO_NEW_ENTRY_AFTER_MINUTE   = 0
REGIME_HISTORY_WINDOW_DAYS  = 250     # ~1 trading year, comfortably covers 60d


# ════════════════════════════════════════════════
# DATA FETCHING
# ════════════════════════════════════════════════

def _fetch_5m_history(symbol):
    try:
        data = yf.download(
            tickers=symbol, period=BACKTEST_INTRADAY_PERIOD,
            interval=BACKTEST_INTRADAY_INTERVAL,
            progress=False, auto_adjust=True,
        )
        if data.empty:
            return None
        data.columns = [c[0] for c in data.columns]
        data = data.dropna(subset=["Close"])
        data = data[data["Close"] > 0]
        return data if not data.empty else None
    except Exception:
        return None


def _fetch_daily_history(symbol):
    try:
        data = yf.download(
            tickers=symbol, period=BACKTEST_DAILY_PERIOD,
            interval="1d", progress=False, auto_adjust=True,
        )
        if data.empty:
            return None
        data.columns = [c[0] for c in data.columns]
        data = data.dropna(subset=["Close"])
        data = data[data["Close"] > 0]
        return data if len(data) >= MIN_DAILY_BARS_FOR_STRUCTURE else None
    except Exception:
        return None


def fetch_nifty_regime_history():
    """
    Reuses the existing DAILY regime engine as the Regime-wise
    performance proxy (see scope limitation #3 above).
    Returns {date_str: regime_label}, or {} if unavailable.
    Call this ONCE per batch run — not per stock.
    """
    try:
        from strategies.market_regime import get_full_regime_analysis, get_regime_history
        analysis   = get_full_regime_analysis(period="2y")
        nifty_data = analysis.get("data")
        if nifty_data is None:
            return {}
        history = get_regime_history(nifty_data, window=REGIME_HISTORY_WINDOW_DAYS)
        return {
            str(pd.to_datetime(h["Date"]).date()): h["Regime"]
            for h in history
        }
    except Exception:
        return {}


# ════════════════════════════════════════════════
# PER-DATE STRUCTURE LOOKUP
# Built once per stock — no lookahead: structure for
# date D uses only daily bars strictly BEFORE D.
# ════════════════════════════════════════════════

def _build_daily_structure_lookup(stock_name, daily_data, trading_dates):
    lookup = {}
    for d in trading_dates:
        before = daily_data[daily_data.index.date < d]
        if len(before) < MIN_DAILY_BARS_FOR_STRUCTURE:
            lookup[d] = None
            continue
        try:
            lookup[d] = validate_market_structure(stock_name, before)
        except Exception:
            lookup[d] = None
    return lookup


# ════════════════════════════════════════════════
# SINGLE-STOCK BAR-BY-BAR REPLAY
# Mirrors the live M38E->G logic exactly, one bar
# at a time, using the real functions from those files.
# ════════════════════════════════════════════════

def run_intraday_backtest(
    stock_name: str,
    symbol: str,
    sector_name: str = "Unknown",
    nifty_regime_map: dict = None,
) -> dict:
    """
    Backtest ONE stock's VCPS intraday performance over the last
    ~60 days of 5-min data. Returns raw trades + a reason string
    if nothing could be tested.
    """
    result = {
        "stock": stock_name, "symbol": symbol, "sector": sector_name,
        "trades": [], "reason": "", "data_available": False,
    }

    intraday = _fetch_5m_history(symbol)
    daily    = _fetch_daily_history(symbol)

    if intraday is None:
        result["reason"] = "Could not fetch 5-min intraday history"
        return result
    if daily is None:
        result["reason"] = f"Need {MIN_DAILY_BARS_FOR_STRUCTURE}+ days of daily history for structure validation"
        return result

    trading_dates = sorted(set(intraday.index.date))
    struct_lookup = _build_daily_structure_lookup(stock_name, daily, trading_dates)
    regime_map    = nifty_regime_map or {}

    closes = intraday["Close"].values
    highs  = intraday["High"].values
    lows   = intraday["Low"].values
    times  = intraday.index

    n = len(intraday)
    trades = []
    position = None   # dict while a trade is open, else None

    for i in range(1, n):
        bar_time  = times[i]
        bar_close = float(closes[i])
        bar_high  = float(highs[i])
        bar_low   = float(lows[i])

        # ── MANAGE OPEN POSITION ──────────────────
        if position is not None:
            # 1. Mandatory 3:15 PM cutoff — always wins
            if bar_time.time() >= dtime(MANDATORY_EXIT_HOUR, MANDATORY_EXIT_MINUTE):
                position = _close_trade(position, bar_close, bar_time, "TIME_EXIT", trades)
                continue

            direction   = position["direction"]
            stop_price  = position["stop_price"]

            # 2. Hard stop (conservative: check intrabar extreme)
            stop_hit = (
                (direction == "LONG"  and bar_low  <= stop_price) or
                (direction == "SHORT" and bar_high >= stop_price)
            )
            if stop_hit:
                reason = "PARTIAL_THEN_BREAKEVEN" if position["partial_sold"] else "STOP"
                position = _close_trade(position, stop_price, bar_time, reason, trades)
                continue

            # 3. Target 1 — partial exit + breakeven (only once)
            if not position["partial_sold"] and position["target_1"] is not None:
                t1 = position["target_1"]
                hit_t1 = (
                    (direction == "LONG"  and bar_high >= t1) or
                    (direction == "SHORT" and bar_low  <= t1)
                )
                if hit_t1:
                    position["partial_sold"]      = True
                    position["partial_price"]      = t1
                    position["partial_time"]       = bar_time
                    position["stop_price"]         = position["entry_price"]  # breakeven
                    continue

            # 4. Remainder: Target 2 / EMA trail (only after partial)
            if position["partial_sold"]:
                t2 = position["target_2"]
                if t2 is not None:
                    hit_t2 = (
                        (direction == "LONG"  and bar_high >= t2) or
                        (direction == "SHORT" and bar_low  <= t2)
                    )
                    if hit_t2:
                        position = _close_trade(position, t2, bar_time, "PARTIAL_THEN_TARGET2", trades)
                        continue

                window = intraday.iloc[max(0, i - COMPRESSION_WINDOW_BUFFER):i + 1]
                ema_check = check_ema_trail_exit(direction, window)
                if ema_check.get("exit_triggered"):
                    position = _close_trade(position, bar_close, bar_time, "PARTIAL_THEN_TRAIL_EMA", trades)
                    continue

            continue   # still holding — next bar

        # ── LOOK FOR NEW ENTRY (no open position) ──
        compression_candle_idx = i - 1
        candle_time = times[compression_candle_idx]

        # No fresh entries flagged in the last ~30 min of the day —
        # a compression candle that late has no realistic same-day follow-through
        if candle_time.time() >= dtime(NO_NEW_ENTRY_AFTER_HOUR, NO_NEW_ENTRY_AFTER_MINUTE):
            continue

        struct = struct_lookup.get(candle_time.date())
        if not struct or not struct.get("data_available"):
            continue

        if struct["valid_for_long"]:
            direction = "LONG"
        elif struct["valid_for_short"]:
            direction = "SHORT"
        else:
            continue

        window = intraday.iloc[max(0, compression_candle_idx - COMPRESSION_WINDOW_BUFFER):compression_candle_idx + 1]
        vol_c = detect_volume_compression(window)
        vlt_c = detect_volatility_compression(window)
        if not (vol_c["volume_compression"] and vlt_c["volatility_compression"]):
            continue

        comp_high = float(highs[compression_candle_idx])
        comp_low  = float(lows[compression_candle_idx])

        breakout = (bar_high > comp_high) if direction == "LONG" else (bar_low < comp_low)
        if not breakout:
            continue

        entry_price = comp_high if direction == "LONG" else comp_low
        zone         = struct["demand_zone"] if direction == "LONG" else struct["supply_zone"]
        opposite_zone= struct["supply_zone"] if direction == "LONG" else struct["demand_zone"]

        atr_value = None
        try:
            atr_series = _calculate_atr(window, period=ATR_STOP_PERIOD)
            latest_atr = atr_series.iloc[-1]
            if not pd.isna(latest_atr):
                atr_value = round(float(latest_atr), 2)
        except Exception:
            pass

        stop_result = calculate_stop_loss(
            direction=direction, entry_price=entry_price, zone=zone,
            compression_candle_high=comp_high, compression_candle_low=comp_low,
            atr_value=atr_value,
        )
        if stop_result is None:
            continue   # invalid setup — no valid stop, skip

        target_result = calculate_targets(
            direction=direction, entry_price=entry_price,
            stop_price=stop_result["stop_price"],
            risk_per_share=stop_result["risk_per_share"],
            opposite_zone=opposite_zone,
        )

        position = {
            "stock": stock_name, "symbol": symbol, "sector": sector_name,
            "direction": direction,
            "entry_price": entry_price, "entry_time": bar_time,
            "stop_price": stop_result["stop_price"],
            "risk_per_share": stop_result["risk_per_share"],
            "target_1": target_result["target_1"],
            "target_2": target_result["target_2"],
            "partial_sold": False, "partial_price": None, "partial_time": None,
            "day_regime": regime_map.get(str(bar_time.date()), "UNKNOWN"),
        }

    # ── Force-close any position still open at end of data ──
    if position is not None:
        position = _close_trade(
            position, float(closes[-1]), times[-1], "END_OF_DATA", trades
        )

    result["trades"]         = trades
    result["data_available"] = True
    result["reason"]         = (
        f"{len(trades)} trade(s) simulated" if trades else "No qualifying entries in this window"
    )
    return result


def _close_trade(position, exit_price, exit_time, exit_reason, trades_out):
    """Finalize a position into a completed trade record. Returns None."""
    direction   = position["direction"]
    entry_price = position["entry_price"]
    risk        = position["risk_per_share"]

    if position["partial_sold"]:
        half1 = position["partial_price"] - entry_price if direction == "LONG" else entry_price - position["partial_price"]
        half2 = exit_price - entry_price if direction == "LONG" else entry_price - exit_price
        pnl_per_share = 0.5 * half1 + 0.5 * half2
    else:
        pnl_per_share = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)

    r_multiple = round(pnl_per_share / risk, 3) if risk else 0.0
    pnl_pct    = round((pnl_per_share / entry_price) * 100, 3)
    holding_minutes = round((exit_time - position["entry_time"]).total_seconds() / 60, 1)

    trades_out.append({
        "stock":            position["stock"],
        "symbol":           position["symbol"],
        "sector":           position["sector"],
        "direction":        direction,
        "entry_time":       position["entry_time"],
        "entry_price":      round(entry_price, 2),
        "exit_time":        exit_time,
        "exit_price":       round(exit_price, 2),
        "stop_price":       round(position["stop_price"], 2),
        "target_1":         position["target_1"],
        "target_2":         position["target_2"],
        "partial_sold":     position["partial_sold"],
        "exit_reason":      exit_reason,
        "r_multiple":       r_multiple,
        "pnl_pct":          pnl_pct,
        "holding_minutes":  holding_minutes,
        "day_regime":       position["day_regime"],
    })
    return None


# ════════════════════════════════════════════════
# BATCH RUNNER — full watchlist
# ════════════════════════════════════════════════

def run_intraday_backtest_batch(
    watchlist_dict: dict,
    sector_map: dict = None,
    max_workers: int = SCANNER_MAX_WORKERS,
) -> dict:
    """
    Runs run_intraday_backtest() across a watchlist in parallel.
    Fetches the NIFTY regime history ONCE and shares it.
    """
    regime_map = fetch_nifty_regime_history()
    all_trades = []
    tested     = []
    skipped    = []

    def _worker(item):
        name, symbol = item
        sector = (sector_map or {}).get(name, "Unknown")
        return run_intraday_backtest(name, symbol, sector, regime_map)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, item): item for item in watchlist_dict.items()}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception:
                continue

            if r["data_available"]:
                tested.append({"stock": r["stock"], "trades": len(r["trades"])})
                all_trades.extend(r["trades"])
            else:
                skipped.append({"stock": r["stock"], "reason": r["reason"]})

    trades_df = pd.DataFrame(all_trades) if all_trades else pd.DataFrame()
    return {
        "trades_df": trades_df,
        "tested":    tested,
        "skipped":   skipped,
        "regime_map_available": bool(regime_map),
    }


# ════════════════════════════════════════════════
# PERFORMANCE METRICS (Module 15 requirements)
# ════════════════════════════════════════════════

def _max_drawdown_r(trades_df: pd.DataFrame) -> float:
    if trades_df.empty:
        return 0.0
    ordered = trades_df.sort_values("exit_time")
    equity  = ordered["r_multiple"].cumsum()
    peak    = equity.cummax()
    dd      = equity - peak
    return round(float(dd.min()), 2)


def _sharpe_sortino(trades_df: pd.DataFrame) -> dict:
    """
    Aggregates R-multiples to a DAILY series (summed per day), then
    annualizes with sqrt(252). Approximation — documented in the
    report's "notes" field, not presented as a precise annualized figure.
    """
    if trades_df.empty:
        return {"sharpe": 0.0, "sortino": 0.0}

    daily = trades_df.groupby(trades_df["exit_time"].dt.date)["r_multiple"].sum()
    if len(daily) < 2 or daily.std() == 0:
        return {"sharpe": 0.0, "sortino": 0.0}

    mean_r = daily.mean()
    std_r  = daily.std()
    sharpe = round((mean_r / std_r) * np.sqrt(252), 2)

    downside = daily[daily < 0]
    if len(downside) == 0 or downside.std() == 0:
        sortino = round(sharpe, 2)   # no downside observed — cap at Sharpe
    else:
        sortino = round((mean_r / downside.std()) * np.sqrt(252), 2)

    return {"sharpe": sharpe, "sortino": sortino}


def calculate_performance_metrics(trades_df: pd.DataFrame) -> dict:
    """Module 15 — the full standard metric set."""
    if trades_df.empty:
        return {
            "Total Trades": 0, "Win Rate": "0%", "Profit Factor": "N/A",
            "Avg R-Multiple": 0, "Expectancy %": "0%",
            "Max Drawdown (R)": 0, "Sharpe Ratio": 0, "Sortino Ratio": 0,
            "Avg Holding Time": "N/A",
        }

    wins   = trades_df[trades_df["r_multiple"] > 0]
    losses = trades_df[trades_df["r_multiple"] <= 0]

    gross_win  = wins["r_multiple"].sum()
    gross_loss = abs(losses["r_multiple"].sum())
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf")

    ss = _sharpe_sortino(trades_df)
    avg_minutes = trades_df["holding_minutes"].mean()
    hh = int(avg_minutes // 60)
    mm = int(avg_minutes % 60)

    return {
        "Total Trades":     len(trades_df),
        "Win Rate":         f"{round(len(wins) / len(trades_df) * 100, 1)}%",
        "Profit Factor":    profit_factor if profit_factor != float("inf") else "∞ (no losses)",
        "Avg R-Multiple":   round(trades_df["r_multiple"].mean(), 3),
        "Expectancy %":     f"{round(trades_df['pnl_pct'].mean(), 3)}%",
        "Max Drawdown (R)": _max_drawdown_r(trades_df),
        "Sharpe Ratio":     ss["sharpe"],
        "Sortino Ratio":    ss["sortino"],
        "Avg Holding Time": f"{hh}h {mm}m",
    }


def _group_performance(trades_df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if trades_df.empty or group_col not in trades_df.columns:
        return pd.DataFrame()

    rows = []
    for group_val, g in trades_df.groupby(group_col):
        wins = g[g["r_multiple"] > 0]
        gross_win  = wins["r_multiple"].sum()
        gross_loss = abs(g[g["r_multiple"] <= 0]["r_multiple"].sum())
        rows.append({
            group_col.replace("_", " ").title(): group_val,
            "Trades":         len(g),
            "Win Rate":       f"{round(len(wins) / len(g) * 100, 1)}%",
            "Avg R":          round(g["r_multiple"].mean(), 3),
            "Total R":        round(g["r_multiple"].sum(), 2),
            "Profit Factor":  round(gross_win / gross_loss, 2) if gross_loss > 0 else "∞",
        })

    df = pd.DataFrame(rows).sort_values("Total R", ascending=False).reset_index(drop=True)
    return df


def get_sector_wise_performance(trades_df: pd.DataFrame) -> pd.DataFrame:
    return _group_performance(trades_df, "sector")


def get_regime_wise_performance(trades_df: pd.DataFrame) -> pd.DataFrame:
    return _group_performance(trades_df, "day_regime")


# ════════════════════════════════════════════════
# MASTER FUNCTION — called by app.py Tab 6
# ════════════════════════════════════════════════

def get_intraday_backtest_report(watchlist_dict: dict = None, active_only: bool = True) -> dict:
    """
    Runs the full M38K pipeline and returns everything the
    dashboard needs in one call.
    """
    result = {
        "overall_metrics":     {},
        "sector_performance":  pd.DataFrame(),
        "regime_performance":  pd.DataFrame(),
        "trades_df":           pd.DataFrame(),
        "tested":              [],
        "skipped":             [],
        "notes": (
            "Backtest window limited to ~60 days (yfinance's 5-min data ceiling). "
            "Sector performance uses each stock's static watchlist sector, not a "
            "re-ranked historical sector score. Regime-wise performance uses the "
            "daily regime engine as a proxy for the intraday direction filter. "
            "Sharpe/Sortino are computed on daily-aggregated R-multiples, annualised "
            "with sqrt(252) — treat as a relative comparison metric."
        ),
        "fetched_at":      datetime.now().strftime('%d %b %Y %H:%M'),
        "data_available":  False,
    }

    if watchlist_dict is None:
        from strategies.watchlist_manager import get_watchlist_dict, load_watchlist
        watchlist_dict = get_watchlist_dict(active_only=active_only)
        wl_df = load_watchlist(active_only=active_only)
        sector_map = dict(zip(wl_df["Name"], wl_df["Sector"])) if not wl_df.empty else {}
    else:
        sector_map = {}

    if not watchlist_dict:
        return result

    batch = run_intraday_backtest_batch(watchlist_dict, sector_map=sector_map)
    trades_df = batch["trades_df"]

    result.update({
        "overall_metrics":    calculate_performance_metrics(trades_df),
        "sector_performance": get_sector_wise_performance(trades_df),
        "regime_performance": get_regime_wise_performance(trades_df),
        "trades_df":          trades_df,
        "tested":             batch["tested"],
        "skipped":            batch["skipped"],
        "data_available":     True,
    })
    return result