# ================================================
# FILE: dashboard/app.py
# PURPOSE: Visual trading dashboard in browser
#          Clickable table + dropdown selector
#          With risk management + backtesting
# ================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import sys
import os
from datetime import datetime

# ── Works on both laptop and cloud ───────────────
# On laptop: app.py is inside dashboard/ → go up two levels
# On Cloud:  app.py is at repo root → go up one level
# This tries both and uses whichever works

_this_file = os.path.abspath(__file__)
_one_up    = os.path.dirname(_this_file)           # dashboard/ or repo root
_two_up    = os.path.dirname(_one_up)              # trading_os/ or parent

# Add both to path — Python will use whichever has the modules
sys.path.insert(0, _one_up)
sys.path.insert(0, _two_up)
from strategies.indicators import analyze_stock
from logs.signal_logger import log_signal, load_signal_log
from strategies.paper_trader import (
    execute_paper_buy,
    execute_paper_sell,
    get_portfolio_summary,
    load_trades,
    get_current_capital,
    STARTING_CAPITAL
)
from portfolio.performance import (
    get_performance_summary,
    get_completed_trades
)
from risk.risk_manager import (
    run_full_risk_check,
    get_risk_summary,
    STOP_LOSS_PCT,
    TARGET_PROFIT_PCT,
    MAX_OPEN_POSITIONS
)
from strategies.backtest import run_backtest
from strategies.ema_strategy import (          
    calculate_ema_signals,
    get_ema_summary,
    run_ema_backtest
)
from strategies.backtest import run_backtest

# ── Page configuration ───────────────────────────
st.set_page_config(
    page_title="Trading OS",
    page_icon="📈",
    layout="wide"
)

# ── Password Protection ───────────────────────────
def check_password():
    """
    Simple password protection for dashboard.
    Returns True if password is correct.
    """

    # If already authenticated this session — skip
    if st.session_state.get("authenticated"):
        return True

    # ── Login Screen ──────────────────────────────
    st.title("🔐 Trading OS — Login")
    st.caption("Enter your password to access the dashboard")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password_input = st.text_input(
            "Password:",
            type="password",
            placeholder="Enter password..."
        )

        if st.button("🔓 Login", use_container_width=True):
            # Get password from secrets file
            correct_password = st.secrets["auth"]["password"]

            if password_input == correct_password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Wrong password. Try again.")

    return False


# ── Block dashboard if not authenticated ──────────
if not check_password():
    st.stop()

# ── Our watchlist ────────────────────────────────
WATCHLIST = {
    "RELIANCE":   "RELIANCE.NS",
    "TCS":        "TCS.NS",
    "HDFCBANK":   "HDFCBANK.NS",
    "INFY":       "INFY.NS",
    "ICICIBANK":  "ICICIBANK.NS",
    "HINDUNILVR": "HINDUNILVR.NS",
    "SBIN":       "SBIN.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "ITC":        "ITC.NS",
    "KOTAKBANK":  "KOTAKBANK.NS",
}
STOCK_NAMES = list(WATCHLIST.keys())

# ── Fetch functions ───────────────────────────────
@st.cache_data(ttl=300)
def fetch_all_stocks():
    summary = []
    for name, symbol in WATCHLIST.items():
        try:
            data = yf.download(
                tickers=symbol,
                period="30d",
                interval="1d",
                progress=False
            )
            if data.empty:
                continue
            data.columns = [col[0] for col in data.columns]
            latest_close = round(float(data['Close'].iloc[-1]), 2)
            oldest_close = round(float(data['Close'].iloc[0]), 2)
            change_pct   = round(((latest_close - oldest_close) / oldest_close) * 100, 2)
            day_high     = round(float(data['High'].iloc[-1]), 2)
            day_low      = round(float(data['Low'].iloc[-1]), 2)
            summary.append({
                "Stock":      name,
                "Close (₹)":  latest_close,
                "30D Change": change_pct,
                "Day High":   day_high,
                "Day Low":    day_low,
            })
        except Exception as e:
            st.warning(f"Could not fetch {name}: {e}")
    return pd.DataFrame(summary)


@st.cache_data(ttl=300)
def fetch_stock_data(symbol):
    data = yf.download(
        tickers=symbol,
        period="30d",
        interval="1d",
        progress=False
    )
    data.columns = [col[0] for col in data.columns]
    return data


# ── Navigation Tabs ───────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📊 Dashboard",
    "🔬 Backtesting",
    "📋 Logs"
])

