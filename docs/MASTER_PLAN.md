# Trading OS - Master Plan

**Project Owner:** Firoj Khan
**Chief Technical Advisor:** ChatGPT
**Implementation Engineer:** Claude
**Version:** 1.0
**Status:** Sprint 1

---

# Vision

Build a professional-grade autonomous trading platform for Indian markets that:

- Protects capital first.
- Generates explainable trading decisions.
- Can operate autonomously.
- Supports paper trading before live trading.
- Integrates with Zerodha.
- Runs independently of a laptop.
- Has Android as the primary user interface.
- Uses only low-cost or free tools wherever possible.

---

# Core Principles

1. Capital Protection > Profit
2. Evidence Before Changes
3. No Duplicate Logic
4. Single Source of Truth
5. Every Feature Must Improve:
   - Profitability
   - Reliability
   - Maintainability
   - Cost
   - User Experience

---

# Technology Stack

Current

- Python
- Streamlit
- GitHub
- Supabase
- yfinance

Future

- FastAPI
- Android
- Zerodha Kite Connect
- VPS (only when required)

---

# Development Workflow

ChatGPT

- Product roadmap
- Architecture
- Design
- Code review
- Prioritization
- Claude prompt generation

Claude

- Code implementation
- Refactoring
- Small feature development

Firoj

- Testing
- Validation
- Final approval
- GitHub management

---

# Current Sprint

Sprint 1

Goal:

Understand Trading OS completely before modifying trading logic.

Deliverables

- Architecture Audit
- Trading Logic Audit
- Risk Audit
- Decision Flow Audit
- Top Improvement Roadmap

Status:

In Progress

---

# Current Known Issues

001 - Intraday bucket remains paused

002 - Composite score inconsistency (to verify)

003 - Very low trade frequency

004 - Limited observability

005 - No automated regression testing

---

# Approved Development Order

Phase 1

Audit & Validation

Phase 2

Observability

Phase 3

Strategy Improvements

Phase 4

Backend (FastAPI)

Phase 5

Android App

Phase 6

Live Zerodha Trading

---

# Current Branches

main

Stable Release

restore

Baseline Backup

feature/trading-analytics

Current Development

---

# Current AI Policy

Never ask Claude open-ended questions.

Every Claude prompt must include:

- Objective
- Background
- Allowed files
- Forbidden files
- Acceptance criteria
- Testing steps
- Rollback instructions

---

# Definition of Done

No feature is complete unless:

- Works correctly
- Doesn't break existing behavior
- Has logs
- Is reviewed
- Is tested
- Is documented

---

# Long-Term Goal

Trading OS v2.0

Features

- FastAPI Backend
- Android App
- Autonomous Scheduler
- Zerodha Integration
- Explainable AI
- Portfolio Analytics
- Multi-strategy Validation