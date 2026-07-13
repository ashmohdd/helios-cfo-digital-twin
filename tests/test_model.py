"""
Test suite for HELIOS.

These tests encode the project's credibility claims as executable assertions.
The headline one — the balance sheet ties out every period — is the kind of
check a real corporate-model auditor runs. Run with:  PYTHONPATH=. pytest -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.generation.model import run_model
from src.analytics.kpis import quarterly, compute_kpis
from src.analytics.variance import revenue_bridge, comp_bridge
from src.scenarios.library import SCENARIO_LIBRARY
from src.scenarios.compare import compare


# ----------------------------------------------------------------------------- #
# The headline claim: the balance sheet balances by construction.
# ----------------------------------------------------------------------------- #
def test_balance_sheet_ties_out_plan():
    df = run_model(mode="plan")
    assert df["balance_check"].abs().max() < 1.0, "balance sheet must tie within $1"


def test_balance_sheet_ties_out_actual():
    df = run_model(mode="actual")
    assert df["balance_check"].abs().max() < 1.0


@pytest.mark.parametrize("name", list(SCENARIO_LIBRARY.keys()))
def test_balance_sheet_ties_out_every_scenario(name):
    df = run_model(scenario=SCENARIO_LIBRARY[name], mode="plan")
    assert df["balance_check"].abs().max() < 1.0, f"{name} broke the balance sheet"


# ----------------------------------------------------------------------------- #
# Variance bridges must reconcile to their own total.
# ----------------------------------------------------------------------------- #
def test_revenue_bridge_reconciles():
    t = revenue_bridge("2025-Q3")["totals"]
    recomposed = t["volume"] + t["price"] + t["fx"]
    assert abs(recomposed - t["variance"]) < 1.0, "Vol+Price+FX must foot to variance"


def test_revenue_bridge_geo_sums_to_total():
    rb = revenue_bridge("2025-Q3")
    geo_var = sum(g["variance"] for g in rb["by_geo"].values())
    assert abs(geo_var - rb["totals"]["variance"]) < 1.0


def test_comp_bridge_reconciles():
    t = comp_bridge("2025-Q3")["totals"]
    assert abs((t["headcount_effect"] + t["rate_effect"]) - t["variance"]) < 1.0


# ----------------------------------------------------------------------------- #
# KPIs must land in economically sane ranges (guards against unit/logic bugs).
# ----------------------------------------------------------------------------- #
def test_kpis_in_sane_ranges():
    df = run_model(mode="plan")
    k = compute_kpis(quarterly(df))
    assert k["gross_margin"].between(0.4, 0.9).all()
    assert k["operating_margin"].between(0.0, 0.6).all()
    assert (k["revenue_yoy"].dropna().between(-0.5, 1.0)).all()


# ----------------------------------------------------------------------------- #
# Scenarios must move the right direction (economic logic, not just plumbing).
# ----------------------------------------------------------------------------- #
def test_hiring_freeze_lifts_operating_income():
    c = compare().set_index("scenario")
    row = c.loc["Hiring Freeze (all functions)"]
    assert row["operating_income_delta"] > 0
    assert row["headcount_total_delta"] < 0


def test_recession_shows_operating_leverage():
    c = compare().set_index("scenario")
    row = c.loc["Economic recession"]
    # OI should fall proportionally far more than revenue (leverage in reverse)
    assert row["operating_income_delta_pct"] < row["revenue_delta_pct"] < 0
