# Trading OS
# Master Architecture Decision Record (ADR)

Version: 1.0 (Final)
Status: APPROVED
Project: Trading OS
Authoritative Document: YES

---

# 1. Purpose

This document defines the approved software architecture for the Trading OS analytics framework.

It replaces all previous discussions, audits, proposals, experiments and architecture drafts.

From this point onward this document becomes the single source of truth for analytics implementation.

No future implementation should contradict this document unless this ADR itself is officially revised.

---

# 2. Project Overview

Trading OS is a modular autonomous trading platform for Indian equity markets.

Current characteristics:

- Single developer
- Single user
- Paper Trading
- Streamlit dashboard
- Supabase database
- CSV fallback everywhere
- Approximately 40 Python modules
- Sequential execution
- No distributed processing
- No microservices
- Heavy focus on maintainability
- Heavy focus on modularity
- Heavy focus on beginner-friendly architecture

Future roadmap includes:

- Zerodha Live Trading
- Android Dashboard
- Web Dashboard
- Strategy Analytics
- Portfolio Analytics
- Risk Analytics
- Capital Analytics
- Execution Funnel
- Decision Analytics
- Win/Loss Analytics
- Historical Analytics

The chosen architecture must support this evolution without requiring major redesign.

---

# 3. Guiding Principles

Every implementation related to analytics shall follow these principles.

## 3.1 Read Only

Analytics observes.

Execution decides.

Analytics must never influence trading decisions.

Analytics must never modify execution behaviour.

---

## 3.2 Single Source of Truth

Trading decisions are produced exactly once.

Analytics records those decisions.

Analytics never recalculates them.

---

## 3.3 No Duplicate Business Logic

Analytics must never:

- calculate indicators
- calculate scores
- calculate votes
- calculate regimes
- rerun strategies
- rerun filters

Everything must be copied from execution outputs.

---

## 3.4 Minimal Intrusion

Execution engine already works.

Analytics must require the smallest possible modification.

No redesign of execution pipeline is allowed.

---

## 3.5 High Maintainability

Trading OS is maintained primarily by one developer.

Architecture must remain understandable after years of development.

Code should favour clarity over sophistication.

---

## 3.6 KISS

Prefer simple architecture that solves today's real requirements.

Avoid complexity whose only justification is hypothetical future needs.

---

## 3.7 YAGNI

Do not build infrastructure until a real requirement exists.

Future extensibility is important.

Speculative complexity is not.

---

# 4. Problem Statement

Originally, the objective was to build a simple Trading Funnel.

Example:

Stocks Scanned

↓

Passed Score

↓

Passed Votes

↓

Passed Regime

↓

Passed Structure

↓

Passed Portfolio Risk

↓

Passed Capital

↓

Executed

During architecture review it became clear that implementing only a funnel would create technical debt because future analytics would require redesign.

The scope therefore expanded from "Trading Funnel" to "Analytics Framework."

The framework must support future analytics naturally.

Examples include:

- Execution Funnel
- Decision Funnel
- Strategy Analytics
- Risk Analytics
- Portfolio Analytics
- Capital Analytics
- Bucket Analytics
- Win Rate
- Loss Rate
- Holding Period
- Regime Performance
- Score Distribution
- Rejection Analysis
- Broker Analytics
- Zerodha Analytics

without requiring architectural redesign.

---

# 5. Architecture Reviews Conducted

Multiple independent architecture reviews were performed before implementation approval.

The following candidate architectures were evaluated.

---

## Option A

Simple Funnel Tracker

Characteristics

- In-memory counters
- One execution cycle only
- Counts each pipeline stage

Advantages

- Extremely simple
- Very small implementation

Disadvantages

- Limited to funnel analytics
- No historical analytics
- Poor extensibility
- Every new metric requires execution changes

Decision

Rejected.

Reason:

Dead-end architecture.

---

## Option B

Event Sourced Analytics

Characteristics

Every pipeline stage emits events.

Example events:

- SCANNED
- SCORED
- VOTED
- REGIME
- STRUCTURE
- RISK
- CAPITAL
- EXECUTED
- EXITED

Each event becomes one database row.

Advantages

- Extremely flexible
- Enterprise architecture
- Full replay capability
- Unlimited analytics

Disadvantages

- Multiple writes per stock
- Correlation IDs
- Event reconstruction
- Higher complexity
- Higher maintenance
- Higher storage

