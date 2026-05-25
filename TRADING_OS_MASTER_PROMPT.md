# 🤖 Firoj Khan's Trading OS — Master Project Prompt
# Use this at the start of every new conversation with Claude or Cursor AI

---

## WHO I AM

I am Firoj Khan — a trader and entrepreneur building an AI-assisted portfolio
management and autonomous paper-trading operating system for Indian equity markets.

My background:
- Occasional trader on Zerodha (NSE/BSE)
- Strong in analytics, Excel, dashboards, structured logic, business thinking
- Beginner in coding, APIs, AI engineering, and algorithmic trading
- Learning through building — prefer practical, motivating, step-by-step guidance
- Can get overwhelmed by excessive technical detail — keep explanations beginner-friendly
- Never skip setup instructions or terminal commands

---

## PRIMARY OBJECTIVES

1. Generate consistent side income safely through disciplined paper trading
2. Build a system for consistent, rules-based income generation
3. Build long-term wealth through intelligent portfolio management
4. Create a fully autonomous AI-assisted portfolio operating system
5. Reduce emotional decision-making through systematic rules
6. Continuously improve through backtesting, learning, and iteration

---

## CORE PHILOSOPHY — NON-NEGOTIABLE

### Capital Protection First
- Protecting capital is MORE important than maximizing profit
- Prioritize risk-adjusted returns over raw returns
- Avoid unrealistic promises or over-optimized strategies
- Long-term survivability matters more than short-term gains
- Cash is a valid and often optimal position
- NO-TRADE is a legitimate and important decision

### Performance Philosophy
Optimize for:
- Consistency over big wins
- Survivability through drawdowns
- Controlled risk exposure
- Portfolio stability
- Disciplined, rule-based execution

NOT: unrealistic profit maximization or overtrading

### AI Philosophy
AI assists in:
- Ranking opportunities by quality
- Filtering out bad trades before they happen
- Improving decision quality through data synthesis
- Explaining reasoning in plain English
- Reducing emotional and impulsive decisions

AI is NOT a magical prediction machine. It supports human judgment.

---

## TECH STACK

- Python, Pandas, NumPy
- Streamlit (dashboard)
- Plotly (charts)
- yfinance (market data)
- SQLite → Supabase (storage, future)
- GitHub (version control)
- Streamlit Cloud (deployment)
- Cursor AI + Claude (development assistants)
- Zerodha Kite API (future — live trading)

---

## PROJECT STRUCTURE

```
trading_os/
├── app.py                          ← Streamlit dashboard (repo root)
├── config/
│   ├── settings.py                 ← Central path + risk settings
│   ├── settings_loader.py          ← Google Sheets settings loader
│   └── strategy_settings.py       ← Exposes settings to all modules
├── strategies/
│   ├── indicators.py               ← MA20 + RSI
│   ├── ema_strategy.py             ← EMA Crossover
│   ├── bollinger_strategy.py       ← Bollinger Bands + RSI filter
│   ├── macd_strategy.py            ← MACD Crossover
│   ├── combined_signal.py          ← 4-strategy voting engine
│   ├── combined_backtest.py        ← Combined signal backtester
│   ├── strategy_comparison.py      ← Side-by-side strategy comparison
│   ├── backtest.py                 ← MA+RSI backtester
│   ├── paper_trader.py             ← Paper trade execution
│   ├── market_regime.py            ← NIFTY regime detection
│   ├── relative_strength.py        ← RS ranking vs NIFTY
│   ├── scoring_engine.py           ← 8-dimension composite score (0-100)
│   ├── explainability_engine.py    ← Plain English signal explanations
│   ├── fundamental_engine.py       ← P/E, ROE, growth, health scoring
│   ├── sentiment_engine.py         ← News sentiment (5 sources)
│   ├── performance_scanner.py      ← Full watchlist scanner
│   └── watchlist_manager.py        ← Dynamic watchlist (CSV + Google Sheets)
├── logs/
│   ├── signal_logger.py
│   ├── signal_log.csv
│   └── paper_trades.csv
├── portfolio/
│   └── performance.py              ← Portfolio performance reporting
├── risk/
│   └── risk_manager.py             ← Stop loss, position limits, daily loss
├── watchlist.csv                   ← Active stock universe
├── requirements.txt
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml                ← Password (never commit this)
└── .gitignore
```

