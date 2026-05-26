# ================================================
# FILE: portfolio/position_manager.py
# PURPOSE: Position Lifecycle Manager — Milestone 25
#
# WHAT THIS FILE DOES:
#   Tracks every position through defined states.
#   Without this, automation (M26) is dangerous —
#   it could double-enter, re-buy a stopped-out stock,
#   or miss trailing stop updates.
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
# DATA STORAGE:
#   logs/position_lifecycle.csv  — full state + audit trail
#
# HOW IT CONNECTS:
#   capital_engine.py  → handles the MONEY (cash, deployed)
#   position_manager.py → handles the STATE (what stage is it)
#   execution_loop.py  → will call both (M26)
# ================================================

import pandas as pd
import os
import sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── File path ─────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR          = os.path.join(BASE_DIR, "logs")
LIFECYCLE_FILE    = os.path.join(LOGS_DIR, "position_lifecycle.csv")

os.makedirs(LOGS_DIR, exist_ok=True)

# ── Valid states ──────────────────────────────────
# These are the ONLY allowed states — nothing else can
# be written. This enforces clean state transitions.
VALID_STATES = {
    "WATCHLIST",    # Being monitored
    "READY",        # Signal fired, waiting to enter
    "ENTERED",      # BUY just executed
    "HOLDING",      # Normal hold — no action needed
    "TRAILING",     # Trailing stop active — lock in gains
    "PARTIAL_EXIT", # Half sold, rest still held
    "EXITED",       # Fully closed
    "COOLDOWN",     # Post stop-loss blackout period
    "REJECTED",     # Blocked from entering
}

# ── State transition rules ────────────────────────
# Maps: current_state → [allowed_next_states]
# This prevents illegal transitions like
# jumping from WATCHLIST directly to EXITED.
ALLOWED_TRANSITIONS = {
    "WATCHLIST":    ["READY",   "REJECTED"],
    "READY":        ["ENTERED", "REJECTED", "WATCHLIST"],
    "ENTERED":      ["HOLDING", "EXITED"],
    "HOLDING":      ["TRAILING", "PARTIAL_EXIT", "EXITED", "HOLDING"],
    "TRAILING":     ["PARTIAL_EXIT", "EXITED", "TRAILING"],
    "PARTIAL_EXIT": ["TRAILING", "EXITED"],
    "EXITED":       ["COOLDOWN", "WATCHLIST"],
    "COOLDOWN":     ["WATCHLIST"],
    "REJECTED":     ["WATCHLIST"],
}

# ── Risk settings ─────────────────────────────────
# Read from strategy_settings if available
try:
    from config.strategy_settings import (
        STOP_LOSS_PCT,
        TARGET_PROFIT_PCT,
        TRAILING_STOP_PCT,
        USE_TRAILING_STOP,
    )
except ImportError:
    STOP_LOSS_PCT     = 0.06   # 6% hard stop
    TARGET_PROFIT_PCT = 0.15   # 15% target
    TRAILING_STOP_PCT = 0.04   # 4% trail below peak
    USE_TRAILING_STOP = True

# ── Cooldown period ───────────────────────────────
# After a stop loss, block re-entry for this many days.
# Prevents "revenge trading" — re-buying a falling stock.
COOLDOWN_DAYS = 3

# ── Partial exit trigger ──────────────────────────
# When gain reaches this %, book 50% of position as profit.
# Keeps some upside while locking in gains.
PARTIAL_EXIT_TRIGGER_PCT = 0.08   # 8% gain → sell half

# ── Trailing stop trigger ─────────────────────────
# When gain reaches this %, activate trailing stop.
# Once active, stop moves UP with the price.
TRAIL_ACTIVATION_PCT = 0.06   # Activate trail at 6% gain


# ════════════════════════════════════════════════
# SCHEMA — columns in position_lifecycle.csv
# ════════════════════════════════════════════════