Decision

Rejected.

Reason:

Excellent enterprise pattern.

Poor fit for Trading OS.

Complexity exceeds project requirements.

Violates KISS and YAGNI for a single-user sequential system.

---

## Option C

Analytics Recorder

Characteristics

Execution performs all trading decisions.

After the final decision is known,

execution writes one analytics record.

One evaluated stock

↓

One analytics record

↓

One database row

Advantages

- Simple
- Maintainable
- Easy to query
- Historical analytics
- Future dashboard support
- Zerodha compatible
- Android compatible
- Web compatible

Disadvantages

- Does not record every intermediate pipeline event
- Cannot replay internal execution history

Decision

APPROVED.

This architecture becomes the official implementation standard.

---

# 6. Final Architecture Decision

The Analytics Recorder architecture is officially approved.

Reasoning:

It provides the best balance between:

- simplicity
- maintainability
- scalability
- historical analytics
- future evolution

without introducing unnecessary complexity.

This architecture satisfies:

✓ Read Only

✓ Single Source of Truth

✓ No Duplicate Logic

✓ Minimal Intrusion

✓ Beginner Friendly

✓ Long-Term Maintainability

It also supports every planned feature currently on the Trading OS roadmap.

No additional architectural redesign is expected before Zerodha integration.

---

# 7. High-Level System Architecture

The Analytics module is a passive observer of the execution pipeline.

Execution remains the only component responsible for making trading decisions.

Analytics only records the outcome of decisions that have already been made.

The dependency direction is intentionally one-way.

```
Execution
    │
    │ Decision Completed
    ▼
Analytics Recorder
    │
    ▼
Persistence Layer
    │
    ├── Supabase (Primary)
    │
    └── CSV (Fallback)
    │
    ▼
Analytics Queries
    │
    ▼
Dashboards / Reports / Statistics
```

Execution never depends on analytics.

Analytics never calls execution.

This separation guarantees that analytics failures cannot affect trading behaviour.

---

# 8. Approved Directory Structure

The analytics system shall exist as its own top-level module.

```
trading_os/

    analytics/
        __init__.py

        recorder.py
        models.py
        storage.py
        queries.py
        dashboard.py

    engine/
        execution_loop.py

    strategies/

    portfolio/

    risk/

    dashboard/

    logs/
```

Purpose of each module:

## recorder.py

Public entry point.

Responsible for accepting snapshots from execution.

No business logic.

No trading logic.

No market calculations.

---

## models.py

Contains analytics record definitions.

Responsible for:

- schema
- field names
- default values
- validation helpers (non-business validation only)

No persistence.

No dashboard code.

---

## storage.py

Responsible only for persistence.

Handles:

- Supabase write
- CSV fallback
- row update
- read operations

No analytics calculations.

No business rules.

---

## queries.py

Read-only analytics.

Examples:

- funnel counts
- win rate
- loss rate
- rejection analysis
- bucket statistics
- score distribution
- regime performance

Queries only.

Never modifies data.

---

## dashboard.py

Presentation helpers.

Transforms query output into:

- Streamlit tables
- charts
- KPIs
- dashboard cards

No persistence.

No execution imports.

---

# 9. Module Responsibilities

## Execution Module

Responsibilities:

- Fetch market data
- Calculate indicators
- Calculate scores
- Aggregate votes
- Determine market regime
- Determine structure
- Check portfolio limits
- Allocate capital
- Execute paper trades
- Execute future live trades
- Build analytics snapshot
- Call Analytics Recorder

Execution owns every trading decision.

Execution owns every trading rule.

Execution owns every calculation.

---

## Analytics Module

Responsibilities:

Receive completed snapshot.

Transform snapshot into analytics record.

Persist analytics record.

Update trade outcome after exit.

Serve historical analytics.

Serve dashboards.

Nothing else.

---

## Storage Module

Responsibilities:

Persist analytics rows.

Load analytics rows.

Update outcome columns.

Handle fallback storage.

Storage knows nothing about trading.

---

## Dashboard Module

Responsibilities:

Display analytics.

Charts.

KPIs.

Historical statistics.

No execution logic.

No persistence logic.

---

# 10. Ownership Boundaries

The ownership boundaries are strict.

Execution owns decisions.

Analytics owns records.

Storage owns persistence.

Dashboard owns presentation.

Each module owns only its own concern.

