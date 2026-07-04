# Trading OS — M38 Intraday Engine (VCPS) Roadmap

**Purpose of this doc:** Milestone 38 is too large to build in one shot, so it's
broken into sub-milestones M38A, M38B, M38C... Upload this file to this
project's knowledge so any new chat has the full picture. To resume work,
just say **"start M38D"** (or whichever letter is next) and Claude should
read this doc + the current codebase state and continue in the same style.

---

## What M38 Is

M38 implements the **Volume Compression Pullback Strategy (VCPS)** —
`Volume_Based_Counter_Trend_Entry.md` in the project files — as a fully
systematic intraday engine, replacing the subjective YouTube-strategy
version. Full original spec: 15 modules. Below is the sub-milestone mapping
that groups those modules into buildable, testable chunks.

**Core rule for every sub-milestone:** reuse existing engines
(`market_structure.py`, `scoring_engine.py`, `capital_engine.py`,
`position_manager.py`) — never duplicate logic that already exists
elsewhere in the codebase.

---

## Sub-Milestone Map

| ID | Spec Module(s) | What It Does | File(s) | Status |
|----|-----------------|--------------|---------|--------|
| **M38A** | Module 2 — Sector Strength Engine | Ranks all watchlist sectors by 40% Relative Strength + 30% Sector Return + 20% Breadth + 10% Volume Expansion. Returns top 3 sectors. | `strategies/sector_strength.py` | ✅ Done |
| **M38B** | Module 3 — Stock Selection Filter | Narrows top-3-sector stocks to F&O-eligible, liquid, real-range candidates (volume ≥1.5x avg, ATR ≥1%, price >₹100, traded value ≥₹5Cr). | `strategies/stock_selection_filter.py`, `config/fo_universe.py` | ✅ Done |
| **M38C** | Module 4 + 5 — Market Structure + Supply/Demand Zones | Classifies each eligible stock as UPTREND/DOWNTREND/RANGE (RANGE rejected), detects BOS/CHOCH, finds nearest Demand/Supply zone with distance %. | `strategies/market_structure_validator.py` | ✅ Done |
| **M38D** | Module 1 + 6 + 7 — Market Direction Filter + Volume Compression + Volatility Compression | Intraday-specific NIFTY direction gate (VWAP + 20 EMA + watchlist breadth proxy, on 5-min data). Detects exhaustion pullbacks: volume < 50% of 20-bar avg AND bottom 10th percentile; ATR < 80% of ATR20 avg AND BB width < 20-bar avg. Uses NIFTYBEES.NS as proxy since index tickers carry no volume. | `strategies/intraday_direction.py` | ✅ Done |
| **M38E** | Module 8 — Entry Logic | Combines M38A-D outputs: LONG if regime=BULLISH + sector top-3 + UPTREND + compression=True + near Demand zone + breaks compression candle high. SHORT is the mirror. | `strategies/intraday_engine.py` (new) | ✅ Done |
| **M38F** | Module 9 + 10 — Stop Loss Engine + Target Engine | Stop = max(zone edge, compression candle edge, ATR stop) for LONG / min(...) for SHORT. Target 1 = 2R, Target 2 = nearest opposite zone edge, Target 3 = 10 EMA trail (dynamic, re-checked live). | `strategies/intraday_engine.py` | ✅ Done |
| **M38G** | Module 11 — Trade Management | At Target 1: book 50%, move stop to breakeven. Remainder trails via 10 EMA (candle closes wrong side of EMA + next candle breaks its high/low). Mandatory 3:15 PM hard exit overrides everything. | `portfolio/position_manager.py` (patch), `strategies/intraday_engine.py` | ✅ Done |
| **M38H** | Module 12 — Trade Quality Score | 0-100 composite: Regime 15 + Sector 20 + Structure 20 + Zone 15 + Vol Compression 10 + Volatility Compression 10 + Risk:Reward 10. Grades A+ (90+) down to Reject (<60). Signals scoring <60 are pulled from long/short signals into `watching` with the reason. | `strategies/intraday_engine.py`, `strategies/intraday_direction.py` (patch) | ✅ Done |
| **M38I** | Module 13 — Scanner Integration | Add intraday columns (Market Regime, Sector Rank, Structure, Zones, Compression flags, Stop, Targets, Trade Score/Grade) to a dashboard tab, same pattern as existing Scanner tab. | `app.py` (patch), `strategies/performance_scanner.py` (patch, optional) | Not started |
| **M38J** | Module 14 — Automation-Ready Output | Standardized dict per spec (`stock`, `signal`, `entry_price`, `stop_price`, `target_1/2`, `trade_score`, `trade_grade`, `market_regime`, `sector_rank`, `structure`) for `execution_loop.py` to consume once intraday bucket goes live. | `strategies/intraday_engine.py` | Not started |
| **M38K** | Module 15 — Backtest Integration | Add VCPS to the backtesting framework: Win Rate, Profit Factor, Avg R-Multiple, Expectancy, Max Drawdown, Sharpe, Sortino, Avg Holding Time, Sector-wise and Regime-wise performance breakdowns. | `strategies/intraday_backtest.py` (new) | Not started |

