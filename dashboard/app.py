# ================================================
# FILE: dashboard/app.py
# PURPOSE: Visual trading dashboard in browser
#          Clickable table + dropdown selector
#          With risk management alerts
# ================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import sys
from datetime import datetime

sys.path.append("D:\\trading_os")
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

# ── Page configuration ───────────────────────────
st.set_page_config(
    page_title="Trading OS",
    page_icon="📈",
    layout="wide"
)

# ── Title ────────────────────────────────────────
st.title("🚀 Trading OS — Market Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
st.divider()

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

# ── Fetch all stocks ──────────────────────────────
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


# ── Fetch single stock data ───────────────────────
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


# ── SECTION 1: Watchlist Summary Table ───────────
st.subheader("📊 Watchlist Summary — Click a row OR use dropdown")

with st.spinner("Fetching market data..."):
    summary_df = fetch_all_stocks()

# ── Clickable table ───────────────────────────────
st.caption("👆 Click any row to select that stock")

selection = st.dataframe(
    summary_df,
    use_container_width=True,
    on_select="rerun",        # Rerun app when row clicked
    selection_mode="single-row",  # Only one row at a time
    hide_index=True,
)

# ── Detect clicked row ────────────────────────────
clicked_stock = None
if selection and selection.selection.rows:
    clicked_index = selection.selection.rows[0]
    clicked_stock = summary_df.iloc[clicked_index]['Stock']

# ── Dropdown selector ─────────────────────────────
# Default to clicked stock if available
default_index = STOCK_NAMES.index(clicked_stock) if clicked_stock else 0

selected_stock = st.selectbox(
    "🎯 Or select from dropdown — both work together:",
    options=STOCK_NAMES,
    index=default_index
)
selected_symbol = WATCHLIST[selected_stock]

st.divider()

# ── SECTION 2: Fetch + Analyze Selected Stock ─────
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

# ── Auto log signal ───────────────────────────────
log_signal(
    stock_name = selected_stock,
    close      = latest_close,
    ma20       = latest_ma20,
    rsi        = latest_rsi,
    signal     = latest_signal
)

# ── SECTION 3: Risk Alerts ────────────────────────
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

# ── SECTION 4: Risk Rules Summary ────────────────
st.subheader("📋 Active Risk Rules")

r1, r2, r3, r4 = st.columns(4)
r1.metric("Stop Loss",       f"{int(STOP_LOSS_PCT * 100)}%")
r2.metric("Profit Target",   f"{int(TARGET_PROFIT_PCT * 100)}%")
r3.metric("Max Position",    "10%")
r4.metric("Max Positions",   f"{MAX_OPEN_POSITIONS} stocks")

st.divider()

# ── SECTION 5: Metric Cards ───────────────────────
st.subheader(f"🧠 Technical Indicators — {selected_stock}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Latest Close", f"₹{latest_close}", f"₹{round(latest_close - prev_close, 2)}")
col2.metric("MA20",         f"₹{latest_ma20}")
col3.metric("RSI",          f"{latest_rsi}",    f"{round(latest_rsi - prev_rsi, 2)}")
col4.metric("Signal",       latest_signal)

st.divider()

# ── SECTION 6: Indicator Table ────────────────────
st.caption(f"Last 5 trading days for **{selected_stock}**")
last5 = analyzed[['Close','MA20','RSI','Signal']].tail(5).round(2)
st.dataframe(last5, use_container_width=True, hide_index=False)

st.divider()

# ── SECTION 7: Price Chart ────────────────────────
st.subheader(f"📈 Price Chart — {selected_stock}")
chart_df = analyzed[['Close', 'MA20']].dropna()
st.line_chart(chart_df, use_container_width=True)

st.divider()

# ── SECTION 8: Paper Trading ──────────────────────
st.subheader(f"💰 Paper Trading — {selected_stock}")

current_capital = get_current_capital()
total_invested  = STARTING_CAPITAL - current_capital

cap1, cap2, cap3 = st.columns(3)
cap1.metric("Starting Capital", f"₹{STARTING_CAPITAL:,}")
cap2.metric("Available Cash",   f"₹{current_capital:,}")
cap3.metric("Total Invested",   f"₹{total_invested:,}")

st.write("")

# ── Risk check before showing buttons ────────────
buy_risk  = run_full_risk_check(selected_stock, latest_close, "BUY")
sell_risk = run_full_risk_check(selected_stock, latest_close, "CHECK")

# Show risk warnings
for block in buy_risk["blocks"]:
    st.error(block)
for warning in sell_risk["warnings"]:
    st.warning(warning)

col_buy, col_sell = st.columns(2)

with col_buy:
    # Disable buy button if risk check failed
    buy_disabled = not buy_risk["approved"]
    if st.button(
        f"🟢 BUY {selected_stock} @ ₹{latest_close}",
        use_container_width=True,
        disabled=buy_disabled
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

# ── SECTION 9: Current Portfolio ─────────────────
st.subheader("📂 Current Portfolio")

portfolio_df = get_portfolio_summary(current_prices)

if portfolio_df.empty:
    st.info("No open positions yet — click BUY above to start!")
else:
    def color_pnl(val):
        color = "green" if val >= 0 else "red"
        return f"color: {color}"

    styled_portfolio = portfolio_df.style.map(
        color_pnl,
        subset=["P&L", "P&L %"]
    )
    st.dataframe(styled_portfolio, use_container_width=True)

st.divider()

# ── SECTION 10: Performance Report ───────────────
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

st.caption("📋 Completed Trades — Round Trips Only")
completed_df = get_completed_trades()

if completed_df.empty:
    st.info("No completed trades yet!")
else:
    def color_result(val):
        if "WIN"  in str(val): return "color: green"
        if "LOSS" in str(val): return "color: red"
        return ""

    styled_completed = completed_df.style.map(
        color_result, subset=["Result"]
    )
    st.dataframe(styled_completed, use_container_width=True)

    csv = completed_df.to_csv(index=False)
    st.download_button(
        label     = "⬇️ Download Performance Report",
        data      = csv,
        file_name = "performance_report.csv",
        mime      = "text/csv"
    )

st.divider()

# ── SECTION 11: Trade History ─────────────────────
st.subheader("📜 Trade History")

trades_df = load_trades()
if trades_df.empty:
    st.info("No trades yet!")
else:
    st.dataframe(
        trades_df.sort_values('Timestamp', ascending=False),
        use_container_width=True
    )
    csv = trades_df.to_csv(index=False)
    st.download_button(
        label     = "⬇️ Download Trade History",
        data      = csv,
        file_name = "paper_trades.csv",
        mime      = "text/csv"
    )

st.divider()

# ── SECTION 12: Signal Log ────────────────────────
st.subheader("📋 Signal Log — History")

log_df = load_signal_log()
if log_df.empty:
    st.info("No signals logged yet!")
else:
    log_df = log_df.sort_values('Timestamp', ascending=False)

    def color_signal(val):
        if "BUY"  in str(val): return "color: green"
        if "SELL" in str(val): return "color: red"
        return "color: orange"

    styled_log = log_df.style.map(color_signal, subset=["Signal"])
    st.dataframe(styled_log, use_container_width=True)

    csv = log_df.to_csv(index=False)
    st.download_button(
        label     = "⬇️ Download Signal Log",
        data      = csv,
        file_name = "signal_log.csv",
        mime      = "text/csv"
    )

st.divider()

# ── Footer ────────────────────────────────────────
st.caption("📌 Data: Yahoo Finance | Refreshes every 5 min | Not financial advice")