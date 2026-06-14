# ================================================
# FILE: engine/decision_engine.py
# PURPOSE: Explainable Autonomous Decision Engine — Milestone 32
#
# WHAT THIS DOES:
#   Acts as the final approval layer before any trade executes.
#   Every BUY, SELL, HOLD, and NO_TRADE gets a full explanation:
#     - Why we are making this decision (reasons for)
#     - Why it might fail (reasons against)
#     - Risk assessment (entry, stop, target, risk:reward)
#     - Portfolio impact (deployment %, bucket utilization)
#     - Confidence score (0-100)
#     - Whether execution is approved
#
# DESIGN PRINCIPLE:
#   The execution loop MUST call this engine before any trade.
#   If execution_allowed = False → trade is blocked.
#   If execution_allowed = True  → trade proceeds.
#   This engine becomes the single trusted approval gateway.
#
# INPUTS (consumed from existing engines):
#   orchestrator.py      → bucket score, routing, confluence
#   scoring_engine.py    → composite score, individual dimensions
#   risk/portfolio_risk  → deployment %, sector limits, drawdown
#   position_manager.py  → lifecycle state, cooldown
#   capital_engine.py    → available cash per bucket
#
# OUTPUTS:
#   DecisionResult dict with full explanation + execution_allowed flag
#
# STORAGE:
#   Primary  : Supabase decision_log table
#   Fallback : logs/decision_log.csv
#
# HOW EXECUTION LOOP USES THIS:
#   result = make_buy_decision(stock, symbol, bucket, orch_result, score_result, regime)
#   if result["execution_allowed"]:
#       bucket_buy(...)
# ================================================

import os
import sys
import pandas as pd
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── Logging paths ─────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR        = os.path.join(BASE_DIR, "logs")
DECISION_LOG_FILE = os.path.join(LOGS_DIR, "decision_log.csv")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Supabase (optional) ───────────────────────────
try:
    from config.supabase_client import get_client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    def get_client():
        return None

# ── Risk settings ─────────────────────────────────
try:
    from config.strategy_settings import (
        STOP_LOSS_PCT,
        TARGET_PROFIT_PCT,
        TRAILING_STOP_PCT,
        MAX_POSITION_PCT,
    )
except ImportError:
    STOP_LOSS_PCT     = 0.06
    TARGET_PROFIT_PCT = 0.15
    TRAILING_STOP_PCT = 0.04
    MAX_POSITION_PCT  = 0.10

# ── Decision type constants ───────────────────────
DECISION_BUY      = "BUY"
DECISION_SELL     = "SELL"
DECISION_HOLD     = "HOLD"
DECISION_NO_TRADE = "NO_TRADE"

# ── Confidence bands ──────────────────────────────
CONFIDENCE_VERY_HIGH = 85
CONFIDENCE_HIGH      = 70
CONFIDENCE_MEDIUM    = 50
CONFIDENCE_LOW       = 0

# ── Decision log columns ──────────────────────────
DECISION_LOG_COLS = [
    "Timestamp", "Stock", "Symbol", "Bucket", "Decision",
    "Confidence", "Composite_Score", "Bucket_Score",
    "Reasons_For", "Reasons_Against",
    "Entry_Price", "Stop_Price", "Target_Price",
    "Risk_Reward", "Position_Size_Pct",
    "Deployed_Before", "Deployed_After",
    "Execution_Allowed", "Rejection_Reason", "Regime",
]


# ════════════════════════════════════════════════
# CONFIDENCE SCORING
# Converts orchestrator + individual scores to
# a single 0-100 human-readable confidence value.
# ════════════════════════════════════════════════

def calculate_confidence(
    composite_score: int,
    bucket_score: int,
    confluence_count: int,
    buy_votes: int,
    regime: str,
    individual_scores: dict,
) -> int:
    """
    Produce a 0-100 confidence score.

    Sources:
      40% — bucket-specific score (most relevant for this trade type)
      30% — confluence count (how many independent signals agree)
      20% — composite score (overall intelligence score)
      10% — regime penalty/bonus

    Returns int 0-100.
    """
    # ── 40% — Bucket score ─────────────────────────
    bucket_pts = round(bucket_score * 0.40)

    # ── 30% — Confluence (0=none, 6=maximum) ──────
    # Scale 0-6 to 0-30
    conf_pts = round(min(confluence_count / 6, 1.0) * 30)

    # ── 20% — Composite score ─────────────────────
    comp_pts = round(composite_score * 0.20)

    # ── 10% — Regime adjustment ───────────────────
    regime_upper = str(regime).upper()
    if "BEAR" in regime_upper and "WEAK" not in regime_upper:
        regime_pts = 0
    elif "WEAK BEAR" in regime_upper:
        regime_pts = 3
    elif "SIDEWAYS" in regime_upper:
        regime_pts = 5
    elif "WEAK BULL" in regime_upper:
        regime_pts = 7
    elif "BULL" in regime_upper:
        regime_pts = 10
    else:
        regime_pts = 5

    total = bucket_pts + conf_pts + comp_pts + regime_pts
    return max(0, min(100, round(total)))


