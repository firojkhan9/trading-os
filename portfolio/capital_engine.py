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
# Use the EXACT same import pattern as paper_trader.py.
# Direct import — no try/except that swallows real errors.
# If secrets are missing → get_client() returns None → CSV fallback.
from config.supabase_client import get_client

# ── File paths ────────────────────────────────────
BASE_DIR           = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR           = os.path.join(BASE_DIR, "logs")
BUCKET_TRADES_FILE = os.path.join(LOGS_DIR, "bucket_trades.csv")
BUCKET_STATE_FILE  = os.path.join(LOGS_DIR, "bucket_state.csv")

os.makedirs(LOGS_DIR, exist_ok=True)


# ════════════════════════════════════════════════
# BUCKET CONFIGURATION
# ════════════════════════════════════════════════

TOTAL_CAPITAL = 600000   # ₹6,00,000

BUCKET_CONFIG = {
    "Long-Term": {
        "allocation_pct":   0.60,        # 60% = ₹3,60,000
        "max_positions":    5,
        "max_position_pct": 0.12,        # max 12% of bucket per stock
        "min_score":        70,          # min composite score to enter
        "min_holding_days": 20,
        "max_holding_days": 365,
        "strategy_style":   "FUNDAMENTAL+TREND",
        "description":      "Long-term investing — fundamentals + trend + RS",
        "color":            "#00cc66",
        # Signal indicators that suggest Long-Term
        "signal_keywords":  ["STRONG BUY"],
        "min_buy_votes":    3,           # needs 3-4 strategies to agree
    },
    "Swing": {
        "allocation_pct":   0.30,        # 30% = ₹1,80,000
        "max_positions":    5,
        "max_position_pct": 0.10,
        "min_score":        60,
        "min_holding_days": 2,
        "max_holding_days": 15,
        "strategy_style":   "MOMENTUM+EMA+MACD",
        "description":      "Swing trading — momentum + EMA + MACD + RS",
        "color":            "#3399ff",
        "signal_keywords":  ["BUY", "STRONG BUY"],
        "min_buy_votes":    2,
    },
    "Intraday": {
        "allocation_pct":   0.10,        # 10% = ₹60,000
        "max_positions":    3,
        "max_position_pct": 0.33,
        "min_score":        55,
        "min_holding_days": 0,
        "max_holding_days": 1,
        "strategy_style":   "VWAP+VOLUME+ATR",
        "description":      "Intraday trading — VWAP + volume + ATR (future)",
        "color":            "#ff9900",
        "signal_keywords":  ["BUY"],
        "min_buy_votes":    1,
    },
}


# ════════════════════════════════════════════════
# SMART BUCKET SUGGESTION
# Given a signal and score, suggest which bucket
# is most appropriate and explain why.
# ════════════════════════════════════════════════