Violation of these boundaries is considered architectural debt.

---

# 11. Approved Data Flow

Execution finishes evaluating a stock.

↓

Execution creates a snapshot.

↓

Analytics receives snapshot.

↓

Analytics creates Analytics Record.

↓

Analytics persists record.

↓

Dashboard reads persisted data later.

No component skips this sequence.

---

# 12. Snapshot Contract

Execution shall provide a complete snapshot.

Analytics shall never request additional information.

Snapshot is a plain dictionary.

No execution objects.

No callbacks.

No mutable references.

Snapshot contains only values already computed.

Example categories:

Identity

Decision

Scores

Votes

Regime

Bucket

Risk Result

Capital Result

Execution Result

Reasons

Trade Information

Analytics is prohibited from deriving missing values.

If execution did not compute a value,

analytics records it as missing.

---

# 13. Approved Analytics Record Lifecycle

Every evaluated stock produces exactly one Analytics Record.

Lifecycle:

Evaluation Starts

↓

Execution Completes

↓

Snapshot Built

↓

Analytics Record Created

↓

Record Persisted

↓

Cycle Continues

If a position is opened,

that same record remains associated with the position.

Later...

Position exits.

↓

Execution computes exit information.

↓

Analytics updates existing record.

No second analytics record is created.

One trade.

One record.

One lifecycle.

---

# 14. Entry Write

The first write happens immediately after execution finishes evaluating a stock.

The entry write records:

- stock identity
- timestamp
- decision
- scores
- votes
- regime
- bucket
- rejection reason
- execution status

Entry write is synchronous.

Execution immediately proceeds to the next stock afterwards.

Analytics failure must never interrupt execution.

---

# 15. Exit Write

If a trade was executed,

the analytics record receives one additional update.

Exit update includes:

- exit price
- exit timestamp
- exit reason
- realized P&L
- holding period
- outcome

The existing record is updated using:

position_id

No duplicate analytics record is created.

Maximum writes per analytics record:

1 Entry Write

+

1 Exit Update

Nothing more.

---

# 16. Record Immutability

Entry-side trading decisions are immutable.

Once recorded they must never change.

Only outcome-related fields may be updated.

Allowed updates include:

- exit price
- exit date
- realized P&L
- holding period
- exit reason

Everything else remains unchanged.

This guarantees historical integrity.

---

# 17. Analytics Recorder Contract

The Analytics Recorder is the only public interface between the execution engine and the analytics framework.

Its responsibility is intentionally small.

Execution computes.

Analytics records.

Nothing more.

The Analytics Recorder is a passive consumer.

It is never an active participant in trading.

---

# 18. Core Responsibilities

The Analytics Recorder SHALL:

- Accept completed execution snapshots.
- Convert snapshots into Analytics Records.
- Persist records immediately.
- Update records when trades close.
- Provide read-only access for analytics queries.

The Analytics Recorder SHALL NOT:

- Calculate indicators.
- Calculate scores.
- Calculate votes.
- Determine market regime.
- Validate structures.
- Allocate capital.
- Execute trades.
- Retry failed trades.
- Modify execution state.
- Influence execution decisions.
- Recalculate missing values.

If execution does not provide a value,

analytics records the absence of that value.

It must never attempt to derive it.

---

# 19. Public Interface Contract

The public surface of the analytics module should remain intentionally small.

Approved entry points:

• Record Entry

Accepts one completed execution snapshot.

Creates one analytics record.

Persists immediately.

---

• Record Exit

Accepts:

- position identifier
- exit information

Updates the previously created analytics record.

Nothing else.

No additional public methods should be introduced unless approved by a future ADR.

Keeping the interface small minimizes coupling and simplifies maintenance.

---

# 20. Fire-and-Forget Principle

Execution calls analytics.

Execution never waits for analytics.

Execution never branches based on analytics.

Execution ignores analytics return values.

Analytics failure must never stop trading.

The relationship is therefore:

```
Execution

↓

Analytics

↓

Storage

↓

Dashboard
```

Never:

```
Dashboard

↓

Analytics

↓

Execution
```

or

```
Analytics

↓

Execution
```

The dependency direction is permanent.

---

# 21. Dependency Rules

Allowed dependencies:

Execution

↓

Analytics

↓

Storage

↓

Database

Dashboard

↓

Analytics

Forbidden dependencies:

Analytics

↓

Execution