def confidence_label(score: int) -> str:
    """Human-readable confidence label."""
    if score >= CONFIDENCE_VERY_HIGH:
        return f"VERY HIGH ({score}/100) 🟢🟢"
    elif score >= CONFIDENCE_HIGH:
        return f"HIGH ({score}/100) 🟢"
    elif score >= CONFIDENCE_MEDIUM:
        return f"MEDIUM ({score}/100) 🟡"
    else:
        return f"LOW ({score}/100) 🔴"


# ════════════════════════════════════════════════
# REASONS BUILDER
# Generates human-readable explanation lists
# from scoring engine + orchestrator + risk data.
# ════════════════════════════════════════════════

def build_reasons_for_buy(
    stock_name: str,
    individual_scores: dict,
    combined_votes: dict,
    confluence: dict,
    regime: str,
    bucket_name: str,
) -> list[str]:
    """
    Build a list of positive reasons supporting a BUY.
    Each reason is plain English. Sorted by impact.
    """
    reasons = []
    confirming = confluence.get("confirming_signals", [])

    buy_votes = combined_votes.get("buy", 0)
    if buy_votes >= 4:
        reasons.append(f"✅ All 4 strategies agree — STRONG BUY consensus")
    elif buy_votes == 3:
        reasons.append(f"✅ 3 of 4 strategies agree — solid buy signal")
    elif buy_votes == 2:
        reasons.append(f"🟡 2 of 4 strategies agree — moderate signal")

    # Individual dimension checks
    trend = individual_scores.get("Trend", 50)
    if trend >= 70:
        reasons.append(f"✅ Strong uptrend: price above MA20 and EMA aligned (Trend={trend}/100)")
    elif trend >= 55:
        reasons.append(f"🟡 Moderate trend: generally above moving averages (Trend={trend}/100)")

    momentum = individual_scores.get("Momentum", 50)
    if momentum >= 70:
        reasons.append(f"✅ Strong momentum: RSI and MACD both bullish (Momentum={momentum}/100)")
    elif momentum >= 55:
        reasons.append(f"🟡 Moderate momentum building (Momentum={momentum}/100)")

    vol = individual_scores.get("Volume", 50)
    if vol >= 70:
        reasons.append(f"✅ Volume confirms the move — above average participation (Volume={vol}/100)")
    elif vol >= 55:
        reasons.append(f"🟡 Volume is adequate (Volume={vol}/100)")

    ms = individual_scores.get("Mkt Structure", 50)
    if ms >= 70:
        reasons.append(f"✅ Bullish market structure: higher highs and higher lows (Structure={ms}/100)")
    elif ms >= 55:
        reasons.append(f"🟡 Neutral to slightly bullish structure (Structure={ms}/100)")

    candle = individual_scores.get("Candlestick", 50)
    if candle >= 70:
        reasons.append(f"✅ Confirmed candlestick pattern supports entry (Candlestick={candle}/100)")

    fund = individual_scores.get("Fundamental", 50)
    if fund >= 70:
        reasons.append(f"✅ Strong fundamentals — financially healthy business (Fundamental={fund}/100)")
    elif fund >= 60 and bucket_name == "Long-Term":
        reasons.append(f"🟡 Acceptable fundamentals for long-term hold (Fundamental={fund}/100)")

    rs = individual_scores.get("Rel. Strength", 50)
    if rs >= 65:
        reasons.append(f"✅ Outperforming NIFTY — relative strength leader (RS={rs}/100)")

    sent = individual_scores.get("Sentiment", 50)
    if sent >= 65:
        reasons.append(f"✅ Positive news sentiment supports bullish case (Sentiment={sent}/100)")

    regime_upper = str(regime).upper()
    if "BULL" in regime_upper and "WEAK" not in regime_upper:
        reasons.append(f"✅ BULL market regime — wind is in our favour ({regime})")
    elif "WEAK BULL" in regime_upper:
        reasons.append(f"🟡 Weak bull regime — market trending cautiously upward ({regime})")

    # Add confluence signals (avoid duplicates)
    for sig in confirming[:3]:
        tag = f"✅ {sig}"
        if tag not in reasons and sig not in str(reasons):
            reasons.append(f"✅ {sig}")

    return reasons[:8]   # Cap at 8 reasons for readability


