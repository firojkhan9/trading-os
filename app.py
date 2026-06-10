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
    load_portfolio,
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

from strategies.volume_engine import (
    get_volume_analysis,
    get_volume_score_only,
)

from strategies.market_structure import (
    get_market_structure_analysis,
    get_market_structure_score_only,
)

from portfolio.capital_engine import (
    get_bucket_summary,
    get_portfolio_totals,
    get_bucket_trade_history,
    get_open_positions_by_bucket,
    bucket_buy,
    bucket_sell,
    check_position_limit,
    get_bucket_available_cash,
    suggest_bucket,
    BUCKET_CONFIG,
    TOTAL_CAPITAL,
    reset_bucket_state,
)

from engine.loop_state import (
    load_loop_state,
    is_market_open,
    start_loop,
    pause_loop,
    stop_loop,
    load_decision_log,
    clear_decision_log,
    get_market_status,
    STATUS_RUNNING,
    STATUS_PAUSED,
    STATUS_STOPPED,
)
from engine.execution_loop import run_one_cycle

from risk.portfolio_risk import get_risk_dashboard_data, format_risk_level

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


def render_quick_buy_panel(
    stock_name,
    tab_key_prefix,
    composite_score=None,
    combined_signal=None,
    buy_votes=None,
    regime=None,
):
    """
    Unified smart trade panel — used on all tabs.
    All trades go through the bucket system (portfolio/capital_engine.py).
    Auto-suggests a fund type (bucket) based on score + signal + regime.
    User sees the suggestion but can override with the dropdown.
 
    stock_name      : e.g. "RELIANCE"
    tab_key_prefix  : unique key prefix to avoid Streamlit widget conflicts
    composite_score : 0-100 (optional — used for suggestion + threshold check)
    combined_signal : e.g. "STRONG BUY 🟢🟢" (optional)
    buy_votes       : int 0-4 (optional)
    regime          : market regime string (optional)
    """
    symbol = WATCHLIST.get(stock_name)
    if not symbol:
        st.warning("Stock not found in watchlist.")
        return
 
    # ── Fetch latest price ────────────────────────
    try:
        quick_data  = fetch_stock_data(symbol)
        quick_price = round(float(quick_data['Close'].iloc[-1]), 2)
    except Exception:
        st.error("Could not fetch price. Try again.")
        return
 
    # ── Fetch regime if not passed in ─────────────
    if regime is None:
        try:
            regime_info = fetch_regime_analysis()
            regime = regime_info.get("regime", "UNKNOWN")
        except Exception:
            regime = "UNKNOWN"
 
    # ── Get smart bucket suggestion ───────────────
    suggestion = suggest_bucket(
        composite_score=composite_score,
        combined_signal=combined_signal,
        buy_votes=buy_votes,
        regime=regime,
    )
    suggested  = suggestion["suggested_bucket"]
    confidence = suggestion["confidence"]
    reason     = suggestion["reason"]
 
    # ── Header ────────────────────────────────────
    st.markdown(f"**💰 Trade — {stock_name} @ ₹{quick_price}**")
 
    # ── Suggestion banner ─────────────────────────
    if suggested:
        conf_icon = "🟢" if confidence == "HIGH" else ("🟡" if confidence == "MEDIUM" else "🔴")
        st.info(f"{conf_icon} **Suggested fund type: {suggested}** — {reason}")
    elif "BEAR" in str(regime).upper() and "WEAK" not in str(regime).upper():
        st.error("🐻 BEAR MARKET — New buys not recommended. Protect capital.")
    else:
        st.warning(f"⚠️ {reason}")
 
    # ── Fund type selector (pre-filled with suggestion) ──
    bucket_options = list(BUCKET_CONFIG.keys())   # Long-Term, Swing, Intraday
    default_idx    = bucket_options.index(suggested) if suggested in bucket_options else 1
 
    sel_col, info_col = st.columns([2, 1])
    with sel_col:
        selected_bucket = st.selectbox(
            "Fund type:",
            options=bucket_options,
            index=default_idx,
            key=f"bucket_sel_{tab_key_prefix}_{stock_name}",
            help=(
                "Long-Term → weeks/months, score ≥70, 3+ strategies agree  |  "
                "Swing → days/weeks, score ≥60, 2+ strategies agree  |  "
                "Intraday → same day, score ≥55"
            ),
        )
    with info_col:
        avail_cash = get_bucket_available_cash(selected_bucket)
        can_add, open_c, max_p = check_position_limit(selected_bucket)
        st.metric("Available", f"₹{avail_cash:,.0f}")
        st.caption(f"{open_c}/{max_p} positions open")
 
    # ── Warn if score below bucket threshold ──────
    cfg = BUCKET_CONFIG[selected_bucket]
    if composite_score is not None and composite_score < cfg["min_score"]:
        st.warning(
            f"⚠️ Score {composite_score}/100 is below {selected_bucket} "
            f"minimum ({cfg['min_score']}/100). "
            f"Consider switching to a lower bucket."
        )
 
    # ── Execute buttons ───────────────────────────
    col_b, col_s = st.columns(2)
 
    with col_b:
        if st.button(
            f"🟢 BUY {stock_name} → {selected_bucket}",
            key=f"buy_{tab_key_prefix}_{stock_name}",
            use_container_width=True,
            disabled=not can_add,
        ):
            result = bucket_buy(
                bucket_name     = selected_bucket,
                stock_name      = stock_name,
                price           = quick_price,
                composite_score = composite_score,
            )
            if result["status"] == "EXECUTED":
                st.success(
                    f"✅ Bought {result['quantity']} shares @ ₹{result['price']} "
                    f"from {selected_bucket} bucket | "
                    f"Cash left: ₹{result['cash_left']:,.0f}"
                )
            else:
                st.error(f"🛑 {result['reason']}")
 
    with col_s:
        if st.button(
            f"🔴 SELL {stock_name} ← {selected_bucket}",
            key=f"sell_{tab_key_prefix}_{stock_name}",
            use_container_width=True,
        ):
            result = bucket_sell(
                bucket_name = selected_bucket,
                stock_name  = stock_name,
                price       = quick_price,
            )
            if result["status"] == "EXECUTED":
                pnl_icon = "✅" if result["pnl"] >= 0 else "❌"
                st.success(
                    f"{pnl_icon} Sold {result['quantity']} @ ₹{result['price']} "
                    f"from {selected_bucket} bucket | "
                    f"P&L: ₹{result['pnl']:+,.0f} ({result['pnl_pct']:+.1f}%)"
                )
            else:
                st.error(f"🛑 {result['reason']}")

