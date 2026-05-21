# ================================================
# FILE: strategies/relative_strength.py
# PURPOSE: Relative Strength Ranking
#          Compare each stock vs NIFTY 50
#          Find which stocks are outperforming
#
# WHY THIS MATTERS:
#   A stock rising 5% when NIFTY is also up 5%
#   is NOT a strong stock — it just moved with market.
#
#   A stock rising 10% when NIFTY is up 5%
#   IS a strong stock — it beat the market.
#
#   Relative Strength tells you which stocks
#   are LEADERS vs LAGGARDS.
#
# HOW IT WORKS:
#   RS Score = Stock Return / NIFTY Return
#   RS > 1.0  = outperforming NIFTY (strong)
#   RS < 1.0  = underperforming NIFTY (weak)
#   RS = 1.0  = moving with NIFTY (neutral)
#
# WE CALCULATE:
#   - 1 month RS
#   - 3 month RS
#   - 6 month RS
#   - Composite RS Score (weighted average)
#   - Momentum rank across watchlist
# ================================================

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


# ── Settings ──────────────────────────────────────
NIFTY_SYMBOL = "^NSEI"    # NIFTY 50 benchmark

# Weights for composite RS score
# More weight to recent performance
RS_WEIGHTS = {
    "1mo":  0.50,   # Last month matters most
    "3mo":  0.30,   # Last quarter
    "6mo":  0.20,   # Last 6 months
}


def fetch_price_data(symbol, period="6mo"):
    """
    Fetch price data for a single symbol.
    Returns None if fetch fails.
    """
    try:
        data = yf.download(
            tickers  = symbol,
            period   = period,
            interval = "1d",
            progress = False
        )
        if data.empty:
            return None
        data.columns = [col[0] for col in data.columns]
        return data
    except Exception:
        return None


def calculate_return(data, days):
    """
    Calculate return over last N trading days.
    Returns percentage return or None if not enough data.
    """
    if data is None or len(data) < days:
        return None

    try:
        start_price = float(data['Close'].iloc[-days])
        end_price   = float(data['Close'].iloc[-1])
        return round(((end_price - start_price) / start_price) * 100, 2)
    except Exception:
        return None


def calculate_rs_score(stock_return, nifty_return):
    """
    Calculate Relative Strength score.

    RS = Stock Return - NIFTY Return
    Positive = outperforming
    Negative = underperforming

    We use difference (not ratio) to handle
    cases where NIFTY return is negative.
    """
    if stock_return is None or nifty_return is None:
        return None
    return round(stock_return - nifty_return, 2)


def get_nifty_returns(nifty_data):
    """
    Calculate NIFTY returns for 1mo, 3mo, 6mo periods.
    Returns a dictionary of returns.
    """
    # Approximate trading days
    periods = {
        "1mo":  21,
        "3mo":  63,
        "6mo":  126,
    }

    returns = {}
    for period, days in periods.items():
        returns[period] = calculate_return(nifty_data, days)

    return returns


