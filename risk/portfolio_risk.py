# ================================================
# FILE: risk/portfolio_risk.py
# PURPOSE: Advanced Portfolio Risk Engine — Milestone 30
#
# WHAT THIS FILE DOES:
#   Moves beyond per-trade stop loss to portfolio-level
#   intelligence. Every BUY must pass through this engine
#   before capital_engine.py executes it.
#
# THE 10 FEATURES:
#   1.  Portfolio Risk Summary      — overall health check
#   2.  Sector Exposure Limit       — max 30% in any one sector
#   3.  Correlation Risk Check      — avoid 3+ correlated stocks
#   4.  Bucket Drawdown Control     — pause bucket if down >10%
#   5.  Daily Portfolio Loss Limit  — halt all buys if down >5% today
#   6.  Max Capital Deployment      — never deploy >70% at once
#   7.  ATR Stop Loss               — dynamic stop based on volatility
#   8.  Volatility-Adjusted Sizing  — smaller positions in volatile stocks
#   9.  Regime-Aware Aggression     — BULL=100%, SIDEWAYS=50%, CRASH=0%
#  10.  Master Risk Gate            — single validate_portfolio_risk()
#
# THE FLOW:
#   BEFORE M30: Scanner → Score → Capital Engine → BUY
#   AFTER  M30: Scanner → Score → Portfolio Risk Gate → Capital Engine → BUY
#
# HOW IT CONNECTS:
#   capital_engine.py      → calls validate_portfolio_risk() before bucket_buy()
#   execution_loop.py      → calls validate_portfolio_risk() in _is_ok_to_buy()
#   app.py Tab 9           → calls get_portfolio_risk_summary() for display
#   position_manager.py    → calls calculate_atr_stop() for dynamic stops
#
# IMPORTANT DESIGN RULE:
#   This engine NEVER places trades. It only approves or rejects them.
#   Rejection reasons are always plain English, logged, and visible
#   in the dashboard so you understand exactly WHY a trade was blocked.
# ================================================

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Internal imports ──────────────────────────────
# Use try/except for each — this engine should never crash the app
try:
    from portfolio.capital_engine import (
        load_bucket_state,
        load_bucket_trades,
        get_portfolio_totals,
        get_open_positions_by_bucket,
        BUCKET_CONFIG,
        TOTAL_CAPITAL,
    )
    CAPITAL_ENGINE_AVAILABLE = True
except ImportError:
    CAPITAL_ENGINE_AVAILABLE = False

try:
    from strategies.watchlist_manager import load_watchlist
    WATCHLIST_AVAILABLE = True
except ImportError:
    WATCHLIST_AVAILABLE = False

try:
    from strategies.market_regime import get_full_regime_analysis
    REGIME_AVAILABLE = True
except ImportError:
    REGIME_AVAILABLE = False


# ════════════════════════════════════════════════
# RISK CONFIGURATION
# All limits configurable here — no hardcoded values
# in the logic functions below.
# ════════════════════════════════════════════════

RISK_CONFIG = {
    # Sector exposure: max % of total portfolio in any one sector
    # Example: 3 banking stocks at 10% each = 30% — allowed
    #          4 banking stocks at 10% each = 40% — BLOCKED
    "max_sector_pct":         0.30,    # 30%

    # Correlation: max number of highly correlated holdings
    # before blocking a new correlated entry
    "max_correlated_holdings": 2,      # block if 3 or more existing are correlated

    # Correlation threshold: daily return correlation above this = "highly correlated"
    "correlation_threshold":  0.80,    # 0.80 = strong positive correlation

    # Days of history to use for correlation calculation
    "correlation_lookback":   60,      # 60 trading days

    # Bucket drawdown limit: if bucket P&L drops below this %,
    # pause that bucket (no new buys from it)
    "bucket_drawdown_limit":  -0.10,   # -10%

    # Daily portfolio loss limit: if total portfolio drops below
    # this % in a single day, halt ALL new BUY orders
    "daily_loss_limit":       -0.05,   # -5%

    # Max capital deployment: never deploy more than this % of total capital
    # Keeps a cash reserve to handle unexpected moves
    "max_deployment_pct":     0.70,    # 70%

    # ATR multiplier for dynamic stop loss
    # Stop = entry_price - (ATR × multiplier)
    "atr_stop_multiplier":    2.0,     # 2x ATR

    # ATR period for calculation
    "atr_period":             14,      # 14 days

    # Volatility tiers for position sizing adjustment
    # ATR as % of price → position multiplier
    "volatility_tiers": [
        (0.02,  1.00),  # ATR% < 2%  → full size (1.00x)
        (0.04,  0.75),  # ATR% < 4%  → 75% of intended size
        (9999,  0.50),  # ATR% >= 4% → 50% of intended size
    ],

    # Regime position multipliers
    # The loop checks this BEFORE calculating position size
    "regime_multipliers": {
        "STRONG_BULL": 1.00,
        "BULL":        1.00,
        "WEAK_BULL":   0.75,
        "SIDEWAYS":    0.50,
        "WEAK_BEAR":   0.25,
        "BEAR":        0.00,   # No new longs in bear market
        "CRASH":       0.00,   # No new longs in crash
        "UNKNOWN":     0.75,   # Unknown regime → cautious
    },
}


