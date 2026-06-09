# ================================================
# FILE: strategies/performance_scanner.py
# PURPOSE: Scan ALL watchlist stocks at once
#
# FIXES IN THIS VERSION:
#   - NIFTY always fetched with "1y" period so it never
#     returns < 30 rows (was causing all vs NIFTY and
#     RS Rating columns to show N/A)
#   - Fundamental score included in composite score
#   - Symbol column kept in full_df for quick buy panel
#   - min_rows lowered to 5 (was 30, too strict for NIFTY)
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

try:
    from strategies.fundamental_engine import get_fundamental_score_only
    FUNDAMENTALS_AVAILABLE = True
except ImportError:
    FUNDAMENTALS_AVAILABLE = False

try:
    from strategies.volume_engine import get_volume_score_only
    VOLUME_AVAILABLE = True
except ImportError:
    VOLUME_AVAILABLE = False

try:
    from strategies.market_structure import get_market_structure_analysis, get_market_structure_score_only
    MARKET_STRUCTURE_AVAILABLE = True
except ImportError:
    MARKET_STRUCTURE_AVAILABLE = False

NIFTY_SYMBOL = "^NSEI"


def days_to_yf_period(days):
    if days <= 5:    return "5d"
    elif days <= 30: return "1mo"
    elif days <= 90: return "3mo"
    elif days <= 180:return "6mo"
    elif days <= 365:return "1y"
    elif days <= 730:return "2y"
    else:            return "3y"


def fetch_stock_for_scan(symbol, period="1y", min_rows=5):
    """
    Fetch stock data for scanning.
    Drops null Close rows so midnight/weekend empty candles
    don't corrupt price calculations.
    """
    try:
        data = yf.download(
            tickers=symbol, period=period,
            interval="1d", progress=False,
            auto_adjust=True
        )
        if data.empty:
            return None

        data.columns = [col[0] for col in data.columns]

        # Drop rows where Close is null or zero
        data = data.dropna(subset=["Close"])
        data = data[data["Close"] > 0]

        if len(data) < min_rows:
            return None

        return data
    except Exception:
        return None


def calculate_period_return(data, days):
    """
    Calculate return over last N trading days.
    Caps to available data if not enough rows.
    """
    if data is None or len(data) < 2:
        return None
    actual_days = min(days, len(data) - 1)
    try:
        start_price = float(data['Close'].iloc[-actual_days])
        end_price   = float(data['Close'].iloc[-1])
        return round(((end_price - start_price) / start_price) * 100, 2)
    except Exception:
        return None


def get_signal_summary(data):
    try:
        analyzed    = analyze_stock(data.copy())
        ema_data    = calculate_ema_signals(data.copy())
        bb_data     = analyze_bollinger(data.copy())
        macd_data   = analyze_macd(data.copy())

        latest_ma   = analyzed.iloc[-1]
        latest_ema  = ema_data.iloc[-1]
        latest_bb   = bb_data.iloc[-1]
        latest_macd = macd_data.iloc[-1]

        combined = build_combined_summary(
            ma_signal   = latest_ma['Signal'],
            ema_signal  = latest_ema['EMA_Signal'],
            bb_signal   = latest_bb['BB_Signal'],
            macd_signal = latest_macd['MACD_Crossover'],
        )

        return {
            "combined":  combined,
            "analyzed":  analyzed,
            "ema_data":  ema_data,
            "bb_data":   bb_data,
            "macd_data": macd_data,
        }
    except Exception:
        return None


