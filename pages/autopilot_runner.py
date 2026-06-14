# ================================================
# FILE: pages/autopilot_runner.py
# PURPOSE: Standalone Auto Pilot heartbeat page.
#
# WHY THIS IS A SEPARATE PAGE:
#   The main app.py has long-running operations (Scanner,
#   Stock Score) that take 30-90 seconds to complete.
#   If autorefresh lives in app.py, it fires a full page
#   rerun every 60 seconds and cancels those operations
#   mid-way — very frustrating.
#
#   Streamlit's multi-page app runs each page in its own
#   independent Python process. A rerun here NEVER affects
#   the main app.py. You can:
#     - Open this page in a second browser tab
#     - Let it refresh itself every 60 seconds
#     - Use the main dashboard in the first tab without
#       any interruption
#
# HOW TO USE:
#   1. Open main dashboard normally in Tab 1 of your browser
#   2. Open a SECOND browser tab → navigate to this page
#      (it appears in the Streamlit sidebar as "autopilot runner")
#   3. Click START LOOP on this page (or on Tab 11 of main app)
#   4. Leave this second tab open and minimised
#   5. Work freely in the main dashboard — no interruptions
#
# WHAT THIS PAGE DOES:
#   - Shows a live status banner (market open/closed, loop status)
#   - Autorefreshes every 60 seconds while loop is RUNNING
#   - On each refresh, checks if the configured interval has elapsed
#   - If yes, runs one full execution cycle
#   - Shares all state with main app via loop_state.py + Supabase
# ================================================

import streamlit as st
import sys
import os
from datetime import datetime

# ── Path fix — same as app.py ─────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── Imports ───────────────────────────────────────
from engine.loop_state import (
    load_loop_state,
    start_loop,
    pause_loop,
    stop_loop,
    load_decision_log,
    clear_decision_log,
    get_market_status,
    is_market_open,
    STATUS_RUNNING,
    STATUS_PAUSED,
    STATUS_STOPPED,
)
from engine.execution_loop import run_one_cycle

st.set_page_config(
    page_title="Auto Pilot Runner — Trading OS",
    page_icon="🤖",
    layout="centered",
)

# ── Password check — same secret as main app ──────
def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.title("🔐 Trading OS — Login")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Password:", type="password")
        if st.button("🔓 Login", use_container_width=True):
            try:
                correct = st.secrets["auth"]["password"]
            except Exception:
                correct = ""
            if pwd == correct:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Wrong password.")
    return False

if not check_password():
    st.stop()

# ════════════════════════════════════════════════
# AUTOREFRESH — fires every 60 seconds while RUNNING
# This is completely isolated from app.py so it
# never interrupts Scanner or Stock Score operations.
# ════════════════════════════════════════════════

_state = load_loop_state()
_running = _state.get("status") == STATUS_RUNNING

try:
    from streamlit_autorefresh import st_autorefresh
    if _running:
        st_autorefresh(interval=60_000, limit=None, key="runner_refresh")
except ImportError:
    pass

# ════════════════════════════════════════════════
# AUTO-EXECUTE: check if interval has elapsed
# ════════════════════════════════════════════════

_cycle_result = None

if _running and is_market_open():
    _last     = _state.get("last_run")
    _interval = int(_state.get("interval_minutes", 15))
    _should_run = False

    if _last is None:
        _should_run = True
    else:
        try:
            _elapsed = (datetime.now() - datetime.strptime(_last, '%Y-%m-%d %H:%M:%S')).total_seconds() / 60
            _should_run = _elapsed >= _interval
        except Exception:
            _should_run = False

    if _should_run:
        with st.spinner(f"🤖 Running cycle... (every {_interval} min)"):
            _cycle_result = run_one_cycle(force=False, scan_only=False)

# ════════════════════════════════════════════════
# PAGE UI
# ════════════════════════════════════════════════

st.title("🤖 Auto Pilot Runner")
st.caption(
    "This is a dedicated runner page. Keep it open in a separate browser tab. "
    "Your main dashboard (app.py) stays completely uninterrupted."
)
st.divider()

