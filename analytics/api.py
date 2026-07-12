# ================================================
# FILE: analytics/api.py
# PURPOSE: Analytics Facade / Public API — Milestone 3
#
# WHAT THIS FILE IS:
#   The ONLY interface the rest of Trading OS (execution_loop.py,
#   position_manager.py, or any future caller) should use to talk to
#   the Analytics module.
#
#   Per ADR Section 19 ("Public Interface Contract") the public
#   surface must stay intentionally small — this file exposes exactly
#   two operations (record_entry, record_exit), matching recorder.py's
#   own contract, plus a small set of re-exported constants so callers
#   never need to reach into analytics.constants or analytics.models
#   directly to build a snapshot.
#
# WHAT THIS FILE DOES:
#   - Delegates record_entry() / record_exit() straight to recorder.py
#   - Re-exports the enum constants (decisions, rejection stages,
#     outcomes, sources) so execution has one single import to reach
#     for — nothing more than name forwarding, no logic attached
#
# WHAT THIS FILE NEVER DOES (ADR Sections 9, 18, 19, 51):
#   - No business logic
#   - No calculations (scores, votes, regimes, P&L, anything)
#   - No validation logic — that already lives in models.py, invoked
#     by recorder.py
#   - No storage logic — that already lives in storage.py, invoked
#     by recorder.py
#   - No trading logic
#   - No imports from execution, strategies, portfolio, or risk
#     modules
#   - No imports of analytics.storage or analytics.models — only
#     recorder.py (and constants.py for re-export) are touched here,
#     keeping this file thin and free of internal implementation
#     details
#
# FAILURE POLICY:
#   Identical to recorder.py (ADR Sections 20, 27-28) — this facade
#   adds no new failure modes. record_entry()/record_exit() already
#   never raise; this file simply forwards their return values
#   unchanged.
# ================================================

from analytics.recorder import (
    record_entry as _record_entry,
    record_exit as _record_exit,
)

from analytics.constants import (
    # Decision states (ADR Section 36)
    DECISION_BUY,
    DECISION_SELL,
    DECISION_NO_TRADE,
    DECISION_REJECTED,
    DECISION_ERROR,
    # Rejection stages (ADR Section 37)
    STAGE_SCORE_GATE,
    STAGE_VOTE_GATE,
    STAGE_REGIME_GATE,
    STAGE_STRUCTURE_GATE,
    STAGE_RISK_GATE,
    STAGE_CAPITAL_GATE,
    STAGE_EXECUTION_RULE,
    # Trade outcomes (ADR Section 34.G)
    OUTCOME_WIN,
    OUTCOME_LOSS,
    OUTCOME_BREAKEVEN,
    OUTCOME_OPEN,
    OUTCOME_NA,
    # Trade source (ADR Section 50)
    SOURCE_PAPER,
    SOURCE_ZERODHA,
)


# ════════════════════════════════════════════════
# PUBLIC API — the only two operations Analytics exposes
# ════════════════════════════════════════════════

def record_entry(snapshot: dict) -> dict:
    """
    Record the outcome of one completed execution evaluation.

    Call this once execution has finished evaluating a stock and
    knows its final decision (BUY / SELL / NO_TRADE / REJECTED /
    ERROR) — pass everything already computed as `snapshot` (ADR
    Section 22, the Snapshot Contract). This function does not
    calculate, validate trading correctness, or infer any missing
    value — it only creates and persists one Analytics Record.

    This call is fire-and-forget (ADR Section 20): execution should
    call it and move on, never branch on its return value, never
    wait for it, never let its failure interrupt trading.

    Parameters:
      snapshot : plain dict of already-computed values — identity,
                 market context, scores, votes, pipeline results,
                 decision info, and (if a trade executed) entry-side
                 trade info. See analytics/constants.py
                 ANALYTICS_COLUMNS for the full recognised field list.

    Returns:
      {"status": "OK", "record_id": "..."} on success
      {"status": "ERROR", "reason": "..."} on failure — never raises.
    """
    return _record_entry(snapshot)


def record_exit(position_id: str, exit_info: dict) -> dict:
    """
    Record the outcome of a closed position.

    Call this once a previously-entered position has exited — locates
    the existing Analytics Record by position_id (ADR Section 30, the
    only approved lookup key) and updates only its outcome-side
    fields (exit price, exit time, exit reason, holding days, P&L,
    outcome). Entry-side facts recorded at record_entry() time remain
    untouched (ADR Section 16, Record Immutability).

    This call is fire-and-forget, same as record_entry().

    Parameters:
      position_id : the same position identifier used at entry time.
      exit_info   : plain dict of already-computed exit-side values,
                    e.g. {"exit_price": ..., "exit_time": ...,
                    "exit_reason": ..., "holding_days": ...,
                    "realized_pnl": ..., "pnl_pct": ...,
                    "outcome": ...}.

    Returns:
      {"status": "OK"} on success
      {"status": "ERROR", "reason": "..."} on failure — never raises.
    """
    return _record_exit(position_id, exit_info)


# ════════════════════════════════════════════════
# RE-EXPORTED CONSTANTS
# Pure name forwarding — no logic. Lets callers build a snapshot
# dict using the same enum values the schema expects, without ever
# importing analytics.constants (or analytics.models/storage)
# directly.
# ════════════════════════════════════════════════

__all__ = [
    # functions
    "record_entry",
    "record_exit",
    # decisions
    "DECISION_BUY",
    "DECISION_SELL",
    "DECISION_NO_TRADE",
    "DECISION_REJECTED",
    "DECISION_ERROR",
    # rejection stages
    "STAGE_SCORE_GATE",
    "STAGE_VOTE_GATE",
    "STAGE_REGIME_GATE",
    "STAGE_STRUCTURE_GATE",
    "STAGE_RISK_GATE",
    "STAGE_CAPITAL_GATE",
    "STAGE_EXECUTION_RULE",
    # outcomes
    "OUTCOME_WIN",
    "OUTCOME_LOSS",
    "OUTCOME_BREAKEVEN",
    "OUTCOME_OPEN",
    "OUTCOME_NA",
    # sources
    "SOURCE_PAPER",
    "SOURCE_ZERODHA",
]