# ════════════════════════════════════════════════
# FEATURE 1 — PORTFOLIO RISK SUMMARY
# Single call to get the overall risk picture.
# Used by the dashboard to show a health banner.
# ════════════════════════════════════════════════

def get_portfolio_risk_summary(regime=None):
    """
    Get a complete risk overview of the current portfolio.

    Returns a dict with:
      capital_deployed_pct  : % of total capital currently deployed
      daily_pnl_pct         : today's portfolio P&L as a %
      largest_sector_pct    : % in the most concentrated sector
      largest_sector_name   : which sector is most concentrated
      open_positions_count  : total open positions across all buckets
      risk_level            : "LOW" / "NORMAL" / "ELEVATED" / "HIGH" / "CRITICAL"
      trading_allowed       : True if all safety checks pass
      warnings              : list of active risk warnings
      regime                : current market regime
    """
    warnings     = []
    risk_level   = "NORMAL"
    trading_ok   = True

    # Defaults in case data isn't available
    deployed_pct  = 0.0
    daily_pnl_pct = 0.0
    sector_pct    = 0.0
    sector_name   = "Unknown"
    open_count    = 0

    try:
        # ── Capital deployment ─────────────────────
        if CAPITAL_ENGINE_AVAILABLE:
            totals       = get_portfolio_totals()
            deployed_pct = round(
                totals["total_deployed"] / totals["total_starting"] * 100, 1
            ) if totals["total_starting"] > 0 else 0.0

            if deployed_pct >= RISK_CONFIG["max_deployment_pct"] * 100:
                warnings.append(
                    f"⚠️ Capital deployment at {deployed_pct}% "
                    f"(limit: {int(RISK_CONFIG['max_deployment_pct']*100)}%)"
                )
                trading_ok = False

        # ── Daily P&L ─────────────────────────────
        daily_ok, daily_pnl_pct = _check_daily_loss_internal()
        if not daily_ok:
            warnings.append(
                f"🛑 Daily loss limit hit ({daily_pnl_pct:+.1f}%) — "
                f"no new buys today"
            )
            trading_ok = False

        # ── Sector concentration ───────────────────
        sector_data  = _get_sector_breakdown()
        if sector_data:
            top_sector   = max(sector_data, key=sector_data.get)
            sector_pct   = round(sector_data[top_sector] * 100, 1)
            sector_name  = top_sector
            limit_pct    = round(RISK_CONFIG["max_sector_pct"] * 100)

            if sector_pct > limit_pct:
                warnings.append(
                    f"⚠️ {top_sector} exposure: {sector_pct}% "
                    f"(limit: {limit_pct}%)"
                )

        # ── Open positions ─────────────────────────
        if CAPITAL_ENGINE_AVAILABLE:
            for bname in BUCKET_CONFIG.keys():
                open_count += len(get_open_positions_by_bucket(bname))

        # ── Regime check ──────────────────────────
        if regime is None and REGIME_AVAILABLE:
            try:
                rd     = get_full_regime_analysis(period="1y")
                regime = rd.get("regime", "UNKNOWN")
            except Exception:
                regime = "UNKNOWN"

        if regime and "BEAR" in str(regime).upper() and "WEAK" not in str(regime).upper():
            warnings.append(
                f"🐻 BEAR market regime ({regime}) — no new longs recommended"
            )

    except Exception as e:
        warnings.append(f"Risk check partial error: {e}")

    # ── Determine overall risk level ───────────────
    if not trading_ok or len(warnings) >= 3:
        risk_level = "CRITICAL"
    elif len(warnings) == 2:
        risk_level = "HIGH"
    elif len(warnings) == 1:
        risk_level = "ELEVATED"
    elif deployed_pct > 50:
        risk_level = "NORMAL"
    else:
        risk_level = "LOW"

    return {
        "capital_deployed_pct": deployed_pct,
        "daily_pnl_pct":        daily_pnl_pct,
        "largest_sector_pct":   sector_pct,
        "largest_sector_name":  sector_name,
        "open_positions_count": open_count,
        "risk_level":           risk_level,
        "trading_allowed":      trading_ok,
        "warnings":             warnings,
        "regime":               regime or "UNKNOWN",
    }


# ════════════════════════════════════════════════
# FEATURE 2 — SECTOR EXPOSURE LIMIT
# Prevent too much concentration in one sector.
# ════════════════════════════════════════════════

