# ================================================
# PATCH FOR app.py — SCANNER TAB
#
# STEP 1: Add this import at top of app.py
#         with other imports:
#
#   from strategies.performance_scanner import scan_all_stocks
#
# STEP 2: Add "📡 Scanner" to your tabs list.
#         Find this line:
#           tab1, tab2, tab3, ... = st.tabs([...])
#         Add "📡 Scanner" to the list.
#         Example:
#           tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
#               "📊 Dashboard",
#               "🌡️ Market Regime",
#               "📡 Scanner",       ← ADD THIS (position 3 recommended)
#               "💯 Stock Score",
#               "📈 RS Ranking",
#               "🔬 Backtesting",
#               "📊 Strategy Comparison",
#               "📋 Logs"
#           ])
#
# STEP 3: Add a new tab block with the code below.
#         Place it after the Market Regime tab block.
# ================================================


# ════════════════════════════════════════════════
# SCANNER TAB — paste this as a new tab block
# ════════════════════════════════════════════════
# with tab3:   ← use whatever tab variable you assigned

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