def build_reasons_against_buy(
    stock_name: str,
    individual_scores: dict,
    combined_votes: dict,
    conflicts: dict,
    regime: str,
    bucket_name: str,
    portfolio_summary: dict,
) -> list[str]:
    """
    Build a list of warnings / risks for a BUY.
    Honest assessment — not to block, but to inform.
    """
    reasons = []
    sell_votes = combined_votes.get("sell", 0)

    if sell_votes >= 2:
        reasons.append(f"⚠️ {sell_votes} strategies say SELL — mixed signals, lower conviction")
    elif sell_votes == 1:
        reasons.append(f"⚠️ 1 strategy is bearish — not full consensus")

    momentum = individual_scores.get("Momentum", 50)
    if momentum <= 35:
        reasons.append(f"⚠️ Weak momentum: RSI or MACD not confirming (Momentum={momentum}/100)")

    vol = individual_scores.get("Volume", 50)
    if vol <= 35:
        reasons.append(f"⚠️ Low volume — move not confirmed by participation (Volume={vol}/100)")
    elif vol <= 45:
        reasons.append(f"⚠️ Volume below average — wait for stronger confirmation")

    ms = individual_scores.get("Mkt Structure", 50)
    if ms <= 35:
        reasons.append(f"⚠️ Weak market structure — not making higher highs (Structure={ms}/100)")

    fund = individual_scores.get("Fundamental", 50)
    if fund <= 35:
        reasons.append(f"⚠️ Weak fundamentals — business health concern (Fundamental={fund}/100)")

    sent = individual_scores.get("Sentiment", 50)
    if sent <= 35:
        reasons.append(f"⚠️ Negative news sentiment — press coverage bearish (Sentiment={sent}/100)")

    regime_upper = str(regime).upper()
    if "WEAK BEAR" in regime_upper:
        reasons.append(f"⚠️ Weak bear regime — market conditions unfavourable ({regime})")
    elif "SIDEWAYS" in regime_upper:
        reasons.append(f"⚠️ Sideways market — trend unclear, whipsaws possible ({regime})")

    # Portfolio warnings
    deployed_pct = portfolio_summary.get("capital_deployed_pct", 0)
    if deployed_pct >= 70:
        reasons.append(f"⚠️ Portfolio heavily deployed ({deployed_pct}%) — limited cash buffer")
    elif deployed_pct >= 55:
        reasons.append(f"⚠️ Moderate deployment ({deployed_pct}%) — watch total exposure")

    sector_name = portfolio_summary.get("largest_sector_name", "")
    sector_pct  = portfolio_summary.get("largest_sector_pct", 0)
    if sector_pct >= 25:
        reasons.append(f"⚠️ Sector concentration: {sector_name} already {sector_pct}% of portfolio")

    # Conflict warnings
    for c in conflicts.get("soft_conflicts", [])[:2]:
        reasons.append(f"⚠️ {c}")

    return reasons[:6]   # Cap at 6 warnings


def build_reasons_for_sell(
    action: str,
    stock_name: str,
    current_pnl_pct: float,
    exit_reason: str,
    individual_scores: dict,
    regime: str,
) -> list[str]:
    """Build reasons for a SELL decision."""
    reasons = []

    if "STOP" in exit_reason.upper():
        reasons.append(f"🛑 Hard stop loss triggered — protecting remaining capital")
        reasons.append(f"📉 Position down {abs(current_pnl_pct):.1f}% — exit to prevent further loss")
    elif "TARGET" in exit_reason.upper():
        reasons.append(f"🎯 Profit target reached — booking gain as planned")
        reasons.append(f"✅ Position up +{current_pnl_pct:.1f}% — taking disciplined profit")
    elif "TRAIL" in exit_reason.upper():
        reasons.append(f"📊 Trailing stop triggered — locking in partial profit")
        reasons.append(f"✅ Peak gain exceeded trigger — trailing stop activated")
    elif "SIGNAL" in exit_reason.upper():
        reasons.append(f"📉 Strategy signal reversed — exit before deeper loss")

    momentum = individual_scores.get("Momentum", 50)
    if momentum <= 35:
        reasons.append(f"📉 Momentum has weakened significantly (Momentum={momentum}/100)")

    ms = individual_scores.get("Mkt Structure", 50)
    if ms <= 35:
        reasons.append(f"📉 Market structure has deteriorated (Structure={ms}/100)")

    regime_upper = str(regime).upper()
    if "BEAR" in regime_upper:
        reasons.append(f"🐻 Regime shifted to {regime} — prudent to reduce exposure")

    return reasons[:5]


def build_no_trade_explanation(rejection_reasons: list[str]) -> str:
    """Build a concise NO_TRADE explanation from rejection list."""
    if not rejection_reasons:
        return "Signal does not meet entry criteria — waiting for better setup."
    primary = rejection_reasons[0]
    if len(rejection_reasons) == 1:
        return f"Rejected: {primary}"
    return f"Rejected: {primary} (+ {len(rejection_reasons)-1} more)"