Analytics

↓

Strategies

Analytics

↓

Portfolio Engine

Analytics

↓

Risk Engine

Analytics

↓

Decision Engine

Dashboard

↓

Execution

Storage

↓

Execution

If any future implementation introduces these dependencies,

the architecture has been violated.

---

# 22. Snapshot Design Rules

The snapshot passed into analytics is a plain data object.

It must contain only values that execution has already computed.

Examples:

Stock Identity

Symbol

Bucket

Composite Score

Individual Scores

Votes

Confluence

Regime

Structure Result

Risk Result

Capital Result

Decision

Rejection Stage

Rejection Reason

Trade Price

Quantity

Position Identifier

Timestamp

Analytics must treat every field as read-only.

It must never modify the snapshot.

---

# 23. Snapshot Ownership

Execution owns the snapshot.

Analytics owns the Analytics Record.

This distinction is important.

Execution may freely change its internal variables,

objects,

and implementation details,

provided the snapshot contract remains unchanged.

Analytics must never inspect execution internals.

The snapshot is the only agreed communication contract.

---

# 24. Single Source of Truth

Execution is the authoritative source.

Analytics is a derived representation.

If there is ever disagreement between:

- trade tables
- position tables
- execution logs
- analytics table

execution wins.

Analytics must never become the authoritative source for trading history.

Analytics exists for reporting,

not execution.

---

# 25. Persistence Strategy

Persistence follows the existing Trading OS pattern.

Primary Storage

Supabase

Fallback Storage

CSV

Analytics shall reuse the same persistence philosophy already adopted across the project.

No new persistence framework should be introduced.

No ORM should be introduced.

No message queue should be introduced.

No asynchronous event broker should be introduced.

The objective is architectural consistency.

---

# 26. Write Policy

Entry records are written immediately.

Exit information updates the same record.

No batching.

No delayed writes.

No overnight synchronization.

No replay process.

Every decision becomes durable before moving to the next stock.

This mirrors existing logging behaviour throughout Trading OS.

---

# 27. Failure Policy

Analytics failures are non-fatal.

Possible failures include:

- Supabase unavailable
- CSV write failure
- schema mismatch
- network interruption

Execution must continue.

Analytics should:

attempt primary storage

↓

fallback storage

↓

log warning

↓

return control

Trading must never fail because analytics failed.

---

# 28. Error Handling Philosophy

Analytics is a reporting subsystem.

Reporting is less critical than execution.

Therefore:

Execution availability has priority over analytics completeness.

Missing analytics is acceptable.

Missing trades are not.

This priority shall guide every future implementation decision.

---

# 29. Update Policy

Entry-side information is immutable.

Exit-side information is mutable exactly once.

Allowed update fields include:

- exit timestamp
- exit price
- realized P&L
- holding period
- exit reason
- trade outcome

Everything else remains frozen.

Historical trading decisions must never be rewritten.

---

# 30. Position Matching

Exit updates locate the existing analytics record using:

position_id

This is the only approved lookup key.

Ticker symbols,

timestamps,

or prices

must never be used as the primary matching mechanism.

Position identifiers uniquely bind entry and exit together.

---

# 31. Data Integrity Rules

Every analytics record should satisfy the following principles.

One evaluated stock

↓

One analytics record

One executed trade

↓

One position identifier

One position identifier

↓

One exit update

No duplicate entry records.

No duplicate exit records.

No multiple ownership.

Every trade should have one complete lifecycle.

---

# 32. Analytics Scope

The Analytics Recorder is intentionally narrow.

Its responsibility ends once data has been persisted.

It does not:

- build dashboards
- create charts
- calculate KPIs
- generate reports
- compute statistics

Those responsibilities belong to the query and dashboard layers.

Keeping these concerns separate preserves modularity and simplifies testing.

---

# 33. Analytics Data Model

The Analytics Record represents one complete trading evaluation.

It is intentionally denormalized.

The objective is fast querying,

easy debugging,

and simple maintenance.

A single row should explain everything important about one stock evaluation.

---

# 34. Logical Data Groups

The Analytics Record is logically divided into the following sections.

## A. Identity

Identifies the evaluation.

Examples include:

- Record ID
- Cycle ID
- Position ID
- Timestamp
- Stock Name
- Symbol

---

## B. Market Context

Captures the market environment at decision time.

Examples include:

- Market Regime
- Bucket
- Strategy
- Source (Paper / Zerodha)

These values describe the environment.

They do not describe performance.

---

## C. Scoring

Captures execution outputs.

Examples:

- Composite Score
- Individual Scores
- Buy Votes
- Sell Votes
- Confluence

Analytics must never calculate these.

Execution provides them.

---

## D. Pipeline Results

Each execution gate records whether the stock passed.

Examples:

Passed Score

Passed Votes

Passed Regime

Passed Structure

Passed Portfolio Risk

Passed Capital

Executed

This information enables funnel analytics without event sourcing.

---

## E. Decision Information

Captures the final execution decision.

Examples:

Decision

Execution Result

Rejection Stage

Rejection Reason

Decision Timestamp

These fields explain why execution stopped or continued.

---

## F. Trade Information

Present only when a trade executes.

Examples:

Entry Price

Quantity

Capital Used

Position Identifier

Trade Source

---

## G. Exit Information

Populated only after position closure.

Examples:

Exit Price

Exit Time

Exit Reason

Holding Days

Realized PnL

PnL Percentage

Trade Outcome

---

# 35. Lifecycle Diagram

The approved lifecycle is:

```
Evaluate Stock

↓

Execution Decision

↓

Snapshot Created

↓

Analytics Record Created

↓

Persist Entry

↓

Continue Trading

↓

Position Closed

↓

Update Same Record

↓

Analytics Complete
```

Every record follows this lifecycle.

No exceptions.

---

# 36. Decision States

Every evaluation must end in exactly one decision state.

Approved states include:

BUY

SELL

NO_TRADE

REJECTED

ERROR

No analytics record should contain multiple final decisions.

Decision state is immutable after entry write.

---

# 37. Rejection Recording

Whenever execution rejects a stock,

analytics records:

Where rejection occurred.

Why rejection occurred.

Examples:

Score Gate

Vote Gate

Regime Gate

Structure Gate

Risk Gate

Capital Gate

Execution Rule

Only execution determines these values.

Analytics merely stores them.

---

# 38. Funnel Analytics

The trading funnel is no longer a dedicated component.

Instead,

the funnel is a view generated from Analytics Records.

Example:

```
Evaluated

↓

Passed Score

↓

Passed Votes

↓

Passed Regime

↓

Passed Structure

↓

Passed Risk

↓

Passed Capital

↓

Executed
```

Counts are calculated by querying pipeline result fields.

No separate Funnel Tracker exists.

---

# 39. Historical Analytics

Historical analytics operate exclusively on persisted Analytics Records.

Examples:

Win Rate

Loss Rate

Average Holding Period

Average Score

Score Distribution

Bucket Performance

Strategy Performance

Regime Performance

Capital Utilization

Monthly Performance

Daily Performance

Hourly Performance

Rejection Analysis

Execution Funnel

All analytics are query-based.

No historical values are stored separately.

---

# 40. Dashboard Data Flow

The dashboard never reads execution state directly.

Approved flow:

```
Dashboard

↓

Analytics Queries

↓

Analytics Storage

↓

Supabase / CSV
```

Execution is never queried for reporting.

This prevents dashboard code from coupling with trading logic.

---

# 41. Schema Evolution Policy

The schema is expected to evolve.

Evolution rules:

New fields may be added.

Existing fields should not be renamed.

Existing meanings should not change.

Deprecated fields should remain readable until officially removed.

Backward compatibility is preferred whenever practical.

---

# 42. Backward Compatibility

Future analytics must preserve historical records.

Historical rows should remain usable even if newer versions contain additional fields.

Missing values should be interpreted as:

Unknown

Not Applicable

Not Recorded

Analytics queries must handle missing data gracefully.

---

# 43. Sequence Diagram — Entry Path

```
Execution Loop

↓

Calculate Indicators

↓

Calculate Scores

↓

Aggregate Votes

↓

Run Orchestrator

↓

Risk Validation

↓

Capital Validation

↓

Final Decision

↓

Create Snapshot

↓

Analytics Recorder

↓

Storage

↓

Next Stock
```

Analytics never interrupts the sequence.

---

# 44. Sequence Diagram — Exit Path

```
Position Manager

↓

Exit Decision

↓

Realized PnL

↓

Holding Days

↓

Exit Snapshot

↓

Analytics Recorder

↓

Locate Record

↓

Update Outcome

↓

Complete
```

