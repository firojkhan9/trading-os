# ================================================
# FILE: strategies/orchestrator.py
# PURPOSE: Strategy Orchestration Engine — Milestone 31
#
# WHAT THIS DOES:
#   Acts as the central decision layer between signal
#   generation and trade execution.
#
#   For every stock opportunity it:
#     1. Calculates bucket-specific weighted scores
#     2. Detects confluence (multiple signals agreeing)
#     3. Detects conflicts (signals disagreeing)
#     4. Routes to the correct bucket (Long-Term / Swing / Intraday)
#     5. Applies all rejection filters (score, risk, lifecycle, cooldown)
#     6. Logs EVERY decision with full reasons (accepted AND rejected)
#
# WHAT IT DOES NOT DO:
#   ❌ Execute trades — that stays in execution_loop.py + capital_engine.py
#   ❌ Fetch market data — caller provides pre-fetched analysis
#   ❌ Duplicate scoring — reuses existing scoring_engine.py outputs
#
# HOW IT CONNECTS:
#   execution_loop.py  → calls orchestrate_opportunity() for each stock
#   capital_engine.py  → called AFTER orchestrator says ACCEPT
#   position_manager.py → cooldown checks via is_in_cooldown()
#   risk/portfolio_risk.py → portfolio-level risk gate
#   Supabase/CSV → all decisions logged via log_orchestration_decision()
#
# OUTPUT STRUCTURE (per stock):
#   {
#     stock, symbol, bucket,
#     decision: ACCEPT / REJECT / REVIEW,
#     confidence_score: 0-100,
#     component_scores: {...},
#     confluence_count: int,
#     routing_reason: str,
#     rejection_reason: str (if rejected),
#     summary: str (plain English),
#   }
#
# BUCKET-SPECIFIC SCORE WEIGHTS:
#   Long-Term : Fundamental(40%) + Trend(30%) + RS(20%) + Sentiment(10%)
#   Swing     : EMA(25%) + MACD(25%) + RS(20%) + Volume(15%) + Candlestick(15%)
#   Intraday  : VWAP(30%) + Volume(25%) + Momentum(25%) + ATR(20%) [future]
# ================================================

import os
import sys
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Logging ───────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR       = os.path.join(BASE_DIR, "logs")
ORCH_LOG_FILE  = os.path.join(LOGS_DIR, "orchestration_log.csv")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Supabase (optional — falls back to CSV if unavailable) ────────────
try:
    from config.supabase_client import get_client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    def get_client():
        return None


# ════════════════════════════════════════════════
# BUCKET-SPECIFIC SCORING WEIGHTS
# Each bucket cares about different dimensions.
# These weights are SEPARATE from the global composite
# score — they reflect how each bucket makes decisions.
# ════════════════════════════════════════════════

BUCKET_SCORE_WEIGHTS = {
    "Long-Term": {
        # Long-term investors care most about business quality
        # and whether the trend supports a multi-week hold
        "fundamental":      0.40,   # Is the business financially strong?
        "trend":            0.30,   # Is the price in a sustained uptrend?
        "rs":               0.20,   # Is it beating NIFTY (relative strength)?
        "sentiment":        0.10,   # What's the news saying?
        # min entry score for this bucket
        "_min_score":       70,
        "_max_holding_days":365,
        "_min_holding_days":20,
    },
    "Swing": {
        # Swing traders care about momentum and short-term signals
        "ema":              0.25,   # EMA crossover — direction change confirmed?
        "macd":             0.25,   # MACD — momentum confirmed?
        "rs":               0.20,   # Beating market (momentum stocks outperform)
        "volume":           0.15,   # Volume confirms the move
        "candlestick":      0.15,   # Price action pattern at key level
        # min entry score
        "_min_score":       60,
        "_max_holding_days":15,
        "_min_holding_days":2,
    },
    "Intraday": {
        # Intraday — placeholder weights (not fully implemented yet)
        # Uses simplified composite score until VWAP/ATR are built
        "volume":           0.35,
        "momentum":         0.35,
        "trend":            0.30,
        "_min_score":       55,
        "_max_holding_days":1,
        "_min_holding_days":0,
    },
}

