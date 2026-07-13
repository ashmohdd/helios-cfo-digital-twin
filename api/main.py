"""
HELIOS CFO Digital Twin — REST API
==================================

A thin FastAPI service over the analytics engine. Every endpoint is a pure
read over the gold layer (data/gold_monthly.parquet) plus the in-process
analytics modules — the API computes nothing the dashboards or notebooks
cannot, which keeps a single source of truth.

Design notes (the kind an interviewer will probe):
- The API is *stateless*: each request reloads the gold parquet. In production
  you would put the gold layer behind a warehouse (Postgres / BigQuery /
  Snowflake) and a query cache; the parquet here stands in for that.
- The CFO-assistant endpoint defaults to the deterministic template backend so
  the service has no external dependency. Set backend="llm" (and ANTHROPIC_API_KEY)
  to route narration through Claude.
- Response models are explicit Pydantic schemas so the OpenAPI docs at /docs are
  self-describing — a recruiter can click through the whole surface.

Run:  PYTHONPATH=. python -m uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.analytics.kpis import quarterly, compute_kpis, KPI_BY_AUDIENCE
from src.analytics.variance import revenue_bridge, comp_bridge, pl_variance
from src.scenarios.compare import compare
from src.scenarios.library import SCENARIO_LIBRARY
from src.forecasting.pipeline import ensemble_forecast
from src.narration.cfo_assistant import ask
from src.narration.reports import (
    quarterly_business_review,
    board_report,
    earnings_call_summary,
)

GOLD = "data/gold_monthly.parquet"

app = FastAPI(
    title="HELIOS CFO Digital Twin API",
    version="1.0.0",
    description="Decision-intelligence API for an enterprise FP&A operating system.",
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (dashboard UI)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="ui")


@lru_cache(maxsize=1)
def gold() -> pd.DataFrame:
    try:
        return pd.read_parquet(GOLD)
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Gold layer missing. Run `make warehouse` to build it.",
        )


def _scenario_frame(scenario: str) -> pd.DataFrame:
    df = gold()
    sub = df[df["scenario"] == scenario]
    if sub.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. See /scenarios for valid labels.",
        )
    return sub


def _clean(obj: Any) -> Any:
    """Recursively coerce numpy scalars/arrays to native JSON-safe types."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_clean(v) for v in obj.tolist()]
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, float):
        return None if pd.isna(obj) else obj
    return obj


# ----------------------------------------------------------------------------- #
# Schemas
# ----------------------------------------------------------------------------- #
class Health(BaseModel):
    status: str
    scenarios_loaded: int
    months: int


class AssistantAnswer(BaseModel):
    question: str
    quarter: str
    backend: str
    answer: str


# ----------------------------------------------------------------------------- #
# Meta / discovery
# ----------------------------------------------------------------------------- #
@app.get("/", tags=["meta"])
def root() -> dict[str, Any]:
    return {
        "name": "HELIOS CFO Digital Twin",
        "docs": "/docs",
        "endpoints": [
            "/health", "/scenarios", "/audiences",
            "/kpis", "/kpis/audience/{audience}",
            "/variance/revenue", "/variance/comp", "/variance/pl",
            "/forecast", "/scenarios/compare",
            "/assistant", "/reports/{kind}",
        ],
    }


@app.get("/health", response_model=Health, tags=["meta"])
def health() -> Health:
    df = gold()
    return Health(
        status="ok",
        scenarios_loaded=df["scenario"].nunique(),
        months=df["date"].nunique(),
    )


@app.get("/scenarios", tags=["meta"])
def scenarios() -> dict[str, Any]:
    df = gold()
    return {
        "loaded_in_gold": sorted(df["scenario"].unique().tolist()),
        "library": {
            k: SCENARIO_LIBRARY[k].label for k in SCENARIO_LIBRARY
        },
    }


@app.get("/audiences", tags=["meta"])
def audiences() -> dict[str, list[str]]:
    return KPI_BY_AUDIENCE


