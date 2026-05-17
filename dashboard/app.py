# ================================================
# FILE: dashboard/app.py
# PURPOSE: Visual trading dashboard in browser
#          One stock selector controls everything
#          With paper trading simulator
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

# ── ONE SINGLE STOCK SELECTOR ────────────────────
st.subheader("🎯 Select Stock")
selected_stock  = st.selectbox(
    "Choose a stock — all charts and indicators will update:",
    options=list(WATCHLIST.keys())
)
selected_symbol = WATCHLIST[selected_stock]

st.divider()

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
st.subheader("📊 Watchlist Summary — All Stocks")

with st.spinner("Fetching market data..."):
    summary_df = fetch_all_stocks()

def highlight_selected(row):
    if row['Stock'] == selected_stock:
        return ['background-color: #1a1a2e; color: white'] * len(row)
    return [''] * len(row)

def color_change(val):
    color = "green" if val > 0 else "red"
    return f"color: {color}"

styled_df = summary_df.style\
    .apply(highlight_selected, axis=1)\
    .map(color_change, subset=["30D Change"])\
    .format({
        "Close (₹)":  "₹{:.2f}",
        "30D Change": "{:.2f}%",
        "Day High":   "₹{:.2f}",
        "Day Low":    "₹{:.2f}",
    })

st.dataframe(styled_df, use_container_width=True)

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

# ── SECTION 3: Metric Cards ───────────────────────
st.subheader(f"🧠 Technical Indicators — {selected_stock}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Latest Close", f"₹{latest_close}", f"₹{round(latest_close - prev_close, 2)}")
col2.metric("MA20",         f"₹{latest_ma20}")
col3.metric("RSI",          f"{latest_rsi}",    f"{round(latest_rsi - prev_rsi, 2)}")
col4.metric("Signal",       latest_signal)

st.divider()

# ── SECTION 4: Indicator Table ────────────────────
st.caption(f"Last 5 trading days for **{selected_stock}**")
last5 = analyzed[['Close','MA20','RSI','Signal']].tail(5).round(2)
st.dataframe(last5, use_container_width=True)

st.divider()

# ── SECTION 5: Price Chart ────────────────────────
st.subheader(f"📈 Price Chart — {selected_stock}")
chart_df = analyzed[['Close', 'MA20']].dropna()
st.line_chart(chart_df, use_container_width=True)

st.divider()

# ── SECTION 6: Paper Trading ──────────────────────
st.subheader(f"💰 Paper Trading — {selected_stock}")

# Show current capital
current_capital = get_current_capital()
total_invested  = STARTING_CAPITAL - current_capital
pnl_pct         = round(((current_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100, 2)

cap1, cap2, cap3 = st.columns(3)
cap1.metric("Starting Capital", f"₹{STARTING_CAPITAL:,}")
cap2.metric("Available Cash",   f"₹{current_capital:,}")
cap3.metric("Total Invested",   f"₹{total_invested:,}")

st.write("")

# ── BUY and SELL buttons ──────────────────────────
col_buy, col_sell = st.columns(2)

with col_buy:
    if st.button(f"🟢 BUY {selected_stock} @ ₹{latest_close}", use_container_width=True):
        result = execute_paper_buy(selected_stock, latest_close)
        if result['status'] == "EXECUTED":
            st.success(f"✅ Bought {result['quantity']} shares of {selected_stock} @ ₹{result['price']}")
            st.info(f"💰 Capital remaining: ₹{result['capital']:,}")
        else:
            st.warning(f"⚠️ {result['reason']}")

with col_sell:
    if st.button(f"🔴 SELL {selected_stock} @ ₹{latest_close}", use_container_width=True):
        result = execute_paper_sell(selected_stock, latest_close)
        if result['status'] == "EXECUTED":
            pnl_color = "✅" if result['pnl'] >= 0 else "❌"
            st.success(f"{pnl_color} Sold {result['quantity']} shares @ ₹{result['price']}")
            st.info(f"📊 P&L: ₹{result['pnl']} ({result['pnl_pct']}%) | Cash: ₹{result['capital']:,}")
        else:
            st.warning(f"⚠️ {result['reason']}")

st.divider()

# ── SECTION 7: Current Portfolio ─────────────────
st.subheader("📂 Current Portfolio")

# Build current prices dict from summary
current_prices = {}
if not summary_df.empty:
    for _, row in summary_df.iterrows():
        current_prices[row['Stock']] = row['Close (₹)']

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

# ── SECTION 8: Trade History ──────────────────────
st.subheader("📜 Trade History")

trades_df = load_trades()
if trades_df.empty:
    st.info("No trades yet — make your first paper trade above!")
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

# ── SECTION 9: Signal Log ─────────────────────────
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