# Minimum buy votes (out of 4 strategies) per bucket
BUCKET_MIN_VOTES = {
    "Long-Term": 3,
    "Swing":     2,
    "Intraday":  1,
}

# Confluence thresholds — how many independent signals must agree
CONFLUENCE_HIGH   = 4   # All 4 agree → HIGH confluence
CONFLUENCE_MEDIUM = 3   # 3 agree     → MEDIUM
CONFLUENCE_LOW    = 2   # 2 agree     → LOW
CONFLUENCE_NONE   = 1   # 0-1 agree   → no confluence

# Decision values
DECISION_ACCEPT = "ACCEPT"
DECISION_REJECT = "REJECT"
DECISION_REVIEW = "REVIEW"    # Human should look at this


# ════════════════════════════════════════════════
# BUCKET-SPECIFIC SCORE CALCULATION
# Uses different dimension weights per bucket
# ════════════════════════════════════════════════

def calculate_bucket_score(bucket_name: str, individual_scores: dict) -> dict:
    """
    Calculate a bucket-specific weighted score using the dimensions
    that matter most for that bucket's strategy style.

    individual_scores: dict from scoring_engine.build_composite_score()
      Keys: "Trend", "Momentum", "Volatility", "Signal", "Regime",
            "Rel. Strength", "Fundamental", "Sentiment", "Volume",
            "Candlestick", "Mkt Structure"

    Returns:
      {
        bucket_score: int 0-100,
        component_breakdown: {dimension: weighted_contribution},
        missing_dimensions: [list of dims with no data],
      }

    Dimension name mapping (scoring_engine names → bucket weight keys):
      "Trend"        → "trend"
      "Momentum"     → "momentum"  / "macd" (approximated)
      "Rel. Strength"→ "rs"
      "Fundamental"  → "fundamental"
      "Sentiment"    → "sentiment"
      "Volume"       → "volume"
      "Candlestick"  → "candlestick"
      "Mkt Structure"→ (not separately weighted in bucket scores — folded into trend)
      EMA signal     → "ema" (approximated via Signal score)

    NOTE: We don't have separate EMA/MACD scores from scoring_engine —
    those are combined into "Signal" and "Momentum". For Swing bucket
    we approximate: EMA ≈ Signal score, MACD ≈ Momentum score.
    This is a pragmatic choice that avoids re-running strategy engines.
    """
    weights_cfg = BUCKET_SCORE_WEIGHTS.get(bucket_name, {})

    # ── Score name mapping ─────────────────────────
    # Maps bucket weight keys → scoring_engine dimension names
    SCORE_MAP = {
        "fundamental":  "Fundamental",
        "trend":        "Trend",
        "rs":           "Rel. Strength",
        "sentiment":    "Sentiment",
        "volume":       "Volume",
        "candlestick":  "Candlestick",
        "momentum":     "Momentum",
        # Approximations for bucket-specific keys:
        "ema":          "Signal",      # EMA crossover ≈ combined Signal vote
        "macd":         "Momentum",    # MACD ≈ Momentum dimension
    }

    total_weight    = 0.0
    weighted_sum    = 0.0
    breakdown       = {}
    missing         = []

    for weight_key, weight_val in weights_cfg.items():
        if weight_key.startswith("_"):
            continue   # Skip config keys like _min_score

        score_dim = SCORE_MAP.get(weight_key)
        if score_dim is None:
            missing.append(weight_key)
            continue

        dim_score = individual_scores.get(score_dim)
        if dim_score is None:
            dim_score = 50    # Neutral if dimension missing
            missing.append(weight_key)

        contribution  = dim_score * weight_val
        weighted_sum += contribution
        total_weight += weight_val

        breakdown[weight_key] = {
            "raw_score":    dim_score,
            "weight":       f"{int(weight_val * 100)}%",
            "contribution": round(contribution, 1),
        }

    # Normalize in case weights don't sum to exactly 1.0
    if total_weight > 0:
        bucket_score = round(weighted_sum / total_weight)
    else:
        bucket_score = 50

    return {
        "bucket_score":      max(0, min(100, bucket_score)),
        "component_breakdown": breakdown,
        "missing_dimensions":  missing,
    }