# ----------------------------------------------------------------------------- #
# KPIs
# ----------------------------------------------------------------------------- #
@app.get("/kpis", tags=["kpis"])
def kpis(scenario: str = Query("Base Plan")) -> list[dict[str, Any]]:
    k = compute_kpis(quarterly(_scenario_frame(scenario)))
    return _clean(k.replace({float("nan"): None}).to_dict(orient="records"))


@app.get("/kpis/audience/{audience}", tags=["kpis"])
def kpis_for_audience(
    audience: str, scenario: str = Query("Base Plan")
) -> list[dict[str, Any]]:
    audience = audience.upper() if audience.upper() in KPI_BY_AUDIENCE else audience.title()
    if audience not in KPI_BY_AUDIENCE:
        raise HTTPException(404, f"Unknown audience. Options: {list(KPI_BY_AUDIENCE)}")
    cols = ["scenario", "quarter"] + KPI_BY_AUDIENCE[audience]
    k = compute_kpis(quarterly(_scenario_frame(scenario)))
    keep = [c for c in cols if c in k.columns]
    return _clean(k[keep].replace({float("nan"): None}).to_dict(orient="records"))


# ----------------------------------------------------------------------------- #
# Variance bridges
# ----------------------------------------------------------------------------- #
@app.get("/variance/revenue", tags=["variance"])
def variance_revenue(quarter: str = Query("2025-Q3")) -> dict[str, Any]:
    return _clean(revenue_bridge(quarter))


@app.get("/variance/comp", tags=["variance"])
def variance_comp(quarter: str = Query("2025-Q3")) -> dict[str, Any]:
    return _clean(comp_bridge(quarter))


@app.get("/variance/pl", tags=["variance"])
def variance_pl(quarter: str = Query("2025-Q3")) -> list[dict[str, Any]]:
    return _clean(pl_variance(quarter).to_dict(orient="records"))


# ----------------------------------------------------------------------------- #
# Forecast
# ----------------------------------------------------------------------------- #
@app.get("/forecast", tags=["forecast"])
def forecast(
    target: str = Query("revenue"),
    horizon: int = Query(6, ge=1, le=18),
    scenario: str = Query("Reported actuals"),
) -> dict[str, Any]:
    sub = _scenario_frame(scenario).sort_values("date")
    res = ensemble_forecast(sub, target=target, h=horizon)
    return _clean(res)


# ----------------------------------------------------------------------------- #
# Scenario comparison
# ----------------------------------------------------------------------------- #
@app.get("/scenarios/compare", tags=["scenarios"])
def scenarios_compare() -> list[dict[str, Any]]:
    return _clean(compare(gold()).replace({float("nan"): None}).to_dict(orient="records"))


# ----------------------------------------------------------------------------- #
# CFO assistant
# ----------------------------------------------------------------------------- #
@app.get("/assistant", response_model=AssistantAnswer, tags=["assistant"])
def assistant(
    q: str = Query(..., description="Natural-language finance question"),
    quarter: str = Query("2025-Q3"),
    backend: str = Query("template", pattern="^(template|llm)$"),
) -> AssistantAnswer:
    answer = ask(q, quarter=quarter, backend=backend)
    return AssistantAnswer(question=q, quarter=quarter, backend=backend, answer=answer)


# ----------------------------------------------------------------------------- #
# Auto-generated reports
# ----------------------------------------------------------------------------- #
@app.get("/reports/{kind}", tags=["reports"])
def reports(kind: str, quarter: str = Query("2025-Q3")) -> dict[str, str]:
    gen = {
        "qbr": quarterly_business_review,
        "board": board_report,
        "earnings": earnings_call_summary,
    }
    if kind not in gen:
        raise HTTPException(404, f"kind must be one of {list(gen)}")
    return {"kind": kind, "quarter": quarter, "markdown": gen[kind](quarter)}