LIFECYCLE_COLUMNS = [
    "Position_ID",      # Unique ID: STOCK_BUCKET_YYYYMMDD_HHMMSS
    "Stock",            # Stock name e.g. RELIANCE
    "Symbol",           # Yahoo symbol e.g. RELIANCE.NS
    "Bucket",           # Which bucket: Long-Term / Swing / Intraday
    "State",            # Current lifecycle state
    "Buy_Price",        # Entry price
    "Buy_Date",         # Entry date
    "Quantity",         # Shares held
    "Buy_Value",        # Total cost
    "Current_Price",    # Last known price
    "Current_PNL_Pct",  # Current P&L %
    "Peak_Price",       # Highest price seen since entry (for trailing)
    "Trail_Stop_Price", # Current trailing stop price (0 if not active)
    "Hard_Stop_Price",  # Fixed hard stop (buy_price × (1 - stop_loss_pct))
    "Target_Price",     # Fixed target (buy_price × (1 + target_pct))
    "Partial_Sold",     # True if we've already done a partial exit
    "Composite_Score",  # Score at time of entry
    "Exit_Reason",      # Why we exited (if exited)
    "Exit_Price",       # Price at exit (if exited)
    "Exit_Date",        # Date of exit (if exited)
    "Days_Held",        # How many calendar days held
    "Cooldown_Until",   # Date cooldown expires (if in COOLDOWN)
    "Rejection_Reason", # Why it was rejected (if rejected)
    "Notes",            # Any additional context
    "Last_Updated",     # Timestamp of last state change
]


# ════════════════════════════════════════════════
# LOAD AND SAVE
# ════════════════════════════════════════════════

def load_lifecycle():
    """
    Load the full position lifecycle table from CSV.
    Returns an empty DataFrame with correct columns
    if the file does not exist yet.

    IMPORTANT: dtype=str forces ALL columns to string (object dtype).
    This prevents pandas from inferring numeric types on columns that
    sometimes hold numbers and sometimes hold empty strings or dates.
    Without this, assignments like df.loc[mask, "Composite_Score"] = "72"
    would raise TypeError on a float64 column.
    """
    if os.path.exists(LIFECYCLE_FILE):
        df = pd.read_csv(LIFECYCLE_FILE, dtype=str)
        # Ensure all columns exist (handles schema evolution gracefully)
        for col in LIFECYCLE_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df

    # First run — empty frame, all columns as string
    return pd.DataFrame(columns=LIFECYCLE_COLUMNS).astype(object)


def save_lifecycle(df):
    """
    Save the lifecycle table back to CSV.
    Called after every state change.
    """
    df.to_csv(LIFECYCLE_FILE, index=False)


