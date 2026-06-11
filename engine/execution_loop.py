# ================================================
# FILE: engine/execution_loop.py
# PURPOSE: Autonomous Execution Loop — Milestone 26
#
# WHAT THIS DOES:
#   Runs automatically every N minutes during market hours.
#   On each cycle it:
#     1. Checks market hours + regime (safety gate)
#     2. Scans all watchlist stocks for new opportunities
#     3. Evaluates every live position for exits
#     4. Places paper trades via the bucket system
#     5. Logs EVERY decision (including NO-TRADE) with reasons
#
# SAFETY DESIGN — NON-NEGOTIABLE RULES:
#   - BEAR market  → zero new BUY orders
#   - Daily loss > 5% → halt ALL trading for the day
#   - Cooldown stocks → skip completely (no re-entry)
#   - Score below bucket minimum → NO-TRADE + reason logged
#   - Already holding stock in bucket → skip (no double buy)
#   - Stop loss hit → SELL immediately, no override
#   - Idempotent: safe to call multiple times, no duplicates
#
# HOW TO RUN:
#   Option A — Streamlit dashboard (Tab 11 "Auto Pilot")
#              Start / Pause / Stop buttons trigger this file.
#              Loop runs via st.experimental_run_on_every_rerun
#              or via a background thread (controlled by loop_state.py)
#
#   Option B — Run directly from terminal (laptop testing):
#              python engine/execution_loop.py
#              Ctrl+C to stop.
#
# CONNECTIONS:
#   Reads from:
#     strategies/performance_scanner.py  → scan_all_stocks()
#     strategies/market_regime.py        → get_full_regime_analysis()
#     portfolio/capital_engine.py        → bucket_buy(), bucket_sell()
#     portfolio/position_manager.py      → update_position_price()
#     engine/loop_state.py               → status, logging
#
#   Writes to:
#     Supabase (via capital_engine + position_manager)
#     logs/loop_decisions.csv (via loop_state)
#     logs/loop_state.json    (via loop_state)
# ================================================

import os
import sys
import time
import traceback
from datetime import datetime, timedelta

# ── Path fix — works from any working directory ───
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── Internal imports ──────────────────────────────
from engine.loop_state import (
    load_loop_state,
    save_loop_state,
    update_after_run,
    reset_daily_counters,
    log_decision,
    is_market_open,
    is_trading_day,
    get_market_status,
    STATUS_RUNNING,
    STATUS_PAUSED,
    STATUS_STOPPED,
)

# ── Trading system imports ────────────────────────
from strategies.watchlist_manager   import get_watchlist_dict
from strategies.market_regime       import get_full_regime_analysis
from strategies.indicators          import analyze_stock
from strategies.ema_strategy        import calculate_ema_signals
from strategies.bollinger_strategy  import analyze_bollinger
from strategies.macd_strategy       import analyze_macd
from strategies.combined_signal     import build_combined_summary
from strategies.scoring_engine      import build_composite_score
from strategies.fundamental_engine  import get_fundamental_score_only

from portfolio.capital_engine       import (
    bucket_buy,
    bucket_sell,
    check_position_limit,
    get_bucket_available_cash,
    suggest_bucket,
    BUCKET_CONFIG,
    get_open_positions_by_bucket,
    get_portfolio_totals,
)
from portfolio.position_manager     import (
    get_live_positions,
    update_position_price,
    is_in_cooldown,
    expire_cooldowns,
    load_lifecycle,
)

from strategies.orchestrator import orchestrate_opportunity, DECISION_ACCEPT, DECISION_REVIEW

import yfinance as yf
import pandas as pd


# ════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════

# Daily loss limit — halt all new BUYs if portfolio P&L
# drops below this % of total starting capital
DAILY_LOSS_HALT_PCT = -5.0    # -5% = halt

# Minimum composite score to even consider entering
# (each bucket also has its own higher threshold)
ABSOLUTE_MIN_SCORE = 50

# How many days of price data to fetch for indicator calculation
INDICATOR_PERIOD = "60d"