# ════════════════════════════════════════════════
# TAB 1: MAIN DASHBOARD
# ════════════════════════════════════════════════
with tab1:

    st.title("🚀 Trading OS — Market Dashboard")
    st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    st.divider()

    # ── Watchlist Table ───────────────────────────
    st.subheader("📊 Watchlist — Click a row OR use dropdown")

    with st.spinner("Fetching market data..."):
        summary_df = fetch_all_stocks()

    st.caption("👆 Click any row to select that stock")
    selection = st.dataframe(
        summary_df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        hide_index=True,
    )

    # Detect clicked row
    clicked_stock = None
    if selection and selection.selection.rows:
        clicked_index = selection.selection.rows[0]
        clicked_stock = summary_df.iloc[clicked_index]['Stock']

    default_index  = STOCK_NAMES.index(clicked_stock) if clicked_stock else 0
    selected_stock = st.selectbox(
        "🎯 Or select from dropdown:",
        options=STOCK_NAMES,
        index=default_index,
        key="main_selector"
    )
    selected_symbol = WATCHLIST[selected_stock]

    st.divider()

    # ── Fetch + Analyze ───────────────────────────
    with st.spinner(f"Analyzing {selected_stock}..."):
        stock_data = fetch_stock_data(selected_symbol)
        analyzed   = analyze_stock(stock_data)

    latest        = analyzed.iloc[-1]
    latest_close  = round(float(latest['Close']), 2)
    latest_ma20   = round(float(latest['MA20']), 2)
    latest_rsi    = round(float(latest['RSI']), 2)
    latest_signal = latest['Signal']
    prev          = analyzed.iloc[-2]
    prev_close    = round(float(prev['Close']), 2)
    prev_rsi      = round(float(prev['RSI']), 2)

    log_signal(
        stock_name = selected_stock,
        close      = latest_close,
        ma20       = latest_ma20,
        rsi        = latest_rsi,
        signal     = latest_signal
    )

    # ── Risk Alerts ───────────────────────────────
    st.subheader("🛡️ Risk Alerts")
    current_prices = {}
    if not summary_df.empty:
        for _, row in summary_df.iterrows():
            current_prices[row['Stock']] = row['Close (₹)']

    alerts = get_risk_summary(current_prices)
    if not alerts:
        st.success("✅ No risk alerts — all positions are safe!")
    else:
        for alert in alerts:
            if alert['color'] == "red":
                st.error(f"🛑 {alert['stock']} — {alert['type']}: {alert['msg']}")
            else:
                st.success(f"🎯 {alert['stock']} — {alert['type']}: {alert['msg']}")

    st.divider()

    # ── Risk Rules ────────────────────────────────
    st.subheader("📋 Active Risk Rules")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Stop Loss",     f"{int(STOP_LOSS_PCT * 100)}%")
    r2.metric("Profit Target", f"{int(TARGET_PROFIT_PCT * 100)}%")
    r3.metric("Max Position",  "10%")
    r4.metric("Max Positions", f"{MAX_OPEN_POSITIONS} stocks")

    st.divider()

    # ── Metric Cards ──────────────────────────────
    st.subheader(f"🧠 Technical Indicators — {selected_stock}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest Close", f"₹{latest_close}", f"₹{round(latest_close - prev_close, 2)}")
    col2.metric("MA20",         f"₹{latest_ma20}")
    col3.metric("RSI",          f"{latest_rsi}",    f"{round(latest_rsi - prev_rsi, 2)}")
    col4.metric("Signal",       latest_signal)

    st.divider()

    # ── Indicator Table ───────────────────────────
    st.caption(f"Last 5 trading days for **{selected_stock}**")
    last5 = analyzed[['Close','MA20','RSI','Signal']].tail(5).round(2)
    st.dataframe(last5, use_container_width=True)

    st.divider()



    st.subheader(f"📈 Price Chart — {selected_stock}")

    # Add EMA indicators to chart data
    ema_data    = calculate_ema_signals(stock_data.copy())
    chart_df    = ema_data[['Close', 'EMA9', 'EMA21']].dropna()
    st.line_chart(chart_df, use_container_width=True)

    st.divider()

    # ── EMA Signal Section ────────────────────────────
    st.subheader(f"⚡ EMA Crossover Signal — {selected_stock}")
    ema_summary = get_ema_summary(ema_data)

    e1, e2, e3 = st.columns(3)
    e4, e5, e6 = st.columns(3)

    e1.metric("Fast EMA (9)",    ema_summary["Fast EMA"])
    e2.metric("Slow EMA (21)",   ema_summary["Slow EMA"])
    e3.metric("EMA Gap",         ema_summary["EMA Gap"])
    e4.metric("Signal",          ema_summary["Signal"])
    e5.metric("Trend",           ema_summary["Trend"])
    e6.metric("Days Since Cross",ema_summary["Days Since Cross"])

    st.divider()

    # ── Paper Trading ─────────────────────────────
    st.subheader(f"💰 Paper Trading — {selected_stock}")
    current_capital = get_current_capital()
    total_invested  = STARTING_CAPITAL - current_capital

    cap1, cap2, cap3 = st.columns(3)
    cap1.metric("Starting Capital", f"₹{STARTING_CAPITAL:,}")
    cap2.metric("Available Cash",   f"₹{current_capital:,}")
    cap3.metric("Total Invested",   f"₹{total_invested:,}")

    st.write("")

    buy_risk  = run_full_risk_check(selected_stock, latest_close, "BUY")
    sell_risk = run_full_risk_check(selected_stock, latest_close, "CHECK")

    for block in buy_risk["blocks"]:
        st.error(block)
    for warning in sell_risk["warnings"]:
        st.warning(warning)

    col_buy, col_sell = st.columns(2)
    with col_buy:
        if st.button(
            f"🟢 BUY {selected_stock} @ ₹{latest_close}",
            use_container_width=True,
            disabled=not buy_risk["approved"]
        ):
            result = execute_paper_buy(selected_stock, latest_close)
            if result['status'] == "EXECUTED":
                st.success(f"✅ Bought {result['quantity']} shares @ ₹{result['price']}")
                st.info(f"💰 Capital remaining: ₹{result['capital']:,}")
            else:
                st.warning(f"⚠️ {result['reason']}")

    with col_sell:
        if st.button(
            f"🔴 SELL {selected_stock} @ ₹{latest_close}",
            use_container_width=True
        ):
            result = execute_paper_sell(selected_stock, latest_close)
            if result['status'] == "EXECUTED":
                pnl_color = "✅" if result['pnl'] >= 0 else "❌"
                st.success(f"{pnl_color} Sold {result['quantity']} shares @ ₹{result['price']}")
                st.info(f"📊 P&L: ₹{result['pnl']} ({result['pnl_pct']}%) | Cash: ₹{result['capital']:,}")
            else:
                st.warning(f"⚠️ {result['reason']}")

    st.divider()

    # ── Current Portfolio ─────────────────────────
    st.subheader("📂 Current Portfolio")
    portfolio_df = get_portfolio_summary(current_prices)

    if portfolio_df.empty:
        st.info("No open positions yet — click BUY above to start!")
    else:
        def color_pnl(val):
            return f"color: {'green' if val >= 0 else 'red'}"
        st.dataframe(
            portfolio_df.style.map(color_pnl, subset=["P&L", "P&L %"]),
            use_container_width=True
        )

    st.divider()

    # ── Performance Report ────────────────────────
    st.subheader("📊 Portfolio Performance Report")
    summary = get_performance_summary()

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Total Trades",    summary["Total Trades"])
    p2.metric("Win Rate",        summary["Win Rate"])
    p3.metric("Total P&L",       summary["Total P&L"])
    p4.metric("Current Capital", summary["Current Capital"])

    p5, p6, p7, p8 = st.columns(4)
    p5.metric("Winning Trades",  summary["Winning Trades"])
    p6.metric("Losing Trades",   summary["Losing Trades"])
    p7.metric("Best Trade",      summary["Best Trade"])
    p8.metric("Worst Trade",     summary["Worst Trade"])

    st.divider()

    completed_df = get_completed_trades()
    st.caption("📋 Completed Trades — Round Trips Only")
    if completed_df.empty:
        st.info("No completed trades yet!")
    else:
        def color_result(val):
            if "WIN"  in str(val): return "color: green"
            if "LOSS" in str(val): return "color: red"
            return ""
        st.dataframe(
            completed_df.style.map(color_result, subset=["Result"]),
            use_container_width=True
        )
        st.download_button(
            label     = "⬇️ Download Performance Report",
            data      = completed_df.to_csv(index=False),
            file_name = "performance_report.csv",
            mime      = "text/csv"
        )