def calculate_composite_score_for_stock(stock_name, symbol, data, signal_info, regime):
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
        s_ma20   = round(float(latest_ma['MA20']), 2)    if not pd.isna(latest_ma['MA20'])          else None
        s_rsi    = round(float(latest_ma['RSI']), 2)     if not pd.isna(latest_ma['RSI'])           else None
        s_ema9   = round(float(latest_ema['EMA9']), 2)   if not pd.isna(latest_ema['EMA9'])         else None
        s_ema21  = round(float(latest_ema['EMA21']), 2)  if not pd.isna(latest_ema['EMA21'])        else None
        s_macd   = float(latest_macd['MACD'])            if not pd.isna(latest_macd['MACD'])        else None
        s_msig   = float(latest_macd['MACD_Signal'])     if not pd.isna(latest_macd['MACD_Signal']) else None
        s_mhist  = float(latest_macd['MACD_Hist'])       if not pd.isna(latest_macd['MACD_Hist'])   else None
        s_bbpct  = float(latest_bb['BB_Pct'])            if not pd.isna(latest_bb['BB_Pct'])        else None
        s_bbsig  = latest_bb['BB_Signal']

        votes = {
            "buy":  combined["Strategies Buy"],
            "sell": combined["Strategies Sell"],
            "hold": combined["Strategies Hold"],
        }

        fund_score = 50
        if FUNDAMENTALS_AVAILABLE:
            try:
                fund_score = get_fundamental_score_only(symbol)
            except Exception:
                fund_score = 50

        vol_score = 50
        if VOLUME_AVAILABLE:
            try:
                vol_score = get_volume_score_only(data)
            except Exception:
                vol_score = 50

        ms_score = 50
        if MARKET_STRUCTURE_AVAILABLE:
            try:
                ms_score = get_market_structure_score_only(data)
            except Exception:
                ms_score = 50

        candle_score = 50
        try:
            from strategies.candlestick_engine import get_candlestick_score_only
            candle_score = get_candlestick_score_only(data, regime=regime)
        except Exception:
            candle_score = 50

        return build_composite_score(
            stock_name=stock_name,
            latest_close=s_close, ma20=s_ma20, rsi=s_rsi,
            ema9=s_ema9, ema21=s_ema21,
            macd=s_macd, macd_signal=s_msig, macd_hist=s_mhist,
            bb_pct=s_bbpct, bb_signal=s_bbsig,
            combined_votes=votes,
            combined_weighted_score=combined["Score"],
            regime=regime, rs_score=None,
            fundamental_score=fund_score,
            sentiment_score=None,
            volume_score=vol_score,
            candlestick_score=candle_score,
            market_structure_score=ms_score,
        )
    except Exception:
        return None


