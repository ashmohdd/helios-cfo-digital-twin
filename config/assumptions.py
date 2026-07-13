"""
Operating-model assumptions for HELIOS, a fictional large-cap technology company.

Design intent: this is the single source of truth for every driver in the model.
Nothing downstream invents a number; it all keys off this file. That is how a real
FP&A team runs a model -- assumptions are auditable, versioned, and owned.

HELIOS deliberately mirrors the *shape* of a Meta-like business so the project
reads as current and segment-aware:

    Segment A  - "Platform"   : ad-driven + a cloud / AI-API business. The cash engine.
    Segment B  - "Frontier"   : an AR / AI-devices moonshot. Heavy R&D + CapEx, loses
                                money on purpose. The strategic bet (the Reality-Labs analog).

All figures are synthetic and chosen to produce realistic ratios, not to match any
real company.
"""

from dataclasses import dataclass, field

# ----------------------------------------------------------------------------- #
# Time grid
# ----------------------------------------------------------------------------- #
START_YEAR = 2023
N_YEARS = 3                      # 2023, 2024, 2025 actuals; plan generated alongside
PERIODS_PER_YEAR = 12           # monthly granularity
RANDOM_SEED = 42

# ----------------------------------------------------------------------------- #
# Geography (used for ads revenue + FX)
# ----------------------------------------------------------------------------- #
GEOS = ["NA", "EU", "APAC", "LATAM", "ROW"]

# Starting monthly active users (millions) and starting monthly ARPU (USD)
GEO_START_MAU = {"NA": 410.0, "EU": 520.0, "APAC": 1180.0, "LATAM": 360.0, "ROW": 740.0}
GEO_START_ARPU = {"NA": 18.5, "EU": 12.2, "APAC": 4.6, "LATAM": 3.1, "ROW": 1.9}

# Annual MAU growth and ARPU growth (organic, before marketing response)
GEO_MAU_GROWTH = {"NA": 0.02, "EU": 0.03, "APAC": 0.07, "LATAM": 0.10, "ROW": 0.12}
GEO_ARPU_GROWTH = {"NA": 0.08, "EU": 0.07, "APAC": 0.11, "LATAM": 0.14, "ROW": 0.16}

# FX index vs USD (1.0 = parity baseline; <1 means local currency weaker -> USD drag)
GEO_FX_BASE = {"NA": 1.00, "EU": 1.05, "APAC": 0.93, "LATAM": 0.88, "ROW": 0.85}
FX_VOL = 0.02  # monthly FX noise (std)

# Q4 ad-seasonality multiplier applied to ARPU (holiday advertising lift)
SEASONALITY = {1: 0.94, 2: 0.93, 3: 0.96, 4: 0.99, 5: 1.00, 6: 1.01,
               7: 1.00, 8: 0.99, 9: 1.02, 10: 1.06, 11: 1.14, 12: 1.20}

# ----------------------------------------------------------------------------- #
# Cloud / AI-API business (gives us the SaaS KPI suite: NRR, CAC, magic number)
# ----------------------------------------------------------------------------- #
CLOUD_START_CUSTOMERS = 8200
CLOUD_START_ARPU_ANNUAL = 47000.0      # avg annual contract value per customer
CLOUD_GROSS_LOGO_ADDS_BASE = 520       # new customers/month at baseline marketing
CLOUD_MONTHLY_CHURN = 0.011            # logo churn / month
CLOUD_NET_EXPANSION = 0.014            # monthly net $ expansion on retained base (NRR>100%)
CLOUD_DEFERRED_REV_PCT = 0.55          # share of cloud revenue billed/collected upfront

# Marketing response: new logos = base * (1 + alpha * log(1 + spend/ref)) * macro
MKT_RESPONSE_ALPHA = 0.45
MKT_REFERENCE_SPEND = 9.0e6            # monthly $ where response curve is "calibrated"

# ----------------------------------------------------------------------------- #
# Frontier (devices) segment
# ----------------------------------------------------------------------------- #
DEVICE_START_UNITS = 240_000           # units / month
DEVICE_UNIT_GROWTH = 0.05              # monthly unit growth (high-growth, small base)
DEVICE_ASP = 430.0                     # average selling price
DEVICE_BOM = 510.0                     # bill of materials -> NEGATIVE hardware margin early
DEVICE_BOM_LEARNING = 0.004            # monthly BOM cost-down from manufacturing learning

# ----------------------------------------------------------------------------- #
# Cost structure
# ----------------------------------------------------------------------------- #
# Infrastructure: compute units scale with platform usage + AI inference.
INFRA_UNIT_COST = 0.085                # $ per compute unit (declines with efficiency)
INFRA_EFFICIENCY_GAIN = 0.003          # monthly unit-cost decline
COMPUTE_PER_MAU = 0.65                 # compute units per MAU/month
COMPUTE_PER_CLOUD_DOLLAR = 0.0000042   # compute units per $ of cloud revenue (inference)

