# ================================================
# FILE: analytics/recorder.py
# PURPOSE: Analytics Recorder — Milestone 2
#
# WHAT THIS FILE DOES:
#   Owns the Analytics Record LIFECYCLE. It is the only place that
#   knows an "entry write" means "build a record and persist it" and
#   an "exit update" means "locate that record by position_id and
#   update only its outcome fields" (ADR Sections 14-17, 30).
#
#   Public interface (ADR Section 19 — kept intentionally small):
#     - record_entry(snapshot)                  → creates + persists
#                                                    one new record
#     - record_exit(position_id, exit_info)      → updates the
#                                                    existing record's
#                                                    outcome fields
#
# WHAT THIS FILE OWNS (ADR Section 9 — Execution Module list,
# Section 51 — Ownership Boundaries):
#   - record_id generation
#   - cycle-level timestamps (timestamp, decision_timestamp when
#     execution didn't supply one, created_at, last_updated)
#   - calling models.py to shape + validate the record
#   - calling storage.py to persist it
#
# WHAT THIS FILE NEVER DOES (ADR Section 18, and the prompt's
# explicit boundary list):
#   - fetch prices / call yfinance
#   - calculate indicators, scores, votes, regimes
#   - call orchestrator, capital_engine, position_manager,
#     decision_engine, or any strategy/execution module
#   - derive or infer any trading value that execution did not
#     already supply in the snapshot
#   - branch execution's behaviour, or return anything execution is
#     expected to act on — this is fire-and-forget (ADR Section 20)
#
# FAILURE POLICY (ADR Section 27-28):
#   Every public function here catches its own exceptions and
#   returns a status dict. It never raises. A broken Supabase
#   connection, a malformed snapshot, or a missing record must never
#   propagate up into the execution loop and interrupt trading.
# ================================================

import uuid
from datetime import datetime

from analytics.models import (
    build_record_from_snapshot,
    validate_record_shape,
)
from analytics.storage import (
    append,
    upsert,
    find_by,
    update_fields,
)
from analytics.constants import (
    ANALYTICS_RECORD_ID_FIELD,   # "record_id"
    ANALYTICS_PRIMARY_KEY,        # "position_id"
    MUTABLE_OUTCOME_FIELDS,       # GROUP_EXIT fields + "last_updated"
)


# ════════════════════════════════════════════════
# INTERNAL HELPERS — recorder-owned bookkeeping only
# ════════════════════════════════════════════════

