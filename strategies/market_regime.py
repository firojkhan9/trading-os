# ================================================
# FILE: strategies/market_regime.py
# PURPOSE: Detect the current market regime
#          Bull / Bear / Sideways
#
# WHY THIS MATTERS:
#   Different strategies work best in different regimes.
#   EMA Crossover is great in trending markets.
#   Bollinger Bands is great in sideways markets.
#   In a bear market — CASH is the best position.
#
# HOW IT WORKS:
#   We use NIFTY 50 index (^NSEI) as the market proxy.
#   Then we apply 4 filters to classify the regime:
#
#   1. Price vs MA50  — is market above or below trend?
#   2. Price vs MA200 — is market in long term bull/bear?
#   3. ADX            — is market trending or sideways?
#   4. Slope of MA50  — is trend going up or down?
#
# REGIMES:
#   BULL  🐂 — market trending up, strategies work well
#   BEAR  🐻 — market trending down, avoid new buys
#   SIDEWAYS ↔️ — market ranging, mean-reversion works
# ================================================

import pandas as pd
import yfinance as yf


# ── Settings ──────────────────────────────────────
NIFTY_SYMBOL = "^NSEI"    # NIFTY 50 index
MA_FAST      = 50         # 50-day moving average
MA_SLOW      = 200        # 200-day moving average
ADX_PERIOD   = 14         # ADX period


def fetch_nifty_data(period="1y"):
    """
    Fetch NIFTY 50 index data.
    We use NIFTY as a proxy for the overall market.
    """
    try:
        data = yf.download(
            tickers  = NIFTY_SYMBOL,
            period   = period,
            interval = "1d",
            progress = False
        )
        if data.empty:
            return None
        data.columns = [col[0] for col in data.columns]
        return data
    except Exception as e:
        return None


def calculate_adx(data, period=14):
    """
    Calculate ADX (Average Directional Index).
    ADX measures the STRENGTH of a trend.

    ADX < 20  = No clear trend (sideways market)
    ADX 20-25 = Weak trend forming
    ADX > 25  = Strong trend (bull or bear)
    ADX > 40  = Very strong trend

    ADX does NOT tell direction — only strength.
    We use MA50 slope to determine direction.
    """
    high  = data['High']
    low   = data['Low']
    close = data['Close']

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    dm_plus  = high - high.shift(1)
    dm_minus = low.shift(1) - low

    dm_plus  = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
    dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)

    # Smoothed values
    atr       = tr.rolling(window=period).mean()
    di_plus   = 100 * (dm_plus.rolling(window=period).mean()  / atr)
    di_minus  = 100 * (dm_minus.rolling(window=period).mean() / atr)

    # DX and ADX
    dx  = 100 * ((di_plus - di_minus).abs() / (di_plus + di_minus))
    adx = dx.rolling(window=period).mean()

    data['ADX']      = adx.round(2)
    data['DI_Plus']  = di_plus.round(2)
    data['DI_Minus'] = di_minus.round(2)

    return data


def calculate_regime_indicators(data):
    """
    Calculate all indicators needed for regime detection.
    Adds MA50, MA200, ADX, and MA50 slope to the dataframe.
    """

    # ── Moving Averages ───────────────────────────
    data['MA50']  = data['Close'].rolling(window=MA_FAST).mean().round(2)
    data['MA200'] = data['Close'].rolling(window=MA_SLOW).mean().round(2)

    # ── MA50 Slope ────────────────────────────────
    # Is the 50-day MA going up or down?
    # Positive slope = uptrend | Negative slope = downtrend
    data['MA50_Slope'] = (
        data['MA50'] - data['MA50'].shift(10)
    ) / data['MA50'].shift(10) * 100
    data['MA50_Slope'] = data['MA50_Slope'].round(4)

    # ── ADX ───────────────────────────────────────
    data = calculate_adx(data, ADX_PERIOD)

    return data


