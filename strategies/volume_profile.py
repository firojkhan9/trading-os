# ================================================
# FILE: strategies/volume_profile.py
# PURPOSE: Shared Intraday Relative Volume (RVOL) Engine
#
# WHY THIS FILE EXISTS:
#   strategies/volume_engine.py and strategies/stock_selection_filter.py
#   both independently computed:
#       ratio = today's_volume_so_far / 20-day_average_FULL_DAY_volume
#
#   During market hours, "today's_volume_so_far" is a PARTIAL-DAY figure
#   (the live daily bar), while the denominator is an average of
#   COMPLETED sessions. This mismatch systematically suppresses the
#   ratio throughout the day — worst right after open, resolving only
#   near close. This is why stocks pass this check after market close
#   but are rejected almost universally during live market hours,
#   regardless of the threshold used.
#
# WHAT THIS FILE DOES:
#   Normalises a raw (current_volume, avg_full_day_volume) pair into a
#   time-of-day-correct relative volume ratio, by comparing today's
#   partial volume against the EXPECTED volume at this point in the
#   session — not the full day's average.
#
# DATA SOURCE:
#   A single, market-wide expected-cumulative-volume curve is built
#   from NIFTYBEES.NS 5-minute bars (the NIFTY 50 ETF — used as a
#   volume proxy in this project because index tickers carry no
#   volume in yfinance, the same reasoning already applied in
#   strategies/intraday_direction.py). This is fully data-driven —
#   no hardcoded assumptions about intraday volume distribution.
#
# COST CONTROL:
#   The curve is built AT MOST ONCE PER CALENDAR DAY and cached in
#   memory. Every subsequent call — across every stock, every scan
#   cycle, for the rest of that day — reuses the cached curve with
#   zero additional network calls.
#
# FAIL-SAFE DESIGN:
#   - If the market-wide fetch/build fails, falls back to a simple
#     linear elapsed-session approximation.
#   - If the latest bar is not a live market bar (historical data, or
#     called after market close), the ORIGINAL raw ratio is returned
#     unchanged — today's existing, already-correct behaviour.
#   - Every function in this file is wrapped so it can never raise —
#     any unexpected failure degrades to the raw ratio, never a crash.
#
# DEPENDENCIES:
#   No import from engine/ — market-hours boundaries are declared
#   locally as small constants, keeping this module self-contained
#   and avoiding a strategies/ -> engine/ dependency direction that
#   does not exist anywhere else in this project.
#
#   Does not import strategies/intraday_direction.py's private
#   _fetch_intraday_data() — performs its own independent fetch to
#   keep the daily-bar scoring/scanning subsystem and the 5-minute
#   VCPS intraday subsystem decoupled.
#
# HOW IT CONNECTS:
#   strategies/volume_engine.py           -> calculate_volume_ratio()
#   strategies/stock_selection_filter.py  -> _run_all_checks()
#   Both call get_intraday_rvol() below. Neither computes its own
#   volume ratio independently anymore.
# ================================================

from datetime import datetime, time as dtime

import pandas as pd
import pytz

# ── Local market-hours constants ──────────────────
# Declared locally (not imported from engine/loop_state.py) to keep
# this module self-contained — see header comment above.
_IST          = pytz.timezone("Asia/Kolkata")
_MARKET_OPEN  = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)

# Floor on expected fraction — prevents the ratio from exploding to an
# absurd value in the first minute or two of the session, when the
# expected-volume denominator would otherwise be near zero.
_MIN_EXPECTED_FRACTION = 0.02

# ── In-memory cache: {date_string: curve_or_None} ─
# Built lazily on first use each day. A cached None means "build
# failed today" — this is intentional so a temporarily unreachable
# data source is not retried on every single stock in a scan; it is
# retried only on the next calendar day.
_curve_cache = {}


# ════════════════════════════════════════════════
# MARKET-HOURS HELPERS (self-contained, no engine/ import)
# ════════════════════════════════════════════════

def get_market_elapsed_fraction(now=None):
    """
    Fraction (0.0-1.0) of today's NSE trading session that has
    elapsed, based on the local market-hours constants above.

    Returns 0.0 before market open, 1.0 after market close or on
    any error (the safest default — treats an unknown state as a
    completed session, so callers fall back to the raw ratio).
    """
    try:
        now = now or datetime.now(_IST)
        open_dt  = datetime.combine(now.date(), _MARKET_OPEN)
        close_dt = datetime.combine(now.date(), _MARKET_CLOSE)
        now_dt   = datetime.combine(now.date(), now.time())

        total_seconds = (close_dt - open_dt).total_seconds()
        if total_seconds <= 0:
            return 1.0

        elapsed_seconds = (now_dt - open_dt).total_seconds()
        return max(0.0, min(1.0, elapsed_seconds / total_seconds))
    except Exception:
        return 1.0