def suggest_bucket(
    composite_score=None,
    combined_signal=None,
    buy_votes=None,
    regime=None,
    holding_preference=None,
):
    """
    Suggest the most appropriate bucket for a trade.
    Returns a dict with:
      - suggested_bucket : "Long-Term" / "Swing" / "Intraday" / None
      - reason           : plain English explanation
      - confidence       : "HIGH" / "MEDIUM" / "LOW"
      - alternatives     : other valid buckets

    Logic (checked in priority order):
      1. User preference overrides everything if provided
      2. If regime is BEAR → no suggestion (protect capital)
      3. Score >= 70 + STRONG BUY + 3+ votes → Long-Term
      4. Score >= 60 + BUY + 2+ votes        → Swing
      5. Score >= 55 + BUY + 1+ vote         → Intraday
      6. Below all thresholds                → no suggestion

    composite_score : int 0-100
    combined_signal : str e.g. "STRONG BUY" or "BUY"
    buy_votes       : int 0-4 (how many strategies say BUY)
    regime          : str e.g. "BULL" / "BEAR" / "SIDEWAYS"
    holding_preference : "long" / "swing" / "intraday" / None
    """
    # ── 0. Defaults ───────────────────────────────
    score   = composite_score or 0
    signal  = str(combined_signal or "").upper()
    votes   = buy_votes or 0
    regime_ = str(regime or "").upper()

    # ── 1. User preference shortcut ───────────────
    if holding_preference == "long":
        if score >= BUCKET_CONFIG["Long-Term"]["min_score"]:
            return {
                "suggested_bucket": "Long-Term",
                "reason":           "You selected Long-Term. Score meets minimum threshold.",
                "confidence":       "HIGH" if score >= 70 else "MEDIUM",
                "alternatives":     ["Swing"],
            }
    elif holding_preference == "intraday":
        return {
            "suggested_bucket": "Intraday",
            "reason":           "You selected Intraday.",
            "confidence":       "MEDIUM",
            "alternatives":     [],
        }

    # ── 2. Bear market → no new longs ─────────────
    if "BEAR" in regime_ and "WEAK" not in regime_:
        return {
            "suggested_bucket": None,
            "reason":           (
                "Market is in BEAR regime. "
                "No new longs recommended — protect capital."
            ),
            "confidence":       "HIGH",
            "alternatives":     [],
        }

    # ── 3. Long-Term: high score + strong conviction ──
    if (
        score >= BUCKET_CONFIG["Long-Term"]["min_score"] and
        "STRONG BUY" in signal and
        votes >= BUCKET_CONFIG["Long-Term"]["min_buy_votes"]
    ):
        alts = []
        if score >= BUCKET_CONFIG["Swing"]["min_score"]:
            alts.append("Swing")
        return {
            "suggested_bucket": "Long-Term",
            "reason": (
                f"Score {score}/100 is strong, {votes}/4 strategies agree, "
                f"STRONG BUY signal — good candidate for a longer hold."
            ),
            "confidence": "HIGH" if score >= 75 else "MEDIUM",
            "alternatives": alts,
        }

    # ── 4. Swing: decent score + majority agree ────
    if (
        score >= BUCKET_CONFIG["Swing"]["min_score"] and
        ("BUY" in signal) and
        votes >= BUCKET_CONFIG["Swing"]["min_buy_votes"]
    ):
        alts = []
        if score >= BUCKET_CONFIG["Long-Term"]["min_score"]:
            alts.append("Long-Term")
        return {
            "suggested_bucket": "Swing",
            "reason": (
                f"Score {score}/100, {votes}/4 strategies agree, "
                f"BUY signal — suited for a swing trade (days to weeks)."
            ),
            "confidence": "HIGH" if votes >= 3 else "MEDIUM",
            "alternatives": alts,
        }

    # ── 5. Intraday: weak signal, score borderline ─
    if (
        score >= BUCKET_CONFIG["Intraday"]["min_score"] and
        "BUY" in signal and
        votes >= BUCKET_CONFIG["Intraday"]["min_buy_votes"]
    ):
        return {
            "suggested_bucket": "Intraday",
            "reason": (
                f"Score {score}/100 and {votes}/4 strategies agree — "
                f"signal is not strong enough for overnight hold, "
                f"but may work as an intraday trade."
            ),
            "confidence": "LOW",
            "alternatives": [],
        }

    # ── 6. No clear suggestion ─────────────────────
    return {
        "suggested_bucket": None,
        "reason": (
            f"Score {score}/100, {votes}/4 strategies agree — "
            f"signal is too weak for any bucket. "
            f"Wait for a stronger setup."
        ),
        "confidence": "LOW",
        "alternatives": [],
    }


# ════════════════════════════════════════════════
# BUCKET STATE MANAGEMENT
# Two-layer storage: Supabase (primary) → CSV (fallback)
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
    """Create initial bucket state on first run."""
    state = _make_default_state()
    save_bucket_state(state)
    return state

