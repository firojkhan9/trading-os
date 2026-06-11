🤖 Firoj Khan's Trading OS — Master Project Prompt
Use this at the start of every new conversation with Claude or Cursor AI
---
WHO I AM
I am Firoj Khan — a trader and entrepreneur building an AI-assisted portfolio
management and autonomous paper-trading operating system for Indian equity markets.
My background:

Occasional trader on Zerodha (NSE/BSE)
Strong in analytics, Excel, dashboards, structured logic, business thinking
Beginner in coding, APIs, AI engineering, and algorithmic trading
Learning through building — prefer practical, motivating, step-by-step guidance
Can get overwhelmed by excessive technical detail — keep explanations beginner-friendly
Never skip setup instructions or terminal commands

---
PRIMARY OBJECTIVES

Generate consistent side income safely through disciplined paper trading
Build a system for consistent, rules-based income generation
Build long-term wealth through intelligent portfolio management
Create a fully autonomous AI-assisted portfolio operating system
Reduce emotional decision-making through systematic rules
Continuously improve through backtesting, learning, and iteration

---
CORE PHILOSOPHY — NON-NEGOTIABLE
Capital Protection First

Protecting capital is MORE important than maximizing profit
Prioritize risk-adjusted returns over raw returns
Avoid unrealistic promises or over-optimized strategies
Long-term survivability matters more than short-term gains
Cash is a valid and often optimal position
NO-TRADE is a legitimate and important decision

Performance Philosophy
Optimize for:

Consistency over big wins
Survivability through drawdowns
Controlled risk exposure
Portfolio stability
Disciplined, rule-based execution

NOT: unrealistic profit maximization or overtrading
AI Philosophy
AI assists in:

Ranking opportunities by quality
Filtering out bad trades before they happen
Improving decision quality through data synthesis
Explaining reasoning in plain English
Reducing emotional and impulsive decisions

AI is NOT a magical prediction machine. It supports human judgment.
---
TECH STACK

Python, Pandas, NumPy
Streamlit (dashboard)
Plotly (charts)
yfinance (market data)
SQLite → Supabase (storage, future)
GitHub (version control)
Streamlit Cloud (deployment)
Cursor AI + Claude (development assistants)
Zerodha Kite API (future — live trading)

---
PROJECT STRUCTURE
trading\_os/
├── app.py                          ← Streamlit dashboard (repo root)
├── config/
│   ├── settings.py                 ← Central path + risk settings
│   ├── settings\_loader.py          ← Google Sheets settings loader
│   └── strategy\_settings.py       ← Exposes settings to all modules
├── strategies/
│   ├── indicators.py               ← MA20 + RSI
│   ├── ema\_strategy.py             ← EMA Crossover
│   ├── bollinger\_strategy.py       ← Bollinger Bands + RSI filter
│   ├── macd\_strategy.py            ← MACD Crossover
│   ├── combined\_signal.py          ← 4-strategy voting engine
│   ├── combined\_backtest.py        ← Combined signal backtester
│   ├── strategy\_comparison.py      ← Side-by-side strategy comparison
│   ├── backtest.py                 ← MA+RSI backtester
│   ├── paper\_trader.py             ← Paper trade execution
│   ├── market\_regime.py            ← NIFTY regime detection
│   ├── relative\_strength.py        ← RS ranking vs NIFTY
│   ├── scoring\_engine.py           ← 8-dimension composite score (0-100)
│   ├── explainability\_engine.py    ← Plain English signal explanations
│   ├── fundamental\_engine.py       ← P/E, ROE, growth, health scoring
│   ├── sentiment\_engine.py         ← News sentiment (5 sources)
│   ├── performance\_scanner.py      ← Full watchlist scanner
│   └── watchlist\_manager.py        ← Dynamic watchlist (CSV + Google Sheets)
├── logs/
│   ├── signal\_logger.py
│   ├── signal\_log.csv
│   └── paper\_trades.csv
├── portfolio/
│   └── performance.py              ← Portfolio performance reporting
├── risk/
│   └── risk\_manager.py             ← Stop loss, position limits, daily loss
├── watchlist.csv                   ← Active stock universe
├── requirements.txt
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml                ← Password (never commit this)
└── .gitignore
---
COMPLETED MILESTONES ✅
#MilestoneStatus
1 Python environment setup✅ Done
2 Single stock data fetcher✅ Done
3 10-stock watchlist engine✅ Done
4 Live browser dashboard (Streamlit)✅ Done
5 Technical indicators (MA20 + RSI)✅ Done
6 Automatic signal logger✅ Done
7 Paper trading simulator✅ Done
8 Portfolio performance report✅ Done
9 Risk management rules✅ Done
10 Strategy backtesting engine✅ Done
11 Cloud deployment (Streamlit Cloud)✅ Done
12 EMA Crossover Strategy✅ Done
13 Bollinger Bands Strategy✅ Done
14 MACD Strategy✅ Done
15 Strategy Comparison Dashboard✅ Done
16 Combined Signal Engine (4-strategy voting)✅ Done
17 Market Regime Detection (NIFTY-based)✅ Done
18 Dynamic Watchlist System (CSV + Google Sheets)✅ Done
19 Relative Strength Ranking vs NIFTY✅ Done
20 Combined Intelligence Scoring Engine (0-100)✅ Done
21 Explainability Engine✅ Done
22 Fundamental Intelligence Layer✅ Done
23 Sentiment Analysis Engine (5 news sources)✅ Done
24 Capital Allocation Engine✅ Done
25A Position Lifecycle Integration ✅ Done
25B Lifecycle Monitoring Engine ✅ Done
26 Autonomous Execution Loop ✅ Done
27 Volume Intelligence Engine ✅ Done
28 Candlestick + Price Action Engine ✅ Done
29 Market Structure Engine ✅ Done
30 Advanced Portfolio Risk Engine  ✅ Done
31 Strategy Orchestration Engine ✅ Done
---
CRITICAL OUTPUT RULES