# ════════════════════════════════════════════════
# CONFLUENCE DETECTION
# How many independent signals agree on direction?
# ════════════════════════════════════════════════

def detect_confluence(
    combined_votes: dict,
    individual_scores: dict,
    regime: str,
) -> dict:
    """
    Count how many independent signals are aligned bullishly.

    Signals checked:
      1. Strategy votes (MA+RSI, EMA, Bollinger, MACD) — from combined_votes
      2. Volume confirmation — Volume score ≥ 60
      3. Market structure    — Mkt Structure score ≥ 60
      4. Candlestick pattern — Candlestick score ≥ 60
      5. Market regime       — Regime score ≥ 60
      6. Fundamental quality — Fundamental score ≥ 60

    Returns:
      confluence_count: int (how many of the above confirm BUY)
      confluence_level: "HIGH" / "MEDIUM" / "LOW" / "NONE"
      confirming_signals: [list of what agrees]
      conflicting_signals: [list of what disagrees]
    """
    confirming  = []
    conflicting = []

    buy_votes  = combined_votes.get("buy",  0)
    sell_votes = combined_votes.get("sell", 0)

    # 1. Strategy votes
    if buy_votes >= 3:
        confirming.append(f"Strategy votes: {buy_votes}/4 say BUY")
    elif buy_votes == 2:
        confirming.append(f"Strategy votes: {buy_votes}/4 say BUY (weak)")
    elif sell_votes >= 2:
        conflicting.append(f"Strategy votes: {sell_votes}/4 say SELL")

    # 2. Volume
    vol_score = individual_scores.get("Volume", 50)
    if vol_score >= 65:
        confirming.append(f"Volume confirms ({vol_score}/100)")
    elif vol_score <= 35:
        conflicting.append(f"Volume weak ({vol_score}/100) — below average")

    # 3. Market Structure
    ms_score = individual_scores.get("Mkt Structure", 50)
    if ms_score >= 65:
        confirming.append(f"Market structure bullish ({ms_score}/100)")
    elif ms_score <= 35:
        conflicting.append(f"Market structure bearish ({ms_score}/100)")

    # 4. Candlestick
    candle_score = individual_scores.get("Candlestick", 50)
    if candle_score >= 65:
        confirming.append(f"Candlestick pattern confirmed ({candle_score}/100)")
    elif candle_score <= 35:
        conflicting.append(f"Candlestick bearish/no pattern ({candle_score}/100)")

    # 5. Regime
    regime_score = individual_scores.get("Regime", 50)
    if regime_score >= 65:
        confirming.append(f"Market regime favorable ({regime})")
    elif regime_score <= 35:
        conflicting.append(f"Market regime unfavorable ({regime})")

    # 6. Fundamental quality (for long-term only — still counted generally)
    fund_score = individual_scores.get("Fundamental", 50)
    if fund_score >= 65:
        confirming.append(f"Fundamentals strong ({fund_score}/100)")
    elif fund_score <= 35:
        conflicting.append(f"Fundamentals weak ({fund_score}/100)")

    count = len(confirming)

    if count >= CONFLUENCE_HIGH:
        level = "HIGH 🟢🟢"
    elif count >= CONFLUENCE_MEDIUM:
        level = "MEDIUM 🟢"
    elif count >= CONFLUENCE_LOW:
        level = "LOW 🟡"
    else:
        level = "NONE ⚪"

    return {
        "confluence_count":    count,
        "confluence_level":    level,
        "confirming_signals":  confirming,
        "conflicting_signals": conflicting,
    }


# ════════════════════════════════════════════════
# CONFLICT DETECTION
# Returns severity and specific conflicts
# ════════════════════════════════════════════════