# ════════════════════════════════════════════════
# RISK ASSESSMENT BLOCK
# Calculates exact price levels for any BUY
# ════════════════════════════════════════════════

def build_risk_assessment(
    entry_price: float,
    bucket_name: str,
    composite_score: int,
    regime: str,
) -> dict:
    """
    Build risk assessment: stop, target, risk:reward, position size.
    Uses ATR-style sizing: smaller size in weaker signals/regimes.
    """
    stop_price   = round(entry_price * (1 - STOP_LOSS_PCT), 2)
    target_price = round(entry_price * (1 + TARGET_PROFIT_PCT), 2)
    trail_price  = round(entry_price * (1 - TRAILING_STOP_PCT), 2)

    risk_amount   = round(entry_price - stop_price, 2)
    reward_amount = round(target_price - entry_price, 2)
    risk_reward   = round(reward_amount / risk_amount, 1) if risk_amount > 0 else 0

    # Position size: scaled by score + regime
    regime_upper = str(regime).upper()
    if composite_score >= 70 and "BULL" in regime_upper:
        position_pct = MAX_POSITION_PCT * 100        # e.g. 10%
    elif composite_score >= 60 or "WEAK BULL" in regime_upper:
        position_pct = MAX_POSITION_PCT * 70         # e.g. 7%
    elif composite_score >= 55 or "SIDEWAYS" in regime_upper:
        position_pct = MAX_POSITION_PCT * 50         # e.g. 5%
    elif "WEAK BEAR" in regime_upper:
        position_pct = MAX_POSITION_PCT * 30         # e.g. 3%
    else:
        position_pct = 0.0

    # Intraday bucket — always smaller
    if bucket_name == "Intraday":
        position_pct = min(position_pct, MAX_POSITION_PCT * 33)

    return {
        "entry_price":    round(entry_price, 2),
        "stop_price":     stop_price,
        "target_price":   target_price,
        "trail_price":    trail_price,
        "stop_pct":       round(STOP_LOSS_PCT * 100, 1),
        "target_pct":     round(TARGET_PROFIT_PCT * 100, 1),
        "trail_pct":      round(TRAILING_STOP_PCT * 100, 1),
        "risk_amount":    risk_amount,
        "reward_amount":  reward_amount,
        "risk_reward":    risk_reward,
        "position_pct":   round(position_pct, 1),
    }


# ════════════════════════════════════════════════
# PORTFOLIO IMPACT BLOCK
# ════════════════════════════════════════════════

def build_portfolio_impact(
    bucket_name: str,
    proposed_value: float,
    portfolio_summary: dict,
) -> dict:
    """
    Show how this trade changes portfolio risk metrics.
    """
    total_capital    = portfolio_summary.get("total_capital", 600000)
    deployed_before  = portfolio_summary.get("capital_deployed_pct", 0)
    open_positions   = portfolio_summary.get("open_positions_count", 0)

    deployed_after = round(
        deployed_before + (proposed_value / total_capital * 100), 1
    ) if total_capital > 0 else deployed_before

    from portfolio.capital_engine import BUCKET_CONFIG, check_position_limit
    cfg = BUCKET_CONFIG.get(bucket_name, {})
    max_pos = cfg.get("max_positions", 5)

    try:
        _, bucket_open, _ = check_position_limit(bucket_name)
    except Exception:
        bucket_open = 0

    return {
        "deployed_before":     deployed_before,
        "deployed_after":      deployed_after,
        "open_positions":      open_positions,
        "bucket_open":         bucket_open,
        "bucket_max":          max_pos,
        "bucket_utilization":  f"{bucket_open + 1}/{max_pos}",
        "trade_value":         round(proposed_value, 2),
        "risk_level_change":   "ELEVATED" if deployed_after >= 70 else "NORMAL",
    }


# ════════════════════════════════════════════════
# FORMATTED EXPLANATION TEXT
# ════════════════════════════════════════════════

