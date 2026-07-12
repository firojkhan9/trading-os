# ================================================
# FILE: analytics/constants.py
# PURPOSE: Central constants for the Analytics module — Milestone 1
#
# WHY THIS FILE EXISTS:
#   Per ADR Section 3.3 ("No Duplicate Business Logic") and Section 54
#   ("Coding Standards" — descriptive names, minimal duplication), every
#   table name, CSV filename, column name, and enumerated value used by
#   the Analytics package lives here ONCE. Future files (models.py,
#   storage.py, and later recorder.py / queries.py) import from this
#   module instead of re-typing strings.
#
# WHAT THIS FILE DOES NOT DO:
#   - No persistence
#   - No business logic
#   - No trading logic
#   - No schema validation (that lives in models.py)
#
# NAMING CONVENTION:
#   Follows the same style already used across the project for table
#   names (position_lifecycle, orchestration_log, decision_log,
#   loop_decisions) and CSV filenames (logs/<name>.csv).
# ================================================

import os

# ════════════════════════════════════════════════
# STORAGE LOCATIONS
# ════════════════════════════════════════════════

# Supabase table name — primary storage layer (see storage.py)
ANALYTICS_TABLE_NAME = "analytics_records"

# CSV fallback path — same LOGS_DIR convention as every other module
# (config/settings.py, portfolio/position_manager.py, strategies/orchestrator.py, etc.)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
ANALYTICS_CSV_FILE = os.path.join(LOGS_DIR, "analytics_records.csv")

# Primary key used for matching entry writes to exit updates.
# Per ADR Section 30: "Exit updates locate the existing analytics
# record using: position_id. This is the only approved lookup key."
ANALYTICS_PRIMARY_KEY = "position_id"

# Secondary unique identifier for the record itself (distinct from
# position_id because NO_TRADE / REJECTED evaluations never have a
# position — see models.py for details).
ANALYTICS_RECORD_ID_FIELD = "record_id"


# ════════════════════════════════════════════════
# DECISION STATES (ADR Section 36)
# Every evaluation ends in exactly one of these.
# ════════════════════════════════════════════════

DECISION_BUY       = "BUY"
DECISION_SELL      = "SELL"
DECISION_NO_TRADE  = "NO_TRADE"
DECISION_REJECTED  = "REJECTED"
DECISION_ERROR     = "ERROR"

VALID_DECISIONS = {
    DECISION_BUY,
    DECISION_SELL,
    DECISION_NO_TRADE,
    DECISION_REJECTED,
    DECISION_ERROR,
}


# ════════════════════════════════════════════════
# REJECTION STAGES (ADR Section 37)
# Where in the pipeline an evaluation was rejected.
# ════════════════════════════════════════════════

STAGE_SCORE_GATE     = "SCORE_GATE"
STAGE_VOTE_GATE      = "VOTE_GATE"
STAGE_REGIME_GATE    = "REGIME_GATE"
STAGE_STRUCTURE_GATE = "STRUCTURE_GATE"
STAGE_RISK_GATE      = "RISK_GATE"
STAGE_CAPITAL_GATE   = "CAPITAL_GATE"
STAGE_EXECUTION_RULE = "EXECUTION_RULE"

VALID_REJECTION_STAGES = {
    STAGE_SCORE_GATE,
    STAGE_VOTE_GATE,
    STAGE_REGIME_GATE,
    STAGE_STRUCTURE_GATE,
    STAGE_RISK_GATE,
    STAGE_CAPITAL_GATE,
    STAGE_EXECUTION_RULE,
}


# ════════════════════════════════════════════════
# TRADE OUTCOME (exit-side only — ADR Section 34.G)
# ════════════════════════════════════════════════

OUTCOME_WIN      = "WIN"
OUTCOME_LOSS     = "LOSS"
OUTCOME_BREAKEVEN= "BREAKEVEN"
OUTCOME_OPEN     = "OPEN"          # trade executed, not yet exited
OUTCOME_NA       = "N/A"           # no trade was ever executed