def _is_market_open_now(now=None):
    """Lightweight local market-open check — Mon-Fri, within hours."""
    try:
        now = now or datetime.now(_IST)
        if now.weekday() >= 5:
            return False
        return _MARKET_OPEN <= now.time() <= _MARKET_CLOSE
    except Exception:
        return False


def _is_latest_bar_live(latest_bar_timestamp, now=None):
    """
    True only if the given bar timestamp is TODAY (IST) AND the
    market is currently open — meaning that bar's Volume figure is a
    partial, still-accumulating number rather than a completed
    session's total.

    Any uncertainty returns False — the safe default, which causes
    the caller to use the ORIGINAL raw ratio (today's existing
    behaviour), never a worse or riskier outcome.
    """
    if latest_bar_timestamp is None:
        return False
    try:
        now = now or datetime.now(_IST)
        bar_date = pd.Timestamp(latest_bar_timestamp).date()
        return bar_date == now.date() and _is_market_open_now(now)
    except Exception:
        return False


# ════════════════════════════════════════════════
# MARKET-WIDE EXPECTED-VOLUME CURVE
# Data-driven — built from real NIFTYBEES.NS 5-minute bars.
# Built at most once per calendar day, cached in memory.
# ════════════════════════════════════════════════

def _fetch_nifty_intraday_bars():
    """
    Fetch recent NIFTYBEES.NS 5-minute bars — the shared market-wide
    volume reference used to build today's expected-cumulative-volume
    curve. Independent of strategies/intraday_direction.py's own
    fetch, by design (keeps the two subsystems decoupled).

    Returns None on any failure — never raises.
    """
    try:
        import yfinance as yf
        data = yf.download(
            tickers="NIFTYBEES.NS", period="5d", interval="5m",
            progress=False, auto_adjust=True,
        )
        if data.empty:
            return None
        data.columns = [col[0] for col in data.columns]
        data = data.dropna(subset=["Close", "Volume"])
        data = data[data["Volume"] > 0]
        if data.empty:
            return None
        return data
    except Exception:
        return None


def _build_market_volume_curve():
    """
    Build a market-wide expected-cumulative-volume curve from real
    NIFTYBEES.NS 5-minute bars — fully data-driven, no hardcoded
    assumptions about intraday volume distribution.

    For each historical trading day available, computes the
    cumulative fraction of that day's total volume traded by each
    5-minute bar, then averages those fractions across all available
    days at each bar position.

    Returns a sorted list of (elapsed_fraction, expected_fraction)
    tuples, or None if the curve could not be built.
    """
    try:
        data = _fetch_nifty_intraday_bars()
        if data is None or data.empty:
            return None

        data = data.copy()
        data["_date"] = data.index.date

        # bar_index_within_day -> list of cumulative volume fractions
        # observed at that bar position, across all available days
        day_fractions = {}

        for _, group in data.groupby("_date"):
            group = group.sort_index()
            day_total = float(group["Volume"].sum())
            if day_total <= 0:
                continue
            cum_fraction = (group["Volume"].cumsum() / day_total).tolist()
            for i, frac in enumerate(cum_fraction):
                day_fractions.setdefault(i, []).append(frac)

        if not day_fractions:
            return None

        max_bars = max(day_fractions.keys()) + 1
        curve = []
        for i in range(max_bars):
            fracs = day_fractions.get(i)
            if not fracs:
                continue
            elapsed_fraction   = (i + 1) / max_bars
            expected_fraction  = sum(fracs) / len(fracs)
            curve.append((elapsed_fraction, expected_fraction))

        curve.sort(key=lambda x: x[0])
        return curve if curve else None
    except Exception:
        return None


def _get_cached_curve():
    """
    Return today's market-wide volume curve, building it at most once
    per calendar day. A cached None (build failed today) is also
    honoured — it is not retried until the calendar date changes, to
    guarantee AT MOST ONE extra network call per day regardless of
    how many stocks or scan cycles occur.
    """
    try:
        today_str = datetime.now(_IST).strftime('%Y-%m-%d')
    except Exception:
        today_str = "unknown"

    if today_str in _curve_cache:
        return _curve_cache[today_str]

    curve = _build_market_volume_curve()
    _curve_cache[today_str] = curve
    return curve


