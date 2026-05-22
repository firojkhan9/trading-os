# ================================================
# FILE: strategies/performance_scanner.py
# PURPOSE: Scan ALL watchlist stocks at once
#          and return sorted performance tables
#
# WHAT IT DOES:
#   For every stock in the watchlist it calculates:
#   1. Price return over any period you choose
#   2. Composite intelligence score (0-100)
#   3. Signal from each strategy
#   4. Relative strength vs NIFTY
#
# OUTPUT TABLES:
#   - Best performers (sorted by return, highest first)
#   - Worst performers (sorted by return, lowest first)
#   - Best scores (sorted by composite score)
#   - Full scan table (everything together)
#
# PERIOD OPTIONS:
#   Any number of days: 5, 10, 30, 90, 180, 365...
#   The dashboard lets user pick freely.
# ================================================

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from strategies.indicators import calculate_ma20, calculate_rsi, analyze_stock
from strategies.ema_strategy import calculate_ema_signals, get_ema_summary
from strategies.bollinger_strategy import analyze_bollinger, get_bollinger_summary
from strategies.macd_strategy import analyze_macd, get_macd_summary
from strategies.combined_signal import build_combined_summary
from strategies.scoring_engine import build_composite_score


# ── NIFTY symbol for RS calculation ──────────────
NIFTY_SYMBOL = "^NSEI"


def days_to_yf_period(days):
    """
    Convert number of days to yfinance period string.
    yfinance accepts: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 3y
    We map days to the nearest valid period.
    """
    if days <= 5:
        return "5d"
    elif days <= 30:
        return "1mo"
    elif days <= 90:
        return "3mo"
    elif days <= 180:
        return "6mo"
    elif days <= 365:
        return "1y"
    elif days <= 730:
        return "2y"
    else:
        return "3y"


def fetch_stock_for_scan(symbol, period="1y"):
    """
    Fetch stock data for scanning.
    Returns None if fetch fails.
    """
    try:
        data = yf.download(
            tickers=symbol, period=period,
            interval="1d", progress=False
        )
        if data.empty or len(data) < 30:
            return None
        data.columns = [col[0] for col in data.columns]
        return data
    except Exception:
        return None


def calculate_period_return(data, days):
    """
    Calculate return over last N trading days.
    Returns percentage return or None.
    """
    if data is None or len(data) < days:
        # Use all available data if not enough history
        if data is not None and len(data) >= 2:
            days = len(data) - 1
        else:
            return None

    try:
        start_price = float(data['Close'].iloc[-days])
        end_price   = float(data['Close'].iloc[-1])
        return round(((end_price - start_price) / start_price) * 100, 2)
    except Exception:
        return None


def get_signal_summary(data):
    """
    Run all 4 strategies on stock data and
    return a combined signal summary.
    """
    try:
        analyzed     = analyze_stock(data.copy())
        ema_data     = calculate_ema_signals(data.copy())
        bb_data      = analyze_bollinger(data.copy())
        macd_data    = analyze_macd(data.copy())

        latest_ma    = analyzed.iloc[-1]
        latest_ema   = ema_data.iloc[-1]
        latest_bb    = bb_data.iloc[-1]
        latest_macd  = macd_data.iloc[-1]

        ma_signal    = latest_ma['Signal']
        ema_signal   = latest_ema['EMA_Signal']
        bb_signal    = latest_bb['BB_Signal']
        macd_signal  = latest_macd['MACD_Crossover']

        combined = build_combined_summary(
            ma_signal=ma_signal, ema_signal=ema_signal,
            bb_signal=bb_signal, macd_signal=macd_signal,
        )

        return {
            "ma_signal":    ma_signal,
            "ema_signal":   ema_signal,
            "bb_signal":    bb_signal,
            "macd_signal":  macd_signal,
            "combined":     combined,
            "analyzed":     analyzed,
            "ema_data":     ema_data,
            "bb_data":      bb_data,
            "macd_data":    macd_data,
        }
    except Exception as e:
        return None


def calculate_composite_score_for_stock(stock_name, data, signal_info, regime):
    """
    Calculate composite intelligence score for one stock.
    Returns score dict or None if calculation fails.
    """
    try:
        analyzed    = signal_info["analyzed"]
        ema_data    = signal_info["ema_data"]
        bb_data     = signal_info["bb_data"]
        macd_data   = signal_info["macd_data"]
        combined    = signal_info["combined"]

        latest_ma   = analyzed.iloc[-1]
        latest_ema  = ema_data.iloc[-1]
        latest_bb   = bb_data.iloc[-1]
        latest_macd = macd_data.iloc[-1]

        s_close  = round(float(latest_ma['Close']), 2)
        s_ma20   = round(float(latest_ma['MA20']), 2)   if not pd.isna(latest_ma['MA20'])   else None
        s_rsi    = round(float(latest_ma['RSI']), 2)    if not pd.isna(latest_ma['RSI'])    else None
        s_ema9   = round(float(latest_ema['EMA9']), 2)  if not pd.isna(latest_ema['EMA9'])  else None
        s_ema21  = round(float(latest_ema['EMA21']), 2) if not pd.isna(latest_ema['EMA21']) else None
        s_macd   = float(latest_macd['MACD'])           if not pd.isna(latest_macd['MACD'])        else None
        s_msig   = float(latest_macd['MACD_Signal'])    if not pd.isna(latest_macd['MACD_Signal']) else None
        s_mhist  = float(latest_macd['MACD_Hist'])      if not pd.isna(latest_macd['MACD_Hist'])   else None
        s_bbpct  = float(latest_bb['BB_Pct'])           if not pd.isna(latest_bb['BB_Pct'])         else None
        s_bbsig  = latest_bb['BB_Signal']

        votes = {
            "buy":  combined["Strategies Buy"],
            "sell": combined["Strategies Sell"],
            "hold": combined["Strategies Hold"],
        }

        result = build_composite_score(
            stock_name=stock_name,
            latest_close=s_close, ma20=s_ma20, rsi=s_rsi,
            ema9=s_ema9, ema21=s_ema21,
            macd=s_macd, macd_signal=s_msig, macd_hist=s_mhist,
            bb_pct=s_bbpct, bb_signal=s_bbsig,
            combined_votes=votes,
            combined_weighted_score=combined["Score"],
            regime=regime, rs_score=None
        )
        return result

    except Exception as e:
        return None


