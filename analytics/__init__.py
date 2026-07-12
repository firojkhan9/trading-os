# ================================================
# FILE: analytics/__init__.py
# PURPOSE: Package marker for the Analytics module.
#
# ARCHITECTURE NOTE (see Trading_OS_Architecture_ADR_v1.0.md):
#   The Analytics package is a passive, read-only observer of
#   the execution pipeline. It never imports execution, strategy,
#   portfolio, or risk modules, and execution never imports from
#   analytics for decision-making purposes (Analytics Recorder is
#   fire-and-forget — Section 20).
#
#   This file intentionally contains no logic. It exists only so
#   `analytics` can be imported as a package, consistent with every
#   other package in this project (strategies/, portfolio/, risk/,
#   engine/), each of which has its own empty/minimal __init__.py.
# ================================================
