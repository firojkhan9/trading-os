# ================================================
# FILE: portfolio/position_manager.py
# PURPOSE: Position Lifecycle Manager — Milestone 25
#
# WHAT THIS FILE DOES:
#   Tracks every position through defined states.
#   Without this, automation (M26) is dangerous —
#   it could double-enter, re-buy a stopped-out stock,
#   or miss a trailing stop update.
#
# THE LIFECYCLE STATES:
#   WATCHLIST   → Stock is being monitored, not yet entered
#   READY       → Signal fired, approved to enter on next bar
#   ENTERED     → BUY executed, position is live
#   HOLDING     → Normal holding, within stop/target range
#   TRAILING    → Profit > trail trigger, stop now trails peak
#   PARTIAL_EXIT→ Partial profit booked, remaining held
#   EXITED      → Position fully closed (target/stop/signal)
#   COOLDOWN    → Stop loss hit — blocked from re-entry N days
#   REJECTED    → Signal fired but blocked (score/limit/regime)
#
# STORAGE — TWO LAYERS:
#   Primary  : Supabase (cloud PostgreSQL) — survives restarts
#   Fallback : logs/position_lifecycle.csv — works on laptop
#
#   Both layers are written on every save. On Streamlit Cloud,
#   Supabase is used. On your laptop, CSV is the fallback.
#   See supabase_setup.sql for the table creation script.
#
# HOW IT CONNECTS:
#   capital_engine.py   → handles the MONEY (cash, deployed)
#   position_manager.py → handles the STATE (what stage is it)
#   execution_loop.py   → will call both (M26)
# ================================================

import pandas as pd
import os
import sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Supabase client ───────────────────────────────
# Same pattern as paper_trader.py.
# Returns client if secrets are configured, None otherwise.
# When None → CSV fallback activates silently.
from config.supabase_client import get_client as _get_supabase_client

# ── File path ─────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR       = os.path.join(BASE_DIR, "logs")
LIFECYCLE_FILE = os.path.join(LOGS_DIR, "position_lifecycle.csv")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Supabase table name ───────────────────────────
SUPABASE_TABLE = "position_lifecycle"


# ════════════════════════════════════════════════
# VALID STATES AND TRANSITION RULES
# ════════════════════════════════════════════════

VALID_STATES = {
    "WATCHLIST",
    "READY",
    "ENTERED",
    "HOLDING",
    "TRAILING",
    "PARTIAL_EXIT",
    "EXITED",
    "COOLDOWN",
    "REJECTED",
}

# Maps: current_state → [allowed_next_states]
# Prevents illegal jumps like WATCHLIST → EXITED
ALLOWED_TRANSITIONS = {
    "WATCHLIST":    ["READY",        "REJECTED"],
    "READY":        ["ENTERED",      "REJECTED", "WATCHLIST"],
    "ENTERED":      ["HOLDING",      "EXITED"],
    "HOLDING":      ["TRAILING",     "PARTIAL_EXIT", "EXITED", "HOLDING"],
    "TRAILING":     ["PARTIAL_EXIT", "EXITED",       "TRAILING"],
    "PARTIAL_EXIT": ["TRAILING",     "EXITED"],
    "EXITED":       ["COOLDOWN",     "WATCHLIST"],
    "COOLDOWN":     ["WATCHLIST"],
    "REJECTED":     ["WATCHLIST"],
}


# ════════════════════════════════════════════════
# RISK SETTINGS
# ════════════════════════════════════════════════

try:
    from config.strategy_settings import (
        STOP_LOSS_PCT,
        TARGET_PROFIT_PCT,
        TRAILING_STOP_PCT,
        USE_TRAILING_STOP,
    )
except ImportError:
    STOP_LOSS_PCT     = 0.06
    TARGET_PROFIT_PCT = 0.15
    TRAILING_STOP_PCT = 0.04
    USE_TRAILING_STOP = True