CONTENT_PAYMENTS_PCT = 0.07            # content/payments cost as % of (ads + cloud) revenue

# ----------------------------------------------------------------------------- #
# Headcount & compensation  (heads -> comp -> opex, fully reconciled)
# ----------------------------------------------------------------------------- #
FUNCTIONS = ["Engineering", "Research", "Sales_Marketing", "G_and_A", "Operations"]

# Starting headcount by function
START_HEADCOUNT = {
    "Engineering": 21000, "Research": 4200, "Sales_Marketing": 9800,
    "G_and_A": 6100, "Operations": 7400,
}
# Annualized headcount growth (the key planning lever scenarios will flex)
HEADCOUNT_GROWTH = {
    "Engineering": 0.10, "Research": 0.14, "Sales_Marketing": 0.06,
    "G_and_A": 0.04, "Operations": 0.05,
}
# Fully loaded average annual cash comp by function (salary + bonus + benefits)
AVG_CASH_COMP = {
    "Engineering": 232000, "Research": 268000, "Sales_Marketing": 178000,
    "G_and_A": 154000, "Operations": 121000,
}
# Stock-based comp as a % of cash comp (non-cash; big at these companies)
SBC_PCT = {
    "Engineering": 0.42, "Research": 0.55, "Sales_Marketing": 0.30,
    "G_and_A": 0.22, "Operations": 0.15,
}
# How each function's cost maps to P&L opex lines
FUNCTION_TO_PL = {
    "Engineering": {"R_and_D": 0.85, "COGS": 0.15},
    "Research": {"R_and_D": 1.00},
    "Sales_Marketing": {"S_and_M": 1.00},
    "G_and_A": {"G_and_A": 1.00},
    "Operations": {"COGS": 0.60, "G_and_A": 0.40},
}
# Segment split of each function's headcount (Frontier is R&D heavy)
FUNCTION_SEGMENT_FRONTIER = {
    "Engineering": 0.18, "Research": 0.62, "Sales_Marketing": 0.08,
    "G_and_A": 0.10, "Operations": 0.12,
}

# ----------------------------------------------------------------------------- #
# Marketing spend (paid media, separate from S&M headcount)
# ----------------------------------------------------------------------------- #
MKT_SPEND_START = 8.2e6                 # monthly paid marketing $
MKT_SPEND_GROWTH = 0.04                 # monthly growth at baseline plan

# ----------------------------------------------------------------------------- #
# CapEx, depreciation, working capital, tax  (drive the balance sheet & cash flow)
# ----------------------------------------------------------------------------- #
CAPEX_PCT_OF_REVENUE = 0.28             # data-center heavy (the AI-infra capex story)
PPE_USEFUL_LIFE_MONTHS = 48             # straight-line depreciation life
DEP_ALLOC_COGS = 0.70                   # share of depreciation hitting COGS (infra)
DSO_DAYS = 38                           # days sales outstanding -> AR
DPO_DAYS = 52                           # days payable outstanding -> AP
TAX_RATE = 0.16                         # effective tax rate
INTEREST_INCOME_RATE_ANNUAL = 0.035     # interest earned on cash balance
STARTING_CASH = 3.0e10

# ----------------------------------------------------------------------------- #
# Plan vs Actual: how actuals deviate from the budget set at the start of the year
# ----------------------------------------------------------------------------- #
ACTUAL_NOISE = {        # std of multiplicative noise applied to actual drivers
    "revenue": 0.018, "marketing": 0.05, "headcount": 0.012, "infra": 0.03,
}

# Injected "events" that create explainable variances for the AI narrator.
# (period_index is months from the start of the dataset, 0-based)
INJECTED_EVENTS = [
    {"period": 16, "kind": "demand_miss",   "geo": "EU",   "magnitude": -0.09,
     "note": "Soft EU ad demand on macro weakness"},
    {"period": 22, "kind": "fx_shock",      "geo": "APAC", "magnitude": -0.06,
     "note": "APAC currency depreciation vs USD"},
    {"period": 28, "kind": "hiring_overrun","function": "Engineering", "magnitude": 0.05,
     "note": "Engineering hiring ran ahead of plan for AI initiatives"},
    {"period": 31, "kind": "cloud_upside",  "magnitude": 0.07,
     "note": "Enterprise AI-API adoption beat plan"},
]


@dataclass
class ScenarioOverrides:
    """Knobs a scenario can flex. Defaults = base plan (no change)."""
    label: str = "Base Plan"
    headcount_growth_mult: dict = field(default_factory=dict)   # per-function multiplier
    headcount_freeze: bool = False
    marketing_spend_mult: float = 1.0
    arpu_shock: float = 0.0                # additive to monthly ARPU growth (e.g. -0.03 recession)
    churn_add: float = 0.0                 # additive to monthly cloud churn
    new_geo: bool = False                  # international expansion toggle
    new_geo_ramp_months: int = 18
    capex_mult: float = 1.0
    product_launch: bool = False           # new product revenue ramp
    macro_index: float = 1.0               # <1 = recession demand drag