You are working on a large existing codebase.

DO NOT rewrite entire files.

DO NOT regenerate functions that are not being changed.

DO NOT output complete files unless I explicitly request FULL FILE.

Default behavior:

1. First analyze current architecture.
2. Identify exact insertion points.
3. Return ONLY:
   - new functions
   - modified functions
   - changed imports
   - changed constants
   - changed SQL

4. Use PATCH FORMAT:

=== FILE: risk/portfolio_risk.py ===

ADD AFTER:
def existing_function():

<new code>

=== FILE: app.py ===

REPLACE:

<old code>

WITH:

<new code>

5. Minimize token usage.
6. Never repeat unchanged code.
7. If a change affects less than 20% of a file, return patch only.
8. Ask for the file if needed rather than guessing.

FULL FILE OUTPUT IS FORBIDDEN UNLESS I EXPLICITLY SAY:
"GENERATE FULL FILE"

PROJECT MODE: TOKEN EFFICIENT

This project is approximately:
- 17,000+ LOC
- 34+ Python files
- Streamlit
- Supabase
- Google Sheets

Rules:

- Assume existing code works.
- Preserve architecture.
- Make smallest possible change.
- Prefer patches over rewrites.
- Prefer function-level changes over file-level changes.
- Never regenerate files larger than 300 lines.
- Show exact insertion locations.
- Output only changed code.
- Explain integration points before code.



CURRENT RISK SETTINGS
SettingValueStop Loss6%Profit Target15%Trailing Stop4% below peakMax Position Size10% of capitalMax Open Positions5 stocksStarting Capital (paper)₹1,00,000Brokerage0.1% per tradeDaily Loss Limit5%
All configurable via Google Sheets (no code changes needed).
---
CURRENT WATCHLIST
RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK,
HINDUNILVR, SBIN, BHARTIARTL, ITC, KOTAKBANK
---
DEPLOYMENT

GitHub: https://github.com/firojkhan9/trading-os
Live App: Streamlit Cloud (password protected)
Settings: Google Sheets (remote config)
Watchlist: Google Sheets (remote management)

---
FUTURE IMPROVEMENTS LOGGED
IDDescriptionFI-001Replace dropdown with clickable row selector (done in Scanner)FI-002Add FII/DII flow data to fundamental engineFI-003Supabase integration for persistent cloud trade storage
---
═══════════════════════════════════════════════════
NEXT PHASE — AUTONOMOUS PORTFOLIO OPERATING SYSTEM
═══════════════════════════════════════════════════
The system now evolves from signal generation dashboard
to autonomous portfolio execution and lifecycle management.
---
ARCHITECTURAL VISION — THREE-BUCKET PORTFOLIO ENGINE
Total Capital: ₹5,00,000 (fully configurable)
BucketCapitalStyleFrequencyLong-Term₹3,00,000 (60%)Fundamentals + Trend + SectorLow — weeks to monthsSwing Trading₹1,50,000 (30%)Momentum + EMA + RS + VolumeMedium — days to weeksIntraday₹50,000 (10%)VWAP + Volume + ATR + MomentumHigh — same day
Each bucket operates completely independently:

own capital pool
own strategy weights
own risk rules
own position limits
own holding periods
own performance tracking

---
NEXT MILESTONES ROADMAP
PHASE 4A — CAPITAL & EXECUTION FOUNDATION
(Build the engine room — do this before any new strategies)
---
Milestone 24 — Capital Allocation Engine
File: portfolio/capitalengine.py
Responsibilities:

Define and manage three capital buckets (Long-Term, Swing, Intraday)
Track available cash per bucket
Track deployed capital per bucket
Enforce bucket-level position limits
Enforce portfolio-level exposure limits
Calculate bucket-level P&L and returns
Support configurable bucket sizes (% of total capital)
Prevent cross-bucket capital leakage

Dashboard additions:

Bucket summary panel (capital, deployed, available, P&L per bucket)
Visual capital allocation chart

---
Milestone 25 — Position Lifecycle Manager
File: portfolio/position\_manager.py
Every trade must move through defined states:
WATCHLIST → READY → ENTERED → HOLDING → PARTIAL\_EXIT
         → TRAILING → EXITED → COOLDOWN
         → REJECTED (with reason logged)
Responsibilities:

Entry management (size, timing, confirmation)
Scaling in (add to winner on confirmation)
Scaling out (partial profit booking)
Stop loss enforcement (hard stop)
Trailing stop management (dynamic)
Time-based exits (max holding period per bucket)
Forced exits (regime change, daily loss limit)
Cooldown periods (no re-entry for N days after stop loss)
Full state audit trail in SQLite/CSV

Next Planned Milestone
Milestone 25A
Position Lifecycle Integration
Deliverables
Create lifecycle record on BUY
Create lifecycle exit record on SELL
Create Lifecycle Dashboard Tab
Populate Supabase position_lifecycle table
No automation yet.
Milestone 25B
Lifecycle Monitoring Engine
Implement:
update_position_price()
Enable:
ENTERED → HOLDING
HOLDING → TRAILING
TRAILING → PARTIAL_EXIT
EXITED → COOLDOWN
Track:
Current Price
Peak Price
Days Held
Trailing Stop
P&L %
---
Milestone 26 — Autonomous Execution Loop
File: engine/execution_loop.py
A scheduler that runs continuously during market hours and:
Every N minutes:

Fetch latest market data for all watchlist stocks
Update all indicators (MA, EMA, RSI, MACD, BB, Volume)
Recalculate intelligence scores
Check market regime (NIFTY)
Scan for new opportunities (by bucket)
Evaluate all open positions (stop loss, trailing, target)
Check portfolio constraints (exposure, daily loss, bucket limits)
Execute paper trades autonomously
Log every decision with full explanation (including NO-TRADE reasons)
Update dashboard metrics

Scheduler requirements:

Configurable interval (e.g. every 5 / 15 / 30 minutes)
Market hours awareness (9:15 AM – 3:30 PM IST, Mon–Fri)
Pre-market preparation run (9:00 AM)
Post-market summary run (3:35 PM)
Safe shutdown on error
Pause/resume support
No duplicate trade execution (idempotent)
Full error recovery with logging

---
PHASE 4B — INTELLIGENCE EXPANSION
(Add new signal types to improve decision quality)
---
Milestone 27 — Volume Intelligence Engine
File: strategies/volume_engine.py
Volume is a confirmation tool — never a standalone signal.
Implement:

Volume spike detection (vs 20-day average volume)
Unusual volume alert (>2x average = significant)
Volume trend analysis (rising/falling volume in trend)
OBV (On-Balance Volume) — accumulation vs distribution
Chaikin Money Flow — buying vs selling pressure
Breakout volume confirmation (breakout without volume = weak)
Volume-weighted confidence adjustment in scoring engine

Rule: Any BUY signal with volume < average volume gets confidence reduced by 20%.
---
Milestone 28 — Candlestick + Price Action Engine
File: strategies/candlestick_engine.py
Priority patterns to detect:

Hammer (bullish reversal at support)
Shooting Star (bearish reversal at resistance)
Bullish Engulfing / Bearish Engulfing
Doji (indecision — watch for confirmation)
Morning Star (3-candle bullish reversal)
Evening Star (3-candle bearish reversal)
Breakout candle (large body, high volume)