def check_sector_exposure(sector, proposed_trade_value):
    """
    Check if adding this trade would breach the sector exposure limit.

    HOW IT WORKS:
      1. Find all currently open positions
      2. Map each stock to its sector (via watchlist)
      3. Calculate what % of total portfolio is in each sector
      4. Add the proposed trade value to that sector's total
      5. Check if result > 30% limit

    sector              : the sector of the stock being considered
                          e.g. "Finance", "Technology", "Energy"
    proposed_trade_value: the ₹ value of the proposed trade

    Returns (approved: bool, current_pct: float, message: str)
    """
    try:
        sector_breakdown  = _get_sector_breakdown()
        current_pct       = sector_breakdown.get(sector, 0.0)

        # What would the sector % be if we add this trade?
        totals            = get_portfolio_totals() if CAPITAL_ENGINE_AVAILABLE else {}
        total_starting    = totals.get("total_starting", TOTAL_CAPITAL if CAPITAL_ENGINE_AVAILABLE else 600000)
        total_deployed    = totals.get("total_deployed", 0)
        total_after_trade = total_deployed + proposed_trade_value

        # Sector value currently + proposed trade
        sector_current_value  = current_pct * total_deployed
        sector_after_value    = sector_current_value + proposed_trade_value
        sector_pct_after      = round(
            sector_after_value / total_starting, 4
        ) if total_starting > 0 else 0.0

        limit = RISK_CONFIG["max_sector_pct"]

        if sector_pct_after > limit:
            return (
                False,
                round(sector_pct_after * 100, 1),
                f"{sector} exposure would be {sector_pct_after*100:.1f}% "
                f"(limit: {limit*100:.0f}%). "
                f"Sector is currently at {current_pct*100:.1f}%. "
                f"Sell a {sector} holding first, or pick a stock from another sector."
            )

        return (
            True,
            round(sector_pct_after * 100, 1),
            f"{sector} exposure after trade: {sector_pct_after*100:.1f}% "
            f"(limit: {limit*100:.0f}%) — OK"
        )

    except Exception as e:
        # If the check fails for any reason, let the trade through
        # (never block because of a data error)
        return True, 0.0, f"Sector check skipped (data issue: {e})"


def _get_sector_breakdown():
    """
    Internal helper: build {sector: fraction_of_deployed} dict
    for all currently open positions.

    Returns empty dict if no positions or data not available.
    """
    if not CAPITAL_ENGINE_AVAILABLE or not WATCHLIST_AVAILABLE:
        return {}

    try:
        # Get sector mapping from watchlist
        wl_df     = load_watchlist(active_only=False)
        sector_map = dict(zip(wl_df["Name"], wl_df["Sector"]))

        totals    = get_portfolio_totals()
        deployed  = totals.get("total_deployed", 0)
        if deployed <= 0:
            return {}

        # Get open positions across all buckets
        all_open = {}
        trades   = load_bucket_trades()
        if trades.empty:
            return {}

        for bname in BUCKET_CONFIG.keys():
            b_trades = trades[trades["Bucket"] == bname]
            buys  = b_trades[b_trades["Action"] == "BUY"]
            sells = set(b_trades[b_trades["Action"] == "SELL"]["Stock"].tolist())
            for _, row in buys.iterrows():
                stock = str(row["Stock"])
                if stock not in sells:
                    value = float(row["Value"]) if row["Value"] else 0
                    if stock in all_open:
                        all_open[stock] = all_open[stock] + value
                    else:
                        all_open[stock] = value

        # Build sector totals
        sector_totals = {}
        for stock, value in all_open.items():
            sector = sector_map.get(stock, "Unknown")
            sector_totals[sector] = sector_totals.get(sector, 0) + value

        # Convert to fraction of deployed capital
        sector_fractions = {
            s: round(v / deployed, 4) for s, v in sector_totals.items()
        }
        return sector_fractions

    except Exception:
        return {}


# ════════════════════════════════════════════════
# FEATURE 3 — CORRELATION RISK CHECK
# Avoid buying stocks that move together.
# ════════════════════════════════════════════════

def check_correlation_risk(stock_symbol):
    """
    Check if this stock is highly correlated with too many current holdings.

    WHY THIS MATTERS:
      TCS, INFY, WIPRO all rise and fall together.
      Holding all three is not real diversification —
      it is effectively one large IT trade.

    HOW IT WORKS:
      1. Fetch 60 days of daily returns for candidate stock
      2. Fetch same for all currently held stocks
      3. Calculate pairwise correlation
      4. Count how many holdings have correlation > 0.80
      5. If 3 or more existing holdings are correlated → BLOCK

    stock_symbol : Yahoo Finance symbol e.g. "INFY.NS"

    Returns (approved: bool, correlated_count: int, message: str)
    """
    try:
        import yfinance as yf

        if not CAPITAL_ENGINE_AVAILABLE:
            return True, 0, "Correlation check skipped (capital engine unavailable)"

        # Get all currently held stocks
        all_held = []
        for bname in BUCKET_CONFIG.keys():
            all_held.extend(get_open_positions_by_bucket(bname))

        if not all_held:
            return True, 0, "No current holdings — correlation check not needed"

        # Get watchlist for symbols
        symbol_map = {}
        if WATCHLIST_AVAILABLE:
            wl_df      = load_watchlist(active_only=False)
            symbol_map = dict(zip(wl_df["Name"], wl_df["Symbol"]))

        lookback = RISK_CONFIG["correlation_lookback"]
        period   = "3mo"   # 3 months ≈ 60 trading days

        # Fetch candidate stock returns
        try:
            cand_data = yf.download(
                tickers=stock_symbol, period=period,
                interval="1d", progress=False, auto_adjust=True
            )
            if cand_data.empty or len(cand_data) < 20:
                return True, 0, "Correlation check skipped (insufficient data for candidate)"
            cand_data.columns   = [col[0] for col in cand_data.columns]
            cand_returns        = cand_data["Close"].pct_change().dropna()
        except Exception:
            return True, 0, "Correlation check skipped (data fetch error)"

        # Calculate correlation with each held stock
        high_corr_count    = 0
        high_corr_stocks   = []
        threshold          = RISK_CONFIG["correlation_threshold"]

        for held_name in all_held:
            held_symbol = symbol_map.get(held_name)
            if not held_symbol or held_symbol == stock_symbol:
                continue

            try:
                held_data = yf.download(
                    tickers=held_symbol, period=period,
                    interval="1d", progress=False, auto_adjust=True
                )
                if held_data.empty or len(held_data) < 20:
                    continue
                held_data.columns = [col[0] for col in held_data.columns]
                held_returns = held_data["Close"].pct_change().dropna()

                # Align on same dates
                aligned = pd.concat(
                    [cand_returns, held_returns], axis=1, join="inner"
                ).dropna()
                if len(aligned) < 20:
                    continue

                corr = round(float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])), 3)

                if corr >= threshold:
                    high_corr_count += 1
                    high_corr_stocks.append(f"{held_name} (r={corr})")

            except Exception:
                continue

        max_allowed = RISK_CONFIG["max_correlated_holdings"]

        if high_corr_count >= max_allowed:
            return (
                False,
                high_corr_count,
                f"Highly correlated with {high_corr_count} existing holding(s): "
                f"{', '.join(high_corr_stocks[:3])}. "
                f"Adding this would create concentrated correlated exposure. "
                f"Pick a stock from a different sector or lower correlation."
            )

        return (
            True,
            high_corr_count,
            f"Correlation check passed — "
            f"{high_corr_count} correlated holding(s) (max allowed: {max_allowed-1})"
        )

    except Exception as e:
        return True, 0, f"Correlation check skipped (error: {e})"