# After a stop loss, block re-entry for this many days
# Prevents "revenge trading" — re-buying a falling stock
COOLDOWN_DAYS = 3

# When gain reaches this %, book 50% of position as profit
PARTIAL_EXIT_TRIGGER_PCT = 0.08   # 8% gain → sell half

# When gain reaches this %, activate trailing stop
TRAIL_ACTIVATION_PCT = 0.06       # 6% gain → trail begins


# ════════════════════════════════════════════════
# SCHEMA
# All columns stored as text to avoid pandas
# dtype conflicts across different row states
# ════════════════════════════════════════════════

LIFECYCLE_COLUMNS = [
    "position_id",       # Unique ID: STOCK_BUCKET_YYYYMMDD_HHMMSS
    "stock",             # Stock name e.g. RELIANCE
    "symbol",            # Yahoo symbol e.g. RELIANCE.NS
    "bucket",            # Long-Term / Swing / Intraday
    "state",             # Current lifecycle state
    "buy_price",         # Entry price
    "buy_date",          # Entry date
    "quantity",          # Shares held
    "buy_value",         # Total cost
    "current_price",     # Last known price
    "current_pnl_pct",   # Current P&L %
    "peak_price",        # Highest price since entry (for trailing)
    "trail_stop_price",  # Current trailing stop price
    "hard_stop_price",   # Fixed hard stop
    "target_price",      # Fixed target
    "partial_sold",      # True if partial exit already done
    "composite_score",   # Score at time of entry
    "exit_reason",       # Why we exited (if exited)
    "exit_price",        # Price at exit (if exited)
    "exit_date",         # Date of exit (if exited)
    "days_held",         # Calendar days held
    "cooldown_until",    # Date cooldown expires
    "rejection_reason",  # Why it was rejected (if rejected)
    "notes",             # Additional context
    "last_updated",      # Timestamp of last state change
]


# ════════════════════════════════════════════════
# LOAD AND SAVE — TWO-LAYER STORAGE
#
# WHY TWO LAYERS?
#   Streamlit Cloud resets its filesystem on every
#   restart. Any CSV data written is LOST.
#   Supabase is a free cloud PostgreSQL database.
#   Data written there persists permanently.
#
#   Pattern: try Supabase → fall back to CSV.
#   Works identically on laptop (CSV) and cloud (Supabase).
# ════════════════════════════════════════════════

def _empty_df():
    """Return a correctly typed empty DataFrame."""
    return pd.DataFrame(columns=LIFECYCLE_COLUMNS).astype(object)


def load_lifecycle():
    """
    Load the full position lifecycle table.

    Priority:
      1. Supabase — persists across Cloud restarts
      2. Local CSV — works on laptop

    dtype=str / astype(object) ensures ALL columns are
    strings, preventing pandas dtype errors when the same
    column holds numbers in some rows and empty strings in others.
    """
    # ── Layer 1: Supabase ─────────────────────────
    client = _get_supabase_client()
    if client:
        try:
            response = (
                client.table(SUPABASE_TABLE)
                .select("*")
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data).astype(str)
                df = df.replace("nan", "").replace("<NA>", "")
                for col in LIFECYCLE_COLUMNS:
                    if col not in df.columns:
                        df[col] = ""
                return df
            return _empty_df()
        except Exception as e:
            print(f"⚠️ Supabase lifecycle load failed: {e} — using CSV")

    # ── Layer 2: CSV fallback ─────────────────────
    if os.path.exists(LIFECYCLE_FILE):
        df = pd.read_csv(LIFECYCLE_FILE, dtype=str)
        for col in LIFECYCLE_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df

    return _empty_df()


