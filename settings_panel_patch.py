# ================================================
# PATCH FOR app.py — SETTINGS PANEL
#
# Add this import at the top of app.py:
#
#   from config.settings_loader import get_settings, DEFAULT_SETTINGS
#
# Then add this section inside your Logs tab
# (or create a new ⚙️ Settings tab if you prefer)
# at the very end, after the signal log section.
# ================================================

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

    # ── Setup guide ───────────────────────────────
    with st.expander("📖 How to set up Google Sheets control"):
        st.markdown("""
**Step 1 — Create Google Sheet**

Create a new Google Sheet with these exact column headers in Row 1:
```
Setting | Value | Description
```

**Step 2 — Add your settings**

Add these rows (copy exactly):
```
STOP_LOSS_PCT      | 0.06  | Hard stop loss - 6%
TARGET_PROFIT_PCT  | 0.15  | Profit target - 15%
USE_TRAILING_STOP  | True  | Enable trailing stop
TRAILING_STOP_PCT  | 0.04  | Trail 4% below peak
MAX_POSITION_PCT   | 0.10  | Max 10% per trade
WEAK_POSITION_PCT  | 0.05  | 5% for weaker signals
BROKERAGE_PCT      | 0.001 | 0.1% brokerage
STRONG_BUY_VOTES   | 3     | Votes for strong entry
WEAK_BUY_VOTES     | 2     | Votes for normal entry
MACD_MOMENTUM_EXIT | 0.03  | MACD momentum exit
STARTING_CAPITAL   | 100000| Paper trading capital
```

**Step 3 — Publish as CSV**

Go to: **File → Share → Publish to web**
- Choose: Sheet1
- Format: Comma-separated values (.csv)
- Click Publish
- Copy the URL

**Step 4 — Add URL to settings_loader.py**

Open `config/settings_loader.py`
Find: `GOOGLE_SHEET_URL = ""`
Replace with your URL:
```python
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/YOUR_ID/pub?output=csv"
```

**Step 5 — Push and done!**
```
git add config/settings_loader.py
git commit -m "Add Google Sheet URL for remote settings"
git push
```

From now on, change any value in your Google Sheet and the dashboard picks it up within 5 minutes — no code changes needed!
        """)