CRITICAL RULE — Candlestick patterns NEVER act alone.
A pattern is only valid when confirmed by ALL of:

Trend direction (EMA/MA alignment)
Volume (above average on signal candle)
Support/Resistance level proximity
Market regime (not in bear market for BUY signals)

Unconfirmed patterns = IGNORED (logged as REJECTED with reason)






---
Milestone 29 — Market Structure Engine
File: strategies/market_structure.py
Implement:

Support and resistance zone detection (recent swing highs/lows)
Breakout detection (price closes above resistance with volume)
Breakdown detection (price closes below support)
Consolidation detection (low ATR, tight BB width)
Volatility compression alerts (squeeze before expansion)
Higher Highs / Higher Lows detection (uptrend structure)
Lower Highs / Lower Lows detection (downtrend structure)
Price structure scoring contribution to composite score






---
PHASE 4C — ADVANCED RISK INTELLIGENCE
(Portfolio-level protection, not just trade-level)
---
Milestone 30 — Advanced Portfolio Risk Engine
File: risk/portfolio\_risk.py
Move beyond per-trade stop loss to portfolio intelligence:

Sector exposure limits (max 30% in any one sector)
Correlation awareness (avoid 3+ highly correlated stocks)
Bucket drawdown control (pause bucket if down >10%)
Portfolio daily loss limit (halt all trading if down >5% today)
Max simultaneous exposure (never >70% capital deployed)
Volatility-adjusted position sizing (smaller size in volatile markets)
ATR-based stop loss (stop = entry - 2x ATR, not fixed %)
Regime-aware aggression (reduce size in WEAK BULL / SIDEWAYS)




---
PHASE 4D — AUTONOMOUS INTELLIGENCE
(The brain of the system)
---
Milestone 31 — Strategy Orchestration Engine
File: strategies/orchestrator.py
Per-bucket strategy configurations:
Long-Term Bucket:

Fundamental Score weight: 40%
Trend (MA/EMA) weight: 30%
Relative Strength weight: 20%
Sentiment weight: 10%
Min composite score to enter: 70/100
Min holding period: 20 trading days

Swing Trading Bucket:

EMA Crossover weight: 25%
MACD weight: 25%
Relative Strength weight: 20%
Volume Confirmation weight: 15%
Candlestick Pattern weight: 15%
Min composite score to enter: 60/100
Max holding period: 15 trading days

Intraday Bucket (future):

VWAP position weight: 30%
Volume spike weight: 25%
Momentum (RSI intraday) weight: 25%
ATR volatility weight: 20%
Same-day exit mandatory

Orchestrator responsibilities:

Route each opportunity to the correct bucket
Resolve signal conflicts between strategies
Calculate bucket-specific confidence score
Reject weak setups before they reach execution
Identify confluence (multiple signals agreeing = higher confidence)
Log all routing decisions with reasons

# Milestone 31 – Strategy Orchestration Engine

## Objective

Build a Strategy Orchestration Engine that acts as the central decision layer between scanners/signals and trade execution.

The goal is to ensure that every stock opportunity is evaluated according to the rules of the target bucket before reaching the execution engine.

The orchestrator should not execute trades.

It should only:

* Evaluate opportunities
* Calculate confidence scores
* Route opportunities to the correct bucket
* Reject weak opportunities
* Log all decisions

---

## Existing System Context

Current system already contains:

* Scanner and signal generation modules
* Composite scoring framework
* Bucket-based capital allocation
* Capital Engine
* Portfolio Risk Engine
* Position Lifecycle Manager
* Trade execution flow

The orchestrator should integrate with these existing components rather than duplicate them.

Before implementation, inspect the current codebase and identify:

* Existing signal generators
* Existing composite scoring logic
* Existing bucket definitions
* Existing risk filters
* Existing trade entry workflow

Reuse wherever possible.

---

## Responsibilities

### 1. Bucket Routing

Determine which bucket a stock belongs to.

Possible buckets:

* Long-Term
* Swing
* Intraday (future)

Routing should be rule-driven and configurable.

Examples:

* Strong fundamentals + trend alignment → Long-Term
* Technical breakout + momentum → Swing
* Intraday momentum setup → Intraday

The routing decision should always include a reason.

---

### 2. Bucket-Specific Scoring

