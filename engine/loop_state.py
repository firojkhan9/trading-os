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
from datetime import datetime, time as dtime
import pytz

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN  = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
PRE_MARKET   = dtime(9,  0)
POST_MARKET  = dtime(15, 35)

try:
    from config.supabase_client import get_client as _get_supabase_client
    _LOOP_SUPABASE = True
except ImportError:
    _LOOP_SUPABASE = False
    def _get_supabase_client():
        return None

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
    "last_reset_date": None,   # NEW — tracks which day today's counters belong to
}

def _maybe_reset_daily(state: dict) -> dict:
    """
    Auto-reset today's counters if the date has rolled over.
    Runs on EVERY load_loop_state() call — dashboard, autopilot
    runner page, or terminal loop — so it always self-corrects,
    no matter how the app was opened.
    """
    today_str  = datetime.now(IST).strftime('%Y-%m-%d')
    last_reset = state.get("last_reset_date")

    if last_reset != today_str:
        state["runs_today"]      = 0
        state["decisions_today"] = 0
        state["buys_today"]      = 0
        state["sells_today"]     = 0
        state["pnl_today"]       = 0.0
        state["error_count"]     = 0
        state["last_error"]      = None
        state["last_reset_date"] = today_str
        save_loop_state(state)
        print(f"✅ Daily counters auto-reset for {today_str}")

    return state


# ════════════════════════════════════════════════
# LOAD AND SAVE
# ════════════════════════════════════════════════

def load_loop_state() -> dict:
    """
    Load the current loop state.
    Priority: Supabase (persists across Cloud restarts) → local JSON → defaults.
    """
    # ── Layer 1: Supabase ─────────────────────────
    try:
        client = _get_supabase_client()
        if client:
            response = client.table("loop_state").select("*").eq("id", 1).execute()
            if response.data:
                row = response.data[0]
                state = DEFAULT_STATE.copy()
                state["status"]           = row.get("status",           DEFAULT_STATE["status"])
                state["interval_minutes"] = row.get("interval_minutes", DEFAULT_STATE["interval_minutes"])
                state["last_run"]         = row.get("last_run")
                state["next_run"]         = row.get("next_run")
                state["runs_today"]       = row.get("runs_today",       0)
                state["decisions_today"]  = row.get("decisions_today",  0)
                state["buys_today"]       = row.get("buys_today",       0)
                state["sells_today"]      = row.get("sells_today",      0)
                state["pnl_today"]        = float(row.get("pnl_today",  0))
                state["last_updated"]     = row.get("last_updated")
                state["error_count"]      = row.get("error_count",      0)
                state["last_error"]       = row.get("last_error")
                state["last_reset_date"]  = row.get("last_reset_date")
                return _maybe_reset_daily(state)
    except Exception as e:
        print(f"⚠️ Supabase loop_state load failed: {e} — trying JSON")

    # ── Layer 2: Local JSON ───────────────────────
    if os.path.exists(LOOP_STATE_FILE):
        try:
            with open(LOOP_STATE_FILE, "r") as f:
                state = json.load(f)
            for key, default_val in DEFAULT_STATE.items():
                if key not in state:
                    state[key] = default_val
            return _maybe_reset_daily(state)
        except Exception as e:
            print(f"⚠️ Could not load loop state JSON: {e}")

    return _maybe_reset_daily(DEFAULT_STATE.copy())