# ════════════════════════════════════════════════
# TAB 2: BACKTESTING
# ════════════════════════════════════════════════
with tab2:

    st.title("🔬 Strategy Backtesting")
    st.caption("Test your strategy on historical data — safely, before risking real money")
    st.divider()

    # ── Backtest Controls ─────────────────────────
    st.subheader("⚙️ Backtest Settings")

    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        bt_stock = st.selectbox(
            "Select Stock:",
            options=STOCK_NAMES,
            key="bt_stock_v2"
        )
    with bc2:
        bt_period = st.selectbox(
            "Select Period:",
            options=["3mo", "6mo", "1y", "2y"],
            index=2,
            format_func=lambda x: {
                "3mo": "3 Months",
                "6mo": "6 Months",
                "1y":  "1 Year",
                "2y":  "2 Years"
            }[x]
        )
    with bc3:
        bt_strategy = st.selectbox(
            "Select Strategy:",
            options=["MA + RSI", "EMA Crossover"],
            key="bt_strategy"
        )

    st.divider()

    if st.button("🚀 Run Backtest", use_container_width=True):
        with st.spinner(f"Running {bt_strategy} backtest for {bt_stock}..."):

            # ── Fetch data ────────────────────────
            raw_data = yf.download(
                tickers=WATCHLIST[bt_stock],
                period=bt_period,
                interval="1d",
                progress=False
            )
            raw_data.columns = [col[0] for col in raw_data.columns]

            if bt_strategy == "MA + RSI":
                result = run_backtest(
                    symbol     = WATCHLIST[bt_stock],
                    stock_name = bt_stock,
                    period     = bt_period
                )
                bt_summary  = result[0]
                bt_equity   = result[1]
                bt_trades   = result[2] if len(result) > 2 else pd.DataFrame()

            else:
                ema_data   = calculate_ema_signals(raw_data.copy())
                ema_data   = ema_data.dropna()
                bt_summary, bt_equity, bt_trades = run_ema_backtest(ema_data)

        if bt_summary is None:
            st.error("Could not fetch data — try again.")
        else:
            st.subheader(f"📊 {bt_strategy} Results — {bt_stock}")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Trades",  bt_summary["Total Trades"])
            m2.metric("Win Rate",      bt_summary["Win Rate"])
            m3.metric("Total P&L",     bt_summary["Total P&L"])
            m4.metric("Total Return",  bt_summary.get("Total Return", "N/A"))

            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Best Trade",    bt_summary.get("Best Trade", "N/A"))
            m6.metric("Worst Trade",   bt_summary.get("Worst Trade", "N/A"))
            m7.metric("Max Drawdown",  bt_summary.get("Max Drawdown", "N/A"))
            m8.metric("Final Capital", bt_summary["Final Capital"])

            st.divider()

            st.subheader("📈 Equity Curve")
            st.line_chart(bt_equity['Equity'], use_container_width=True)

            st.divider()

            if not bt_trades.empty:
                st.subheader("📋 Trade by Trade Breakdown")

                def color_result(val):
                    if "WIN"  in str(val): return "color: green"
                    if "LOSS" in str(val): return "color: red"
                    return ""

                st.dataframe(
                    bt_trades.style.map(
                        color_result,
                        subset=["Result"]
                    ),
                    use_container_width=True
                )

                st.download_button(
                    label     = "⬇️ Download Backtest Results",
                    data      = bt_trades.to_csv(index=False),
                    file_name = f"backtest_{bt_stock}_{bt_strategy}_{bt_period}.csv",
                    mime      = "text/csv"
                )
            else:
                st.info("No trades generated in this period.")
    else:
        st.info("👆 Select stock, period and strategy, then click Run Backtest")