---

## COMPLETED MILESTONES ✅

| # | Milestone | Status |
|---|-----------|--------|
| 1  | Python environment setup | ✅ Done |
| 2  | Single stock data fetcher | ✅ Done |
| 3  | 10-stock watchlist engine | ✅ Done |
| 4  | Live browser dashboard (Streamlit) | ✅ Done |
| 5  | Technical indicators (MA20 + RSI) | ✅ Done |
| 6  | Automatic signal logger | ✅ Done |
| 7  | Paper trading simulator | ✅ Done |
| 8  | Portfolio performance report | ✅ Done |
| 9  | Risk management rules | ✅ Done |
| 10 | Strategy backtesting engine | ✅ Done |
| 11 | Cloud deployment (Streamlit Cloud) | ✅ Done |
| 12 | EMA Crossover Strategy | ✅ Done |
| 13 | Bollinger Bands Strategy | ✅ Done |
| 14 | MACD Strategy | ✅ Done |
| 15 | Strategy Comparison Dashboard | ✅ Done |
| 16 | Combined Signal Engine (4-strategy voting) | ✅ Done |
| 17 | Market Regime Detection (NIFTY-based) | ✅ Done |
| 18 | Dynamic Watchlist System (CSV + Google Sheets) | ✅ Done |
| 19 | Relative Strength Ranking vs NIFTY | ✅ Done |
| 20 | Combined Intelligence Scoring Engine (0-100) | ✅ Done |
| 21 | Explainability Engine | ✅ Done |
| 22 | Fundamental Intelligence Layer | ✅ Done |
| 23 | Sentiment Analysis Engine (5 news sources) | ✅ Done |

---

## CURRENT RISK SETTINGS

| Setting | Value |
|---------|-------|
| Stop Loss | 6% |
| Profit Target | 15% |
| Trailing Stop | 4% below peak |
| Max Position Size | 10% of capital |
| Max Open Positions | 5 stocks |
| Starting Capital (paper) | ₹1,00,000 |
| Brokerage | 0.1% per trade |
| Daily Loss Limit | 5% |

All configurable via Google Sheets (no code changes needed).

---

## CURRENT WATCHLIST

RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK,
HINDUNILVR, SBIN, BHARTIARTL, ITC, KOTAKBANK

---

## DEPLOYMENT

- GitHub: https://github.com/firojkhan9/trading-os
- Live App: Streamlit Cloud (password protected)
- Settings: Google Sheets (remote config)
- Watchlist: Google Sheets (remote management)

---

## FUTURE IMPROVEMENTS LOGGED

| ID | Description |
|----|-------------|
| FI-001 | Replace dropdown with clickable row selector (done in Scanner) |
| FI-002 | Add FII/DII flow data to fundamental engine |
| FI-003 | Supabase integration for persistent cloud trade storage |

---

## ═══════════════════════════════════════════════════
## NEXT PHASE — AUTONOMOUS PORTFOLIO OPERATING SYSTEM
## ═══════════════════════════════════════════════════

The system now evolves from signal generation dashboard
to autonomous portfolio execution and lifecycle management.

---

## ARCHITECTURAL VISION — THREE-BUCKET PORTFOLIO ENGINE

### Total Capital: ₹5,00,000 (fully configurable)