def detect_regime(data):
    """
    Detect the current market regime based on indicators.

    Returns one of:
    - BULL 🐂    : Uptrend, strategies should be active
    - BEAR 🐻    : Downtrend, avoid new positions
    - SIDEWAYS ↔️ : No clear trend, use mean-reversion
    - UNKNOWN ❓  : Not enough data yet
    """

    # Need enough data for MA200
    if len(data) < MA_SLOW + 10:
        return "UNKNOWN ❓", "Not enough data to detect regime"

    latest = data.iloc[-1]

    # Check for NaN values
    if pd.isna(latest['MA50']) or pd.isna(latest['MA200']) or pd.isna(latest['ADX']):
        return "UNKNOWN ❓", "Indicators still warming up"

    price     = float(latest['Close'])
    ma50      = float(latest['MA50'])
    ma200     = float(latest['MA200'])
    adx       = float(latest['ADX'])
    slope     = float(latest['MA50_Slope'])
    di_plus   = float(latest['DI_Plus'])
    di_minus  = float(latest['DI_Minus'])

    # ── SIDEWAYS Detection ────────────────────────
    # ADX below 20 = no strong trend in either direction
    if adx < 20:
        return "SIDEWAYS ↔️", f"ADX={adx:.1f} (weak trend) — market ranging"

    # ── BULL Detection ────────────────────────────
    # Price above both MAs + upward slope + DI+ dominates
    if (price > ma50 and
        price > ma200 and
        slope > 0 and
        di_plus > di_minus):
        return "BULL 🐂", f"Price above MA50 & MA200, ADX={adx:.1f}, slope rising"

    # ── BEAR Detection ────────────────────────────
    # Price below both MAs + downward slope + DI- dominates
    if (price < ma50 and
        price < ma200 and
        slope < 0 and
        di_minus > di_plus):
        return "BEAR 🐻", f"Price below MA50 & MA200, ADX={adx:.1f}, slope falling"

    # ── Weak Bull (transitioning) ─────────────────
    # Price above MA50 but below MA200 (early recovery)
    if price > ma50 and slope > 0:
        return "WEAK BULL 📈", f"Price above MA50, below MA200 — early recovery"

    # ── Weak Bear (transitioning) ─────────────────
    if price < ma50 and slope < 0:
        return "WEAK BEAR 📉", f"Price below MA50 — trend weakening"

    # ── Default ───────────────────────────────────
    return "SIDEWAYS ↔️", "Mixed signals — no clear regime"


def get_regime_strategy_advice(regime):
    """
    Based on the detected regime, recommend which
    strategies to trust and how to behave.

    This is the core insight of Milestone 17 —
    matching strategy to market condition.
    """

    advice = {
        "BULL 🐂": {
            "Action":           "✅ ACTIVE TRADING",
            "Best Strategies":  "EMA Crossover, MACD",
            "Avoid":            "Nothing — all strategies work",
            "Position Size":    "Full size (10% per trade)",
            "Cash Reserve":     "20% minimum",
            "Explanation":      (
                "Trending markets favour momentum strategies. "
                "EMA and MACD crossovers are highly reliable. "
                "Buy dips confidently."
            ),
        },
        "WEAK BULL 📈": {
            "Action":           "🟡 SELECTIVE TRADING",
            "Best Strategies":  "EMA Crossover, MA + RSI",
            "Avoid":            "Aggressive position sizing",
            "Position Size":    "Reduced (7% per trade)",
            "Cash Reserve":     "40% minimum",
            "Explanation":      (
                "Market recovering but not confirmed bull yet. "
                "Trade selectively, only strong signals. "
                "Keep more cash as buffer."
            ),
        },
        "SIDEWAYS ↔️": {
            "Action":           "🟡 MEAN REVERSION MODE",
            "Best Strategies":  "Bollinger Bands, MA + RSI",
            "Avoid":            "EMA Crossover (too many false signals)",
            "Position Size":    "Reduced (5% per trade)",
            "Cash Reserve":     "50% minimum",
            "Explanation":      (
                "Ranging markets suit Bollinger Bands perfectly. "
                "Buy at lower band, sell at upper band. "
                "Avoid trend-following strategies — they whipsaw."
            ),
        },
        "WEAK BEAR 📉": {
            "Action":           "🔴 DEFENSIVE MODE",
            "Best Strategies":  "None — wait for clarity",
            "Avoid":            "All long positions",
            "Position Size":    "Minimal (3% max)",
            "Cash Reserve":     "70% minimum",
            "Explanation":      (
                "Market weakening. New buys are risky. "
                "Exit existing positions on strength. "
                "Protect capital — cash is a valid position."
            ),
        },
        "BEAR 🐻": {
            "Action":           "🛑 STOP ALL BUYING",
            "Best Strategies":  "None — cash is king",
            "Avoid":            "Any new long positions",
            "Position Size":    "Zero new trades",
            "Cash Reserve":     "90%+ — stay in cash",
            "Explanation":      (
                "Bear market confirmed. Do NOT buy dips. "
                "Exit all positions. Sit in cash. "
                "Wait for regime to shift to Bull before trading."
            ),
        },
        "UNKNOWN ❓": {
            "Action":           "⏳ WAIT FOR DATA",
            "Best Strategies":  "N/A",
            "Avoid":            "Any trading decisions",
            "Position Size":    "N/A",
            "Cash Reserve":     "N/A",
            "Explanation":      "Not enough data to detect regime yet.",
        },
    }

    # Return advice for the detected regime
    # Default to SIDEWAYS if regime not found
    return advice.get(regime, advice["SIDEWAYS ↔️"])