def save_loop_state(state: dict):
    """
    Save loop state to Supabase (primary) and local JSON (fallback).
    Supabase uses a single row (id=1), upserted on every save.
    """
    state["last_updated"] = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

    # ── Layer 1: Supabase ─────────────────────────
    try:
        client = _get_supabase_client()
        if client:
            client.table("loop_state").upsert({
                "id":               1,
                "status":           state.get("status",           STATUS_STOPPED),
                "interval_minutes": state.get("interval_minutes", 15),
                "last_run":         state.get("last_run"),
                "next_run":         state.get("next_run"),
                "runs_today":       state.get("runs_today",       0),
                "decisions_today":  state.get("decisions_today",  0),
                "buys_today":       state.get("buys_today",       0),
                "sells_today":      state.get("sells_today",      0),
                "pnl_today":        float(state.get("pnl_today",  0)),
                "last_updated":     state["last_updated"],
                "error_count":      state.get("error_count",      0),
                "last_error":       state.get("last_error"),
                "last_reset_date":  state.get("last_reset_date"),
            }, on_conflict="id").execute()
    except Exception as e:
        print(f"⚠️ Supabase loop_state save failed: {e} — saved to JSON only")

    # ── Layer 2: Local JSON (always) ─────────────
    try:
        with open(LOOP_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        print(f"⚠️ Could not save loop state JSON: {e}")


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
    Append one decision to the decision log.
    Written to Supabase (primary) and CSV (fallback).
    Duplicate Supabase block removed in M33.
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

    # ── Layer 1: Supabase ─────────────────────────
    try:
        client = _get_supabase_client()
        if client:
            client.table("loop_decisions").insert({
                "timestamp":   entry["Timestamp"],
                "stock":       entry["Stock"],
                "bucket":      entry["Bucket"],
                "decision":    entry["Decision"],
                "score":       float(entry["Score"]),
                "signal":      entry["Signal"],
                "price":       float(entry["Price"]),
                "reason":      entry["Reason"],
                "regime":      entry["Regime"],
                "exit_reason": entry["Exit_Reason"],
            }).execute()
    except Exception as e:
        print(f"⚠️ Supabase loop_decisions insert failed: {e}")

    # ── Layer 2: CSV fallback ─────────────────────
    df = pd.DataFrame([entry])
    try:
        if os.path.exists(LOOP_LOG_FILE):
            df.to_csv(LOOP_LOG_FILE, mode='a', header=False, index=False)
        else:
            df.to_csv(LOOP_LOG_FILE, mode='w', header=True, index=False)
    except Exception as e:
        print(f"⚠️ Could not write decision log CSV: {e}")



def load_decision_log(max_rows: int = 5000) -> pd.DataFrame:
    """
    Load the decision log for dashboard display.
    Tries Supabase first, falls back to CSV.
    """
    # ── Layer 1: Supabase ─────────────────────────
    try:
        client = _get_supabase_client()
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
        print(f"⚠️ Supabase loop_decisions load failed: {e} — using CSV")

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
    Clear the decision log from Supabase and CSV.
    Called by the dashboard reset button.
    """
    try:
        client = _get_supabase_client()
        if client:
            client.table("loop_decisions").delete().neq("id", 0).execute()
    except Exception as e:
        print(f"⚠️ Could not clear Supabase loop_decisions: {e}")

    if os.path.exists(LOOP_LOG_FILE):
        try:
            os.remove(LOOP_LOG_FILE)
        except Exception as e:
            print(f"⚠️ Could not clear decision log CSV: {e}")


# ════════════════════════════════════════════════
# MARKET HOURS HELPER
# Used by execution_loop.py to decide whether to run
# ════════════════════════════════════════════════


def _is_nse_holiday(date_str: str) -> bool:
    """
    Check if a given date (YYYY-MM-DD) is an NSE holiday.
    Tries Supabase first, falls back to a local hardcoded set.
    """
    # ── Try Supabase ──────────────────────────────
    try:
        client = _get_supabase_client()
        if client:
            response = (
                client.table("nse_holidays")
                .select("date")
                .eq("date", date_str)
                .execute()
            )
            return len(response.data) > 0
    except Exception:
        pass

    # ── Hardcoded fallback (subset of known holidays) ─
    KNOWN_HOLIDAYS = {
        "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31",
        "2025-04-10", "2025-04-14", "2025-04-18", "2025-05-01",
        "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-21",
        "2025-10-22", "2025-11-05", "2025-12-25",
        "2026-01-26", "2026-03-03", "2026-03-20", "2026-04-02",
        "2026-04-03", "2026-04-14", "2026-05-01", "2026-08-15",
        "2026-09-18", "2026-10-02", "2026-10-28", "2026-11-10",
        "2026-12-25",
    }
    return date_str in KNOWN_HOLIDAYS


def is_market_open() -> bool:
    """
    Returns True if NSE is currently open for trading.
    Checks: (1) Mon–Fri, (2) market hours IST, (3) not an NSE holiday.
    """
    now_ist  = datetime.now(IST)
    weekday  = now_ist.weekday()   # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    now_time = now_ist.time()
    today    = now_ist.strftime('%Y-%m-%d')

    if weekday >= 5:
        return False

    if _is_nse_holiday(today):
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