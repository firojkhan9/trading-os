# ================================================
# FILE: strategies/paper_trader.py
# PURPOSE: Simulate trades based on signals
#          PRIMARY: Supabase database (permanent)
#          FALLBACK: CSV file (local only)
#
# WHY SUPABASE:
#   CSV files on Streamlit Cloud are wiped on every
#   redeploy. Supabase keeps your trades permanently.
#   All paper trades, portfolio positions and capital
#   are stored safely in the cloud database.
# ================================================

import pandas as pd
import os
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.supabase_client import get_client

# ── Settings ──────────────────────────────────────
try:
    from config.strategy_settings import (
        STARTING_CAPITAL,
        MAX_POSITION_PCT,
    )
except ImportError:
    STARTING_CAPITAL = 100000
    MAX_POSITION_PCT = 0.10

# ── CSV fallback paths ────────────────────────────
try:
    from config.settings import TRADES_FILE, PORTFOLIO_FILE
except Exception:
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TRADES_FILE    = os.path.join(_base, "logs", "paper_trades.csv")
    PORTFOLIO_FILE = os.path.join(_base, "logs", "paper_portfolio.csv")


# ════════════════════════════════════════════════
# LOAD FUNCTIONS
# ════════════════════════════════════════════════

def load_trades():
    """
    Load all paper trades.
    Tries Supabase first, falls back to CSV.
    """
    client = get_client()

    if client:
        try:
            response = (
                client.table("paper_trades")
                .select("*")
                .order("timestamp", desc=True)
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
                cols = ["Timestamp", "Stock", "Action", "Price", "Quantity", "Value", "Capital_After"]
                df = df[[c for c in cols if c in df.columns]]
                return df
            return pd.DataFrame(columns=["Timestamp", "Stock", "Action", "Price", "Quantity", "Value", "Capital_After"])
        except Exception as e:
            print(f"⚠️ Supabase trades load failed: {e}")

    # CSV fallback
    if os.path.exists(TRADES_FILE):
        try:
            return pd.read_csv(TRADES_FILE)
        except Exception:
            pass

    return pd.DataFrame(columns=["Timestamp", "Stock", "Action", "Price", "Quantity", "Value", "Capital_After"])


def load_portfolio():
    """
    Load current open positions.
    Tries Supabase first, falls back to CSV.
    """
    client = get_client()

    if client:
        try:
            response = (
                client.table("paper_portfolio")
                .select("*")
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "stock":     "Stock",
                    "buy_price": "Buy_Price",
                    "quantity":  "Quantity",
                    "buy_value": "Buy_Value",
                    "buy_date":  "Buy_Date",
                })
                cols = ["Stock", "Buy_Price", "Quantity", "Buy_Value", "Buy_Date"]
                df = df[[c for c in cols if c in df.columns]]
                return df
            return pd.DataFrame(columns=["Stock", "Buy_Price", "Quantity", "Buy_Value", "Buy_Date"])
        except Exception as e:
            print(f"⚠️ Supabase portfolio load failed: {e}")

    # CSV fallback
    if os.path.exists(PORTFOLIO_FILE):
        try:
            return pd.read_csv(PORTFOLIO_FILE)
        except Exception:
            pass

    return pd.DataFrame(columns=["Stock", "Buy_Price", "Quantity", "Buy_Value", "Buy_Date"])


def get_current_capital():
    """
    Get current available cash.
    Reads from last trade's capital_after field.
    """
    trades = load_trades()

    if trades.empty:
        return STARTING_CAPITAL

    # Sort by timestamp to get latest
    trades = trades.sort_values('Timestamp', ascending=True)
    return float(trades['Capital_After'].iloc[-1])


# ════════════════════════════════════════════════
# WRITE FUNCTIONS
# ════════════════════════════════════════════════

def _save_trade_to_supabase(client, trade_dict):
    """Save a trade record to Supabase."""
    client.table("paper_trades").insert({
        "timestamp":     trade_dict["Timestamp"],
        "stock":         trade_dict["Stock"],
        "action":        trade_dict["Action"],
        "price":         trade_dict["Price"],
        "quantity":      trade_dict["Quantity"],
        "value":         trade_dict["Value"],
        "capital_after": trade_dict["Capital_After"],
    }).execute()


def _save_trade_to_csv(trade_dict):
    """Save a trade record to CSV."""
    os.makedirs(os.path.dirname(TRADES_FILE), exist_ok=True)
    trade_df = pd.DataFrame([trade_dict])
    if os.path.exists(TRADES_FILE):
        trade_df.to_csv(TRADES_FILE, mode='a', header=False, index=False)
    else:
        trade_df.to_csv(TRADES_FILE, mode='w', header=True, index=False)