def format_decision_text(
    stock_name: str,
    bucket_name: str,
    decision: str,
    confidence: int,
    composite_score: int,
    reasons_for: list[str],
    reasons_against: list[str],
    risk: dict,
    portfolio_impact: dict,
    execution_allowed: bool,
    rejection_reason: str = "",
    regime: str = "",
) -> str:
    """
    Format the full decision as a human-readable text block.
    This is what gets logged and shown in the dashboard.
    """
    lines = []
    lines.append(f"{'='*55}")
    lines.append(f"DECISION: {decision}")
    lines.append(f"Stock: {stock_name}  |  Bucket: {bucket_name}")
    lines.append(f"Confidence: {confidence}/100  |  Score: {composite_score}/100")
    lines.append(f"Regime: {regime}")
    lines.append("")

    if reasons_for:
        lines.append("REASONS FOR:")
        for r in reasons_for:
            lines.append(f"  {r}")
        lines.append("")

    if reasons_against:
        lines.append("REASONS AGAINST:")
        for r in reasons_against:
            lines.append(f"  {r}")
        lines.append("")

    if decision == DECISION_BUY and risk:
        lines.append("RISK ASSESSMENT:")
        lines.append(f"  Entry:  ₹{risk['entry_price']}")
        lines.append(
            f"  Stop:   ₹{risk['stop_price']}  "
            f"(-{risk['stop_pct']}% = -₹{risk['risk_amount']})"
        )
        lines.append(
            f"  Target: ₹{risk['target_price']}  "
            f"(+{risk['target_pct']}% = +₹{risk['reward_amount']})"
        )
        lines.append(f"  Risk:Reward = 1:{risk['risk_reward']}")
        lines.append(f"  Position Size: {risk['position_pct']}% of bucket")
        lines.append("")

    if decision in (DECISION_BUY, DECISION_SELL) and portfolio_impact:
        lines.append("PORTFOLIO IMPACT:")
        lines.append(
            f"  Deployment:  {portfolio_impact['deployed_before']}% → "
            f"{portfolio_impact['deployed_after']}%"
        )
        lines.append(
            f"  Bucket Usage: {portfolio_impact['bucket_utilization']}"
        )
        lines.append("")

    if execution_allowed:
        lines.append(f"✅ EXECUTION APPROVED")
    else:
        lines.append(f"❌ EXECUTION BLOCKED")
        if rejection_reason:
            lines.append(f"   Reason: {rejection_reason}")

    lines.append(f"{'='*55}")
    return "\n".join(lines)


# ════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════

def log_decision(result: dict):
    """
    Save one decision to Supabase (primary) and CSV (fallback).
    Called after every make_buy_decision() or make_sell_decision() call.
    """
    entry = {
        "Timestamp":        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Stock":            result.get("stock",            ""),
        "Symbol":           result.get("symbol",           ""),
        "Bucket":           result.get("bucket",           ""),
        "Decision":         result.get("decision",         ""),
        "Confidence":       result.get("confidence",       0),
        "Composite_Score":  result.get("composite_score",  0),
        "Bucket_Score":     result.get("bucket_score",     0),
        "Reasons_For":      " | ".join(result.get("reasons_for",     [])),
        "Reasons_Against":  " | ".join(result.get("reasons_against", [])),
        "Entry_Price":      result.get("entry_price",      0),
        "Stop_Price":       result.get("stop_price",       0),
        "Target_Price":     result.get("target_price",     0),
        "Risk_Reward":      result.get("risk_reward",      0),
        "Position_Size_Pct":result.get("position_size_pct",0),
        "Deployed_Before":  result.get("deployed_before",  0),
        "Deployed_After":   result.get("deployed_after",   0),
        "Execution_Allowed":result.get("execution_allowed", False),
        "Rejection_Reason": result.get("rejection_reason", ""),
        "Regime":           result.get("regime",            ""),
    }

    # ── Layer 1: Supabase ─────────────────────────
    try:
        client = get_client()
        if client:
            client.table("decision_log").insert({
                "timestamp":           entry["Timestamp"],
                "stock":               entry["Stock"],
                "symbol":              entry["Symbol"],
                "bucket":              entry["Bucket"],
                "decision":            entry["Decision"],
                "confidence":          int(entry["Confidence"]),
                "composite_score":     int(entry["Composite_Score"]),
                "bucket_score":        int(entry["Bucket_Score"]),
                "reasons_for":         entry["Reasons_For"],
                "reasons_against":     entry["Reasons_Against"],
                "entry_price":         float(entry["Entry_Price"]) if entry["Entry_Price"] else 0,
                "stop_price":          float(entry["Stop_Price"]) if entry["Stop_Price"] else 0,
                "target_price":        float(entry["Target_Price"]) if entry["Target_Price"] else 0,
                "risk_reward":         float(entry["Risk_Reward"]) if entry["Risk_Reward"] else 0,
                "position_size_pct":   float(entry["Position_Size_Pct"]),
                "deployed_pct_before": float(entry["Deployed_Before"]),
                "deployed_pct_after":  float(entry["Deployed_After"]),
                "execution_allowed":   bool(entry["Execution_Allowed"]),
                "rejection_reason":    entry["Rejection_Reason"],
                "regime":              entry["Regime"],
            }).execute()
    except Exception as e:
        print(f"⚠️ Supabase decision_log insert failed: {e}")

    # ── Layer 2: CSV (always) ─────────────────────
    df = pd.DataFrame([entry])
    try:
        if os.path.exists(DECISION_LOG_FILE):
            df.to_csv(DECISION_LOG_FILE, mode='a', header=False, index=False)
        else:
            df.to_csv(DECISION_LOG_FILE, mode='w', header=True, index=False)
    except Exception as e:
        print(f"⚠️ decision_log CSV write failed: {e}")


