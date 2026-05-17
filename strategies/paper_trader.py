# ================================================
# FILE: strategies/paper_trader.py
# PURPOSE: Simulate trades based on signals
#          Track P&L without real money
# ================================================

import pandas as pd
import os
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    TRADES_FILE,
    PORTFOLIO_FILE,
    STARTING_CAPITAL,
    MAX_POSITION_PCT
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

    # Get the capital after the last trade
    return float(trades['Capital_After'].iloc[-1])


def execute_paper_buy(stock_name, price):
    """
    Simulate buying a stock.
    Automatically calculates quantity based on capital.
    """
    capital    = get_current_capital()
    portfolio  = load_portfolio()

    # Check if we already own this stock
    if not portfolio.empty and stock_name in portfolio['Stock'].values:
        return {
            "status":  "SKIPPED",
            "reason":  f"Already holding {stock_name}",
            "capital": capital
        }

    # Calculate how much we can spend on this trade
    # Never more than 10% of total capital
    max_spend = STARTING_CAPITAL * MAX_POSITION_PCT

    # Can't spend more than we have
    spend = min(max_spend, capital)

    if spend < price:
        return {
            "status":  "SKIPPED",
            "reason":  "Not enough capital",
            "capital": capital
        }

    # Calculate quantity (how many shares we can buy)
    quantity = int(spend // price)

    if quantity == 0:
        return {
            "status":  "SKIPPED",
            "reason":  "Price too high for position size",
            "capital": capital
        }

    # Total money spent
    buy_value      = round(quantity * price, 2)
    capital_after  = round(capital - buy_value, 2)

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

    # Save to trades file
    trade_df = pd.DataFrame([trade])
    if os.path.exists(TRADES_FILE):
        trade_df.to_csv(TRADES_FILE, mode='a', header=False, index=False)
    else:
        trade_df.to_csv(TRADES_FILE, mode='w', header=True, index=False)

    # Save to portfolio file
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

    # Check if we own this stock
    if portfolio.empty or stock_name not in portfolio['Stock'].values:
        return {
            "status": "SKIPPED",
            "reason": f"No position in {stock_name}"
        }

    # Get our position details
    position  = portfolio[portfolio['Stock'] == stock_name].iloc[0]
    buy_price = float(position['Buy_Price'])
    quantity  = int(position['Quantity'])
    buy_value = float(position['Buy_Value'])

    # Calculate sale value and profit/loss
    sell_value    = round(quantity * price, 2)
    pnl           = round(sell_value - buy_value, 2)
    pnl_pct       = round((pnl / buy_value) * 100, 2)
    capital_after = round(capital + sell_value, 2)

    # Record the trade
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
    updated_portfolio = portfolio[portfolio['Stock'] != stock_name]
    updated_portfolio.to_csv(PORTFOLIO_FILE, index=False)

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


def get_portfolio_summary(current_prices):
    """
    Show current portfolio with live P&L.
    current_prices = dict of {stock_name: current_price}
    """
    portfolio = load_portfolio()

    if portfolio.empty:
        return pd.DataFrame()

    rows = []
    for _, pos in portfolio.iterrows():
        stock     = pos['Stock']
        buy_price = float(pos['Buy_Price'])
        quantity  = int(pos['Quantity'])
        buy_value = float(pos['Buy_Value'])

        # Get current price if available
        curr_price = current_prices.get(stock, buy_price)
        curr_value = round(quantity * curr_price, 2)
        pnl        = round(curr_value - buy_value, 2)
        pnl_pct    = round((pnl / buy_value) * 100, 2)

        rows.append({
            "Stock":       stock,
            "Buy Price":   f"₹{buy_price}",
            "Current":     f"₹{curr_price}",
            "Qty":         quantity,
            "Buy Value":   f"₹{buy_value}",
            "Curr Value":  f"₹{curr_value}",
            "P&L":         pnl,
            "P&L %":       pnl_pct,
        })

    return pd.DataFrame(rows)