# ================================================
# FILE: strategies/paper_trader.py
# PURPOSE: Simulate trades based on signals
#          Track P&L without real money
#
# UPDATED:
#   get_portfolio_summary now returns:
#   - Stop Loss price and % away
#   - Target price and % away
#   - Days held
#   - Suggestion: ADD / HOLD / SELL / STOP LOSS
#   - Portfolio totals row (total invested, total value, total P&L)
# ================================================

import pandas as pd
import os
from datetime import datetime, date

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    TRADES_FILE,
    PORTFOLIO_FILE,
    STARTING_CAPITAL,
    MAX_POSITION_PCT,
    STOP_LOSS_PCT,
    TARGET_PROFIT_PCT,
)


def load_trades():
    """Load all past paper trades from CSV."""
    if os.path.exists(TRADES_FILE):
        return pd.read_csv(TRADES_FILE)
    return pd.DataFrame(columns=[
        "Timestamp", "Stock", "Action",
        "Price", "Quantity", "Value",
        "Capital_After"
    ])


def load_portfolio():
    """
    Load current open positions.
    These are stocks we have 'bought' but not yet 'sold'.
    """
    if os.path.exists(PORTFOLIO_FILE):
        return pd.read_csv(PORTFOLIO_FILE)
    return pd.DataFrame(columns=[
        "Stock", "Buy_Price", "Quantity",
        "Buy_Value", "Buy_Date"
    ])


def get_current_capital():
    """
    Calculate how much virtual cash we have left.
    Starts at STARTING_CAPITAL minus all open positions.
    """
    trades = load_trades()
    if trades.empty:
        return STARTING_CAPITAL
    return float(trades['Capital_After'].iloc[-1])