# ── Show last cycle result if one just ran ────────
if _cycle_result is not None:
    if _cycle_result.get("ran"):
        st.success(
            f"✅ Cycle ran at {datetime.now().strftime('%H:%M:%S')} | "
            f"Regime: {_cycle_result.get('regime','?')} | "
            f"Buys: {_cycle_result['buys']} | "
            f"Sells: {_cycle_result['sells']} | "
            f"No-trades: {_cycle_result['no_trades']}"
        )
    elif _cycle_result.get("error"):
        st.error(f"❌ Cycle error: {_cycle_result['error'][:200]}")
    elif _cycle_result.get("skipped"):
        st.info(f"ℹ️ Skipped: {_cycle_result['skip_reason']}")

# ── Market status ─────────────────────────────────
mkt = get_market_status()
if mkt["open"]:
    st.success(f"🟢 **Market OPEN** — {mkt['time']}")
else:
    st.warning(f"⚫ **{mkt['status']}** — {mkt['time']}")

st.caption("NSE Hours: 9:15 AM – 3:30 PM IST, Mon–Fri")

# ── Autorefresh status ────────────────────────────
if _running:
    st.info(
        "🔄 **Auto-refresh ON** — this page refreshes every 60 seconds. "
        "Leave it open and minimised. Your main dashboard is unaffected."
    )
else:
    st.warning("⏸️ Loop is not RUNNING. Start it below to enable auto-refresh.")

st.divider()

# ── Load fresh state for display ─────────────────
loop_state  = load_loop_state()
loop_status = loop_state.get("status", STATUS_STOPPED)
last_run    = loop_state.get("last_run",       "Never")
next_run    = loop_state.get("next_run",        "—")
runs_today  = loop_state.get("runs_today",      0)
buys_today  = loop_state.get("buys_today",      0)
sells_today = loop_state.get("sells_today",     0)
pnl_today   = loop_state.get("pnl_today",       0.0)
error_count = loop_state.get("error_count",     0)
last_error  = loop_state.get("last_error",      None)
interval_min= loop_state.get("interval_minutes",15)

# ── Status banner ─────────────────────────────────
if loop_status == STATUS_RUNNING:
    st.success("## 🟢 Loop: RUNNING")
elif loop_status == STATUS_PAUSED:
    st.warning("## ⏸️ Loop: PAUSED")
else:
    st.error("## ⛔ Loop: STOPPED")

# ── Stats ─────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Runs Today",  runs_today)
c2.metric("Buys",        buys_today)
c3.metric("Sells",       sells_today)
c4.metric("P&L Today",  f"₹{pnl_today:+,.0f}")
c5.metric("Errors",      error_count)

st.caption(
    f"Last run: **{last_run}** | "
    f"Next run: **{next_run}** | "
    f"Interval: every **{interval_min} min**"
)

if last_error:
    st.error(f"⚠️ Last error: {last_error}")

st.divider()

# ── Controls ──────────────────────────────────────
st.subheader("⚙️ Controls")
st.caption("You can also control the loop from Tab 11 of the main dashboard — both are in sync.")

ctrl1, ctrl2, ctrl3, ctrl4 = st.columns(4)

with ctrl1:
    new_interval = st.selectbox(
        "Run every:",
        options=[5, 10, 15, 30, 60],
        index=[5, 10, 15, 30, 60].index(interval_min) if interval_min in [5, 10, 15, 30, 60] else 2,
        format_func=lambda x: f"{x} min",
        key="runner_interval"
    )

with ctrl2:
    if st.button("▶️ START", use_container_width=True, disabled=(loop_status == STATUS_RUNNING)):
        start_loop(interval_minutes=new_interval)
        st.rerun()

with ctrl3:
    if st.button("⏸️ PAUSE", use_container_width=True, disabled=(loop_status != STATUS_RUNNING)):
        pause_loop()
        st.rerun()