def detect_conflicts(
    combined_votes: dict,
    individual_scores: dict,
    suggested_bucket: str,
) -> dict:
    """
    Detect conflicting signals that should reduce confidence
    or trigger a REVIEW decision.

    Conflict types:
      HARD  → must resolve before entering (e.g. bear market + BUY signal)
      SOFT  → reduces confidence but doesn't block (e.g. weak volume on breakout)

    Returns:
      hard_conflicts: list of strings
      soft_conflicts: list of strings
      conflict_severity: "NONE" / "LOW" / "HIGH"
    """
    hard = []
    soft = []

    buy_votes  = combined_votes.get("buy",  0)
    sell_votes = combined_votes.get("sell", 0)
    hold_votes = combined_votes.get("hold", 0)

    # Hard: SELL signals present alongside BUY signals
    if buy_votes > 0 and sell_votes > 0:
        hard.append(
            f"Conflicting strategy signals: {buy_votes} BUY vs {sell_votes} SELL — "
            "strategies are disagreeing on direction"
        )

    # Hard: Regime score very low but signal says BUY
    regime_score = individual_scores.get("Regime", 50)
    if regime_score <= 25 and buy_votes >= 2:
        hard.append(
            f"BEAR market (Regime={regime_score}/100) with BUY signal — "
            "market conditions oppose this trade"
        )

    # Soft: Strong fundamental signal + weak technical (for Long-Term)
    if suggested_bucket == "Long-Term":
        fund_score = individual_scores.get("Fundamental", 50)
        trend_score = individual_scores.get("Trend", 50)
        if fund_score >= 70 and trend_score <= 35:
            soft.append(
                f"Strong fundamentals ({fund_score}/100) but weak trend ({trend_score}/100) — "
                "fundamentally good business in a price downtrend. Wait for trend to improve."
            )

    # Soft: Volume below average on a breakout signal
    vol_score = individual_scores.get("Volume", 50)
    ms_score  = individual_scores.get("Mkt Structure", 50)
    if ms_score >= 70 and vol_score <= 40:
        soft.append(
            f"Breakout signal (structure={ms_score}/100) but volume is low ({vol_score}/100) — "
            "breakout without volume is often a false move"
        )

    # Soft: Only 2 strategies agree for a Long-Term bucket
    if suggested_bucket == "Long-Term" and buy_votes < 3:
        soft.append(
            f"Long-Term bucket requires 3+ strategy votes — only {buy_votes}/4 agree. "
            "Lower conviction for a multi-week hold."
        )

    # Severity
    if hard:
        severity = "HIGH ⚠️"
    elif len(soft) >= 2:
        severity = "HIGH ⚠️"
    elif soft:
        severity = "LOW 🟡"
    else:
        severity = "NONE ✅"

    return {
        "hard_conflicts":    hard,
        "soft_conflicts":    soft,
        "conflict_severity": severity,
    }


# ════════════════════════════════════════════════
# REJECTION LAYER
# All reasons a trade can be blocked before execution
# ════════════════════════════════════════════════

def apply_rejection_filters(
    stock_name:      str,
    bucket_name:     str,
    bucket_score:    int,
    composite_score: int,
    buy_votes:       int,
    regime:          str,
    conflicts:       dict,
    proposed_value:  float = 0,
) -> tuple[bool, list[str]]:
    """
    Apply all rejection filters in sequence.
    Returns (approved: bool, rejection_reasons: list[str])

    Filters (in priority order):
      1. Bear market gate       — no new longs in full BEAR
      2. Bucket score threshold — bucket-specific min score
      3. Minimum vote count     — bucket requires N strategies to agree
      4. Hard conflict block    — conflicting signals require resolution
      5. Cooldown check         — was this stock stopped out recently?
      6. Portfolio risk gate    — bucket exposure, sector limits etc.
    """
    reasons = []

    # 1. Bear market
    if "BEAR" in str(regime).upper() and "WEAK" not in str(regime).upper():
        reasons.append(
            f"BEAR market ({regime}) — no new BUY orders. Capital protection mode."
        )

    # 2. Bucket score threshold
    min_score = BUCKET_SCORE_WEIGHTS.get(bucket_name, {}).get("_min_score", 60)
    if bucket_score < min_score:
        reasons.append(
            f"Bucket score {bucket_score}/100 below {bucket_name} minimum ({min_score}/100)."
        )

    # 3. Minimum vote count
    min_votes = BUCKET_MIN_VOTES.get(bucket_name, 2)
    if buy_votes < min_votes:
        reasons.append(
            f"Only {buy_votes}/4 strategies agree — {bucket_name} requires at least {min_votes}."
        )

    # 4. Hard conflicts block
    hard_conflicts = conflicts.get("hard_conflicts", [])
    if hard_conflicts:
        for c in hard_conflicts:
            reasons.append(f"Hard conflict: {c}")

    # 5. Cooldown
    try:
        from portfolio.position_manager import is_in_cooldown
        in_cd, until = is_in_cooldown(stock_name, bucket_name)
        if in_cd:
            reasons.append(
                f"In cooldown until {until} after previous stop loss in {bucket_name} bucket."
            )
    except Exception:
        pass

    # 6. Portfolio risk gate (M30)
    try:
        from risk.portfolio_risk import validate_portfolio_risk
        risk_result = validate_portfolio_risk(
            stock_name           = stock_name,
            stock_symbol         = stock_name + ".NS",
            bucket_name          = bucket_name,
            proposed_trade_value = proposed_value,
            regime               = regime,
            skip_correlation     = True,
        )
        if not risk_result.get("approved", True):
            reasons.append(f"Portfolio risk gate: {risk_result.get('summary', 'Risk limit exceeded')}")
    except Exception:
        pass   # Risk engine unavailable — don't block the trade

    approved = len(reasons) == 0
    return approved, reasons


