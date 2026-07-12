# ================================================
# FILE: analytics/models.py
# PURPOSE: Analytics Record schema — Milestone 1 (revised)
#
# WHAT THIS FILE DOES:
#   Defines the shape of one Analytics Record (ADR Section 33-34:
#   one denormalized row per evaluated stock) and provides:
#     - build_empty_record()          → a fully-keyed default record
#     - build_record_from_snapshot()   → maps an execution-provided
#                                          snapshot dict onto the schema
#     - validate_record_shape()        → STRUCTURAL checks only
#
# WHAT THIS FILE DOES NOT DO (ADR Section 18, and this revision):
#   - Does NOT persist anything (that's storage.py)
#   - Does NOT calculate scores, votes, regimes, or any trading value
#   - Does NOT derive or infer missing trading values
#   - Does NOT decide what the record's identity/primary key is —
#     that decision belongs to the future recorder.py. This file
#     never assumes record_id (or any other field) is "the" key.
#   - Does NOT validate trading correctness (e.g. "is this score
#     good enough", "does this entry price make sense"). Only
#     schema shape: required fields present, values match the
#     declared enum/type where one exists in constants.py.
#
# TYPE CONVENTION (revised):
#   Fields keep natural Python types — int/float/bool/str/None —
#   rather than being forced to strings. A missing value is
#   represented as None uniformly, which behaves correctly across
#   plain dicts, pandas, and JSON (Supabase) without extra
#   conversion logic living in this module. Any type coercion needed
#   purely for CSV/Supabase transport happens in storage.py at the
#   write boundary, not here — this module describes the record as
#   Python would naturally represent it.
#
# SNAPSHOT CONTRACT (ADR Section 22-23):
#   Execution owns the snapshot dict it will eventually pass to the
#   future Analytics Recorder. Analytics treats every snapshot field
#   as read-only and never modifies it. This module only maps
#   snapshot keys onto Analytics Record columns — no calculation,
#   no invented values.
# ================================================

from analytics.constants import (
    ANALYTICS_COLUMNS,
    VALID_DECISIONS,
    VALID_REJECTION_STAGES,
    VALID_OUTCOMES,
    VALID_SOURCES,
    OUTCOME_NA,
    SOURCE_PAPER,
)


# ════════════════════════════════════════════════
# STRUCTURAL DEFAULTS
# ════════════════════════════════════════════════

# Most fields default to None — the universal "not yet known" marker.
# Only a couple of purely bookkeeping fields get a non-None default,
# and both are structural/administrative, not trading-derived:
#   - source defaults to PAPER because that's this project's current
#     mode of operation (paper trading), not a guessed trading fact.
#   - outcome defaults to OUTCOME_NA because "no outcome yet" is a
#     valid, honest structural state — not a derived trading value.
_FIELD_DEFAULTS = {
    "source": SOURCE_PAPER,
    "outcome": OUTCOME_NA,
}


def build_empty_record() -> dict:
    """
    Return a fully-keyed Analytics Record dict with every column
    from ANALYTICS_COLUMNS present. Values default to None unless a
    structural default is declared in _FIELD_DEFAULTS above.

    This is the base every record starts from. It does NOT assign a
    record_id, position_id, or timestamp — identity and bookkeeping
    strategy belongs to the future recorder.py, not to this schema.
    """
    return {col: _FIELD_DEFAULTS.get(col, None) for col in ANALYTICS_COLUMNS}


# ════════════════════════════════════════════════
# BUILD FROM EXECUTION SNAPSHOT
# ════════════════════════════════════════════════

def build_record_from_snapshot(snapshot: dict) -> dict:
    """
    Map an execution-provided snapshot dict onto the Analytics Record
    schema. Pure mapping — no calculation, no inference, no type
    coercion. Whatever type execution supplies (int, float, bool,
    str, dict, None) is copied through as-is.

    Parameters:
      snapshot : plain dict supplied by execution (ADR Section 22).
                 Keys not found in ANALYTICS_COLUMNS are ignored —
                 analytics never invents new columns from arbitrary
                 execution output. Keys in ANALYTICS_COLUMNS that are
                 absent from snapshot keep their structural default.

    Returns:
      A fully-keyed record dict, natural Python types, ready to be
      handed to storage.py by the future recorder.

    NOTE: This function does not generate or require a record_id.
    Whether/how a record is identified for persistence is entirely a
    decision for recorder.py (Milestone 2), not this schema.
    """
    record = build_empty_record()

    for col in ANALYTICS_COLUMNS:
        if col in snapshot:
            record[col] = snapshot[col]

    return record


# ════════════════════════════════════════════════
# STRUCTURAL VALIDATION ONLY
# ════════════════════════════════════════════════

def validate_record_shape(record: dict) -> tuple[bool, list[str]]:
    """
    STRUCTURAL validation only — never business/trading validation.

    Checks performed:
      1. Schema shape — every column in ANALYTICS_COLUMNS is present
         as a key on the record (missing columns are reported, not
         silently filled in — the caller decides how to handle that).
      2. Minimum required identity — 'stock' and 'symbol' are present
         and non-empty. These two are the only fields treated as
         universally required at the schema level, because without
         them a record cannot even be described as "about a stock".
         Nothing else (record_id, position_id, timestamp, decision,
         etc.) is required here — assigning those is a recorder-level
         concern, not a schema-level one.
      3. Enum shape — IF a value is present for a field that has a
         declared closed set of valid values in constants.py
         (decision, rejection_stage, outcome, source, trade_source),
         it must be a member of that set. This is a type/shape check
         (same category as "this column must be an integer"), not a
         judgement about whether the value makes trading sense.

    This function deliberately does NOT check things like:
      - whether entry_price is positive
      - whether a BUY decision has an entry_price set
      - whether composite_score is within a sensible range
      - whether rejection_reason is consistent with rejection_stage
    Those are business rules and are out of scope for this module.

    Returns:
      (is_valid: bool, problems: list[str])
    """
    problems = []

    missing_cols = [c for c in ANALYTICS_COLUMNS if c not in record]
    if missing_cols:
        problems.append(f"Missing columns: {missing_cols}")

    for required in ("stock", "symbol"):
        value = record.get(required)
        if value is None or value == "":
            problems.append(f"Required field '{required}' is missing or empty")

    def _check_enum(field_name, valid_set):
        value = record.get(field_name)
        if value not in (None, "") and value not in valid_set:
            problems.append(f"'{field_name}' has an invalid value: {value!r}")

    _check_enum("decision", VALID_DECISIONS)
    _check_enum("rejection_stage", VALID_REJECTION_STAGES)
    _check_enum("outcome", VALID_OUTCOMES)
    _check_enum("source", VALID_SOURCES)
    _check_enum("trade_source", VALID_SOURCES)

    return (len(problems) == 0), problems