# ════════════════════════════════════════════════
# FEATURE 4 — BUCKET DRAWDOWN CONTROL
# If a bucket has lost too much, pause it.
# ════════════════════════════════════════════════

def check_bucket_drawdown(bucket_name):
    """
    Check if a specific bucket has exceeded its drawdown limit.

    WHY:
      Even if overall portfolio is fine, one bucket might be
      in a losing streak. We pause that bucket to protect it
      while others continue operating.

    HOW:
      Drawdown = (Available Cash + Deployed Capital - Starting Capital)
                  / Starting Capital × 100

    If drawdown <= -10% → bucket is paused.

    bucket_name : "Long-Term" / "Swing" / "Intraday"

    Returns (allowed: bool, drawdown_pct: float, message: str)
    """
    try:
        if not CAPITAL_ENGINE_AVAILABLE:
            return True, 0.0, "Drawdown check skipped"

        state = load_bucket_state()
        if bucket_name not in state:
            return True, 0.0, f"Bucket '{bucket_name}' not found — check skipped"

        bucket     = state[bucket_name]
        starting   = float(bucket.get("Starting_Capital", 0))
        available  = float(bucket.get("Available_Cash",   0))
        deployed   = float(bucket.get("Deployed_Capital", 0))
        pnl        = float(bucket.get("Total_PNL",        0))

        if starting <= 0:
            return True, 0.0, "Starting capital unavailable — check skipped"

        # Current equity = cash + deployed (mark-to-market would need live prices,
        # so we use book value as a conservative proxy)
        current_equity = available + deployed
        drawdown_pct   = round(
            (current_equity - starting) / starting * 100, 2
        )

        limit_pct = round(RISK_CONFIG["bucket_drawdown_limit"] * 100, 1)

        if drawdown_pct <= (RISK_CONFIG["bucket_drawdown_limit"] * 100):
            return (
                False,
                drawdown_pct,
                f"{bucket_name} bucket drawdown: {drawdown_pct:+.1f}% "
                f"(limit: {limit_pct}%). "
                f"Bucket paused — no new entries until losses recover. "
                f"Existing positions continue unaffected."
            )

        return (
            True,
            drawdown_pct,
            f"{bucket_name} drawdown: {drawdown_pct:+.1f}% — within limit ({limit_pct}%)"
        )

    except Exception as e:
        return True, 0.0, f"Drawdown check skipped (error: {e})"


# ════════════════════════════════════════════════
# FEATURE 5 — DAILY PORTFOLIO LOSS LIMIT
# Stop all new trading if today has been terrible.
# ════════════════════════════════════════════════

def check_daily_loss_limit():
    """
    Check if the portfolio has lost too much today.

    If total portfolio P&L has fallen by more than 5% today →
    halt all new BUY orders for the rest of the day.
    Existing positions and their stop losses are still monitored.

    IMPORTANT: This is a DAILY check, not an all-time check.
    It resets at the start of each trading day.

    Returns (trading_allowed: bool, daily_pnl_pct: float, message: str)
    """
    allowed, pnl_pct = _check_daily_loss_internal()

    if not allowed:
        return (
            False,
            pnl_pct,
            f"Daily loss limit reached: portfolio down {pnl_pct:+.1f}% today "
            f"(limit: {RISK_CONFIG['daily_loss_limit']*100:.0f}%). "
            f"No new BUY orders until tomorrow. "
            f"Existing stop losses still active."
        )

    return (
        True,
        pnl_pct,
        f"Daily P&L: {pnl_pct:+.1f}% — within limit ({RISK_CONFIG['daily_loss_limit']*100:.0f}%)"
    )