| Bucket | Capital | Style | Frequency |
|--------|---------|-------|-----------|
| Long-Term | ₹3,00,000 (60%) | Fundamentals + Trend + Sector | Low — weeks to months |
| Swing Trading | ₹1,50,000 (30%) | Momentum + EMA + RS + Volume | Medium — days to weeks |
| Intraday | ₹50,000 (10%) | VWAP + Volume + ATR + Momentum | High — same day |

Each bucket operates completely independently:
- own capital pool
- own strategy weights
- own risk rules
- own position limits
- own holding periods
- own performance tracking

---

## NEXT MILESTONES ROADMAP

### PHASE 4A — CAPITAL & EXECUTION FOUNDATION
*(Build the engine room — do this before any new strategies)*

---

#### Milestone 24 — Capital Allocation Engine
**File:** `portfolio/capital_engine.py`

Responsibilities:
- Define and manage three capital buckets (Long-Term, Swing, Intraday)
- Track available cash per bucket
- Track deployed capital per bucket
- Enforce bucket-level position limits
- Enforce portfolio-level exposure limits
- Calculate bucket-level P&L and returns
- Support configurable bucket sizes (% of total capital)
- Prevent cross-bucket capital leakage

Dashboard additions:
- Bucket summary panel (capital, deployed, available, P&L per bucket)
- Visual capital allocation chart

---

#### Milestone 25 — Position Lifecycle Manager
**File:** `portfolio/position_manager.py`

Every trade must move through defined states:

```
WATCHLIST → READY → ENTERED → HOLDING → PARTIAL_EXIT
         → TRAILING → EXITED → COOLDOWN
         → REJECTED (with reason logged)
```

Responsibilities:
- Entry management (size, timing, confirmation)
- Scaling in (add to winner on confirmation)
- Scaling out (partial profit booking)
- Stop loss enforcement (hard stop)
- Trailing stop management (dynamic)
- Time-based exits (max holding period per bucket)
- Forced exits (regime change, daily loss limit)
- Cooldown periods (no re-entry for N days after stop loss)
- Full state audit trail in SQLite/CSV

---

#### Milestone 26 — Autonomous Execution Loop
**File:** `engine/execution_loop.py`

A scheduler that runs continuously during market hours and:

Every N minutes:
1. Fetch latest market data for all watchlist stocks
2. Update all indicators (MA, EMA, RSI, MACD, BB, Volume)
3. Recalculate intelligence scores
4. Check market regime (NIFTY)
5. Scan for new opportunities (by bucket)
6. Evaluate all open positions (stop loss, trailing, target)
7. Check portfolio constraints (exposure, daily loss, bucket limits)
8. Execute paper trades autonomously
9. Log every decision with full explanation (including NO-TRADE reasons)
10. Update dashboard metrics

Scheduler requirements:
- Configurable interval (e.g. every 5 / 15 / 30 minutes)
- Market hours awareness (9:15 AM – 3:30 PM IST, Mon–Fri)
- Pre-market preparation run (9:00 AM)
- Post-market summary run (3:35 PM)
- Safe shutdown on error
- Pause/resume support
- No duplicate trade execution (idempotent)
- Full error recovery with logging

---

### PHASE 4B — INTELLIGENCE EXPANSION
*(Add new signal types to improve decision quality)*

---

#### Milestone 27 — Volume Intelligence Engine
**File:** `strategies/volume_engine.py`

Volume is a confirmation tool — never a standalone signal.

Implement:
- Volume spike detection (vs 20-day average volume)
- Unusual volume alert (>2x average = significant)
- Volume trend analysis (rising/falling volume in trend)
- OBV (On-Balance Volume) — accumulation vs distribution
- Chaikin Money Flow — buying vs selling pressure
- Breakout volume confirmation (breakout without volume = weak)
- Volume-weighted confidence adjustment in scoring engine

Rule: Any BUY signal with volume < average volume gets confidence reduced by 20%.

---

#### Milestone 28 — Candlestick + Price Action Engine
**File:** `strategies/candlestick_engine.py`

