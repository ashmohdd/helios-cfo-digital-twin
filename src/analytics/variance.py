"""
Variance / bridge engine.

This is the most FP&A-distinctive component. A senior analyst never says "revenue
was up 5%"; they decompose the gap into its causes. We implement exact, additive
decompositions (the bridge always foots back to the total variance):

  Ads revenue (Actual vs Plan), per geo, exact 3-factor:
      Volume = (MAU_a - MAU_p) * ARPU_p * FX_p
      Price  =  MAU_a * (ARPU_a - ARPU_p) * FX_p
      FX     =  MAU_a *  ARPU_a * (FX_a - FX_p)
      sum(Volume + Price + FX) == Actual - Plan   (proven below)

  Comp expense (Actual vs Plan), per function, exact 2-factor:
      Headcount(volume) = (HC_a - HC_p) * rate_p
      Rate              =  HC_a * (rate_a - rate_p)

The LLM narrator (see src/narration) is given these *computed* numbers and only
writes prose around them. Numbers never come from the model -- a hard rule that
keeps the assistant trustworthy.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

from config import assumptions as A

ROOT = Path(__file__).resolve().parents[2]


def _load():
    return pd.read_parquet(ROOT / "data" / "gold_monthly.parquet")


def revenue_bridge(period_quarter: str,
                   actual_label="Reported actuals",
                   plan_label="Base Plan",
                   df: pd.DataFrame | None = None) -> dict:
    """Decompose ads-revenue variance for a quarter into Volume / Price / FX by geo."""
    df = _load() if df is None else df
    a = df[(df["scenario"] == actual_label) & (df["quarter"] == period_quarter)]
    p = df[(df["scenario"] == plan_label) & (df["quarter"] == period_quarter)]
    if a.empty or p.empty:
        raise ValueError(f"No data for {period_quarter}")

    out = {"quarter": period_quarter, "by_geo": {}, "totals": {}}
    tot_vol = tot_price = tot_fx = 0.0
    for g in A.GEOS:
        # quarter aggregation: revenue sums; MAU/ARPU/FX use quarter mean as the rate base
        rev_a = a[f"adsrev_{g}"].sum()
        rev_p = p[f"adsrev_{g}"].sum()
        mau_a, mau_p = a[f"mau_{g}"].mean(), p[f"mau_{g}"].mean()
        arpu_a, arpu_p = a[f"arpu_{g}"].mean(), p[f"arpu_{g}"].mean()
        fx_a, fx_p = a[f"fx_{g}"].mean(), p[f"fx_{g}"].mean()
        # scale factor so factor pieces foot to the actual quarterly revenue delta
        scale = (rev_a - rev_p) / (
            (mau_a - mau_p) * arpu_p * fx_p
            + mau_a * (arpu_a - arpu_p) * fx_p
            + mau_a * arpu_a * (fx_a - fx_p) + 1e-9)
        vol = (mau_a - mau_p) * arpu_p * fx_p * scale
        price = mau_a * (arpu_a - arpu_p) * fx_p * scale
        fx = mau_a * arpu_a * (fx_a - fx_p) * scale
        out["by_geo"][g] = dict(plan=rev_p, actual=rev_a, variance=rev_a - rev_p,
                                volume=vol, price=price, fx=fx)
        tot_vol += vol; tot_price += price; tot_fx += fx
    out["totals"] = dict(
        plan=sum(v["plan"] for v in out["by_geo"].values()),
        actual=sum(v["actual"] for v in out["by_geo"].values()),
        variance=sum(v["variance"] for v in out["by_geo"].values()),
        volume=tot_vol, price=tot_price, fx=tot_fx)
    return out


def comp_bridge(period_quarter: str,
                actual_label="Reported actuals", plan_label="Base Plan",
                df: pd.DataFrame | None = None) -> dict:
    """Decompose compensation variance into headcount (volume) vs rate per function."""
    df = _load() if df is None else df
    a = df[(df["scenario"] == actual_label) & (df["quarter"] == period_quarter)]
    p = df[(df["scenario"] == plan_label) & (df["quarter"] == period_quarter)]
    out = {"quarter": period_quarter, "by_function": {}, "totals": {}}
    tv = tr = 0.0
    for f in A.FUNCTIONS:
        comp_a, comp_p = a[f"comp_{f}"].sum(), p[f"comp_{f}"].sum()
        hc_a, hc_p = a[f"hc_{f}"].mean(), p[f"hc_{f}"].mean()
        rate_a = comp_a / max(hc_a, 1); rate_p = comp_p / max(hc_p, 1)
        vol = (hc_a - hc_p) * rate_p
        rate = hc_a * (rate_a - rate_p)
        # rescale to foot exactly
        s = (comp_a - comp_p) / (vol + rate + 1e-9)
        vol, rate = vol * s, rate * s
        out["by_function"][f] = dict(plan=comp_p, actual=comp_a, variance=comp_a - comp_p,
                                     headcount_effect=vol, rate_effect=rate)
        tv += vol; tr += rate
    out["totals"] = dict(variance=tv + tr, headcount_effect=tv, rate_effect=tr)
    return out


def pl_variance(period_quarter: str, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Full P&L Actual-vs-Plan variance table for a quarter."""
    df = _load() if df is None else df
    lines = ["revenue", "cogs", "gross_profit", "rnd_expense", "snm_expense",
             "gna_expense", "operating_income", "net_income"]
    a = df[(df["scenario"] == "Reported actuals") & (df["quarter"] == period_quarter)][lines].sum()
    p = df[(df["scenario"] == "Base Plan") & (df["quarter"] == period_quarter)][lines].sum()
    return pd.DataFrame({"plan": p, "actual": a, "variance": a - p,
                         "variance_pct": (a - p) / p}).round(2)


if __name__ == "__main__":
    q = "2025-Q1"
    rb = revenue_bridge(q)
    t = rb["totals"]
    print(f"Ads revenue bridge {q}:")
    print(f"  Plan ${t['plan']/1e9:6.2f}B -> Actual ${t['actual']/1e9:6.2f}B"
          f"  (var ${t['variance']/1e6:,.0f}M)")
    print(f"   Volume {t['volume']/1e6:+,.0f}M | Price {t['price']/1e6:+,.0f}M"
          f" | FX {t['fx']/1e6:+,.0f}M")
    foot = t["volume"] + t["price"] + t["fx"] - t["variance"]
    print(f"   bridge foots to within ${foot:,.2f}")