def _save_position_to_supabase(client, position_dict):
    """Save or update a portfolio position in Supabase."""
    # Use upsert — if stock already exists update it, else insert
    client.table("paper_portfolio").upsert({
        "stock":     position_dict["Stock"],
        "buy_price": position_dict["Buy_Price"],
        "quantity":  position_dict["Quantity"],
        "buy_value": position_dict["Buy_Value"],
        "buy_date":  position_dict["Buy_Date"],
    }, on_conflict="stock").execute()


def _delete_position_from_supabase(client, stock_name):
    """Remove a stock from portfolio in Supabase."""
    client.table("paper_portfolio").delete().eq("stock", stock_name).execute()


# ════════════════════════════════════════════════
# PAPER TRADING FUNCTIONS
# ════════════════════════════════════════════════

def execute_paper_buy(stock_name, price):
    """
    Simulate buying a stock.
    Saves to Supabase (permanent) with CSV fallback.
    """
    capital   = get_current_capital()
    portfolio = load_portfolio()

    # Check if already holding
    if not portfolio.empty and stock_name in portfolio['Stock'].values:
        return {
            "status":  "SKIPPED",
            "reason":  f"Already holding {stock_name}",
            "capital": capital
        }

    # Calculate position size
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
    timestamp     = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    trade = {
        "Timestamp":     timestamp,
        "Stock":         stock_name,
        "Action":        "BUY",
        "Price":         round(price, 2),
        "Quantity":      quantity,
        "Value":         buy_value,
        "Capital_After": capital_after,
    }

    position = {
        "Stock":     stock_name,
        "Buy_Price": round(price, 2),
        "Quantity":  quantity,
        "Buy_Value": buy_value,
        "Buy_Date":  datetime.now().strftime('%Y-%m-%d'),
    }

    # ── Try Supabase ──────────────────────────────
    client = get_client()
    if client:
        try:
            _save_trade_to_supabase(client, trade)
            _save_position_to_supabase(client, position)
            return {
                "status":   "EXECUTED",
                "action":   "BUY",
                "stock":    stock_name,
                "price":    round(price, 2),
                "quantity": quantity,
                "value":    buy_value,
                "capital":  capital_after,
                "saved_to": "Supabase ✅"
            }
        except Exception as e:
            print(f"⚠️ Supabase BUY failed: {e} — falling back to CSV")

    # ── CSV fallback ──────────────────────────────
    try:
        _save_trade_to_csv(trade)

        position_df = pd.DataFrame([position])
        os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
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
            "capital":  capital_after,
            "saved_to": "CSV (Supabase unavailable)"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "reason": str(e)
        }


def execute_paper_sell(stock_name, price):
    """
    Simulate selling a stock.
    Saves to Supabase (permanent) with CSV fallback.
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
    timestamp     = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    trade = {
        "Timestamp":     timestamp,
        "Stock":         stock_name,
        "Action":        "SELL",
        "Price":         round(price, 2),
        "Quantity":      quantity,
        "Value":         sell_value,
        "Capital_After": capital_after,
    }

    # ── Try Supabase ──────────────────────────────
    client = get_client()
    if client:
        try:
            _save_trade_to_supabase(client, trade)
            _delete_position_from_supabase(client, stock_name)
            return {
                "status":   "EXECUTED",
                "action":   "SELL",
                "stock":    stock_name,
                "price":    round(price, 2),
                "quantity": quantity,
                "value":    sell_value,
                "pnl":      pnl,
                "pnl_pct":  pnl_pct,
                "capital":  capital_after,
                "saved_to": "Supabase ✅"
            }
        except Exception as e:
            print(f"⚠️ Supabase SELL failed: {e} — falling back to CSV")

    # ── CSV fallback ──────────────────────────────
    try:
        _save_trade_to_csv(trade)

        # Remove from portfolio CSV
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
            "capital":  capital_after,
            "saved_to": "CSV (Supabase unavailable)"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "reason": str(e)
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

        curr_price = current_prices.get(stock, buy_price)
        curr_value = round(quantity * curr_price, 2)
        pnl        = round(curr_value - buy_value, 2)
        pnl_pct    = round((pnl / buy_value) * 100, 2)

        rows.append({
            "Stock":      stock,
            "Buy Price":  f"₹{buy_price}",
            "Current":    f"₹{curr_price}",
            "Qty":        quantity,
            "Buy Value":  f"₹{buy_value}",
            "Curr Value": f"₹{curr_value}",
            "P&L":        pnl,
            "P&L %":      pnl_pct,
        })

    return pd.DataFrame(rows)
