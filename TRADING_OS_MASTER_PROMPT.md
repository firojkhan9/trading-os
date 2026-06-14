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
│   ├── settings\_trading_config.py  ← Google Sheets settings setting database fetcher
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
32 Explainable Autonomous Decision Engine ✅ Done
33 Database & State Foundation ✅ Done
34 Execution Loop Bug Fixes + Partial Exit ✅ Done
35 Speed, Caching & Score Consistency ✅ Done
36 FII/DII Intelligence Layer ✅ Done
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






---

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

Trading OS — Roadmap Gap Analysis & Implementation Plan
1. Gaps in the Current Roadmap
From reviewing the source code, implementation_plan2.md, and the master prompt, these are the real gaps between what exists today and what a reliable autonomous system needs:
Critical gaps (blocking automation):

execution_loop._run_buy_scan() uses approved and reject_reason variables that are never defined after the orchestrator integration — the loop will crash on any BUY attempt
loop_state.py has two duplicate Supabase insert blocks in log_decision() — every decision is written twice
loop_state.py uses a local JSON file for loop status — wiped on every Streamlit Cloud restart, meaning the loop appears STOPPED after every deploy
supabase_setup.sql is missing DDL for three tables: orchestration_log, loop_decisions, and decision_log — these are referenced by code but don't exist in the DB script
No NSE holiday calendar — the loop runs on market holidays (Republic Day, Diwali etc.)
Partial exit is detected but never executed — PARTIAL_EXIT is logged as a suggestion only

Functional gaps (reducing intelligence quality):

Scanner uses SCANNER_SKIP_FUNDAMENTALS = False but fetches fundamentals synchronously per stock — on a 1,000-stock watchlist this takes 30-60 minutes
Composite score differs between Scanner and Stock Score tab because Scanner uses tail(60) data while Stock Score uses 1y data — users notice this and it erodes trust
Fundamental data has no cache — every scan re-fetches yfinance fundamentals, hammering the API
Market regime has no fallback — if ^NSEI fails, the entire cycle fails
No intraday mandatory same-day exit safety net

Infrastructure gaps:

SCANNER_MAX_WORKERS is hardcoded at 20 in performance_scanner.py, not in settings.py
No loop_state Supabase table — state is local JSON only
No nse_holidays table — holidays not handled
capital_engine.bucket_sell doesn't accept a quantity_to_sell parameter — partial exits can't be automated


2. Milestone Dependencies
M33 (DB fixes + loop state)
  └─► M34 (execution loop bug fixes + partial exit)
        └─► M35 (speed + caching)
            └─► M36 (FII/DII Intelligence)
                  └─► M37 (Zerodha live data)
M33 must go first — the database is the foundation. You can't reliably test the loop until the Supabase tables exist and loop state persists across restarts.
M34 fixes the code bugs that would cause crashes. Once M33 and M34 are done, the loop is genuinely autonomous and reliable for the first time.
M35 is a performance milestone — the system works correctly after M34 but is slow on large watchlists. M35 makes it fast enough for 1,000 stocks.
M37 (Zerodha) depends on everything before it being stable — you don't connect live broker API to a buggy loop.

3. Recommended Implementation Order
M33 — Database & State Foundation
Files: supabase_setup.sql, loop_state.py
Deliverables:

Add missing DDL for orchestration_log, loop_decisions, decision_log to supabase_setup.sql
Add loop_state table DDL (persists loop status, interval, last_run, regime across restarts)
Add nse_holidays table DDL with 2025–2026 NSE holiday data pre-populated
Fix loop_state.py: remove duplicate Supabase insert block in log_decision()
Fix loop_state.py: read/write loop status from Supabase loop_state table instead of local JSON

M34 — Execution Loop Bug Fixes + Partial Exit
Files: execution_loop.py, capital_engine.py, position_manager.py
Deliverables:

Fix undefined approved / reject_reason in _run_buy_scan() — call _is_ok_to_buy() before checking orchestrator result
Implement automated partial exit: when update_position_price() returns PARTIAL_EXIT, calculate qty // 2, call bucket_sell(quantity_to_sell=qty//2), then call mark_partial_exit_done()
Add quantity_to_sell optional parameter to capital_engine.bucket_sell()
Update position_manager.mark_partial_exit_done() to subtract sold quantity from position_lifecycle
Add NSE holiday check using nse_holidays Supabase table in is_market_open()