def save_lifecycle(df):
    """
    Save to BOTH Supabase AND CSV.

    Supabase  → upserts on position_id (update if exists, insert if new)
    CSV       → always written as local backup

    This means:
    - Cloud app uses Supabase (permanent)
    - Laptop uses CSV (no Supabase needed)
    - CSV is also a downloadable backup of your cloud data
    """
    # ── Layer 1: Supabase ─────────────────────────
    client = _get_supabase_client()
    if client:
        try:
            records = []
            for _, row in df.iterrows():
                record = {}
                for col in LIFECYCLE_COLUMNS:
                    val = row.get(col, "")
                    # Store empty string as NULL in Supabase
                    record[col] = str(val) if val not in ("", None, "nan") else None
                records.append(record)
            if records:
                client.table(SUPABASE_TABLE).upsert(
                    records,
                    on_conflict="position_id"
                ).execute()
        except Exception as e:
            print(f"⚠️ Supabase lifecycle save failed: {e} — saved to CSV only")

    # ── Layer 2: CSV (always) ─────────────────────
    try:
        df.to_csv(LIFECYCLE_FILE, index=False)
    except Exception as e:
        print(f"⚠️ CSV lifecycle save failed: {e}")


# ════════════════════════════════════════════════
# INTERNAL HELPERS
# ════════════════════════════════════════════════

