# ================================================
# FILE: strategies/sector_strength.py
# PURPOSE: Sector Strength Engine — Milestone 38A
#          Module 2 of the Volume Compression Pullback
#          Strategy (VCPS) intraday specification.
#
# WHAT THIS DOES:
#   Ranks all sectors in the watchlist by strength so the
#   Intraday Engine (M38B) only looks for trades inside the
#   3 strongest sectors of the day — "trade the leaders,
#   not the laggards."
#
# SECTOR SCORE FORMULA (from spec):
#   Sector Score = 0.40 × Relative Strength
#                + 0.30 × Sector Return
#                + 0.20 × Breadth
#                + 0.10 × Volume Expansion
#
# DEFINITIONS:
#   Sector Return      — average % price return of stocks
#                         in the sector over the lookback period
#   Relative Strength   — Sector Return minus NIFTY Return
#                         (positive = sector beating the market)
#   Breadth             — % of stocks in the sector trading
#                         above their own 20-day MA (checks real
#                         participation, not 1-2 stocks pulling
#                         the average up)
#   Volume Expansion     — average (today's volume / 20-day avg)
#                         across the sector's stocks — are more
#                         people trading this sector right now?
#
# HOW IT CONNECTS:
#   watchlist_manager.py   → load_watchlist() for Symbol/Sector data
#   Upcoming M38B (intraday_engine.py) will call get_top_sectors()
#   to restrict its stock universe to today's leaders.
# ================================================

import pandas as pd
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from strategies.watchlist_manager import load_watchlist

NIFTY_SYMBOL = "^NSEI"

try:
    from config.settings import SCANNER_MAX_WORKERS
except ImportError:
    SCANNER_MAX_WORKERS = 10

LOOKBACK_DAYS         = 20   # ~1 trading month for sector return calc
MIN_STOCKS_PER_SECTOR = 2    # skip sectors too small to trust the average


def _fetch_stock_for_sector(symbol, period="2mo"):
    """
    Fetch OHLCV data for one stock — used to build sector stats.
    Returns None on any failure (never crashes the engine).
    """
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
        if len(data) < 10:
            return None
        return data
    except Exception:
        return None


def _calculate_stock_stats(data, lookback_days=LOOKBACK_DAYS):
    """
    Per-stock numbers needed for sector aggregation:
      - period return %
      - above/below 20-day MA (for breadth)
      - volume ratio (today vs 20-day average)
    Returns None if not enough data.
    """
    if data is None or len(data) < lookback_days + 1:
        return None

    try:
        closes = data["Close"]
        actual_days = min(lookback_days, len(data) - 1)

        start_price = float(closes.iloc[-actual_days])
        end_price   = float(closes.iloc[-1])
        ret_pct     = round(((end_price - start_price) / start_price) * 100, 2)

        ma20 = closes.rolling(window=20).mean()
        above_ma20 = bool(end_price > float(ma20.iloc[-1])) if not pd.isna(ma20.iloc[-1]) else None

        vol       = data["Volume"]
        vol_ma20  = vol.rolling(window=20).mean()
        today_vol = float(vol.iloc[-1])
        avg_vol   = float(vol_ma20.iloc[-1]) if not pd.isna(vol_ma20.iloc[-1]) else None
        vol_ratio = round(today_vol / avg_vol, 3) if avg_vol and avg_vol > 0 else None

        return {
            "return_pct": ret_pct,
            "above_ma20": above_ma20,
            "vol_ratio":  vol_ratio,
        }
    except Exception:
        return None


def _fetch_nifty_return(lookback_days=LOOKBACK_DAYS):
    """Fetch NIFTY 50 return over the same lookback period — the benchmark."""
    data  = _fetch_stock_for_sector(NIFTY_SYMBOL, period="2mo")
    stats = _calculate_stock_stats(data, lookback_days)
    return stats["return_pct"] if stats else 0.0


def _fetch_all_sector_stocks(watchlist_df, max_workers=SCANNER_MAX_WORKERS):
    """
    Parallel-fetch data for every active stock in the watchlist.
    Returns {symbol: stats_dict} for stocks with usable data.
    """
    symbols = watchlist_df["Symbol"].tolist()
    results = {}

    def _worker(symbol):
        data  = _fetch_stock_for_sector(symbol)
        stats = _calculate_stock_stats(data)
        return symbol, stats

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, sym): sym for sym in symbols}
        for future in as_completed(futures):
            try:
                symbol, stats = future.result()
                if stats is not None:
                    results[symbol] = stats
            except Exception:
                continue

    return results