Only outcome fields are modified.

Entry-side data remains unchanged.

---

# 45. Failure Recovery

If persistence fails,

the following recovery order is used.

Attempt Supabase.

↓

If unsuccessful,

attempt CSV fallback.

↓

If unsuccessful,

log warning.

↓

Return control to execution.

Execution must continue regardless of analytics status.

---

# 46. Consistency Rules

The analytics table should always satisfy:

One evaluation

↓

One analytics record

One position

↓

One position identifier

One position identifier

↓

One outcome update

Duplicate lifecycle records indicate implementation defects.

---

# 47. Read Model Philosophy

The Analytics Record is a read model.

It is optimized for:

Fast reporting.

Historical analysis.

Dashboard queries.

Human readability.

It is not optimized for transaction processing.

It is not an execution log.

It is not an event store.

This distinction is intentional.

---

# 48. Performance Expectations

The approved architecture is expected to provide:

Very low write overhead.

Simple indexed lookups.

Minimal joins.

Fast dashboard loading.

Good scalability for a single-user sequential system.

Performance improvements should prioritize simplicity over premature optimization.

---

# 49. Future Extension Strategy

The approved Analytics Recorder architecture is intentionally designed to grow without requiring architectural redesign.

Future enhancements should extend the existing analytics record rather than introducing parallel analytics systems.

The preferred evolution strategy is:

Existing Snapshot

↓

Additional Snapshot Fields

↓

Additional Analytics Columns

↓

Additional Queries

↓

Additional Dashboards

Architecture remains unchanged.

---

# 50. Approved Future Analytics

The following analytics are expected to be implemented over time.

These are all supported by the approved architecture.

## Execution Analytics

Examples:

- Executed Trades
- Rejected Trades
- Execution Funnel
- Decision Distribution
- Trade Frequency

---

## Strategy Analytics

Examples:

- Win Rate by Strategy
- Average Score by Strategy
- Strategy Profitability
- Strategy Usage
- Strategy Consistency

---

## Bucket Analytics

Examples:

- Swing Performance
- Intraday Performance
- Long-Term Performance
- Capital Usage
- Bucket Allocation

---

## Risk Analytics

Examples:

- Risk Gate Rejections
- Maximum Drawdown
- Average Risk Utilization
- Portfolio Exposure
- Capital Protection Statistics

---

## Regime Analytics

Examples:

- Bull Market Performance
- Bear Market Performance
- Sideways Market Performance
- Regime Win Rate
- Regime Profitability

---

## Portfolio Analytics

Examples:

- Portfolio Growth
- Portfolio Return
- Open Positions
- Closed Positions
- Capital Utilization
- Allocation History

---

## Trade Analytics

Examples:

- Holding Period
- Average Winner
- Average Loser
- Profit Factor
- Expectancy
- Reward/Risk Ratio

---

## Broker Analytics

Future Zerodha integration may introduce:

- Order Latency
- Fill Rate
- Slippage
- Order Rejections
- API Errors

These become additional fields.

They do not require architectural redesign.

---

# 51. Dashboard Philosophy

Dashboards must never perform business calculations.

Dashboard responsibilities:

Read analytics.

Display analytics.

Filter analytics.

Visualize analytics.

Nothing more.

Business calculations belong inside analytics queries.

Execution calculations belong inside execution.

---

# 52. Query Layer Philosophy

Every dashboard metric should originate from a query.

Examples:

Win Rate

↓

Query

Average Holding Period

↓

Query

Top Rejection Reasons

↓

Query

Execution Funnel

↓

Query

No dashboard should manually calculate statistics.

This keeps business logic centralized.

---

# 53. Reporting Philosophy

Reports are generated from Analytics Records.

Reports never inspect execution modules.

Reports never inspect strategy modules.

Reports never inspect position manager internals.

The Analytics Record is the reporting contract.

---

# 54. Coding Standards

Every future analytics implementation should follow these principles.

Readable code.

Small functions.

Single responsibility.

Descriptive names.

Minimal nesting.

Minimal coupling.

Prefer composition over duplication.

Prefer explicit code over clever code.

Trading OS prioritizes maintainability over sophistication.

---

# 55. Architecture Guardrails

The following rules are mandatory.

Rule 1

Analytics never imports execution modules.

---

Rule 2

Execution never knows analytics schema.

---

Rule 3

Storage never knows trading rules.

