# ================================================
# FILE: engine/loop_state.py
# PURPOSE: Persistent state for the Autonomous Execution Loop
#
# Tracks:
#   - Loop status     : RUNNING / PAUSED / STOPPED
#   - Last run time   : when the loop last ran
#   - Next run time   : when it will run again
#   - Decision log    : every BUY / SELL / NO-TRADE with reasons
#   - Today's stats   : trades taken, P&L, decisions made
#
# STORAGE:
#   Primary  : Supabase bucket_state table
#              (uses special prefix "__loop__" rows to avoid
#               creating a new table — reuses existing schema)
#   Fallback : logs/loop_state.json (local file)
#
# WHY A SEPARATE FILE?
#   The loop state needs to survive a Streamlit Cloud restart.
#   The dashboard (app.py) reads it to show the status panel.
#   The execution loop (execution_loop.py) writes it on every run.
#   Keeping state separate from logic makes both files simpler.
# ================================================

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── File path for local fallback ──────────────────
BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR        = os.path.join(BASE_DIR, "logs")
LOOP_STATE_FILE = os.path.join(LOGS_DIR, "loop_state.json")
LOOP_LOG_FILE   = os.path.join(LOGS_DIR, "loop_decisions.csv")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Valid loop statuses ───────────────────────────
STATUS_RUNNING = "RUNNING"
STATUS_PAUSED  = "PAUSED"
STATUS_STOPPED = "STOPPED"

# ── Default state ─────────────────────────────────
DEFAULT_STATE = {
    "status":          STATUS_STOPPED,
    "interval_minutes":15,
    "last_run":        None,
    "next_run":        None,
    "runs_today":      0,
    "decisions_today": 0,
    "buys_today":      0,
    "sells_today":     0,
    "pnl_today":       0.0,
    "last_updated":    None,
    "error_count":     0,
    "last_error":      None,
}


# ════════════════════════════════════════════════
# LOAD AND SAVE
# ════════════════════════════════════════════════

def load_loop_state() -> dict:
    """
    Load the current loop state.
    Returns a dict — always safe to call, never crashes.
    """
    # Try local JSON file
    if os.path.exists(LOOP_STATE_FILE):
        try:
            with open(LOOP_STATE_FILE, "r") as f:
                state = json.load(f)
            # Fill any missing keys with defaults
            for key, default_val in DEFAULT_STATE.items():
                if key not in state:
                    state[key] = default_val
            return state
        except Exception as e:
            print(f"⚠️ Could not load loop state: {e}")

    return DEFAULT_STATE.copy()


