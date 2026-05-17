# ================================================
# FILE: portfolio/performance.py
# PURPOSE: Calculate portfolio performance metrics
#          from paper trading history
# ================================================

import pandas as pd
import os

# ── File locations ────────────────────────────────
TRADES_FILE    = "logs/paper_trades.csv"
PORTFOLIO_FILE = "logs/paper_portfolio.csv"
STARTING_CAPITAL = 100000  # ₹1,00,000

def load_trades():
    """Load all completed trades from CSV."""
    if os.path.exists(TRADES_FILE):
        return pd.read_csv(TRADES_FILE)
    return pd.DataFrame()


def get_completed_trades():
    """
    Match BUY and SELL trades together.
    Only completed round-trips count for P&L.
    A round-trip = one BUY + one SELL of same stock.
    """
    trades = load_trades()

    if trades.empty:
        return pd.DataFrame()

    # Separate buys and sells
    buys  = trades[trades['Action'] == 'BUY'].copy()
    sells = trades[trades['Action'] == 'SELL'].copy()

    if sells.empty:
        return pd.DataFrame()

    completed = []

    for _, sell in sells.iterrows():
        stock = sell['Stock']

        # Find matching buy for this stock
        matching_buys = buys[buys['Stock'] == stock]

        if matching_buys.empty:
            continue

        # Get the most recent buy before this sell
        buy = matching_buys.iloc[-1]

        # Calculate P&L for this trade
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
        current_capital = float(trades['Capital_After'].iloc[-1])

    # Total P&L
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

    # Count wins and losses
    wins   = completed[completed['P&L'] >= 0]
    losses = completed[completed['P&L'] < 0]

    total  = len(completed)
    win_rate = round((len(wins) / total) * 100, 2)

    # Best and worst trades
    best_idx   = completed['P&L'].idxmax()
    worst_idx  = completed['P&L'].idxmin()
    best_trade = completed.loc[best_idx]
    worst_trade= completed.loc[worst_idx]

    # Average P&L per trade
    avg_pnl = round(completed['P&L'].mean(), 2)

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