Priority patterns to detect:
- Hammer (bullish reversal at support)
- Shooting Star (bearish reversal at resistance)
- Bullish Engulfing / Bearish Engulfing
- Doji (indecision — watch for confirmation)
- Morning Star (3-candle bullish reversal)
- Evening Star (3-candle bearish reversal)
- Breakout candle (large body, high volume)

CRITICAL RULE — Candlestick patterns NEVER act alone.
A pattern is only valid when confirmed by ALL of:
1. Trend direction (EMA/MA alignment)
2. Volume (above average on signal candle)
3. Support/Resistance level proximity
4. Market regime (not in bear market for BUY signals)

Unconfirmed patterns = IGNORED (logged as REJECTED with reason)

---

#### Milestone 29 — Market Structure Engine
**File:** `strategies/market_structure.py`

Implement:
- Support and resistance zone detection (recent swing highs/lows)
- Breakout detection (price closes above resistance with volume)
- Breakdown detection (price closes below support)
- Consolidation detection (low ATR, tight BB width)
- Volatility compression alerts (squeeze before expansion)
- Higher Highs / Higher Lows detection (uptrend structure)
- Lower Highs / Lower Lows detection (downtrend structure)
- Price structure scoring contribution to composite score

---

### PHASE 4C — ADVANCED RISK INTELLIGENCE
*(Portfolio-level protection, not just trade-level)*

---

#### Milestone 30 — Advanced Portfolio Risk Engine
**File:** `risk/portfolio_risk.py`

Move beyond per-trade stop loss to portfolio intelligence:

- Sector exposure limits (max 30% in any one sector)
- Correlation awareness (avoid 3+ highly correlated stocks)
- Bucket drawdown control (pause bucket if down >10%)
- Portfolio daily loss limit (halt all trading if down >5% today)
- Max simultaneous exposure (never >70% capital deployed)
- Volatility-adjusted position sizing (smaller size in volatile markets)
- ATR-based stop loss (stop = entry - 2x ATR, not fixed %)
- Regime-aware aggression (reduce size in WEAK BULL / SIDEWAYS)

---

### PHASE 4D — AUTONOMOUS INTELLIGENCE
*(The brain of the system)*

---

#### Milestone 31 — Strategy Orchestration Engine
**File:** `strategies/orchestrator.py`

Per-bucket strategy configurations:

**Long-Term Bucket:**
- Fundamental Score weight: 40%
- Trend (MA/EMA) weight: 30%
- Relative Strength weight: 20%
- Sentiment weight: 10%
- Min composite score to enter: 70/100
- Min holding period: 20 trading days

**Swing Trading Bucket:**
- EMA Crossover weight: 25%
- MACD weight: 25%
- Relative Strength weight: 20%
- Volume Confirmation weight: 15%
- Candlestick Pattern weight: 15%
- Min composite score to enter: 60/100
- Max holding period: 15 trading days

**Intraday Bucket (future):**
- VWAP position weight: 30%
- Volume spike weight: 25%
- Momentum (RSI intraday) weight: 25%
- ATR volatility weight: 20%
- Same-day exit mandatory

Orchestrator responsibilities:
- Route each opportunity to the correct bucket
- Resolve signal conflicts between strategies
- Calculate bucket-specific confidence score
- Reject weak setups before they reach execution
- Identify confluence (multiple signals agreeing = higher confidence)
- Log all routing decisions with reasons

---

#### Milestone 32 — Explainable Autonomous Decision Engine
**File:** `engine/decision_engine.py`

Every autonomous decision (BUY, SELL, HOLD, NO-TRADE) must produce:

```
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
```

NO-TRADE decisions are equally important:
```
DECISION: NO-TRADE
Stock: HDFCBANK
Reason: Composite score 48/100 — below 60 threshold
Reason: Only 1/4 strategies voting BUY
Reason: Volume below average — no confirmation
Action: Added to WATCHLIST for tomorrow
```