def save_loop_state(state: dict):
    """
    Save loop state to JSON file.
    Simple and fast — called frequently.
    """
    state["last_updated"] = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(LOOP_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        print(f"⚠️ Could not save loop state: {e}")


# ════════════════════════════════════════════════
# STATUS CONTROLS
# Called by the dashboard Start / Pause / Stop buttons
# ════════════════════════════════════════════════

def start_loop(interval_minutes: int = 15):
    """
    Set loop to RUNNING.
    Called when user clicks START on dashboard.

    interval_minutes: How often the loop runs (default 15).
    Minimum 5 minutes — don't hammer yfinance.
    """
    interval_minutes = max(5, interval_minutes)
    state = load_loop_state()
    state["status"]           = STATUS_RUNNING
    state["interval_minutes"] = interval_minutes
    state["last_error"]       = None
    state["error_count"]      = 0
    save_loop_state(state)
    return state


def pause_loop():
    """
    Set loop to PAUSED.
    Loop will not run new cycles but keeps state.
    Called when user clicks PAUSE on dashboard.
    """
    state = load_loop_state()
    state["status"] = STATUS_PAUSED
    save_loop_state(state)
    return state


def stop_loop():
    """
    Set loop to STOPPED.
    Resets run counters but keeps decision log.
    Called when user clicks STOP on dashboard.
    """
    state = load_loop_state()
    state["status"]   = STATUS_STOPPED
    state["next_run"] = None
    save_loop_state(state)
    return state


def update_after_run(
    decisions_made: int,
    buys: int,
    sells: int,
    pnl_delta: float,
    next_run_time: str,
    error: str = None,
):
    """
    Update state after one execution cycle completes.
    Called at the end of every loop run.
    """
    state = load_loop_state()
    state["last_run"]        = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
    state["next_run"]        = next_run_time
    state["runs_today"]      = state.get("runs_today", 0) + 1
    state["decisions_today"] = state.get("decisions_today", 0) + decisions_made
    state["buys_today"]      = state.get("buys_today", 0)  + buys
    state["sells_today"]     = state.get("sells_today", 0) + sells
    state["pnl_today"]       = round(state.get("pnl_today", 0.0) + pnl_delta, 2)

    if error:
        state["error_count"] = state.get("error_count", 0) + 1
        state["last_error"]  = error

    save_loop_state(state)
    return state


def reset_daily_counters():
    """
    Called at market open each day to reset today's stats.
    Run counts, decision counts and P&L reset to 0.
    """
    state = load_loop_state()
    state["runs_today"]      = 0
    state["decisions_today"] = 0
    state["buys_today"]      = 0
    state["sells_today"]     = 0
    state["pnl_today"]       = 0.0
    save_loop_state(state)
    return state


# ════════════════════════════════════════════════
# DECISION LOG
# Every BUY, SELL, and NO-TRADE gets logged here.
# This is the audit trail for autonomous decisions.
# ════════════════════════════════════════════════

import pandas as pd

DECISION_LOG_COLS = [
    "Timestamp",
    "Stock",
    "Bucket",
    "Decision",       # BUY / SELL / NO-TRADE / HOLD
    "Score",
    "Signal",
    "Price",
    "Reason",         # Plain English explanation
    "Regime",
    "Exit_Reason",    # Filled only for SELL decisions
]


def log_decision(
    stock:       str,
    bucket:      str,
    decision:    str,
    score:       float,
    signal:      str,
    price:       float,
    reason:      str,
    regime:      str,
    exit_reason: str = "",
):
    """
    Append one decision to the decision log CSV AND Supabase.
    Called for EVERY decision the loop makes — including NO-TRADE.

    Logging NO-TRADE is just as important as logging BUY/SELL.
    It lets you audit why the system stayed out.
    """
    entry = {
        "Timestamp":   datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S'),
        "Stock":       stock,
        "Bucket":      bucket,
        "Decision":    decision,
        "Score":       round(float(score), 1) if score else 0,
        "Signal":      signal,
        "Price":       round(float(price), 2) if price else 0,
        "Reason":      reason,
        "Regime":      regime,
        "Exit_Reason": exit_reason,
    }

    # ── Layer 1: Supabase (permanent across restarts) ──
    try:
        from config.supabase_client import get_client
        client = get_client()
        if client:
            client.table("loop_decisions").insert({
                "timestamp":   entry["Timestamp"],
                "stock":       entry["Stock"],
                "bucket":      entry["Bucket"],
                "decision":    entry["Decision"],
                "score":       entry["Score"],
                "signal":      entry["Signal"],
                "price":       entry["Price"],
                "reason":      entry["Reason"],
                "regime":      entry["Regime"],
                "exit_reason": entry["Exit_Reason"],
            }).execute()
    except Exception as e:
        print(f"⚠️ Supabase decision log failed: {e}")

    # ── Layer 2: CSV fallback ──────────────────────────
    df = pd.DataFrame([entry])
    try:
        if os.path.exists(LOOP_LOG_FILE):
            df.to_csv(LOOP_LOG_FILE, mode='a', header=False, index=False)
        else:
            df.to_csv(LOOP_LOG_FILE, mode='w', header=True, index=False)
    except Exception as e:
        print(f"⚠️ Could not write decision log CSV: {e}")


def load_decision_log(max_rows: int = 200) -> pd.DataFrame:
    """
    Load the decision log for dashboard display.
    Tries Supabase first (survives restarts), falls back to CSV.
    Returns last N rows, newest first.
    """
    # ── Layer 1: Supabase ─────────────────────────
    try:
        from config.supabase_client import get_client
        client = get_client()
        if client:
            response = (
                client.table("loop_decisions")
                .select("*")
                .order("timestamp", desc=True)
                .limit(max_rows)
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "timestamp":   "Timestamp",
                    "stock":       "Stock",
                    "bucket":      "Bucket",
                    "decision":    "Decision",
                    "score":       "Score",
                    "signal":      "Signal",
                    "price":       "Price",
                    "reason":      "Reason",
                    "regime":      "Regime",
                    "exit_reason": "Exit_Reason",
                })
                cols = [c for c in DECISION_LOG_COLS if c in df.columns]
                return df[cols].reset_index(drop=True)
            return pd.DataFrame(columns=DECISION_LOG_COLS)
    except Exception as e:
        print(f"\u26a0\ufe0f Supabase decision log load failed: {e}")

    # ── Layer 2: CSV fallback ─────────────────────
    if not os.path.exists(LOOP_LOG_FILE):
        return pd.DataFrame(columns=DECISION_LOG_COLS)

    try:
        df = pd.read_csv(LOOP_LOG_FILE)
        df = df.sort_values("Timestamp", ascending=False).head(max_rows)
        return df.reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=DECISION_LOG_COLS)