---

Rule 4

Dashboard never knows execution internals.

---

Rule 5

Queries never modify data.

---

Rule 6

Analytics never recalculates trading decisions.

---

Rule 7

Execution remains the single source of truth.

Violation of any guardrail requires an Architecture Decision Review before implementation continues.

---

# 56. Anti-Patterns

The following patterns are explicitly prohibited.

Creating duplicate score calculations.

Creating duplicate vote calculations.

Creating duplicate regime calculations.

Running strategies inside analytics.

Calling market data providers from analytics.

Building dashboard-specific business logic.

Sharing mutable objects across execution and analytics.

Introducing circular imports.

Creating multiple analytics tables representing the same lifecycle.

Implementing event sourcing without an approved ADR.

Adding analytics conditions that affect trading decisions.

These anti-patterns introduce technical debt and violate approved architecture.

---

# 57. Testing Philosophy

Testing should be performed independently for each layer.

Execution Tests

Verify trading decisions.

Analytics Tests

Verify snapshots become correct records.

Storage Tests

Verify persistence.

Query Tests

Verify statistics.

Dashboard Tests

Verify presentation.

Each layer should be testable in isolation.

---

# 58. Migration Strategy

Future changes should follow this order.

Step 1

Extend snapshot.

↓

Step 2

Extend Analytics Record.

↓

Step 3

Extend persistence.

↓

Step 4

Extend query.

↓

Step 5

Extend dashboard.

Execution changes should remain minimal.

The architecture should evolve through extension rather than replacement.

---

# 59. Event Sourcing Reconsideration Policy

Event Sourcing has been evaluated and rejected for the current project.

It should only be reconsidered if Trading OS fundamentally changes.

Examples include:

Multiple concurrent users.

Distributed execution.

Multiple execution workers.

Replay requirements.

Regulatory audit requirements.

External analytics consumers requiring raw event streams.

Until such requirements exist,

Analytics Recorder remains the approved architecture.

---

# 60. Long-Term Vision

The Analytics Recorder architecture is intended to remain stable throughout the planned evolution of Trading OS.

Expected future milestones include:

Paper Trading

↓

Live Trading

↓

Android Dashboard

↓

Web Dashboard

↓

Advanced Analytics

↓

AI Insights

↓

Portfolio Intelligence

These milestones should require new fields and new queries,

not a new architecture.

The goal is evolutionary growth with minimal technical debt.

---

# 61. Implementation Roadmap

The implementation of the Analytics Recorder shall be performed incrementally.

The recommended order is:

Phase 1

Create analytics module.

↓

Phase 2

Create Analytics Record model.

↓

Phase 3

Implement storage layer.

↓

Phase 4

Implement Analytics Recorder.

↓

Phase 5

Connect execution to Analytics Recorder.

↓

Phase 6

Implement dashboard queries.

↓

Phase 7

Build Analytics Dashboard.

Each phase should produce a working system.

Large "big bang" implementations should be avoided.

---

# 62. Implementation Principles

Implementation must remain additive.

The existing execution engine is considered stable.

Implementation should avoid modifying existing trading logic unless absolutely necessary.

The Analytics Recorder must consume existing outputs rather than introducing new execution behaviour.

If a future feature requires significant execution changes solely for analytics purposes, the implementation should be paused and reviewed.

---

# 63. Code Review Checklist

Before approving any analytics-related code, verify the following:

✓ Analytics never changes trading decisions.

✓ Analytics never recalculates scores.

✓ Analytics never recalculates votes.

✓ Analytics never recalculates regimes.

✓ Analytics never recalculates risk.

✓ Analytics never imports execution modules.

✓ Execution never depends on analytics success.

✓ Analytics writes immediately.

✓ Entry records are immutable.

✓ Exit updates modify only outcome fields.

✓ Queries are read-only.

✓ Dashboard contains no business logic.

✓ No duplicate calculations exist.

✓ No circular imports exist.

✓ Storage follows the existing Supabase → CSV fallback pattern.

If any item fails,

implementation should not be merged until corrected.

---

# 64. Definition of Done

The Analytics Recorder implementation is considered complete when all of the following are true.

A complete Analytics Record is written for every evaluated stock.

Executed trades receive an outcome update after exit.

Dashboard queries operate exclusively on persisted analytics records.

Execution can continue even if analytics persistence fails.