def scan_all_stocks(watchlist_dict, period_days=30, regime="UNKNOWN ❓"):
    """
    Master scan function — runs everything for all stocks.

    Parameters:
      watchlist_dict : {"RELIANCE": "RELIANCE.NS", ...}
      period_days    : how many days to measure return over
      regime         : current market regime string

    Returns:
      full_df        : complete scan results
      best_return_df : top 5 by return
      worst_return_df: bottom 5 by return
      best_score_df  : top 5 by composite score
    """

    # Convert days to yfinance period
    yf_period = days_to_yf_period(period_days)

    # Fetch NIFTY for RS calculation
    nifty_data = fetch_stock_for_scan(NIFTY_SYMBOL, yf_period)
    nifty_return = None
    if nifty_data is not None:
        nifty_return = calculate_period_return(nifty_data, min(period_days, len(nifty_data) - 1))

    rows = []

    for name, symbol in watchlist_dict.items():
        try:
            # Fetch data
            data = fetch_stock_for_scan(symbol, "60d")  # Always 60d for indicators
            if data is None:
                continue

            # Also fetch longer period data for return calculation
            if period_days > 50:
                long_data = fetch_stock_for_scan(symbol, yf_period)
            else:
                long_data = data

            # Current price
            current_price = round(float(data['Close'].iloc[-1]), 2)

            # Period return
            actual_days   = min(period_days, len(long_data) - 1) if long_data is not None else min(period_days, len(data) - 1)
            period_return = calculate_period_return(long_data if long_data is not None else data, actual_days)

            # RS vs NIFTY
            rs_vs_nifty = None
            if period_return is not None and nifty_return is not None:
                rs_vs_nifty = round(period_return - nifty_return, 2)

            # RS rating
            if rs_vs_nifty is None:
                rs_rating = "N/A"
            elif rs_vs_nifty >= 5:
                rs_rating = "STRONG 🟢"
            elif rs_vs_nifty >= 1:
                rs_rating = "ABOVE ↑"
            elif rs_vs_nifty >= -1:
                rs_rating = "IN LINE ↔️"
            elif rs_vs_nifty >= -5:
                rs_rating = "BELOW ↓"
            else:
                rs_rating = "WEAK 🔴"

            # Strategy signals
            signal_info = get_signal_summary(data)

            combined_signal = "N/A"
            buy_votes       = 0
            if signal_info:
                combined_signal = signal_info["combined"]["Final Signal"]
                buy_votes       = signal_info["combined"]["Strategies Buy"]

            # Composite score
            composite_score = None
            score_action    = "N/A"
            if signal_info:
                score_result = calculate_composite_score_for_stock(
                    name, data, signal_info, regime
                )
                if score_result:
                    composite_score = score_result["Composite Score"]
                    score_action    = score_result["Action"]

            rows.append({
                "Stock":           name,
                "Price":           f"₹{current_price}",
                f"{period_days}D Return": f"{period_return}%" if period_return is not None else "N/A",
                "vs NIFTY":        f"{rs_vs_nifty}%" if rs_vs_nifty is not None else "N/A",
                "RS Rating":       rs_rating,
                "Combined Signal": combined_signal,
                "Buy Votes":       buy_votes,
                "Score":           composite_score if composite_score is not None else 0,
                "Action":          score_action,
                # Hidden numeric columns for sorting
                "_return":         period_return if period_return is not None else -999,
                "_score":          composite_score if composite_score is not None else 0,
                "_rs":             rs_vs_nifty if rs_vs_nifty is not None else -999,
            })

        except Exception as e:
            continue

    if not rows:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    full_df = pd.DataFrame(rows)

    # ── Sort tables ───────────────────────────────

    # Best performers by return
    best_return_df = (
        full_df[full_df['_return'] != -999]
        .sort_values('_return', ascending=False)
        .head(5)
        .drop(columns=['_return', '_score', '_rs'])
        .reset_index(drop=True)
    )
    best_return_df.insert(0, "Rank", ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][:len(best_return_df)])

    # Worst performers by return
    worst_return_df = (
        full_df[full_df['_return'] != -999]
        .sort_values('_return', ascending=True)
        .head(5)
        .drop(columns=['_return', '_score', '_rs'])
        .reset_index(drop=True)
    )
    worst_return_df.insert(0, "Rank", ["⚠️1", "⚠️2", "⚠️3", "⚠️4", "⚠️5"][:len(worst_return_df)])

    # Best composite scores
    best_score_df = (
        full_df[full_df['_score'] > 0]
        .sort_values('_score', ascending=False)
        .head(5)
        .drop(columns=['_return', '_score', '_rs'])
        .reset_index(drop=True)
    )
    best_score_df.insert(0, "Rank", ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][:len(best_score_df)])

    # Full table — sorted by score descending
    full_display_df = (
        full_df
        .sort_values('_score', ascending=False)
        .drop(columns=['_return', '_score', '_rs'])
        .reset_index(drop=True)
    )

    return full_display_df, best_return_df, worst_return_df, best_score_df