def execute_paper_buy(stock_name, price):
    """
    Simulate buying a stock.
    Automatically calculates quantity based on capital.
    """
    capital   = get_current_capital()
    portfolio = load_portfolio()

    # Check if we already own this stock
    if not portfolio.empty and stock_name in portfolio['Stock'].values:
        return {
            "status":  "SKIPPED",
            "reason":  f"Already holding {stock_name}",
            "capital": capital
        }

    # Max 10% of total capital per position
    max_spend = STARTING_CAPITAL * MAX_POSITION_PCT
    spend     = min(max_spend, capital)

    if spend < price:
        return {
            "status":  "SKIPPED",
            "reason":  "Not enough capital",
            "capital": capital
        }

    quantity = int(spend // price)

    if quantity == 0:
        return {
            "status":  "SKIPPED",
            "reason":  "Price too high for position size",
            "capital": capital
        }

    buy_value     = round(quantity * price, 2)
    capital_after = round(capital - buy_value, 2)

    # Record the trade
    trade = {
        "Timestamp":     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Stock":         stock_name,
        "Action":        "BUY",
        "Price":         round(price, 2),
        "Quantity":      quantity,
        "Value":         buy_value,
        "Capital_After": capital_after
    }

    trade_df = pd.DataFrame([trade])
    if os.path.exists(TRADES_FILE):
        trade_df.to_csv(TRADES_FILE, mode='a', header=False, index=False)
    else:
        trade_df.to_csv(TRADES_FILE, mode='w', header=True, index=False)

    # Save to portfolio file with today's date
    position = {
        "Stock":     stock_name,
        "Buy_Price": round(price, 2),
        "Quantity":  quantity,
        "Buy_Value": buy_value,
        "Buy_Date":  datetime.now().strftime('%Y-%m-%d')
    }
    position_df = pd.DataFrame([position])
    if os.path.exists(PORTFOLIO_FILE):
        position_df.to_csv(PORTFOLIO_FILE, mode='a', header=False, index=False)
    else:
        position_df.to_csv(PORTFOLIO_FILE, mode='w', header=True, index=False)

    return {
        "status":   "EXECUTED",
        "action":   "BUY",
        "stock":    stock_name,
        "price":    round(price, 2),
        "quantity": quantity,
        "value":    buy_value,
        "capital":  capital_after
    }


def execute_paper_sell(stock_name, price):
    """
    Simulate selling a stock we own.
    Calculates profit or loss automatically.
    """
    portfolio = load_portfolio()
    capital   = get_current_capital()

    if portfolio.empty or stock_name not in portfolio['Stock'].values:
        return {
            "status": "SKIPPED",
            "reason": f"No position in {stock_name}"
        }

    position  = portfolio[portfolio['Stock'] == stock_name].iloc[0]
    buy_price = float(position['Buy_Price'])
    quantity  = int(position['Quantity'])
    buy_value = float(position['Buy_Value'])

    sell_value    = round(quantity * price, 2)
    pnl           = round(sell_value - buy_value, 2)
    pnl_pct       = round((pnl / buy_value) * 100, 2)
    capital_after = round(capital + sell_value, 2)

    trade = {
        "Timestamp":     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Stock":         stock_name,
        "Action":        "SELL",
        "Price":         round(price, 2),
        "Quantity":      quantity,
        "Value":         sell_value,
        "Capital_After": capital_after
    }

    trade_df = pd.DataFrame([trade])
    if os.path.exists(TRADES_FILE):
        trade_df.to_csv(TRADES_FILE, mode='a', header=False, index=False)
    else:
        trade_df.to_csv(TRADES_FILE, mode='w', header=True, index=False)

    # Remove from portfolio
    updated = portfolio[portfolio['Stock'] != stock_name]
    updated.to_csv(PORTFOLIO_FILE, index=False)

    return {
        "status":   "EXECUTED",
        "action":   "SELL",
        "stock":    stock_name,
        "price":    round(price, 2),
        "quantity": quantity,
        "value":    sell_value,
        "pnl":      pnl,
        "pnl_pct":  pnl_pct,
        "capital":  capital_after
    }


def _get_suggestion(pnl_pct, stop_loss_pct, target_pct, combined_signal=None):
    """
    Decide what action to suggest for a held position.

    Logic:
    - If loss exceeds stop loss % → SELL (Stop Loss)
    - If gain exceeds target % → SELL (Take Profit)
    - If combined signal says STRONG BUY → ADD (scale in)
    - If combined signal says SELL → SELL (Signal Exit)
    - Otherwise → HOLD
    """
    stop_pct   = stop_loss_pct * 100     # e.g. 0.06 → 6
    target_pct_val = target_pct * 100    # e.g. 0.15 → 15

    if pnl_pct <= -stop_pct:
        return "🔴 SELL (Stop Loss)"
    elif pnl_pct >= target_pct_val:
        return "✅ SELL (Take Profit)"
    elif combined_signal and "STRONG BUY" in str(combined_signal):
        return "🟢 ADD (Strong Signal)"
    elif combined_signal and "SELL" in str(combined_signal):
        return "🔴 SELL (Signal Exit)"
    elif pnl_pct >= (target_pct_val * 0.6):
        # At 60% of target — consider partial booking
        return "🟡 HOLD (Near Target)"
    elif pnl_pct < 0 and pnl_pct > -stop_pct:
        return "🟡 HOLD (Monitor Loss)"
    else:
        return "🟢 HOLD"


def get_portfolio_summary(current_prices, combined_signals=None):
    """
    Show current portfolio with live P&L and suggestions.

    current_prices   = dict of {stock_name: current_price}
    combined_signals = dict of {stock_name: combined_signal_string} (optional)
                       If provided, suggestions use signal context.

    Returns a dataframe with columns:
      Stock | Buy Price | Current | Qty | Buy Value | Curr Value |
      P&L ₹ | P&L % | Stop Loss | Target | Days Held | Suggestion

    Last row = TOTAL summary row.
    """
    portfolio = load_portfolio()

    if portfolio.empty:
        return pd.DataFrame()

    rows            = []
    total_buy_value = 0
    total_curr_value= 0

    for _, pos in portfolio.iterrows():
        stock     = pos['Stock']
        buy_price = float(pos['Buy_Price'])
        quantity  = int(pos['Quantity'])
        buy_value = float(pos['Buy_Value'])

        # Current price — fall back to buy price if not available
        curr_price = current_prices.get(stock, buy_price)
        curr_value = round(quantity * curr_price, 2)
        pnl        = round(curr_value - buy_value, 2)
        pnl_pct    = round((pnl / buy_value) * 100, 2)

        # Stop loss and target price levels
        stop_price   = round(buy_price * (1 - STOP_LOSS_PCT), 2)
        target_price = round(buy_price * (1 + TARGET_PROFIT_PCT), 2)
        stop_away    = round(((curr_price - stop_price) / curr_price) * 100, 1)
        target_away  = round(((target_price - curr_price) / curr_price) * 100, 1)

        # Days held
        days_held = 0
        try:
            buy_date  = pd.to_datetime(pos['Buy_Date']).date()
            days_held = (date.today() - buy_date).days
        except Exception:
            days_held = 0

        # Suggestion
        signal     = combined_signals.get(stock) if combined_signals else None
        suggestion = _get_suggestion(pnl_pct, STOP_LOSS_PCT, TARGET_PROFIT_PCT, signal)

        total_buy_value  += buy_value
        total_curr_value += curr_value

        rows.append({
            "Stock":        stock,
            "Buy ₹":        round(buy_price, 2),
            "Now ₹":        round(curr_price, 2),
            "Qty":          quantity,
            "Invested ₹":   round(buy_value, 2),
            "Value ₹":      round(curr_value, 2),
            "P&L ₹":        pnl,
            "P&L %":        pnl_pct,
            "Stop ₹":       stop_price,
            "Stop Away":    f"{stop_away}%",
            "Target ₹":     target_price,
            "Target Away":  f"{target_away}%",
            "Days Held":    days_held,
            "Suggestion":   suggestion,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # ── Add TOTAL summary row ─────────────────────
    total_pnl     = round(total_curr_value - total_buy_value, 2)
    total_pnl_pct = round((total_pnl / total_buy_value) * 100, 2) if total_buy_value > 0 else 0

    total_row = {
        "Stock":       "📊 TOTAL",
        "Buy ₹":       "",
        "Now ₹":       "",
        "Qty":         df["Qty"].sum(),
        "Invested ₹":  round(total_buy_value, 2),
        "Value ₹":     round(total_curr_value, 2),
        "P&L ₹":       total_pnl,
        "P&L %":       total_pnl_pct,
        "Stop ₹":      "",
        "Stop Away":   "",
        "Target ₹":    "",
        "Target Away": "",
        "Days Held":   "",
        "Suggestion":  "✅ Profit" if total_pnl >= 0 else "⚠️ Overall Loss",
    }

    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

    return df