# ── Fetch functions ───────────────────────────────
@st.cache_data(ttl=300)
def fetch_all_stocks():
    summary  = []
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

            # Drop rows where Close is null
            data = data.dropna(subset=["Close"])
            if data.empty:
                continue

            latest_close = round(float(data['Close'].iloc[-1]), 2)
            oldest_close = round(float(data['Close'].iloc[0]), 2)

            # Skip if price is zero or invalid
            if latest_close <= 0 or oldest_close <= 0:
                continue

            change_pct = round(((latest_close - oldest_close) / oldest_close) * 100, 2)
            day_high   = round(float(data['High'].iloc[-1]), 2)
            day_low    = round(float(data['Low'].iloc[-1]), 2)

            summary.append({
                "Stock":      name,
                "Close (₹)":  latest_close,
                "30D Change": change_pct,
                "Day High":   day_high,
                "Day Low":    day_low,
            })
        except Exception:
            continue  # silent skip — don't show warning for every stock at midnight

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
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
    "📊 Dashboard",
    "🌡️ Market Regime",
    "📡 Scanner",
    "💯 Stock Score",
    "📈 RS Ranking",
    "🔬 Backtesting",
    "📊 Strategy Comparison",
    "📋 Logs",
    "🪣 Portfolio Buckets",
    "🔄 Position Lifecycle",
    "🤖 Auto Pilot"
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
    # Load last known prices as fallback
    from portfolio.capital_engine import load_last_known_prices, save_last_known_prices
    last_known = load_last_known_prices()

    if not summary_df.empty:
        for _, row in summary_df.iterrows():
            stock = row['Stock']
            price = row.get('Close (₹)')
            if price and float(price) > 0:
                current_prices[stock] = float(price)
            elif stock in last_known:
                current_prices[stock] = last_known[stock]

        # Save good prices back for next midnight
        save_last_known_prices(current_prices)

    elif last_known:
        # summary_df itself is empty — full fallback
        current_prices = last_known

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
    # ── Trade Panel ───────────────────────────────
    st.subheader(f"💰 Trade — {selected_stock}")
 
    # Show total capital across all 3 buckets (₹6,00,000 total)
    totals = get_portfolio_totals()
    cap1, cap2, cap3, cap4 = st.columns(4)
    cap1.metric("Total Capital",   f"₹{totals['total_starting']:,.0f}")
    cap2.metric("Available Cash",  f"₹{totals['total_available']:,.0f}")
    cap3.metric("Deployed",        f"₹{totals['total_deployed']:,.0f}")
    cap4.metric("Portfolio P&L",   f"₹{totals['total_pnl']:+,.0f}",
                delta=f"{totals['total_return_pct']:+.2f}%")
    st.write("")
 
    render_quick_buy_panel(
        stock_name      = selected_stock,
        tab_key_prefix  = "dashboard",
        combined_signal = combined["Final Signal"],
        buy_votes       = combined["Strategies Buy"],
        regime          = regime,
    )

    st.divider()

    # ── Portfolio ─────────────────────────────────
    st.subheader("📂 Current Portfolio")
 
    # ── Collect live signals for held stocks ──────
    # So the Suggestion column can say ADD/SELL based
    # on the actual current strategy signal, not just price.
    # AFTER — single source of truth
    from portfolio.capital_engine import load_portfolio_from_bucket_trades

    portfolio_raw           = load_portfolio_from_bucket_trades()
    portfolio_combined_sigs = {}

    if portfolio_raw is not None and not portfolio_raw.empty:
        for held_stock in portfolio_raw['Stock'].tolist():
            try:
                held_symbol = WATCHLIST.get(held_stock)
                if held_symbol:
                    held_data     = fetch_stock_data(held_symbol)
                    held_analyzed = analyze_stock(held_data.copy())
                    held_ema      = calculate_ema_signals(held_data.copy())
                    held_bb       = analyze_bollinger(held_data.copy())
                    held_macd     = analyze_macd(held_data.copy())
                    held_combined = build_combined_summary(
                        ma_signal   = held_analyzed.iloc[-1]['Signal'],
                        ema_signal  = held_ema.iloc[-1]['EMA_Signal'],
                        bb_signal   = held_bb.iloc[-1]['BB_Signal'],
                        macd_signal = held_macd.iloc[-1]['MACD_Crossover'],
                    )
                    portfolio_combined_sigs[held_stock] = held_combined["Final Signal"]
            except Exception:
                pass

        portfolio_df = get_portfolio_summary(current_prices, portfolio_combined_sigs)
    
        if portfolio_df.empty:
            st.info("No open positions yet — click BUY above to start!")
    
        else:
            # ── Headline summary metrics ──────────────
            # Pull totals from the TOTAL row at the bottom
            total_row = portfolio_df[portfolio_df['Stock'] == '📊 TOTAL']
            if not total_row.empty:
                t           = total_row.iloc[0]
                t_invested  = float(t['Invested ₹'])
                t_value     = float(t['Value ₹'])
                t_pnl       = float(t['P&L ₹'])
                t_pnl_pct   = float(t['P&L %'])
    
                pm1, pm2, pm3, pm4 = st.columns(4)
                pm1.metric(
                    "Total Invested",
                    f"₹{t_invested:,.0f}"
                )
                pm2.metric(
                    "Current Value",
                    f"₹{t_value:,.0f}",
                    delta=f"₹{t_pnl:+,.0f}"
                )
                pm3.metric(
                    "Total P&L ₹",
                    f"₹{t_pnl:+,.0f}"
                )
                pm4.metric(
                    "Total P&L %",
                    f"{t_pnl_pct:+.2f}%"
                )
                st.write("")
    
            # ── Color functions for the table ─────────
            def color_pnl_val(val):
                """Green for profit, red for loss."""
                try:
                    f = float(val)
                    if f > 0: return "color: green; font-weight: bold"
                    if f < 0: return "color: red; font-weight: bold"
                except Exception:
                    pass
                return ""
    
            def color_suggestion(val):
                """Color each suggestion by action type."""
                s = str(val)
                if "Stop Loss"    in s: return "color: red;       font-weight: bold"
                if "Take Profit"  in s: return "color: green;     font-weight: bold"
                if "Strong Signal Exit" in s: return "color: red; font-weight: bold"
                if "Signal Exit"  in s: return "color: orange;    font-weight: bold"
                if "ADD"          in s: return "color: green;     font-weight: bold"
                if "Near Target"  in s: return "color: goldenrod"
                if "Watch Loss"   in s: return "color: orange"
                if "Overall Loss" in s: return "color: red;       font-weight: bold"
                if "Overall Profit" in s: return "color: green;   font-weight: bold"
                return "color: gray"
    
            def highlight_total_row(row):
                """Bold background for the TOTAL row."""
                if row['Stock'] == '📊 TOTAL':
                    return ['font-weight: bold; background-color: #1a1a2e'] * len(row)
                return [''] * len(row)
    
            # ── Display the table ─────────────────────
            st.dataframe(
                portfolio_df.style
                    .map(color_pnl_val,    subset=["P&L ₹", "P&L %"])
                    .map(color_suggestion, subset=["Suggestion"])
                    .apply(highlight_total_row, axis=1),
                use_container_width=True,
                hide_index=True
            )
    
            # ── Legend ───────────────────────────────
            st.caption(
                "🟢 ADD = Strong signal, consider scaling in  |  "
                "✅ SELL (Take Profit) = Target % reached  |  "
                "🔴 SELL (Stop Loss) = Stop % breached  |  "
                "🟠 SELL (Signal Exit) = Strategy says SELL  |  "
                "🟡 HOLD = No action needed"
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
            regime_info  = fetch_regime_analysis()
            scan_regime  = regime_info["regime"]
            full_df, best_return_df, worst_return_df, best_score_df = scan_all_stocks(
                watchlist_dict = WATCHLIST,
                period_days    = period_days,
                regime         = scan_regime,
            )
        if full_df.empty:
            st.error("Could not fetch data — try again.")
        else:
            # Store results so they survive BUY button clicks
            st.session_state["scan_full_df"]        = full_df
            st.session_state["scan_best_return_df"] = best_return_df
            st.session_state["scan_worst_return_df"]= worst_return_df
            st.session_state["scan_best_score_df"]  = best_score_df
            st.session_state["scan_regime"]         = scan_regime

    # Display results from session_state (persists across reruns)
    if "scan_full_df" in st.session_state:
        full_df        = st.session_state["scan_full_df"]
        best_return_df = st.session_state["scan_best_return_df"]
        worst_return_df= st.session_state["scan_worst_return_df"]
        best_score_df  = st.session_state["scan_best_score_df"]
        scan_regime    = st.session_state["scan_regime"]

    

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

        # ── Full scan table with row selection ────
        st.caption("👆 Click any row to instantly select that stock for trading")
        scan_selection = st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        # Auto-update selected stock from row click
        if scan_selection and scan_selection.selection.rows:
            clicked_idx   = scan_selection.selection.rows[0]
            clicked_stock = full_df.iloc[clicked_idx]["Stock"]
            if clicked_stock in STOCK_NAMES:
                st.session_state["scanner_trade_stock_sel"] = clicked_stock

        st.divider()

        # ── Quick Trade Panel ─────────────────
        st.subheader("💰 Quick Trade from Scanner")
        st.caption("Click a row above to auto-select, or pick manually")

        # Determine default: row click > previous selection > first stock
        scan_default = st.session_state.get("scanner_trade_stock_sel", STOCK_NAMES[0])
        scan_default_idx = STOCK_NAMES.index(scan_default) if scan_default in STOCK_NAMES else 0

        scanner_trade_stock = st.selectbox(
            "Selected stock:",
            options=STOCK_NAMES,
            index=scan_default_idx,
            key="scanner_trade_stock",
        )
        # Keep session state in sync with dropdown
        st.session_state["scanner_trade_stock_sel"] = scanner_trade_stock

        render_quick_buy_panel(scanner_trade_stock, "scanner")
        st.divider()

        # ── Download ──────────────────────────
        st.download_button(
            label     = f"⬇️ Download Scan Results ({period_label})",
            data      = full_df.to_csv(index=False),
            file_name = f"scan_{period_label.replace(' ', '_')}.csv",
            mime      = "text/csv"
        )

    elif "scan_full_df" not in st.session_state:
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
            {"Column": "Div Yield",       "What it means": "Annual dividend yield % — useful for Long-Term bucket picks"},
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
 
            # Fetch 1y for indicators — better EMA, market structure, candlestick accuracy
            score_data = yf.download(
                tickers=score_symbol, period="1y",
                interval="1d", progress=False
            )
            score_data.columns = [col[0] for col in score_data.columns]
            score_data = score_data.dropna(subset=["Close"])
 
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
            with st.spinner(f"Analysing volume for {score_stock}..."):
                volume_result      = get_volume_analysis(score_data.copy())
                volume_score_value = volume_result["volume_score"]
            with st.spinner(f"Analysing market structure for {score_stock}..."):
                ms_result      = get_market_structure_analysis(score_stock, score_data.copy())
                ms_score_value = ms_result["market_structure_score"]
            with st.spinner(f"Analysing candlestick patterns for {score_stock}..."):
                from strategies.candlestick_engine import get_candlestick_analysis
                candle_result      = get_candlestick_analysis(score_stock, score_data.copy(), regime=score_regime)
                candle_score_value = candle_result["candlestick_score"]
            score_result = build_composite_score(
                stock_name=score_stock, latest_close=s_close,
                ma20=s_ma20, rsi=s_rsi, ema9=s_ema9, ema21=s_ema21,
                macd=s_macd, macd_signal=s_msig, macd_hist=s_mhist,
                bb_pct=s_bbpct, bb_signal=s_bb_sig,
                combined_votes=s_votes,
                combined_weighted_score=score_combined["Score"],
                regime=score_regime, rs_score=None,
                fundamental_score=fund_score_value,
                sentiment_score=sentiment_score_value,
                volume_score=volume_score_value,
                candlestick_score=candle_score_value,
                market_structure_score=ms_score_value,
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
                "Trend":          "16%",
                "Momentum":       "12%",
                "Volatility":     "7%",
                "Signal":         "10%",
                "Regime":         "10%",
                "Rel. Strength":  "4%",
                "Fundamental":    "8%",
                "Sentiment":      "7%",
                "Volume":         "10%",
                "Candlestick":    "8%",
                "Mkt Structure":  "8%",
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
            div_yield = fund_data.get("dividend_yield")
        
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

            # ── Dividend yield — shown separately as it's key for Long-Term holds ──
            st.divider()
            st.caption("💰 Dividend Information (Important for Long-Term & Swing Bucket Holders)")
            dv1, dv2, dv3 = st.columns(3)
            dv1.metric(
                "Dividend Yield",
                f"{div_yield:.2f}%" if div_yield is not None else "N/A",
                help=(
                    "Annual dividend as % of current price. "
                    "For Long-Term holds, this is EXTRA income on top of price gains. "
                    "ITC, Coal India etc. typically pay 3–6% dividend yield."
                )
            )
            dv2.metric(
                "Dividend in ₹ per ₹1L invested",
                f"₹{round(div_yield * 1000, 0):.0f}/yr" if div_yield is not None else "N/A",
                help="Approximate annual dividend received if you invest ₹1,00,000 in this stock."
            )

            if div_yield is not None:
                if div_yield >= 3:
                    dv3.success(f"HIGH dividend yield — adds {div_yield:.1f}% annual income on top of price gain")
                elif div_yield >= 1:
                    dv3.info(f"MODERATE dividend yield — useful bonus for long-term hold")
                else:
                    dv3.caption(f"LOW dividend yield — this stock returns value via price growth, not dividends")
            else:
                dv3.caption("Dividend data unavailable for this stock")

            st.caption(
                "⚠️ **Paper trading note:** Dividends are NOT automatically credited in this paper trading system. "
                "They are shown here as information only. In real trading via Zerodha, dividends are credited "
                "to your bank account automatically on the ex-dividend date."
            )
        
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
        # VOLUME INTELLIGENCE SECTION — M27
        # ════════════════════════════════════════
        st.subheader("📊 Volume Intelligence")
        st.caption("Does volume confirm this price move? Volume without confirmation = weak signal.")

        vol_score_v    = volume_result.get("volume_score",    50)
        vol_label      = volume_result.get("volume_label",    "N/A")
        vol_trend      = volume_result.get("volume_trend",    "N/A")
        obv_label      = volume_result.get("obv_label",       "N/A")
        cmf_label      = volume_result.get("cmf_label",       "N/A")
        cmf_val        = volume_result.get("cmf",             None)
        breakout_sig   = volume_result.get("breakout_signal", "N/A")
        interpretation = volume_result.get("interpretation",  "N/A")
        curr_vol       = volume_result.get("current_volume",  0)
        avg_vol        = volume_result.get("avg_volume",      0)
        vol_ratio      = volume_result.get("volume_ratio",    None)

        # ── Volume score banner ───────────────────
        if vol_score_v >= 70:
            st.success(f"### Volume Score: {vol_score_v}/100 — Volume CONFIRMS the move ✅")
        elif vol_score_v >= 50:
            st.info(f"### Volume Score: {vol_score_v}/100 — Volume is neutral")
        else:
            st.warning(f"### Volume Score: {vol_score_v}/100 — Volume does NOT confirm ⚠️")

        st.caption(interpretation)
        st.write("")

        # ── Volume metrics ────────────────────────
        def _fmt_vol(v):
            try:
                v = int(v)
                if v >= 10_000_000: return f"{round(v/10_000_000,2)} Cr"
                if v >= 100_000:    return f"{round(v/100_000,2)} L"
                return f"{v:,}"
            except Exception:
                return "N/A"

        vm1, vm2, vm3, vm4 = st.columns(4)
        vm1.metric("Today's Volume",  _fmt_vol(curr_vol),
                   help="Raw volume traded today")
        vm2.metric("20D Avg Volume",  _fmt_vol(avg_vol),
                   help="Normal volume baseline for this stock")
        vm3.metric("vs Average",      vol_label,
                   help="Today's volume as a multiple of 20-day average")
        vm4.metric("Volume Score",    f"{vol_score_v}/100")

        vm5, vm6, vm7, vm8 = st.columns(4)
        vm5.metric("OBV Trend",       obv_label,
                   help="On-Balance Volume: rising = accumulation, falling = distribution")
        vm6.metric("CMF",             f"{cmf_val}" if cmf_val is not None else "N/A",
                   help="Chaikin Money Flow: +0.25 = strong buy pressure, -0.25 = strong sell")
        vm7.metric("CMF Signal",      cmf_label)
        vm8.metric("Breakout Signal", breakout_sig,
                   help="Is today's price move confirmed by volume?")

        st.write("")

        # ── Volume trend direction ─────────────────
        if vol_trend and vol_trend != "N/A":
            if "RISING" in vol_trend:
                st.success(f"📈 Volume Trend: **{vol_trend}** — more participants joining")
            elif "FALLING" in vol_trend:
                st.warning(f"📉 Volume Trend: **{vol_trend}** — participation fading")
            else:
                st.info(f"↔️ Volume Trend: **{vol_trend}**")

        # ── Volume charts ────────────────────────
        with st.expander("📈 View Volume Charts"):
            vol_df = volume_result.get("enriched_data", pd.DataFrame())
            if not vol_df.empty and "Volume" in vol_df.columns:
                st.caption("Volume vs 20-Day Average Volume (last 60 days)")
                chart_df = vol_df[["Volume"]].dropna().tail(60)
                st.bar_chart(chart_df, use_container_width=True)

                if "Volume_MA" in vol_df.columns:
                    ma_chart = vol_df[["Volume_MA"]].dropna().tail(60)
                    st.line_chart(ma_chart, use_container_width=True)

            if not vol_df.empty and "OBV" in vol_df.columns:
                st.caption("On-Balance Volume — rising = smart money buying")
                obv_chart = vol_df[["OBV"]].dropna().tail(60)
                st.line_chart(obv_chart, use_container_width=True)

            if not vol_df.empty and "CMF" in vol_df.columns:
                st.caption("Chaikin Money Flow — above 0 = buying pressure")
                cmf_chart = vol_df[["CMF"]].dropna().tail(60)
                st.line_chart(cmf_chart, use_container_width=True)

        st.divider()

        # ════════════════════════════════════════
        # MARKET STRUCTURE SECTION — M29
        # ════════════════════════════════════════
        st.subheader("🏗️ Market Structure Analysis")
        st.caption("Price structure — where is this stock in its journey? Higher Highs, Support/Resistance, Breakouts.")

        ms_score_display = ms_result["market_structure_score"]
        ms_trend_display = ms_result["trend_state"]

        # Score banner
        if ms_score_display >= 70:
            st.success(f"### Structure Score: {ms_score_display}/100 — Bullish Structure ✅")
        elif ms_score_display >= 50:
            st.info(f"### Structure Score: {ms_score_display}/100 — Neutral Structure")
        else:
            st.warning(f"### Structure Score: {ms_score_display}/100 — Weak/Bearish Structure ⚠️")

        st.caption(ms_result["summary"])
        st.write("")

        # Core metrics row
        mm1, mm2, mm3, mm4, mm5 = st.columns(5)
        mm1.metric("Trend State",  ms_trend_display)
        mm2.metric("HH / HL",      f"{ms_result['hh_count']} / {ms_result['hl_count']}",
                   help="Higher Highs / Higher Lows — bullish if both > 0")
        mm3.metric("LH / LL",      f"{ms_result['lh_count']} / {ms_result['ll_count']}",
                   help="Lower Highs / Lower Lows — bearish if both > 0")
        mm4.metric("EMA20",        f"₹{ms_result.get('ema20', 'N/A')}",
                   help="20-day EMA — price above = bullish")
        mm5.metric("EMA50",        f"₹{ms_result.get('ema50', 'N/A')}",
                   help="50-day EMA — price above = medium-term bullish")

        st.write("")

        # Support / Resistance
        sr1, sr2 = st.columns(2)
        with sr1:
            st.caption("🟢 Nearest Support")
            sup = ms_result.get("nearest_support")
            if sup:
                st.metric(
                    f"₹{sup['price']:.2f}",
                    f"{sup['touches']} touch(es)",
                    help="Price level where buyers have stepped in before"
                )
                latest_c = float(score_data["Close"].iloc[-1])
                pct_away = round((latest_c - sup["price"]) / latest_c * 100, 1)
                st.caption(f"Price is {pct_away}% above this support")
            else:
                st.info("No clear support zone identified in recent data")

        with sr2:
            st.caption("🔴 Nearest Resistance")
            res = ms_result.get("nearest_resistance")
            if res:
                st.metric(
                    f"₹{res['price']:.2f}",
                    f"{res['touches']} touch(es)",
                    help="Price level where sellers have emerged before"
                )
                latest_c  = float(score_data["Close"].iloc[-1])
                pct_away  = round((res["price"] - latest_c) / latest_c * 100, 1)
                st.caption(f"Price is {pct_away}% below this resistance")
            else:
                st.info("No clear resistance zone identified in recent data")

        st.write("")

        # Breakout / Breakdown / Consolidation / Squeeze row
        bs1, bs2, bs3, bs4 = st.columns(4)

        breakout_info = ms_result.get("breakout", {})
        breakdown_info= ms_result.get("breakdown", {})
        consol_info   = ms_result.get("consolidation", {})
        squeeze_info  = ms_result.get("squeeze", {})

        with bs1:
            if breakout_info.get("breakout"):
                st.success(
                    f"🚀 **BREAKOUT**\n\n"
                    f"{breakout_info.get('strength', '')}\n\n"
                    f"+{breakout_info.get('distance_pct', 0)}% above resistance\n\n"
                    f"Vol: {breakout_info.get('vol_ratio', '?')}x avg"
                )
            else:
                st.info("No Breakout")

        with bs2:
            if breakdown_info.get("breakdown"):
                st.error(
                    f"🔻 **BREAKDOWN**\n\n"
                    f"{breakdown_info.get('strength', '')}\n\n"
                    f"-{breakdown_info.get('distance_pct', 0)}% below support"
                )
            else:
                st.info("No Breakdown")

        with bs3:
            if consol_info.get("consolidation"):
                st.warning(
                    f"📦 **CONSOLIDATION**\n\n"
                    f"Compression: {consol_info.get('compression_score', 0)}/100\n\n"
                    f"Range: {consol_info.get('range_pct', '?')}%"
                )
            else:
                st.info("No Consolidation")

        with bs4:
            if squeeze_info.get("squeeze_active"):
                st.warning(
                    f"⚡ **SQUEEZE ACTIVE**\n\n"
                    f"{squeeze_info.get('squeeze_strength', '')}\n\n"
                    f"BB Width in bottom {squeeze_info.get('bb_width_percentile', '?')}%"
                )
            else:
                st.info(f"No Squeeze\n\nBB Width: {squeeze_info.get('bb_width_percentile', '?')}th pct")

        # Swing points table
        with st.expander("📋 Recent Swing Highs & Lows"):
            swing_cols = st.columns(2)
            with swing_cols[0]:
                st.caption("Swing Highs (recent first)")
                sh_list = ms_result.get("swing_highs", [])
                if sh_list:
                    st.dataframe(
                        pd.DataFrame(sh_list)[["price", "date"]].rename(
                            columns={"price": "High ₹", "date": "Date"}
                        ),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("No swing highs found")

            with swing_cols[1]:
                st.caption("Swing Lows (recent first)")
                sl_list = ms_result.get("swing_lows", [])
                if sl_list:
                    st.dataframe(
                        pd.DataFrame(sl_list)[["price", "date"]].rename(
                            columns={"price": "Low ₹", "date": "Date"}
                        ),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("No swing lows found")

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
        render_quick_buy_panel(
            stock_name      = score_stock,
            tab_key_prefix  = f"score_{score_stock}",
            composite_score = composite,
            combined_signal = final_signal,
            buy_votes       = explanation["buy_votes"],
            regime          = score_regime,
        )
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
    st.caption("All trades from the Bucket Portfolio system (Long-Term, Swing, Intraday)")
    from portfolio.capital_engine import load_bucket_trades
    trades_df = load_bucket_trades()
    if trades_df.empty:
        st.info("No trades yet! Use the Portfolio Buckets tab or Dashboard to place trades.")
    else:
        def _color_trade_action(val):
            if val == "BUY":  return "color: green; font-weight: bold"
            if val == "SELL": return "color: red; font-weight: bold"
            return ""
        def _color_trade_pnl(val):
            try:
                f = float(val)
                if f > 0: return "color: green"
                if f < 0: return "color: red"
            except Exception:
                pass
            return ""
        display_cols = [c for c in ["Timestamp","Bucket","Action","Stock","Price","Quantity","Value","PNL"] if c in trades_df.columns]
        st.dataframe(
            trades_df[display_cols].sort_values('Timestamp', ascending=False).style
                .map(_color_trade_action, subset=["Action"] if "Action" in display_cols else [])
                .map(_color_trade_pnl,    subset=["PNL"]    if "PNL"    in display_cols else []),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            label="⬇️ Download Trade History",
            data=trades_df[display_cols].to_csv(index=False),
            file_name="bucket_trades.csv", mime="text/csv"
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

# ════════════════════════════════════════════════
# TAB 9: PORTFOLIO BUCKETS — Milestone 24
# ════════════════════════════════════════════════
with tab9:
 
    st.title("🪣 Portfolio Buckets — Capital Allocation Engine")
    st.caption("Three independent capital pools — each with its own strategy, risk rules, and performance tracking")
    st.divider()
 
    # ── Portfolio-level headline metrics ──────────
    totals = get_portfolio_totals()
 
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric(
        "Total Capital",
        f"₹{totals['total_starting']:,.0f}"
    )
    t2.metric(
        "Available Cash",
        f"₹{totals['total_available']:,.0f}",
    )
    t3.metric(
        "Deployed",
        f"₹{totals['total_deployed']:,.0f}",
    )
    t4.metric(
        "Total P&L",
        f"₹{totals['total_pnl']:+,.0f}",
        delta=f"{totals['total_return_pct']:+.2f}%"
    )
    t5.metric(
        "Overall Win Rate",
        f"{totals['overall_win_rate']}%",
        delta=f"{totals['total_trades']} trades"
    )
 
    st.divider()

    # ── Portfolio Risk Dashboard ──────────────────
    st.subheader("🛡️ Portfolio Risk Status")
    with st.spinner("Running risk checks..."):
        from risk.portfolio_risk import (
            get_risk_dashboard_data,
            format_risk_level,
        )
        rd = get_risk_dashboard_data(regime=regime)
        ps = rd["portfolio_summary"]

    risk_color = {
        "LOW":      "normal", "NORMAL":   "normal",
        "ELEVATED": "off",    "HIGH":     "inverse",
        "CRITICAL": "inverse",
    }

    rc1, rc2, rc3, rc4, rc5 = st.columns(5)
    rc1.metric("Risk Level",       format_risk_level(ps["risk_level"]))
    rc2.metric("Deployed",         f"{ps['capital_deployed_pct']}%")
    rc3.metric("Top Sector",       f"{ps['largest_sector_name']} {ps['largest_sector_pct']}%")
    rc4.metric("Open Positions",   ps["open_positions_count"])
    rc5.metric("Trading Allowed",  "✅ YES" if ps["trading_allowed"] else "🛑 NO")

    if ps["warnings"]:
        for w in ps["warnings"]:
            st.warning(w)
    else:
        st.success("✅ All portfolio risk checks passed — normal trading conditions")

    st.divider()

 
    # ── Bucket summary cards ──────────────────────
    st.subheader("🪣 Bucket Overview")
    st.caption("Each bucket is completely independent — different capital, strategy, and rules")
 
    bucket_summary = get_bucket_summary()
 
    if bucket_summary:
        # Display as three side-by-side cards
        cols = st.columns(3)
        bucket_colors = {
            "Long-Term": "🟢",
            "Swing":     "🔵",
            "Intraday":  "🟠",
        }
 
        for i, bucket_data in enumerate(bucket_summary):
            with cols[i]:
                bname  = bucket_data["Bucket"]
                cfg    = BUCKET_CONFIG[bname]
                icon   = bucket_colors.get(bname, "⚪")
                pnl_val= bucket_data["Total P&L ₹"]
                pnl_sign = "+" if pnl_val >= 0 else ""
 
                st.markdown(f"### {icon} {bname}")
                st.caption(cfg["description"])
 
                # Capital bar
                avail   = bucket_data["Available ₹"]
                deployed= bucket_data["Deployed ₹"]
                start   = bucket_data["Starting ₹"]
                util_pct= round(deployed / start * 100) if start > 0 else 0
 
                st.progress(
                    min(util_pct / 100, 1.0),
                    text=f"Deployed: {util_pct}% of ₹{start:,.0f}"
                )
 
                m1, m2 = st.columns(2)
                m1.metric("Available",   f"₹{avail:,.0f}")
                m2.metric("Deployed",    f"₹{deployed:,.0f}")
 
                m3, m4 = st.columns(2)
                m3.metric("P&L",         f"₹{pnl_sign}{pnl_val:,.0f}")
                m4.metric("Return",      bucket_data["Return %"])
 
                m5, m6 = st.columns(2)
                m5.metric("Win Rate",    bucket_data["Win Rate"])
                m6.metric("Positions",   bucket_data["Open Positions"])
 
                st.caption(
                    f"Min score: {cfg['min_score']}/100 | "
                    f"Max per stock: {int(cfg['max_position_pct']*100)}% | "
                    f"Hold: {cfg['min_holding_days']}–{cfg['max_holding_days']} days"
                )
 
    st.divider()
 
    # ── Bucket summary table ──────────────────────
    st.subheader("📋 Bucket Comparison Table")
    if bucket_summary:
        display_df = pd.DataFrame(bucket_summary)[[
            "Bucket", "Style", "Starting ₹", "Available ₹",
            "Deployed ₹", "Utilization", "Open Positions",
            "Total P&L ₹", "Return %", "Win Rate", "Total Trades"
        ]]
 
        def color_pnl_bucket(val):
            try:
                f = float(str(val).replace("₹","").replace(",",""))
                if f > 0: return "color: green; font-weight: bold"
                if f < 0: return "color: red; font-weight: bold"
            except Exception:
                pass
            return ""
 
        def color_return(val):
            s = str(val)
            if s.startswith("+"): return "color: green"
            if s.startswith("-"): return "color: red"
            return ""
 
        st.dataframe(
            display_df.style
                .map(color_pnl_bucket, subset=["Total P&L ₹"])
                .map(color_return,     subset=["Return %"]),
            use_container_width=True,
            hide_index=True
        )
 
    st.divider()
 
    # ── Manual bucket trade panel ─────────────────
    st.subheader("💰 Manual Bucket Trade")
    st.caption(
        "Trade directly from a specific bucket. "
        "In future milestones this will happen automatically — "
        "for now you can test it manually."
    )
 
    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        trade_bucket = st.selectbox(
            "Select Bucket:",
            options=list(BUCKET_CONFIG.keys()),
            key="bucket_trade_bucket"
        )
    with tc2:
        trade_stock = st.selectbox(
            "Select Stock:",
            options=STOCK_NAMES,
            key="bucket_trade_stock"
        )
    with tc3:
        # Show current price for selected stock
        try:
            bt_symbol = WATCHLIST.get(trade_stock)
            bt_data   = fetch_stock_data(bt_symbol)
            bt_price  = round(float(bt_data['Close'].iloc[-1]), 2)
        except Exception:
            bt_price  = 0.0
 
        st.metric("Current Price", f"₹{bt_price}")
 
    # Show bucket constraints as guidance
    if trade_bucket and bt_price > 0:
        cfg         = BUCKET_CONFIG[trade_bucket]
        avail_cash  = get_bucket_available_cash(trade_bucket)
        can_add, open_c, max_p = check_position_limit(trade_bucket)
 
        gc1, gc2, gc3, gc4 = st.columns(4)
        gc1.metric("Available in Bucket", f"₹{avail_cash:,.0f}")
        gc2.metric("Open Positions",      f"{open_c}/{max_p}")
        gc3.metric("Min Score Required",  f"{cfg['min_score']}/100")
        gc4.metric("Max Per Stock",       f"{int(cfg['max_position_pct']*100)}%")
 
        if not can_add:
            st.error(f"🛑 {trade_bucket} bucket is at max positions ({open_c}/{max_p}). Sell something first.")
 
    st.write("")
    bc1, bc2 = st.columns(2)
 
    with bc1:
        if st.button(
            f"🟢 BUY {trade_stock} from {trade_bucket} Bucket",
            use_container_width=True,
            key="bucket_buy_btn"
        ):
            if bt_price > 0:
                result = bucket_buy(
                    bucket_name     = trade_bucket,
                    stock_name      = trade_stock,
                    price           = bt_price,
                    composite_score = None   # No score check for manual trades
                )
                if result["status"] == "EXECUTED":
                    st.success(
                        f"✅ Bought {result['quantity']} shares of {trade_stock} "
                        f"@ ₹{result['price']} from {trade_bucket} bucket | "
                        f"Cash left: ₹{result['cash_left']:,.0f}"
                    )
                else:
                    st.error(f"🛑 Rejected: {result['reason']}")
            else:
                st.error("Could not fetch price. Try again.")
 
    with bc2:
        if st.button(
            f"🔴 SELL {trade_stock} from {trade_bucket} Bucket",
            use_container_width=True,
            key="bucket_sell_btn"
        ):
            if bt_price > 0:
                result = bucket_sell(
                    bucket_name = trade_bucket,
                    stock_name  = trade_stock,
                    price       = bt_price,
                )
                if result["status"] == "EXECUTED":
                    pnl_icon = "✅" if result["pnl"] >= 0 else "❌"
                    st.success(
                        f"{pnl_icon} Sold {result['quantity']} shares of {trade_stock} "
                        f"@ ₹{result['price']} | "
                        f"P&L: ₹{result['pnl']:+,.0f} ({result['pnl_pct']:+.1f}%) | "
                        f"Cash now: ₹{result['cash_now']:,.0f}"
                    )
                else:
                    st.error(f"🛑 Rejected: {result['reason']}")
            else:
                st.error("Could not fetch price. Try again.")
 
    st.divider()
 
    # ── Open positions per bucket ─────────────────
    st.subheader("📂 Open Positions by Bucket")
    any_open = False
    for bname in BUCKET_CONFIG.keys():
        open_stocks = get_open_positions_by_bucket(bname)
        if open_stocks:
            any_open = True
            icon = bucket_colors.get(bname, "⚪")
            st.markdown(f"**{icon} {bname}:** {', '.join(open_stocks)}")
 
    if not any_open:
        st.info("No open positions in any bucket yet. Use the trade panel above to test.")
 
    st.divider()
 
    # ── Bucket trade history ──────────────────────
    st.subheader("📋 Bucket Trade History")
 
    hist_bucket = st.selectbox(
        "Filter by bucket:",
        options=["All Buckets"] + list(BUCKET_CONFIG.keys()),
        key="hist_bucket_filter"
    )
 
    history_df = get_bucket_trade_history(
        None if hist_bucket == "All Buckets" else hist_bucket
    )
 
    if history_df.empty:
        st.info("No bucket trades yet. Use the trade panel above to start.")
    else:
        def color_action(val):
            if val == "BUY":  return "color: green"
            if val == "SELL": return "color: red"
            return ""
 
        def color_pnl_hist(val):
            try:
                f = float(val)
                if f > 0: return "color: green"
                if f < 0: return "color: red"
            except Exception:
                pass
            return ""
 
        st.dataframe(
            history_df.sort_values("Timestamp", ascending=False)
                .style
                .map(color_action,   subset=["Action"])
                .map(color_pnl_hist, subset=["PNL"]),
            use_container_width=True,
            hide_index=True
        )
 
        st.download_button(
            label     = "⬇️ Download Bucket Trade History",
            data      = history_df.to_csv(index=False),
            file_name = "bucket_trades.csv",
            mime      = "text/csv"
        )
 
    st.divider()
 
    # ── Bucket configuration reference ───────────
    with st.expander("⚙️ Bucket Configuration Reference"):
        st.caption("These settings control how each bucket behaves. Edit capital_engine.py to change them.")
        cfg_rows = []
        for bname, cfg in BUCKET_CONFIG.items():
            cfg_rows.append({
                "Bucket":           bname,
                "Allocation":       f"{int(cfg['allocation_pct']*100)}% = ₹{TOTAL_CAPITAL*cfg['allocation_pct']:,.0f}",
                "Max Positions":    cfg["max_positions"],
                "Max Per Stock":    f"{int(cfg['max_position_pct']*100)}%",
                "Min Score":        f"{cfg['min_score']}/100",
                "Hold Period":      f"{cfg['min_holding_days']}–{cfg['max_holding_days']} days",
                "Strategy Style":   cfg["strategy_style"],
            })
        st.dataframe(pd.DataFrame(cfg_rows), use_container_width=True, hide_index=True)
 
    # ── Danger zone — reset ───────────────────────
    st.divider()
    with st.expander("⚠️ Danger Zone — Reset All Buckets"):
        st.warning(
            "This will reset ALL bucket capital and trade history back to starting values. "
            "This cannot be undone. Use only when starting fresh."
        )
        if st.button("🗑️ Reset All Bucket Data", key="reset_buckets"):
            reset_bucket_state()
            st.success("✅ All buckets reset to starting capital. Refresh the page.")

# ════════════════════════════════════════════════
# TAB 10: POSITION LIFECYCLE — Milestone 25A
# ════════════════════════════════════════════════
with tab10:

    st.title("🔄 Position Lifecycle Manager")
    st.caption("Track every position through its full journey — from watchlist to exit")
    st.divider()

    # Import lifecycle functions
    from portfolio.position_manager import (
        get_lifecycle_summary,
        get_lifecycle_display_df,
        get_full_history,
        get_state_color,
        expire_cooldowns,
        is_in_cooldown,
    )

    # ── Expire old cooldowns automatically ────────
    expired = expire_cooldowns()
    if expired:
        st.info(f"✅ Cooldown expired for: {', '.join(expired)} — back on watchlist")

    # ── Headline metrics ──────────────────────────
    summary = get_lifecycle_summary()

    lc1, lc2, lc3, lc4, lc5 = st.columns(5)
    lc1.metric("Live Positions",  summary["live"],
               help="ENTERED + HOLDING + TRAILING + PARTIAL_EXIT")
    lc2.metric("Watchlist",       summary["watchlist"],
               help="Being monitored — not yet entered")
    lc3.metric("Ready to Enter",  summary["ready"],
               help="Signal fired, approved — enter on next tick")
    lc4.metric("In Cooldown",     summary["cooldown"],
               help="Stop loss hit — blocked from re-entry")
    lc5.metric("Exited Today",    summary["exited_today"])

    st.divider()

    # ── Backfill older positions ──────────────────
    from portfolio.position_manager import backfill_lifecycle_from_trades
    with st.expander("⚙️ First Time Setup — Import Existing Positions"):
        st.caption(
            "If you had open positions before the lifecycle system was added, "
            "click below to import them. Safe to run multiple times — skips duplicates."
        )
        if st.button("📥 Import Existing Open Positions", key="backfill_lifecycle"):
            backfilled = backfill_lifecycle_from_trades()
            if backfilled:
                st.success(f"✅ Imported {len(backfilled)} position(s): {', '.join(backfilled)}")
                st.rerun()
            else:
                st.info("Nothing to import — all open positions already have lifecycle records.")
    
    # ── Live positions table ──────────────────────
    st.subheader("📊 Active Positions")
    st.caption("All positions currently in the system (not yet exited)")

    display_df = get_lifecycle_display_df()

    if display_df.empty:
        st.info(
            "No active lifecycle positions yet. "
            "Every BUY you make through the bucket system will appear here automatically."
        )
    else:
        def color_state(val):
            return get_state_color(val)

        def color_pnl_lc(val):
            s = str(val)
            if s.startswith("+") or (s.replace(".","").replace("%","").lstrip("-").isdigit() and not s.startswith("-")):
                return "color: green"
            if s.startswith("-"):
                return "color: red"
            return ""

        styled = display_df.style
        if "State" in display_df.columns:
            styled = styled.map(color_state, subset=["State"])
        if "P&L %" in display_df.columns:
            styled = styled.map(color_pnl_lc, subset=["P&L %"])

        st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()

    # ── 25B: Position Monitor ─────────────────────
    st.subheader("🔄 Position Monitor")
    st.caption(
        "Fetch latest prices for all live positions and check for "
        "stop loss hits, trailing stop triggers, and profit targets."
    )

    from portfolio.position_manager import (
        get_live_positions,
        update_position_price,
    )

    if st.button("🔄 Refresh All Live Positions", use_container_width=True, key="refresh_lifecycle"):

        live_df = get_live_positions()

        if live_df.empty:
            st.info("No live positions to monitor right now.")
        else:
            st.write(f"Checking {len(live_df)} live position(s)...")
            action_rows = []

            for _, pos in live_df.iterrows():
                stock     = str(pos["stock"])
                pos_id    = str(pos["position_id"])
                bucket    = str(pos["bucket"])
                buy_price = float(pos["buy_price"]) if pos["buy_price"] not in ("", "nan") else 0

                # Fetch latest price
                try:
                    sym        = WATCHLIST.get(stock, stock + ".NS")
                    price_data = fetch_stock_data(sym)
                    curr_price = round(float(price_data['Close'].iloc[-1]), 2)
                except Exception:
                    curr_price = buy_price   # fallback to buy price

                # Run the lifecycle update
                result = update_position_price(pos_id, curr_price)

                action     = result.get("action",   "HOLD")
                pnl_pct    = result.get("pnl_pct",  0)
                trail_stop = result.get("trail_stop", "—")
                reason     = result.get("reason",   "")
                new_state  = result.get("state",    "—")
                days_held  = result.get("days_held", 0)

                action_rows.append({
                    "Stock":       stock,
                    "Bucket":      bucket,
                    "Buy ₹":       f"₹{buy_price}",
                    "Now ₹":       f"₹{curr_price}",
                    "P&L %":       f"{pnl_pct:+.2f}%",
                    "State":       new_state,
                    "Action":      action,
                    "Trail Stop":  f"₹{trail_stop}" if isinstance(trail_stop, float) else trail_stop,
                    "Days Held":   days_held,
                    "Reason":      reason,
                })

            if action_rows:
                results_df = pd.DataFrame(action_rows)

                # Color the Action column
                def color_action_lc(val):
                    if val == "SELL_STOP":    return "color: red;    font-weight: bold"
                    if val == "SELL_TARGET":  return "color: green;  font-weight: bold"
                    if val == "SELL_TRAIL":   return "color: orange; font-weight: bold"
                    if val == "TRAIL_ACTIVATED": return "color: cyan"
                    if val == "PARTIAL_EXIT": return "color: orange"
                    return "color: gray"

                def color_pnl_monitor(val):
                    if str(val).startswith("+"): return "color: green"
                    if str(val).startswith("-"): return "color: red"
                    return ""

                st.dataframe(
                    results_df.style
                        .map(color_action_lc,   subset=["Action"])
                        .map(color_pnl_monitor, subset=["P&L %"]),
                    use_container_width=True,
                    hide_index=True
                )

                # ── Action alerts ──────────────────
                urgent = [r for r in action_rows if r["Action"] not in ("HOLD", "NO_ACTION")]
                if urgent:
                    st.divider()
                    st.subheader("⚠️ Actions Required")
                    for r in urgent:
                        action = r["Action"]
                        stock  = r["Stock"]
                        bucket = r["Bucket"]
                        reason = r["Reason"]

                        if action == "SELL_STOP":
                            st.error(
                                f"🛑 **{stock} ({bucket})** — SELL IMMEDIATELY\n\n"
                                f"{reason}"
                            )
                        elif action == "SELL_TARGET":
                            st.success(
                                f"🎯 **{stock} ({bucket})** — TARGET HIT — Consider selling\n\n"
                                f"{reason}"
                            )
                        elif action == "SELL_TRAIL":
                            st.warning(
                                f"📉 **{stock} ({bucket})** — TRAILING STOP HIT — Consider selling\n\n"
                                f"{reason}"
                            )
                        elif action == "TRAIL_ACTIVATED":
                            st.info(
                                f"🔔 **{stock} ({bucket})** — TRAILING STOP ACTIVATED\n\n"
                                f"{reason}"
                            )
                        elif action == "PARTIAL_EXIT":
                            st.warning(
                                f"📊 **{stock} ({bucket})** — PARTIAL EXIT SUGGESTED — Sell 50%\n\n"
                                f"{reason}"
                            )
                else:
                    st.success("✅ All positions healthy — no urgent actions needed")

    st.divider()
    st.caption(
        "💡 In Milestone 26 (Autonomous Execution Loop), "
        "this refresh will run automatically every 15 minutes during market hours."
    )
    st.divider()

    # ── State guide ───────────────────────────────
    st.subheader("📖 Lifecycle State Guide")
    state_guide = [
        {"State": "WATCHLIST",    "Meaning": "Stock is being monitored, signal not yet fired",
         "Next": "READY when signal fires"},
        {"State": "READY",        "Meaning": "Signal fired, score approved, waiting to enter",
         "Next": "ENTERED on next tick"},
        {"State": "ENTERED",      "Meaning": "BUY just executed, position is live",
         "Next": "HOLDING after first price update"},
        {"State": "HOLDING",      "Meaning": "Normal hold — within stop/target range",
         "Next": "TRAILING (gain ≥6%) or EXITED"},
        {"State": "TRAILING",     "Meaning": "Profit locked — stop now trails peak price",
         "Next": "PARTIAL_EXIT or EXITED"},
        {"State": "PARTIAL_EXIT", "Meaning": "50% profit booked, rest still running",
         "Next": "EXITED when stop or target hit"},
        {"State": "EXITED",       "Meaning": "Position fully closed",
         "Next": "COOLDOWN (if stop loss) or WATCHLIST"},
        {"State": "COOLDOWN",     "Meaning": "Stop loss hit — blocked from re-entry for 3 days",
         "Next": "WATCHLIST after cooldown expires"},
        {"State": "REJECTED",     "Meaning": "Signal blocked — score too low, bear market, etc.",
         "Next": "WATCHLIST to re-evaluate"},
    ]
    st.dataframe(
        pd.DataFrame(state_guide),
        use_container_width=True, hide_index=True
    )

    st.divider()

    # ── Full history ──────────────────────────────
    st.subheader("📋 Full Position History")
    st.caption("All positions including exited ones — complete audit trail")

    show_exited  = st.checkbox("Include exited positions", value=True)
    show_rejected= st.checkbox("Include rejected positions", value=False)

    history_df = get_full_history(
        include_exited=show_exited,
        include_rejected=show_rejected
    )

    if history_df.empty:
        st.info("No history yet.")
    else:
        # Show key columns only
        hist_cols = [
            "stock", "bucket", "state",
            "buy_price", "exit_price", "current_pnl_pct",
            "exit_reason", "days_held", "last_updated"
        ]
        existing = [c for c in hist_cols if c in history_df.columns]
        st.dataframe(
            history_df[existing].style.map(
                lambda v: get_state_color(v) if v in {
                    "WATCHLIST","READY","ENTERED","HOLDING",
                    "TRAILING","PARTIAL_EXIT","EXITED","COOLDOWN","REJECTED"
                } else "",
                subset=["state"] if "state" in existing else []
            ),
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            label="⬇️ Download Full Lifecycle History",
            data=history_df.to_csv(index=False),
            file_name="position_lifecycle_history.csv",
            mime="text/csv"
        )

    st.divider()

    # ── Cooldown checker ──────────────────────────
    st.subheader("🔒 Cooldown Checker")
    st.caption("Check if a stock is blocked from re-entry after a stop loss")

    cd_col1, cd_col2 = st.columns(2)
    with cd_col1:
        cd_stock  = st.selectbox("Stock:", options=STOCK_NAMES, key="cd_stock")
    with cd_col2:
        cd_bucket = st.selectbox("Bucket:", options=list(BUCKET_CONFIG.keys()), key="cd_bucket")

    in_cd, until = is_in_cooldown(cd_stock, cd_bucket)
    if in_cd:
        st.error(f"🔒 {cd_stock} is in COOLDOWN for {cd_bucket} bucket until **{until}**")
    else:
        st.success(f"✅ {cd_stock} is NOT in cooldown for {cd_bucket} — free to trade")


# ════════════════════════════════════════════════
# TAB 11: AUTO PILOT — Autonomous Execution Loop
# ════════════════════════════════════════════════
with tab11:
 
    st.title("🤖 Auto Pilot — Autonomous Execution Loop")
    st.caption(
        "The loop watches all stocks during market hours, finds opportunities, "
        "monitors positions, and places paper trades automatically."
    )
    st.divider()

    # ── Runner page banner ────────────────────────
    # The autorefresh and execution loop have been moved to
    # pages/autopilot_runner.py — a dedicated second page.
    # This keeps the main dashboard completely free of interruptions.
    st.info(
        "### 🤖 To enable autonomous trading, open the Auto Pilot Runner page.\n\n"
        "Look in the **sidebar** (top-left ☰) for **autopilot runner** and open it "
        "in a **second browser tab**. Leave that tab open during market hours. "
        "This main dashboard will never be interrupted."
    )

    # ── Market status banner ──────────────────────
    mkt_status = get_market_status()
    if mkt_status["open"]:
        st.success(f"🟢 **Market OPEN** — {mkt_status['time']}")
    else:
        st.warning(f"⚫ **{mkt_status['status']}** — {mkt_status['time']}")
    st.caption("NSE Market Hours: 9:15 AM – 3:30 PM IST (Mon–Fri) | All times in IST (UTC+5:30)")
 
    st.divider()
 
    # ── Load current loop state ───────────────────
    loop_state    = load_loop_state()
    loop_status   = loop_state.get("status", STATUS_STOPPED)
    last_run      = loop_state.get("last_run",        "Never")
    next_run      = loop_state.get("next_run",         "—")
    runs_today    = loop_state.get("runs_today",        0)
    buys_today    = loop_state.get("buys_today",        0)
    sells_today   = loop_state.get("sells_today",       0)
    pnl_today     = loop_state.get("pnl_today",         0.0)
    error_count   = loop_state.get("error_count",       0)
    last_error    = loop_state.get("last_error",        None)
    interval_min  = loop_state.get("interval_minutes",  15)
 
    # ── Status banner ─────────────────────────────
    if loop_status == STATUS_RUNNING:
        st.success(f"## 🟢 Loop Status: RUNNING")
    elif loop_status == STATUS_PAUSED:
        st.warning(f"## ⏸️ Loop Status: PAUSED")
    else:
        st.error(f"## ⛔ Loop Status: STOPPED")
 
    # ── Today's stats ─────────────────────────────
    lc1, lc2, lc3, lc4, lc5 = st.columns(5)
    lc1.metric("Runs Today",    runs_today)
    lc2.metric("Buys Today",    buys_today)
    lc3.metric("Sells Today",   sells_today)
    lc4.metric(
        "P&L Today",
        f"₹{pnl_today:+,.0f}",
        delta=f"{'▲' if pnl_today >= 0 else '▼'}"
    )
    lc5.metric("Errors Today",  error_count)
 
    st.caption(f"Last run: {last_run}  |  Next run: {next_run}  |  Current interval: every **{interval_min} min**")
 
    if last_error:
        st.error(f"⚠️ Last error: {last_error}")
 
    st.divider()
 
    # ── Controls ──────────────────────────────────
    st.subheader("⚙️ Loop Controls")
 
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns(4)
 
    with ctrl_col1:
        # Interval selector
        new_interval = st.selectbox(
            "Run every:",
            options=[5, 10, 15, 30, 60],
            index=[5, 10, 15, 30, 60].index(interval_min)
                if interval_min in [5, 10, 15, 30, 60] else 2,
            format_func=lambda x: f"{x} minutes",
            key="loop_interval"
        )
 
    with ctrl_col2:
        if st.button(
            "▶️ START Loop",
            use_container_width=True,
            disabled=(loop_status == STATUS_RUNNING),
            key="start_loop_btn"
        ):
            start_loop(interval_minutes=new_interval)
            st.success(f"✅ Loop started — will run every {new_interval} minutes")
            st.rerun()
 
    with ctrl_col3:
        if st.button(
            "⏸️ PAUSE Loop",
            use_container_width=True,
            disabled=(loop_status != STATUS_RUNNING),
            key="pause_loop_btn"
        ):
            pause_loop()
            st.info("⏸️ Loop paused — positions still monitored on next RUN NOW")
            st.rerun()
 
    with ctrl_col4:
        if st.button(
            "⛔ STOP Loop",
            use_container_width=True,
            disabled=(loop_status == STATUS_STOPPED),
            key="stop_loop_btn"
        ):
            stop_loop()
            st.warning("⛔ Loop stopped")
            st.rerun()
 
    st.divider()
 
    # ── Manual Run Now ────────────────────────────
    st.subheader("🚀 Manual Controls")
    st.caption(
        "Run one cycle manually — useful for testing outside market hours "
        "or triggering an immediate scan."
    )
 
    man1, man2, man3 = st.columns(3)
 
    with man1:
        if st.button(
            "🔍 RUN NOW (Live)",
            use_container_width=True,
            key="run_now_live"
        ):
            with st.spinner("Running one cycle... this takes 30-60 seconds"):
                result = run_one_cycle(force=True, scan_only=False)
            if result.get("skipped"):
                st.info(f"ℹ️ Skipped: {result['skip_reason']}")
            elif result.get("error"):
                st.error(f"❌ Error: {result['error'][:300]}")
            else:
                st.success(
                    f"✅ Cycle complete | Regime: {result['regime']} | "
                    f"Buys: {result['buys']} | Sells: {result['sells']} | "
                    f"No-trades: {result['no_trades']}"
                )
            st.rerun()
 
    with man2:
        if st.button(
            "🔬 SCAN ONLY (No Trades)",
            use_container_width=True,
            key="run_scan_only"
        ):
            with st.spinner("Scanning (no trades will be placed)..."):
                result = run_one_cycle(force=True, scan_only=True)
            st.info(
                f"Scan complete | Regime: {result.get('regime','?')} | "
                f"Decisions logged: {len(result.get('decisions', []))}"
            )
            st.rerun()
 
    with man3:
        if st.button(
            "🗑️ Clear Decision Log",
            use_container_width=True,
            key="clear_log_btn"
        ):
            clear_decision_log()
            st.info("Decision log cleared")
            st.rerun()
 
    st.divider()
 
    # ── How the loop works ────────────────────────
    st.subheader("📖 How the Loop Works")
    st.caption("Each cycle runs these steps in order:")
 
    steps = [
        {"Step": "1", "Action": "Market Hours Check",
         "Detail": "Only runs 9:15 AM – 3:30 PM IST, Mon–Fri"},
        {"Step": "2", "Action": "Expire Cooldowns",
         "Detail": "Releases stocks blocked after stop loss (after 3 days)"},
        {"Step": "3", "Action": "Fetch Market Regime",
         "Detail": "Reads NIFTY 50 to determine BULL/BEAR/SIDEWAYS"},
        {"Step": "4", "Action": "Portfolio Safety Gate",
         "Detail": "BEAR market → pause buys | Daily loss >5% → halt all"},
        {"Step": "5", "Action": "Exit Monitor",
         "Detail": "Checks all live positions — sells if stop/target/trail hit"},
        {"Step": "6", "Action": "Buy Scanner",
         "Detail": "Runs all strategies, scores every stock, buys best opportunities"},
        {"Step": "7", "Action": "Log Everything",
         "Detail": "Every decision (including NO-TRADE) logged with full reasons"},
    ]
    st.dataframe(pd.DataFrame(steps), use_container_width=True, hide_index=True)
 
    st.divider()
 
    # ── Safety rules ──────────────────────────────
    st.subheader("🛡️ Built-in Safety Rules")
 
    rules = [
        {"Rule": "Bear Market Gate",     "Action": "Zero new BUY orders in BEAR regime"},
        {"Rule": "Daily Loss Limit",     "Action": "Halt all buys if portfolio down >5% today"},
        {"Rule": "Cooldown Period",      "Action": "No re-entry for 3 days after stop loss"},
        {"Rule": "Score Gate",           "Action": "Minimum score per bucket (Long-Term=70, Swing=60, Intraday=55)"},
        {"Rule": "No Double-Buy",        "Action": "Won't buy a stock already held in same bucket"},
        {"Rule": "Position Limit",       "Action": "Max 5 open positions per bucket"},
        {"Rule": "Auto-Pause on Errors", "Action": "Loop pauses itself after 3 consecutive errors"},
        {"Rule": "Stop Loss Priority",   "Action": "Stop loss executes immediately — no override"},
    ]
    st.dataframe(pd.DataFrame(rules), use_container_width=True, hide_index=True)
 
    st.divider()
 
    # ── Decision log ──────────────────────────────
    st.subheader("📋 Decision Log")
    st.caption(
        "Every BUY, SELL, and NO-TRADE with full reasons — "
        "the audit trail of autonomous decisions"
    )
 
    decision_df = load_decision_log(max_rows=100)
 
    if decision_df.empty:
        st.info(
            "No decisions logged yet. "
            "Click **RUN NOW** above to run one cycle "
            "and see decisions here."
        )
    else:
        def color_decision(val):
            if val == "BUY":            return "color: green;  font-weight: bold"
            if val == "SELL":           return "color: orange; font-weight: bold"
            if val == "HALTED":         return "color: red;    font-weight: bold"
            if val == "NO-TRADE":       return "color: gray"
            if "PARTIAL" in str(val):   return "color: cyan"
            return ""
 
        def color_exit(val):
            if "STOP"   in str(val): return "color: red"
            if "TARGET" in str(val): return "color: green"
            if "TRAIL"  in str(val): return "color: orange"
            return ""
 
        st.dataframe(
            decision_df.style
                .map(color_decision, subset=["Decision"])
                .map(color_exit,     subset=["Exit_Reason"]),
            use_container_width=True,
            hide_index=True
        )
 
        # ── Summary counts ─────────────────────────
        total_shown = len(decision_df)
        buy_count   = len(decision_df[decision_df["Decision"] == "BUY"])
        sell_count  = len(decision_df[decision_df["Decision"] == "SELL"])
        nt_count    = len(decision_df[decision_df["Decision"] == "NO-TRADE"])
 
        st.caption(
            f"Showing last {total_shown} decisions | "
            f"BUY: {buy_count} | SELL: {sell_count} | NO-TRADE: {nt_count}"
        )
 
        st.download_button(
            label     = "⬇️ Download Decision Log",
            data      = decision_df.to_csv(index=False),
            file_name = "decision_log.csv",
            mime      = "text/csv",
        )

        st.divider()  

        # ── Orchestration Log ─────────────────────────
        st.subheader("🎯 Orchestration Log")
        st.caption(
            "Every stock the loop evaluated — bucket routing decisions, "
            "confluence scores, and rejection reasons from the Strategy Orchestrator"
        )

        from strategies.orchestrator import (
            load_orchestration_log,
            clear_orchestration_log,
            get_orchestration_stats,
        )

        orch_stats = get_orchestration_stats()
        os1, os2, os3, os4, os5 = st.columns(5)
        os1.metric("Total Evaluated", orch_stats["total"])
        os2.metric("Accepted",        orch_stats["accepted"])
        os3.metric("Reviewed",        orch_stats["reviewed"])
        os4.metric("Rejected",        orch_stats["rejected"])
        os5.metric("Accept Rate",     orch_stats["accept_rate"])

        orch_df = load_orchestration_log(max_rows=100)

        if orch_df.empty:
            st.info("No orchestration decisions logged yet. Run a cycle to see routing decisions here.")
        else:
            def color_orch_decision(val):
                if val == "ACCEPT": return "color: green;  font-weight: bold"
                if val == "REJECT": return "color: red;    font-weight: bold"
                if val == "REVIEW": return "color: orange; font-weight: bold"
                return ""

            # Show key columns only for readability
            show_cols = [c for c in [
                "Timestamp", "Stock", "Bucket", "Decision",
                "Bucket_Score", "Composite_Score", "Confluence_Count",
                "Confluence_Level", "Buy_Votes", "Regime", "Summary"
            ] if c in orch_df.columns]

            st.dataframe(
                orch_df[show_cols].style.map(color_orch_decision, subset=["Decision"]),
                use_container_width=True,
                hide_index=True,
            )

            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button(
                    label     = "⬇️ Download Orchestration Log",
                    data      = orch_df.to_csv(index=False),
                    file_name = "orchestration_log.csv",
                    mime      = "text/csv",
                )
            with col_dl2:
                if st.button("🗑️ Clear Orchestration Log", key="clear_orch_log"):
                    clear_orchestration_log()
                    st.info("Orchestration log cleared")
                    st.rerun()
            st.divider()



st.divider()
st.caption("📌 Data: Yahoo Finance | Refreshes every 5 min | Not financial advice")