def load_decision_log(max_rows: int = 200) -> pd.DataFrame:
    """
    Load the explainable decision log for dashboard display.
    Tries Supabase first, falls back to CSV.
    """
    # ── Layer 1: Supabase ─────────────────────────
    try:
        client = get_client()
        if client:
            response = (
                client.table("decision_log")
                .select("*")
                .order("timestamp", desc=True)
                .limit(max_rows)
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "timestamp":           "Timestamp",
                    "stock":               "Stock",
                    "symbol":              "Symbol",
                    "bucket":              "Bucket",
                    "decision":            "Decision",
                    "confidence":          "Confidence",
                    "composite_score":     "Composite_Score",
                    "bucket_score":        "Bucket_Score",
                    "reasons_for":         "Reasons_For",
                    "reasons_against":     "Reasons_Against",
                    "entry_price":         "Entry_Price",
                    "stop_price":          "Stop_Price",
                    "target_price":        "Target_Price",
                    "risk_reward":         "Risk_Reward",
                    "position_size_pct":   "Position_Size_Pct",
                    "deployed_pct_before": "Deployed_Before",
                    "deployed_pct_after":  "Deployed_After",
                    "execution_allowed":   "Execution_Allowed",
                    "rejection_reason":    "Rejection_Reason",
                    "regime":              "Regime",
                })
                cols = [c for c in DECISION_LOG_COLS if c in df.columns]
                return df[cols].reset_index(drop=True)
            return pd.DataFrame(columns=DECISION_LOG_COLS)
    except Exception as e:
        print(f"⚠️ Supabase decision_log load failed: {e} — using CSV")

    # ── Layer 2: CSV fallback ─────────────────────
    if not os.path.exists(DECISION_LOG_FILE):
        return pd.DataFrame(columns=DECISION_LOG_COLS)
    try:
        df = pd.read_csv(DECISION_LOG_FILE)
        return df.sort_values("Timestamp", ascending=False).head(max_rows).reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=DECISION_LOG_COLS)


def clear_decision_log():
    """Clear the decision log from Supabase and CSV."""
    try:
        client = get_client()
        if client:
            client.table("decision_log").delete().neq("id", 0).execute()
    except Exception as e:
        print(f"⚠️ Could not clear Supabase decision_log: {e}")
    if os.path.exists(DECISION_LOG_FILE):
        try:
            os.remove(DECISION_LOG_FILE)
        except Exception as e:
            print(f"⚠️ Could not clear decision_log CSV: {e}")


# ════════════════════════════════════════════════
# MASTER DECISION FUNCTIONS
# Called by execution_loop.py — one per trade type
# ════════════════════════════════════════════════