def _generate_position_id(stock, bucket):
    """
    Generate a unique position ID.
    Format: RELIANCE_Swing_20250526_143022
    Makes it easy to find a position in logs.
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{stock}_{bucket}_{ts}"


# ════════════════════════════════════════════════
# STATE TRANSITION ENGINE
# The core logic — validates and applies transitions
# ════════════════════════════════════════════════

def _can_transition(current_state, new_state):
    """
    Check if a state transition is legal.
    Prevents invalid jumps like WATCHLIST → EXITED.
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
    Apply a state transition to a position row.

    df           : the lifecycle DataFrame
    position_id  : which position to update
    new_state    : the new state to transition to
    updates      : dict of additional column updates

    Returns updated DataFrame.
    Raises ValueError if transition is not allowed.
    """
    mask = df["Position_ID"] == position_id
    if not mask.any():
        raise ValueError(f"Position {position_id} not found in lifecycle table")

    current_state = df.loc[mask, "State"].iloc[0]
    allowed, reason = _can_transition(current_state, new_state)

    if not allowed:
        raise ValueError(reason)

    # Apply state change
    df.loc[mask, "State"]        = new_state
    df.loc[mask, "Last_Updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Apply any additional column updates
    # Cast every value to str to avoid pandas dtype conflicts
    # (all columns are stored as text in the CSV)
    if updates:
        for col, val in updates.items():
            if col in LIFECYCLE_COLUMNS:
                df.loc[mask, col] = str(val)

    return df


# ════════════════════════════════════════════════
# POSITION CREATION
# Called when a new opportunity is spotted
# ════════════════════════════════════════════════

def add_to_watchlist(stock, symbol, bucket, notes=""):
    """
    Add a stock to the lifecycle as WATCHLIST.
    This is the entry point — every position starts here.

    Called by: scanner, scoring engine, or manually.
    Next step: mark_ready() when signal fires.
    """
    df = load_lifecycle()

    # Don't add duplicates — check if already being tracked
    active_states = {"WATCHLIST", "READY", "ENTERED", "HOLDING", "TRAILING", "PARTIAL_EXIT"}
    existing = df[
        (df["Stock"]  == stock) &
        (df["Bucket"] == bucket) &
        (df["State"].isin(active_states))
    ]
    if not existing.empty:
        return {
            "status":  "SKIPPED",
            "reason":  f"{stock} is already being tracked in {bucket} ({existing.iloc[0]['State']})",
        }

    position_id = _generate_position_id(stock, bucket)
    new_row = {col: "" for col in LIFECYCLE_COLUMNS}
    new_row.update({
        "Position_ID":  position_id,
        "Stock":        stock,
        "Symbol":       symbol,
        "Bucket":       bucket,
        "State":        "WATCHLIST",
        "Notes":        notes,
        "Last_Updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_lifecycle(df)

    return {
        "status":      "OK",
        "position_id": position_id,
        "state":       "WATCHLIST",
    }


def mark_ready(position_id, composite_score):
    """
    Mark a WATCHLIST position as READY to enter.
    Called when the combined signal fires AND score threshold met.
    Next step: mark_entered() when BUY is executed.
    """
    df = load_lifecycle()
    df = _update_position_state(df, position_id, "READY", {
        "Composite_Score": composite_score,
    })
    save_lifecycle(df)
    return {"status": "OK", "state": "READY"}


def mark_rejected(position_id, reason):
    """
    Mark a position as REJECTED — will not be traded.
    Examples: score too low, market in bear regime,
              bucket at max positions, daily loss limit hit.

    Rejected positions move to WATCHLIST after a reset
    so they can be re-evaluated tomorrow.
    """
    df = load_lifecycle()
    df = _update_position_state(df, position_id, "REJECTED", {
        "Rejection_Reason": reason,
    })
    save_lifecycle(df)
    return {"status": "OK", "state": "REJECTED", "reason": reason}


# ════════════════════════════════════════════════
# POSITION ENTRY
# Called when BUY is executed
# ════════════════════════════════════════════════

def mark_entered(position_id, buy_price, quantity, buy_value):
    """
    Mark a position as ENTERED after BUY is executed.
    Calculates hard stop and target prices from buy price.
    Initialises peak price = buy price (trailing stop starts here).

    Called by: execution_loop after bucket_buy() succeeds.
    """
    hard_stop   = round(buy_price * (1 - STOP_LOSS_PCT),     2)
    target      = round(buy_price * (1 + TARGET_PROFIT_PCT), 2)
    trail_stop  = round(buy_price * (1 - TRAILING_STOP_PCT), 2)

    df = load_lifecycle()
    df = _update_position_state(df, position_id, "ENTERED", {
        "Buy_Price":        buy_price,
        "Buy_Date":         datetime.now().strftime('%Y-%m-%d'),
        "Quantity":         quantity,
        "Buy_Value":        buy_value,
        "Current_Price":    buy_price,
        "Current_PNL_Pct":  0.0,
        "Peak_Price":       buy_price,       # trailing starts at entry
        "Trail_Stop_Price": trail_stop,      # initial trail price
        "Hard_Stop_Price":  hard_stop,
        "Target_Price":     target,
        "Partial_Sold":     False,
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
# POSITION MONITORING
# Called on every price update — the heartbeat
# ════════════════════════════════════════════════

def update_position_price(position_id, current_price):
    """
    Update a live position with the latest price.
    This is called by the execution loop on every tick.

    It does FIVE things:
    1. Updates current price and P&L %
    2. Updates peak price if new high reached
    3. Updates trailing stop if price moved up
    4. Transitions to HOLDING if just entered
    5. Detects if trailing stop should activate
    6. Returns a recommended ACTION

    Return value:
    {
        "action":       "HOLD" / "SELL_STOP" / "SELL_TARGET" /
                        "SELL_TRAIL" / "PARTIAL_EXIT" / "TRAIL_ACTIVATED",
        "pnl_pct":      current P&L %,
        "peak_price":   highest price seen,
        "trail_stop":   current trailing stop price,
        "state":        current state after update,
        "reason":       plain English reason for action
    }
    """
    df   = load_lifecycle()
    mask = df["Position_ID"] == position_id

    if not mask.any():
        return {"action": "ERROR", "reason": f"Position {position_id} not found"}

    row = df.loc[mask].iloc[0]
    state = row["State"]

    # Only update live positions
    if state not in {"ENTERED", "HOLDING", "TRAILING", "PARTIAL_EXIT"}:
        return {"action": "NO_ACTION", "reason": f"Position in {state} — not live"}

    # ── Recalculate metrics ────────────────────────
    buy_price   = float(row["Buy_Price"])
    pnl_pct     = round(((current_price - buy_price) / buy_price) * 100, 3)
    peak_price  = max(float(row["Peak_Price"]), current_price)

    # Recalculate trailing stop based on new peak
    trail_stop  = round(peak_price * (1 - TRAILING_STOP_PCT), 2)
    hard_stop   = float(row["Hard_Stop_Price"])
    target      = float(row["Target_Price"])

    # Convert flags safely — CSV stores everything as strings
    partial_sold = str(row.get("Partial_Sold", "False")).strip().lower() in ("true", "1", "yes")

    # Determine days held
    try:
        buy_date  = pd.to_datetime(row["Buy_Date"]).date()
        days_held = (date.today() - buy_date).days
    except Exception:
        days_held = 0

    # ── Determine recommended action ──────────────
    action = "HOLD"
    reason = "Within normal range — no action needed"

    # Priority 1: Hard stop loss (most urgent)
    if current_price <= hard_stop:
        action = "SELL_STOP"
        reason = (
            f"Hard stop loss hit. "
            f"Bought ₹{buy_price} → Stop ₹{hard_stop} → Now ₹{current_price} "
            f"({pnl_pct:.1f}%)"
        )

    # Priority 2: Profit target
    elif current_price >= target:
        action = "SELL_TARGET"
        reason = (
            f"Profit target reached! "
            f"Bought ₹{buy_price} → Target ₹{target} → Now ₹{current_price} "
            f"(+{pnl_pct:.1f}%)"
        )

    # Priority 3: Trailing stop triggered (only when trailing is active)
    elif state == "TRAILING" and current_price <= trail_stop:
        action = "SELL_TRAIL"
        reason = (
            f"Trailing stop triggered. "
            f"Peak ₹{peak_price} → Trail Stop ₹{trail_stop} → Now ₹{current_price} "
            f"(locked in ~{round(((peak_price - buy_price)/buy_price)*100, 1)}% peak gain)"
        )

    # Priority 4: Activate trailing stop (transition HOLDING → TRAILING)
    elif (
        USE_TRAILING_STOP
        and pnl_pct >= (TRAIL_ACTIVATION_PCT * 100)
        and state in {"HOLDING", "ENTERED"}
    ):
        action = "TRAIL_ACTIVATED"
        reason = (
            f"Trailing stop activated at {pnl_pct:.1f}% gain. "
            f"Trail stop now at ₹{trail_stop} (moves up with price)."
        )

    # Priority 5: Partial exit (only once)
    elif (
        not partial_sold
        and pnl_pct >= (PARTIAL_EXIT_TRIGGER_PCT * 100)
        and state in {"HOLDING", "ENTERED", "TRAILING"}
    ):
        action = "PARTIAL_EXIT"
        reason = (
            f"Partial exit trigger reached at {pnl_pct:.1f}% gain. "
            f"Sell 50% of position to lock in profit, keep rest running."
        )

    # ── Determine new state ────────────────────────
    new_state = state   # default: no change

    if action == "TRAIL_ACTIVATED":
        new_state = "TRAILING"
    elif action == "PARTIAL_EXIT":
        new_state = "PARTIAL_EXIT"
    elif state == "ENTERED":
        new_state = "HOLDING"   # first update after entry → HOLDING

    # ── Apply updates to DataFrame ─────────────────
    updates = {
        "Current_Price":    current_price,
        "Current_PNL_Pct":  pnl_pct,
        "Peak_Price":       peak_price,
        "Trail_Stop_Price": trail_stop,
        "Days_Held":        days_held,
    }

    # Only do a state transition if state changed
    if new_state != state:
        df = _update_position_state(df, position_id, new_state, updates)
    else:
        # Just update price fields without a state transition
        # Cast to str to avoid pandas dtype conflicts
        mask = df["Position_ID"] == position_id
        for col, val in updates.items():
            df.loc[mask, col] = str(val)
        df.loc[mask, "Last_Updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    save_lifecycle(df)

    return {
        "action":       action,
        "pnl_pct":      pnl_pct,
        "peak_price":   peak_price,
        "trail_stop":   trail_stop,
        "hard_stop":    hard_stop,
        "target":       target,
        "days_held":    days_held,
        "state":        new_state,
        "reason":       reason,
    }


# ════════════════════════════════════════════════
# POSITION EXIT
# Called when a position is fully closed
# ════════════════════════════════════════════════

def mark_exited(position_id, exit_price, exit_reason):
    """
    Mark a position as EXITED.
    Records exit price, reason, and final P&L.
    Triggers cooldown if exit reason was a stop loss.

    exit_reason: "STOP_LOSS" / "TARGET" / "TRAIL_STOP" /
                 "SIGNAL_EXIT" / "MANUAL" / "TIME_EXIT"
    """
    df   = load_lifecycle()
    mask = df["Position_ID"] == position_id

    if not mask.any():
        return {"status": "ERROR", "reason": "Position not found"}

    row       = df.loc[mask].iloc[0]
    buy_price = float(row["Buy_Price"])
    pnl_pct   = round(((exit_price - buy_price) / buy_price) * 100, 3)

    # Calculate days held
    try:
        buy_date  = pd.to_datetime(row["Buy_Date"]).date()
        days_held = (date.today() - buy_date).days
    except Exception:
        days_held = 0

    df = _update_position_state(df, position_id, "EXITED", {
        "Exit_Price":    exit_price,
        "Exit_Date":     datetime.now().strftime('%Y-%m-%d'),
        "Exit_Reason":   exit_reason,
        "Current_PNL_Pct": pnl_pct,
        "Days_Held":     days_held,
    })
    save_lifecycle(df)

    # ── Trigger cooldown if stop loss hit ──────────
    if exit_reason == "STOP_LOSS":
        _trigger_cooldown(df, position_id, row["Stock"], row["Bucket"])

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
    Sets Partial_Sold = True so we don't trigger it again.
    Position remains ACTIVE (in PARTIAL_EXIT or TRAILING state).
    """
    df   = load_lifecycle()
    mask = df["Position_ID"] == position_id
    if not mask.any():
        return {"status": "ERROR", "reason": "Position not found"}

    df.loc[mask, "Partial_Sold"]  = "True"
    df.loc[mask, "Notes"]         = (
        str(df.loc[mask, 'Notes'].iloc[0]) + " | "
        f"Partial exit: {qty_sold} shares @ ₹{partial_price} "
        f"on {datetime.now().strftime('%Y-%m-%d')}"
    )
    df.loc[mask, "Last_Updated"]  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_lifecycle(df)

    return {"status": "OK", "partial_sold": True}