def _now_str() -> str:
    """Single timestamp format used everywhere in this file."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _generate_record_id() -> str:
    """
    Recorder-owned identity. Execution never supplies this — a
    snapshot describes trading facts, not analytics bookkeeping
    (ADR Section 22: "Analytics Record" is owned by analytics).
    """
    return uuid.uuid4().hex


# ════════════════════════════════════════════════
# ENTRY WRITE
# ════════════════════════════════════════════════

def record_entry(snapshot: dict) -> dict:
    """
    Create and persist ONE new Analytics Record from an execution
    snapshot (ADR Section 14 — Entry Write).

    Parameters:
      snapshot : plain dict already computed by execution. Every
                 field is treated as read-only trading fact. This
                 function copies it — it never calculates, derives,
                 or fills in missing trading values.

    Recorder-owned fields assigned here (never taken from snapshot,
    even if present — identity/bookkeeping is analytics' own concern):
      record_id, timestamp, created_at, last_updated

    decision_timestamp is filled from the same "now" ONLY if
    execution did not already provide one in the snapshot — the
    exact moment execution decided is execution's fact if it chooses
    to supply it, so recorder does not overwrite an existing value.

    Returns:
      {"status": "OK", "record_id": "..."} on success
      {"status": "ERROR", "reason": "..."} on any failure

    This function never raises. A failure here must never interrupt
    the execution loop (ADR Section 20, 27-28).
    """
    try:
        if not isinstance(snapshot, dict):
            return {"status": "ERROR", "reason": "snapshot must be a dict"}

        now = _now_str()

        record = build_record_from_snapshot(snapshot)

        # ── Recorder-owned metadata — always assigned here ────
        # NOTE: "timestamp" is the single creation-time field per
        # ANALYTICS_COLUMNS (GROUP_IDENTITY). There is no separate
        # "created_at" column in the schema — a previous version of
        # this function set one anyway, which silently added a stray
        # column to the CSV fallback (storage.append()'s CSV branch
        # does not filter to ANALYTICS_COLUMNS the way the Supabase
        # branch does). Do not reintroduce it without first adding
        # "created_at" to ANALYTICS_COLUMNS in constants.py.
        record[ANALYTICS_RECORD_ID_FIELD] = _generate_record_id()
        record["timestamp"]    = now
        record["last_updated"] = now

        # decision_timestamp: only fill if execution left it unset —
        # this is the one field that could plausibly be either side's
        # to set, so recorder defers to execution's own value first.
        if not record.get("decision_timestamp"):
            record["decision_timestamp"] = now

        # ── Structural validation only (models.py owns the rules) ─
        is_valid, problems = validate_record_shape(record)
        if not is_valid:
            return {
                "status": "ERROR",
                "reason": f"Record failed validation: {'; '.join(problems)}",
            }

        # ── Persist — storage.py decides Supabase vs CSV ─────────
        result = append(record)
        if result.get("status") != "OK":
            return {
                "status": "ERROR",
                "reason": f"Persistence failed: {result.get('reason', 'unknown')}",
            }

        return {"status": "OK", "record_id": record[ANALYTICS_RECORD_ID_FIELD]}

    except Exception as e:
        # Analytics must never take execution down with it.
        return {"status": "ERROR", "reason": str(e)}


# ════════════════════════════════════════════════
# EXIT UPDATE
# ════════════════════════════════════════════════

def record_exit(position_id: str, exit_info: dict) -> dict:
    """
    Update the existing Analytics Record for a closed position
    (ADR Section 15 — Exit Write, Section 30 — Position Matching).

    Locates the record using position_id — the ONLY approved lookup
    key (ADR Section 30). Updates ONLY fields that belong to the
    exit-side / outcome group (MUTABLE_OUTCOME_FIELDS from
    constants.py, mirroring models.py's own enum-shape rules).
    Entry-side facts are never touched here — that is enforced by
    filtering, not by trusting the caller (ADR Section 16 — Record
    Immutability).

    Parameters:
      position_id : the position identifier used at entry time.
                    If no record exists with this position_id, that
                    is reported as an error — recorder never creates
                    a new record from an exit call.
      exit_info   : plain dict of outcome-side values already
                    computed by execution (exit_price, exit_time,
                    exit_reason, holding_days, realized_pnl,
                    pnl_pct, outcome, ...). Any key not in
                    MUTABLE_OUTCOME_FIELDS is silently ignored —
                    recorder does not let an exit call smuggle in
                    changes to entry-side facts.

    Returns:
      {"status": "OK"} on success
      {"status": "ERROR", "reason": "..."} on any failure
      (including "no record found for this position_id")

    This function never raises.
    """
    try:
        if not position_id:
            return {"status": "ERROR", "reason": "position_id is required"}
        if not isinstance(exit_info, dict):
            return {"status": "ERROR", "reason": "exit_info must be a dict"}

        existing = find_by(ANALYTICS_PRIMARY_KEY, position_id)
        if existing is None:
            return {
                "status": "ERROR",
                "reason": f"No analytics record found for position_id={position_id!r}",
            }

        # ── Filter to outcome fields only — immutability guard ───
        updates = {
            field: value
            for field, value in exit_info.items()
            if field in MUTABLE_OUTCOME_FIELDS
        }
        updates["last_updated"] = _now_str()

        result = update_fields(ANALYTICS_PRIMARY_KEY, position_id, updates)
        if result.get("status") != "OK":
            return {
                "status": "ERROR",
                "reason": f"Persistence failed: {result.get('reason', 'unknown')}",
            }

        return {"status": "OK"}

    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}
