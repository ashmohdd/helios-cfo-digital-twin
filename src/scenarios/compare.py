"""
Scenario comparison.

Runs every scenario in the library against the base plan and reports the full-year
(FY, last 12 months) impact on the metrics an executive cares about. Because each
scenario is a driver override flowing through the whole model, the deltas capture
second-order effects (e.g. a marketing cut lifts near-term margin but lowers forward
revenue via the logo-response curve).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
METRICS = ["revenue", "operating_income", "net_income", "frontier_operating_income",
           "capex", "headcount_total"]


def compare(df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data" / "gold_monthly.parquet") if df is None else df
    last_year = df["year"].max()
    fy = df[df["year"] == last_year]

    def fy_value(scenario, metric):
        s = fy[fy["scenario"] == scenario]
        return s[metric].iloc[-1] if metric == "headcount_total" else s[metric].sum()

    base = "Base Plan"
    rows = []
    for scen in df["scenario"].unique():
        if scen in (base, "Reported actuals"):
            continue
        row = {"scenario": scen}
        for m in METRICS:
            b, v = fy_value(base, m), fy_value(scen, m)
            row[f"{m}_base"] = b
            row[f"{m}_scn"] = v
            row[f"{m}_delta"] = v - b
            row[f"{m}_delta_pct"] = (v - b) / b if b else 0.0
        # derived
        row["op_margin_base"] = fy_value(base, "operating_income") / fy_value(base, "revenue")
        row["op_margin_scn"] = fy_value(scen, "operating_income") / fy_value(scen, "revenue")
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    c = compare()
    show = c[["scenario", "revenue_delta_pct", "operating_income_delta_pct",
              "op_margin_base", "op_margin_scn", "headcount_total_delta"]].copy()
    show["revenue_delta_pct"] = (show["revenue_delta_pct"] * 100).round(1)
    show["operating_income_delta_pct"] = (show["operating_income_delta_pct"] * 100).round(1)
    show["op_margin_base"] = (show["op_margin_base"] * 100).round(1)
    show["op_margin_scn"] = (show["op_margin_scn"] * 100).round(1)
    show["headcount_total_delta"] = show["headcount_total_delta"].round(0)
    show.columns = ["Scenario", "Rev Δ%", "OI Δ%", "OpMgn base%", "OpMgn scn%", "HC Δ"]
    print(show.to_string(index=False))
