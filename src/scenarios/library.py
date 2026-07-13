"""
Scenario library.

Each scenario is just an override on the operating model's assumptions. Because the
model is fully articulated, a single knob flows all the way through to the P&L,
balance sheet, cash flow and KPIs -- which is what makes the what-if analysis *real*
rather than cosmetic. Example: a marketing cut lowers spend -> the response curve
produces fewer logo adds -> lower forward cloud revenue -> margin up short-term but
growth down. That second-order effect is the whole point of driver-based planning.
"""
from config.assumptions import ScenarioOverrides

SCENARIO_LIBRARY = {
    # NOTE: the base case is the model's default run ("Base Plan"), always present.
    "bull": ScenarioOverrides(
        label="Bull Case (demand tailwind + launch lands)",
        arpu_shock=0.02, macro_index=1.05,
        product_launch=True, marketing_spend_mult=1.10,
    ),
    "bear": ScenarioOverrides(
        label="Bear Case (macro drag + elevated churn)",
        arpu_shock=-0.03, churn_add=0.008, macro_index=0.90,
        marketing_spend_mult=0.80, capex_mult=0.85,
    ),
    "hiring_freeze": ScenarioOverrides(
        label="Hiring Freeze (all functions)",
        headcount_freeze=True,
    ),
    "eng_surge": ScenarioOverrides(
        label="Engineering hiring +20%",
        headcount_growth_mult={"Engineering": 1.20, "Research": 1.20},
    ),
    "intl_expansion": ScenarioOverrides(
        label="International expansion (new geo)",
        new_geo=True, new_geo_ramp_months=18,
        marketing_spend_mult=1.15, capex_mult=1.10,
    ),
    "marketing_cut": ScenarioOverrides(
        label="Marketing budget -30%",
        marketing_spend_mult=0.70,
    ),
    "recession": ScenarioOverrides(
        label="Economic recession",
        arpu_shock=-0.03, churn_add=0.006, macro_index=0.92,
        marketing_spend_mult=0.85,
    ),
    "product_launch": ScenarioOverrides(
        label="Major AI product launch",
        product_launch=True, marketing_spend_mult=1.25, capex_mult=1.20,
    ),
}
