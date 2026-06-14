================================================= STRATEGY OVERVIEW ================================================= Strategy Name: Volume-Based Counter-Trend Entry (Prime Technical) Strategy Type: Intraday Reversal/Mean Reversion Market: Stocks (F&O segment only) Timeframe: 5-minute charts Holding Period: Intraday (up to 3:15 PM) Core Idea: Capitalize on exhaustion points by identifying price retracements against the primary trend where volume reaches a daily low, signaling that the 'train' has emptied and is ready to resume the primary direction. ================================================= 2. INDICATORS USED Indicator Name: Volume Settings: Tick-by-tick (Real-time data recommended) Purpose: Identification of exhaustion/low liquidity points. Interpretation: Lowest volume bar relative to the morning session indicates a 'resting' point for entry. Indicator Name: Exponential Moving Average (EMA) Settings: 10 EMA Purpose: Trend-following exit mechanism. Interpretation: Used as a trailing stop/exit signal for the remaining open position. ================================================= 3. ENTRY CONDITIONS Short Entry Rules: Market sentiment: NSE Advance/Decline ratio shows majority Declining (at 9:25 AM). Sector selection: Identify the top-performing sector (e.g., Media) that is trending with the market. Setup: Wait for the first three 5-minute candles (9:15-9:30 AM) to close. Identify a green candle (opposite to trend) that displays the lowest volume of the day so far. Enter short below the low of that green candle. Long Entry Rules: (Inverted Logic) Market sentiment: Advancing stocks > Declining stocks. Sector selection: Top performing Advancing sector. Setup: Identify a red candle (opposite to trend) with the lowest volume of the day. Enter long above the high of that candle. Mandatory Conditions: Use only F&O stocks for high liquidity and circuit-breaker flexibility. ================================================= 4. EXIT CONDITIONS Profit Target Rules: Book 50% of position at a 1:2 Risk-Reward ratio. Apply 'Cost SL' (Break-even stop) to the remaining 50%. Trailing Stop Rules: If not hitting 3:15 PM time exit, exit the remaining position when price closes above/below the 10 EMA and breaks the high/low of that specific candle. Time Based Exit Rules: Hard exit at 3:15 PM. ================================================= 5. RISK MANAGEMENT Position Sizing: Defined by predefined risk amount (e.g., 1000 INR risk per trade). Maximum Risk Per Trade: Set by the distance between entry and the high/low of the signal candle. Maximum Daily Loss: Not explicitly quantified, but limited to 2 entry attempts per stock. Risk Reward Ratio: Theoretically unlimited; minimum target 1:2. ================================================= 6. MARKET CONDITIONS Best Market Conditions: Trending (Up or Down) where the intraday pullback provides an entry. Worst Market Conditions: Low volatility/sideways markets where no clear sector leader exists. ================================================= 7. TRADE FILTERS Sector Filter: Must trade stocks from the dominant sector of the day. Index Confirmation: NSE Advance/Decline ratio check at 9:25 AM. F&O Filter: Only F&O stocks are eligible due to liquidity requirements. ================================================= 8. SUPPORT AND RESISTANCE LOGIC Logic: Not based on classic S&R. Resistance/Support is dynamic, defined by the high/low of the exhaustion candle (the one with the lowest volume). ================================================= 9. MARKET STRUCTURE LOGIC Logic: Focuses on 'Origin of Move' and trend continuation. The strategy assumes that a low-volume retracement is a continuation pattern rather than a reversal. ================================================= 10. AUTOMATION SPECIFICATION Entry Logic: IF (CurrentTrend == Down) AND (CandleColor == Green) AND (Volume == DailyMinimum) THEN LIMIT_ORDER_SHORT_BELOW_LOW. Exit Logic: IF (Target_1_Hit) THEN SELL_50 AND MOVE_SL_TO_ENTRY. Stop Logic: IF (Entry_Price_Breached) THEN EXIT_ALL. ================================================= 11. BACKTEST SPECIFICATION Universe: Nifty 50 constituents (or F&O list). Timeframe: 5-minute. Lookback Period: 9:30 AM onwards. ================================================= 12. MISSING INFORMATION Precise definition of 'Top Performing Sector' (Automated logic for ranking). Handling of overlapping signal candles. Systematic handling of gap-up/gap-down scenarios. ================================================= 13. QUANT REVIEW Potential Edge: Mean reversion of volume at intraday levels. Strengths: High R:R potential. Weaknesses: Subjectivity in selecting sectors; reliance on 9:25 AM data snapshot. Confidence Score: 65/100 ================================================= 14. TRADING OS IMPLEMENTATION READINESS Ready To Code: NO Missing Info: Need a programmatic method for sector ranking based on real-time relative performance against the benchmark (Nifty 50).



# TRADING OS IMPLEMENTATION SPECIFICATION

## FEATURE NAME

Volume Compression Pullback Strategy (VCPS)

Version: 1.0

Category: Intraday Strategy

Priority: High

Goal: Create an institutional-grade intraday continuation strategy by combining:

* Market Structure
* Sector Strength
* Volume Contraction
* Volatility Compression
* Support/Resistance Zones
* Dynamic Risk Management

This strategy will replace the subjective YouTube implementation with a fully systematic and backtestable model.

---

# OBJECTIVES

Build a complete intraday engine capable of:

1. Identifying strong trending sectors.
2. Identifying strong trending stocks inside those sectors.
3. Detecting low-volume pullbacks.
4. Detecting volatility compression.
5. Detecting support and resistance zones.
6. Validating market structure.
7. Calculating dynamic stop loss.
8. Calculating dynamic targets.
9. Producing trade quality scores.
10. Supporting future automation.

---

# NEW FILE

Create:

strategies/intraday_engine.py

---

# DEPENDENCIES

