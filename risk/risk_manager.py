# ================================================
# FILE: risk/risk_manager.py
# PURPOSE: Protect capital with automatic rules
#          Stop loss, profit target, position limits
# ================================================

import pandas as pd
import os

# ── Risk Rules Configuration ─────────────────────
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    STOP_LOSS_PCT,
    TARGET_PROFIT_PCT,
    MAX_POSITION_PCT,
    MAX_OPEN_POSITIONS,
    TRADES_FILE,
    PORTFOLIO_FILE,
    STARTING_CAPITAL
)
MAX_DAILY_LOSS = 0.05


def load_portfolio():
    """Load current open positions."""
    if os.path.exists(PORTFOLIO_FILE):
        return pd.read_csv(PORTFOLIO_FILE)
    return pd.DataFrame(columns=[
        "Stock", "Buy_Price", "Quantity",
        "Buy_Value", "Buy_Date"
    ])


def load_trades():
    """Load all trades."""
    if os.path.exists(TRADES_FILE):
        return pd.read_csv(TRADES_FILE)
    return pd.DataFrame()


def get_current_capital():
    """Get available cash."""
    trades = load_trades()
    if trades.empty:
        return STARTING_CAPITAL
    return float(trades['Capital_After'].iloc[-1])


def check_stop_loss(stock_name, current_price):
    """
    Check if a stock has hit its stop loss.
    Returns True if we should SELL immediately.

    Example:
    Bought at ₹1000
    Stop loss at 3% = ₹970
    If current price < ₹970 → SELL NOW
    """
    portfolio = load_portfolio()

    if portfolio.empty:
        return False, None

    if stock_name not in portfolio['Stock'].values:
        return False, None

    position  = portfolio[portfolio['Stock'] == stock_name].iloc[0]
    buy_price = float(position['Buy_Price'])

    # Calculate stop loss price
    stop_price = round(buy_price * (1 - STOP_LOSS_PCT), 2)

    # Calculate current loss %
    loss_pct = round(((current_price - buy_price) / buy_price) * 100, 2)

    if current_price <= stop_price:
        return True, {
            "reason":     "STOP LOSS HIT",
            "buy_price":  buy_price,
            "stop_price": stop_price,
            "curr_price": current_price,
            "loss_pct":   loss_pct
        }

    return False, None


def check_profit_target(stock_name, current_price):
    """
    Check if a stock has hit its profit target.
    Returns True if we should SELL and take profit.

    Example:
    Bought at ₹1000
    Target at 6% = ₹1060
    If current price > ₹1060 → SELL and book profit
    """
    portfolio = load_portfolio()

    if portfolio.empty:
        return False, None

    if stock_name not in portfolio['Stock'].values:
        return False, None

    position  = portfolio[portfolio['Stock'] == stock_name].iloc[0]
    buy_price = float(position['Buy_Price'])

    # Calculate target price
    target_price = round(buy_price * (1 + TARGET_PROFIT_PCT), 2)

    # Calculate current gain %
    gain_pct = round(((current_price - buy_price) / buy_price) * 100, 2)

    if current_price >= target_price:
        return True, {
            "reason":       "PROFIT TARGET HIT",
            "buy_price":    buy_price,
            "target_price": target_price,
            "curr_price":   current_price,
            "gain_pct":     gain_pct
        }

    return False, None


def check_position_limit():
    """
    Check if we already have too many open positions.
    Returns True if we should NOT open any new trades.
    """
    portfolio = load_portfolio()

    if portfolio.empty:
        return False, 0

    open_positions = len(portfolio)

    if open_positions >= MAX_OPEN_POSITIONS:
        return True, open_positions

    return False, open_positions


def check_position_size(price, quantity):
    """
    Check if a trade is within safe position size.
    Never risk more than 10% of capital on one stock.
    """
    trade_value   = price * quantity
    capital       = get_current_capital()
    position_pct  = round((trade_value / STARTING_CAPITAL) * 100, 2)

    if position_pct > (MAX_POSITION_PCT * 100):
        return False, position_pct

    return True, position_pct


