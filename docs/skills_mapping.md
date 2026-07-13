# HELIOS — Competency Mapping (what a recruiter sees, by role)

The project is deliberately ordered so finance rigor leads and ML supports. Each
component below maps to skills evaluated for specific roles.

## Financial Analyst / Senior Financial Analyst
- **Variance analysis** with correct favorable/unfavorable polarity (`src/analytics`).
- **Price / Volume / Mix revenue bridges** that reconcile to the total — the single
  most-asked question in any business review.
- **KPI fluency**: Rule of 40, operating margin, FCF margin, revenue per head, CAC.
- **Budget vs actual vs forecast** across a real ledger structure.

## FP&A Manager / Finance Manager
- **Driver-based, three-statement planning** from one auditable assumptions file.
- **Scenario / what-if modeling** where a single knob flows through P&L, BS, CFS, KPIs
  — including second-order effects (a marketing cut lowering forward revenue).
- **Executive communication**: auto-generated QBR, Board, and Earnings narratives.

## Strategic / Corporate Finance
- **Segment economics**: a Platform cash engine funding a Frontier moonshot, framed
  as an explicit capital-allocation tradeoff (the margin-compression narrative).
- **Long-range planning** and the growth-vs-profitability decisions behind it.

## Business Intelligence
- **Dimensional warehouse design** (star schema, conformed dimensions, sign-aware
  account dimension) plus a semantic layer so every dashboard agrees on KPI math.
- **ETL**: generate → load → gold parquet, with tests on the marts.

## Data Science / ML
- **Ensemble forecasting** with a walk-forward backtest (not a single in-sample fit).
- **Grounding architecture**: the LLM narrates only; every number is computed
  deterministically in Python, which prevents hallucinated financials — the fastest
  way an AI finance tool otherwise loses a finance team's trust.

## The differentiator in one line
Most finance portfolio projects fit random numbers with Prophet. HELIOS is a
balanced three-statement operating model with segment-level capital-allocation
storytelling — which is what the job actually is.