def load_portfolio_from_bucket_trades() -> pd.DataFrame:
    cols  = ["Stock", "Buy_Price", "Quantity", "Buy_Value", "Buy_Date", "Bucket"]  # ADD Bucket
    empty = pd.DataFrame(columns=cols)

    try:
        trades_df = load_bucket_trades()
    except Exception as e:
        print(f"⚠️ load_portfolio_from_bucket_trades error: {e}")
        return None

    if trades_df.empty:
        return empty

    holdings = {}

    for _, t in trades_df.iterrows():
        stock  = str(t.get("Stock", "") or "")
        action = str(t.get("Action", "") or "").upper()
        qty    = int(t.get("Quantity") or 0)
        price  = float(t.get("Price") or 0)
        ts     = str(t.get("Timestamp", "") or "")
        bucket = str(t.get("Bucket", "") or "")  # ADD THIS

        if not stock or qty <= 0:
            continue

        if action == "BUY":
            if stock not in holdings:
                holdings[stock] = {
                    "Stock":     stock,
                    "Buy_Price": price,
                    "Quantity":  qty,
                    "Buy_Value": price * qty,
                    "Buy_Date":  ts,
                    "Bucket":    bucket,  # ADD THIS
                }
            else:
                h = holdings[stock]
                new_qty   = h["Quantity"] + qty
                new_value = h["Buy_Value"] + (price * qty)
                h["Quantity"]  = new_qty
                h["Buy_Value"] = new_value
                h["Buy_Price"] = new_value / new_qty

        elif action == "SELL":
            if stock in holdings:
                holdings[stock]["Quantity"] -= qty
                if holdings[stock]["Quantity"] <= 0:
                    del holdings[stock]
                else:
                    h = holdings[stock]
                    h["Buy_Value"] = h["Buy_Price"] * h["Quantity"]

    if not holdings:
        return empty

    return pd.DataFrame(list(holdings.values()))[cols]

def load_bucket_state():
    """
    Load current state of all three buckets.

    Priority:
      1. Supabase — persists across Cloud restarts
      2. Local CSV — works on laptop
      3. Defaults  — first run with no data anywhere
    """
    df = None

    # ── Layer 1: Supabase ─────────────────────────
    client = get_client()
    if client:
        try:
            response = client.table("bucket_state").select("*").execute()
            if response.data:
                # Clean up any legacy __price__ rows (from old code)
                price_rows = [
                    r["bucket"] for r in response.data
                    if str(r.get("bucket", "")).startswith("__price__")
                ]
                if price_rows:
                    try:
                        for pk in price_rows:
                            client.table("bucket_state").delete().eq("bucket", pk).execute()
                        print(f"🧹 Cleaned {len(price_rows)} legacy __price__ rows from bucket_state")
                    except Exception:
                        pass
                # Filter to only real bucket rows
                real_rows = [
                    r for r in response.data
                    if not str(r.get("bucket", "")).startswith("__price__")
                ]
                if real_rows:
                    df = pd.DataFrame(real_rows)
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
    """
    rows = []
    for bucket_name, data in state.items():
        row = {"Bucket": bucket_name}
        row.update(data)
        row["Last_Updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows.append(row)

    # ── Layer 1: Supabase ─────────────────────────
    client = get_client()
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
    USE WITH CARE — clears ALL trade history.
    """
    client = get_client()
    if client:
        try:
            client.table("bucket_trades").delete().neq("bucket", "").execute()
            client.table("bucket_state").delete().neq("bucket", "").execute()
        except Exception as e:
            print(f"Supabase reset failed: {e}")

    for f in [BUCKET_STATE_FILE, BUCKET_TRADES_FILE]:
        if os.path.exists(f):
            os.remove(f)

    return _initialize_bucket_state()


# ════════════════════════════════════════════════
# BUCKET TRADE LOGGING
# ════════════════════════════════════════════════

