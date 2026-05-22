# ================================================
# FILE: app.py  ← lives at REPO ROOT
# PURPOSE: Visual trading dashboard in browser
# ================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import sys
import os
from datetime import datetime

# ── Path fix ─────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── All imports 
from strategies.performance_scanner import scan_all_stocks
from config.settings_loader import get_settings, DEFAULT_SETTINGS
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
from strategies.bollinger_strategy import (
    analyze_bollinger,
    get_bollinger_summary,
    run_bollinger_backtest
)
from strategies.macd_strategy import (
    analyze_macd,
    get_macd_summary,
    run_macd_backtest
)
from strategies.strategy_comparison import (
    run_all_backtests,
    get_best_strategy,
    get_strategy_scores
)
from strategies.combined_signal import (
    build_combined_summary
)
from strategies.combined_backtest import (
    run_combined_backtest
)
from strategies.market_regime import (
    get_full_regime_analysis,
    get_regime_history
)
from strategies.watchlist_manager import (
    load_watchlist,
    get_watchlist_dict,
    get_watchlist_summary,
    initialize_watchlist
)
from strategies.relative_strength import (
    rank_stocks_by_rs,
    get_top_rs_stocks,
    get_bottom_rs_stocks
)
from strategies.scoring_engine import (
    build_composite_score
)

# ── Page configuration ───────────────────────────
st.set_page_config(
    page_title="Firoj Khan's Trading OS",
    page_icon="📈",
    layout="wide"
)

# ── Initialize watchlist on first run ─────────────
initialize_watchlist()

# ── Password Protection ───────────────────────────
def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.title("🔐 Trading OS — Login")
    st.caption("Enter your password to access the dashboard")
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password_input = st.text_input(
            "Password:", type="password", placeholder="Enter password..."
        )
        if st.button("🔓 Login", use_container_width=True):
            correct_password = st.secrets["auth"]["password"]
            if password_input == correct_password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Wrong password. Try again.")
    return False

if not check_password():
    st.stop()

# ── Load watchlist dynamically ────────────────────
# This replaces the hardcoded WATCHLIST dictionary
WATCHLIST   = get_watchlist_dict()
STOCK_NAMES = list(WATCHLIST.keys())

# ── Fetch functions ───────────────────────────────
@st.cache_data(ttl=300)
def fetch_all_stocks():
    summary = []
    watchlist = get_watchlist_dict()
    for name, symbol in watchlist.items():
        try:
            data = yf.download(
                tickers=symbol, period="30d",
                interval="1d", progress=False
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
        tickers=symbol, period="60d",
        interval="1d", progress=False
    )
    data.columns = [col[0] for col in data.columns]
    return data


@st.cache_data(ttl=300)
def fetch_regime_analysis():
    return get_full_regime_analysis(period="1y")


@st.cache_data(ttl=600)
def fetch_rs_ranking():
    watchlist = get_watchlist_dict()
    return rank_stocks_by_rs(watchlist)


# ── Navigation Tabs ───────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 Dashboard",
    "🌡️ Market Regime",
    "📡 Scanner",
    "💯 Stock Score",
    "📈 RS Ranking",
    "🔬 Backtesting",
    "📊 Strategy Comparison",
    "📋 Logs"
])

