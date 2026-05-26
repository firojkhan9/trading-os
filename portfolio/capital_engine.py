# ================================================
# FILE: portfolio/capital_engine.py
# PURPOSE: Capital Allocation Engine — Milestone 24
#
# Manages three independent capital buckets:
#   1. Long-Term  — fundamentals + trend (weeks/months)
#   2. Swing      — momentum + EMA + RS  (days/weeks)
#   3. Intraday   — volume + ATR         (same day, future)
#
# Each bucket is completely independent:
#   - own capital pool
#   - own available cash
#   - own deployed capital tracking
#   - own position count limit
#   - own max position size
#   - own performance tracking
#
# DATA STORAGE — TWO LAYERS:
#   Primary  : Supabase (cloud PostgreSQL) — survives Cloud restarts
#   Fallback : logs/bucket_trades.csv + logs/bucket_state.csv (local)
#
#   Both layers written on every save. Supabase used on Cloud,
#   CSV used on laptop. See supabase_setup.sql for table scripts.
#
# HOW IT WORKS:
#   - BUY  → deducts from bucket's available cash
#   - SELL → returns proceeds to bucket's available cash
#   - P&L  → tracked per bucket independently
#   - No cross-bucket capital movement (enforced)
# ================================================

import pandas as pd
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Supabase client ───────────────────────────────
try:
    from config.supabase_client import get_client as _get_supabase_client
except ImportError:
    def _get_supabase_client():
        return None

# ── File paths ────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR          = os.path.join(BASE_DIR, "logs")
BUCKET_TRADES_FILE= os.path.join(LOGS_DIR, "bucket_trades.csv")
BUCKET_STATE_FILE = os.path.join(LOGS_DIR, "bucket_state.csv")

# Create logs folder if it doesn't exist
os.makedirs(LOGS_DIR, exist_ok=True)


# ════════════════════════════════════════════════
# BUCKET CONFIGURATION
# Change these numbers here OR override via
# Google Sheets settings in the future.
# ════════════════════════════════════════════════

# Total paper trading capital
TOTAL_CAPITAL = 500000   # ₹5,00,000

# Bucket allocation as % of total capital
BUCKET_CONFIG = {
    "Long-Term": {
        "allocation_pct":   0.60,        # 60% = ₹3,00,000
        "max_positions":    5,           # max stocks held at once
        "max_position_pct": 0.12,        # max 12% of bucket per stock
        "min_score":        70,          # min composite score to enter
        "min_holding_days": 20,          # don't sell before 20 days
        "max_holding_days": 365,         # force review after 1 year
        "strategy_style":   "FUNDAMENTAL+TREND",
        "description":      "Long-term investing — fundamentals + trend + RS",
        "color":            "#00cc66",   # green
    },
    "Swing": {
        "allocation_pct":   0.30,        # 30% = ₹1,50,000
        "max_positions":    5,
        "max_position_pct": 0.10,        # max 10% of bucket per stock
        "min_score":        60,          # slightly lower threshold
        "min_holding_days": 2,           # can exit after 2 days
        "max_holding_days": 15,          # force exit after 15 days
        "strategy_style":   "MOMENTUM+EMA+MACD",
        "description":      "Swing trading — momentum + EMA + MACD + RS",
        "color":            "#3399ff",   # blue
    },
    "Intraday": {
        "allocation_pct":   0.10,        # 10% = ₹50,000
        "max_positions":    3,
        "max_position_pct": 0.33,        # max 33% of bucket per trade
        "min_score":        55,
        "min_holding_days": 0,           # same-day exit
        "max_holding_days": 1,           # must exit by end of day
        "strategy_style":   "VWAP+VOLUME+ATR",
        "description":      "Intraday trading — VWAP + volume + ATR (future)",
        "color":            "#ff9900",   # orange
    },
}


# ════════════════════════════════════════════════
# BUCKET STATE MANAGEMENT
# Two-layer storage: Supabase (primary) → CSV (fallback)
# Supabase table: bucket_state  (upsert on bucket column)
# Supabase table: bucket_trades (append only)
# ════════════════════════════════════════════════