# ════════════════════════════════════════════════
# AUDIT LOGGING
# Every orchestration decision — accepted AND rejected
# ════════════════════════════════════════════════

ORCH_LOG_COLS = [
    "Timestamp", "Stock", "Symbol", "Bucket",
    "Decision", "Bucket_Score", "Composite_Score",
    "Confluence_Count", "Confluence_Level",
    "Buy_Votes", "Regime",
    "Routing_Reason", "Rejection_Reason", "Summary",
]


def log_orchestration_decision(result: dict):
    """
    Append one orchestration decision to the audit log.
    Writes to Supabase (primary) and CSV (fallback).
    """
    entry = {
        "Timestamp":        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Stock":            result.get("stock",            ""),
        "Symbol":           result.get("symbol",           ""),
        "Bucket":           result.get("bucket",           ""),
        "Decision":         result.get("decision",         ""),
        "Bucket_Score":     result.get("bucket_score",     0),
        "Composite_Score":  result.get("composite_score",  0),
        "Confluence_Count": result.get("confluence_count", 0),
        "Confluence_Level": result.get("confluence_level", ""),
        "Buy_Votes":        result.get("buy_votes",        0),
        "Regime":           result.get("regime",           ""),
        "Routing_Reason":   result.get("routing_reason",   ""),
        "Rejection_Reason": " | ".join(result.get("rejection_reasons", [])),
        "Summary":          result.get("summary",          ""),
    }

    # ── Layer 1: Supabase ─────────────────────────────
    try:
        client = get_client()
        if client:
            client.table("orchestration_log").insert({
                "timestamp":        entry["Timestamp"],
                "stock":            entry["Stock"],
                "symbol":           entry["Symbol"],
                "bucket":           entry["Bucket"],
                "decision":         entry["Decision"],
                "bucket_score":     entry["Bucket_Score"],
                "composite_score":  entry["Composite_Score"],
                "confluence_count": entry["Confluence_Count"],
                "confluence_level": entry["Confluence_Level"],
                "buy_votes":        entry["Buy_Votes"],
                "regime":           entry["Regime"],
                "routing_reason":   entry["Routing_Reason"],
                "rejection_reason": entry["Rejection_Reason"],
                "summary":          entry["Summary"],
            }).execute()
    except Exception as e:
        print(f"⚠️ Supabase orchestration log failed: {e}")

    # ── Layer 2: CSV fallback ────────────────────────
    df = pd.DataFrame([entry])
    try:
        if os.path.exists(ORCH_LOG_FILE):
            df.to_csv(ORCH_LOG_FILE, mode='a', header=False, index=False)
        else:
            df.to_csv(ORCH_LOG_FILE, mode='w', header=True, index=False)
    except Exception as e:
        print(f"⚠️ Orchestration log CSV write failed: {e}")


