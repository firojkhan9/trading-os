# ================================================
# FILE: portfolio/performance.py
# PURPOSE: Calculate portfolio performance metrics
#          PRIMARY: Supabase database (permanent)
#          FALLBACK: CSV file (local only)
# ================================================

import pandas as pd
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.supabase_client import get_client

# ── Settings ──────────────────────────────────────
try:
    from config.strategy_settings import STARTING_CAPITAL
except ImportError:
    STARTING_CAPITAL = 100000

# ── CSV fallback ──────────────────────────────────
try:
    from config.settings import TRADES_FILE, PORTFOLIO_FILE
except Exception:
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TRADES_FILE    = os.path.join(_base, "logs", "paper_trades.csv")
    PORTFOLIO_FILE = os.path.join(_base, "logs", "paper_portfolio.csv")


def load_trades():
    """
    Load all trades from Supabase or CSV fallback.
    Returns dataframe with standardised column names.
    """
    client = get_client()

    if client:
        try:
            response = (
                client.table("paper_trades")
                .select("*")
                .order("timestamp", desc=False)
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "timestamp":     "Timestamp",
                    "stock":         "Stock",
                    "action":        "Action",
                    "price":         "Price",
                    "quantity":      "Quantity",
                    "value":         "Value",
                    "capital_after": "Capital_After",
                })
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"⚠️ Supabase trades load failed: {e}")

    if os.path.exists(TRADES_FILE):
        try:
            return pd.read_csv(TRADES_FILE)
        except Exception:
            pass

    return pd.DataFrame()


def get_completed_trades():
    """
    Match BUY and SELL trades into completed round trips.
    A round trip = one BUY + one SELL of same stock.
    """
    trades = load_trades()

    if trades.empty:
        return pd.DataFrame()

    buys  = trades[trades['Action'] == 'BUY'].copy()
    sells = trades[trades['Action'] == 'SELL'].copy()

    if sells.empty:
        return pd.DataFrame()

    completed = []

    for _, sell in sells.iterrows():
        stock = sell['Stock']
        matching_buys = buys[buys['Stock'] == stock]

        if matching_buys.empty:
            continue

        buy = matching_buys.iloc[-1]

        buy_value  = float(buy['Value'])
        sell_value = float(sell['Value'])
        pnl        = round(sell_value - buy_value, 2)
        pnl_pct    = round((pnl / buy_value) * 100, 2)

        completed.append({
            "Stock":      stock,
            "Buy Date":   buy['Timestamp'],
            "Sell Date":  sell['Timestamp'],
            "Buy Price":  float(buy['Price']),
            "Sell Price": float(sell['Price']),
            "Quantity":   int(buy['Quantity']),
            "Buy Value":  round(buy_value, 2),
            "Sell Value": round(sell_value, 2),
            "P&L":        pnl,
            "P&L %":      pnl_pct,
            "Result":     "WIN 🟢" if pnl >= 0 else "LOSS 🔴"
        })

    return pd.DataFrame(completed)


def get_performance_summary():
    """
    Calculate overall performance metrics.
    Returns a dictionary of key stats.
    """
    trades    = load_trades()
    completed = get_completed_trades()

    # Current capital
    if trades.empty:
        current_capital = STARTING_CAPITAL
    else:
        trades_sorted   = trades.sort_values('Timestamp', ascending=True)
        current_capital = float(trades_sorted['Capital_After'].iloc[-1])

    total_pnl     = round(current_capital - STARTING_CAPITAL, 2)
    total_pnl_pct = round((total_pnl / STARTING_CAPITAL) * 100, 2)

    if completed.empty:
        return {
            "Total Trades":    0,
            "Winning Trades":  0,
            "Losing Trades":   0,
            "Win Rate":        "0%",
            "Total P&L":       f"₹{total_pnl}",
            "Total P&L %":     f"{total_pnl_pct}%",
            "Best Trade":      "N/A",
            "Worst Trade":     "N/A",
            "Avg P&L":         "N/A",
            "Current Capital": f"₹{current_capital:,}",
        }

    wins   = completed[completed['P&L'] >= 0]
    losses = completed[completed['P&L'] < 0]
    total  = len(completed)

    win_rate    = round((len(wins) / total) * 100, 2)
    best_trade  = completed.loc[completed['P&L'].idxmax()]
    worst_trade = completed.loc[completed['P&L'].idxmin()]
    avg_pnl     = round(completed['P&L'].mean(), 2)

    return {
        "Total Trades":    total,
        "Winning Trades":  len(wins),
        "Losing Trades":   len(losses),
        "Win Rate":        f"{win_rate}%",
        "Total P&L":       f"₹{total_pnl}",
        "Total P&L %":     f"{total_pnl_pct}%",
        "Best Trade":      f"{best_trade['Stock']} +₹{best_trade['P&L']}",
        "Worst Trade":     f"{worst_trade['Stock']} ₹{worst_trade['P&L']}",
        "Avg P&L":         f"₹{avg_pnl}",
        "Current Capital": f"₹{current_capital:,}",
    }
