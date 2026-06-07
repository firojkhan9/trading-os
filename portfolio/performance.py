# ================================================
# FILE: portfolio/performance.py
# PURPOSE: Calculate portfolio performance metrics
#          from the BUCKET TRADES system (M24+)
#
# UPDATED: Reads from load_bucket_trades() which is
#          the single source of truth for all trades.
#          The old paper_trades.csv is no longer used.
# ================================================

import pandas as pd
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Starting capital — total across all 3 buckets
try:
    from portfolio.capital_engine import (
        load_bucket_trades,
        get_portfolio_totals,
        TOTAL_CAPITAL,
    )
    STARTING_CAPITAL = TOTAL_CAPITAL   # ₹6,00,000
except ImportError:
    STARTING_CAPITAL = 600000
    def load_bucket_trades():
        return pd.DataFrame()
    def get_portfolio_totals():
        return {"total_pnl": 0, "total_return_pct": 0, "total_trades": 0, "winning_trades": 0}


def load_trades():
    """
    Load all trades — now reads from bucket_trades (the current system).
    Kept for backward compatibility with Logs tab.
    """
    return load_bucket_trades()


def get_completed_trades():
    """
    Find completed round-trip trades (BUY + matching SELL).
    Reads from bucket_trades — works across all three buckets.
    A round-trip = one BUY + one SELL for the same stock in the same bucket.
    """
    trades = load_bucket_trades()

    if trades.empty:
        return pd.DataFrame()

    completed = []

    # Work bucket-by-bucket to avoid cross-bucket matching
    for bucket in trades["Bucket"].unique() if "Bucket" in trades.columns else [""]:
        if "Bucket" in trades.columns:
            bucket_df = trades[trades["Bucket"] == bucket]
        else:
            bucket_df = trades

        buys  = bucket_df[bucket_df["Action"] == "BUY"].copy()
        sells = bucket_df[bucket_df["Action"] == "SELL"].copy()

        if sells.empty or buys.empty:
            continue

        # Match each SELL to the most recent preceding BUY for that stock
        for _, sell in sells.iterrows():
            stock = sell["Stock"]
            matching_buys = buys[buys["Stock"] == stock]
            if matching_buys.empty:
                continue

            buy = matching_buys.iloc[-1]

            try:
                buy_value  = float(buy["Value"])
                sell_value = float(sell["Value"])
                buy_price  = float(buy["Price"])
                sell_price = float(sell["Price"])
                quantity   = int(buy["Quantity"])
                pnl        = round(sell_value - buy_value, 2)
                pnl_pct    = round((pnl / buy_value) * 100, 2) if buy_value else 0

                # Include dividend yield for Long-Term (informational)
                div_note = ""
                if str(bucket) == "Long-Term":
                    div_note = " (excl. dividends)"

                completed.append({
                    "Bucket":     bucket,
                    "Stock":      stock,
                    "Buy Date":   str(buy["Timestamp"])[:10],
                    "Sell Date":  str(sell["Timestamp"])[:10],
                    "Buy Price":  buy_price,
                    "Sell Price": sell_price,
                    "Quantity":   quantity,
                    "Buy Value":  buy_value,
                    "Sell Value": sell_value,
                    "P&L":        pnl,
                    "P&L %":      str(pnl_pct) + "%" + div_note,
                    "Result":     "WIN 🟢" if pnl >= 0 else "LOSS 🔴",
                })
            except Exception:
                continue

    return pd.DataFrame(completed)


def get_performance_summary():
    """
    Calculate overall performance metrics across all buckets.
    Returns a dictionary of key stats for the dashboard.
    """
    completed = get_completed_trades()

    # Pull real-time totals from the bucket engine (single source of truth)
    try:
        totals = get_portfolio_totals()
        total_pnl       = round(totals["total_pnl"], 2)
        total_return_pct= round(totals["total_return_pct"], 2)
        total_trades_all= totals["total_trades"]
        winning_trades  = totals["winning_trades"]
        current_value   = round(STARTING_CAPITAL + total_pnl, 2)
    except Exception:
        total_pnl        = 0
        total_return_pct = 0
        total_trades_all = 0
        winning_trades   = 0
        current_value    = STARTING_CAPITAL

    if completed.empty:
        return {
            "Total Trades":    total_trades_all,
            "Winning Trades":  winning_trades,
            "Losing Trades":   max(0, total_trades_all - winning_trades),
            "Win Rate":        f"{round(winning_trades/total_trades_all*100,1)}%" if total_trades_all > 0 else "0%",
            "Total P&L":       f"₹{total_pnl:+,.2f}",
            "Total P&L %":     f"{total_return_pct:+.2f}%",
            "Best Trade":      "N/A — no completed trades yet",
            "Worst Trade":     "N/A — no completed trades yet",
            "Avg P&L":         "N/A",
            "Current Capital": f"₹{current_value:,.2f}",
        }

    # Compute from completed trades
    pnl_series = completed["P&L"]
    wins        = completed[completed["P&L"] >= 0]
    losses      = completed[completed["P&L"] < 0]
    total       = len(completed)
    win_rate    = round((len(wins) / total) * 100, 1) if total > 0 else 0
    avg_pnl     = round(pnl_series.mean(), 2)

    best_idx    = pnl_series.idxmax()
    worst_idx   = pnl_series.idxmin()
    best_trade  = completed.loc[best_idx]
    worst_trade = completed.loc[worst_idx]

    return {
        "Total Trades":    total,
        "Winning Trades":  len(wins),
        "Losing Trades":   len(losses),
        "Win Rate":        f"{win_rate}%",
        "Total P&L":       f"₹{total_pnl:+,.2f}",
        "Total P&L %":     f"{total_return_pct:+.2f}%",
        "Best Trade":      f"{best_trade['Stock']} ({best_trade['Bucket']}) +₹{best_trade['P&L']:,.0f}",
        "Worst Trade":     f"{worst_trade['Stock']} ({worst_trade['Bucket']}) ₹{worst_trade['P&L']:,.0f}",
        "Avg P&L":         f"₹{avg_pnl:,.2f}",
        "Current Capital": f"₹{current_value:,.2f}",
    }