Integrate with:

strategies/market_structure.py

Existing Scanner

Composite Score Engine

Capital Engine

Position Manager

Risk Manager

Execution Engine

---

# MODULE 1

MARKET DIRECTION FILTER

Purpose:

Trade only in direction of broader market.

Inputs:

NIFTY

BANKNIFTY

Conditions:

Bullish Market:

* NIFTY above VWAP
* NIFTY above 20 EMA
* Market Breadth > 1

Bearish Market:

* NIFTY below VWAP
* NIFTY below 20 EMA
* Market Breadth < 1

Output:

market_regime

Values:

BULLISH

BEARISH

NEUTRAL

No trades allowed in NEUTRAL.

---

# MODULE 2

SECTOR STRENGTH ENGINE

Create sector ranking.

Calculate:

Sector Return %

Relative Strength vs Nifty

Sector Breadth

Volume Expansion

Sector Score Formula:

Sector Score =
0.40 × Relative Strength
+
0.30 × Sector Return
+
0.20 × Breadth
+
0.10 × Volume Expansion

Rank all sectors.

Select:

Top 3 sectors only.

Output:

sector_score

sector_rank

---

# MODULE 3

STOCK SELECTION FILTER

Only allow stocks satisfying:

F&O Stock

Volume > 1.5 × 20-period average volume

ATR above minimum threshold

Price > ₹100

Daily traded value above threshold

Output:

eligible_stocks

---

# MODULE 4

MARKET STRUCTURE VALIDATION

Use market_structure.py

Implement:

Higher Highs

Higher Lows

Lower Highs

Lower Lows

BOS

CHOCH

Bullish Structure:

HH + HL

Bearish Structure:

LH + LL

Outputs:

structure_type

Values:

UPTREND

DOWNTREND

RANGE

Only trade UPTREND or DOWNTREND.

Reject RANGE.

---

# MODULE 5

SUPPLY AND DEMAND ZONES

Use recent swing highs and lows.

Demand Zone:

Most recent valid swing low cluster.

Supply Zone:

Most recent valid swing high cluster.

Store:

zone_low

zone_high

zone_strength

Output:

nearest_demand_zone

nearest_supply_zone

---

# MODULE 6

VOLUME COMPRESSION DETECTION

Purpose:

Identify exhaustion pullbacks.

Requirements:

Current Volume < 50% of 20-bar average volume

AND

Current Volume within lowest 10 percentile of last 20 bars

Output:

volume_compression = True/False

---

# MODULE 7

VOLATILITY COMPRESSION

Calculate:

ATR Compression

Bollinger Band Width Compression

Conditions:

Current ATR < 80% of ATR20 average

AND

BB Width < 20-bar average width

Output:

volatility_compression = True/False

---

# MODULE 8

ENTRY LOGIC

LONG SETUP

Requirements:

Market Regime = BULLISH

Sector Rank <= 3

Structure = UPTREND

Volume Compression = True

Volatility Compression = True

Price near Demand Zone

Entry Trigger:

Break above high of compression candle

Generate:

BUY signal

SHORT SETUP

Requirements:

Market Regime = BEARISH

Sector Rank <= 3

Structure = DOWNTREND

Volume Compression = True

Volatility Compression = True

Price near Supply Zone

Entry Trigger:

Break below low of compression candle

Generate:

SELL signal

---

# MODULE 9

STOP LOSS ENGINE

Long:

Stop = max(
Demand Zone Low,
Compression Candle Low,
ATR Stop
)

Short:

Stop = min(
Supply Zone High,
Compression Candle High,
ATR Stop
)

Store:

stop_price

risk_per_share

---

# MODULE 10

TARGET ENGINE

Target 1:

2R

Target 2:

Nearest Supply Zone (Long)

Nearest Demand Zone (Short)

Target 3:

EMA Trail Exit

Store:

target_1

target_2

target_3

---

# MODULE 11

TRADE MANAGEMENT

At Target 1:

Book 50%

Move stop to breakeven.

Remaining quantity:

Trail using:

10 EMA

or

Structure-based trailing stop.

---

# MODULE 12

TRADE QUALITY SCORE

Create score from 0-100.

Components:

Market Regime = 15

Sector Strength = 20

Structure Quality = 20

Zone Quality = 15

Volume Compression = 10

Volatility Compression = 10

Risk Reward = 10

Total = 100

Output:

trade_score

Classification:

90+ = A+

80-89 = A

70-79 = B

60-69 = C

Below 60 = Reject

---

# MODULE 13

SCANNER INTEGRATION

Add new scanner output columns:

Market Regime

Sector Rank

Sector Score

Structure

Demand Zone

Supply Zone

Volume Compression

Volatility Compression

Stop Price

Target 1

Target 2

Trade Score

Trade Grade

---

# MODULE 14

AUTOMATION READY OUTPUT

Return dictionary:

{
"stock": "",
"signal": "",
"entry_price": 0,
"stop_price": 0,
"target_1": 0,
"target_2": 0,
"trade_score": 0,
"trade_grade": "",
"market_regime": "",
"sector_rank": 0,
"structure": ""
}

---

# MODULE 15

BACKTEST REQUIREMENTS

Add strategy to backtesting framework.

Metrics:

Win Rate

Profit Factor

Average R Multiple

Expectancy

Max Drawdown

Sharpe Ratio

Sortino Ratio

Average Holding Time

Sector-wise Performance

Regime-wise Performance

---

# DELIVERABLES

1. Fully coded intraday_engine.py

2. Integration with market_structure.py

3. Integration with scanner

4. Integration with composite score

5. Integration with backtest engine

6. Unit test functions

7. Example output

8. Documentation

Do not provide pseudocode.

Provide production-ready Python code compatible with Trading OS architecture.