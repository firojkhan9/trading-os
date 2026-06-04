# ================================================
# FILE: strategies/paper_trader.py
# PURPOSE: Simulate trades based on signals
#          PRIMARY: Supabase database (permanent)
#          FALLBACK: CSV file (local only)
#
# UPDATED — Milestone 24 portfolio improvements:
#   get_portfolio_summary() now returns:
#   - Stop Loss price + how far away (%)
#   - Target price + how far away (%)
#   - Days Held
#   - Suggestion: ADD / HOLD / SELL with reason
#   - TOTAL summary row at the bottom
#
# Everything else unchanged — Supabase + CSV fallback
# logic is exactly as before.
# ================================================

import pandas as pd
import os
from datetime import datetime, date

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.supabase_client import get_client

# ── Settings ──────────────────────────────────────
try:
    from config.strategy_settings import (
        STARTING_CAPITAL,
        MAX_POSITION_PCT,
        STOP_LOSS_PCT,
        TARGET_PROFIT_PCT,
    )
except ImportError:
    STARTING_CAPITAL  = 100000
    MAX_POSITION_PCT  = 0.10
    STOP_LOSS_PCT     = 0.06
    TARGET_PROFIT_PCT = 0.15

# ── CSV fallback paths ────────────────────────────
try:
    from config.settings import TRADES_FILE, PORTFOLIO_FILE
except Exception:
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TRADES_FILE    = os.path.join(_base, "logs", "paper_trades.csv")
    PORTFOLIO_FILE = os.path.join(_base, "logs", "paper_portfolio.csv")


# ════════════════════════════════════════════════
# LOAD FUNCTIONS — unchanged from original
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
    from portfolio.capital_engine import load_portfolio_from_bucket_trades
    df = load_portfolio_from_bucket_trades()
    if df is not None:
        return df
    return pd.DataFrame(columns=["Stock", "Buy_Price", "Quantity", "Buy_Value", "Buy_Date", "Bucket"])

def get_current_capital():
    """
    Get current available cash.
    Reads from last trade's capital_after field.
    """
    trades = load_trades()

    if trades.empty:
        return STARTING_CAPITAL

    trades = trades.sort_values('Timestamp', ascending=True)
    return float(trades['Capital_After'].iloc[-1])


# ════════════════════════════════════════════════
# WRITE FUNCTIONS — unchanged from original
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
# PAPER TRADING FUNCTIONS — unchanged from original
# ════════════════════════════════════════════════

def execute_paper_buy(stock_name, price):
    """
    Simulate buying a stock.
    Saves to Supabase (permanent) with CSV fallback.
    """
    capital   = get_current_capital()
    portfolio = load_portfolio()

    if not portfolio.empty and stock_name in portfolio['Stock'].values:
        return {
            "status":  "SKIPPED",
            "reason":  f"Already holding {stock_name}",
            "capital": capital
        }

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


# ════════════════════════════════════════════════
# UPDATED: get_portfolio_summary
# Now includes stop/target levels, days held,
# suggestion per stock, and a TOTAL row at bottom
# ════════════════════════════════════════════════

def _get_suggestion(pnl_pct, combined_signal=None):
    """
    Decide what action to suggest for a held position.

    Rules (checked in priority order):
      1. Loss >= stop loss %      → SELL (Stop Loss)
      2. Gain >= target %         → SELL (Take Profit)
      3. Combined signal = STRONG BUY → ADD
      4. Combined signal has SELL  → SELL (Signal Exit)
      5. Gain >= 60% of target     → HOLD (Near Target)
      6. Small loss, not at stop   → HOLD (Watch Loss)
      7. Everything normal         → HOLD

    pnl_pct        : current P&L % (positive = profit)
    combined_signal: string like "STRONG BUY 🟢🟢" or None
    """
    stop_threshold   = -(STOP_LOSS_PCT * 100)      # e.g. -6.0
    target_threshold =  (TARGET_PROFIT_PCT * 100)  # e.g. 15.0
    near_target      =  target_threshold * 0.60    # e.g. 9.0

    if pnl_pct <= stop_threshold:
        return "🔴 SELL — Stop Loss Hit"

    if pnl_pct >= target_threshold:
        return "✅ SELL — Take Profit"

    sig = str(combined_signal).upper() if combined_signal else ""

    if "STRONG BUY" in sig:
        return "🟢 ADD — Strong Signal"

    if "SELL" in sig and "STRONG SELL" in sig:
        return "🔴 SELL — Strong Signal Exit"

    if "SELL" in sig:
        return "🟠 SELL — Signal Exit"

    if pnl_pct >= near_target:
        return "🟡 HOLD — Near Target"

    if pnl_pct < 0:
        return "🟡 HOLD — Watch Loss"

    return "🟢 HOLD"


def get_portfolio_summary(current_prices, combined_signals=None):
    """
    Show current portfolio with live P&L, risk levels, and suggestions.

    Parameters:
      current_prices   : dict {stock_name: current_price}
      combined_signals : dict {stock_name: combined_signal_string}  (optional)
                         If passed, suggestions use live signal context.
                         If None, suggestions use price logic only.

    Returns a DataFrame with columns:
      Stock | Buy ₹ | Now ₹ | Qty | Invested ₹ | Value ₹ |
      P&L ₹ | P&L % | Stop ₹ | Stop Away | Target ₹ | Target Away |
      Days Held | Suggestion

    Last row is a TOTAL summary row showing portfolio-level totals.
    """
    portfolio = load_portfolio()

    if portfolio.empty:
        return pd.DataFrame()

    rows             = []
    total_invested   = 0.0
    total_curr_value = 0.0

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

        # ── Stop loss and target price levels ─────
        stop_price   = round(buy_price * (1 - STOP_LOSS_PCT), 2)
        target_price = round(buy_price * (1 + TARGET_PROFIT_PCT), 2)

        # How far is current price from stop / target (%)
        stop_away   = round(((curr_price - stop_price)   / curr_price) * 100, 1)
        target_away = round(((target_price - curr_price) / curr_price) * 100, 1)

        # ── Days held ─────────────────────────────
        days_held = 0
        try:
            buy_date  = pd.to_datetime(pos['Buy_Date']).date()
            days_held = (date.today() - buy_date).days
        except Exception:
            days_held = 0

        # ── Suggestion ────────────────────────────
        signal     = combined_signals.get(stock) if combined_signals else None
        suggestion = _get_suggestion(pnl_pct, signal)

        total_invested   += buy_value
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

    # ── TOTAL row ─────────────────────────────────
    total_pnl     = round(total_curr_value - total_invested, 2)
    total_pnl_pct = round((total_pnl / total_invested) * 100, 2) if total_invested > 0 else 0.0

    total_row = {
        "Stock":        "📊 TOTAL",
        "Buy ₹":        "",
        "Now ₹":        "",
        "Qty":          int(df["Qty"].sum()),
        "Invested ₹":   round(total_invested, 2),
        "Value ₹":      round(total_curr_value, 2),
        "P&L ₹":        total_pnl,
        "P&L %":        total_pnl_pct,
        "Stop ₹":       "",
        "Stop Away":    "",
        "Target ₹":     "",
        "Target Away":  "",
        "Days Held":    "",
        "Suggestion":   "✅ Overall Profit" if total_pnl >= 0 else "⚠️ Overall Loss",
    }

    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)
    return df