# ════════════════════════════════════════════════
# TAB 1: MAIN DASHBOARD
# ════════════════════════════════════════════════
with tab1:

    st.title("🚀 Trading OS — Market Dashboard")
    st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    st.divider()

    # ── Market Regime Mini Banner ─────────────────
    with st.spinner("Checking market regime..."):
        regime_data  = fetch_regime_analysis()
    regime       = regime_data["regime"]
    regime_advice= regime_data["advice"]

    if "BULL" in regime and "WEAK" not in regime:
        st.success(f"🌡️ Market Regime: **{regime}** — {regime_advice['Action']} | Best: {regime_advice['Best Strategies']}")
    elif "BEAR" in regime and "WEAK" not in regime:
        st.error(f"🌡️ Market Regime: **{regime}** — {regime_advice['Action']}")
    elif "WEAK" in regime or "SIDEWAYS" in regime:
        st.warning(f"🌡️ Market Regime: **{regime}** — {regime_advice['Action']} | Best: {regime_advice['Best Strategies']}")
    else:
        st.info(f"🌡️ Market Regime: **{regime}** — {regime_advice['Action']}")
    st.caption("👆 Full analysis in 🌡️ Market Regime tab")

    st.divider()

    # ── Watchlist Table ───────────────────────────
    st.subheader("📊 Watchlist")
    with st.spinner("Fetching market data..."):
        summary_df = fetch_all_stocks()

    st.caption("👆 Click any row to select that stock")
    selection = st.dataframe(
        summary_df, use_container_width=True,
        on_select="rerun", selection_mode="single-row", hide_index=True,
    )

    clicked_stock = None
    if selection and selection.selection.rows:
        clicked_index = selection.selection.rows[0]
        clicked_stock = summary_df.iloc[clicked_index]['Stock']

    default_index  = STOCK_NAMES.index(clicked_stock) if clicked_stock in STOCK_NAMES else 0
    selected_stock = st.selectbox(
        "🎯 Or select from dropdown:",
        options=STOCK_NAMES, index=default_index, key="main_selector"
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
        stock_name=selected_stock, close=latest_close,
        ma20=latest_ma20, rsi=latest_rsi, signal=latest_signal
    )

    # ── All strategy signals ──────────────────────
    ema_data     = calculate_ema_signals(stock_data.copy())
    ema_summary  = get_ema_summary(ema_data)
    bb_data      = analyze_bollinger(stock_data.copy())
    bb_summary   = get_bollinger_summary(bb_data)
    macd_data    = analyze_macd(stock_data.copy())
    macd_summary = get_macd_summary(macd_data)

    combined = build_combined_summary(
        ma_signal=latest_signal, ema_signal=ema_summary["Signal"],
        bb_signal=bb_summary["Signal"], macd_signal=macd_summary["Signal"],
    )

    # ── Combined Signal Banner ────────────────────
    st.subheader(f"🎯 Combined Signal — {selected_stock}")
    final_signal = combined["Final Signal"]
    if "STRONG BUY"  in final_signal: st.success(f"## {final_signal}")
    elif "BUY"       in final_signal: st.success(f"### {final_signal}")
    elif "STRONG SELL" in final_signal: st.error(f"## {final_signal}")
    elif "SELL"      in final_signal: st.error(f"### {final_signal}")
    else:                              st.info(f"### {final_signal}")

    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("Confidence",      combined["Confidence"])
    cs2.metric("Strategies BUY",  combined["Strategies Buy"])
    cs3.metric("Strategies SELL", combined["Strategies Sell"])
    cs4.metric("Strategies HOLD", combined["Strategies Hold"])

    st.caption("📋 Individual Strategy Votes")
    vote_data = []
    for strategy, signal in combined["Signals"].items():
        vote = combined["Votes"][strategy]
        vote_label = "🟢 BUY" if vote == 1 else ("🔴 SELL" if vote == -1 else "⚪ HOLD")
        vote_data.append({"Strategy": strategy, "Signal": signal, "Vote": vote_label})
    st.dataframe(pd.DataFrame(vote_data), use_container_width=True, hide_index=True)

    st.caption("👆 See full composite score in 💯 Stock Score tab")
    st.divider()

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

    # ── Technical Indicators ──────────────────────
    st.subheader(f"🧠 Technical Indicators — {selected_stock}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest Close", f"₹{latest_close}", f"₹{round(latest_close - prev_close, 2)}")
    col2.metric("MA20",         f"₹{latest_ma20}")
    col3.metric("RSI",          f"{latest_rsi}", f"{round(latest_rsi - prev_rsi, 2)}")
    col4.metric("Signal",       latest_signal)

    st.divider()
    st.caption(f"Last 5 trading days — {selected_stock}")
    last5 = analyzed[['Close','MA20','RSI','Signal']].tail(5).round(2)
    st.dataframe(last5, use_container_width=True)
    st.divider()

    # ── Charts ────────────────────────────────────
    st.subheader(f"📈 Price Chart with EMA — {selected_stock}")
    chart_df = ema_data[['Close', 'EMA9', 'EMA21']].dropna()
    st.line_chart(chart_df, use_container_width=True)
    st.divider()

    st.subheader(f"⚡ EMA Crossover — {selected_stock}")
    e1, e2, e3 = st.columns(3)
    e4, e5, e6 = st.columns(3)
    e1.metric("Fast EMA (9)",     ema_summary["Fast EMA"])
    e2.metric("Slow EMA (21)",    ema_summary["Slow EMA"])
    e3.metric("EMA Gap",          ema_summary["EMA Gap"])
    e4.metric("Signal",           ema_summary["Signal"])
    e5.metric("Trend",            ema_summary["Trend"])
    e6.metric("Days Since Cross", ema_summary["Days Since Cross"])
    st.divider()

    st.subheader(f"📉 Bollinger Bands — {selected_stock}")
    bb_chart = bb_data[['Close', 'BB_Upper', 'BB_Middle', 'BB_Lower']].dropna()
    st.line_chart(bb_chart, use_container_width=True)
    b1, b2, b3 = st.columns(3)
    b4, b5, b6 = st.columns(3)
    b1.metric("Upper Band",  bb_summary["Upper Band"])
    b2.metric("Middle Band", bb_summary["Middle Band"])
    b3.metric("Lower Band",  bb_summary["Lower Band"])
    b4.metric("Signal",      bb_summary["Signal"])
    b5.metric("Position",    bb_summary["Position"])
    b6.metric("Squeeze",     bb_summary["Squeeze"])
    st.divider()

    st.subheader(f"📊 MACD — {selected_stock}")
    macd_chart = macd_data[['MACD', 'MACD_Signal']].dropna()
    st.line_chart(macd_chart, use_container_width=True)
    st.caption("Histogram — above zero = bullish, below zero = bearish")
    hist_chart = macd_data[['MACD_Hist']].dropna()
    st.bar_chart(hist_chart, use_container_width=True)
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc5, mc6, mc7      = st.columns(3)
    mc1.metric("MACD Line",        macd_summary["MACD Line"])
    mc2.metric("Signal Line",      macd_summary["Signal Line"])
    mc3.metric("Histogram",        macd_summary["Histogram"])
    mc4.metric("Signal",           macd_summary["Signal"])
    mc5.metric("Momentum",         macd_summary["Momentum"])
    mc6.metric("Histogram Trend",  macd_summary["Histogram Trend"])
    mc7.metric("Days Since Cross", macd_summary["Days Since Cross"])
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
    if "BEAR" in regime and "WEAK" not in regime:
        st.error("🐻 BEAR MARKET — New buys not recommended. Protect capital.")

    col_buy, col_sell = st.columns(2)
    with col_buy:
        if st.button(
            f"🟢 BUY {selected_stock} @ ₹{latest_close}",
            use_container_width=True, disabled=not buy_risk["approved"]
        ):
            result = execute_paper_buy(selected_stock, latest_close)
            if result['status'] == "EXECUTED":
                st.success(f"✅ Bought {result['quantity']} shares @ ₹{result['price']}")
                st.info(f"💰 Remaining: ₹{result['capital']:,}")
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
                st.success(f"{pnl_color} Sold {result['quantity']} @ ₹{result['price']}")
                st.info(f"P&L: ₹{result['pnl']} ({result['pnl_pct']}%) | Cash: ₹{result['capital']:,}")
            else:
                st.warning(f"⚠️ {result['reason']}")

    st.divider()

    # ── Portfolio ─────────────────────────────────
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

    # ── Performance ───────────────────────────────
    st.subheader("📊 Performance Report")
    perf_summary = get_performance_summary()
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Total Trades",    perf_summary["Total Trades"])
    p2.metric("Win Rate",        perf_summary["Win Rate"])
    p3.metric("Total P&L",       perf_summary["Total P&L"])
    p4.metric("Current Capital", perf_summary["Current Capital"])
    p5, p6, p7, p8 = st.columns(4)
    p5.metric("Winning Trades",  perf_summary["Winning Trades"])
    p6.metric("Losing Trades",   perf_summary["Losing Trades"])
    p7.metric("Best Trade",      perf_summary["Best Trade"])
    p8.metric("Worst Trade",     perf_summary["Worst Trade"])
    st.divider()

    completed_df = get_completed_trades()
    st.caption("📋 Completed Trades")
    if completed_df.empty:
        st.info("No completed trades yet!")
    else:
        def color_result_perf(val):
            if "WIN"  in str(val): return "color: green"
            if "LOSS" in str(val): return "color: red"
            return ""
        st.dataframe(
            completed_df.style.map(color_result_perf, subset=["Result"]),
            use_container_width=True
        )
        st.download_button(
            label="⬇️ Download Performance Report",
            data=completed_df.to_csv(index=False),
            file_name="performance_report.csv", mime="text/csv"
        )