Each bucket should have its own weighting model.

### Long-Term Bucket

Suggested weight model:

* Fundamental Score = 40%
* Trend Score = 30%
* Relative Strength = 20%
* Sentiment = 10%

Minimum entry score:
70/100

Minimum holding period:
20 trading days

---

### Swing Bucket

Suggested weight model:

* EMA Crossover = 25%
* MACD = 25%
* Relative Strength = 20%
* Volume Confirmation = 15%
* Candlestick Pattern = 15%

Minimum entry score:
60/100

Maximum holding period:
15 trading days

---

### Intraday Bucket (Future)

Suggested weight model:

* VWAP Position = 30%
* Volume Spike = 25%
* RSI Momentum = 25%
* ATR Volatility = 20%

Mandatory same-day exit.

Implementation can be placeholder if Intraday is not active yet.

---

### 3. Confluence Detection

Identify when multiple independent signals support the same direction.

Examples:

* EMA crossover + MACD bullish
* Breakout + volume confirmation
* Relative strength + trend alignment

More confluence should increase confidence.

Confluence should be configurable.

---

### 4. Conflict Resolution

Detect conflicting signals.

Examples:

* Bullish EMA crossover but bearish MACD
* Strong fundamentals but weak trend
* Breakout candidate during risk-off market regime

The orchestrator should decide whether to:

* Reject
* Reduce confidence
* Route differently

All decisions must be explainable.

---

### 5. Opportunity Rejection Layer

Reject opportunities before they reach execution.

Examples:

* Score below threshold
* Risk engine rejection
* Bucket exposure limits reached
* Position lifecycle restriction
* Cooldown active
* Portfolio risk limits exceeded

Return structured rejection reasons.

---

### 6. Confidence Scoring

Produce a normalized confidence score.

Target:
0–100

Output should include:

* Raw component scores
* Weighted score
* Final confidence score
* Routing reason
* Rejection reason (if rejected)

---

### 7. Logging

Create a full audit trail.

Every opportunity should be logged regardless of outcome.

Log:

* Timestamp
* Stock
* Bucket selected
* Component scores
* Confidence score
* Accepted/Rejected
* Reason

Prefer Supabase-backed persistence if consistent with existing architecture.

---

## Suggested Output Structure

For every evaluated opportunity return something similar to:

{
stock,
bucket,
confidence_score,
decision,
reasons,
component_scores,
confluence_count
}

Decision values:

* ACCEPT
* REJECT
* REVIEW

---

## Design Principles

1. Reuse existing scoring systems.
2. Reuse existing risk engine outputs.
3. Reuse lifecycle restrictions.
4. Avoid duplicating calculations already available elsewhere.
5. Keep bucket rules configurable.
6. Keep future support for Intraday trading.
7. Make every routing decision explainable and auditable.

---

## Deliverables

Claude should:

1. Review existing codebase.
2. Identify reusable modules.
3. Design orchestration architecture.
4. Recommend required data structures.
5. Recommend Supabase logging schema if needed.
6. Implement orchestrator using existing project patterns.
7. Ensure compatibility with Capital Engine, Risk Engine, and Position Lifecycle Manager.



---
Milestone 32 — Explainable Autonomous Decision Engine
File: engine/decision\_engine.py
Every autonomous decision (BUY, SELL, HOLD, NO-TRADE) must produce:
DECISION: BUY / SELL / HOLD / NO-TRADE
Stock: RELIANCE
Bucket: Swing Trading
Confidence: 78%
Composite Score: 72/100

REASONS FOR:
  ✅ EMA crossover confirmed (fast above slow, gap 1.2%)
  ✅ MACD bullish crossover today
  ✅ Volume 2.3x average — strong confirmation
  ✅ Hammer pattern at MA20 support
  ✅ Market regime: BULL

REASONS AGAINST:
  ⚠️ RSI at 64 — approaching overbought
  ⚠️ Sector (Energy) already 25% of portfolio

RISK ASSESSMENT:
  Entry: ₹2,847
  Stop Loss: ₹2,762 (ATR-based, -3.0%)
  Target: ₹3,130 (+9.9%)
  Risk:Reward = 1:3.3
  Position Size: 7% of Swing bucket

PORTFOLIO IMPACT:
  Current exposure: 45% deployed
  After this trade: 52% deployed
  Bucket utilization: 3/5 positions