def check_daily_loss():
    """
    Check if we've lost too much today.
    If daily loss exceeds 5% — stop all trading.
    """
    trades = load_trades()

    if trades.empty:
        return False, 0

    # Get today's date
    today = pd.Timestamp.now().strftime('%Y-%m-%d')

    # Filter today's trades
    trades['Date'] = pd.to_datetime(trades['Timestamp']).dt.strftime('%Y-%m-%d')
    today_trades   = trades[trades['Date'] == today]

    if today_trades.empty:
        return False, 0

    # Capital at start of today vs now
    start_capital = float(today_trades['Capital_After'].iloc[0])
    end_capital   = float(today_trades['Capital_After'].iloc[-1])
    daily_loss_pct= round(((end_capital - start_capital) / start_capital) * 100, 2)

    if daily_loss_pct <= -(MAX_DAILY_LOSS * 100):
        return True, daily_loss_pct

    return False, daily_loss_pct


def run_full_risk_check(stock_name, current_price, action="BUY"):
    """
    Run ALL risk checks before any trade.
    Returns a clear GO / NO-GO decision with reasons.

    This is the main function called by the dashboard.
    """
    results = {
        "action":   action,
        "stock":    stock_name,
        "price":    current_price,
        "approved": True,
        "warnings": [],
        "blocks":   []
    }

    # ── Check 1: Daily loss limit ─────────────────
    daily_loss_hit, daily_loss_pct = check_daily_loss()
    if daily_loss_hit:
        results["approved"] = False
        results["blocks"].append(
            f"🛑 Daily loss limit hit ({daily_loss_pct}%) — no more trades today"
        )

    # ── Check 2: Position limit ───────────────────
    if action == "BUY":
        limit_hit, open_count = check_position_limit()
        if limit_hit:
            results["approved"] = False
            results["blocks"].append(
                f"🛑 Max positions reached ({open_count}/{MAX_OPEN_POSITIONS})"
            )
        else:
            results["warnings"].append(
                f"📊 Open positions: {open_count}/{MAX_OPEN_POSITIONS}"
            )

    # ── Check 3: Stop loss ────────────────────────
    if action == "SELL" or action == "CHECK":
        sl_hit, sl_info = check_stop_loss(stock_name, current_price)
        if sl_hit:
            results["warnings"].append(
                f"🛑 STOP LOSS: Buy ₹{sl_info['buy_price']} → "
                f"Stop ₹{sl_info['stop_price']} → "
                f"Now ₹{sl_info['curr_price']} "
                f"({sl_info['loss_pct']}%)"
            )

    # ── Check 4: Profit target ────────────────────
    if action == "SELL" or action == "CHECK":
        pt_hit, pt_info = check_profit_target(stock_name, current_price)
        if pt_hit:
            results["warnings"].append(
                f"🎯 PROFIT TARGET: Buy ₹{pt_info['buy_price']} → "
                f"Target ₹{pt_info['target_price']} → "
                f"Now ₹{pt_info['curr_price']} "
                f"(+{pt_info['gain_pct']}%)"
            )

    return results


def get_risk_summary(current_prices):
    """
    Scan all open positions for risk alerts.
    current_prices = dict of {stock_name: current_price}
    Returns list of alerts to show on dashboard.
    """
    portfolio = load_portfolio()
    alerts    = []

    if portfolio.empty:
        return alerts

    for _, position in portfolio.iterrows():
        stock         = position['Stock']
        current_price = current_prices.get(stock, float(position['Buy_Price']))

        # Check stop loss
        sl_hit, sl_info = check_stop_loss(stock, current_price)
        if sl_hit:
            alerts.append({
                "type":  "STOP LOSS",
                "stock": stock,
                "msg":   f"Loss: {sl_info['loss_pct']}% | Sell immediately!",
                "color": "red"
            })

        # Check profit target
        pt_hit, pt_info = check_profit_target(stock, current_price)
        if pt_hit:
            alerts.append({
                "type":  "PROFIT TARGET",
                "stock": stock,
                "msg":   f"Gain: +{pt_info['gain_pct']}% | Consider selling!",
                "color": "green"
            })

    return alerts