def load_orchestration_log(max_rows: int = 200) -> pd.DataFrame:
    """Load the orchestration decision log for dashboard display. Tries Supabase first."""
    # ── Layer 1: Supabase ─────────────────────────────
    try:
        client = get_client()
        if client:
            response = (
                client.table("orchestration_log")
                .select("*")
                .order("timestamp", desc=True)
                .limit(max_rows)
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "timestamp":        "Timestamp",
                    "stock":            "Stock",
                    "symbol":           "Symbol",
                    "bucket":           "Bucket",
                    "decision":         "Decision",
                    "bucket_score":     "Bucket_Score",
                    "composite_score":  "Composite_Score",
                    "confluence_count": "Confluence_Count",
                    "confluence_level": "Confluence_Level",
                    "buy_votes":        "Buy_Votes",
                    "regime":           "Regime",
                    "routing_reason":   "Routing_Reason",
                    "rejection_reason": "Rejection_Reason",
                    "summary":          "Summary",
                })
                cols = [c for c in ORCH_LOG_COLS if c in df.columns]
                return df[cols].reset_index(drop=True)
            return pd.DataFrame(columns=ORCH_LOG_COLS)
    except Exception as e:
        print(f"⚠️ Supabase orchestration log load failed: {e}")
    # ── Layer 2: CSV fallback ────────────────────────
    if not os.path.exists(ORCH_LOG_FILE):
        return pd.DataFrame(columns=ORCH_LOG_COLS)
    try:
        df = pd.read_csv(ORCH_LOG_FILE)
        return df.sort_values("Timestamp", ascending=False).head(max_rows).reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=ORCH_LOG_COLS)


def clear_orchestration_log():
    """Clear the orchestration log from Supabase and CSV."""
    try:
        client = get_client()
        if client:
            client.table("orchestration_log").delete().neq("id", 0).execute()
    except Exception as e:
        print(f"⚠️ Could not clear Supabase orchestration log: {e}")
    if os.path.exists(ORCH_LOG_FILE):
        try:
            os.remove(ORCH_LOG_FILE)
        except Exception as e:
            print(f"⚠️ Could not clear orchestration log CSV: {e}")


# ════════════════════════════════════════════════
# MASTER FUNCTION
# Called by execution_loop.py for every stock
# ════════════════════════════════════════════════