def clear_decision_log():
    """
    Clear the decision log from CSV and Supabase.
    Called by the dashboard reset button.
    """
    # Clear Supabase
    try:
        from config.supabase_client import get_client
        client = get_client()
        if client:
            client.table("loop_decisions").delete().neq("id", 0).execute()
    except Exception as e:
        print(f"⚠️ Could not clear Supabase decision log: {e}")
    # Clear CSV
    if os.path.exists(LOOP_LOG_FILE):
        try:
            os.remove(LOOP_LOG_FILE)
        except Exception as e:
            print(f"⚠️ Could not clear decision log CSV: {e}")


# ════════════════════════════════════════════════
# MARKET HOURS HELPER
# Used by execution_loop.py to decide whether to run
# ════════════════════════════════════════════════

from datetime import time as dtime
import pytz

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN  = dtime(9, 15)    # 9:15 AM IST
MARKET_CLOSE = dtime(15, 30)   # 3:30 PM IST
PRE_MARKET   = dtime(9,  0)    # Pre-market prep: 9:00 AM IST
POST_MARKET  = dtime(15, 35)   # Post-market summary: 3:35 PM IST


def is_market_open() -> bool:
    """
    Returns True if NSE is currently open for trading.
    Checks time (IST) and day of week (Mon-Fri only).
    Does NOT check public holidays (keep it simple for now).
    """
    now_ist    = datetime.now(IST)
    weekday    = now_ist.weekday()     # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    now_time   = now_ist.time()

    if weekday >= 5:      # Saturday or Sunday
        return False

    return MARKET_OPEN <= now_time <= MARKET_CLOSE


def is_trading_day() -> bool:
    """Returns True if today is Mon-Fri (ignores holidays)."""
    now_ist  = datetime.now(IST)
    weekday  = now_ist.weekday()
    return weekday < 5


def get_market_status() -> dict:
    """
    Return a human-readable market status dict.
    Used by the dashboard status banner.
    Always uses IST (Asia/Kolkata = UTC+5:30).
    """
    now_ist  = datetime.now(IST)
    weekday  = now_ist.weekday()
    now_time = now_ist.time()
    time_str = now_ist.strftime('%I:%M %p IST (UTC+5:30)')

    if weekday >= 5:
        return {
            "open":   False,
            "status": "CLOSED — Weekend",
            "color":  "gray",
            "time":   time_str,
        }

    if now_time < MARKET_OPEN:
        return {
            "open":   False,
            "status": "PRE-MARKET",
            "color":  "orange",
            "time":   time_str,
        }

    if MARKET_OPEN <= now_time <= MARKET_CLOSE:
        return {
            "open":   True,
            "status": "OPEN 🟢",
            "color":  "green",
            "time":   time_str,
        }

    return {
        "open":   False,
        "status": "CLOSED — After Hours",
        "color":  "gray",
        "time":   time_str,
    }