def scan_all_stocks(watchlist_dict, period_days=30, regime="UNKNOWN ❓"):
    """
    Master scan function.

    KEY FIX for vs NIFTY / RS Rating N/A:
      NIFTY is always fetched with period="1y" regardless of what
      the user picked. This guarantees we get 250 trading days of
      data. We then slice to period_days for the return calculation.
      Previously NIFTY was fetched with the same short period as
      the scan (e.g. "5d"), which gave fewer than 30 rows and
      triggered the None return — making ALL stocks show N/A.
    """

    # Always fetch NIFTY with 1y — then slice to period_days
    nifty_data   = fetch_stock_for_scan(NIFTY_SYMBOL, period="1y", min_rows=5)
    nifty_return = None
    if nifty_data is not None:
        nifty_return = calculate_period_return(nifty_data, period_days)

    rows = []

    for name, symbol in watchlist_dict.items():
        try:
            # 60d data for indicators
            data = fetch_stock_for_scan(symbol, "60d", min_rows=5)
            if data is None:
                continue

            # 1y data for return calculation (sliced to period_days)
            long_data = fetch_stock_for_scan(symbol, "1y", min_rows=5)
            if long_data is None:
                long_data = data

            current_price = round(float(data['Close'].iloc[-1]), 2)
            period_return = calculate_period_return(long_data, period_days)

            # RS vs NIFTY
            rs_vs_nifty = None
            if period_return is not None and nifty_return is not None:
                rs_vs_nifty = round(period_return - nifty_return, 2)

            if   rs_vs_nifty is None:     rs_rating = "N/A"
            elif rs_vs_nifty >= 5:        rs_rating = "STRONG 🟢"
            elif rs_vs_nifty >= 1:        rs_rating = "ABOVE ↑"
            elif rs_vs_nifty >= -1:       rs_rating = "IN LINE ↔️"
            elif rs_vs_nifty >= -5:       rs_rating = "BELOW ↓"
            else:                          rs_rating = "WEAK 🔴"

            signal_info     = get_signal_summary(data)
            combined_signal = "N/A"
            buy_votes       = 0
            if signal_info:
                combined_signal = signal_info["combined"]["Final Signal"]
                buy_votes       = signal_info["combined"]["Strategies Buy"]

            composite_score = None
            score_action    = "N/A"
            if signal_info:
                score_result = calculate_composite_score_for_stock(
                    name, symbol, data, signal_info, regime
                )
                if score_result:
                    composite_score = score_result["Composite Score"]
                    score_action    = score_result["Action"]

            # Dividend yield — fetched separately (lightweight)
            div_yield_pct = "N/A"
            try:
                from strategies.fundamental_engine import fetch_fundamentals as _ff
                _fd = _ff(symbol)
                dv  = _fd.get("dividend_yield")
                if dv is not None:
                    div_yield_pct = f"{round(float(dv), 2)}%"
            except Exception:
                pass
            
            # Market Structure (Milestone 29)
            ms_trend   = "N/A"
            ms_score_v = 50
            ms_breakout= "—"
            ms_squeeze = "—"
            ms_hh = ms_hl = ms_lh = ms_ll = 0
            ms_support = ms_resistance = "N/A"

            if MARKET_STRUCTURE_AVAILABLE:
                try:
                    ms = get_market_structure_analysis(name, data)
                    ms_trend    = ms.get("trend_state", "N/A")
                    ms_score_v  = ms.get("market_structure_score", 50)
                    ms_breakout = "YES 🚀" if ms["breakout"].get("breakout") else "—"
                    ms_squeeze  = ms["squeeze"].get("squeeze_strength", "NONE")
                    ms_hh       = ms.get("hh_count", 0)
                    ms_hl       = ms.get("hl_count", 0)
                    ms_lh       = ms.get("lh_count", 0)
                    ms_ll       = ms.get("ll_count", 0)
                    sup = ms.get("nearest_support")
                    res = ms.get("nearest_resistance")
                    ms_support    = f"₹{sup['price']:.0f} ({sup['touches']}x)" if sup else "N/A"
                    ms_resistance = f"₹{res['price']:.0f} ({res['touches']}x)" if res else "N/A"
                except Exception:
                    pass

            rows.append({
                "Stock":           name,
                "Symbol":          symbol,
                "Price":           f"₹{current_price}",
                f"{period_days}D Return": f"{period_return}%" if period_return is not None else "N/A",
                "vs NIFTY":        f"{rs_vs_nifty}%" if rs_vs_nifty is not None else "N/A",
                "RS Rating":       rs_rating,
                "Combined Signal": combined_signal,
                "Buy Votes":       buy_votes,
                "Score":           composite_score if composite_score is not None else 0,
                "Action":          score_action,
                "Dividend Yield":  div_yield_pct,
                "Trend State":     ms_trend,
                "Struct Score":    ms_score_v,
                "Support":         ms_support,
                "Resistance":      ms_resistance,
                "Breakout":        ms_breakout,
                "Squeeze":         ms_squeeze,
                "HH":              ms_hh,
                "HL":              ms_hl,
                "LH":              ms_lh,
                "LL":              ms_ll,
                "_return":         period_return if period_return is not None else -999,
                "_score":          composite_score if composite_score is not None else 0,
                "_rs":             rs_vs_nifty if rs_vs_nifty is not None else -999,
                "_price":          current_price,
            })

        except Exception:
            continue

    if not rows:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    full_df    = pd.DataFrame(rows)
    hidden     = ['_return', '_score', '_rs', '_price', 'Symbol']

    best_return_df = (
        full_df[full_df['_return'] != -999]
        .sort_values('_return', ascending=False).head(5)
        .drop(columns=hidden, errors='ignore').reset_index(drop=True)
    )
    best_return_df.insert(0, "Rank", ["🥇","🥈","🥉","4️⃣","5️⃣"][:len(best_return_df)])

    worst_return_df = (
        full_df[full_df['_return'] != -999]
        .sort_values('_return', ascending=True).head(5)
        .drop(columns=hidden, errors='ignore').reset_index(drop=True)
    )
    worst_return_df.insert(0, "Rank", ["⚠️1","⚠️2","⚠️3","⚠️4","⚠️5"][:len(worst_return_df)])

    best_score_df = (
        full_df[full_df['_score'] > 0]
        .sort_values('_score', ascending=False).head(5)
        .drop(columns=hidden, errors='ignore').reset_index(drop=True)
    )
    best_score_df.insert(0, "Rank", ["🥇","🥈","🥉","4️⃣","5️⃣"][:len(best_score_df)])

    # Full display keeps Symbol for quick-buy panel in app.py
    full_display_df = (
        full_df
        .sort_values('_score', ascending=False)
        .drop(columns=['_return','_score','_rs','_price'], errors='ignore')
        .reset_index(drop=True)
    )

    return full_display_df, best_return_df, worst_return_df, best_score_df