VALID_OUTCOMES = {
    OUTCOME_WIN,
    OUTCOME_LOSS,
    OUTCOME_BREAKEVEN,
    OUTCOME_OPEN,
    OUTCOME_NA,
}


# ════════════════════════════════════════════════
# TRADE SOURCE (supports future Zerodha per ADR Section 50)
# ════════════════════════════════════════════════

SOURCE_PAPER   = "PAPER"
SOURCE_ZERODHA = "ZERODHA"

VALID_SOURCES = {SOURCE_PAPER, SOURCE_ZERODHA}


# ════════════════════════════════════════════════
# ANALYTICS RECORD COLUMNS (ADR Section 34)
# One denormalized row per evaluated stock.
# Grouped exactly per the ADR's logical data groups A-G.
# All columns stored as text (see models.py for rationale —
# mirrors position_lifecycle's LIFECYCLE_COLUMNS convention).
# ════════════════════════════════════════════════

# --- A. Identity ---
GROUP_IDENTITY = [
    "record_id",         # unique per analytics record (generated at entry write)
    "cycle_id",           # identifies which execution loop cycle produced this
    "position_id",        # set only if a trade was executed; the exit-update lookup key
    "timestamp",           # when this record was created
    "stock",               # e.g. "RELIANCE"
    "symbol",               # e.g. "RELIANCE.NS"
]

# --- B. Market Context ---
GROUP_MARKET_CONTEXT = [
    "regime",              # e.g. "BULL", "BEAR", "SIDEWAYS"
    "bucket",               # "Long-Term" / "Swing" / "Intraday" / ""
    "strategy",             # which strategy/engine produced this evaluation
    "source",               # PAPER / ZERODHA
]

# --- C. Scoring ---
GROUP_SCORING = [
    "composite_score",
    "individual_scores",   # JSON string — execution's own dimension scores, copied verbatim
    "buy_votes",
    "sell_votes",
    "confluence_count",
]

# --- D. Pipeline Results ---
GROUP_PIPELINE_RESULTS = [
    "passed_score",
    "passed_votes",
    "passed_regime",
    "passed_structure",
    "passed_risk",
    "passed_capital",
    "executed",
]

# --- E. Decision Information ---
GROUP_DECISION = [
    "decision",             # one of VALID_DECISIONS
    "execution_result",     # e.g. "EXECUTED" / "REJECTED" / "ERROR" string from execution
    "rejection_stage",      # one of VALID_REJECTION_STAGES, or ""
    "rejection_reason",     # plain-English reason, copied verbatim from execution
    "decision_timestamp",
]

# --- F. Trade Information (entry side — populated only if a trade executed) ---
GROUP_TRADE = [
    "entry_price",
    "quantity",
    "capital_used",
    "trade_source",         # PAPER / ZERODHA
]

# --- G. Exit Information (populated only after position closure) ---
GROUP_EXIT = [
    "exit_price",
    "exit_time",
    "exit_reason",
    "holding_days",
    "realized_pnl",
    "pnl_pct",
    "outcome",               # one of VALID_OUTCOMES
]

# Full column list, in group order — this is the canonical schema.
ANALYTICS_COLUMNS = (
    GROUP_IDENTITY
    + GROUP_MARKET_CONTEXT
    + GROUP_SCORING
    + GROUP_PIPELINE_RESULTS
    + GROUP_DECISION
    + GROUP_TRADE
    + GROUP_EXIT
    + ["last_updated"]       # bookkeeping — set on every write, entry or exit
)

# Fields that update_record_outcome() (storage.py) is allowed to touch.
# Everything else on an existing record is immutable after the entry
# write (ADR Section 16 — "Record Immutability").
MUTABLE_OUTCOME_FIELDS = set(GROUP_EXIT) | {"last_updated"}
