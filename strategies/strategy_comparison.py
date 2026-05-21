# ================================================
# FILE: strategies/strategy_comparison.py
# PURPOSE: Compare all strategies side by side
#          Run all 4 backtests and rank them
#          by performance metrics
# ================================================

import pandas as pd
import yfinance as yf

from strategies.indicators import calculate_ma20, calculate_rsi
from strategies.ema_strategy import calculate_ema_signals, run_ema_backtest
from strategies.bollinger_strategy import analyze_bollinger, run_bollinger_backtest
from strategies.macd_strategy import analyze_macd, run_macd_backtest
from strategies.backtest import run_backtest


def fetch_data(symbol, period="1y"):
    """Fetch stock data for given symbol and period."""
    data = yf.download(
        tickers=symbol,
        period=period,
        interval="1d",
        progress=False
    )
    data.columns = [col[0] for col in data.columns]
    return data


def run_all_backtests(symbol, stock_name, period="1y"):
    """
    Run all 4 strategies on the same stock and period.
    Returns a comparison dataframe ranked by Total Return.

    This is the core of Milestone 15 — apples to apples
    comparison of all strategies on identical data.
    """

    raw_data = fetch_data(symbol, period)

    if raw_data.empty:
        return pd.DataFrame(), {}

    results    = {}
    equity_all = {}

    # ── Strategy 1: MA + RSI ──────────────────────
    try:
        result = run_backtest(
            symbol     = symbol,
            stock_name = stock_name,
            period     = period
        )
        results["MA + RSI"]    = result[0]
        equity_all["MA + RSI"] = result[1]
    except Exception as e:
        results["MA + RSI"] = {"error": str(e)}

    # ── Strategy 2: EMA Crossover ─────────────────
    try:
        ema_data = calculate_ema_signals(raw_data.copy())
        ema_data = ema_data.dropna()
        summary, equity, _ = run_ema_backtest(ema_data)
        results["EMA Crossover"]    = summary
        equity_all["EMA Crossover"] = equity
    except Exception as e:
        results["EMA Crossover"] = {"error": str(e)}

    # ── Strategy 3: Bollinger Bands ───────────────
    try:
        bb_data = analyze_bollinger(raw_data.copy())
        bb_data = bb_data.dropna()
        summary, equity, _ = run_bollinger_backtest(bb_data)
        results["Bollinger Bands"]    = summary
        equity_all["Bollinger Bands"] = equity
    except Exception as e:
        results["Bollinger Bands"] = {"error": str(e)}

    # ── Strategy 4: MACD ──────────────────────────
    try:
        macd_data = analyze_macd(raw_data.copy())
        macd_data = macd_data.dropna()
        summary, equity, _ = run_macd_backtest(macd_data)
        results["MACD"]    = summary
        equity_all["MACD"] = equity
    except Exception as e:
        results["MACD"] = {"error": str(e)}

    # ── Build comparison table ────────────────────
    rows = []
    for strategy, summary in results.items():
        if "error" in summary:
            continue

        # Extract numeric return for ranking
        ret_str  = summary.get("Total Return", "0%").replace("%", "").replace("₹", "")
        pnl_str  = summary.get("Total P&L", "0").replace("₹", "").replace(",", "")
        dd_str   = summary.get("Max Drawdown", "0%").replace("%", "")
        wr_str   = summary.get("Win Rate", "0%").replace("%", "")

        try:
            ret_val = float(ret_str)
        except:
            ret_val = 0.0

        try:
            pnl_val = float(pnl_str)
        except:
            pnl_val = 0.0

        try:
            dd_val = float(dd_str)
        except:
            dd_val = 0.0

        try:
            wr_val = float(wr_str)
        except:
            wr_val = 0.0

        rows.append({
            "Strategy":      strategy,
            "Total Trades":  summary.get("Total Trades", 0),
            "Win Rate":      summary.get("Win Rate", "N/A"),
            "Total P&L":     summary.get("Total P&L", "N/A"),
            "Total Return":  summary.get("Total Return", "N/A"),
            "Max Drawdown":  summary.get("Max Drawdown", "N/A"),
            "Final Capital": summary.get("Final Capital", "N/A"),
            "Best Trade":    summary.get("Best Trade", "N/A"),
            "Worst Trade":   summary.get("Worst Trade", "N/A"),
            # Hidden numeric values for sorting/ranking
            "_return":       ret_val,
            "_pnl":          pnl_val,
            "_drawdown":     dd_val,
            "_winrate":      wr_val,
        })

    if not rows:
        return pd.DataFrame(), equity_all

    # Sort by Total Return descending
    comparison_df = pd.DataFrame(rows)
    comparison_df = comparison_df.sort_values("_return", ascending=False)
    comparison_df = comparison_df.reset_index(drop=True)

    # Add rank column
    comparison_df.insert(0, "Rank", ["🥇", "🥈", "🥉", "4️⃣"][:len(comparison_df)])

    # Drop hidden numeric columns before display
    display_df = comparison_df.drop(
        columns=["_return", "_pnl", "_drawdown", "_winrate"]
    )

    return display_df, equity_all, comparison_df


def get_best_strategy(comparison_df):
    """
    Return the name of the best performing strategy
    based on Total Return.
    """
    if comparison_df.empty:
        return "N/A"
    return comparison_df.iloc[0]["Strategy"]


def get_strategy_scores(comparison_df):
    """
    Score each strategy across multiple dimensions:
    - Return score    (higher = better)
    - Win Rate score  (higher = better)
    - Risk score      (lower drawdown = better)

    Returns a scored summary for the dashboard.
    Useful for the Combined Signal Engine in Milestone 16.
    """
    if comparison_df.empty:
        return {}

    scores = {}

    # Normalize each metric to 0-100 scale
    max_ret = comparison_df["_return"].max()
    max_wr  = comparison_df["_winrate"].max()
    min_dd  = comparison_df["_drawdown"].min()   # most negative = worst

    for _, row in comparison_df.iterrows():
        strategy = row["Strategy"]

        # Return score: best gets 100
        ret_score = (row["_return"] / max_ret * 100) if max_ret != 0 else 0

        # Win rate score: best gets 100
        wr_score = (row["_winrate"] / max_wr * 100) if max_wr != 0 else 0

        # Risk score: least drawdown gets 100
        # Drawdown is negative — closer to 0 is better
        if min_dd != 0:
            dd_score = (row["_drawdown"] / min_dd * 100)
        else:
            dd_score = 100

        # Composite score: weighted average
        # Return matters most (50%), then win rate (30%), then risk (20%)
        composite = round(
            (ret_score * 0.50) +
            (wr_score  * 0.30) +
            (dd_score  * 0.20),
            1
        )

        scores[strategy] = {
            "Return Score":    round(ret_score, 1),
            "Win Rate Score":  round(wr_score, 1),
            "Risk Score":      round(dd_score, 1),
            "Composite Score": composite,
        }

    return scores