M35 — Speed, Caching & Score Consistency
Files: performance_scanner.py, fundamental_engine.py, settings.py, market_regime.py
Deliverables:

Move SCANNER_MAX_WORKERS to settings.py (default 8, configurable via Google Sheets)
Add fundamental cache: store results in logs/fundamental_cache.json with TTL of 3 days — avoids re-fetching on every scan
Fix score consistency: Scanner and Stock Score both use same indicator period (1y data, tail(60) for indicators) so scores match
Implement 5-tier regime fallback: ^NSEI → NIFTYBEES.NS scaled → Supabase last known → local JSON last known → "SIDEWAYS" default
Expose FUNDAMENTAL_CACHE_TTL_DAYS = 3 in settings.py



---
M36 — FII/DII Intelligence Layer
File: strategies/institutional_flow.py

Fetch FII/DII daily data from NSE website
Track net FII buying/selling (₹ crores)
Track net DII buying/selling (₹ crores)
Detect institutional accumulation patterns
Add FII/DII flow score to composite scoring engine
Alert on unusual institutional activity




M37 — Zerodha Kite API Integration
Files: brokers/zerodha_connector.py (new), execution_loop.py (patch)
Deliverables:

Create brokers/zerodha_connector.py with Kite Connect integration
Replace yfinance live price fetch in execution loop with Kite quote API
Paper order routing: log orders to loop_decisions with source=KITE_PAPER
Real order routing: kite.place_order() with manual confirmation gate
GTT (Good Till Triggered) orders for stop losses
Real-time P&L tracking via Kite portfolio API


4. Risks
M33 risks:

Running the new supabase_setup.sql on a production DB that already has some tables — mitigated by CREATE TABLE IF NOT EXISTS (already used in existing script)
If loop_state Supabase table is added but old JSON still exists locally, there's a brief conflict window — mitigated by reading Supabase first, JSON as fallback

M34 risks:

Partial exit sends a sell order for half the position — if the price fetch fails mid-cycle, the partial sell could execute at a stale price — mitigate with a fresh price fetch immediately before partial sell execution
The approved/reject_reason bug has been silently catching exceptions in the loop — fixing it may reveal other issues downstream that were masked

M35 risks:

Fundamental cache of 3 days means Scanner may show slightly stale PE/ROE data — acceptable for a daily scanner, document this limitation clearly
Score consistency fix (using same data period for Scanner and Stock Score) will change Scanner scores slightly — users will notice different numbers initially, then see them stabilize

M37 risks:

Zerodha Kite Connect requires a daily token refresh (login) — the autonomous loop needs a token manager that handles re-auth without manual intervention
Rate limits: Kite API allows 3 requests/second for quotes — on a 1,000-stock watchlist this is a bottleneck; need to batch quote requests (Kite supports up to 500 symbols per quote call)
Live trading risk: even "paper" mode using Kite sandbox can have subtle differences from production — keep yfinance as a parallel fallback for validation


5. Expected Impact
MilestoneWhat changes for youM33Loop status survives Streamlit Cloud restarts. No more "loop appears stopped after deploy." Decision log writes correctly — no duplicates.M34Loop runs without crashing. Partial profits are automatically booked. Loop respects market holidays. The system is genuinely autonomous for the first time.M351,000-stock watchlist scans in under 3 minutes instead of 30+. Scanner scores match Stock Score tab — no more confusion. Fundamentals load from cache — less API hammering.M36Real-time prices replace 15-minute delayed yfinance data. Stop losses execute at accurate prices. Path to live trading is open.


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







CURRENT SESSION CONTEXT
(Update this section at the start of each conversation)
Last completed milestone: Milestone 36 — FII/DII Intelligence Layer
Next planned milestone:    see how we can work on intraday trading setup, I have provided one strategy from youtube video  Volume_Based_Counter_Trend_Entry.md 





---
Trading OS v4.0 — Firoj Khan
"Survive first. Profit second. Automate third."
Never give full python file for any modification or correction etc. only give patches if same file is already available. Give full file only when it is fully new