---

#### Milestone 33 — Zerodha Integration (Live Paper → Real)
**File:** `brokers/zerodha_connector.py`

- Connect Kite API
- Fetch live quotes (replace yfinance for live data)
- Place paper orders via Kite sandbox
- Place real orders (manual confirmation required initially)
- Real-time P&L tracking
- Order status monitoring
- GTT (Good Till Triggered) order support for stop losses

---

#### Milestone 34 — Supabase Persistent Storage
**File:** `database/supabase_client.py`

- Replace CSV files with Supabase (PostgreSQL)
- Persist trades across cloud restarts
- Historical performance database
- Multi-session portfolio state
- Audit trail for all decisions

---

#### Milestone 35 — FII/DII Intelligence Layer
**File:** `strategies/institutional_flow.py`

- Fetch FII/DII daily data from NSE website
- Track net FII buying/selling (₹ crores)
- Track net DII buying/selling (₹ crores)
- Detect institutional accumulation patterns
- Add FII/DII flow score to composite scoring engine
- Alert on unusual institutional activity

---

## ENGINEERING RULES — ALWAYS FOLLOW

### Architecture
- One file per strategy / engine / component
- No monolithic files — keep modules small and focused
- Every module independently testable
- Clean imports — no circular dependencies
- Graceful error handling everywhere (never crash the dashboard)
- Prevent duplicate trade execution (check state before acting)

### Code Quality
- Comments on every function explaining WHAT and WHY
- Explain design decisions before writing code
- Use type hints where practical
- Structured logging (not just print statements)
- Config-driven (no hardcoded values in strategy files)

### Safety
- Human oversight on all real money decisions (initially)
- Paper trading always runs parallel to validate new strategies
- Never deploy untested strategy to live trading
- Always backtest on 2y+ data before enabling
- Always explain risk before enabling any feature

### Git Workflow
After every milestone:
```
git add .
git commit -m "Milestone XX: description"
git push
```

---

## DASHBOARD EVOLUTION PLAN

Current tabs (8):
1. Dashboard
2. Market Regime
3. Scanner
4. Stock Score
5. RS Ranking
6. Backtesting
7. Strategy Comparison
8. Logs

Future tabs to add:
9. Portfolio Buckets (capital allocation, bucket P&L)
10. Autonomous Bot (start/stop/status, live decision log)
11. Position Lifecycle (all open trades with state)
12. Risk Dashboard (exposure, correlation, drawdown)
13. Volume Intelligence (unusual activity alerts)
14. Market Structure (support/resistance, breakouts)

---

## HOW TO HELP ME

When assisting with this project:

1. **Think like a professional quant architect** — design for scalability and safety
2. **Teach gradually** — explain what we're building and WHY before writing code
3. **Beginner-friendly** — I may not know terminal commands, always include them
4. **Modular first** — always suggest the cleanest module boundary
5. **Safety first** — suggest the safest implementation path, not the cleverest
6. **Avoid unnecessary complexity** — simple and working beats clever and fragile
7. **Always remind me** to git add, commit, push after completing a milestone
8. **Never expose** API keys, passwords, or secrets in code
9. **Handle failures gracefully** — every external call needs try/except
10. **One milestone at a time** — don't overwhelm, build incrementally

---

## CURRENT SESSION CONTEXT

*(Update this section at the start of each conversation)*

Last completed milestone: **Milestone 23 — Sentiment Analysis Engine**

Current bugs/fixes in progress:
- Scanner results reset on row click → FIXED (session_state)
- Sentiment engine returning no news → FIXED (5 sources + diagnostics)
- Backtest "no trades" confusion → FIXED (better explanation + 5y option)

Next planned milestone: **Milestone 24 — Capital Allocation Engine**

---

*Trading OS v4.0 — Firoj Khan*
*"Survive first. Profit second. Automate third."*
