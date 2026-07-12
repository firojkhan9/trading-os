# ================================================
# FILE: analytics/storage.py
# PURPOSE: Persistence layer for Analytics Records — Milestone 1 (revised)
#
# WHAT THIS FILE DOES:
#   Provides GENERIC persistence operations only. This module has no
#   concept of "entry write" or "exit update" — it does not know what
#   a record means, only how to store and retrieve rows. The future
#   recorder.py is the only place that will know that an "entry
#   write" is a call to append()/upsert() and an "exit update" is a
#   call to update_fields() with certain values — that meaning lives
#   entirely outside this file, per ADR Section 9 ("Storage knows
#   nothing about trading").
#
#   Exposed operations:
#     - read_all()                              → full table read
#     - find_by(key_field, key_value)            → single-row read
#     - append(record)                            → add a new row,
#                                                     no identity logic
#     - upsert(record, key_field)                 → insert or replace
#                                                     a row matching
#                                                     key_field's value
#                                                     in `record`
#     - update_fields(key_field, key_value, updates)
#                                                   → partial update of
#                                                     an existing row
#
#   The caller supplies key_field every time an identity-based
#   operation is needed. Storage never hardcodes which field is "the"
#   primary key — that decision belongs to recorder.py.
#
# WHAT THIS FILE DOES NOT DO (ADR Section 9 — Storage Module):
#   - No trading logic
#   - No score/vote/regime calculations
#   - No recorder-level orchestration
#   - No dashboard/query logic
#   - No assumption about which field identifies a record
#
# PERSISTENCE PATTERN — REUSED, NOT REINVENTED:
#   - Supabase primary, via the SAME shared client
#     (config.supabase_client.get_client() — singleton, already used
#     by every other module in the project)
#   - CSV fallback, following the same LOGS_DIR / two-layer approach
#     used throughout the project (capital_engine.py, position_manager.py,
#     orchestrator.py, decision_engine.py)
#
# TYPE HANDLING:
#   read_all() lets pandas infer natural types from both Supabase
#   (already native Python/JSON types) and CSV (pandas' own type
#   inference) rather than forcing everything to strings. The one
#   place type coercion happens is the Supabase write boundary
#   (_json_safe()), because JSON transport requires it — that
#   coercion is transport-only and does not change what's held in
#   memory or in the CSV file.
# ================================================

import os
import math
import pandas as pd

from config.supabase_client import get_client

from analytics.constants import (
    ANALYTICS_TABLE_NAME,
    ANALYTICS_CSV_FILE,
    ANALYTICS_COLUMNS,
    LOGS_DIR,
)

os.makedirs(LOGS_DIR, exist_ok=True)


# ════════════════════════════════════════════════
# INTERNAL HELPERS
# ════════════════════════════════════════════════

def _empty_df() -> pd.DataFrame:
    """Correctly shaped empty DataFrame — every declared column
    present, no forced dtype."""
    return pd.DataFrame(columns=ANALYTICS_COLUMNS)


def _ensure_all_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee every ANALYTICS_COLUMNS entry exists on the
    DataFrame, even if the source (Supabase or an older CSV) is
    missing a newer column. Does not touch existing column types."""
    for col in ANALYTICS_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df


def _json_safe(value):
    """
    Convert a single value into something JSON-serializable for the
    Supabase client. This is a transport-boundary concern only — it
    does not change how values are represented anywhere else
    (DataFrame in memory, CSV on disk).
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    # numpy scalar types (e.g. numpy.int64, numpy.bool_) are not
    # JSON-serializable by default — convert via .item() when present
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _record_to_supabase_row(record: dict) -> dict:
    """Apply _json_safe() to every field of a record dict, keeping
    only columns that belong to the declared schema."""
    return {col: _json_safe(record.get(col)) for col in ANALYTICS_COLUMNS}


# ════════════════════════════════════════════════
# READ
# ════════════════════════════════════════════════

def read_all() -> pd.DataFrame:
    """
    Read the full Analytics Records table.

    Priority:
      1. Supabase — persists across Streamlit Cloud restarts
      2. Local CSV — works on laptop / when Supabase is unreachable

    Returns a DataFrame with every ANALYTICS_COLUMNS column present.
    No dtype is forced — values keep whatever type Supabase/pandas
    naturally produced.
    """
    # ── Layer 1: Supabase ─────────────────────────
    client = get_client()
    if client:
        try:
            response = client.table(ANALYTICS_TABLE_NAME).select("*").execute()
            if response.data:
                df = pd.DataFrame(response.data)
                return _ensure_all_columns(df)
            return _empty_df()
        except Exception as e:
            print(f"⚠️ Supabase analytics_records read failed: {e} — using CSV")

    # ── Layer 2: CSV fallback ─────────────────────
    if os.path.exists(ANALYTICS_CSV_FILE):
        try:
            df = pd.read_csv(ANALYTICS_CSV_FILE)
            return _ensure_all_columns(df)
        except Exception as e:
            print(f"⚠️ CSV analytics_records read failed: {e}")
            return _empty_df()

    return _empty_df()


def find_by(key_field: str, key_value) -> dict | None:
    """
    Return a single record as a dict, or None if no row has
    row[key_field] == key_value. Purely a read — no aggregation, no
    business logic. Which field to search on is entirely up to the
    caller; storage does not assume any field is special.
    """
    if key_field not in ANALYTICS_COLUMNS:
        return None

    df = read_all()
    if df.empty:
        return None

    mask = df[key_field] == key_value
    if not mask.any():
        return None

    return df.loc[mask].iloc[0].to_dict()


# ════════════════════════════════════════════════
# WRITE — internal full-table save, both layers
# ════════════════════════════════════════════════