# ════════════════════════════════════════════════
# COOLDOWN MANAGEMENT
# After a stop loss, block re-entry for N days
# ════════════════════════════════════════════════

def _trigger_cooldown(df, position_id, stock, bucket):
    """
    Internal helper — called automatically when STOP_LOSS exits.
    Adds a new COOLDOWN row for this stock+bucket combination.
    This blocks the entry engine from re-buying for COOLDOWN_DAYS.
    """
    cooldown_until = (date.today() + timedelta(days=COOLDOWN_DAYS)).strftime('%Y-%m-%d')
    cooldown_id    = _generate_position_id(stock + "_COOLDOWN", bucket)

    new_row = {col: "" for col in LIFECYCLE_COLUMNS}
    new_row.update({
        "Position_ID":    cooldown_id,
        "Stock":          stock,
        "Bucket":         bucket,
        "State":          "COOLDOWN",
        "Cooldown_Until": cooldown_until,
        "Notes":          f"Cooldown after stop loss. Re-entry allowed after {cooldown_until}.",
        "Last_Updated":   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_lifecycle(df)
    return cooldown_until


def is_in_cooldown(stock, bucket):
    """
    Check if a stock is currently in cooldown for a given bucket.
    Returns (in_cooldown: bool, cooldown_until: str or None)

    Called by the entry engine before placing any BUY.
    If in cooldown → skip this stock, log REJECTED with reason.
    """
    df = load_lifecycle()
    if df.empty:
        return False, None

    cooldowns = df[
        (df["Stock"]  == stock)  &
        (df["Bucket"] == bucket) &
        (df["State"]  == "COOLDOWN")
    ]

    if cooldowns.empty:
        return False, None

    today_str = date.today().strftime('%Y-%m-%d')

    for _, row in cooldowns.iterrows():
        until = str(row.get("Cooldown_Until", ""))
        if until and until >= today_str:
            return True, until

    # All cooldowns have expired — clean them up
    expired_mask = (
        (df["Stock"]  == stock) &
        (df["Bucket"] == bucket) &
        (df["State"]  == "COOLDOWN")
    )
    df.loc[expired_mask, "State"] = "WATCHLIST"
    save_lifecycle(df)

    return False, None


def expire_cooldowns():
    """
    Scan all COOLDOWN positions and expire any that have passed.
    Move them back to WATCHLIST so they can be re-evaluated.
    Call this at the start of each trading day.
    """
    df        = load_lifecycle()
    today_str = date.today().strftime('%Y-%m-%d')
    expired   = []

    cooldown_mask = df["State"] == "COOLDOWN"
    for idx, row in df[cooldown_mask].iterrows():
        until = str(row.get("Cooldown_Until", ""))
        if until and until < today_str:
            df.loc[idx, "State"]        = "WATCHLIST"
            df.loc[idx, "Last_Updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            df.loc[idx, "Notes"]        = str(row["Notes"]) + " | Cooldown expired."
            expired.append(row["Stock"])

    if expired:
        save_lifecycle(df)

    return expired   # list of stocks now back in WATCHLIST


# ════════════════════════════════════════════════
# QUERY FUNCTIONS
# Used by the dashboard and execution loop
# ════════════════════════════════════════════════

def get_live_positions():
    """
    Return all currently LIVE positions.
    Live = ENTERED, HOLDING, TRAILING, or PARTIAL_EXIT.
    These are the positions the execution loop should monitor every tick.
    """
    df         = load_lifecycle()
    live_states= {"ENTERED", "HOLDING", "TRAILING", "PARTIAL_EXIT"}
    return df[df["State"].isin(live_states)].copy()


def get_ready_positions():
    """
    Return all positions in READY state.
    These are approved to enter on the next price tick.
    Used by execution_loop to fire the BUY.
    """
    df = load_lifecycle()
    return df[df["State"] == "READY"].copy()


def get_watchlist_positions():
    """
    Return all positions being watched but not yet entered.
    """
    df = load_lifecycle()
    return df[df["State"] == "WATCHLIST"].copy()


def get_position_by_id(position_id):
    """
    Get a single position row by its ID.
    Returns a dict or None if not found.
    """
    df   = load_lifecycle()
    mask = df["Position_ID"] == position_id
    if not mask.any():
        return None
    return df.loc[mask].iloc[0].to_dict()


def get_positions_by_stock(stock, bucket=None):
    """
    Get all lifecycle records for a stock.
    Optionally filter by bucket.
    Returns DataFrame — may include history (EXITED, COOLDOWN).
    """
    df = load_lifecycle()
    mask = df["Stock"] == stock
    if bucket:
        mask = mask & (df["Bucket"] == bucket)
    return df[mask].copy()


def get_cooldown_stocks(bucket=None):
    """
    Return list of stocks currently in cooldown.
    Optionally filter by bucket.
    Used by scanner to exclude blocked stocks.
    """
    df = load_lifecycle()
    today_str = date.today().strftime('%Y-%m-%d')

    mask = (df["State"] == "COOLDOWN") & (df["Cooldown_Until"] >= today_str)
    if bucket:
        mask = mask & (df["Bucket"] == bucket)

    return df[mask]["Stock"].tolist()


def get_full_history(include_exited=True, include_rejected=False):
    """
    Return full lifecycle history for all positions.
    Useful for the dashboard audit log.
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
        df = df[~df["State"].isin(excluded)]

    return df.sort_values("Last_Updated", ascending=False)


# ════════════════════════════════════════════════
# SUMMARY FOR DASHBOARD
# ════════════════════════════════════════════════

def get_lifecycle_summary():
    """
    Get a high-level summary of all position states.
    Used for the dashboard header metrics.

    Returns dict:
    {
        "live":         count of ENTERED+HOLDING+TRAILING+PARTIAL_EXIT,
        "watchlist":    count of WATCHLIST,
        "ready":        count of READY,
        "cooldown":     count of active cooldowns,
        "exited_today": count of positions exited today,
        "total":        total records,
    }
    """
    df        = load_lifecycle()
    today_str = date.today().strftime('%Y-%m-%d')

    live_states = {"ENTERED", "HOLDING", "TRAILING", "PARTIAL_EXIT"}

    summary = {
        "live":         len(df[df["State"].isin(live_states)]),
        "watchlist":    len(df[df["State"] == "WATCHLIST"]),
        "ready":        len(df[df["State"] == "READY"]),
        "cooldown":     len(df[
            (df["State"] == "COOLDOWN") &
            (df["Cooldown_Until"] >= today_str)
        ]),
        "exited_today": len(df[
            (df["State"] == "EXITED") &
            (df["Exit_Date"] == today_str)
        ]),
        "total":        len(df),
    }

    return summary


def get_lifecycle_display_df():
    """
    Return a clean, dashboard-ready DataFrame of all live positions.
    Selects and renames the most useful columns for display.
    Shows live + ready + watchlist + cooldown (not exited).
    """
    df = load_lifecycle()
    if df.empty:
        return pd.DataFrame()

    # Exclude fully exited and rejected positions from the main view
    active_states = {
        "WATCHLIST", "READY", "ENTERED", "HOLDING",
        "TRAILING", "PARTIAL_EXIT", "COOLDOWN"
    }
    df = df[df["State"].isin(active_states)].copy()

    if df.empty:
        return pd.DataFrame()

    # Select display columns
    display_cols = [
        "Stock", "Bucket", "State",
        "Buy_Price", "Current_Price", "Current_PNL_Pct",
        "Peak_Price", "Trail_Stop_Price", "Hard_Stop_Price",
        "Target_Price", "Days_Held", "Partial_Sold",
        "Cooldown_Until", "Composite_Score",
    ]
    existing = [c for c in display_cols if c in df.columns]
    result   = df[existing].copy()

    # Format numeric columns
    for col in ["Buy_Price", "Current_Price", "Peak_Price",
                "Trail_Stop_Price", "Hard_Stop_Price", "Target_Price"]:
        if col in result.columns:
            result[col] = result[col].apply(
                lambda x: f"₹{float(x):.2f}" if x not in ("", None) and str(x).replace('.','').isdigit() else x
            )

    if "Current_PNL_Pct" in result.columns:
        result["Current_PNL_Pct"] = result["Current_PNL_Pct"].apply(
            lambda x: f"{float(x):+.2f}%" if x not in ("", None) and str(x).lstrip('-').replace('.','').isdigit() else x
        )

    # Rename for cleaner display
    result = result.rename(columns={
        "Current_PNL_Pct":  "P&L %",
        "Trail_Stop_Price": "Trail Stop ₹",
        "Hard_Stop_Price":  "Hard Stop ₹",
        "Target_Price":     "Target ₹",
        "Buy_Price":        "Buy ₹",
        "Current_Price":    "Now ₹",
        "Peak_Price":       "Peak ₹",
        "Composite_Score":  "Score",
        "Days_Held":        "Days",
        "Partial_Sold":     "Half Sold?",
        "Cooldown_Until":   "Cooldown Till",
    })

    return result.reset_index(drop=True)


def get_state_color(state):
    """
    Return a color string for a lifecycle state.
    Used by the dashboard for conditional formatting.
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