DECISION RATIONALE:
  Strong confluence of 4 signals. Volume confirms breakout.
  Regime supports. Risk:Reward acceptable. APPROVED.
NO-TRADE decisions are equally important:
DECISION: NO-TRADE
Stock: HDFCBANK
Reason: Composite score 48/100 — below 60 threshold
Reason: Only 1/4 strategies voting BUY
Reason: Volume below average — no confirmation
Action: Added to WATCHLIST for tomorrow

# MILESTONE 32 — EXPLAINABLE AUTONOMOUS DECISION ENGINE

## OBJECTIVE

Build a transparent decision engine that explains EVERY autonomous trading decision before execution.

The system must never return only BUY or SELL.

Every decision must include:

* What decision was made
* Why it was made
* Why it might fail
* Portfolio impact
* Risk assessment
* Confidence level
* Supporting signals
* Conflicting signals

The goal is to make Trading OS auditable, trustworthy, and suitable for future fully autonomous execution.

---

# FILE

engine/decision_engine.py

---

# WHY THIS MILESTONE EXISTS

Current system can calculate:

* Composite scores
* Risk metrics
* Market structure
* Portfolio exposure
* Orchestrator routing

But the final output is still difficult to audit.

Example:

BAD:

BUY RELIANCE

GOOD:

BUY RELIANCE

Because:

* EMA crossover confirmed
* MACD bullish
* Volume expansion
* Market regime bullish

Risks:

* RSI elevated
* Sector concentration increasing

Expected reward exceeds risk by 3.3x

This milestone creates that explanation layer.

---

# CORE RESPONSIBILITY

Create a centralized engine that converts all trading intelligence into a single explainable decision object.

The engine must support:

BUY

SELL

HOLD

NO_TRADE

---

# INPUTS

Decision engine should consume outputs from:

## Orchestrator

* bucket assignment
* composite score
* signal contributions
* confidence score

## Portfolio Risk Engine

* deployment %
* bucket utilization
* drawdown status
* correlation warnings
* sector concentration

## Market Structure

* trend state
* breakout status
* breakdown status
* consolidation status

## Scoring Engine

* technical score
* volume score
* sentiment score
* structure score

## Position Lifecycle

* current state
* cooldown status
* holding duration

---

# OUTPUT OBJECT

Standardized structure:


---

# DECISION TYPES

## BUY

Conditions:

* score above threshold
* risk engine approval
* not in cooldown
* capital available
* bucket capacity available

---

## SELL

Conditions:

* stop hit
* target hit
* trailing stop triggered
* structure breakdown
* risk override
* lifecycle exit

---

## HOLD

Conditions:

* existing position
* no exit trigger

---

## NO_TRADE

Conditions:

* weak score
* risk rejection
* correlation rejection
* exposure limits reached
* cooldown active

---

# REASONS FOR

Must provide human-readable positives.

Examples:

```text
EMA crossover confirmed

MACD bullish crossover

Volume 2.3x average

Breakout above resistance

Higher highs / higher lows structure

Bull market regime

Strong relative strength

Composite score above threshold
```

---

# REASONS AGAINST

Must provide human-readable warnings.

Examples:

```text
RSI approaching overbought

Sector exposure elevated

Portfolio already heavily deployed

Correlation with existing holdings

Market volatility increasing

Weak sentiment

Near major resistance
```

---

# CONFIDENCE SCORE

Range:

0-100

Source:

Orchestrator confidence score.

Decision engine should display:

```text
Low Confidence:
0-49

Medium Confidence:
50-69

High Confidence:
70-84

Very High Confidence:
85+
```

---

# RISK ASSESSMENT BLOCK


```

Data source:

Portfolio Risk Engine.

---

# PORTFOLIO IMPACT BLOCK


```

Purpose:

Show exactly how this trade changes portfolio risk.

---

# DECISION EXPLANATION TEXT

Create formatted summary.

Example:

DECISION: BUY

Stock: RELIANCE

Bucket: Swing Trading

Confidence: 78%

Composite Score: 72/100

REASONS FOR:

EMA crossover confirmed

MACD bullish crossover

Volume 2.3x average

Hammer pattern near MA20 support

Bull market regime

REASONS AGAINST:

RSI elevated

Sector exposure already 25%

RISK:

Entry ₹2847

Stop ₹2762

Target ₹3130

Risk Reward 1:3.3

Position Size 7%

PORTFOLIO IMPACT:

Current Deployment 45%

Post Trade Deployment 52%