def make_buy_decision(
    stock_name: str,
    symbol: str,
    bucket_name: str,
    current_price: float,
    orch_result: dict,
    score_result: dict,
    regime: str,
    proposed_value: float = 0,
    write_log: bool = True,
) -> dict:
    """
    Evaluate a BUY opportunity and produce a full decision with explanation.

    Parameters:
      stock_name     : e.g. "RELIANCE"
      symbol         : e.g. "RELIANCE.NS"
      bucket_name    : "Long-Term" / "Swing" / "Intraday"
      current_price  : current market price
      orch_result    : output from orchestrate_opportunity()
      score_result   : output from build_composite_score()
      regime         : market regime string
      proposed_value : estimated trade value in ₹
      write_log      : whether to write to audit log

    Returns complete DecisionResult dict.
    execution_allowed=True only when ALL checks pass.
    """

    composite_score  = score_result.get("Composite Score", 0)
    individual_scores= score_result.get("Individual Scores", {})
    bucket_score     = orch_result.get("bucket_score",     0)
    confluence_count = orch_result.get("confluence_count", 0)
    confluence       = {
        "confirming_signals": orch_result.get("confirming_signals", []),
        "conflicting_signals":orch_result.get("conflicting_signals",[]),
    }
    conflicts        = {
        "hard_conflicts": orch_result.get("hard_conflicts", []),
        "soft_conflicts": orch_result.get("soft_conflicts", []),
    }
    combined_votes   = {
        "buy":  orch_result.get("buy_votes", 0),
        "sell": 0,
        "hold": 0,
    }

    # ── Confidence ────────────────────────────────
    confidence = calculate_confidence(
        composite_score  = composite_score,
        bucket_score     = bucket_score,
        confluence_count = confluence_count,
        buy_votes        = combined_votes["buy"],
        regime           = regime,
        individual_scores= individual_scores,
    )

    # ── Rejection check (from orchestrator) ───────
    orch_approved     = orch_result.get("approved", False)
    rejection_reasons = orch_result.get("rejection_reasons", [])
    rejection_reason  = orch_result.get("summary", "") if not orch_approved else ""

    # ── Risk assessment ───────────────────────────
    risk = build_risk_assessment(
        entry_price     = current_price,
        bucket_name     = bucket_name,
        composite_score = composite_score,
        regime          = regime,
    )

    # ── Portfolio impact ──────────────────────────
    portfolio_summary = {}
    try:
        from risk.portfolio_risk import get_risk_dashboard_data
        rd = get_risk_dashboard_data(regime=regime)
        portfolio_summary = rd.get("portfolio_summary", {})
    except Exception:
        pass

    portfolio_impact = build_portfolio_impact(
        bucket_name      = bucket_name,
        proposed_value   = proposed_value or (current_price * 10),  # estimate if not provided
        portfolio_summary= portfolio_summary,
    )

    # ── Build reasons ─────────────────────────────
    reasons_for = build_reasons_for_buy(
        stock_name      = stock_name,
        individual_scores=individual_scores,
        combined_votes  = combined_votes,
        confluence      = confluence,
        regime          = regime,
        bucket_name     = bucket_name,
    )

    reasons_against = build_reasons_against_buy(
        stock_name      = stock_name,
        individual_scores=individual_scores,
        combined_votes  = combined_votes,
        conflicts       = conflicts,
        regime          = regime,
        bucket_name     = bucket_name,
        portfolio_summary=portfolio_summary,
    )

    # ── Final execution approval ───────────────────
    # Execution is allowed only when orchestrator approved it
    execution_allowed = orch_approved

    # Additional hard blocks (portfolio-level)
    if portfolio_impact.get("deployed_after", 0) > 85:
        execution_allowed = False
        rejection_reason = f"Portfolio would be >85% deployed after this trade — capital buffer too thin"

    # ── Assemble result ───────────────────────────
    result = {
        "stock":            stock_name,
        "symbol":           symbol,
        "bucket":           bucket_name,
        "decision":         DECISION_BUY if execution_allowed else DECISION_NO_TRADE,
        "confidence":       confidence,
        "confidence_label": confidence_label(confidence),
        "composite_score":  composite_score,
        "bucket_score":     bucket_score,
        "reasons_for":      reasons_for,
        "reasons_against":  reasons_against,
        "entry_price":      current_price,
        "stop_price":       risk["stop_price"],
        "target_price":     risk["target_price"],
        "trail_price":      risk["trail_price"],
        "risk_reward":      risk["risk_reward"],
        "position_size_pct":risk["position_pct"],
        "stop_pct":         risk["stop_pct"],
        "target_pct":       risk["target_pct"],
        "deployed_before":  portfolio_impact["deployed_before"],
        "deployed_after":   portfolio_impact["deployed_after"],
        "bucket_utilization":portfolio_impact["bucket_utilization"],
        "execution_allowed":execution_allowed,
        "rejection_reason": rejection_reason,
        "regime":           regime,
        "text_summary":     format_decision_text(
            stock_name        = stock_name,
            bucket_name       = bucket_name,
            decision          = DECISION_BUY if execution_allowed else DECISION_NO_TRADE,
            confidence        = confidence,
            composite_score   = composite_score,
            reasons_for       = reasons_for,
            reasons_against   = reasons_against,
            risk              = risk,
            portfolio_impact  = portfolio_impact,
            execution_allowed = execution_allowed,
            rejection_reason  = rejection_reason,
            regime            = regime,
        ),
    }

    if write_log:
        log_decision(result)

    return result