def _check_daily_loss_internal():
    """
    Internal helper: returns (allowed: bool, pnl_pct: float).
    Separated so get_portfolio_risk_summary() can also use it
    without the message formatting overhead.
    """
    try:
        if not CAPITAL_ENGINE_AVAILABLE:
            return True, 0.0

        trades_df = load_bucket_trades()
        if trades_df.empty:
            return True, 0.0

        today_str = date.today().strftime('%Y-%m-%d')

        # Filter today's trades
        trades_df["Date"] = pd.to_datetime(
            trades_df["Timestamp"], errors="coerce"
        ).dt.strftime('%Y-%m-%d')
        today_trades = trades_df[trades_df["Date"] == today_str]

        if today_trades.empty:
            return True, 0.0

        # Sum realised P&L from today's SELL trades
        today_sells  = today_trades[today_trades["Action"] == "SELL"]
        today_pnl    = 0.0
        if not today_sells.empty and "PNL" in today_sells.columns:
            pnl_values = pd.to_numeric(today_sells["PNL"], errors="coerce").dropna()
            today_pnl  = float(pnl_values.sum())

        totals    = get_portfolio_totals()
        starting  = totals.get("total_starting", 1)
        pnl_pct   = round(today_pnl / starting * 100, 2) if starting > 0 else 0.0

        allowed = pnl_pct > (RISK_CONFIG["daily_loss_limit"] * 100)
        return allowed, pnl_pct

    except Exception:
        return True, 0.0


# ════════════════════════════════════════════════
# FEATURE 6 — MAX CAPITAL DEPLOYMENT
# Always keep some cash in reserve.
# ════════════════════════════════════════════════

def check_max_exposure(proposed_trade_value):
    """
    Check if adding this trade would exceed the max deployment limit.

    WHY:
      Markets can move against you suddenly. If 90% of capital is
      deployed and prices crash 10%, there's nothing left to average
      down or take new opportunities. Keeping 30% as cash is a
      discipline — not a weakness.

    proposed_trade_value: ₹ value of the proposed trade

    Returns (approved: bool, deployment_pct_after: float, message: str)
    """
    try:
        if not CAPITAL_ENGINE_AVAILABLE:
            return True, 0.0, "Deployment check skipped"

        totals   = get_portfolio_totals()
        starting = totals.get("total_starting", TOTAL_CAPITAL)
        deployed = totals.get("total_deployed", 0)

        deployed_after = deployed + proposed_trade_value
        pct_after      = round(deployed_after / starting * 100, 1) if starting > 0 else 0.0
        limit_pct      = round(RISK_CONFIG["max_deployment_pct"] * 100)

        if pct_after > limit_pct:
            return (
                False,
                pct_after,
                f"Max deployment would be {pct_after}% after this trade "
                f"(limit: {limit_pct}%). "
                f"Currently {round(deployed/starting*100,1)}% deployed. "
                f"Sell an existing position first to free up capital."
            )

        return (
            True,
            pct_after,
            f"Deployment after trade: {pct_after}% (limit: {limit_pct}%) — OK"
        )

    except Exception as e:
        return True, 0.0, f"Deployment check skipped (error: {e})"


# ════════════════════════════════════════════════
# FEATURE 7 — ATR STOP LOSS
# Dynamic stop based on actual stock volatility.
# ════════════════════════════════════════════════

def calculate_atr_stop(symbol, entry_price):
    """
    Calculate a dynamic stop loss price using ATR.

    WHAT IS ATR?
      Average True Range = the average daily price movement
      of a stock over the last 14 days.
      It is a direct measure of how volatile a stock is.

    WHY ATR-BASED STOP?
      A fixed 6% stop loss makes no sense for all stocks.
      If TCS normally moves 1% per day, a 6% stop is fine.
      If TATASTEEL moves 3% per day, a 6% stop gets triggered
      constantly by normal noise.

      ATR-based stop: entry - (2 × ATR)
      This gives the stock "room to breathe" based on its own
      normal range, without triggering on routine fluctuations.

    symbol      : Yahoo Finance symbol e.g. "RELIANCE.NS"
    entry_price : the price you're entering at

    Returns dict:
      {
        atr          : float (14-day ATR in ₹),
        atr_pct      : float (ATR as % of entry price),
        stop_price   : float (entry - 2×ATR),
        stop_pct     : float (stop % below entry),
        data_available: bool
      }
    """
    try:
        import yfinance as yf

        data = yf.download(
            tickers=symbol, period="2mo",
            interval="1d", progress=False, auto_adjust=True
        )
        if data.empty or len(data) < RISK_CONFIG["atr_period"] + 2:
            return {
                "atr":            None,
                "atr_pct":        None,
                "stop_price":     round(entry_price * 0.94, 2),  # fallback: 6%
                "stop_pct":       6.0,
                "data_available": False,
            }

        data.columns = [col[0] for col in data.columns]

        high  = data["High"]
        low   = data["Low"]
        close = data["Close"]
        prev  = close.shift(1)

        tr = pd.concat([
            high - low,
            (high - prev).abs(),
            (low  - prev).abs(),
        ], axis=1).max(axis=1)

        atr_period = RISK_CONFIG["atr_period"]
        atr        = float(tr.rolling(window=atr_period).mean().iloc[-1])
        atr_pct    = round(atr / entry_price * 100, 2)
        multiplier = RISK_CONFIG["atr_stop_multiplier"]
        stop_price = round(entry_price - (atr * multiplier), 2)
        stop_pct   = round((entry_price - stop_price) / entry_price * 100, 2)

        return {
            "atr":            round(atr, 2),
            "atr_pct":        atr_pct,
            "stop_price":     stop_price,
            "stop_pct":       stop_pct,
            "data_available": True,
        }

    except Exception as e:
        return {
            "atr":            None,
            "atr_pct":        None,
            "stop_price":     round(entry_price * 0.94, 2),
            "stop_pct":       6.0,
            "data_available": False,
            "error":          str(e),
        }