def _interpolate_curve(elapsed_fraction, curve):
    """
    Piecewise-linear interpolation of the expected cumulative volume
    fraction at a given point in the session, from the cached curve.
    Returns None if no curve is available (caller falls back to a
    linear approximation).
    """
    if not curve:
        return None

    ef = max(0.0, min(1.0, elapsed_fraction))

    if ef <= curve[0][0]:
        return max(_MIN_EXPECTED_FRACTION, curve[0][1])
    if ef >= curve[-1][0]:
        return max(_MIN_EXPECTED_FRACTION, curve[-1][1])

    for i in range(len(curve) - 1):
        x0, y0 = curve[i]
        x1, y1 = curve[i + 1]
        if x0 <= ef <= x1:
            if x1 == x0:
                return max(_MIN_EXPECTED_FRACTION, y0)
            frac = y0 + (y1 - y0) * (ef - x0) / (x1 - x0)
            return max(_MIN_EXPECTED_FRACTION, frac)

    return max(_MIN_EXPECTED_FRACTION, curve[-1][1])


def get_expected_volume(avg_full_day_volume, now=None):
    """
    Expected cumulative volume AT THIS MOMENT, scaled from the
    historical full-day average using the cached market-wide curve.

    Falls back to a simple linear elapsed-session approximation if
    the data-driven curve is unavailable. Returns None if
    avg_full_day_volume is missing/invalid.
    """
    try:
        if avg_full_day_volume is None or pd.isna(avg_full_day_volume) or avg_full_day_volume <= 0:
            return None

        elapsed_fraction = get_market_elapsed_fraction(now)
        curve = _get_cached_curve()
        expected_fraction = _interpolate_curve(elapsed_fraction, curve)

        if expected_fraction is None:
            # Fallback: simple linear elapsed-session approximation —
            # used only when the market-wide curve could not be built.
            expected_fraction = max(_MIN_EXPECTED_FRACTION, elapsed_fraction)

        return float(avg_full_day_volume) * expected_fraction
    except Exception:
        return None


# ════════════════════════════════════════════════
# PUBLIC ENTRY POINT — the single source of truth
# ════════════════════════════════════════════════

def get_intraday_rvol(current_volume, avg_volume, latest_bar_timestamp=None, now=None):
    """
    THE single source of truth for relative volume normalization.

    Parameters:
      current_volume        : latest bar's Volume (today's cumulative
                               volume-so-far if the bar is live, or a
                               completed day's total volume otherwise)
      avg_volume             : historical average FULL-DAY volume
                               (e.g. 20-day rolling mean)
      latest_bar_timestamp   : timestamp/date of the bar current_volume
                               came from (e.g. data.index[-1]) — used
                               to detect whether this is a live bar
      now                     : optional override for "current time"
                               (defaults to real time)

    Returns:
      A float ratio, or None if avg_volume is unusable.

      - If the bar is a COMPLETED session (historical row, or today's
        bar fetched after market close) -> returns the RAW ratio
        (current/avg) — already mathematically valid, unchanged from
        today's behaviour.
      - If the bar is LIVE (today, market currently open) -> returns
        the CORRECTED ratio: current_volume / expected_volume_at_this_
        time, comparable to 1.0x at any point during the session.
      - On any failure, falls back to the raw ratio (or None) — never
        raises, never blocks a caller.
    """
    try:
        if current_volume is None or avg_volume is None:
            return None
        current_volume = float(current_volume)
        avg_volume = float(avg_volume)
        if pd.isna(avg_volume) or avg_volume <= 0:
            return None

        if not _is_latest_bar_live(latest_bar_timestamp, now=now):
            # Completed session — raw ratio is already mathematically valid
            return round(current_volume / avg_volume, 4)

        expected_volume = get_expected_volume(avg_volume, now=now)
        if not expected_volume or expected_volume <= 0:
            # Could not compute expected volume — safe fallback to raw
            return round(current_volume / avg_volume, 4)

        return round(current_volume / expected_volume, 4)

    except Exception:
        # Absolute last-resort fallback — never crash the caller
        try:
            return round(float(current_volume) / float(avg_volume), 4)
        except Exception:
            return None