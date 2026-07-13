"""
KPI engine -- the metric suite a tech-company FP&A team actually reports.

These are the metrics that show up in CFO/board decks and investor materials.
Grouped so a dashboard can render them by audience.
"""
from __future__ import annotations
import pandas as pd


def quarterly(df: pd.DataFrame) -> pd.DataFrame:
    """Roll monthly model output to quarterly with correct aggregation rules.
    Flows (revenue, costs) sum; stocks (headcount, balances) take period-end."""
    flow = ["ads_revenue", "cloud_revenue", "new_geo_revenue", "device_revenue",
            "revenue", "platform_revenue", "frontier_revenue", "cogs", "gross_profit",
            "rnd_expense", "snm_expense", "gna_expense", "opex", "operating_income",
            "sbc", "net_income", "platform_operating_income",
            "frontier_operating_income", "depreciation", "capex", "marketing_spend",
            "cfo", "cfi", "net_change_in_cash"]
    stock = ["headcount_total", "cloud_customers", "cloud_arpu_annual", "total_mau_m",
             "cash", "total_assets", "total_equity", "deferred_revenue", "ppe_net"]
    g = df.groupby(["scenario", "quarter"], sort=False)
    out = g[flow].sum()
    out[stock] = g[stock].last()
    return out.reset_index()


def compute_kpis(q: pd.DataFrame) -> pd.DataFrame:
    """Compute KPIs on a quarterly frame (one scenario or many)."""
    k = q.copy()
    k = k.sort_values(["scenario", "quarter"])
    g = k.groupby("scenario")

    # --- profitability & margins ---
    k["gross_margin"] = k["gross_profit"] / k["revenue"]
    k["operating_margin"] = k["operating_income"] / k["revenue"]
    k["net_margin"] = k["net_income"] / k["revenue"]
    k["fcf"] = k["cfo"] + k["cfi"]                       # free cash flow
    k["fcf_margin"] = k["fcf"] / k["revenue"]

    # --- growth ---
    k["revenue_yoy"] = g["revenue"].pct_change(4)
    k["revenue_qoq"] = g["revenue"].pct_change(1)

    # --- Rule of 40 (growth% + FCF margin%): elite SaaS/tech health metric ---
    k["rule_of_40"] = (k["revenue_yoy"] + k["fcf_margin"]) * 100

    # --- efficiency ---
    k["sbc_pct_revenue"] = k["sbc"] / k["revenue"]
    k["rnd_pct_revenue"] = k["rnd_expense"] / k["revenue"]
    k["snm_pct_revenue"] = k["snm_expense"] / k["revenue"]
    k["capex_pct_revenue"] = k["capex"] / k["revenue"]
    k["revenue_per_head"] = k["revenue"] * 4 / k["headcount_total"]   # annualized

    # --- cloud SaaS KPIs ---
    k["nrr"] = k["cloud_arpu_annual"] / g["cloud_arpu_annual"].shift(4)
    k["new_cloud_customers"] = g["cloud_customers"].diff()
    k["cac"] = k["snm_expense"] / k["new_cloud_customers"].clip(lower=1)
    k["magic_number"] = (g["cloud_revenue"].diff() * 4) / g["snm_expense"].shift(1)

    # --- segment ---
    k["frontier_drag_bps"] = (-k["frontier_operating_income"] / k["revenue"]) * 10000
    return k


KPI_BY_AUDIENCE = {
    "CFO": ["revenue", "operating_margin", "fcf", "fcf_margin", "capex_pct_revenue",
            "sbc_pct_revenue", "rule_of_40", "revenue_per_head"],
    "CEO": ["revenue", "revenue_yoy", "operating_income", "rule_of_40",
            "frontier_operating_income", "nrr"],
    "Board": ["revenue", "revenue_yoy", "operating_margin", "net_margin", "fcf",
              "rule_of_40", "frontier_drag_bps", "capex_pct_revenue"],
    "Investor": ["revenue_yoy", "operating_margin", "fcf_margin", "sbc_pct_revenue",
                 "rule_of_40", "magic_number", "nrr"],
    "Department": ["rnd_pct_revenue", "snm_pct_revenue", "revenue_per_head",
                   "headcount_total"],
}


if __name__ == "__main__":
    from pathlib import Path
    df = pd.read_parquet(Path(__file__).resolve().parents[2] / "data" / "gold_monthly.parquet")
    q = quarterly(df[df["scenario"].isin(["Base Plan"])] if "Base Plan" in df["scenario"].unique()
                  else df)
    k = compute_kpis(quarterly(df))
    cols = ["scenario", "quarter", "revenue", "operating_margin", "rule_of_40",
            "fcf_margin", "revenue_per_head"]
    print(k[k["scenario"] == k["scenario"].iloc[0]][cols].tail(6).to_string(index=False))