with ctrl4:
    if st.button("⛔ STOP", use_container_width=True, disabled=(loop_status == STATUS_STOPPED)):
        stop_loop()
        st.rerun()

st.divider()

# ── Manual run ────────────────────────────────────
st.subheader("🚀 Manual")

m1, m2, m3 = st.columns(3)

with m1:
    if st.button("🔍 RUN NOW", use_container_width=True):
        with st.spinner("Running cycle..."):
            result = run_one_cycle(force=True, scan_only=False)
        if result.get("ran"):
            st.success(
                f"✅ Done | Buys: {result['buys']} | "
                f"Sells: {result['sells']} | No-trades: {result['no_trades']}"
            )
        elif result.get("error"):
            st.error(result["error"][:200])
        else:
            st.info(result.get("skip_reason", "Skipped"))
        st.rerun()

with m2:
    if st.button("🔬 SCAN ONLY", use_container_width=True):
        with st.spinner("Scanning..."):
            result = run_one_cycle(force=True, scan_only=True)
        st.info(f"Scan done | {len(result.get('decisions',[]))} decisions logged")
        st.rerun()

with m3:
    if st.button("🗑️ Clear Log", use_container_width=True):
        clear_decision_log()
        st.rerun()

st.divider()

# ── Recent decisions ──────────────────────────────
st.subheader("📋 Recent Decisions")

import pandas as pd
decision_df = load_decision_log(max_rows=50)

if decision_df.empty:
    st.info("No decisions yet. Click RUN NOW or wait for the next auto cycle.")
else:
    def _color_dec(val):
        if val == "BUY":      return "color: green;  font-weight: bold"
        if val == "SELL":     return "color: orange; font-weight: bold"
        if val == "HALTED":   return "color: red;    font-weight: bold"
        if val == "NO-TRADE": return "color: gray"
        return ""

    def _color_exit(val):
        if "STOP"   in str(val): return "color: red"
        if "TARGET" in str(val): return "color: green"
        if "TRAIL"  in str(val): return "color: orange"
        return ""

    st.dataframe(
        decision_df.style
            .map(_color_dec,  subset=["Decision"])
            .map(_color_exit, subset=["Exit_Reason"]),
        use_container_width=True,
        hide_index=True,
    )

    total = len(decision_df)
    buys  = len(decision_df[decision_df["Decision"] == "BUY"])
    sells = len(decision_df[decision_df["Decision"] == "SELL"])
    st.caption(f"Last {total} decisions | BUY: {buys} | SELL: {sells} | NO-TRADE: {total - buys - sells}")



st.divider()

# ── Orchestration Log ─────────────────────────────
st.subheader("🎯 Orchestration Log")
st.caption("Routing decisions — which bucket each stock was sent to and why")

try:
    from strategies.orchestrator import load_orchestration_log, get_orchestration_stats
    orch_stats = get_orchestration_stats()
    oc1, oc2, oc3, oc4 = st.columns(4)
    oc1.metric("Evaluated", orch_stats["total"])
    oc2.metric("Accepted",  orch_stats["accepted"])
    oc3.metric("Rejected",  orch_stats["rejected"])
    oc4.metric("Accept %",  orch_stats["accept_rate"])

    orch_df = load_orchestration_log(max_rows=50)
    if orch_df.empty:
        st.info("No orchestration decisions yet.")
    else:
        def _color_orch(val):
            if val == "ACCEPT": return "color: green; font-weight: bold"
            if val == "REJECT": return "color: red; font-weight: bold"
            if val == "REVIEW": return "color: orange; font-weight: bold"
            return ""
        show = [c for c in ["Timestamp","Stock","Bucket","Decision","Bucket_Score","Confluence_Level","Summary"] if c in orch_df.columns]
        st.dataframe(
            orch_df[show].style.map(_color_orch, subset=["Decision"]),
            use_container_width=True, hide_index=True
        )
except Exception as e:
    st.info(f"Orchestration log unavailable: {e}")

st.divider()
st.caption("🤖 Trading OS — Auto Pilot Runner | Data: Yahoo Finance | Not financial advice")

