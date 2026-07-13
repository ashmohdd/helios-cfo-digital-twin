"""
Automated executive reporting.

Generates three artifacts straight from the warehouse + analytics layers:
  * Quarterly Business Review (QBR)
  * Board report
  * Earnings-call-style summary

Same discipline as the assistant: every figure is computed; prose is assembled around
computed figures. With ANTHROPIC_API_KEY set, narrative sections can be upgraded to
LLM prose via src.narration.cfo_assistant.narrate_llm.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

from src.analytics import kpis as K
from src.analytics.variance import revenue_bridge, pl_variance
from src.forecasting.pipeline import ensemble_forecast

ROOT = Path(__file__).resolve().parents[2]


def _load():
    return pd.read_parquet(ROOT / "data" / "gold_monthly.parquet")


def _b(x):
    x = float(x)
    return f"${x/1e9:.2f}B" if abs(x) >= 1e9 else f"${x/1e6:,.0f}M"


def quarterly_business_review(quarter: str = "2025-Q3") -> str:
    df = _load()
    act = df[df["scenario"] == "Reported actuals"]
    kq = K.compute_kpis(K.quarterly(act))
    row = kq[kq["quarter"] == quarter].iloc[0]
    rb = revenue_bridge(quarter, df=df)["totals"]
    plv = pl_variance(quarter, df=df)

    md = [f"# HELIOS — Quarterly Business Review · {quarter}",
          "_Prepared by FP&A · figures computed from the warehouse_\n",
          "## 1. Headline",
          f"- Revenue **{_b(row['revenue'])}**, {row['revenue_yoy']*100:.1f}% YoY",
          f"- Operating margin **{row['operating_margin']*100:.1f}%**, "
          f"FCF margin **{row['fcf_margin']*100:.1f}%**",
          f"- Rule of 40: **{row['rule_of_40']:.0f}** "
          f"({'above' if row['rule_of_40']>=40 else 'below'} the 40 threshold)",
          f"- Frontier segment operating loss **{_b(row['frontier_operating_income'])}** "
          f"({row['frontier_drag_bps']:.0f} bps drag on company margin)\n",
          "## 2. Revenue vs Plan — bridge",
          f"Ads revenue {_b(rb['actual'])} vs plan {_b(rb['plan'])} "
          f"(variance {_b(rb['variance'])}):",
          f"- Volume: {_b(rb['volume'])}",
          f"- Price: {_b(rb['price'])}",
          f"- FX: {_b(rb['fx'])}\n",
          "## 3. P&L vs Plan",
          "| Line | Plan | Actual | Var | Var % |",
          "|---|--:|--:|--:|--:|"]
    for line, r in plv.iterrows():
        md.append(f"| {line} | {_b(r['plan'])} | {_b(r['actual'])} | "
                  f"{_b(r['variance'])} | {r['variance_pct']*100:+.1f}% |")
    md += ["\n## 4. Efficiency",
           f"- R&D {row['rnd_pct_revenue']*100:.1f}% of revenue · "
           f"S&M {row['snm_pct_revenue']*100:.1f}% · CapEx {row['capex_pct_revenue']*100:.1f}%",
           f"- SBC {row['sbc_pct_revenue']*100:.1f}% of revenue · "
           f"Revenue/head {_b(row['revenue_per_head'])} (annualized)",
           f"- Net revenue retention (cloud): {row['nrr']*100:.0f}%\n"]
    return "\n".join(md)


def board_report(quarter: str = "2025-Q3") -> str:
    df = _load()
    fc = ensemble_forecast(
        df[df["scenario"] == "Reported actuals"].sort_values("date").reset_index(drop=True),
        "revenue", h=6)
    qbr = quarterly_business_review(quarter)
    fwd = ", ".join(f"{d}: ${v/1e9:.2f}B" for d, v in
                    zip(fc["future_dates"], fc["ensemble"]))
    return (f"# HELIOS — Board of Directors Report · {quarter}\n\n"
            f"{qbr}\n\n## 5. Forward outlook (ensemble forecast)\n"
            f"Next 6 months revenue: {fwd}.\n\n"
            f"Forecast is an inverse-WAPE ensemble "
            f"({', '.join(f'{k} {round(v*100)}%' for k, v in fc['weights'].items())}); "
            f"weights set by walk-forward backtest.\n\n"
            f"## 6. Capital allocation note\n"
            f"CapEx intensity reflects continued data-center / AI-infrastructure buildout. "
            f"The Frontier segment remains a funded strategic bet; its operating loss is "
            f"the primary discretionary lever available to management on company margin.")


def earnings_call_summary(quarter: str = "2025-Q3") -> str:
    df = _load()
    kq = K.compute_kpis(K.quarterly(df[df["scenario"] == "Reported actuals"]))
    row = kq[kq["quarter"] == quarter].iloc[0]
    return (f"# HELIOS — {quarter} Earnings Summary (illustrative)\n\n"
            f"HELIOS reported {quarter} revenue of {_b(row['revenue'])}, up "
            f"{row['revenue_yoy']*100:.0f}% year over year, with an operating margin of "
            f"{row['operating_margin']*100:.0f}%. Free cash flow margin was "
            f"{row['fcf_margin']*100:.0f}%. Growth was led by the Platform segment "
            f"(ads and cloud/AI), while the company continued to invest in the Frontier "
            f"segment, which posted an operating loss of {_b(row['frontier_operating_income'])}. "
            f"Management cited disciplined hiring and infrastructure efficiency as drivers of "
            f"margin, alongside elevated capital expenditure of "
            f"{row['capex_pct_revenue']*100:.0f}% of revenue tied to AI capacity.")


if __name__ == "__main__":
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "QBR_2025Q3.md").write_text(quarterly_business_review())
    (out / "Board_2025Q3.md").write_text(board_report())
    (out / "Earnings_2025Q3.md").write_text(earnings_call_summary())
    print("Reports written to reports/. Preview:\n")
    print(quarterly_business_review()[:900])
