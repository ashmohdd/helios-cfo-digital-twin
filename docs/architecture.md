# HELIOS — Architecture

## 1. Design principle: one source of truth

`config/assumptions.py` holds every operating driver (segment growth, ARPU, churn,
headcount plans by function, comp, CapEx, tax, working-capital terms). Nothing
downstream invents a number — the generator, scenarios, and forecasts all key off
this file. Assumptions are auditable and versioned, exactly as a real FP&A team
would manage them.

## 2. Data flow

```
config/assumptions.py
        │  (drivers)
        ▼
src/generation/model.py        three-statement engine
        │   P&L ─► Balance Sheet ─► Cash Flow   (BS balances by construction)
        ▼
src/warehouse/build_warehouse.py
        │   star schema (SQLite)  +  gold_monthly.parquet
        ▼
   ┌───────────────┬──────────────────┬─────────────────┐
   ▼               ▼                  ▼                 ▼
analytics/kpis  analytics/variance  scenarios/library  forecasting/pipeline
(KPI suite)     (PVM bridges)       (6 overrides)      (ensemble + backtest)
   └───────────────┴──────────────────┴─────────────────┘
                          │
                          ▼
              narration/ (CFO assistant + auto reports)
                          │
            ┌─────────────┴──────────────┐
            ▼                            ▼
       api/main.py (FastAPI)      app/streamlit_app.py
       JSON endpoints             executive dashboards
```

## 3. Warehouse (dimensional star schema)

Dimensions: `dim_date, dim_segment, dim_geo, dim_function, dim_account, dim_scenario`.
Facts: `fact_pl, fact_revenue, fact_headcount, fact_balance_sheet, fact_cash_flow,
fact_drivers`. `dim_account` carries `statement`, `line_group`, and a `sign`
convention so the same account math drives every view consistently.

## 4. The three-statement tie-out (why it's credible)

The balance sheet balances by construction. Walking the deltas:

```
d_assets = d_cash + d_AR + d_PPE
d_cash   = NI + dep + sbc - d_AR + d_AP + d_deferred - capex   (indirect CFS)
d_PPE    = capex - dep
=> d_assets = NI + sbc + d_AP + d_deferred = d_(Liabilities + Equity)
```

A `pytest` asserts assets = liabilities + equity every month, so a broken assumption
fails CI rather than silently producing a wrong board number.

## 5. Serving

- **FastAPI** (`api/main.py`) exposes KPIs, variance, scenarios, forecast, and the
  assistant as typed JSON, calling the same `src/` functions the CLI uses.
- **Streamlit** (`app/streamlit_app.py`) renders the CFO / CEO / Board / Department
  / Investor dashboards from that JSON.

## 6. Deployment analogue

```
Docker Compose: postgres · api (uvicorn) · dashboard (streamlit) · scheduler
Cloud:          managed Postgres · container service · object store · secrets mgr
```