Bucket Usage 3/5

FINAL VERDICT:

BUY APPROVED

---

# DECISION LOGGING

Create new persistent log.

File:

logs/decision_log.csv

Optional Supabase table:

decision_log

Columns:

timestamp

stock

bucket

decision

confidence

composite_score

reasons_for

reasons_against

entry

stop

target

risk_reward

portfolio_impact

execution_allowed

---

# STREAMLIT INTEGRATION

Create display-ready dataframe.

Function:

get_decision_dashboard_df()

Purpose:

Show latest decisions.

Columns:

Timestamp

Stock

Bucket

Decision

Confidence

Score

Risk Reward

Deployment Impact

Approved

---

# FUTURE USE

Milestone 33+

Execution loop should NOT make decisions directly.

Execution loop must call:

decision_engine

and only execute trades that return:

execution_allowed = True

Decision engine becomes the final approval layer before trade execution.

---

# SUCCESS CRITERIA

Milestone is complete when:

✓ Every BUY has a full explanation

✓ Every SELL has a full explanation

✓ Every HOLD has a full explanation

✓ Every NO_TRADE has a full explanation

✓ Portfolio impact is shown

✓ Risk assessment is shown

✓ Confidence is shown

✓ Decisions are logged

✓ Streamlit can display latest decisions

✓ Execution loop can consume decision output

This milestone is primarily an explainability and audit layer, not a signal generation engine.




---
Milestone 33 — Zerodha Integration (Live Paper → Real)
File: brokers/zerodha\_connector.py

Connect Kite API
Fetch live quotes (replace yfinance for live data)
Place paper orders via Kite sandbox
Place real orders (manual confirmation required initially)
Real-time P&L tracking
Order status monitoring
GTT (Good Till Triggered) order support for stop losses

---
Milestone 34 — Supabase Persistent Storage
File: database/supabase\_client.py

Replace CSV files with Supabase (PostgreSQL)
Persist trades across cloud restarts
Historical performance database
Multi-session portfolio state
Audit trail for all decisions

---
Milestone 35 — FII/DII Intelligence Layer
File: strategies/institutional\_flow.py

Fetch FII/DII daily data from NSE website
Track net FII buying/selling (₹ crores)
Track net DII buying/selling (₹ crores)
Detect institutional accumulation patterns
Add FII/DII flow score to composite scoring engine
Alert on unusual institutional activity

---
ENGINEERING RULES — ALWAYS FOLLOW
Architecture

One file per strategy / engine / component
No monolithic files — keep modules small and focused
Every module independently testable
Clean imports — no circular dependencies
Graceful error handling everywhere (never crash the dashboard)
Prevent duplicate trade execution (check state before acting)

Code Quality

Comments on every function explaining WHAT and WHY
Explain design decisions before writing code
Use type hints where practical
Structured logging (not just print statements)
Config-driven (no hardcoded values in strategy files)

Safety

Human oversight on all real money decisions (initially)
Paper trading always runs parallel to validate new strategies
Never deploy untested strategy to live trading
Always backtest on 2y+ data before enabling
Always explain risk before enabling any feature

Git Workflow
After every milestone:
git add .
git commit -m "Milestone XX: description"
git push
---
DASHBOARD EVOLUTION PLAN
Current tabs (8):

Dashboard
Market Regime
Scanner
Stock Score
RS Ranking
Backtesting
Strategy Comparison
Logs


---
HOW TO HELP ME
When assisting with this project:

Think like a professional quant architect — design for scalability and safety
Teach gradually — explain what we're building and WHY before writing code
Beginner-friendly — I may not know terminal commands, always include them
Modular first — always suggest the cleanest module boundary
Safety first — suggest the safest implementation path, not the cleverest
Avoid unnecessary complexity — simple and working beats clever and fragile
Always remind me to git add, commit, push after completing a milestone
Never expose API keys, passwords, or secrets in code
Handle failures gracefully — every external call needs try/except
One milestone at a time — don't overwhelm, build incrementally

---
CURRENT SESSION CONTEXT
(Update this section at the start of each conversation)
Last completed milestone: Milestone 30 — Advanced Portfolio Risk Engine
Next planned milestone:   Milestone 31 — Strategy Orchestration Engine
---
Trading OS v4.0 — Firoj Khan
"Survive first. Profit second. Automate third."
Never give full python file for any modification or correction etc. only give patches if same file is already available. Give full file only when it is fully new