Analytics answers all currently planned reporting requirements without requiring changes to execution logic.

No duplicate business logic exists.

The architecture guardrails remain intact.

---

# 65. Future ADR Process

Architecture should remain stable.

Future Architecture Decision Reviews (ADR) should only be created when one of the following occurs:

A fundamental architectural limitation is discovered.

Trading OS changes from a single-user application to a multi-user platform.

Distributed execution becomes necessary.

Regulatory requirements require immutable event histories.

External systems require real-time event streaming.

The analytics architecture can no longer satisfy project requirements through additive changes alone.

Normal feature requests should not trigger new architecture reviews.

---

# 66. Architecture Risks

Every architecture has trade-offs.

The approved Analytics Recorder architecture accepts the following risks:

Loss of intermediate pipeline replay.

Reduced visibility into every internal execution step.

Future schema evolution through additional columns.

These risks are considered acceptable because they significantly reduce implementation complexity and maintenance burden.

The architecture deliberately optimizes for simplicity rather than maximum flexibility.

---

# 67. Explicitly Rejected Alternatives

The following alternatives were evaluated and rejected.

Simple Funnel Tracker

Reason:

Too limited.

Creates a dead-end architecture.

---

Full Event Sourcing

Reason:

Over-engineered for a single-user sequential system.

Introduces unnecessary implementation and maintenance complexity.

---

Hybrid Event + Recorder Architecture

Reason:

Provides little additional value for current project requirements.

Increases cognitive load.

Violates KISS.

---

The approved Analytics Recorder architecture replaces all rejected alternatives.

---

# 68. Expected Benefits

After implementation, Trading OS will gain a unified analytics foundation capable of supporting:

Execution Funnel

Decision Analytics

Rejection Analytics

Strategy Analytics

Bucket Analytics

Portfolio Analytics

Capital Analytics

Holding Period Analytics

Score Distribution

Regime Analytics

Win/Loss Analytics

Broker Analytics

Future Zerodha Analytics

Android Dashboard

Web Dashboard

without requiring architectural redesign.

---

# 69. Architecture Summary

Trading OS follows a layered architecture.

Execution Layer

↓

Analytics Layer

↓

Persistence Layer

↓

Query Layer

↓

Presentation Layer

Each layer has one responsibility.

Communication is one-directional.

Execution remains the single source of truth.

Analytics remains a passive observer.

Persistence remains an implementation detail.

Queries remain read-only.

Presentation remains independent of business logic.

This separation of concerns is the foundation of long-term maintainability.

---

# 70. Final Architecture Decision

Architecture Name

Analytics Recorder

Status

APPROVED

Decision Date

Final Architecture Review

Primary Goals

Maintainability

Simplicity

Correctness

Long-Term Evolution

Beginner-Friendly Design

Future Compatibility

The approved architecture satisfies:

✓ Read-only analytics

✓ Single source of truth

✓ No duplicate business logic

✓ Minimal execution changes

✓ Long-term maintainability

✓ Historical analytics

✓ Dashboard compatibility

✓ Future Zerodha compatibility

✓ Android compatibility

✓ Web compatibility

No additional architecture work is required before implementation.

Future work should focus on building features rather than redesigning architecture.

---

# 71. Instructions for Future Contributors

Anyone implementing Trading OS analytics should follow these principles:

Understand this ADR before modifying analytics.

Extend the architecture instead of replacing it.

Prefer adding fields and queries over creating new subsystems.

Avoid introducing unnecessary abstractions.

Keep execution independent.

Keep analytics passive.

Keep code readable.

When in doubt, choose the simpler design.

---

# 72. Final Sign-off

This document represents the approved Analytics Architecture for Trading OS.

It supersedes previous architecture discussions, proposals, drafts, and reviews.

All future analytics implementation should follow this document unless a new ADR formally replaces it.

Architecture Status:

APPROVED

Implementation Status:

READY

Next Step:

Begin implementation.

No further architecture reviews are required before coding.

---

# Appendix A – Guiding Philosophy

Trading OS is intentionally engineered as a maintainable, modular, single-developer platform.

Architecture decisions favor clarity over sophistication, evolution over reinvention, and practical value over theoretical completeness.

The goal is not to build the most complex architecture.

The goal is to build the most sustainable architecture.

Every new feature should make Trading OS easier to understand, easier to maintain, and easier to extend.

That principle takes precedence over all others.

---

# End of Document