def orchestrate_opportunity(
    stock_name:       str,
    symbol:           str,
    composite_score:  int,
    individual_scores: dict,
    combined_votes:   dict,
    final_signal:     str,
    regime:           str,
    suggested_bucket: str | None = None,
    proposed_value:   float = 0,
    log_decision:     bool = True,
) -> dict:
    """
    Master orchestration function.
    Call this for every stock the scanner identifies.

    Parameters:
      stock_name       : e.g. "RELIANCE"
      symbol           : Yahoo Finance symbol e.g. "RELIANCE.NS"
      composite_score  : 0-100 from scoring_engine.build_composite_score()
      individual_scores: dict of dimension scores from scoring_engine
      combined_votes   : {"buy": N, "sell": N, "hold": N}
      final_signal     : e.g. "STRONG BUY 🟢🟢"
      regime           : e.g. "BULL 🐂"
      suggested_bucket : If None, orchestrator picks it
      proposed_value   : Estimated trade value in ₹ (for risk gate)
      log_decision     : Whether to write to audit log (default True)

    Returns:
      {
        stock, symbol, bucket, decision,
        bucket_score, composite_score,
        component_breakdown,
        confluence_count, confluence_level,
        confirming_signals, conflicting_signals,
        conflict_severity, hard_conflicts, soft_conflicts,
        buy_votes, regime,
        routing_reason, rejection_reasons, summary,
        approved: bool,
      }
    """

    buy_votes  = combined_votes.get("buy",  0)
    sell_votes = combined_votes.get("sell", 0)

    # ── Step 1: Determine target bucket ───────────
    # If caller didn't supply one, use suggest_bucket() from capital_engine
    if suggested_bucket is None:
        try:
            from portfolio.capital_engine import suggest_bucket as _suggest
            suggestion    = _suggest(
                composite_score = composite_score,
                combined_signal = final_signal,
                buy_votes       = buy_votes,
                regime          = regime,
            )
            suggested_bucket = suggestion.get("suggested_bucket")
            routing_reason   = suggestion.get("reason", "")
        except Exception as e:
            suggested_bucket = None
            routing_reason   = f"Bucket suggestion failed: {e}"
    else:
        routing_reason = f"Bucket pre-assigned by caller: {suggested_bucket}"

    # No bucket available at all
    if suggested_bucket is None:
        result = {
            "stock":            stock_name,
            "symbol":           symbol,
            "bucket":           "—",
            "decision":         DECISION_REJECT,
            "bucket_score":     0,
            "composite_score":  composite_score,
            "component_breakdown": {},
            "confluence_count": 0,
            "confluence_level": "NONE ⚪",
            "confirming_signals":  [],
            "conflicting_signals": [],
            "conflict_severity":   "NONE ✅",
            "hard_conflicts":      [],
            "soft_conflicts":      [],
            "buy_votes":        buy_votes,
            "regime":           regime,
            "routing_reason":   routing_reason,
            "rejection_reasons":[routing_reason],
            "summary":          f"No suitable bucket for {stock_name}. {routing_reason}",
            "approved":         False,
        }
        if log_decision:
            log_orchestration_decision(result)
        return result

    # ── Step 2: Bucket-specific score ─────────────
    bucket_score_result = calculate_bucket_score(suggested_bucket, individual_scores)
    bucket_score        = bucket_score_result["bucket_score"]
    component_breakdown = bucket_score_result["component_breakdown"]

    # ── Step 3: Confluence detection ──────────────
    confluence = detect_confluence(combined_votes, individual_scores, regime)

    # ── Step 4: Conflict detection ─────────────────
    conflicts  = detect_conflicts(combined_votes, individual_scores, suggested_bucket)

    # ── Step 5: Rejection filters ─────────────────
    approved, rejection_reasons = apply_rejection_filters(
        stock_name      = stock_name,
        bucket_name     = suggested_bucket,
        bucket_score    = bucket_score,
        composite_score = composite_score,
        buy_votes       = buy_votes,
        regime          = regime,
        conflicts       = conflicts,
        proposed_value  = proposed_value,
    )

    # ── Step 6: Final decision ─────────────────────
    # ACCEPT  → approved AND no hard conflicts
    # REVIEW  → approved but has soft conflicts with HIGH confluence
    # REJECT  → not approved OR hard conflicts present
    hard_conflicts = conflicts.get("hard_conflicts", [])
    soft_conflicts = conflicts.get("soft_conflicts", [])

    if not approved:
        decision = DECISION_REJECT
    elif hard_conflicts:
        decision = DECISION_REJECT
    elif soft_conflicts and confluence["confluence_count"] < CONFLUENCE_LOW:
        # Soft conflicts + low confluence = REVIEW (human should look)
        decision = DECISION_REVIEW
    else:
        decision = DECISION_ACCEPT

    # ── Step 7: Plain English summary ─────────────
    summary = _build_summary(
        stock_name, suggested_bucket, decision,
        bucket_score, composite_score,
        confluence, conflicts,
        buy_votes, regime,
        rejection_reasons,
    )

    result = {
        "stock":            stock_name,
        "symbol":           symbol,
        "bucket":           suggested_bucket,
        "decision":         decision,
        "bucket_score":     bucket_score,
        "composite_score":  composite_score,
        "component_breakdown": component_breakdown,
        "confluence_count": confluence["confluence_count"],
        "confluence_level": confluence["confluence_level"],
        "confirming_signals":  confluence["confirming_signals"],
        "conflicting_signals": confluence["conflicting_signals"],
        "conflict_severity":   conflicts["conflict_severity"],
        "hard_conflicts":      hard_conflicts,
        "soft_conflicts":      soft_conflicts,
        "buy_votes":        buy_votes,
        "regime":           regime,
        "routing_reason":   routing_reason,
        "rejection_reasons":rejection_reasons,
        "summary":          summary,
        "approved":         (decision == DECISION_ACCEPT),
    }

    if log_decision:
        log_orchestration_decision(result)

    return result