---

## Engineering Conventions Used So Far (keep consistent)

- **Patch-only for existing files** — `REPLACE...WITH` or `str_replace` blocks
  only. Full files only when the file is brand new.
- **New engine files** follow the pattern: constants at top → per-item
  helper functions (prefixed `_`) → one batch/master function using
  `ThreadPoolExecutor(max_workers=SCANNER_MAX_WORKERS)` → a convenience
  "get_X" wrapper for dashboard/other-module use.
- **Every rejection gets a reason string** — never a silent skip. Matches
  the project's audit-everything philosophy (decision_engine.py,
  orchestrator.py, candlestick_engine.py all do this).
- **Dashboard blocks** go in `app.py` Tab 2 (Market Regime tab), guarded
  by a button + `st.session_state` cache, same pattern as the M38A/M38B/M38C
  blocks already added.
- **Data fetch pattern**: `yf.download(period=..., interval="1d", auto_adjust=True)`
  → flatten multi-index columns → `dropna(subset=["Close"])` → filter
  `Close > 0` → minimum row-count guard before returning `None`.
- **F&O universe** (`config/fo_universe.py`) follows the same
  Google-Sheet → CSV → built-in-default priority as `watchlist_manager.py`.

---

## Files Created So Far (M38 series)

- `strategies/sector_strength.py` (M38A)
- `strategies/stock_selection_filter.py` (M38B)
- `config/fo_universe.py` (M38B)
- `strategies/market_structure_validator.py` (M38C)
- `strategies/intraday_direction.py` (M38D)
- `strategies/intraday_engine.py` (M38E)

## Files Patched So Far (M38 series)

- `app.py` — Tab 2 (Market Regime), added Sector Strength Ranking (M38A),
  Stock Selection Filter (M38B), and Intraday Market Direction Filter +
  Compression Checker (M38D) display blocks, all button-triggered with
  session_state caching. (M38C's own dashboard block is still pending —
  currently `market_structure_validator.py` is called by other modules
  but has no standalone Tab 2 block yet; worth a quick follow-up patch.)

---

## How To Resume

1. Open a new chat in this project (or continue this one).
2. Say: **"start M38D"** (or the relevant next letter).
3. Claude should re-read this doc's table, confirm the next module(s),
   check `strategies/market_structure_validator.py` and the M38B/M38C
   `app.py` blocks for the exact shape of data being passed forward,
   then build the next piece in the same conventions.
4. After each sub-milestone: `git add`, `git commit -m "M38X: description"`,
   `git push` — same as every other milestone in this project.

---

*Last updated: after M38H (Trade Quality Score Engine — 0-100 composite score, A+ to REJECT grading, sub-60 signals auto-demoted to watching)*