# ════════════════════════════════════════════════
# TAB 3: LOGS
# ════════════════════════════════════════════════
with tab3:

    st.title("📋 System Logs")
    st.divider()

    # ── Trade History ─────────────────────────────
    st.subheader("📜 Trade History")
    trades_df = load_trades()
    if trades_df.empty:
        st.info("No trades yet!")
    else:
        st.dataframe(
            trades_df.sort_values('Timestamp', ascending=False),
            use_container_width=True
        )
        st.download_button(
            label     = "⬇️ Download Trade History",
            data      = trades_df.to_csv(index=False),
            file_name = "paper_trades.csv",
            mime      = "text/csv"
        )

    st.divider()

    # ── Signal Log ────────────────────────────────
    st.subheader("📋 Signal Log")
    log_df = load_signal_log()
    if log_df.empty:
        st.info("No signals logged yet!")
    else:
        log_df = log_df.sort_values('Timestamp', ascending=False)

        def color_signal(val):
            if "BUY"  in str(val): return "color: green"
            if "SELL" in str(val): return "color: red"
            return "color: orange"

        st.dataframe(
            log_df.style.map(color_signal, subset=["Signal"]),
            use_container_width=True
        )
        st.download_button(
            label     = "⬇️ Download Signal Log",
            data      = log_df.to_csv(index=False),
            file_name = "signal_log.csv",
            mime      = "text/csv"
        )

# ── Footer ────────────────────────────────────────
st.divider()
st.caption("📌 Data: Yahoo Finance | Refreshes every 5 min | Not financial advice")