# ════════════════════════════════════════════════
# FEATURE 8 — VOLATILITY-ADJUSTED POSITION SIZING
# Smaller positions when the stock is more volatile.
# ════════════════════════════════════════════════

def get_volatility_multiplier(symbol):
    """
    Return a position size multiplier based on the stock's volatility.

    LOGIC:
      ATR%  = ATR / Current Price × 100
      (how big is a typical daily move as a % of price?)

      Low volatility  (ATR% < 2%)  → full size  (1.00×)
      Medium          (ATR% 2-4%)  → 75% of size (0.75×)
      High volatility (ATR% > 4%)  → 50% of size (0.50×)

    WHY:
      Buying a highly volatile stock at full size means
      your stop loss needs to be further away (larger loss)
      or gets triggered constantly by noise (death by cuts).
      Smaller position = same risk amount, wider stop allowed.

    symbol : Yahoo Finance symbol e.g. "TATASTEEL.NS"

    Returns (multiplier: float, atr_pct: float, label: str)
    """
    try:
        import yfinance as yf

        data = yf.download(
            tickers=symbol, period="1mo",
            interval="1d", progress=False, auto_adjust=True
        )
        if data.empty or len(data) < 10:
            return 1.0, 0.0, "NORMAL (data unavailable)"

        data.columns = [col[0] for col in data.columns]
        high  = data["High"]
        low   = data["Low"]
        close = data["Close"]
        prev  = close.shift(1)

        tr     = pd.concat([
            high - low,
            (high - prev).abs(),
            (low  - prev).abs(),
        ], axis=1).max(axis=1)

        atr       = float(tr.rolling(window=14).mean().dropna().iloc[-1])
        price     = float(close.iloc[-1])
        atr_pct   = round(atr / price, 4) if price > 0 else 0

        tiers = RISK_CONFIG["volatility_tiers"]
        for (threshold, multiplier) in tiers:
            if atr_pct < threshold:
                if multiplier == 1.00:
                    label = f"LOW VOLATILITY (ATR {atr_pct*100:.1f}%) → full size"
                elif multiplier == 0.75:
                    label = f"MEDIUM VOLATILITY (ATR {atr_pct*100:.1f}%) → 75% size"
                else:
                    label = f"HIGH VOLATILITY (ATR {atr_pct*100:.1f}%) → 50% size"
                return multiplier, round(atr_pct * 100, 2), label

        return 0.50, round(atr_pct * 100, 2), f"VERY HIGH VOLATILITY (ATR {atr_pct*100:.1f}%) → 50% size"

    except Exception as e:
        return 1.0, 0.0, f"NORMAL (error: {e})"


# ════════════════════════════════════════════════
# FEATURE 9 — REGIME-AWARE AGGRESSION
# Scale down position sizes in weak or bear markets.
# ════════════════════════════════════════════════

def get_regime_position_multiplier(regime=None):
    """
    Return a position size multiplier based on current market regime.

    BULL market     → trade at full intended size (1.00×)
    WEAK BULL       → slightly cautious (0.75×)
    SIDEWAYS        → defensive (0.50×)
    WEAK BEAR       → very cautious (0.25×)
    BEAR / CRASH    → NO new trades (0.00×)

    WHY:
      A strategy that works in a BULL market can fail badly in BEAR.
      Adjusting size based on regime is the single most powerful
      risk management lever available. It keeps you in the game
      when conditions are against you, without forcing you out
      entirely (which would mean missing the recovery).

    regime : market regime string from market_regime.py
             If None, tries to fetch it automatically.

    Returns (multiplier: float, regime: str, label: str)
    """
    if regime is None and REGIME_AVAILABLE:
        try:
            rd     = get_full_regime_analysis(period="1y")
            regime = rd.get("regime", "UNKNOWN")
        except Exception:
            regime = "UNKNOWN"

    regime_upper = str(regime).upper()
    multipliers  = RISK_CONFIG["regime_multipliers"]

    # Match regime string to config key
    if "CRASH"     in regime_upper:               mult = multipliers["CRASH"]
    elif "BEAR"    in regime_upper and "WEAK" not in regime_upper: mult = multipliers["BEAR"]
    elif "WEAK"    in regime_upper and "BEAR" in regime_upper:     mult = multipliers["WEAK_BEAR"]
    elif "SIDEWAYS" in regime_upper:              mult = multipliers["SIDEWAYS"]
    elif "WEAK"    in regime_upper and "BULL" in regime_upper:     mult = multipliers["WEAK_BULL"]
    elif "STRONG"  in regime_upper and "BULL" in regime_upper:     mult = multipliers["STRONG_BULL"]
    elif "BULL"    in regime_upper:               mult = multipliers["BULL"]
    else:                                         mult = multipliers["UNKNOWN"]

    if   mult == 0.00: label = "NO new positions allowed"
    elif mult <= 0.25: label = f"Very cautious — {int(mult*100)}% of intended size"
    elif mult <= 0.50: label = f"Defensive sizing — {int(mult*100)}% of intended size"
    elif mult <= 0.75: label = f"Reduced sizing — {int(mult*100)}% of intended size"
    else:              label = "Full sizing allowed"

    return mult, str(regime), label