# ════════════════════════════════════════════════
# PRICE FETCHER
# Fast single-stock price fetch for exit monitoring
# ════════════════════════════════════════════════

def _fetch_latest_price(symbol: str) -> float | None:
    """
    Fetch the most recent closing price for one stock.
    Returns None if fetch fails — caller handles gracefully.
    """
    try:
        data = yf.download(
            tickers=symbol,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if data.empty:
            return None
        data.columns = [col[0] for col in data.columns]
        data = data.dropna(subset=["Close"])
        if data.empty:
            return None
        return round(float(data["Close"].iloc[-1]), 2)
    except Exception:
        return None


def _fetch_stock_data(symbol: str) -> pd.DataFrame | None:
    """
    Fetch 60 days of daily OHLCV data for one stock.
    Returns None if fetch fails.
    """
    try:
        data = yf.download(
            tickers=symbol,
            period=INDICATOR_PERIOD,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if data.empty:
            return None
        data.columns = [col[0] for col in data.columns]
        data = data.dropna(subset=["Close"])
        data = data[data["Close"] > 0]
        if len(data) < 10:    # Need at least 10 rows for indicators
            return None
        return data
    except Exception:
        return None


# ════════════════════════════════════════════════
# SIGNAL ANALYSER
# Run all 4 strategies + composite score for one stock
# ════════════════════════════════════════════════

def _analyse_stock_signals(
    stock_name: str,
    symbol: str,
    data: pd.DataFrame,
    regime: str,
) -> dict | None:
    """
    Run the full signal pipeline on one stock.
    Returns a result dict with score, signal, votes.
    Returns None if analysis fails.

    This is a lightweight version of what the Scanner tab does —
    same logic, but called per-stock in the loop.
    """
    try:
        analyzed   = analyze_stock(data.copy())
        ema_data   = calculate_ema_signals(data.copy())
        bb_data    = analyze_bollinger(data.copy())
        macd_data  = analyze_macd(data.copy())

        latest_ma   = analyzed.iloc[-1]
        latest_ema  = ema_data.iloc[-1]
        latest_bb   = bb_data.iloc[-1]
        latest_macd = macd_data.iloc[-1]

        combined = build_combined_summary(
            ma_signal   = latest_ma["Signal"],
            ema_signal  = latest_ema["EMA_Signal"],
            bb_signal   = latest_bb["BB_Signal"],
            macd_signal = latest_macd["MACD_Crossover"],
        )

        # Extract safe float values for composite score
        def sf(val):
            try:
                v = float(val)
                return None if pd.isna(v) else v
            except Exception:
                return None

        s_close = sf(latest_ma["Close"])
        s_ma20  = sf(latest_ma["MA20"])
        s_rsi   = sf(latest_ma["RSI"])
        s_ema9  = sf(latest_ema["EMA9"])
        s_ema21 = sf(latest_ema["EMA21"])
        s_macd  = sf(latest_macd["MACD"])
        s_msig  = sf(latest_macd["MACD_Signal"])
        s_mhist = sf(latest_macd["MACD_Hist"])
        s_bbpct = sf(latest_bb["BB_Pct"])
        s_bbsig = latest_bb["BB_Signal"]

        if s_close is None:
            return None

        votes = {
            "buy":  combined["Strategies Buy"],
            "sell": combined["Strategies Sell"],
            "hold": combined["Strategies Hold"],
        }

        # Fundamental score (cached or neutral)
        try:
            fund_score = get_fundamental_score_only(symbol)
        except Exception:
            fund_score = 50

        score_result = build_composite_score(
            stock_name            = stock_name,
            latest_close          = s_close,
            ma20                  = s_ma20,
            rsi                   = s_rsi,
            ema9                  = s_ema9,
            ema21                 = s_ema21,
            macd                  = s_macd,
            macd_signal           = s_msig,
            macd_hist             = s_mhist,
            bb_pct                = s_bbpct,
            bb_signal             = s_bbsig,
            combined_votes        = votes,
            combined_weighted_score = combined["Score"],
            regime                = regime,
            rs_score              = None,
            fundamental_score     = fund_score,
            sentiment_score       = None,    # Skip in loop — too slow
        )

        return {
            "stock":          stock_name,
            "symbol":         symbol,
            "price":          s_close,
            "composite_score":score_result["Composite Score"],
            "action":         score_result["Action"],
            "final_signal":   combined["Final Signal"],
            "buy_votes":      combined["Strategies Buy"],
            "sell_votes":     combined["Strategies Sell"],
            "confidence":     score_result["Confidence"],
            "position_size":  score_result["Position Size"],
            "regime":         regime,
        }

    except Exception as e:
        print(f"⚠️ Signal analysis failed for {stock_name}: {e}")
        return None


# ════════════════════════════════════════════════
# SAFETY GATE
# All safety checks run BEFORE any BUY decision
# ════════════════════════════════════════════════

def _check_portfolio_safety(regime: str) -> tuple[bool, str]:
    """
    Portfolio-level safety checks.
    If ANY check fails → return (False, reason).
    Only when ALL pass → return (True, "").

    Checks:
      1. Bear market  → no new buys
      2. Daily loss   → halt if portfolio down > DAILY_LOSS_HALT_PCT
    """
    # ── 1. Bear market ─────────────────────────────
    if "BEAR" in str(regime).upper() and "WEAK" not in str(regime).upper():
        return False, (
            f"BEAR market detected ({regime}). "
            "No new BUY orders — capital protection mode."
        )

    # ── 2. Daily loss limit ────────────────────────
    try:
        totals  = get_portfolio_totals()
        pnl_pct = totals.get("total_return_pct", 0.0)
        if pnl_pct <= DAILY_LOSS_HALT_PCT:
            return False, (
                f"Daily loss limit hit ({pnl_pct:.1f}% < {DAILY_LOSS_HALT_PCT}%). "
                "All new BUY orders halted for the day."
            )
    except Exception:
        pass    # If we can't check, don't block trading

    return True, ""


def _is_ok_to_buy(
    stock_name: str,
    bucket_name: str,
    score: int,
    regime: str,
) -> tuple[bool, str]:
    """
    Stock-level safety checks for a specific BUY candidate.
    Returns (approved: bool, reason: str).

    Checks (in order):
      1. Portfolio safety (regime + daily loss)
      2. Cooldown — was this stock recently stopped out?
      3. Already holding this stock in this bucket?
      4. Bucket position limit
      5. Score threshold for this bucket
      6. Sufficient cash in bucket
    """
    # 1. Portfolio safety
    safe, reason = _check_portfolio_safety(regime)
    if not safe:
        return False, reason

    # 2. Cooldown check
    in_cd, until = is_in_cooldown(stock_name, bucket_name)
    if in_cd:
        return False, f"In cooldown until {until} after previous stop loss."

    # 3. Already holding
    open_positions = get_open_positions_by_bucket(bucket_name)
    if stock_name in open_positions:
        return False, f"Already holding {stock_name} in {bucket_name} bucket."

    # 4. Position limit
    can_trade, open_count, max_pos = check_position_limit(bucket_name)
    if not can_trade:
        return False, (
            f"{bucket_name} bucket full ({open_count}/{max_pos} positions). "
            "Sell something first."
        )

    # 5. Score threshold
    cfg       = BUCKET_CONFIG.get(bucket_name, {})
    min_score = cfg.get("min_score", 60)
    if score < min_score:
        return False, (
            f"Score {score}/100 below {bucket_name} minimum ({min_score}/100)."
        )

    # 6. Cash check (quick sanity check — bucket_buy does the real calc)
    avail = get_bucket_available_cash(bucket_name)
    if avail <= 0:
        return False, f"No cash available in {bucket_name} bucket."

    # 7. Portfolio Risk Gate (Milestone 30)
    try:
        from risk.portfolio_risk import validate_portfolio_risk
        from portfolio.capital_engine import get_max_position_size
        from strategies.watchlist_manager import get_watchlist_dict
        wl      = get_watchlist_dict()
        sym     = wl.get(stock_name, stock_name + ".NS")
        qty, spend, _ = get_max_position_size(bucket_name, 0)   # 0 = just estimate
        # Estimate trade value using bucket's max position size
        avail = get_bucket_available_cash(bucket_name)
        cfg   = BUCKET_CONFIG.get(bucket_name, {})
        from portfolio.capital_engine import load_bucket_state
        st    = load_bucket_state()
        start = st.get(bucket_name, {}).get("Starting_Capital", avail)
        estimated_value = round(start * cfg.get("max_position_pct", 0.10), 2)

        risk_result = validate_portfolio_risk(
            stock_name          = stock_name,
            stock_symbol        = sym,
            bucket_name         = bucket_name,
            proposed_trade_value= estimated_value,
            regime              = regime,
            skip_correlation    = True,   # Skip in loop — too slow per-stock
        )
        if not risk_result["approved"]:
            return False, risk_result["summary"]
    except Exception as e:
        print(f"⚠️ Portfolio risk check skipped: {e}")

    return True, ""

    return True, ""


# ════════════════════════════════════════════════
# BUY SCANNER
# Scans all watchlist stocks, decides what to buy
# and in which bucket
# ════════════════════════════════════════════════

def _run_buy_scan(watchlist: dict, regime: str) -> list[dict]:
    """
    Scan all watchlist stocks for new BUY opportunities.
    Returns a list of executed trade result dicts.

    HOW IT WORKS:
      For each stock in watchlist:
        1. Fetch price data
        2. Run all indicators + composite score
        3. Ask suggest_bucket() which bucket fits
        4. Run safety checks
        5. Execute BUY if approved
        6. Log decision (BUY or NO-TRADE) with reasons

    Returns list of all decisions made this cycle.
    """
    decisions = []

    for stock_name, symbol in watchlist.items():

        # ── Fetch data ────────────────────────────
        data = _fetch_stock_data(symbol)
        if data is None:
            log_decision(
                stock=stock_name, bucket="—",
                decision="NO-TRADE",
                score=0, signal="—",
                price=0, regime=regime,
                reason="Could not fetch price data — skipping this cycle.",
            )
            continue

        # ── Analyse signals ───────────────────────
        result = _analyse_stock_signals(stock_name, symbol, data, regime)
        if result is None:
            continue    # Analysis failed — silent skip

        score       = result["composite_score"]
        final_signal= result["final_signal"]
        buy_votes   = result["buy_votes"]
        price       = result["price"]

        # ── Skip if score is too low to even consider ─
        if score < ABSOLUTE_MIN_SCORE:
            log_decision(
                stock=stock_name, bucket="—",
                decision="NO-TRADE",
                score=score, signal=final_signal,
                price=price, regime=regime,
                reason=(
                    f"Score {score}/100 below minimum {ABSOLUTE_MIN_SCORE}/100. "
                    "No bucket would accept this."
                ),
            )
            decisions.append({
                "stock": stock_name, "decision": "NO-TRADE",
                "reason": f"Score {score} too low"
            })
            continue

        # ── Skip if signal is not bullish ─────────
        if "BUY" not in str(final_signal).upper():
            log_decision(
                stock=stock_name, bucket="—",
                decision="NO-TRADE",
                score=score, signal=final_signal,
                price=price, regime=regime,
                reason=(
                    f"Signal is {final_signal} — not a BUY. "
                    "No action taken."
                ),
            )
            decisions.append({
                "stock": stock_name, "decision": "NO-TRADE",
                "reason": f"Signal not bullish: {final_signal}"
            })
            continue

        # ── Orchestrate: route + score + validate ──
        orch_result = orchestrate_opportunity(
            stock_name        = stock_name,
            symbol            = symbol,
            composite_score   = score,
            individual_scores = result.get("individual_scores", {}),
            combined_votes    = {
                "buy":  result["buy_votes"],
                "sell": result["sell_votes"],
                "hold": 4 - result["buy_votes"] - result["sell_votes"],
            },
            final_signal      = final_signal,
            regime            = regime,
            log_decision      = True,
        )

        target_bucket = orch_result["bucket"]

        if orch_result["decision"] not in (DECISION_ACCEPT, DECISION_REVIEW):
            log_decision(
                stock=stock_name, bucket=target_bucket or "—",
                decision="NO-TRADE",
                score=score, signal=final_signal,
                price=price, regime=regime,
                reason=orch_result["summary"],
            )
            decisions.append({
                "stock": stock_name, "decision": "NO-TRADE",
                "reason": orch_result["summary"],
            })
            continue

        # REVIEW decisions still proceed but get flagged in the log
        if orch_result["decision"] == DECISION_REVIEW:
            print(f"  🟡 REVIEW: {stock_name} — {orch_result['summary']}")

        if not approved:
            log_decision(
                stock=stock_name, bucket=target_bucket,
                decision="NO-TRADE",
                score=score, signal=final_signal,
                price=price, regime=regime,
                reason=reject_reason,
            )
            decisions.append({
                "stock": stock_name, "decision": "NO-TRADE",
                "reason": reject_reason
            })
            continue

        # ── EXECUTE BUY ───────────────────────────
        buy_result = bucket_buy(
            bucket_name     = target_bucket,
            stock_name      = stock_name,
            price           = price,
            composite_score = score,
        )

        if buy_result["status"] == "EXECUTED":
            reason_text = (
                f"Score {score}/100 | Signal: {final_signal} | "
                f"{buy_votes}/4 strategies agree | "
                f"Regime: {regime} | "
                f"Bought {buy_result['quantity']} shares @ ₹{price} | "
                f"Cash left in {target_bucket}: ₹{buy_result['cash_left']:,.0f}"
            )
            log_decision(
                stock=stock_name, bucket=target_bucket,
                decision="BUY",
                score=score, signal=final_signal,
                price=price, regime=regime,
                reason=reason_text,
            )
            decisions.append({
                "stock": stock_name, "decision": "BUY",
                "bucket": target_bucket, "price": price,
                "score": score, "quantity": buy_result["quantity"],
            })
            print(
                f"  ✅ BUY: {stock_name} → {target_bucket} | "
                f"Score={score} | ₹{price} x {buy_result['quantity']} shares"
            )

        else:
            log_decision(
                stock=stock_name, bucket=target_bucket,
                decision="NO-TRADE",
                score=score, signal=final_signal,
                price=price, regime=regime,
                reason=f"BUY rejected by bucket engine: {buy_result.get('reason','')}",
            )
            decisions.append({
                "stock": stock_name, "decision": "NO-TRADE",
                "reason": buy_result.get("reason", "")
            })

    return decisions


# ════════════════════════════════════════════════
# EXIT MONITOR
# Checks every live position for stop loss, target,
# or trailing stop. Sells immediately if triggered.
# ════════════════════════════════════════════════

def _run_exit_monitor(watchlist: dict, regime: str) -> list[dict]:
    """
    Check all live positions for exits.
    Returns list of decisions made.

    Exit rules (checked in priority order):
      1. Hard stop loss  → SELL_STOP   — always execute
      2. Profit target   → SELL_TARGET — always execute
      3. Trailing stop   → SELL_TRAIL  — execute if in TRAILING state
      4. Strategy exit   → SELL_SIGNAL — if signal flipped to SELL
      5. Time-based exit → SELL_TIME   — if max holding days exceeded

    After a stop loss exit, position enters COOLDOWN automatically
    (handled by position_manager.py's mark_exited).
    """
    decisions = []
    live_df   = get_live_positions()

    if live_df.empty:
        return decisions

    for _, pos in live_df.iterrows():
        stock    = str(pos["stock"])
        pos_id   = str(pos["position_id"])
        bucket   = str(pos["bucket"])
        symbol   = watchlist.get(stock, stock + ".NS")

        # ── Fetch latest price ─────────────────────
        current_price = _fetch_latest_price(symbol)
        if current_price is None:
            print(f"  ⚠️ Could not fetch price for {stock} — skipping exit check")
            continue

        # ── Run lifecycle price update ─────────────
        # This is the core of Milestone 25B — the lifecycle
        # engine calculates stops, targets, and trailing stops
        # and tells us what action to take.
        result = update_position_price(pos_id, current_price)
        action = result.get("action", "HOLD")

        if action in ("HOLD", "NO_ACTION"):
            continue    # Nothing to do — position is fine

        pnl_pct    = result.get("pnl_pct",    0)
        trail_stop = result.get("trail_stop",  "—")
        reason_txt = result.get("reason",      "")

        # ── SELL decisions ─────────────────────────
        if action in ("SELL_STOP", "SELL_TARGET", "SELL_TRAIL"):

            sell_result = bucket_sell(
                bucket_name = bucket,
                stock_name  = stock,
                price       = current_price,
            )

            if sell_result["status"] == "EXECUTED":
                actual_pnl = sell_result.get("pnl", 0)
                pnl_pct    = sell_result.get("pnl_pct", pnl_pct)
                log_decision(
                    stock=stock, bucket=bucket,
                    decision="SELL",
                    score=0, signal="—",
                    price=current_price,
                    regime=regime,
                    reason=reason_txt,
                    exit_reason=action,
                )
                decisions.append({
                    "stock":    stock,
                    "decision": "SELL",
                    "action":   action,
                    "bucket":   bucket,
                    "price":    current_price,
                    "pnl_pct":  pnl_pct,
                    "pnl":      sell_result.get("pnl", 0),
                })
                print(
                    f"  {'✅' if actual_pnl >= 0 else '🔴'} SELL [{action}]: "
                    f"{stock} ← {bucket} | "
                    f"₹{current_price} | P&L: {pnl_pct:+.1f}%"
                )
            else:
                print(
                    f"  ⚠️ SELL failed for {stock}: "
                    f"{sell_result.get('reason','')}"
                )

        # ── Informational actions ──────────────────
        elif action == "TRAIL_ACTIVATED":
            log_decision(
                stock=stock, bucket=bucket,
                decision="HOLD",
                score=0, signal="TRAILING",
                price=current_price,
                regime=regime,
                reason=reason_txt,
                exit_reason="TRAIL_ACTIVATED",
            )
            print(
                f"  🔔 TRAIL ACTIVATED: {stock} ({bucket}) | "
                f"Trail stop ₹{trail_stop}"
            )

        elif action == "PARTIAL_EXIT":
            # Suggest but don't auto-execute partial exits yet
            # Automation of partial exits comes in Milestone 27
            log_decision(
                stock=stock, bucket=bucket,
                decision="PARTIAL_EXIT_SUGGESTED",
                score=0, signal="PARTIAL",
                price=current_price,
                regime=regime,
                reason=reason_txt,
            )
            print(
                f"  📊 PARTIAL EXIT SUGGESTED: {stock} ({bucket}) | "
                f"Gain {pnl_pct:+.1f}% — consider selling 50%"
            )

    return decisions


# ════════════════════════════════════════════════
# SINGLE CYCLE — one full run of the loop
# ════════════════════════════════════════════════

def run_one_cycle(
    force: bool = False,
    scan_only: bool = False,
) -> dict:
    """
    Execute one complete cycle of the autonomous loop.

    Parameters:
      force     : If True, runs even outside market hours (for testing)
      scan_only : If True, analyses but does NOT execute any trades

    Returns a summary dict with what happened this cycle.
    Always safe to call — never crashes the app.

    THE CYCLE (in order):
      PRE-CHECK  → market hours, loop status, safety gates
      STEP 1     → expire old cooldowns
      STEP 2     → fetch market regime (NIFTY-based)
      STEP 3     → portfolio safety check
      STEP 4     → exit monitor (sell if stop/target hit)
      STEP 5     → buy scanner (find new opportunities)
      POST-RUN   → update loop state, calculate next run time
    """
    cycle_start = datetime.now()
    summary = {
        "cycle_time":  cycle_start.strftime('%Y-%m-%d %H:%M:%S'),
        "ran":         False,
        "skipped":     False,
        "skip_reason": "",
        "regime":      "UNKNOWN",
        "buys":        0,
        "sells":       0,
        "no_trades":   0,
        "decisions":   [],
        "error":       None,
    }

    try:
        # ── PRE-CHECK: market hours ────────────────
        if not force and not is_market_open():
            status = get_market_status()
            summary["skipped"]     = True
            summary["skip_reason"] = f"Market {status['status']} — loop waiting"
            return summary

        # ── PRE-CHECK: loop status ─────────────────
        state = load_loop_state()
        if not force and state.get("status") != STATUS_RUNNING:
            summary["skipped"]     = True
            summary["skip_reason"] = f"Loop is {state.get('status')} — not running"
            return summary

        print(f"\n{'='*55}")
        print(f"🤖 Execution Loop Cycle — {cycle_start.strftime('%H:%M:%S IST')}")
        print(f"{'='*55}")

        # ── Load watchlist ─────────────────────────
        watchlist = get_watchlist_dict()
        if not watchlist:
            summary["error"] = "Watchlist is empty — nothing to scan"
            return summary

        # ── STEP 1: Expire cooldowns ───────────────
        expired = expire_cooldowns()
        if expired:
            print(f"✅ Cooldowns expired: {', '.join(expired)}")

        # ── STEP 2: Market regime ──────────────────
        print("📡 Fetching market regime...")
        try:
            regime_data = get_full_regime_analysis(period="1y")
            regime      = regime_data.get("regime", "UNKNOWN ❓")
        except Exception:
            regime = "UNKNOWN ❓"

        summary["regime"] = regime
        print(f"🌡️ Regime: {regime}")

        # ── STEP 3: Portfolio safety ───────────────
        safe, halt_reason = _check_portfolio_safety(regime)
        if not safe:
            print(f"🛑 Safety gate: {halt_reason}")
            log_decision(
                stock="PORTFOLIO", bucket="ALL",
                decision="HALTED",
                score=0, signal="—",
                price=0, regime=regime,
                reason=halt_reason,
            )
            summary["skipped"]     = True
            summary["skip_reason"] = halt_reason
            # Still run exit monitor even when buys are halted
            # (we still need to protect existing positions)

        # ── STEP 4: Exit monitor ───────────────────
        print(f"\n📋 Monitoring live positions for exits...")
        exit_decisions = _run_exit_monitor(watchlist, regime)

        sell_count = sum(1 for d in exit_decisions if d.get("decision") == "SELL")
        total_pnl  = sum(d.get("pnl", 0) for d in exit_decisions)
        summary["sells"]     = sell_count
        summary["decisions"].extend(exit_decisions)

        # ── STEP 5: Buy scanner (if safe) ─────────
        buy_decisions = []
        if safe and not scan_only:
            print(f"\n🔍 Scanning {len(watchlist)} stocks for entries...")
            buy_decisions = _run_buy_scan(watchlist, regime)
            buy_count  = sum(1 for d in buy_decisions if d.get("decision") == "BUY")
            no_trade_c = sum(1 for d in buy_decisions if d.get("decision") == "NO-TRADE")
            summary["buys"]      = buy_count
            summary["no_trades"] = no_trade_c
            summary["decisions"].extend(buy_decisions)

        elif scan_only:
            print("⚠️ Scan-only mode — no trades executed")

        # ── POST-RUN: Update loop state ────────────
        loop_state  = load_loop_state()
        interval    = loop_state.get("interval_minutes", 15)
        next_run    = (datetime.now(IST) + timedelta(minutes=interval)).strftime(
            '%Y-%m-%d %H:%M:%S'
        )
        update_after_run(
            decisions_made = len(summary["decisions"]),
            buys           = summary["buys"],
            sells          = summary["sells"],
            pnl_delta      = total_pnl,
            next_run_time  = next_run,
        )

        cycle_secs    = (datetime.now() - cycle_start).total_seconds()
        summary["ran"] = True
        print(
            f"\n✅ Cycle complete in {cycle_secs:.1f}s | "
            f"Buys: {summary['buys']} | Sells: {summary['sells']} | "
            f"No-trades: {summary['no_trades']} | Regime: {regime}"
        )

    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        summary["error"] = err_msg
        print(f"❌ Cycle error: {err_msg}")

        # Update error count in loop state
        state = load_loop_state()
        state["error_count"] = state.get("error_count", 0) + 1
        state["last_error"]  = str(e)
        save_loop_state(state)

        # Auto-pause after 3 consecutive errors (safety)
        if state.get("error_count", 0) >= 3:
            state["status"] = STATUS_PAUSED
            save_loop_state(state)
            print("⚠️ Loop auto-paused after 3 consecutive errors.")

    return summary


# ════════════════════════════════════════════════
# CONTINUOUS RUNNER
# Called when running this file directly from terminal
# ════════════════════════════════════════════════

def run_continuous():
    """
    Run the execution loop continuously.
    Checks loop state every minute and runs a cycle
    when the interval has elapsed.

    Designed for terminal use during testing:
      python engine/execution_loop.py

    On Streamlit Cloud, the loop is triggered differently
    (via the dashboard's manual RUN NOW button or
    Streamlit's background thread support).
    """
    print("\n🤖 Autonomous Execution Loop — Starting")
    print("   Press Ctrl+C to stop\n")

    last_daily_reset = None

    while True:
        try:
            state    = load_loop_state()
            status   = state.get("status", STATUS_STOPPED)
            interval = state.get("interval_minutes", 15)

            # Daily reset at 9:00 AM IST
            now_date = datetime.now().date()
            now_ist = datetime.now(IST)
            now_date = now_ist.date()     # use IST date, not local date
            if last_daily_reset != now_date and is_trading_day():
                if now_ist.time() >= dtime(9, 0):
                    reset_daily_counters()
                    last_daily_reset = now_date
                    print("✅ Daily counters reset for new trading day")

            if status == STATUS_STOPPED:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    "Loop STOPPED — waiting. "
                    "Start via dashboard or set status to RUNNING."
                )
                time.sleep(60)
                continue

            if status == STATUS_PAUSED:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    "Loop PAUSED — waiting..."
                )
                time.sleep(60)
                continue

            # ── Running — check if interval has elapsed ──
            last_run   = state.get("last_run")
            should_run = False

            if last_run is None:
                should_run = True
            else:
                try:
                    last_dt    = datetime.strptime(last_run, '%Y-%m-%d %H:%M:%S')
                    elapsed    = (datetime.now() - last_dt).total_seconds() / 60
                    should_run = elapsed >= interval
                except Exception:
                    should_run = True

            if should_run:
                run_one_cycle()
            else:
                elapsed_min = (datetime.now() - datetime.strptime(
                    last_run, '%Y-%m-%d %H:%M:%S'
                )).total_seconds() / 60
                remaining   = round(interval - elapsed_min, 1)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Next run in {remaining:.1f} min..."
                )

            time.sleep(60)   # Check every 60 seconds

        except KeyboardInterrupt:
            print("\n\n⛔ Loop stopped by user (Ctrl+C)")
            break
        except Exception as e:
            print(f"❌ Outer loop error: {e}")
            time.sleep(60)


# ════════════════════════════════════════════════
# ENTRY POINT — terminal testing
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Trading OS — Autonomous Execution Loop"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle and exit (good for testing)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run even outside market hours"
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Analyse but do not execute any trades"
    )
    args = parser.parse_args()

    if args.once or args.force or args.scan_only:
        print("🤖 Running one cycle...")
        result = run_one_cycle(force=args.force, scan_only=args.scan_only)
        print(f"\n📋 Result: {result}")
    else:
        run_continuous()