def get_full_regime_analysis(period="1y"):
    """
    Master function — fetches NIFTY data, runs all
    regime indicators, and returns a complete analysis.

    Called by app.py to display on the dashboard.
    """

    # Step 1: Fetch NIFTY data
    data = fetch_nifty_data(period)

    if data is None or data.empty:
        return {
            "regime":      "UNKNOWN ❓",
            "reason":      "Could not fetch NIFTY data",
            "advice":      get_regime_strategy_advice("UNKNOWN ❓"),
            "indicators":  {},
            "data":        None,
        }

    # Step 2: Calculate indicators
    data = calculate_regime_indicators(data)

    # Step 3: Detect regime
    regime, reason = detect_regime(data)

    # Step 4: Get strategy advice
    advice = get_regime_strategy_advice(regime)

    # Step 5: Extract latest indicator values
    latest = data.iloc[-1]
    indicators = {}

    try:
        indicators = {
            "NIFTY Price":  round(float(latest['Close']), 2),
            "MA50":         round(float(latest['MA50']), 2)  if not pd.isna(latest['MA50'])  else "N/A",
            "MA200":        round(float(latest['MA200']), 2) if not pd.isna(latest['MA200']) else "N/A",
            "ADX":          round(float(latest['ADX']), 2)   if not pd.isna(latest['ADX'])   else "N/A",
            "MA50 Slope":   round(float(latest['MA50_Slope']), 4) if not pd.isna(latest['MA50_Slope']) else "N/A",
            "DI+":          round(float(latest['DI_Plus']), 2)  if not pd.isna(latest['DI_Plus'])  else "N/A",
            "DI-":          round(float(latest['DI_Minus']), 2) if not pd.isna(latest['DI_Minus']) else "N/A",
        }
    except Exception:
        pass

    return {
        "regime":     regime,
        "reason":     reason,
        "advice":     advice,
        "indicators": indicators,
        "data":       data,
    }


def get_regime_history(data, window=60):
    """
    Get regime for each day in recent history.
    Used to plot regime changes over time on the chart.
    Returns a list of (date, regime) tuples.
    """
    if data is None or len(data) < MA_SLOW:
        return []

    history = []
    subset  = data.tail(window)

    for i in range(len(subset)):
        row = subset.iloc[i]
        try:
            price    = float(row['Close'])
            ma50     = float(row['MA50'])
            ma200    = float(row['MA200'])
            adx      = float(row['ADX'])
            slope    = float(row['MA50_Slope'])
            di_plus  = float(row['DI_Plus'])
            di_minus = float(row['DI_Minus'])

            if any(pd.isna(v) for v in [ma50, ma200, adx, slope]):
                regime = "UNKNOWN"
            elif adx < 20:
                regime = "SIDEWAYS"
            elif price > ma50 and price > ma200 and slope > 0 and di_plus > di_minus:
                regime = "BULL"
            elif price < ma50 and price < ma200 and slope < 0 and di_minus > di_plus:
                regime = "BEAR"
            elif price > ma50 and slope > 0:
                regime = "WEAK BULL"
            elif price < ma50 and slope < 0:
                regime = "WEAK BEAR"
            else:
                regime = "SIDEWAYS"

            history.append({
                "Date":   subset.index[i],
                "Regime": regime,
                "Close":  round(price, 2),
                "MA50":   round(ma50, 2),
                "MA200":  round(ma200, 2) if not pd.isna(ma200) else None,
                "ADX":    round(adx, 2),
            })
        except Exception:
            continue

    return history