def _log_bucket_trade(bucket, action, stock, price, quantity, value, pnl=None):
    """
    Log a trade to Supabase (primary) and bucket_trades.csv (fallback).
    Append-only — each trade becomes a new row, never updated.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    pnl_val   = round(pnl, 2) if pnl is not None else None

    # ── Layer 1: Supabase ─────────────────────────
    client = get_client()
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

    client = get_client()
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

    if os.path.exists(BUCKET_TRADES_FILE):
        try:
            return pd.read_csv(BUCKET_TRADES_FILE)
        except Exception:
            pass

    return pd.DataFrame(columns=COLS)


# ════════════════════════════════════════════════
# CAPITAL CHECKS
# ════════════════════════════════════════════════

def get_bucket_available_cash(bucket_name):
    """How much cash is available in this bucket right now."""
    state = load_bucket_state()
    if bucket_name not in state:
        return 0.0
    return state[bucket_name]["Available_Cash"]


def get_max_position_size(bucket_name, price):
    """
    Calculate max shares we can buy in this bucket.
    Respects max_position_pct AND available_cash.
    Returns (quantity, spend_amount, reason_if_rejected)
    """
    state = load_bucket_state()
    cfg   = BUCKET_CONFIG.get(bucket_name, {})

    if bucket_name not in state:
        return 0, 0, f"Bucket '{bucket_name}' not found"

    available = state[bucket_name]["Available_Cash"]
    starting  = state[bucket_name]["Starting_Capital"]
    max_pct   = cfg.get("max_position_pct", 0.10)
    max_spend = round(starting * max_pct, 2)
    actual    = min(max_spend, available)

    if actual < price:
        return 0, 0, (
            f"Insufficient cash in {bucket_name} bucket "
            f"(₹{available:,.0f} available, price ₹{price:,.0f})"
        )

    quantity = int(actual // price)
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

    bucket_trades = trades_df[trades_df["Bucket"] == bucket_name]
    buys  = set(bucket_trades[bucket_trades["Action"] == "BUY"]["Stock"].tolist())
    sells = set(bucket_trades[bucket_trades["Action"] == "SELL"]["Stock"].tolist())
    open_positions = buys - sells

    open_count = len(open_positions)
    can_trade  = open_count < max_pos

    return can_trade, open_count, max_pos


def check_score_threshold(bucket_name, composite_score):
    """Check if stock's score meets this bucket's minimum."""
    cfg       = BUCKET_CONFIG.get(bucket_name, {})
    min_score = cfg.get("min_score", 60)
    approved  = composite_score >= min_score
    reason    = "" if approved else (
        f"Score {composite_score}/100 below {bucket_name} minimum ({min_score})"
    )
    return approved, min_score, reason


# ════════════════════════════════════════════════
# BUY AND SELL — BUCKET-AWARE EXECUTION
# ════════════════════════════════════════════════

def bucket_buy(bucket_name, stock_name, price, composite_score=None):
    """
    Execute a paper BUY from a specific bucket.
    Saves to both Supabase and CSV.

    composite_score: pass None to skip score check (manual trades).
    """
    state = load_bucket_state()

    if bucket_name not in state:
        return {"status": "REJECTED", "reason": f"Unknown bucket: {bucket_name}"}

    # Already holding this stock in this bucket?
    trades_df = load_bucket_trades()
    if not trades_df.empty:
        b_trades = trades_df[trades_df["Bucket"] == bucket_name]
        buys  = set(b_trades[b_trades["Action"] == "BUY"]["Stock"].tolist())
        sells = set(b_trades[b_trades["Action"] == "SELL"]["Stock"].tolist())
        if stock_name in (buys - sells):
            return {
                "status": "REJECTED",
                "reason": f"Already holding {stock_name} in {bucket_name} bucket",
            }

    # Position limit
    can_trade, open_count, max_pos = check_position_limit(bucket_name)
    if not can_trade:
        return {
            "status": "REJECTED",
            "reason": f"{bucket_name} bucket at max positions ({open_count}/{max_pos})",
        }

    # Score threshold (optional)
    if composite_score is not None:
        approved, min_score, reason = check_score_threshold(bucket_name, composite_score)
        if not approved:
            return {
                "status":    "REJECTED",
                "reason":    reason,
                "score":     composite_score,
                "min_score": min_score,
            }

    # Position size
    quantity, spend, err = get_max_position_size(bucket_name, price)
    if quantity == 0:
        return {"status": "REJECTED", "reason": err}

    # Execute
    state[bucket_name]["Available_Cash"]   = round(
        state[bucket_name]["Available_Cash"] - spend, 2
    )
    state[bucket_name]["Deployed_Capital"] = round(
        state[bucket_name]["Deployed_Capital"] + spend, 2
    )
    state[bucket_name]["Total_Trades"] += 1

    save_bucket_state(state)
    _log_bucket_trade(bucket_name, "BUY", stock_name, price, quantity, spend)
        # ── Create lifecycle record ───────────────────
    try:
        from portfolio.position_manager import add_to_watchlist
        from portfolio.position_manager import mark_ready
        from portfolio.position_manager import mark_entered as _pm_enter
        try:
            from strategies.watchlist_manager import get_watchlist_dict
            wl     = get_watchlist_dict()
            symbol = wl.get(stock_name, stock_name + ".NS")
        except Exception:
            symbol = stock_name + ".NS"
        watch_result = add_to_watchlist(stock_name, symbol, bucket_name)
        if watch_result["status"] in ("OK", "SKIPPED"):
            pos_id = watch_result.get("position_id")
            if pos_id:
                mark_ready(pos_id, composite_score or 0)
                _pm_enter(pos_id, round(price, 2), quantity, spend)
    except Exception as e:
        print(f"⚠️ Lifecycle create failed (non-critical): {e}")
    
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
    Finds the original BUY to calculate P&L.
    Saves to both Supabase and CSV.
    """
    state     = load_bucket_state()
    trades_df = load_bucket_trades()

    if bucket_name not in state:
        return {"status": "REJECTED", "reason": f"Unknown bucket: {bucket_name}"}

    if trades_df.empty:
        return {"status": "REJECTED", "reason": f"No trades found in {bucket_name}"}

    b_trades = trades_df[
        (trades_df["Bucket"] == bucket_name) &
        (trades_df["Stock"]  == stock_name)  &
        (trades_df["Action"] == "BUY")
    ]

    if b_trades.empty:
        return {
            "status": "REJECTED",
            "reason": f"No open position in {stock_name} in {bucket_name} bucket",
        }

    buy_row   = b_trades.iloc[-1]
    buy_price = float(buy_row["Price"])
    quantity  = int(buy_row["Quantity"])
    buy_value = float(buy_row["Value"])

    sell_value = round(quantity * price, 2)
    pnl        = round(sell_value - buy_value, 2)
    pnl_pct    = round((pnl / buy_value) * 100, 2)

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
        # ── Update lifecycle record to EXITED ─────────
    try:
        from portfolio.position_manager import load_lifecycle, mark_exited
        df = load_lifecycle()
        # Find the active lifecycle record for this stock+bucket
        active = df[
            (df["stock"]  == stock_name) &
            (df["bucket"] == bucket_name) &
            (df["state"].isin(["ENTERED","HOLDING","TRAILING","PARTIAL_EXIT"]))
        ]
        if not active.empty:
            pos_id = active.iloc[-1]["position_id"]
            exit_reason = "STOP_LOSS" if pnl < 0 else "TARGET"
            mark_exited(pos_id, round(price, 2), exit_reason)
    except Exception as e:
        print(f"⚠️ Lifecycle exit update failed (non-critical): {e}")
    
    return {
        "status":   "EXECUTED",
        "action":   "SELL",
        "bucket":   bucket_name,
        "stock":    stock_name,
        "price":    round(price, 2),
        "quantity": quantity,
        "value":    sell_value,
        "pnl":      pnl,
        "pnl_pct":  pnl_pct,
        "cash_now": state[bucket_name]["Available_Cash"],
    }