# ════════════════════════════════════════════════
# TAB 2: MARKET REGIME
# ════════════════════════════════════════════════
with tab2:

    st.title("🌡️ Market Regime Detection")
    st.caption("Understanding the overall market environment before placing trades")
    st.divider()

    with st.spinner("Analyzing NIFTY 50..."):
        regime_analysis = fetch_regime_analysis()

    regime     = regime_analysis["regime"]
    reason     = regime_analysis["reason"]
    advice     = regime_analysis["advice"]
    indicators = regime_analysis["indicators"]
    nifty_data = regime_analysis["data"]

    if "BULL" in regime and "WEAK" not in regime:
        st.success(f"# {regime}")
    elif "BEAR" in regime and "WEAK" not in regime:
        st.error(f"# {regime}")
    elif "WEAK" in regime or "SIDEWAYS" in regime:
        st.warning(f"# {regime}")
    else:
        st.info(f"# {regime}")

    st.caption(f"Reason: {reason}")
    st.divider()

    st.subheader("🎯 What Should You Do Now?")
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**Recommended Action**")
        st.info(advice["Action"])
        st.markdown("**Best Strategies**")
        st.success(advice["Best Strategies"])
        st.markdown("**Strategies to Avoid**")
        st.error(advice["Avoid"])
    with a2:
        st.markdown("**Position Size Guidance**")
        st.info(advice["Position Size"])
        st.markdown("**Cash Reserve Target**")
        st.warning(advice["Cash Reserve"])
        st.markdown("**Explanation**")
        st.write(advice["Explanation"])

    st.divider()

    st.subheader("📊 NIFTY 50 Indicators")
    if indicators:
        i1, i2, i3 = st.columns(3)
        i4, i5, i6 = st.columns(3)
        i1.metric("NIFTY Price", f"₹{indicators.get('NIFTY Price', 'N/A')}")
        i2.metric("MA50",        f"₹{indicators.get('MA50', 'N/A')}")
        i3.metric("MA200",       f"₹{indicators.get('MA200', 'N/A')}")
        i4.metric("ADX",         indicators.get('ADX', 'N/A'))
        i5.metric("DI+",         indicators.get('DI+', 'N/A'))
        i6.metric("DI-",         indicators.get('DI-', 'N/A'))
        st.caption("ADX < 20 = Sideways | ADX > 25 = Strong trend | DI+ > DI- = Bullish")

    st.divider()

    if nifty_data is not None:
        st.subheader("📈 NIFTY 50 — Price with MA50 and MA200")
        chart_cols  = [c for c in ['Close', 'MA50', 'MA200'] if c in nifty_data.columns]
        nifty_chart = nifty_data[chart_cols].dropna()
        st.line_chart(nifty_chart, use_container_width=True)
        st.divider()

        st.subheader("📋 Regime History — Last 60 Days")
        history = get_regime_history(nifty_data, window=60)
        if history:
            hist_df = pd.DataFrame(history)
            hist_df['Date'] = pd.to_datetime(hist_df['Date']).dt.strftime('%Y-%m-%d')
            def color_regime(val):
                if "BULL"     in str(val) and "WEAK" not in str(val): return "color: green; font-weight: bold"
                if "BEAR"     in str(val) and "WEAK" not in str(val): return "color: red; font-weight: bold"
                if "WEAK"     in str(val): return "color: orange"
                if "SIDEWAYS" in str(val): return "color: gray"
                return ""
            st.dataframe(
                hist_df.style.map(color_regime, subset=["Regime"]),
                use_container_width=True, hide_index=True
            )

    st.divider()
    st.subheader("📚 Strategy Guide by Regime")
    guide_data = [
        {"Regime": "BULL 🐂",       "Use": "EMA, MACD",      "Avoid": "Nothing",      "Cash": "20%"},
        {"Regime": "WEAK BULL 📈",  "Use": "EMA, MA+RSI",    "Avoid": "Large sizes",  "Cash": "40%"},
        {"Regime": "SIDEWAYS ↔️",   "Use": "Bollinger",      "Avoid": "EMA (whipsaws)","Cash": "50%"},
        {"Regime": "WEAK BEAR 📉",  "Use": "Nothing new",    "Avoid": "All buys",     "Cash": "70%"},
        {"Regime": "BEAR 🐻",       "Use": "Cash only",      "Avoid": "Everything",   "Cash": "90%+"},
    ]
    st.dataframe(pd.DataFrame(guide_data), use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════
# SCANNER TAB — paste this as a new tab block
# ════════════════════════════════════════════════
with tab3:   

    st.title("📡 Watchlist Scanner")
    st.caption("Scan all stocks at once — find the best and worst performers")
    st.divider()

    # ── Period selector ───────────────────────────
    st.subheader("⚙️ Scan Settings")

    scan_col1, scan_col2 = st.columns(2)

    with scan_col1:
        period_type = st.selectbox(
            "Select Period Type:",
            options=["Days", "Months"],
            key="scan_period_type"
        )

    with scan_col2:
        if period_type == "Days":
            period_value = st.selectbox(
                "Number of Days:",
                options=[5, 10, 15, 20, 30, 45, 60, 90],
                index=4,   # Default 30 days
                key="scan_days"
            )
            period_days  = period_value
            period_label = f"{period_value} Days"
        else:
            period_value = st.selectbox(
                "Number of Months:",
                options=[1, 2, 3, 6, 9, 12, 18, 24, 36],
                index=2,   # Default 3 months
                key="scan_months"
            )
            period_days  = period_value * 21   # ~21 trading days per month
            period_label = f"{period_value} Month{'s' if period_value > 1 else ''}"

    st.divider()

    if st.button("🔍 Scan All Stocks", use_container_width=True, key="run_scan"):

        with st.spinner(f"Scanning all {len(STOCK_NAMES)} stocks over {period_label}... this takes ~60 seconds"):

            # Get current regime for scoring
            regime_info  = fetch_regime_analysis()
            scan_regime  = regime_info["regime"]

            # Run the scan
            full_df, best_return_df, worst_return_df, best_score_df = scan_all_stocks(
                watchlist_dict = WATCHLIST,
                period_days    = period_days,
                regime         = scan_regime,
            )

        if full_df.empty:
            st.error("Could not fetch data — try again.")
        else:

            # ── Regime context ────────────────────
            if "BULL" in scan_regime and "WEAK" not in scan_regime:
                st.success(f"🌡️ Market Regime during scan: **{scan_regime}**")
            elif "BEAR" in scan_regime and "WEAK" not in scan_regime:
                st.error(f"🌡️ Market Regime during scan: **{scan_regime}**")
            else:
                st.warning(f"🌡️ Market Regime during scan: **{scan_regime}**")

            st.divider()

            # ── Best performers ───────────────────
            st.subheader(f"🚀 Best Performers — Last {period_label}")
            st.caption("Stocks with highest price return in this period")

            if not best_return_df.empty:
                def color_return_best(val):
                    v = str(val)
                    if v.startswith('-'):  return "color: red"
                    if v != "N/A" and v != "0%": return "color: green"
                    return ""
                col_name = f"{period_days}D Return"
                if col_name in best_return_df.columns:
                    st.dataframe(
                        best_return_df.style.map(color_return_best, subset=[col_name]),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.dataframe(best_return_df, use_container_width=True, hide_index=True)

            st.divider()

            # ── Worst performers ──────────────────
            st.subheader(f"⚠️ Worst Performers — Last {period_label}")
            st.caption("Stocks with lowest price return — avoid or monitor for recovery")

            if not worst_return_df.empty:
                def color_return_worst(val):
                    v = str(val)
                    if v.startswith('-'): return "color: red; font-weight: bold"
                    if v != "N/A":       return "color: green"
                    return ""
                col_name = f"{period_days}D Return"
                if col_name in worst_return_df.columns:
                    st.dataframe(
                        worst_return_df.style.map(color_return_worst, subset=[col_name]),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.dataframe(worst_return_df, use_container_width=True, hide_index=True)

            st.divider()

            # ── Best scores ───────────────────────
            st.subheader("💯 Best Intelligence Scores Right Now")
            st.caption("Stocks with highest composite score — strongest buy opportunities")

            if not best_score_df.empty:
                def color_action(val):
                    if "STRONG BUY"  in str(val): return "color: green; font-weight: bold"
                    if "BUY"         in str(val): return "color: lightgreen"
                    if "AVOID"       in str(val): return "color: red"
                    if "HOLD"        in str(val): return "color: orange"
                    return ""
                st.dataframe(
                    best_score_df.style.map(color_action, subset=["Action"]),
                    use_container_width=True, hide_index=True
                )

            st.divider()

            # ── Full scan table ───────────────────
            st.subheader("📋 Full Scan — All Stocks")
            st.caption("Complete scan results sorted by composite score")

            def color_signal_scan(val):
                if "STRONG BUY"  in str(val): return "color: green; font-weight: bold"
                if "BUY"         in str(val): return "color: lightgreen"
                if "STRONG SELL" in str(val): return "color: red; font-weight: bold"
                if "SELL"        in str(val): return "color: orange"
                return ""

            def color_rs_scan(val):
                if "STRONG" in str(val): return "color: green; font-weight: bold"
                if "ABOVE"  in str(val): return "color: lightgreen"
                if "BELOW"  in str(val): return "color: orange"
                if "WEAK"   in str(val): return "color: red"
                return ""

            style_cols = {}
            if "Combined Signal" in full_df.columns:
                style_cols["Combined Signal"] = color_signal_scan
            if "RS Rating" in full_df.columns:
                style_cols["RS Rating"] = color_rs_scan

            styled = full_df.style
            for col, func in style_cols.items():
                styled = styled.map(func, subset=[col])

            st.dataframe(styled, use_container_width=True, hide_index=True)

            st.divider()

            # ── Download ──────────────────────────
            st.download_button(
                label     = f"⬇️ Download Scan Results ({period_label})",
                data      = full_df.to_csv(index=False),
                file_name = f"scan_{period_label.replace(' ', '_')}.csv",
                mime      = "text/csv"
            )

    else:
        st.info(f"👆 Select a period and click Scan All Stocks")
        st.caption("The scanner will fetch data for all stocks, calculate signals, scores and relative performance — all in one view")

        # ── Preview what scanner shows ────────────
        st.divider()
        st.subheader("📖 What the Scanner Shows")
        preview_data = [
            {"Column": f"N Days Return",  "What it means": "How much the stock moved in your chosen period"},
            {"Column": "vs NIFTY",        "What it means": "Return minus NIFTY return — positive = beating market"},
            {"Column": "RS Rating",       "What it means": "STRONG / ABOVE / IN LINE / BELOW / WEAK vs NIFTY"},
            {"Column": "Combined Signal", "What it means": "What all 4 strategies together are saying"},
            {"Column": "Buy Votes",       "What it means": "How many of 4 strategies say BUY right now"},
            {"Column": "Score",           "What it means": "Composite intelligence score 0-100"},
            {"Column": "Action",          "What it means": "Recommended action based on score"},
        ]
        st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════
# TAB 4: STOCK SCORE (Composite Intelligence Score)
# ════════════════════════════════════════════════
with tab4:

    st.title("💯 Stock Intelligence Score")
    st.caption("Composite score combining all indicators into one clear number")
    st.divider()

    sc1, sc2 = st.columns(2)
    with sc1:
        score_stock = st.selectbox(
            "Select Stock to Score:",
            options=STOCK_NAMES, key="score_stock"
        )

    st.divider()

    if st.button("🔍 Calculate Score", use_container_width=True, key="calc_score"):
        with st.spinner(f"Scoring {score_stock}..."):

            score_symbol  = WATCHLIST[score_stock]
            score_data    = fetch_stock_data(score_symbol)
            score_analyzed= analyze_stock(score_data)
            score_latest  = score_analyzed.iloc[-1]

            # Extract all needed values
            s_close   = round(float(score_latest['Close']), 2)
            s_ma20    = round(float(score_latest['MA20']), 2)
            s_rsi     = round(float(score_latest['RSI']), 2)
            s_signal  = score_latest['Signal']

            s_ema_data    = calculate_ema_signals(score_data.copy())
            s_ema_latest  = s_ema_data.iloc[-1]
            s_ema9        = round(float(s_ema_latest['EMA9']), 2)
            s_ema21       = round(float(s_ema_latest['EMA21']), 2)

            s_bb_data     = analyze_bollinger(score_data.copy())
            s_bb_latest   = s_bb_data.iloc[-1]
            s_bb_pct      = float(s_bb_latest['BB_Pct']) if not pd.isna(s_bb_latest['BB_Pct']) else None
            s_bb_signal   = s_bb_latest['BB_Signal']

            s_macd_data   = analyze_macd(score_data.copy())
            s_macd_latest = s_macd_data.iloc[-1]
            s_macd        = float(s_macd_latest['MACD'])        if not pd.isna(s_macd_latest['MACD'])        else None
            s_macd_sig    = float(s_macd_latest['MACD_Signal']) if not pd.isna(s_macd_latest['MACD_Signal']) else None
            s_macd_hist   = float(s_macd_latest['MACD_Hist'])   if not pd.isna(s_macd_latest['MACD_Hist'])   else None

            s_combined = build_combined_summary(
                ma_signal=s_signal, ema_signal=s_ema_data.iloc[-1]['EMA_Signal'],
                bb_signal=s_bb_signal, macd_signal=s_macd_data.iloc[-1]['MACD_Crossover'],
            )

            s_votes = {
                "buy":  s_combined["Strategies Buy"],
                "sell": s_combined["Strategies Sell"],
                "hold": s_combined["Strategies Hold"],
            }

            s_regime_data = fetch_regime_analysis()
            s_regime      = s_regime_data["regime"]

            # Build composite score
            result = build_composite_score(
                stock_name           = score_stock,
                latest_close         = s_close,
                ma20                 = s_ma20,
                rsi                  = s_rsi,
                ema9                 = s_ema9,
                ema21                = s_ema21,
                macd                 = s_macd,
                macd_signal          = s_macd_sig,
                macd_hist            = s_macd_hist,
                bb_pct               = s_bb_pct,
                bb_signal            = s_bb_signal,
                combined_votes       = s_votes,
                combined_weighted_score = s_combined["Score"],
                regime               = s_regime,
                rs_score             = None
            )

        # ── Display Score ─────────────────────────
        composite = result["Composite Score"]

        # Score color
        if composite >= 70:
            st.success(f"# 💯 Score: {composite}/100")
        elif composite >= 55:
            st.success(f"## 💯 Score: {composite}/100")
        elif composite >= 40:
            st.info(f"## 💯 Score: {composite}/100")
        else:
            st.error(f"## 💯 Score: {composite}/100")

        sc_a, sc_b, sc_c, sc_d = st.columns(4)
        sc_a.metric("Action",        result["Action"])
        sc_b.metric("Confidence",    result["Confidence"])
        sc_c.metric("Position Size", result["Position Size"])
        sc_d.metric("Regime",        result["Regime"])

        st.divider()

        # ── Score Breakdown ───────────────────────
        st.subheader("📊 Score Breakdown")
        st.caption("How each dimension contributed to the final score")

        breakdown_rows = []
        for dim, val in result["Individual Scores"].items():
            breakdown_rows.append({
                "Dimension": dim,
                "Score":     f"{val}/100",
                "Weight":    {
                    "Trend": "25%", "Momentum": "25%",
                    "Volatility": "15%", "Signal": "20%",
                    "Regime": "10%", "Rel. Strength": "5%"
                }.get(dim, "N/A"),
                "Bar": "█" * (val // 10) + "░" * (10 - val // 10),
            })

        st.dataframe(
            pd.DataFrame(breakdown_rows),
            use_container_width=True, hide_index=True
        )

        st.divider()

        # ── Explanation ───────────────────────────
        st.subheader("📝 Explanation")
        st.markdown(result["Explanation"])

    else:
        st.info("👆 Select a stock and click Calculate Score")


# ════════════════════════════════════════════════
# TAB 5: RELATIVE STRENGTH RANKING
# ════════════════════════════════════════════════
with tab5:

    st.title("📈 Relative Strength Ranking")
    st.caption("Which stocks are outperforming NIFTY 50? Leaders vs Laggards.")
    st.divider()

    if st.button("🏆 Rank All Stocks by Relative Strength", use_container_width=True):
        with st.spinner("Fetching 6 months of data for all stocks... this takes ~60 seconds"):
            rs_df = fetch_rs_ranking()

        if rs_df.empty:
            st.error("Could not fetch data — try again.")
        else:
            # ── Top performers ────────────────────
            st.subheader("🥇 Market Leaders — Outperforming NIFTY")
            top_df = get_top_rs_stocks(rs_df, n=3)
            if not top_df.empty:
                st.dataframe(top_df, use_container_width=True, hide_index=True)

            st.divider()

            # ── Full ranking ──────────────────────
            st.subheader("📋 Full Ranking Table")
            st.caption("Sorted by composite RS score — higher = stronger vs NIFTY")

            def color_rs(val):
                if "STRONG"  in str(val): return "color: green; font-weight: bold"
                if "ABOVE"   in str(val): return "color: lightgreen"
                if "BELOW"   in str(val): return "color: orange"
                if "WEAK"    in str(val): return "color: red"
                if "BENCHMARK" in str(val): return "color: gray"
                return ""

            st.dataframe(
                rs_df.style.map(color_rs, subset=["RS Rating"]),
                use_container_width=True, hide_index=True
            )

            st.divider()

            # ── Bottom performers ─────────────────
            st.subheader("⚠️ Market Laggards — Underperforming NIFTY")
            st.caption("Avoid trading these stocks — they are weak relative to market")
            bottom_df = get_bottom_rs_stocks(rs_df, n=3)
            if not bottom_df.empty:
                st.dataframe(bottom_df, use_container_width=True, hide_index=True)

            st.divider()
            st.download_button(
                label="⬇️ Download RS Ranking",
                data=rs_df.to_csv(index=False),
                file_name="rs_ranking.csv", mime="text/csv"
            )
    else:
        st.info("👆 Click the button to rank all stocks — takes about 60 seconds")
        st.caption("This fetches 6 months of data for all stocks + NIFTY to calculate relative performance")


# ════════════════════════════════════════════════
# TAB 6: BACKTESTING
# ════════════════════════════════════════════════
with tab6:

    st.title("🔬 Strategy Backtesting")
    st.caption("Test strategies on historical data — safely, before risking real money")
    st.divider()
 
    # ── Strategy selector ─────────────────────────
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
            key="bt_period_v2",
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
            options=[
                "Combined Signal",      # ← NEW — shown first as recommended
                "MA + RSI",
                "EMA Crossover",
                "Bollinger Bands",
                "MACD",
            ],
            key="bt_strategy_v2"
        )
 
    # ── Strategy description ──────────────────────
    strategy_descriptions = {
        "Combined Signal":  "🎯 All 4 strategies vote together — most realistic test. Buys on consensus, sells on reversal.",
        "MA + RSI":         "📈 Classic trend + momentum combination. MA20 for trend, RSI for entry timing.",
        "EMA Crossover":    "⚡ Fast EMA(9) crosses Slow EMA(21). Good for trending markets.",
        "Bollinger Bands":  "📉 Mean reversion at band extremes with RSI confirmation. Good for sideways markets.",
        "MACD":             "📊 Momentum crossover strategy. MACD line crosses signal line.",
    }
    st.caption(f"ℹ️ {strategy_descriptions.get(bt_strategy, '')}")
 
    st.divider()
 
    if st.button("🚀 Run Backtest", use_container_width=True):
        with st.spinner(f"Running {bt_strategy} backtest for {bt_stock}..."):
 
            raw_data = yf.download(
                tickers=WATCHLIST[bt_stock],
                period=bt_period,
                interval="1d",
                progress=False
            )
            raw_data.columns = [col[0] for col in raw_data.columns]
 
            # ── Run selected strategy ─────────────
            if bt_strategy == "Combined Signal":
                bt_summary, bt_equity, bt_trades = run_combined_backtest(raw_data.copy())
 
            elif bt_strategy == "MA + RSI":
                result     = run_backtest(
                    symbol     = WATCHLIST[bt_stock],
                    stock_name = bt_stock,
                    period     = bt_period
                )
                bt_summary = result[0]
                bt_equity  = result[1]
                bt_trades  = result[2] if len(result) > 2 else pd.DataFrame()
 
            elif bt_strategy == "EMA Crossover":
                ema_data             = calculate_ema_signals(raw_data.copy())
                ema_data             = ema_data.dropna()
                bt_summary, bt_equity, bt_trades = run_ema_backtest(ema_data)
 
            elif bt_strategy == "Bollinger Bands":
                bb_data              = analyze_bollinger(raw_data.copy())
                bb_data              = bb_data.dropna()
                bt_summary, bt_equity, bt_trades = run_bollinger_backtest(bb_data)
 
            elif bt_strategy == "MACD":
                macd_bt_data         = analyze_macd(raw_data.copy())
                macd_bt_data         = macd_bt_data.dropna()
                bt_summary, bt_equity, bt_trades = run_macd_backtest(macd_bt_data)
 
        # ── Results ───────────────────────────────
        if bt_summary is None:
            st.error("Could not fetch data — try again.")
        else:
            st.subheader(f"📊 {bt_strategy} Results — {bt_stock}")
 
            # Show note if present (e.g. no trades generated)
            if "Note" in bt_summary:
                st.info(f"ℹ️ {bt_summary['Note']}")
 
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
 
            # ── Extra metrics for Combined Signal ─
            if bt_strategy == "Combined Signal":
                st.divider()
                st.caption("📋 Combined Signal Entry Breakdown")
                ce1, ce2, ce3 = st.columns(3)
                ce1.metric(
                    "Strong Buy Entries",
                    bt_summary.get("Strong Buy Entries", 0),
                    help="3-4 strategies agreed — full 10% position"
                )
                ce2.metric(
                    "Weak Buy Entries",
                    bt_summary.get("Weak Buy Entries", 0),
                    help="Exactly 2 strategies agreed — half 5% position"
                )
                ce3.metric(
                    "Winning Trades",
                    bt_summary.get("Winning Trades", 0),
                )
 
            st.divider()
 
            # ── Equity Curve ──────────────────────
            st.subheader("📈 Equity Curve")
            if 'Equity' in bt_equity.columns:
                st.line_chart(bt_equity['Equity'], use_container_width=True)
 
            st.divider()
 
            # ── Trade Breakdown ───────────────────
            if not bt_trades.empty:
                st.subheader("📋 Trade by Trade Breakdown")
 
                def color_result_bt(val):
                    if "WIN"  in str(val): return "color: green"
                    if "LOSS" in str(val): return "color: red"
                    return ""
 
                # Show Entry Type column for Combined Signal
                if bt_strategy == "Combined Signal" and "Entry Type" in bt_trades.columns:
                    st.caption(
                        "Entry Type: STRONG BUY = 3-4 strategies agreed (10% position) | "
                        "BUY = 2 strategies agreed (5% position)"
                    )
 
                st.dataframe(
                    bt_trades.style.map(color_result_bt, subset=["Result"]),
                    use_container_width=True
                )
                st.download_button(
                    label     = "⬇️ Download Backtest Results",
                    data      = bt_trades.to_csv(index=False),
                    file_name = f"backtest_{bt_stock}_{bt_strategy}_{bt_period}.csv",
                    mime      = "text/csv"
                )
            else:
                st.info("No trades generated in this period — signals never reached the BUY threshold.")
    else:
        st.info("👆 Select stock, period and strategy, then click Run Backtest")
        st.caption("💡 Try 'Combined Signal' first — it's the most realistic test of your full system")


# ════════════════════════════════════════════════
# TAB 7: STRATEGY COMPARISON
# ════════════════════════════════════════════════
with tab7:

    st.title("📊 Strategy Comparison")
    st.caption("Run all 4 strategies on the same stock and period — find the best one")
    st.divider()

    cc1, cc2 = st.columns(2)
    with cc1:
        cmp_stock = st.selectbox("Select Stock:", options=STOCK_NAMES, key="cmp_stock")
    with cc2:
        cmp_period = st.selectbox(
            "Select Period:", options=["3mo", "6mo", "1y", "2y"],
            index=2, key="cmp_period",
            format_func=lambda x: {"3mo":"3 Months","6mo":"6 Months","1y":"1 Year","2y":"2 Years"}[x]
        )

    st.divider()

    if st.button("🏆 Compare All Strategies", use_container_width=True):
        with st.spinner(f"Running all 4 strategies on {cmp_stock}..."):
            result        = run_all_backtests(symbol=WATCHLIST[cmp_stock], stock_name=cmp_stock, period=cmp_period)
            display_df    = result[0]
            equity_all    = result[1]
            comparison_df = result[2]

        if display_df.empty:
            st.error("Could not run comparison — try again.")
        else:
            best = get_best_strategy(comparison_df)
            st.success(f"🏆 Best Strategy for {cmp_stock} over {cmp_period}: **{best}**")
            st.divider()
            st.subheader("📋 Strategy Comparison Table")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.divider()
            st.subheader("📈 Equity Curves — All Strategies")
            equity_combined = pd.DataFrame()
            for strategy_name, eq_df in equity_all.items():
                if not eq_df.empty and 'Equity' in eq_df.columns:
                    equity_combined[strategy_name] = eq_df['Equity']
            if not equity_combined.empty:
                st.line_chart(equity_combined, use_container_width=True)
            st.divider()
            st.subheader("🎯 Strategy Scores")
            st.caption("Composite = 50% Return + 30% Win Rate + 20% Risk")
            scores = get_strategy_scores(comparison_df)
            score_rows = []
            for strategy, s in scores.items():
                score_rows.append({
                    "Strategy":        strategy,
                    "Return Score":    f"{s['Return Score']}/100",
                    "Win Rate Score":  f"{s['Win Rate Score']}/100",
                    "Risk Score":      f"{s['Risk Score']}/100",
                    "Composite Score": f"{s['Composite Score']}/100",
                })
            st.dataframe(pd.DataFrame(score_rows), use_container_width=True, hide_index=True)
            st.divider()
            st.download_button(
                label="⬇️ Download Comparison Report",
                data=display_df.to_csv(index=False),
                file_name=f"strategy_comparison_{cmp_stock}_{cmp_period}.csv", mime="text/csv"
            )
    else:
        st.info("👆 Select a stock and period, then click Compare All Strategies")


# ════════════════════════════════════════════════
# TAB 8: LOGS
# ════════════════════════════════════════════════
with tab8:

    st.title("📋 System Logs")
    st.divider()

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
            label="⬇️ Download Trade History",
            data=trades_df.to_csv(index=False),
            file_name="paper_trades.csv", mime="text/csv"
        )

    st.divider()

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
            label="⬇️ Download Signal Log",
            data=log_df.to_csv(index=False),
            file_name="signal_log.csv", mime="text/csv"
        )

    st.divider()

    # ── Watchlist Manager ─────────────────────────
    st.subheader("📋 Watchlist Manager")
    st.caption("Your current watchlist loaded from watchlist.csv")

    wl_df = load_watchlist(active_only=False)
    if not wl_df.empty:
        st.dataframe(wl_df, use_container_width=True, hide_index=True)
        st.download_button(
            label="⬇️ Download Watchlist",
            data=wl_df.to_csv(index=False),
            file_name="watchlist.csv", mime="text/csv"
        )
        st.caption("💡 To add/remove stocks: download the CSV, edit it, then replace watchlist.csv in your repo")

    wl_summary = get_watchlist_summary()
    w1, w2, w3 = st.columns(3)
    w1.metric("Active Stocks", wl_summary["Active Stocks"])
    w2.metric("Total Stocks",  wl_summary["Total Stocks"])
    w3.metric("Sectors",       wl_summary["Sectors"])

    st.divider()

    # ════════════════════════════════════════════
    # SETTINGS PANEL
    # ════════════════════════════════════════════
    st.subheader("⚙️ Strategy Settings")
    st.caption("These settings control all backtesting and trading logic")

    # Load current settings
    current_settings = get_settings()
    source = current_settings.get("_source", "defaults")

    # Show where settings are coming from
    if source == "Google Sheet":
        st.success("✅ Settings loaded from Google Sheet — edit the sheet to change values")
    else:
        st.info("ℹ️ Using default settings — set up Google Sheet for remote control")
        st.caption(
            "To control settings from Google Sheets: "
            "open config/settings_loader.py and add your Google Sheet URL"
        )

    # Display current settings in a clean table
    settings_display = []
    settings_labels = {
        "STOP_LOSS_PCT":      ("Stop Loss",              "%",  100),
        "TARGET_PROFIT_PCT":  ("Profit Target",          "%",  100),
        "USE_TRAILING_STOP":  ("Trailing Stop Enabled",  "",   1),
        "TRAILING_STOP_PCT":  ("Trailing Stop %",        "%",  100),
        "MAX_POSITION_PCT":   ("Max Position Size",      "%",  100),
        "WEAK_POSITION_PCT":  ("Weak Signal Position",   "%",  100),
        "BROKERAGE_PCT":      ("Brokerage",              "%",  100),
        "STRONG_BUY_VOTES":   ("Strong Buy Votes Needed","",   1),
        "WEAK_BUY_VOTES":     ("Weak Buy Votes Needed",  "",   1),
        "MACD_MOMENTUM_EXIT": ("MACD Momentum Exit",     "%",  100),
        "STARTING_CAPITAL":   ("Starting Capital",       "₹",  1),
    }

    for key, (label, unit, multiplier) in settings_labels.items():
        value = current_settings.get(key, DEFAULT_SETTINGS.get(key, "N/A"))
        default = DEFAULT_SETTINGS.get(key, "N/A")

        # Format display value
        if unit == "%" and multiplier == 100:
            display_value   = f"{round(float(value) * 100, 1)}%"
            display_default = f"{round(float(default) * 100, 1)}%"
        elif unit == "₹":
            display_value   = f"₹{int(value):,}"
            display_default = f"₹{int(default):,}"
        else:
            display_value   = str(value)
            display_default = str(default)

        # Flag if different from default
        changed = str(value) != str(default)

        settings_display.append({
            "Setting":         label,
            "Current Value":   display_value,
            "Default":         display_default,
            "Changed":         "✏️ Modified" if changed else "—",
        })

    st.dataframe(
        pd.DataFrame(settings_display),
        use_container_width=True,
        hide_index=True
    )

    # ── Key metrics display ───────────────────────
    st.caption("📊 Key Trading Parameters at a Glance")
    sv1, sv2, sv3, sv4 = st.columns(4)
    sv1.metric(
        "Stop Loss",
        f"{round(current_settings['STOP_LOSS_PCT'] * 100, 1)}%"
    )
    sv2.metric(
        "Profit Target",
        f"{round(current_settings['TARGET_PROFIT_PCT'] * 100, 1)}%"
    )
    sv3.metric(
        "Trailing Stop",
        f"{round(current_settings['TRAILING_STOP_PCT'] * 100, 1)}%" if current_settings['USE_TRAILING_STOP'] else "OFF"
    )
    sv4.metric(
        "Max Position",
        f"{round(current_settings['MAX_POSITION_PCT'] * 100, 1)}%"
    )

# ── Footer ─────────────────────────────────────────
st.divider()
st.caption("📌 Data: Yahoo Finance | Refreshes every 5 min | Not financial advice")
