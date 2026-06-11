# Trading OS — Quick Resume Prompt
 
# Paste this at the start of every new conversation (instead of the full prompt)
 
# Update the 3 lines at the bottom after each session
 
\---
 
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
• Long-Term  ₹3,60,000 — Fundamentals + Trend + RS (low frequency)
• Swing      ₹1,80,000 — EMA + MACD + Volume + RS (medium frequency)
• Intraday   ₹60,000   — VWAP + Volume + ATR (high frequency, future)
 
UPCOMING MILESTONES:
31 · Strategy Orchestration Engine → strategies/orchestrator.py
32 · Explainable Decision Engine   → engine/decision\_engine.py
33 · Zerodha Integration           → brokers/zerodha\_connector.py
34 · Supabase Storage              → database/supabase\_client.py
35 · FII/DII Intelligence          → strategies/institutional\_flow.py
 
ENGINEERING RULES:
One file per module · Modular architecture · Comments everywhere ·
Graceful error handling · No hardcoded values · Always explain before coding ·
Remind git add/commit/push after each milestone · Never expose secrets
 
\---
 
LAST COMPLETED : Milestone 31 — Strategy Orchestration Engine
CURRENT REQUIRED FIXES  :1.there is a time zone mismatch on auto pilot page. At morning 11am its showing around 2:30, 2.I have updated my watchlist with 1001 stock, now it's taking too much time to scan, is there a way to increase speed and efficiency?, 3. There is difference in composite score in the scanner and in stock score page. I ran scanner→ selected one stock→ ran stock score for that stock→ composite scores are different. i have uploaded the latest files. 4. I have created two tables in supabase: loop_decisions and orchestration_log.sql code given below for eference. Give logging codes accordingly.
NEXT MILESTONE : Milestone 32 — Explainable Autonomous Decision Engine
Dont give full python file if patches can be done in smaller edits. Only give full file when it is fully new
