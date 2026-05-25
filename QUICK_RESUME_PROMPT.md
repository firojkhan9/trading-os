# Trading OS — Quick Resume Prompt
# Paste this at the start of every new conversation (instead of the full prompt)
# Update the 3 lines at the bottom after each session

---

I am building "Firoj Khan's Trading OS" — an AI-assisted autonomous paper-trading
system for Indian equity markets (NSE). Built with Python, Streamlit, yfinance,
deployed on Streamlit Cloud. GitHub: https://github.com/firojkhan9/trading-os

PHILOSOPHY: Capital protection first. Consistency over big wins. NO-TRADE is valid.
AI assists — it does not predict. Beginner-friendly explanations always.

TECH: Python · Pandas · Streamlit · yfinance · Google Sheets (config) · SQLite (future)

COMPLETED (Milestones 1–23):
MA+RSI · EMA · Bollinger · MACD · Combined Signal · Backtesting · Paper Trading ·
Risk Manager · Market Regime · RS Ranking · Scoring Engine (0-100, 8 dimensions) ·
Explainability Engine · Fundamental Engine · Sentiment Engine (5 sources) ·
Dynamic Watchlist · Strategy Comparison · Cloud Deployment

CURRENT PROJECT STRUCTURE (key files):
app.py (root) · strategies/ · portfolio/ · risk/ · config/ · logs/ · engine/ (upcoming)

ARCHITECTURE DIRECTION (Phase 4):
Building a 3-bucket autonomous portfolio engine:
  • Long-Term  ₹3,00,000 — Fundamentals + Trend + RS (low frequency)
  • Swing      ₹1,50,000 — EMA + MACD + Volume + RS (medium frequency)
  • Intraday   ₹50,000   — VWAP + Volume + ATR (high frequency, future)

UPCOMING MILESTONES:
  24 · Capital Allocation Engine     → portfolio/capital_engine.py
  25 · Position Lifecycle Manager    → portfolio/position_manager.py
  26 · Autonomous Execution Loop     → engine/execution_loop.py
  27 · Volume Intelligence Engine    → strategies/volume_engine.py
  28 · Candlestick Engine            → strategies/candlestick_engine.py
  29 · Market Structure Engine       → strategies/market_structure.py
  30 · Advanced Portfolio Risk       → risk/portfolio_risk.py
  31 · Strategy Orchestration Engine → strategies/orchestrator.py
  32 · Explainable Decision Engine   → engine/decision_engine.py
  33 · Zerodha Integration           → brokers/zerodha_connector.py
  34 · Supabase Storage              → database/supabase_client.py
  35 · FII/DII Intelligence          → strategies/institutional_flow.py

ENGINEERING RULES:
One file per module · Modular architecture · Comments everywhere ·
Graceful error handling · No hardcoded values · Always explain before coding ·
Remind git add/commit/push after each milestone · Never expose secrets

---
LAST COMPLETED : Milestone 23 — Sentiment Analysis Engine (5 sources + diagnostics)
CURRENT FIXES  : Scanner persistence fix · Backtest period options · Sentiment diagnostics
NEXT MILESTONE : Milestone 24 — Capital Allocation Engine