def _make_default_state():
    """Build the default starting state dict for all buckets."""
    state = {}
    for bucket_name, cfg in BUCKET_CONFIG.items():
        starting = round(TOTAL_CAPITAL * cfg["allocation_pct"], 2)
        state[bucket_name] = {
            "Starting_Capital": starting,
            "Available_Cash":   starting,
            "Deployed_Capital": 0.0,
            "Total_PNL":        0.0,
            "Total_Trades":     0,
            "Winning_Trades":   0,
            "Last_Updated":     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    return state


def _initialize_bucket_state():
    """
    Create initial bucket state on first run.
    Writes to both Supabase and CSV so both start populated.
    """
    state = _make_default_state()
    save_bucket_state(state)   # writes to Supabase + CSV
    return state


def load_bucket_state():
    """
    Load current state of all three buckets.

    Priority:
      1. Supabase — persists across Cloud restarts
      2. Local CSV — works on laptop
      3. Defaults  — first run with no data anywhere

    Returns a dict keyed by bucket name:
    {
        "Long-Term": { "Starting_Capital": 300000, "Available_Cash": 285000, ... },
        "Swing":     { ... },
        "Intraday":  { ... },
    }
    """
    df = None

    # ── Layer 1: Supabase ─────────────────────────
    client = _get_supabase_client()
    if client:
        try:
            response = client.table("bucket_state").select("*").execute()
            if response.data:
                df = pd.DataFrame(response.data)
                # Supabase returns lowercase column names
                df = df.rename(columns={
                    "bucket":           "Bucket",
                    "starting_capital": "Starting_Capital",
                    "available_cash":   "Available_Cash",
                    "deployed_capital": "Deployed_Capital",
                    "total_pnl":        "Total_PNL",
                    "total_trades":     "Total_Trades",
                    "winning_trades":   "Winning_Trades",
                    "last_updated":     "Last_Updated",
                })
        except Exception as e:
            print(f"Supabase bucket_state load failed: {e} — using CSV")

    # ── Layer 2: CSV fallback ─────────────────────
    if df is None:
        if os.path.exists(BUCKET_STATE_FILE):
            try:
                df = pd.read_csv(BUCKET_STATE_FILE)
            except Exception:
                pass

    # ── Layer 3: Defaults (first run) ────────────
    if df is None or df.empty:
        return _make_default_state()

    # Convert to dict
    state = {}
    for _, row in df.iterrows():
        try:
            state[str(row["Bucket"])] = {
                "Starting_Capital": float(row["Starting_Capital"]),
                "Available_Cash":   float(row["Available_Cash"]),
                "Deployed_Capital": float(row["Deployed_Capital"]),
                "Total_PNL":        float(row["Total_PNL"]),
                "Total_Trades":     int(float(row["Total_Trades"])),
                "Winning_Trades":   int(float(row["Winning_Trades"])),
                "Last_Updated":     str(row["Last_Updated"]),
            }
        except Exception:
            continue

    # Add any missing buckets
    for bucket_name, cfg in BUCKET_CONFIG.items():
        if bucket_name not in state:
            starting = round(TOTAL_CAPITAL * cfg["allocation_pct"], 2)
            state[bucket_name] = {
                "Starting_Capital": starting,
                "Available_Cash":   starting,
                "Deployed_Capital": 0.0,
                "Total_PNL":        0.0,
                "Total_Trades":     0,
                "Winning_Trades":   0,
                "Last_Updated":     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }

    return state


def save_bucket_state(state):
    """
    Save bucket state to Supabase (primary) and CSV (fallback).
    Called after every BUY or SELL.
    Supabase upserts on bucket name so there is never a duplicate row.
    """
    rows = []
    for bucket_name, data in state.items():
        row = {"Bucket": bucket_name}
        row.update(data)
        row["Last_Updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows.append(row)

    # ── Layer 1: Supabase ─────────────────────────
    client = _get_supabase_client()
    if client:
        try:
            records = [
                {
                    "bucket":           r["Bucket"],
                    "starting_capital": r["Starting_Capital"],
                    "available_cash":   r["Available_Cash"],
                    "deployed_capital": r["Deployed_Capital"],
                    "total_pnl":        r["Total_PNL"],
                    "total_trades":     r["Total_Trades"],
                    "winning_trades":   r["Winning_Trades"],
                    "last_updated":     r["Last_Updated"],
                }
                for r in rows
            ]
            client.table("bucket_state").upsert(
                records, on_conflict="bucket"
            ).execute()
        except Exception as e:
            print(f"Supabase bucket_state save failed: {e} — saved to CSV only")

    # ── Layer 2: CSV (always) ─────────────────────
    try:
        pd.DataFrame(rows).to_csv(BUCKET_STATE_FILE, index=False)
    except Exception as e:
        print(f"CSV bucket_state save failed: {e}")


def reset_bucket_state():
    """
    Reset ALL buckets back to starting capital.
    USE WITH CARE — clears ALL trade history from Supabase AND CSV.
    Called only when user explicitly resets from the dashboard.
    """
    # ── Clear Supabase ────────────────────────────
    client = _get_supabase_client()
    if client:
        try:
            # Delete all rows from both tables
            client.table("bucket_trades").delete().neq("bucket", "").execute()
            client.table("bucket_state").delete().neq("bucket", "").execute()
        except Exception as e:
            print(f"Supabase reset failed: {e}")

    # ── Clear CSV files ───────────────────────────
    for f in [BUCKET_STATE_FILE, BUCKET_TRADES_FILE]:
        if os.path.exists(f):
            os.remove(f)

    return _initialize_bucket_state()


# ════════════════════════════════════════════════
# BUCKET TRADE LOGGING
# Every trade logged separately from the old
# paper_trades.csv — bucket-aware audit trail
# ════════════════════════════════════════════════

def _log_bucket_trade(bucket, action, stock, price, quantity, value, pnl=None):
    """
    Log a trade to Supabase (primary) and bucket_trades.csv (fallback).
    Append-only — each trade becomes a new row, never updated.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    pnl_val   = round(pnl, 2) if pnl is not None else None

    # ── Layer 1: Supabase ─────────────────────────
    client = _get_supabase_client()
    if client:
        try:
            client.table("bucket_trades").insert({
                "timestamp": timestamp,
                "bucket":    bucket,
                "action":    action,
                "stock":     stock,
                "price":     round(price, 2),
                "quantity":  quantity,
                "value":     round(value, 2),
                "pnl":       pnl_val,
            }).execute()
        except Exception as e:
            print(f"Supabase bucket_trades insert failed: {e} — saved to CSV only")

    # ── Layer 2: CSV (always) ─────────────────────
    try:
        entry = {
            "Timestamp": timestamp,
            "Bucket":    bucket,
            "Action":    action,
            "Stock":     stock,
            "Price":     round(price, 2),
            "Quantity":  quantity,
            "Value":     round(value, 2),
            "PNL":       pnl_val if pnl_val is not None else "",
        }
        df = pd.DataFrame([entry])
        if os.path.exists(BUCKET_TRADES_FILE):
            df.to_csv(BUCKET_TRADES_FILE, mode='a', header=False, index=False)
        else:
            df.to_csv(BUCKET_TRADES_FILE, mode='w', header=True, index=False)
    except Exception as e:
        print(f"CSV bucket_trades save failed: {e}")


def load_bucket_trades():
    """
    Load full bucket trade history.
    Tries Supabase first, falls back to CSV.
    """
    COLS = ["Timestamp", "Bucket", "Action", "Stock",
            "Price", "Quantity", "Value", "PNL"]

    # ── Layer 1: Supabase ─────────────────────────
    client = _get_supabase_client()
    if client:
        try:
            response = (
                client.table("bucket_trades")
                .select("*")
                .order("timestamp", desc=False)
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "timestamp": "Timestamp",
                    "bucket":    "Bucket",
                    "action":    "Action",
                    "stock":     "Stock",
                    "price":     "Price",
                    "quantity":  "Quantity",
                    "value":     "Value",
                    "pnl":       "PNL",
                })
                return df[[c for c in COLS if c in df.columns]]
            return pd.DataFrame(columns=COLS)
        except Exception as e:
            print(f"Supabase bucket_trades load failed: {e} — using CSV")

    # ── Layer 2: CSV fallback ─────────────────────
    if os.path.exists(BUCKET_TRADES_FILE):
        try:
            return pd.read_csv(BUCKET_TRADES_FILE)
        except Exception:
            pass

    return pd.DataFrame(columns=COLS)


# ════════════════════════════════════════════════
# CAPITAL CHECKS
# Before any trade, check if bucket can take it
# ════════════════════════════════════════════════

def get_bucket_available_cash(bucket_name):
    """
    How much cash is available in this bucket right now.
    This is what's left after all open positions are accounted for.
    """
    state = load_bucket_state()
    if bucket_name not in state:
        return 0.0
    return state[bucket_name]["Available_Cash"]


def get_max_position_size(bucket_name, price):
    """
    Calculate the maximum number of shares we can buy
    in this bucket for this stock.

    Respects both:
    1. max_position_pct (% of bucket's starting capital)
    2. available_cash (can't spend more than we have)

    Returns (quantity, spend_amount, reason_if_rejected)
    """
    state  = load_bucket_state()
    cfg    = BUCKET_CONFIG.get(bucket_name, {})

    if bucket_name not in state:
        return 0, 0, f"Bucket '{bucket_name}' not found"

    available   = state[bucket_name]["Available_Cash"]
    starting    = state[bucket_name]["Starting_Capital"]
    max_pct     = cfg.get("max_position_pct", 0.10)

    # Max spend = max_position_pct of starting capital
    max_spend   = round(starting * max_pct, 2)

    # Can't spend more than available
    actual_spend = min(max_spend, available)

    if actual_spend < price:
        return 0, 0, f"Insufficient cash in {bucket_name} bucket (₹{available:,.0f} available, price ₹{price:,.0f})"

    quantity = int(actual_spend // price)

    if quantity == 0:
        return 0, 0, f"Price ₹{price:,.0f} too high for position size in {bucket_name}"

    return quantity, round(quantity * price, 2), ""


def check_position_limit(bucket_name):
    """
    Check if this bucket already has too many open positions.
    Returns (can_trade: bool, open_count: int, max_allowed: int)
    """
    trades_df = load_bucket_trades()
    cfg       = BUCKET_CONFIG.get(bucket_name, {})
    max_pos   = cfg.get("max_positions", 5)

    if trades_df.empty:
        return True, 0, max_pos

    # Count stocks that have been bought but not yet sold in this bucket
    bucket_trades = trades_df[trades_df["Bucket"] == bucket_name]
    buys  = set(bucket_trades[bucket_trades["Action"] == "BUY"]["Stock"].tolist())
    sells = set(bucket_trades[bucket_trades["Action"] == "SELL"]["Stock"].tolist())
    open_positions = buys - sells   # bought but not sold

    open_count = len(open_positions)
    can_trade  = open_count < max_pos

    return can_trade, open_count, max_pos


def check_score_threshold(bucket_name, composite_score):
    """
    Check if a stock's composite score meets this bucket's minimum.
    Returns (approved: bool, min_required: int, reason: str)
    """
    cfg         = BUCKET_CONFIG.get(bucket_name, {})
    min_score   = cfg.get("min_score", 60)
    approved    = composite_score >= min_score
    reason      = "" if approved else f"Score {composite_score}/100 below {bucket_name} minimum ({min_score})"
    return approved, min_score, reason


# ════════════════════════════════════════════════
# BUY AND SELL — BUCKET-AWARE EXECUTION
# ════════════════════════════════════════════════

def bucket_buy(bucket_name, stock_name, price, composite_score=None):
    """
    Execute a paper BUY from a specific bucket.

    Checks (in order):
    1. Bucket exists and has cash
    2. Position limit not exceeded
    3. Score threshold met (if score provided)
    4. Position size calculation
    5. Execute and update state

    Returns a result dict with status and details.
    """
    state = load_bucket_state()

    # ── Check 1: Bucket exists ────────────────────
    if bucket_name not in state:
        return {
            "status":  "REJECTED",
            "reason":  f"Unknown bucket: {bucket_name}",
            "bucket":  bucket_name,
        }

    # ── Check 2: Already holding this stock ───────
    trades_df = load_bucket_trades()
    if not trades_df.empty:
        b_trades = trades_df[trades_df["Bucket"] == bucket_name]
        buys  = set(b_trades[b_trades["Action"] == "BUY"]["Stock"].tolist())
        sells = set(b_trades[b_trades["Action"] == "SELL"]["Stock"].tolist())
        if stock_name in (buys - sells):
            return {
                "status":  "REJECTED",
                "reason":  f"Already holding {stock_name} in {bucket_name} bucket",
                "bucket":  bucket_name,
            }

    # ── Check 3: Position limit ───────────────────
    can_trade, open_count, max_pos = check_position_limit(bucket_name)
    if not can_trade:
        return {
            "status":  "REJECTED",
            "reason":  f"{bucket_name} bucket at max positions ({open_count}/{max_pos})",
            "bucket":  bucket_name,
        }

    # ── Check 4: Score threshold ──────────────────
    if composite_score is not None:
        approved, min_score, reason = check_score_threshold(bucket_name, composite_score)
        if not approved:
            return {
                "status":  "REJECTED",
                "reason":  reason,
                "bucket":  bucket_name,
                "score":   composite_score,
                "min_score": min_score,
            }

    # ── Check 5: Position size ────────────────────
    quantity, spend, err = get_max_position_size(bucket_name, price)
    if quantity == 0:
        return {
            "status":  "REJECTED",
            "reason":  err,
            "bucket":  bucket_name,
        }

    # ── Execute BUY ───────────────────────────────
    state[bucket_name]["Available_Cash"]   = round(
        state[bucket_name]["Available_Cash"] - spend, 2
    )
    state[bucket_name]["Deployed_Capital"] = round(
        state[bucket_name]["Deployed_Capital"] + spend, 2
    )
    state[bucket_name]["Total_Trades"] += 1

    save_bucket_state(state)
    _log_bucket_trade(bucket_name, "BUY", stock_name, price, quantity, spend)

    return {
        "status":    "EXECUTED",
        "action":    "BUY",
        "bucket":    bucket_name,
        "stock":     stock_name,
        "price":     round(price, 2),
        "quantity":  quantity,
        "value":     spend,
        "cash_left": state[bucket_name]["Available_Cash"],
    }


def bucket_sell(bucket_name, stock_name, price):
    """
    Execute a paper SELL from a specific bucket.

    Finds the original BUY trade to calculate P&L.
    Updates bucket state with proceeds and P&L.

    Returns a result dict with status, P&L, and details.
    """
    state     = load_bucket_state()
    trades_df = load_bucket_trades()

    if bucket_name not in state:
        return {
            "status": "REJECTED",
            "reason": f"Unknown bucket: {bucket_name}",
        }

    if trades_df.empty:
        return {
            "status": "REJECTED",
            "reason": f"No trades found in {bucket_name} bucket",
        }

    # Find the most recent BUY for this stock in this bucket
    b_trades    = trades_df[
        (trades_df["Bucket"] == bucket_name) &
        (trades_df["Stock"]  == stock_name)  &
        (trades_df["Action"] == "BUY")
    ]

    if b_trades.empty:
        return {
            "status": "REJECTED",
            "reason": f"No open position in {stock_name} in {bucket_name} bucket",
        }

    # Get the most recent BUY
    buy_row   = b_trades.iloc[-1]
    buy_price = float(buy_row["Price"])
    quantity  = int(buy_row["Quantity"])
    buy_value = float(buy_row["Value"])

    # Calculate P&L
    sell_value = round(quantity * price, 2)
    pnl        = round(sell_value - buy_value, 2)
    pnl_pct    = round((pnl / buy_value) * 100, 2)

    # Update bucket state
    state[bucket_name]["Available_Cash"]   = round(
        state[bucket_name]["Available_Cash"] + sell_value, 2
    )
    state[bucket_name]["Deployed_Capital"] = round(
        max(0, state[bucket_name]["Deployed_Capital"] - buy_value), 2
    )
    state[bucket_name]["Total_PNL"] = round(
        state[bucket_name]["Total_PNL"] + pnl, 2
    )
    if pnl >= 0:
        state[bucket_name]["Winning_Trades"] += 1

    save_bucket_state(state)
    _log_bucket_trade(bucket_name, "SELL", stock_name, price, quantity, sell_value, pnl)

    return {
        "status":    "EXECUTED",
        "action":    "SELL",
        "bucket":    bucket_name,
        "stock":     stock_name,
        "price":     round(price, 2),
        "quantity":  quantity,
        "value":     sell_value,
        "pnl":       pnl,
        "pnl_pct":   pnl_pct,
        "cash_now":  state[bucket_name]["Available_Cash"],
    }


# ════════════════════════════════════════════════
# PORTFOLIO SUMMARY — for dashboard display
# ════════════════════════════════════════════════

def get_bucket_summary():
    """
    Get a full summary of all three buckets for dashboard display.

    Returns a list of dicts — one per bucket — with:
    - Name, starting capital, available cash, deployed capital
    - Total P&L (₹ and %)
    - Win rate
    - Utilization % (how much of bucket is deployed)
    - Open position count
    """
    state     = load_bucket_state()
    trades_df = load_bucket_trades()
    summary   = []

    for bucket_name, cfg in BUCKET_CONFIG.items():
        data = state.get(bucket_name, {})

        starting   = data.get("Starting_Capital", 0)
        available  = data.get("Available_Cash",   0)
        deployed   = data.get("Deployed_Capital", 0)
        total_pnl  = data.get("Total_PNL",        0)
        total_tr   = data.get("Total_Trades",     0)
        winning_tr = data.get("Winning_Trades",   0)

        # Utilization = % of starting capital currently deployed
        utilization = round((deployed / starting * 100), 1) if starting > 0 else 0

        # Win rate
        win_rate = round((winning_tr / total_tr * 100), 1) if total_tr > 0 else 0

        # Return % vs starting capital
        pnl_pct = round((total_pnl / starting * 100), 2) if starting > 0 else 0

        # Open positions count
        open_count = 0
        if not trades_df.empty:
            b_trades = trades_df[trades_df["Bucket"] == bucket_name]
            buys     = set(b_trades[b_trades["Action"] == "BUY"]["Stock"].tolist())
            sells    = set(b_trades[b_trades["Action"] == "SELL"]["Stock"].tolist())
            open_count = len(buys - sells)

        summary.append({
            "Bucket":         bucket_name,
            "Style":          cfg["strategy_style"],
            "Starting ₹":     starting,
            "Available ₹":    available,
            "Deployed ₹":     deployed,
            "Utilization":    f"{utilization}%",
            "Open Positions": f"{open_count}/{cfg['max_positions']}",
            "Total P&L ₹":   total_pnl,
            "Return %":       f"{pnl_pct:+.2f}%",
            "Win Rate":       f"{win_rate}%",
            "Total Trades":   total_tr,
        })

    return summary


def get_portfolio_totals():
    """
    Get aggregate totals across all three buckets.
    Used for the headline metrics at top of Portfolio Buckets tab.
    """
    state   = load_bucket_state()
    totals  = {
        "total_starting":  0,
        "total_available": 0,
        "total_deployed":  0,
        "total_pnl":       0,
        "total_trades":    0,
        "winning_trades":  0,
    }

    for bucket_name, data in state.items():
        totals["total_starting"]  += data.get("Starting_Capital", 0)
        totals["total_available"] += data.get("Available_Cash",   0)
        totals["total_deployed"]  += data.get("Deployed_Capital", 0)
        totals["total_pnl"]       += data.get("Total_PNL",        0)
        totals["total_trades"]    += data.get("Total_Trades",     0)
        totals["winning_trades"]  += data.get("Winning_Trades",   0)

    totals["total_return_pct"] = round(
        (totals["total_pnl"] / totals["total_starting"] * 100), 2
    ) if totals["total_starting"] > 0 else 0

    totals["overall_win_rate"] = round(
        (totals["winning_trades"] / totals["total_trades"] * 100), 1
    ) if totals["total_trades"] > 0 else 0

    return totals


def get_open_positions_by_bucket(bucket_name):
    """
    Get list of currently open positions in a specific bucket.
    Returns list of stock names.
    """
    trades_df = load_bucket_trades()
    if trades_df.empty:
        return []

    b_trades = trades_df[trades_df["Bucket"] == bucket_name]
    buys     = set(b_trades[b_trades["Action"] == "BUY"]["Stock"].tolist())
    sells    = set(b_trades[b_trades["Action"] == "SELL"]["Stock"].tolist())
    return list(buys - sells)


def get_bucket_trade_history(bucket_name=None):
    """
    Get trade history for a specific bucket, or all buckets.
    Returns a DataFrame filtered by bucket if specified.
    """
    df = load_bucket_trades()
    if df.empty:
        return df
    if bucket_name:
        return df[df["Bucket"] == bucket_name].copy()
    return df


def suggest_bucket_for_stock(composite_score, holding_period_preference="swing"):
    """
    Given a stock's composite score and preferred holding period,
    suggest which bucket is most appropriate.

    This is a helper used by the orchestrator (Milestone 31).
    For now it uses simple rules — will become more sophisticated later.

    Returns bucket name string.
    """
    if holding_period_preference == "long":
        # Long-term: needs high score + fundamentals
        if composite_score >= BUCKET_CONFIG["Long-Term"]["min_score"]:
            return "Long-Term"
        else:
            return None  # Not good enough for any bucket

    elif holding_period_preference == "intraday":
        return "Intraday"

    else:
        # Default: swing trading
        if composite_score >= BUCKET_CONFIG["Swing"]["min_score"]:
            return "Swing"
        elif composite_score >= BUCKET_CONFIG["Long-Term"]["min_score"]:
            return "Long-Term"
        else:
            return None  # Below all thresholds — no trade