# ════════════════════════════════════════════════
# PORTFOLIO SUMMARY
# ════════════════════════════════════════════════

def get_bucket_summary():
    """
    Full summary of all three buckets for dashboard display.
    Returns a list of dicts — one per bucket.
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

        utilization = round((deployed / starting * 100), 1) if starting > 0 else 0
        win_rate    = round((winning_tr / total_tr * 100), 1) if total_tr > 0 else 0
        pnl_pct     = round((total_pnl / starting * 100), 2) if starting > 0 else 0

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
    """Aggregate totals across all three buckets."""
    state  = load_bucket_state()
    totals = {
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
    """Return list of currently open stock names in a bucket."""
    trades_df = load_bucket_trades()
    if trades_df.empty:
        return []
    b_trades = trades_df[trades_df["Bucket"] == bucket_name]
    buys     = set(b_trades[b_trades["Action"] == "BUY"]["Stock"].tolist())
    sells    = set(b_trades[b_trades["Action"] == "SELL"]["Stock"].tolist())
    return list(buys - sells)


def get_bucket_trade_history(bucket_name=None):
    """Trade history for a specific bucket, or all buckets."""
    df = load_bucket_trades()
    if df.empty:
        return df
    if bucket_name:
        return df[df["Bucket"] == bucket_name].copy()
    return df


def save_last_known_prices(prices: dict):
    """Save last known good prices to a local JSON file (not Supabase)."""
    try:
        import json
        price_file = os.path.join(LOGS_DIR, "last_known_prices.json")
        with open(price_file, "w") as f:
            json.dump(prices, f)
    except Exception as e:
        print(f"⚠️ save_last_known_prices failed: {e}")

def load_last_known_prices() -> dict:
    """Load last known prices from local JSON file."""
    try:
        import json
        price_file = os.path.join(LOGS_DIR, "last_known_prices.json")
        if os.path.exists(price_file):
            with open(price_file, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}