def _save_all(df: pd.DataFrame, upsert_key: str | None = None) -> None:
    """
    Write the full table to Supabase and CSV.

    upsert_key : if provided, the Supabase write uses upsert() with
                 that field as the conflict target. If None, the
                 Supabase write is a plain insert of every row in df
                 (only safe for brand-new rows — callers responsible
                 for not re-inserting existing ones when upsert_key
                 is omitted).
    """
    # ── Layer 1: Supabase ─────────────────────────
    client = get_client()
    if client:
        try:
            rows = [_record_to_supabase_row(row.to_dict()) for _, row in df.iterrows()]
            if rows:
                table = client.table(ANALYTICS_TABLE_NAME)
                if upsert_key:
                    table.upsert(rows, on_conflict=upsert_key).execute()
                else:
                    table.insert(rows).execute()
        except Exception as e:
            print(f"⚠️ Supabase analytics_records write failed: {e} — saved to CSV only")

    # ── Layer 2: CSV (always) ─────────────────────
    try:
        df.to_csv(ANALYTICS_CSV_FILE, index=False)
    except Exception as e:
        print(f"⚠️ CSV analytics_records write failed: {e}")


# ════════════════════════════════════════════════
# GENERIC WRITE OPERATIONS
# ════════════════════════════════════════════════

def append(record: dict) -> dict:
    """
    Add one new row. No identity/dedup logic — this simply adds the
    record as-is. If the caller wants insert-or-replace semantics,
    use upsert() instead.

    IMPLEMENTATION NOTE (bug fix): Supabase and CSV are written with
    different granularity and different read sources here, on
    purpose.

    Supabase's `record_id` column is a primary key with no
    conflict-handling on plain insert(), so only the single new
    record is ever sent there (as a one-row batch) — resending
    previously-persisted rows through insert() is what previously
    caused "duplicate key value violates unique constraint" errors
    from the second append() call onward.

    The CSV layer is read directly from disk rather than via
    read_all(), because read_all() prefers Supabase when a client is
    available — reading Supabase AFTER the insert above would pull
    the just-inserted record back down and append it into the CSV a
    second time. Reading the CSV file directly avoids that.

    Each persistence layer's success/failure is tracked
    independently; a failure in one never blocks the other from
    being attempted. The overall call is only reported as ERROR if
    BOTH layers fail.

    Returns {"status": "OK"} or {"status": "ERROR", "reason": ...}.
    """
    supabase_ok = False
    csv_ok      = False
    last_error  = None

    # ── Layer 1: Supabase — insert ONLY the new record ────────
    try:
        client = get_client()
        if client:
            row = _record_to_supabase_row(record)
            client.table(ANALYTICS_TABLE_NAME).insert([row]).execute()
            supabase_ok = True
    except Exception as e:
        last_error = str(e)
        print(f"⚠️ Supabase analytics_records insert failed: {e} — trying CSV")

    # ── Layer 2: CSV — read local file directly, never Supabase ──
    try:
        if os.path.exists(ANALYTICS_CSV_FILE):
            df = pd.read_csv(ANALYTICS_CSV_FILE)
            df = _ensure_all_columns(df)
        else:
            df = _empty_df()
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        df.to_csv(ANALYTICS_CSV_FILE, index=False)
        csv_ok = True
    except Exception as e:
        last_error = str(e)
        print(f"⚠️ CSV analytics_records write failed: {e}")

    if supabase_ok or csv_ok:
        return {"status": "OK"}
    return {"status": "ERROR", "reason": last_error or "Both persistence layers failed"}


def upsert(record: dict, key_field: str) -> dict:
    """
    Insert a new row, or replace an existing row whose key_field
    matches record[key_field].

    key_field must be present in ANALYTICS_COLUMNS and must have a
    non-empty value in `record` — beyond that, storage has no
    opinion about what key_field represents (record_id, position_id,
    or anything else the recorder chooses).

    Returns {"status": "OK"} or {"status": "ERROR", "reason": ...}.
    """
    if key_field not in ANALYTICS_COLUMNS:
        return {"status": "ERROR", "reason": f"'{key_field}' is not a known column"}

    key_value = record.get(key_field)
    if key_value is None or key_value == "":
        return {"status": "ERROR", "reason": f"record['{key_field}'] must be set to upsert"}

    try:
        df = read_all()

        if not df.empty and key_field in df.columns:
            mask = df[key_field] == key_value
        else:
            mask = pd.Series([], dtype=bool)

        if mask.any():
            for col, val in record.items():
                if col in df.columns:
                    df.loc[mask, col] = val
        else:
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)

        _save_all(df, upsert_key=key_field)
        return {"status": "OK"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


def update_fields(key_field: str, key_value, updates: dict) -> dict:
    """
    Apply a partial update to whichever row(s) match
    row[key_field] == key_value. Storage does not restrict which
    fields may be updated — that restriction (e.g. "only outcome
    fields may change after entry") is a business rule the future
    recorder.py is responsible for enforcing before calling this
    function, per ADR Section 16.

    Returns {"status": "OK"} or {"status": "ERROR", "reason": ...}
    (including when no matching row is found).
    """
    if key_field not in ANALYTICS_COLUMNS:
        return {"status": "ERROR", "reason": f"'{key_field}' is not a known column"}

    try:
        df = read_all()
        if df.empty:
            return {"status": "ERROR", "reason": "No records exist yet"}

        mask = df[key_field] == key_value
        if not mask.any():
            return {"status": "ERROR", "reason": f"No record found where {key_field}={key_value!r}"}

        for col, val in updates.items():
            if col in df.columns:
                df.loc[mask, col] = val

        _save_all(df, upsert_key=key_field)
        return {"status": "OK"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}