def calculate_sector_scores(active_only=True):
    """
    Master function — calculates the Sector Score for every
    sector in the watchlist and ranks them.

    Returns a DataFrame sorted by Sector Score descending:
      Rank | Sector | Sector Return % | Relative Strength % |
      Breadth % | Volume Expansion | Stock Count | Sector Score

    Sectors with fewer than MIN_STOCKS_PER_SECTOR active stocks
    are excluded — not enough data to trust the average.
    """
    watchlist_df = load_watchlist(active_only=active_only)
    if watchlist_df.empty:
        return pd.DataFrame()

    nifty_return = _fetch_nifty_return()
    stock_stats  = _fetch_all_sector_stocks(watchlist_df)

    watchlist_df = watchlist_df.copy()
    watchlist_df["_stats"] = watchlist_df["Symbol"].map(stock_stats)
    watchlist_df = watchlist_df[watchlist_df["_stats"].notna()]

    if watchlist_df.empty:
        return pd.DataFrame()

    rows = []

    for sector, group in watchlist_df.groupby("Sector"):
        stats_list  = group["_stats"].tolist()
        stock_count = len(stats_list)

        if stock_count < MIN_STOCKS_PER_SECTOR:
            continue

        returns    = [s["return_pct"] for s in stats_list if s["return_pct"] is not None]
        above_ma   = [s["above_ma20"] for s in stats_list if s["above_ma20"] is not None]
        vol_ratios = [s["vol_ratio"]  for s in stats_list if s["vol_ratio"]  is not None]

        if not returns:
            continue

        sector_return = round(sum(returns) / len(returns), 2)
        rel_strength  = round(sector_return - nifty_return, 2)
        breadth_pct   = round((sum(above_ma) / len(above_ma)) * 100, 1) if above_ma else 50.0
        vol_expansion = round(sum(vol_ratios) / len(vol_ratios), 3) if vol_ratios else 1.0

        rows.append({
            "Sector":              sector,
            "Sector Return %":     sector_return,
            "Relative Strength %": rel_strength,
            "Breadth %":           breadth_pct,
            "Volume Expansion":    vol_expansion,
            "Stock Count":         stock_count,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # ── Normalise components onto comparable scales ───────
    # Relative Strength / Sector Return are already %.
    # Breadth is already 0-100.
    # Volume Expansion (typically ~0.5-2.5x) is scaled ×20 so
    # 1.0x average volume contributes ~20 pts, 2x+ contributes strongly.
    rs_component     = df["Relative Strength %"]
    return_component = df["Sector Return %"]
    breadth_component= df["Breadth %"]
    volume_component = df["Volume Expansion"] * 20

    df["Sector Score"] = (
        rs_component      * 0.40 +
        return_component  * 0.30 +
        breadth_component * 0.20 +
        volume_component  * 0.10
    ).round(2)

    df = df.sort_values("Sector Score", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", df.index + 1)

    return df


def get_top_sectors(n=3, active_only=True):
    """
    Convenience wrapper — returns just the names of the top N sectors.
    Used by the Intraday Engine (M38B) to restrict its stock universe.
    """
    df = calculate_sector_scores(active_only=active_only)
    if df.empty:
        return []
    return df.head(n)["Sector"].tolist()


def get_sector_rank(sector_name, active_only=True):
    """
    Return (rank, score) for a single sector. (None, None) if not found.
    Lets the Intraday Engine ask "is this stock's sector top-3 today?"
    without recalculating everything itself.
    """
    df = calculate_sector_scores(active_only=active_only)
    if df.empty:
        return None, None
    match = df[df["Sector"] == sector_name]
    if match.empty:
        return None, None
    row = match.iloc[0]
    return int(row["Rank"]), float(row["Sector Score"])


def get_sector_strength_summary(active_only=True):
    """
    Full display-ready result for the dashboard.
    Returns the ranked DataFrame, top 3 sector names, and metadata.
    """
    df = calculate_sector_scores(active_only=active_only)

    if df.empty:
        return {
            "ranked_df":      pd.DataFrame(),
            "top_sectors":    [],
            "fetched_at":     datetime.now().strftime('%d %b %Y %H:%M'),
            "data_available": False,
        }

    return {
        "ranked_df":      df,
        "top_sectors":    df.head(3)["Sector"].tolist(),
        "fetched_at":     datetime.now().strftime('%d %b %Y %H:%M'),
        "data_available": True,
    }