# ════════════════════════════════════════════════
# FEATURE 10 — MASTER RISK GATE
# THE single function every BUY path must call.
# ════════════════════════════════════════════════

def validate_portfolio_risk(
    stock_name,
    stock_symbol,
    bucket_name,
    proposed_trade_value,
    sector=None,
    regime=None,
    skip_correlation=False,
):
    """
    Master risk gate — run ALL checks before any BUY.

    This is the single approval function that protects the portfolio.
    Every BUY path (manual, scanner, autonomous loop) MUST call this
    before executing. If it returns approved=False, the trade does NOT happen.

    CHECKS RUN (in order — stops at first hard block):
      1. Daily loss limit      (hard block)
      2. Bucket drawdown       (hard block)
      3. Max deployment        (hard block)
      4. Regime gate           (hard block if BEAR/CRASH)
      5. Sector exposure       (soft warning + block if exceeded)
      6. Correlation risk      (soft warning + block if exceeded)

    Parameters:
      stock_name          : e.g. "RELIANCE"
      stock_symbol        : e.g. "RELIANCE.NS" (Yahoo Finance format)
      bucket_name         : "Long-Term" / "Swing" / "Intraday"
      proposed_trade_value: estimated ₹ value of the trade
      sector              : sector string — if None, looked up from watchlist
      regime              : regime string — if None, fetched automatically
      skip_correlation    : set True to skip correlation check (saves ~5 seconds)

    Returns dict:
      {
        approved        : True / False
        reasons         : [] (empty if approved)
        warnings        : [] (non-blocking issues)
        checks          : {check_name: {passed, detail}} — full audit trail
        regime          : what regime was used
        regime_mult     : position size multiplier from regime
        vol_multiplier  : position size multiplier from volatility
        final_size_mult : regime_mult × vol_multiplier (combined size adjustment)
      }
    """
    reasons  = []    # blocking failures
    warnings = []    # non-blocking observations
    checks   = {}    # audit trail of every check

    # ── Fetch sector from watchlist if not provided ──
    if sector is None and WATCHLIST_AVAILABLE:
        try:
            wl_df      = load_watchlist(active_only=False)
            sector_map = dict(zip(wl_df["Name"], wl_df["Sector"]))
            sector     = sector_map.get(stock_name, "Unknown")
        except Exception:
            sector = "Unknown"

    # ── Fetch regime if not provided ─────────────────
    if regime is None and REGIME_AVAILABLE:
        try:
            rd     = get_full_regime_analysis(period="1y")
            regime = rd.get("regime", "UNKNOWN")
        except Exception:
            regime = "UNKNOWN"

    # ────────────────────────────────────────────
    # CHECK 1: Daily loss limit
    # ────────────────────────────────────────────
    daily_ok, daily_pnl, daily_msg = check_daily_loss_limit()
    checks["daily_loss"] = {
        "passed": daily_ok,
        "detail": daily_msg,
        "pnl_pct": daily_pnl,
    }
    if not daily_ok:
        reasons.append(daily_msg)
        # Hard stop — no point running other checks
        return _build_result(False, reasons, warnings, checks, regime, 0, 0)

    # ────────────────────────────────────────────
    # CHECK 2: Bucket drawdown
    # ────────────────────────────────────────────
    dd_ok, dd_pct, dd_msg = check_bucket_drawdown(bucket_name)
    checks["bucket_drawdown"] = {
        "passed":    dd_ok,
        "detail":    dd_msg,
        "drawdown":  dd_pct,
        "bucket":    bucket_name,
    }
    if not dd_ok:
        reasons.append(dd_msg)
        return _build_result(False, reasons, warnings, checks, regime, 0, 0)

    # ────────────────────────────────────────────
    # CHECK 3: Max deployment
    # ────────────────────────────────────────────
    dep_ok, dep_pct, dep_msg = check_max_exposure(proposed_trade_value)
    checks["max_deployment"] = {
        "passed":     dep_ok,
        "detail":     dep_msg,
        "pct_after":  dep_pct,
    }
    if not dep_ok:
        reasons.append(dep_msg)
        return _build_result(False, reasons, warnings, checks, regime, 0, 0)

    # ────────────────────────────────────────────
    # CHECK 4: Regime gate
    # ────────────────────────────────────────────
    regime_mult, regime_used, regime_label = get_regime_position_multiplier(regime)
    checks["regime"] = {
        "passed":     regime_mult > 0,
        "detail":     regime_label,
        "multiplier": regime_mult,
        "regime":     regime_used,
    }
    if regime_mult == 0:
        reasons.append(
            f"Regime gate blocked: {regime_used} — {regime_label}. "
            "No new long positions in bear/crash markets."
        )
        return _build_result(False, reasons, warnings, checks, regime, regime_mult, 0)

    if regime_mult < 1.0:
        warnings.append(
            f"Regime sizing: position will be reduced to "
            f"{int(regime_mult*100)}% of intended size ({regime_used})"
        )

    # ────────────────────────────────────────────
    # CHECK 5: Sector exposure
    # ────────────────────────────────────────────
    sec_ok, sec_pct, sec_msg = check_sector_exposure(sector, proposed_trade_value)
    checks["sector_exposure"] = {
        "passed":     sec_ok,
        "detail":     sec_msg,
        "sector":     sector,
        "pct_after":  sec_pct,
    }
    if not sec_ok:
        reasons.append(sec_msg)
        # Don't hard-stop here — record it but continue to show full picture
    elif sec_pct > 20:
        warnings.append(f"{sector} sector would be at {sec_pct}% (limit: 30%)")

    # ────────────────────────────────────────────
    # CHECK 6: Correlation risk (optional — slowest check)
    # ────────────────────────────────────────────
    if skip_correlation:
        checks["correlation"] = {
            "passed": True,
            "detail": "Skipped (skip_correlation=True)",
            "count":  0,
        }
    else:
        corr_ok, corr_count, corr_msg = check_correlation_risk(stock_symbol)
        checks["correlation"] = {
            "passed": corr_ok,
            "detail": corr_msg,
            "count":  corr_count,
        }
        if not corr_ok:
            reasons.append(corr_msg)
        elif corr_count > 0:
            warnings.append(
                f"Correlation note: {corr_count} existing holding(s) are correlated "
                f"with {stock_name} — still within limit"
            )

    # ────────────────────────────────────────────
    # VOLATILITY SIZE ADJUSTMENT (not a block — just info)
    # ────────────────────────────────────────────
    vol_mult, atr_pct, vol_label = get_volatility_multiplier(stock_symbol)
    checks["volatility"] = {
        "passed":    True,      # Never blocks — only adjusts size
        "detail":    vol_label,
        "atr_pct":   atr_pct,
        "multiplier":vol_mult,
    }
    if vol_mult < 1.0:
        warnings.append(
            f"Volatility adjustment: {vol_label}"
        )

    # ────────────────────────────────────────────
    # FINAL RESULT
    # ────────────────────────────────────────────
    approved = len(reasons) == 0
    return _build_result(
        approved, reasons, warnings, checks, regime_used, regime_mult, vol_mult
    )