def make_sell_decision(
    stock_name: str,
    symbol: str,
    bucket_name: str,
    current_price: float,
    exit_action: str,
    lifecycle_result: dict,
    individual_scores: dict,
    regime: str,
    write_log: bool = True,
) -> dict:
    """
    Evaluate a SELL and produce a full explanation.

    exit_action: one of SELL_STOP / SELL_TARGET / SELL_TRAIL / SIGNAL_EXIT
    lifecycle_result: output from update_position_price()
    """
    pnl_pct = lifecycle_result.get("pnl_pct", 0)

    reasons_for = build_reasons_for_sell(
        action          = exit_action,
        stock_name      = stock_name,
        current_pnl_pct = pnl_pct,
        exit_reason     = exit_action,
        individual_scores=individual_scores,
        regime          = regime,
    )

    confidence = 90 if "STOP" in exit_action or "TARGET" in exit_action else 70

    result = {
        "stock":            stock_name,
        "symbol":           symbol,
        "bucket":           bucket_name,
        "decision":         DECISION_SELL,
        "confidence":       confidence,
        "confidence_label": confidence_label(confidence),
        "composite_score":  0,
        "bucket_score":     0,
        "reasons_for":      reasons_for,
        "reasons_against":  [],
        "entry_price":      lifecycle_result.get("trail_stop", current_price),
        "stop_price":       lifecycle_result.get("hard_stop",  0),
        "target_price":     lifecycle_result.get("target",     0),
        "trail_price":      lifecycle_result.get("trail_stop", 0),
        "risk_reward":      0,
        "position_size_pct":0,
        "stop_pct":         0,
        "target_pct":       0,
        "deployed_before":  0,
        "deployed_after":   0,
        "bucket_utilization":"",
        "execution_allowed":True,   # Sells always execute — no blocking
        "rejection_reason": "",
        "regime":           regime,
        "pnl_pct":          pnl_pct,
        "exit_action":      exit_action,
        "text_summary":     format_decision_text(
            stock_name       = stock_name,
            bucket_name      = bucket_name,
            decision         = DECISION_SELL,
            confidence       = confidence,
            composite_score  = 0,
            reasons_for      = reasons_for,
            reasons_against  = [],
            risk             = {},
            portfolio_impact = {},
            execution_allowed= True,
            regime           = regime,
        ),
    }

    if write_log:
        log_decision(result)

    return result


def make_no_trade_decision(
    stock_name: str,
    symbol: str,
    bucket_name: str,
    rejection_reasons: list[str],
    composite_score: int,
    regime: str,
    write_log: bool = True,
) -> dict:
    """
    Create a logged NO_TRADE decision.
    Always execution_allowed=False.
    """
    explanation = build_no_trade_explanation(rejection_reasons)

    result = {
        "stock":            stock_name,
        "symbol":           symbol,
        "bucket":           bucket_name or "—",
        "decision":         DECISION_NO_TRADE,
        "confidence":       0,
        "confidence_label": "N/A — not traded",
        "composite_score":  composite_score,
        "bucket_score":     0,
        "reasons_for":      [],
        "reasons_against":  rejection_reasons[:5],
        "entry_price":      0,
        "stop_price":       0,
        "target_price":     0,
        "trail_price":      0,
        "risk_reward":      0,
        "position_size_pct":0,
        "stop_pct":         0,
        "target_pct":       0,
        "deployed_before":  0,
        "deployed_after":   0,
        "bucket_utilization":"",
        "execution_allowed":False,
        "rejection_reason": explanation,
        "regime":           regime,
        "text_summary":     f"NO_TRADE: {stock_name}\nReason: {explanation}",
    }

    if write_log:
        log_decision(result)

    return result


# ════════════════════════════════════════════════
# DASHBOARD DISPLAY FUNCTIONS
# Used by app.py Tab 11 (Auto Pilot)
# ════════════════════════════════════════════════

def get_decision_dashboard_df(max_rows: int = 100) -> pd.DataFrame:
    """
    Return a Streamlit-ready DataFrame of recent decisions.
    Shows: Timestamp, Stock, Bucket, Decision, Confidence,
           Score, Risk:Reward, Entry, Stop, Target, Approved, Reason
    """
    df = load_decision_log(max_rows)
    if df.empty:
        return df

    display_cols = [
        c for c in [
            "Timestamp", "Stock", "Bucket", "Decision",
            "Confidence", "Composite_Score", "Bucket_Score",
            "Entry_Price", "Stop_Price", "Target_Price",
            "Risk_Reward", "Position_Size_Pct",
            "Deployed_Before", "Deployed_After",
            "Execution_Allowed", "Regime",
        ]
        if c in df.columns
    ]
    return df[display_cols].copy()


def get_decision_stats() -> dict:
    """
    High-level stats for the decision log summary panel.
    """
    df = load_decision_log(max_rows=500)
    if df.empty:
        return {
            "total": 0, "buys": 0, "sells": 0,
            "no_trades": 0, "avg_confidence": 0,
        }

    total    = len(df)
    buys     = len(df[df["Decision"] == DECISION_BUY])
    sells    = len(df[df["Decision"] == DECISION_SELL])
    no_trades= len(df[df["Decision"] == DECISION_NO_TRADE])

    avg_conf = 0
    if "Confidence" in df.columns and total > 0:
        try:
            avg_conf = round(df["Confidence"].astype(float).mean())
        except Exception:
            avg_conf = 0

    return {
        "total":          total,
        "buys":           buys,
        "sells":          sells,
        "no_trades":      no_trades,
        "avg_confidence": avg_conf,
    }