def _build_summary(
    stock_name, bucket, decision,
    bucket_score, composite_score,
    confluence, conflicts,
    buy_votes, regime, rejection_reasons,
) -> str:
    """Plain English summary of the orchestration decision."""
    lines = []

    if decision == DECISION_ACCEPT:
        lines.append(
            f"✅ **{stock_name} → {bucket}** ACCEPTED | "
            f"Bucket Score: {bucket_score}/100 | Composite: {composite_score}/100"
        )
        lines.append(
            f"Confluence: {confluence['confluence_level']} "
            f"({confluence['confluence_count']} signals confirming)"
        )
        if confluence["confirming_signals"]:
            lines.append("Confirming: " + " | ".join(confluence["confirming_signals"][:3]))
        if conflicts["soft_conflicts"]:
            lines.append("⚠️ Watch: " + " | ".join(conflicts["soft_conflicts"]))

    elif decision == DECISION_REVIEW:
        lines.append(
            f"🟡 **{stock_name} → {bucket}** REVIEW — human check needed | "
            f"Score: {bucket_score}/100"
        )
        if conflicts["soft_conflicts"]:
            lines.append("Soft conflicts: " + " | ".join(conflicts["soft_conflicts"]))

    else:
        lines.append(
            f"❌ **{stock_name}** REJECTED for {bucket} | "
            f"Score: {bucket_score}/100 | Votes: {buy_votes}/4"
        )
        if rejection_reasons:
            lines.append("Reasons: " + " | ".join(rejection_reasons[:2]))

    return " ".join(lines)


# ════════════════════════════════════════════════
# BATCH ORCHESTRATION
# Convenience wrapper for scanning multiple stocks
# Used by execution_loop.py
# ════════════════════════════════════════════════

def orchestrate_batch(opportunities: list[dict]) -> list[dict]:
    """
    Run orchestrate_opportunity() for a list of stock analyses.
    Each item in opportunities must be a dict with:
      stock_name, symbol, composite_score, individual_scores,
      combined_votes, final_signal, regime

    Returns list of orchestration results.
    Accepted ones are sorted by bucket_score descending.
    This means the best opportunities go first in the execution queue.
    """
    results   = []
    accepted  = []
    reviewed  = []
    rejected  = []

    for opp in opportunities:
        try:
            result = orchestrate_opportunity(
                stock_name        = opp.get("stock_name", ""),
                symbol            = opp.get("symbol", ""),
                composite_score   = opp.get("composite_score", 0),
                individual_scores = opp.get("individual_scores", {}),
                combined_votes    = opp.get("combined_votes", {}),
                final_signal      = opp.get("final_signal", ""),
                regime            = opp.get("regime", "UNKNOWN"),
                suggested_bucket  = opp.get("suggested_bucket"),
                proposed_value    = opp.get("proposed_value", 0),
                log_decision      = True,
            )
            results.append(result)

            if result["decision"] == DECISION_ACCEPT:
                accepted.append(result)
            elif result["decision"] == DECISION_REVIEW:
                reviewed.append(result)
            else:
                rejected.append(result)

        except Exception as e:
            print(f"⚠️ Orchestration error for {opp.get('stock_name','?')}: {e}")

    # Sort accepted by bucket_score descending (best first)
    accepted.sort(key=lambda x: x["bucket_score"], reverse=True)

    return {
        "accepted":  accepted,
        "reviewed":  reviewed,
        "rejected":  rejected,
        "all":       results,
        "counts": {
            "accepted": len(accepted),
            "reviewed": len(reviewed),
            "rejected": len(rejected),
            "total":    len(results),
        },
    }


# ════════════════════════════════════════════════
# SUMMARY STATS — for dashboard display
# ════════════════════════════════════════════════

def get_orchestration_stats() -> dict:
    """
    High-level stats from the orchestration log.
    Used by the Auto Pilot tab.
    """
    df = load_orchestration_log(max_rows=500)
    if df.empty:
        return {
            "total": 0, "accepted": 0,
            "reviewed": 0, "rejected": 0,
            "accept_rate": "0%",
        }

    total    = len(df)
    accepted = len(df[df["Decision"] == DECISION_ACCEPT])
    reviewed = len(df[df["Decision"] == DECISION_REVIEW])
    rejected = len(df[df["Decision"] == DECISION_REJECT])

    return {
        "total":       total,
        "accepted":    accepted,
        "reviewed":    reviewed,
        "rejected":    rejected,
        "accept_rate": f"{round(accepted / total * 100, 1)}%" if total > 0 else "0%",
    }