def _build_result(approved, reasons, warnings, checks, regime, regime_mult, vol_mult):
    """Internal helper to build the final result dict."""
    final_mult = round(regime_mult * vol_mult, 2) if (regime_mult and vol_mult) else 0.0

    return {
        "approved":        approved,
        "reasons":         reasons,
        "warnings":        warnings,
        "checks":          checks,
        "regime":          regime,
        "regime_mult":     regime_mult,
        "vol_multiplier":  vol_mult,
        "final_size_mult": final_mult,
        "summary":         (
            "✅ All risk checks passed"
            if approved else
            f"🛑 Blocked: {reasons[0]}" if reasons else "⚠️ Unknown"
        ),
    }


# ════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS — for dashboard display
# ════════════════════════════════════════════════

def get_risk_dashboard_data(regime=None):
    """
    Get all risk data formatted for the dashboard.
    Bundles portfolio summary + bucket-level checks in one call.
    Called by app.py Tab 9 (Portfolio Buckets) risk panel.
    """
    summary = get_portfolio_risk_summary(regime)

    bucket_status = {}
    for bname in (BUCKET_CONFIG.keys() if CAPITAL_ENGINE_AVAILABLE else []):
        dd_ok, dd_pct, dd_msg = check_bucket_drawdown(bname)
        can_add, open_c, max_p = (True, 0, 5)
        if CAPITAL_ENGINE_AVAILABLE:
            from portfolio.capital_engine import check_position_limit
            can_add, open_c, max_p = check_position_limit(bname)

        bucket_status[bname] = {
            "drawdown_ok":    dd_ok,
            "drawdown_pct":   dd_pct,
            "drawdown_msg":   dd_msg,
            "positions_ok":   can_add,
            "open_positions": open_c,
            "max_positions":  max_p,
        }

    return {
        "portfolio_summary": summary,
        "bucket_status":     bucket_status,
        "timestamp":         datetime.now().strftime('%d %b %Y %H:%M:%S'),
    }


def format_risk_level(level):
    """Return an emoji + color label for a risk level string."""
    mapping = {
        "LOW":      "🟢 LOW",
        "NORMAL":   "🟡 NORMAL",
        "ELEVATED": "🟠 ELEVATED",
        "HIGH":     "🔴 HIGH",
        "CRITICAL": "🚨 CRITICAL",
    }
    return mapping.get(str(level).upper(), f"❓ {level}")