def rank_stocks_by_rs(watchlist_dict):
    """
    Calculate relative strength for all stocks
    in the watchlist and rank them.

    watchlist_dict = {"RELIANCE": "RELIANCE.NS", ...}

    Returns a ranked dataframe with RS scores.
    This is the core function of Milestone 19.
    """

    # Step 1: Fetch NIFTY data as benchmark
    nifty_data    = fetch_price_data(NIFTY_SYMBOL, period="6mo")
    nifty_returns = get_nifty_returns(nifty_data) if nifty_data is not None else {}

    rows = []

    # Step 2: Calculate RS for each stock
    for name, symbol in watchlist_dict.items():

        try:
            # Fetch stock data
            stock_data = fetch_price_data(symbol, period="6mo")

            if stock_data is None or stock_data.empty:
                continue

            # Current price
            current_price = round(float(stock_data['Close'].iloc[-1]), 2)

            # Calculate returns for each period
            ret_1mo = calculate_return(stock_data, 21)
            ret_3mo = calculate_return(stock_data, 63)
            ret_6mo = calculate_return(stock_data, 126)

            # NIFTY returns for same periods
            nifty_1mo = nifty_returns.get("1mo")
            nifty_3mo = nifty_returns.get("3mo")
            nifty_6mo = nifty_returns.get("6mo")

            # RS scores vs NIFTY
            rs_1mo = calculate_rs_score(ret_1mo, nifty_1mo)
            rs_3mo = calculate_rs_score(ret_3mo, nifty_3mo)
            rs_6mo = calculate_rs_score(ret_6mo, nifty_6mo)

            # Composite RS score (weighted average)
            composite_rs = None
            available_scores = []
            total_weight     = 0

            if rs_1mo is not None:
                available_scores.append(rs_1mo * RS_WEIGHTS["1mo"])
                total_weight += RS_WEIGHTS["1mo"]
            if rs_3mo is not None:
                available_scores.append(rs_3mo * RS_WEIGHTS["3mo"])
                total_weight += RS_WEIGHTS["3mo"]
            if rs_6mo is not None:
                available_scores.append(rs_6mo * RS_WEIGHTS["6mo"])
                total_weight += RS_WEIGHTS["6mo"]

            if available_scores and total_weight > 0:
                composite_rs = round(sum(available_scores) / total_weight, 2)

            # RS Rating label
            if composite_rs is None:
                rs_rating = "N/A"
            elif composite_rs >= 5:
                rs_rating = "STRONG 🟢"
            elif composite_rs >= 1:
                rs_rating = "ABOVE MARKET 📈"
            elif composite_rs >= -1:
                rs_rating = "IN LINE ↔️"
            elif composite_rs >= -5:
                rs_rating = "BELOW MARKET 📉"
            else:
                rs_rating = "WEAK 🔴"

            rows.append({
                "Stock":         name,
                "Price":         current_price,
                "1M Return":     f"{ret_1mo}%" if ret_1mo is not None else "N/A",
                "3M Return":     f"{ret_3mo}%" if ret_3mo is not None else "N/A",
                "6M Return":     f"{ret_6mo}%" if ret_6mo is not None else "N/A",
                "RS vs NIFTY 1M":f"{rs_1mo}%" if rs_1mo is not None else "N/A",
                "RS vs NIFTY 3M":f"{rs_3mo}%" if rs_3mo is not None else "N/A",
                "RS Score":      composite_rs if composite_rs is not None else 0,
                "RS Rating":     rs_rating,
                # Hidden numeric for sorting
                "_rs_score":     composite_rs if composite_rs is not None else -999,
            })

        except Exception as e:
            continue

    if not rows:
        return pd.DataFrame()

    # Step 3: Sort by composite RS score descending
    df = pd.DataFrame(rows)
    df = df.sort_values("_rs_score", ascending=False).reset_index(drop=True)

    # Step 4: Add rank
    df.insert(0, "Rank", range(1, len(df) + 1))

    # Step 5: Add NIFTY benchmark row
    nifty_row = {
        "Rank":          "📊",
        "Stock":         "NIFTY 50",
        "Price":         round(float(nifty_data['Close'].iloc[-1]), 2) if nifty_data is not None else "N/A",
        "1M Return":     f"{nifty_returns.get('1mo')}%" if nifty_returns.get('1mo') else "N/A",
        "3M Return":     f"{nifty_returns.get('3mo')}%" if nifty_returns.get('3mo') else "N/A",
        "6M Return":     f"{nifty_returns.get('6mo')}%" if nifty_returns.get('6mo') else "N/A",
        "RS vs NIFTY 1M":"0% (benchmark)",
        "RS vs NIFTY 3M":"0% (benchmark)",
        "RS Score":      0,
        "RS Rating":     "BENCHMARK",
        "_rs_score":     0,
    }

    # Add NIFTY as last row for reference
    df = pd.concat([df, pd.DataFrame([nifty_row])], ignore_index=True)

    # Drop hidden column before returning
    display_df = df.drop(columns=["_rs_score"])

    return display_df


def get_sector_rs(watchlist_df, price_data_cache=None):
    """
    Calculate average RS score by sector.
    Shows which sectors are leading vs lagging.

    watchlist_df = full watchlist dataframe with Sector column
    Returns a sector-level summary dataframe.
    """
    if watchlist_df.empty or 'Sector' not in watchlist_df.columns:
        return pd.DataFrame()

    # We need RS scores per stock
    # For now return sector grouping from watchlist
    sector_summary = watchlist_df.groupby('Sector').agg(
        Stocks=('Name', 'count')
    ).reset_index()

    return sector_summary


def get_top_rs_stocks(rs_df, n=3):
    """
    Return the top N stocks by RS score.
    These are the market leaders — strongest stocks.
    """
    if rs_df.empty:
        return pd.DataFrame()

    # Exclude the NIFTY benchmark row
    stock_df = rs_df[rs_df['Stock'] != 'NIFTY 50']

    return stock_df.head(n)


def get_bottom_rs_stocks(rs_df, n=3):
    """
    Return the bottom N stocks by RS score.
    These are the laggards — weakest stocks.
    Avoid trading these in a bull market.
    """
    if rs_df.empty:
        return pd.DataFrame()

    stock_df = rs_df[rs_df['Stock'] != 'NIFTY 50']

    return stock_df.tail(n)