def _generate_position_id(stock, bucket):
    """
    Generate a unique position ID.
    Format: RELIANCE_Swing_20250526_143022
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{stock}_{bucket}_{ts}"


def _can_transition(current_state, new_state):
    """
    Check if a state transition is legal.
    Returns (allowed: bool, reason: str)
    """
    allowed = ALLOWED_TRANSITIONS.get(current_state, [])
    if new_state in allowed:
        return True, ""
    return False, (
        f"Illegal transition: {current_state} → {new_state}. "
        f"Allowed from {current_state}: {allowed}"
    )


def _update_position_state(df, position_id, new_state, updates=None):
    """
    Apply a validated state transition to a position row.
    Raises ValueError if the transition is not allowed.
    All values stored as strings (object dtype).
    """
    mask = df["position_id"] == position_id
    if not mask.any():
        raise ValueError(f"Position {position_id} not found")

    current_state = df.loc[mask, "state"].iloc[0]
    allowed, reason = _can_transition(current_state, new_state)
    if not allowed:
        raise ValueError(reason)

    df.loc[mask, "state"]        = new_state
    df.loc[mask, "last_updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if updates:
        for col, val in updates.items():
            if col in LIFECYCLE_COLUMNS:
                df.loc[mask, col] = str(val)

    return df


# ════════════════════════════════════════════════
# POSITION CREATION
# ════════════════════════════════════════════════

def add_to_watchlist(stock, symbol, bucket, notes=""):
    """
    Add a stock to the lifecycle as WATCHLIST.
    Entry point — every position starts here.
    Returns SKIPPED if already being tracked.
    """
    df = load_lifecycle()

    active_states = {
        "WATCHLIST", "READY", "ENTERED",
        "HOLDING", "TRAILING", "PARTIAL_EXIT"
    }
    existing = df[
        (df["stock"]  == stock) &
        (df["bucket"] == bucket) &
        (df["state"].isin(active_states))
    ]
    if not existing.empty:
        return {
            "status": "SKIPPED",
            "reason": (
                f"{stock} is already tracked in {bucket} "
                f"({existing.iloc[0]['state']})"
            ),
        }

    position_id = _generate_position_id(stock, bucket)
    new_row = {col: "" for col in LIFECYCLE_COLUMNS}
    new_row.update({
        "position_id":  position_id,
        "stock":        stock,
        "symbol":       symbol,
        "bucket":       bucket,
        "state":        "WATCHLIST",
        "notes":        notes,
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_lifecycle(df)

    return {"status": "OK", "position_id": position_id, "state": "WATCHLIST"}


def mark_ready(position_id, composite_score):
    """
    Mark WATCHLIST → READY.
    Signal has fired and score threshold is met.
    """
    df = load_lifecycle()
    df = _update_position_state(df, position_id, "READY", {
        "composite_score": composite_score,
    })
    save_lifecycle(df)
    return {"status": "OK", "state": "READY"}


def mark_rejected(position_id, reason):
    """
    Mark a position as REJECTED with a reason.
    Examples: score too low, bear market, bucket full, daily loss limit.
    """
    df = load_lifecycle()
    df = _update_position_state(df, position_id, "REJECTED", {
        "rejection_reason": reason,
    })
    save_lifecycle(df)
    return {"status": "OK", "state": "REJECTED", "reason": reason}


# ════════════════════════════════════════════════
# POSITION ENTRY
# ════════════════════════════════════════════════

def mark_entered(position_id, buy_price, quantity, buy_value):
    """
    Mark READY → ENTERED after BUY executes.
    Calculates hard stop, target, and initial trailing stop.
    """
    hard_stop  = round(buy_price * (1 - STOP_LOSS_PCT),     2)
    target     = round(buy_price * (1 + TARGET_PROFIT_PCT), 2)
    trail_stop = round(buy_price * (1 - TRAILING_STOP_PCT), 2)

    df = load_lifecycle()
    df = _update_position_state(df, position_id, "ENTERED", {
        "buy_price":        buy_price,
        "buy_date":         datetime.now().strftime('%Y-%m-%d'),
        "quantity":         quantity,
        "buy_value":        buy_value,
        "current_price":    buy_price,
        "current_pnl_pct":  0.0,
        "peak_price":       buy_price,
        "trail_stop_price": trail_stop,
        "hard_stop_price":  hard_stop,
        "target_price":     target,
        "partial_sold":     "False",
    })
    save_lifecycle(df)
    return {
        "status":     "OK",
        "state":      "ENTERED",
        "hard_stop":  hard_stop,
        "target":     target,
        "trail_stop": trail_stop,
    }


# ════════════════════════════════════════════════
# POSITION MONITORING — the heartbeat
# Called on every price update by the execution loop
# ════════════════════════════════════════════════

def update_position_price(position_id, current_price):
    """
    Update a live position with the latest price.
    Called by the execution loop on every tick (M26).

    Does five things on every call:
      1. Updates current price and P&L %
      2. Updates peak price if new high reached
      3. Recalculates trailing stop from peak
      4. Checks all exit conditions in priority order
      5. Applies valid state transitions

    State transition rules:
      ENTERED     → HOLDING      (first update after entry, always)
      HOLDING     → TRAILING     (when gain >= trail activation %)
      HOLDING     → PARTIAL_EXIT (when gain >= partial exit %)
      TRAILING    → PARTIAL_EXIT (when gain >= partial exit %)
      PARTIAL_EXIT respects trailing stop and hard stop

    Returns action the caller should take:
      HOLD          — no action needed
      TRAIL_ACTIVATED — trailing stop just turned on
      PARTIAL_EXIT  — sell 50%, keep rest
      SELL_STOP     — hard stop loss hit, sell all immediately
      SELL_TARGET   — profit target hit, sell all
      SELL_TRAIL    — trailing stop triggered, sell all
    """
    df   = load_lifecycle()
    mask = df["position_id"] == position_id

    if not mask.any():
        return {"action": "ERROR", "reason": f"Position {position_id} not found"}

    row   = df.loc[mask].iloc[0]
    state = str(row["state"])

    if state not in {"ENTERED", "HOLDING", "TRAILING", "PARTIAL_EXIT"}:
        return {
            "action": "NO_ACTION",
            "reason": f"Position in {state} — not live"
        }

    # ── Recalculate all metrics ────────────────────
    buy_price    = float(row["buy_price"])
    pnl_pct      = round(((current_price - buy_price) / buy_price) * 100, 3)
    peak_price   = max(float(row["peak_price"]), current_price)
    trail_stop   = round(peak_price * (1 - TRAILING_STOP_PCT), 2)
    hard_stop    = float(row["hard_stop_price"])
    target       = float(row["target_price"])
    partial_sold = str(row.get("partial_sold", "False")).strip().lower() in (
        "true", "1", "yes"
    )

    try:
        buy_date  = pd.to_datetime(row["buy_date"]).date()
        days_held = (date.today() - buy_date).days
    except Exception:
        days_held = 0

    # ── Determine recommended action ──────────────
    # Priority order matters — stop loss always beats target
    action = "HOLD"
    reason = "Within normal range — no action needed"

    if current_price <= hard_stop:
        action = "SELL_STOP"
        reason = (
            f"Hard stop loss hit. "
            f"Bought ₹{buy_price} → Stop ₹{hard_stop} → "
            f"Now ₹{current_price} ({pnl_pct:.1f}%)"
        )
    elif current_price >= target:
        action = "SELL_TARGET"
        reason = (
            f"Profit target reached! "
            f"Bought ₹{buy_price} → Target ₹{target} → "
            f"Now ₹{current_price} (+{pnl_pct:.1f}%)"
        )
    elif state in {"TRAILING", "PARTIAL_EXIT"} and current_price <= trail_stop:
        action = "SELL_TRAIL"
        reason = (
            f"Trailing stop triggered. "
            f"Peak ₹{peak_price} → Trail ₹{trail_stop} → "
            f"Now ₹{current_price} "
            f"(peak gain ~{round(((peak_price-buy_price)/buy_price)*100,1)}%)"
        )
    elif (
        USE_TRAILING_STOP
        and pnl_pct >= (TRAIL_ACTIVATION_PCT * 100)
        and state in {"HOLDING", "ENTERED"}
    ):
        action = "TRAIL_ACTIVATED"
        reason = (
            f"Trailing stop activated at {pnl_pct:.1f}% gain. "
            f"Trail stop ₹{trail_stop} — moves up with price."
        )
    elif (
        not partial_sold
        and pnl_pct >= (PARTIAL_EXIT_TRIGGER_PCT * 100)
        and state in {"HOLDING", "ENTERED", "TRAILING"}
    ):
        action = "PARTIAL_EXIT"
        reason = (
            f"Partial exit trigger at {pnl_pct:.1f}% gain. "
            f"Sell 50% to lock in profit, keep rest running."
        )

    # ── Determine new state ────────────────────────
    # RULE: ENTERED must always go to HOLDING first.
    # The state machine does not allow ENTERED → TRAILING directly.
    # So we do two steps when needed:
    # Step A: ENTERED → HOLDING (always, on first update)
    # Step B: HOLDING → TRAILING or PARTIAL_EXIT (if action says so)

    price_updates = {
        "current_price":    current_price,
        "current_pnl_pct":  pnl_pct,
        "peak_price":       peak_price,
        "trail_stop_price": trail_stop,
        "days_held":        days_held,
    }

    # Step A — resolve ENTERED → HOLDING first
    if state == "ENTERED":
        df    = _update_position_state(df, position_id, "HOLDING", price_updates)
        state = "HOLDING"

    # Step B — apply action-driven transition
    if action == "TRAIL_ACTIVATED" and state == "HOLDING":
        df        = _update_position_state(df, position_id, "TRAILING", price_updates)
        new_state = "TRAILING"

    elif action == "PARTIAL_EXIT" and state in {"HOLDING", "TRAILING"}:
        df        = _update_position_state(df, position_id, "PARTIAL_EXIT", price_updates)
        new_state = "PARTIAL_EXIT"

    else:
        # HOLD, SELL_*, or no valid transition — just write price updates in place
        mask = df["position_id"] == position_id
        for col, val in price_updates.items():
            df.loc[mask, col] = str(val)
        df.loc[mask, "last_updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_state = state

    save_lifecycle(df)

    return {
        "action":     action,
        "pnl_pct":    pnl_pct,
        "peak_price": peak_price,
        "trail_stop": trail_stop,
        "hard_stop":  hard_stop,
        "target":     target,
        "days_held":  days_held,
        "state":      new_state,
        "reason":     reason,
    }


# ════════════════════════════════════════════════
# POSITION EXIT
# ════════════════════════════════════════════════

def mark_exited(position_id, exit_price, exit_reason):
    """
    Mark a position as EXITED.
    Records final P&L, exit price, and reason.

    exit_reason values:
      STOP_LOSS   → hard stop hit     (triggers cooldown)
      TARGET      → profit target hit (no cooldown)
      TRAIL_STOP  → trailing stop hit (no cooldown)
      SIGNAL_EXIT → strategy said SELL (no cooldown)
      MANUAL      → user manually closed (no cooldown)
      TIME_EXIT   → max holding period reached (no cooldown)
    """
    df   = load_lifecycle()
    mask = df["position_id"] == position_id

    if not mask.any():
        return {"status": "ERROR", "reason": "Position not found"}

    row       = df.loc[mask].iloc[0]
    buy_price = float(row["buy_price"])
    pnl_pct   = round(((exit_price - buy_price) / buy_price) * 100, 3)

    try:
        buy_date  = pd.to_datetime(row["buy_date"]).date()
        days_held = (date.today() - buy_date).days
    except Exception:
        days_held = 0

    df = _update_position_state(df, position_id, "EXITED", {
        "exit_price":       exit_price,
        "exit_date":        datetime.now().strftime('%Y-%m-%d'),
        "exit_reason":      exit_reason,
        "current_pnl_pct":  pnl_pct,
        "days_held":        days_held,
    })
    save_lifecycle(df)

    # Only STOP_LOSS triggers a cooldown
    # TARGET and TRAIL_STOP exits mean the strategy worked — no penalty
    if exit_reason == "STOP_LOSS":
        _trigger_cooldown(
            df,
            str(row["stock"]),
            str(row["bucket"])
        )

    return {
        "status":      "OK",
        "state":       "EXITED",
        "exit_price":  exit_price,
        "exit_reason": exit_reason,
        "pnl_pct":     pnl_pct,
        "days_held":   days_held,
    }


def mark_partial_exit_done(position_id, partial_price, qty_sold):
    """
    Record that a partial exit has been executed.
    Sets partial_sold = True so it never triggers again.
    Position stays active (PARTIAL_EXIT or TRAILING state).
    """
    df   = load_lifecycle()
    mask = df["position_id"] == position_id
    if not mask.any():
        return {"status": "ERROR", "reason": "Position not found"}

    existing_notes = str(df.loc[mask, "notes"].iloc[0])
    df.loc[mask, "partial_sold"]  = "True"
    df.loc[mask, "notes"]         = (
        existing_notes +
        f" | Partial exit: {qty_sold} shares @ "
        f"Rs {partial_price} on {datetime.now().strftime('%Y-%m-%d')}"
    )
    df.loc[mask, "last_updated"]  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_lifecycle(df)
    return {"status": "OK", "partial_sold": True}


# ════════════════════════════════════════════════
# COOLDOWN MANAGEMENT
# After a stop loss, block re-entry for N days.
# Prevents revenge trading — re-buying a falling stock.
# ════════════════════════════════════════════════

def _trigger_cooldown(df, stock, bucket):
    """
    Internal — called by mark_exited when exit_reason == STOP_LOSS.
    Adds a COOLDOWN row for this stock + bucket combination.
    """
    cooldown_until = (
        date.today() + timedelta(days=COOLDOWN_DAYS)
    ).strftime('%Y-%m-%d')

    cooldown_id = _generate_position_id(stock + "_CD", bucket)

    new_row = {col: "" for col in LIFECYCLE_COLUMNS}
    new_row.update({
        "position_id":    cooldown_id,
        "stock":          stock,
        "bucket":         bucket,
        "state":          "COOLDOWN",
        "cooldown_until": cooldown_until,
        "notes":          (
            f"Cooldown after stop loss. "
            f"Re-entry allowed after {cooldown_until}."
        ),
        "last_updated":   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_lifecycle(df)
    return cooldown_until


def is_in_cooldown(stock, bucket):
    """
    Check if a stock is in cooldown for a given bucket.
    Returns (in_cooldown: bool, cooldown_until: str or None)

    Called by the entry engine before placing any BUY.
    """
    df        = load_lifecycle()
    today_str = date.today().strftime('%Y-%m-%d')

    if df.empty:
        return False, None

    cooldowns = df[
        (df["stock"]  == stock)  &
        (df["bucket"] == bucket) &
        (df["state"]  == "COOLDOWN")
    ]

    if cooldowns.empty:
        return False, None

    for _, row in cooldowns.iterrows():
        until = str(row.get("cooldown_until", ""))
        if until and until >= today_str:
            return True, until

    # All cooldowns expired — move them back to WATCHLIST
    expired_mask = (
        (df["stock"]  == stock)  &
        (df["bucket"] == bucket) &
        (df["state"]  == "COOLDOWN")
    )
    df.loc[expired_mask, "state"] = "WATCHLIST"
    save_lifecycle(df)
    return False, None


def expire_cooldowns():
    """
    Scan all COOLDOWN positions and expire any that have passed.
    Move them back to WATCHLIST so they can be re-evaluated.
    Call this once at the start of each trading day.
    Returns list of stocks whose cooldown expired.
    """
    df        = load_lifecycle()
    today_str = date.today().strftime('%Y-%m-%d')
    expired   = []

    if df.empty:
        return expired

    for idx, row in df[df["state"] == "COOLDOWN"].iterrows():
        until = str(row.get("cooldown_until", ""))
        if until and until < today_str:
            df.loc[idx, "state"]        = "WATCHLIST"
            df.loc[idx, "last_updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            df.loc[idx, "notes"]        = str(row["notes"]) + " | Cooldown expired."
            expired.append(str(row["stock"]))

    if expired:
        save_lifecycle(df)

    return expired


# ════════════════════════════════════════════════
# QUERY FUNCTIONS
# ════════════════════════════════════════════════

def get_live_positions():
    """
    Return all currently live positions.
    Live = ENTERED, HOLDING, TRAILING, or PARTIAL_EXIT.
    The execution loop monitors these every tick.
    """
    df         = load_lifecycle()
    live_states = {"ENTERED", "HOLDING", "TRAILING", "PARTIAL_EXIT"}
    return df[df["state"].isin(live_states)].copy()


def get_ready_positions():
    """
    Return all READY positions.
    These are approved to enter on the next price tick.
    """
    df = load_lifecycle()
    return df[df["state"] == "READY"].copy()


def get_watchlist_positions():
    """Return all WATCHLIST positions."""
    df = load_lifecycle()
    return df[df["state"] == "WATCHLIST"].copy()


def get_position_by_id(position_id):
    """Get a single position as a dict, or None."""
    df   = load_lifecycle()
    mask = df["position_id"] == position_id
    if not mask.any():
        return None
    return df.loc[mask].iloc[0].to_dict()


def get_cooldown_stocks(bucket=None):
    """
    Return list of stocks currently in cooldown.
    Used by scanner to exclude blocked stocks.
    """
    df        = load_lifecycle()
    today_str = date.today().strftime('%Y-%m-%d')
    if df.empty:
        return []

    mask = (df["state"] == "COOLDOWN") & (df["cooldown_until"] >= today_str)
    if bucket:
        mask = mask & (df["bucket"] == bucket)
    return df[mask]["stock"].tolist()


def get_full_history(include_exited=True, include_rejected=False):
    """
    Return full lifecycle history.
    Used by the dashboard audit log.
    """
    df = load_lifecycle()
    if df.empty:
        return df

    excluded = set()
    if not include_exited:
        excluded.add("EXITED")
    if not include_rejected:
        excluded.add("REJECTED")

    if excluded:
        df = df[~df["state"].isin(excluded)]

    return df.sort_values("last_updated", ascending=False)


# ════════════════════════════════════════════════
# SUMMARY AND DISPLAY — for dashboard
# ════════════════════════════════════════════════

def get_lifecycle_summary():
    """
    High-level count of positions per state group.
    Used for the Tab 10 headline metrics.
    """
    df        = load_lifecycle()
    today_str = date.today().strftime('%Y-%m-%d')
    live_states = {"ENTERED", "HOLDING", "TRAILING", "PARTIAL_EXIT"}

    return {
        "live":         len(df[df["state"].isin(live_states)]),
        "watchlist":    len(df[df["state"] == "WATCHLIST"]),
        "ready":        len(df[df["state"] == "READY"]),
        "cooldown":     len(df[
            (df["state"] == "COOLDOWN") &
            (df["cooldown_until"] >= today_str)
        ]) if not df.empty else 0,
        "exited_today": len(df[
            (df["state"] == "EXITED") &
            (df["exit_date"] == today_str)
        ]) if not df.empty else 0,
        "total":        len(df),
    }


def get_lifecycle_display_df():
    """
    Dashboard-ready DataFrame of all non-exited positions.
    Formats numbers with Rs prefix, adds % to P&L.
    """
    df = load_lifecycle()
    if df.empty:
        return pd.DataFrame()

    active_states = {
        "WATCHLIST", "READY", "ENTERED", "HOLDING",
        "TRAILING", "PARTIAL_EXIT", "COOLDOWN"
    }
    df = df[df["state"].isin(active_states)].copy()
    if df.empty:
        return pd.DataFrame()

    display_cols = [
        "stock", "bucket", "state",
        "buy_price", "current_price", "current_pnl_pct",
        "peak_price", "trail_stop_price", "hard_stop_price",
        "target_price", "days_held", "partial_sold",
        "cooldown_until", "composite_score",
    ]
    existing = [c for c in display_cols if c in df.columns]
    result   = df[existing].copy()

    # Format price columns
    for col in [
        "buy_price", "current_price", "peak_price",
        "trail_stop_price", "hard_stop_price", "target_price"
    ]:
        if col in result.columns:
            result[col] = result[col].apply(
                lambda x: f"Rs {float(x):.2f}"
                if str(x).replace(".", "").replace("-", "").isdigit()
                and str(x) not in ("", "nan")
                else x
            )

    if "current_pnl_pct" in result.columns:
        result["current_pnl_pct"] = result["current_pnl_pct"].apply(
            lambda x: f"{float(x):+.2f}%"
            if str(x).lstrip("-").replace(".", "").isdigit()
            and str(x) not in ("", "nan")
            else x
        )

    result = result.rename(columns={
        "stock":            "Stock",
        "bucket":           "Bucket",
        "state":            "State",
        "buy_price":        "Buy",
        "current_price":    "Now",
        "current_pnl_pct":  "P&L %",
        "peak_price":       "Peak",
        "trail_stop_price": "Trail Stop",
        "hard_stop_price":  "Hard Stop",
        "target_price":     "Target",
        "days_held":        "Days",
        "partial_sold":     "Half Sold?",
        "cooldown_until":   "Cooldown Till",
        "composite_score":  "Score",
    })

    return result.reset_index(drop=True)


def get_state_color(state):
    """
    CSS color string for a lifecycle state.
    Used by Streamlit dataframe styling.
    """
    colors = {
        "WATCHLIST":    "color: gray",
        "READY":        "color: gold; font-weight: bold",
        "ENTERED":      "color: green",
        "HOLDING":      "color: lightgreen",
        "TRAILING":     "color: cyan; font-weight: bold",
        "PARTIAL_EXIT": "color: orange",
        "EXITED":       "color: gray",
        "COOLDOWN":     "color: red",
        "REJECTED":     "color: darkred",
    }
    return colors.get(str(state).upper(), "")
