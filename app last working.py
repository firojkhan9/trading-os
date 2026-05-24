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
from strategies.explainability_engine import get_full_explanation 
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
from strategies.fundamental_engine import (
    get_fundamental_display,
    get_fundamental_score_only,
    format_market_cap,
)
from strategies.sentiment_engine import (
    get_stock_sentiment,
    get_market_sentiment,
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
    st.title("🔐 Firoj Khan's Trading OS — Login")
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

# ── Shared session state for cross-tab stock selection ─────────────
# This lets Scanner, RS Ranking, Stock Score tabs share the same
# selected stock — and enables one-click select + buy from any tab.
if "shared_stock" not in st.session_state:
    st.session_state["shared_stock"] = STOCK_NAMES[0]


def render_quick_buy_panel(stock_name, tab_key_prefix):
    """
    Reusable buy/sell panel shown on Scanner, RS Ranking, Stock Score tabs.
    stock_name      : e.g. "RELIANCE"
    tab_key_prefix  : unique string like "scanner", "rs", "score"
                      prevents Streamlit duplicate widget key errors.
    """
    symbol        = WATCHLIST.get(stock_name)
    if not symbol:
        st.warning("Stock not found in watchlist.")
        return

    # Fetch latest price
    try:
        quick_data    = fetch_stock_data(symbol)
        quick_price   = round(float(quick_data['Close'].iloc[-1]), 2)
    except Exception:
        st.error("Could not fetch price. Try again.")
        return

    current_capital = get_current_capital()
    buy_risk        = run_full_risk_check(stock_name, quick_price, "BUY")
    sell_risk       = run_full_risk_check(stock_name, quick_price, "CHECK")

    st.markdown(f"**💰 Quick Trade — {stock_name} @ ₹{quick_price}**")
    cap1, cap2 = st.columns(2)
    cap1.metric("Available Cash", f"₹{current_capital:,}")
    cap2.metric("Price",          f"₹{quick_price}")

    for block   in buy_risk["blocks"]:   st.error(block)
    for warning in sell_risk["warnings"]:st.warning(warning)

    col_b, col_s = st.columns(2)
    with col_b:
        if st.button(
            f"🟢 BUY {stock_name}",
            key=f"buy_{tab_key_prefix}_{stock_name}",
            use_container_width=True,
            disabled=not buy_risk["approved"]
        ):
            result = execute_paper_buy(stock_name, quick_price)
            if result['status'] == "EXECUTED":
                st.success(f"✅ Bought {result['quantity']} shares @ ₹{result['price']} | Cash left: ₹{result['capital']:,}")
            else:
                st.warning(f"⚠️ {result['reason']}")
    with col_s:
        if st.button(
            f"🔴 SELL {stock_name}",
            key=f"sell_{tab_key_prefix}_{stock_name}",
            use_container_width=True,
        ):
            result = execute_paper_sell(stock_name, quick_price)
            if result['status'] == "EXECUTED":
                pnl_icon = "✅" if result['pnl'] >= 0 else "❌"
                st.success(f"{pnl_icon} Sold {result['quantity']} @ ₹{result['price']} | P&L: ₹{result['pnl']} ({result['pnl_pct']}%)")
            else:
                st.warning(f"⚠️ {result['reason']}")

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


@st.cache_data(ttl=1800)   # Cache 30 minutes — news doesn't change that fast
def fetch_market_sentiment_cached():
    return get_market_sentiment()


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

    st.title("🚀 Firoj Khan's Trading OS — Market Dashboard")
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

    # ── Row click → update shared session state ───
    if selection and selection.selection.rows:
        clicked_index = selection.selection.rows[0]
        clicked_stock = summary_df.iloc[clicked_index]['Stock']
        if clicked_stock in STOCK_NAMES:
            st.session_state["shared_stock"] = clicked_stock

    default_index  = STOCK_NAMES.index(st.session_state["shared_stock"]) \
                     if st.session_state["shared_stock"] in STOCK_NAMES else 0
    selected_stock = st.selectbox(
        "🎯 Or select from dropdown:",
        options=STOCK_NAMES, index=default_index, key="main_selector"
    )
    # Keep session state in sync with dropdown too
    st.session_state["shared_stock"] = selected_stock
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

            # ── Quick Buy Panel ───────────────────
            st.divider()
            st.subheader("💰 Quick Trade from Scanner")
            st.caption("Select a stock from the scan results and trade directly here")
            scanner_trade_stock = st.selectbox(
                "Select stock to trade:",
                options=STOCK_NAMES,
                key="scanner_trade_stock"
            )
            render_quick_buy_panel(scanner_trade_stock, "scanner")
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
    st.caption("Full explanation of why a signal was generated — with signal rarity analysis")
    st.divider()
 
    sc1, sc2 = st.columns(2)
    with sc1:
        score_stock = st.selectbox(
            "Select Stock to Analyse:",
            options=STOCK_NAMES,
            key="score_stock"
        )
 
    st.divider()
 
    if st.button("🔍 Analyse & Explain", use_container_width=True, key="calc_score"):
        with st.spinner(f"Running full analysis on {score_stock}... fetching 6 months of data"):
 
            score_symbol = WATCHLIST[score_stock]
 
            # Fetch 6 months for rarity analysis
            score_data_long = yf.download(
                tickers=score_symbol, period="6mo",
                interval="1d", progress=False
            )
            score_data_long.columns = [col[0] for col in score_data_long.columns]
 
            # Also fetch 60d for indicators
            score_data = fetch_stock_data(score_symbol)
 
            # Run all strategies
            score_analyzed  = analyze_stock(score_data.copy())
            score_ema_data  = calculate_ema_signals(score_data.copy())
            score_bb_data   = analyze_bollinger(score_data.copy())
            score_macd_data = analyze_macd(score_data.copy())
 
            score_latest     = score_analyzed.iloc[-1]
            score_ema_latest = score_ema_data.iloc[-1]
            score_bb_latest  = score_bb_data.iloc[-1]
            score_macd_latest= score_macd_data.iloc[-1]
 
            s_signal   = score_latest['Signal']
            s_ema_sig  = score_ema_latest['EMA_Signal']
            s_bb_sig   = score_bb_latest['BB_Signal']
            s_macd_sig = score_macd_latest['MACD_Crossover']
 
            score_combined = build_combined_summary(
                ma_signal=s_signal, ema_signal=s_ema_sig,
                bb_signal=s_bb_sig, macd_signal=s_macd_sig,
            )
 
            # Get regime
            score_regime_data = fetch_regime_analysis()
            score_regime      = score_regime_data["regime"]
 
            # Build composite score
            s_close  = round(float(score_latest['Close']), 2)
            s_ma20   = round(float(score_latest['MA20']), 2)   if not pd.isna(score_latest['MA20'])   else None
            s_rsi    = round(float(score_latest['RSI']), 2)    if not pd.isna(score_latest['RSI'])    else None
            s_ema9   = round(float(score_ema_latest['EMA9']), 2)  if not pd.isna(score_ema_latest['EMA9'])  else None
            s_ema21  = round(float(score_ema_latest['EMA21']), 2) if not pd.isna(score_ema_latest['EMA21']) else None
            s_macd   = float(score_macd_latest['MACD'])        if not pd.isna(score_macd_latest['MACD'])        else None
            s_msig   = float(score_macd_latest['MACD_Signal']) if not pd.isna(score_macd_latest['MACD_Signal']) else None
            s_mhist  = float(score_macd_latest['MACD_Hist'])   if not pd.isna(score_macd_latest['MACD_Hist'])   else None
            s_bbpct  = float(score_bb_latest['BB_Pct'])        if not pd.isna(score_bb_latest['BB_Pct'])        else None
 
            s_votes = {
                "buy":  score_combined["Strategies Buy"],
                "sell": score_combined["Strategies Sell"],
                "hold": score_combined["Strategies Hold"],
            }
            with st.spinner(f"Fetching fundamental data for {score_stock}..."):
                fund_display = get_fundamental_display(score_symbol, score_stock)
                fund_score_value = fund_display["score_result"]["Fundamental Score"]
            with st.spinner(f"Analysing sentiment for {score_stock}..."):
                sentiment_result = get_stock_sentiment(score_stock, score_symbol, max_results=10)
                sentiment_score_value = sentiment_result["score_0_100"]
            score_result = build_composite_score(
                stock_name=score_stock, latest_close=s_close,
                ma20=s_ma20, rsi=s_rsi, ema9=s_ema9, ema21=s_ema21,
                macd=s_macd, macd_signal=s_msig, macd_hist=s_mhist,
                bb_pct=s_bbpct, bb_signal=s_bb_sig,
                combined_votes=s_votes,
                combined_weighted_score=score_combined["Score"],
                regime=score_regime, rs_score=None,
                fundamental_score=fund_score_value,
                sentiment_score=sentiment_score_value
            )
 
            # Get full explanation
            explanation = get_full_explanation(
                stock_name   = score_stock,
                data         = score_data_long,
                analyzed     = score_analyzed,
                ema_data     = score_ema_data,
                bb_data      = score_bb_data,
                macd_data    = score_macd_data,
                combined     = score_combined,
                regime       = score_regime,
                composite_score = score_result["Composite Score"],
            )
 
        # ════════════════════════════════════════
        # DISPLAY RESULTS
        # ════════════════════════════════════════
 
        composite    = score_result["Composite Score"]
        final_signal = explanation["final_signal"]
        rarity       = explanation["rarity"]
        risk         = explanation["risk"]
 
        # ── Main signal banner ────────────────────
        if "STRONG BUY" in final_signal:
            st.success(f"## {final_signal} — {score_stock}")
        elif "BUY" in final_signal:
            st.success(f"### {final_signal} — {score_stock}")
        elif "STRONG SELL" in final_signal:
            st.error(f"## {final_signal} — {score_stock}")
        elif "SELL" in final_signal:
            st.error(f"### {final_signal} — {score_stock}")
        else:
            st.info(f"### {final_signal} — {score_stock}")
 
        # ── Top metrics row ───────────────────────
        tm1, tm2, tm3, tm4, tm5 = st.columns(5)
        tm1.metric("Composite Score",  f"{composite}/100")
        tm2.metric("Confidence",       score_result["Confidence"])
        tm3.metric("Position Size",    score_result["Position Size"])
        tm4.metric("Strategies BUY",   explanation["buy_votes"])
        tm5.metric("Market Regime",    score_regime)
 
        st.divider()
 
        # ════════════════════════════════════════
        # SIGNAL RARITY SECTION
        # ════════════════════════════════════════
        st.subheader("🔥 Signal Rarity Analysis")
        st.caption(f"How often has this signal occurred in the last {rarity['total_days']} trading days (~6 months)?")
 
        r1, r2, r3, r4 = st.columns(4)
        r1.metric(
            "Rarity",
            rarity["rarity_label"],
        )
        r2.metric(
            "Occurrences",
            f"{rarity['occurrences']} / {rarity['total_days']} days",
            help="How many days had the same signal type in the last 6 months"
        )
        r3.metric(
            "Frequency",
            f"{rarity['rarity_pct']}% of days",
            help="Percentage of trading days with this signal"
        )
        r4.metric(
            "Last Seen",
            f"{rarity['days_since_last']} days ago",
            help=f"Last occurrence: {rarity['last_occurrence']}"
        )
 
        # Rarity interpretation
        if rarity["occurrences"] == 0:
            st.error(
                f"🔥 **NEVER occurred in 6 months** — This is an extremely rare signal. "
                f"The backtest showed 0 trades because this combination never triggered historically. "
                f"It is triggering for the first time now. Treat with high conviction but verify manually."
            )
        elif rarity["rarity_pct"] <= 5:
            st.warning(
                f"⭐ **RARE signal** — Only {rarity['occurrences']} occurrences in {rarity['total_days']} days. "
                f"Last occurred {rarity['days_since_last']} days ago ({rarity['last_occurrence']}). "
                f"This is why backtests may show few or no trades — the signal is selective by design."
            )
        elif rarity["rarity_pct"] <= 15:
            st.info(
                f"🔔 **Occasional signal** — Occurred {rarity['occurrences']} times in 6 months. "
                f"Last seen {rarity['days_since_last']} days ago."
            )
        else:
            st.info(
                f"📊 **Common signal** — Occurred {rarity['occurrences']} times ({rarity['rarity_pct']}% of days). "
                f"This signal triggers frequently — use with other filters."
            )
 
        st.divider()
 
        # ════════════════════════════════════════
        # WHY THIS SIGNAL — STRATEGY BREAKDOWN
        # ════════════════════════════════════════
        st.subheader("📋 Why This Signal — Strategy by Strategy")
 
        if explanation["reasons_buy"]:
            st.markdown("**✅ Reasons Supporting BUY:**")
            for reason in explanation["reasons_buy"]:
                st.markdown(f"- {reason}")
 
        if explanation["reasons_sell"]:
            st.markdown("**🔴 Reasons Against / Bearish:**")
            for reason in explanation["reasons_sell"]:
                st.markdown(f"- {reason}")
 
        if explanation["reasons_hold"]:
            st.markdown("**⚪ Neutral / Watch:**")
            for reason in explanation["reasons_hold"]:
                st.markdown(f"- {reason}")
 
        st.divider()
 
        # ════════════════════════════════════════
        # SCORE BREAKDOWN
        # ════════════════════════════════════════
        st.subheader("📊 Composite Score Breakdown")
        st.caption("How each dimension contributed to the final score")
 
        breakdown_rows = []
        for dim, val in score_result["Individual Scores"].items():
            weight_map = {
                "Trend":         "20%",   # MA + EMA direction
                "Momentum":      "20%",   # RSI + MACD
                "Volatility":    "12%",   # Bollinger Bands
                "Signal":        "17%",   # Combined strategy votes
                "Regime":        "10%",   # Market regime
                "Rel. Strength": "5%",    # vs NIFTY
                "Fundamental":   "8%",    # Business health
                "Sentiment":     "8%",    # News sentiment
            }
            bar = "█" * (val // 10) + "░" * (10 - val // 10)
            breakdown_rows.append({
                "Dimension": dim,
                "Score":     f"{val}/100",
                "Weight":    weight_map.get(dim, "N/A"),
                "Visual":    bar,
            })
        st.dataframe(
            pd.DataFrame(breakdown_rows),
            use_container_width=True, hide_index=True
        )
 
        st.divider()
 
        # ════════════════════════════════════════
        # ENTRY PRICE LEVELS
        # ════════════════════════════════════════
        st.subheader("🎯 Entry & Risk Levels")
        st.caption("Exact price levels if you decide to trade this")
 
        el1, el2, el3, el4 = st.columns(4)
        el1.metric("Entry Price",    f"₹{risk['entry_price']}")
        el2.metric(
            f"Stop Loss ({risk['stop_pct']}%)",
            f"₹{risk['stop_price']}",
            delta=f"-₹{round(risk['entry_price'] - risk['stop_price'], 2)}",
            delta_color="inverse"
        )
        el3.metric(
            f"Target ({risk['target_pct']}%)",
            f"₹{risk['target_price']}",
            delta=f"+₹{round(risk['target_price'] - risk['entry_price'], 2)}"
        )
        el4.metric("Risk:Reward",    f"1 : {risk['risk_reward']}")
 
        st.caption(
            f"💡 Trailing stop activates once profitable — "
            f"trails {risk['trail_pct']}% below peak price to lock in gains"
        )
 
        st.divider()

        # ════════════════════════════════════════════════
        # FUNDAMENTAL INTELLIGENCE SECTION
        # ════════════════════════════════════════════════
        
        st.subheader("🏦 Fundamental Intelligence")
        st.caption("Financial health of the business behind the stock")
        
        fund_result = fund_display["score_result"]
        fund_data   = fund_display["fundamentals"]
        
        if not fund_result["Data Available"]:
            st.warning(
                "⚠️ Fundamental data not available for this stock right now. "
                "This can happen for some NSE stocks on Yahoo Finance. "
                "The composite score uses a neutral 50 for this dimension."
            )
        else:
            # ── Fundamental grade banner ───────────────────
            fund_composite = fund_result["Fundamental Score"]
            fund_grade     = fund_result["Grade"]
        
            if fund_composite >= 70:
                st.success(f"### Fundamental Grade: {fund_grade}  |  Score: {fund_composite}/100")
            elif fund_composite >= 50:
                st.info(f"### Fundamental Grade: {fund_grade}  |  Score: {fund_composite}/100")
            else:
                st.warning(f"### Fundamental Grade: {fund_grade}  |  Score: {fund_composite}/100")
        
            st.caption(fund_result["Summary"])
            st.write("")
        
            # ── Company identity ──────────────────────────
            st.caption("📋 Company Profile")
            fi1, fi2, fi3 = st.columns(3)
            fi1.metric("Sector",   fund_data.get("sector",   "N/A"))
            fi2.metric("Industry", fund_data.get("industry", "N/A"))
            fi3.metric("Market Cap", format_market_cap(fund_data.get("market_cap_cr")))
        
            st.divider()
        
            # ── Dimension scores ──────────────────────────
            st.caption("📊 Fundamental Score Breakdown")
            fund_breakdown = []
            weight_map = {
                "Valuation":     "25%",
                "Profitability": "25%",
                "Growth":        "20%",
                "Health":        "20%",
                "Size":          "10%",
            }
            for dim, val in fund_result["Individual Scores"].items():
                bar = "█" * (val // 10) + "░" * (10 - val // 10)
                fund_breakdown.append({
                    "Dimension": dim,
                    "Score":     f"{val}/100",
                    "Weight":    weight_map.get(dim, "N/A"),
                    "Visual":    bar,
                })
            st.dataframe(
                pd.DataFrame(fund_breakdown),
                use_container_width=True, hide_index=True
            )
        
            st.divider()
        
            # ── Raw metrics ───────────────────────────────
            st.caption("📈 Key Financial Metrics")
            fm1, fm2, fm3, fm4 = st.columns(4)
            fm5, fm6, fm7, fm8 = st.columns(4)
        
            pe  = fund_data.get("pe_ratio")
            pb  = fund_data.get("pb_ratio")
            roe = fund_data.get("roe")
            pm  = fund_data.get("profit_margin")
            de  = fund_data.get("debt_equity")
            cr  = fund_data.get("current_ratio")
            rg  = fund_data.get("revenue_growth")
            eg  = fund_data.get("earnings_growth")
        
            fm1.metric("P/E Ratio",       f"{pe}x"   if pe  is not None else "N/A",
                    help="Price vs Earnings. Lower = cheaper. 15-25x is fair for India.")
            fm2.metric("P/B Ratio",       f"{pb}x"   if pb  is not None else "N/A",
                    help="Price vs Book Value. Below 3x is generally reasonable.")
            fm3.metric("ROE",             f"{roe}%"  if roe is not None else "N/A",
                    help="Return on Equity. 15%+ is good.")
            fm4.metric("Profit Margin",   f"{pm}%"   if pm  is not None else "N/A",
                    help="Net profit as % of revenue. Higher = more profitable.")
            fm5.metric("Debt / Equity",   f"{de}"    if de  is not None else "N/A",
                    help="Lower is safer. Above 2 = high debt risk.")
            fm6.metric("Current Ratio",   f"{cr}"    if cr  is not None else "N/A",
                    help="Ability to pay short-term bills. Above 1.5 is comfortable.")
            fm7.metric("Revenue Growth",  f"{rg}%"   if rg  is not None else "N/A",
                    help="Year-over-year revenue growth. 10%+ is healthy.")
            fm8.metric("Earnings Growth", f"{eg}%"   if eg  is not None else "N/A",
                    help="Year-over-year earnings growth.")
        
            st.divider()
        
            # ── Signals and warnings ──────────────────────
            if fund_result["Signals"]:
                st.caption("✅ Fundamental Strengths")
                for sig in fund_result["Signals"]:
                    st.markdown(f"- {sig}")
        
            if fund_result["Warnings"]:
                st.caption("⚠️ Fundamental Risks")
                for warn in fund_result["Warnings"]:
                    st.markdown(f"- {warn}")
        
            # ── Data freshness note ───────────────────────
            st.caption(
                f"📅 Data fetched: {fund_data.get('fetched_at', 'N/A')} | "
                "Source: Yahoo Finance (yfinance). "
                "Fundamental data updates quarterly. Use as direction, not exact values."
            )

        st.divider()

        # ════════════════════════════════════════════════
        # SENTIMENT INTELLIGENCE SECTION
        # ════════════════════════════════════════════════

        st.subheader("📰 Sentiment Intelligence")
        st.caption("What is the news saying about this stock right now?")
        
        if not sentiment_result["news_available"]:
            st.info(
                "ℹ️ No recent news found for this stock. "
                "This can happen when news APIs are rate-limited or the stock has low media coverage. "
                "The composite score uses a neutral 50 for this dimension. "
                "You can manually enter headlines below to analyse them."
            )
        else:
            # ── Sentiment banner ──────────────────────────
            sent_label    = sentiment_result["label"]
            sent_score_v  = sentiment_result["score_0_100"]
            sent_avg      = sentiment_result["avg_score"]
        
            if "VERY BULLISH" in sent_label:
                st.success(f"### News Sentiment: {sent_label}  |  Score: {sent_score_v}/100")
            elif "BULLISH" in sent_label:
                st.success(f"### News Sentiment: {sent_label}  |  Score: {sent_score_v}/100")
            elif "VERY BEARISH" in sent_label:
                st.error(f"### News Sentiment: {sent_label}  |  Score: {sent_score_v}/100")
            elif "BEARISH" in sent_label:
                st.error(f"### News Sentiment: {sent_label}  |  Score: {sent_score_v}/100")
            else:
                st.info(f"### News Sentiment: {sent_label}  |  Score: {sent_score_v}/100")
        
            # ── Sentiment breakdown metrics ────────────────
            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Headlines Analysed", sentiment_result["total_headlines"])
            sm2.metric("Bullish Headlines",  sentiment_result["bullish_count"],
                    help="Headlines with positive financial language")
            sm3.metric("Bearish Headlines",  sentiment_result["bearish_count"],
                    help="Headlines with negative financial language")
            sm4.metric("Neutral Headlines",  sentiment_result["neutral_count"],
                    help="Headlines with no strong directional signal")
        
            st.divider()
        
            # ── Scored headlines table ─────────────────────
            st.caption("📋 Headline by Headline Sentiment Breakdown")
            st.caption("Each headline scored: +1.0 = very bullish, 0 = neutral, -1.0 = very bearish")
        
            if sentiment_result["scored_headlines"]:
                headlines_df = pd.DataFrame(sentiment_result["scored_headlines"])
        
                # Show only the most useful columns
                display_cols = ["Headline", "Sentiment", "Score"]
                headlines_df_display = headlines_df[display_cols].copy()
        
                def color_sentiment(val):
                    if "BULLISH" in str(val):  return "color: green"
                    if "BEARISH" in str(val):  return "color: red"
                    return "color: gray"
        
                def color_score(val):
                    try:
                        f = float(val)
                        if f >= 0.15:  return "color: green"
                        if f <= -0.15: return "color: red"
                    except Exception:
                        pass
                    return "color: gray"
        
                st.dataframe(
                    headlines_df_display.style
                        .map(color_sentiment, subset=["Sentiment"])
                        .map(color_score,     subset=["Score"]),
                    use_container_width=True, hide_index=True
                )
        
            st.caption(
                f"📅 Fetched: {sentiment_result.get('fetched_at', 'N/A')} | "
                "Source: Google News RSS via GNews. "
                "Scored using Financial Lexicon (60%) + TextBlob NLP (40%)."
            )
        
        # ── Manual headline analyser ──────────────────────
        st.divider()
        st.caption("🔍 Manual Sentiment Tester — Paste your own headlines to analyse")
        st.caption(
            "Copy headlines from Moneycontrol, ET Markets, or any news source. "
            "One headline per line."
        )
        
        manual_input = st.text_area(
            "Paste headlines here (one per line):",
            placeholder=(
                "Example:\n"
                "Reliance Q4 profit jumps 18 percent, beats estimates\n"
                "HDFC Bank faces RBI regulatory action on credit card growth"
            ),
            height=120,
            key="manual_headlines_input"
        )
        
        if st.button("🔍 Analyse My Headlines", key="analyse_manual_headlines"):
            if manual_input.strip():
                lines = [l.strip() for l in manual_input.strip().split('\n') if l.strip()]
                from strategies.sentiment_engine import demo_sentiment
                manual_result = demo_sentiment(lines)
        
                if manual_result["total_headlines"] > 0:
                    if "BULLISH" in manual_result["label"]:
                        st.success(f"Manual Sentiment: **{manual_result['label']}** | Score: {manual_result['score_0_100']}/100")
                    elif "BEARISH" in manual_result["label"]:
                        st.error(f"Manual Sentiment: **{manual_result['label']}** | Score: {manual_result['score_0_100']}/100")
                    else:
                        st.info(f"Manual Sentiment: **{manual_result['label']}** | Score: {manual_result['score_0_100']}/100")
        
                    manual_df = pd.DataFrame(manual_result["scored_headlines"])[["Headline","Sentiment","Score"]]
                    st.dataframe(manual_df, use_container_width=True, hide_index=True)
            else:
                st.warning("Please paste at least one headline to analyse.")
        
        
        # ════════════════════════════════════════════════
        # CHANGE 5 (optional but recommended) — Market Sentiment banner in Tab 1
        #
        # In Tab 1 (Dashboard), after the Market Regime banner
        # (the st.caption("👆 Full analysis in...") line),
        # add this block to show overall market sentiment:
        # ════════════════════════════════════════════════
        
        # ── Market Sentiment Mini Banner (Tab 1) ──────────
        market_sent = fetch_market_sentiment_cached()
        if market_sent["news_available"]:
            sent_lbl = market_sent["label"]
            if "BULLISH" in sent_lbl:
                st.success(f"📰 Market Sentiment: **{sent_lbl}** ({market_sent['score_0_100']}/100) | Based on {market_sent['total_headlines']} news items")
            elif "BEARISH" in sent_lbl:
                st.error(f"📰 Market Sentiment: **{sent_lbl}** ({market_sent['score_0_100']}/100) | Based on {market_sent['total_headlines']} news items")
            else:
                st.info(f"📰 Market Sentiment: **{sent_lbl}** ({market_sent['score_0_100']}/100)")

        st.divider()

        # ════════════════════════════════════════
        # VERDICT
        # ════════════════════════════════════════
        st.subheader("⚖️ Final Verdict")
        st.markdown(explanation["verdict"])
 
        st.divider()
 
        # ════════════════════════════════════════
        # SIGNAL HISTORY — LAST 30 DAYS
        # ════════════════════════════════════════
        st.subheader("📅 Signal History — Last 30 Trading Days")
        st.caption("What has the Combined Signal been saying over the past 30 days?")
 
        recent = explanation["recent_history"]
 
        def color_hist_signal(val):
            if "STRONG BUY"  in str(val): return "color: green; font-weight: bold"
            if "BUY"         in str(val): return "color: lightgreen"
            if "STRONG SELL" in str(val): return "color: red; font-weight: bold"
            if "SELL"        in str(val): return "color: orange"
            return "color: gray"
 
        if not recent.empty:
            st.dataframe(
                recent.style.map(color_hist_signal, subset=["Signal"]),
                use_container_width=True
            )
 
        # Download full report
        st.divider()
        report_text = f"""
TRADING OS — STOCK ANALYSIS REPORT
Stock: {score_stock}
Date:  {datetime.now().strftime('%d %b %Y %I:%M %p')}
 
SIGNAL: {final_signal}
COMPOSITE SCORE: {composite}/100
CONFIDENCE: {score_result['Confidence']}
REGIME: {score_regime}
 
SIGNAL RARITY:
- Occurrences in 6 months: {rarity['occurrences']} / {rarity['total_days']} days
- Frequency: {rarity['rarity_pct']}% of days
- Last seen: {rarity['last_occurrence']} ({rarity['days_since_last']} days ago)
- Rarity rating: {rarity['rarity_label']}
 
ENTRY LEVELS:
- Entry: Rs {risk['entry_price']}
- Stop Loss ({risk['stop_pct']}%): Rs {risk['stop_price']}
- Target ({risk['target_pct']}%): Rs {risk['target_price']}
- Risk:Reward: 1:{risk['risk_reward']}
- Suggested Position: {risk['position_pct']}%
 
VERDICT:
{explanation['verdict']}
        """.strip()

        # ── Quick Buy from Stock Score ────────────
        st.divider()
        st.subheader("💰 Quick Trade")
        st.caption("Score looks good? Trade directly from this page")
        render_quick_buy_panel(score_stock, "score")
        st.divider()

        st.download_button(
            label     = f"⬇️ Download Analysis Report — {score_stock}",
            data      = report_text,
            file_name = f"analysis_{score_stock}_{datetime.now().strftime('%Y%m%d')}.txt",
            mime      = "text/plain"
        )
 
    else:
        st.info("👆 Select a stock and click Analyse & Explain")
        st.caption(
            "This will run all 4 strategies, calculate the composite score, "
            "analyse 6 months of history to measure signal rarity, "
            "and explain exactly why the signal was generated — in plain English."
        )
 
        # Preview
        st.divider()
        st.subheader("📖 What This Analysis Shows")
        preview = [
            {"Section": "Signal Banner",        "Shows": "Current combined signal with color coding"},
            {"Section": "Signal Rarity",        "Shows": "How often this signal occurred in last 6 months"},
            {"Section": "Strategy Breakdown",   "Shows": "Why each of 4 strategies voted BUY / SELL / HOLD"},
            {"Section": "Score Breakdown",      "Shows": "How each dimension contributed to 0-100 score"},
            {"Section": "Entry & Risk Levels",  "Shows": "Exact stop loss, target and risk-reward prices"},
            {"Section": "Final Verdict",        "Shows": "Plain English summary with regime context"},
            {"Section": "Signal History",       "Shows": "Last 30 days of combined signals for this stock"},
            {"Section": "Download Report",      "Shows": "Full analysis as downloadable text file"},
        ]
        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
 

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

            # ── Quick Buy from RS Ranking ─────────
            st.divider()
            st.subheader("💰 Quick Trade from RS Ranking")
            st.caption("Found a strong RS stock? Trade directly here")
            rs_trade_stock = st.selectbox(
                "Select stock to trade:",
                options=STOCK_NAMES,
                key="rs_trade_stock"
            )
            render_quick_buy_panel(rs_trade_stock, "rs")
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
