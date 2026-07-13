"""
Conversational CFO assistant.

Architecture (the important part): the model NEVER invents numbers. A deterministic
Python layer computes an "evidence pack" from the warehouse (variance bridges, KPI
deltas, forecast). The LLM is handed that pack and asked only to *narrate* it in
executive language. This "calculator-in-the-loop" pattern is what makes an AI finance
assistant safe to put in front of a CFO -- the figures are auditable and reproducible,
the prose is generated.

Two narration backends:
  * template  -> deterministic, runs with zero dependencies (default; great for a demo)
  * llm       -> calls the Anthropic Messages API if ANTHROPIC_API_KEY is set

Intents handled: revenue_change, variance_explanation, budget_performance,
cost_optimization, forecast_change.
"""
from __future__ import annotations
import os
import json
import pandas as pd

from src.analytics.variance import revenue_bridge, comp_bridge, pl_variance
from src.analytics import kpis as K
from src.forecasting.pipeline import ensemble_forecast


# --------------------------------------------------------------------------- #
# 1) Evidence pack -- pure computation, no LLM
# --------------------------------------------------------------------------- #
def build_evidence(question: str, quarter: str, df: pd.DataFrame) -> dict:
    intent = classify_intent(question)
    ev = {"question": question, "quarter": quarter, "intent": intent}

    if intent in ("revenue_change", "variance_explanation"):
        rb = revenue_bridge(quarter, df=df)
        ev["revenue_bridge"] = rb["totals"]
        ev["revenue_bridge_by_geo"] = rb["by_geo"]
        ev["pl_variance"] = pl_variance(quarter, df=df).to_dict("index")
        notes = df[(df["scenario"] == "Reported actuals") &
                   (df["quarter"] == quarter)]["event_notes"]
        ev["event_notes"] = sorted({n for n in notes if n})

    if intent in ("variance_explanation", "budget_performance", "cost_optimization"):
        ev["comp_bridge"] = comp_bridge(quarter, df=df)["totals"]
        ev.setdefault("pl_variance", pl_variance(quarter, df=df).to_dict("index"))

    if intent == "cost_optimization":
        q = K.compute_kpis(K.quarterly(df[df["scenario"] == "Reported actuals"]))
        last = q[q["quarter"] == quarter].iloc[0]
        ev["efficiency"] = {m: float(last[m]) for m in
                            ["rnd_pct_revenue", "snm_pct_revenue", "capex_pct_revenue",
                             "sbc_pct_revenue", "revenue_per_head", "operating_margin"]}

    if intent == "forecast_change":
        hist = df[df["scenario"] == "Reported actuals"].sort_values("date").reset_index(drop=True)
        fc = ensemble_forecast(hist, "revenue", h=6)
        ev["forecast"] = {"future_dates": fc["future_dates"],
                          "ensemble_b": [round(x / 1e9, 2) for x in fc["ensemble"]],
                          "weights": fc["weights"], "backtest_wape": fc["backtest_wape"]}
    return ev


def classify_intent(q: str) -> str:
    ql = q.lower()
    if any(w in ql for w in ["forecast", "outlook", "next quarter", "next two", "projection"]):
        return "forecast_change"
    if any(w in ql for w in ["cost", "optimi", "efficien", "save", "cut"]):
        return "cost_optimization"
    if "revenue" in ql and any(w in ql for w in ["why", "change", "move", "driver", "down", "up"]):
        return "revenue_change"
    if any(w in ql for w in ["budget", "against plan", "vs plan", "versus plan"]):
        return "budget_performance"
    return "variance_explanation"


# --------------------------------------------------------------------------- #
# 2) Narration
# --------------------------------------------------------------------------- #
def _b(x):  # format $ billions/millions
    x = float(x)
    return f"${x/1e9:.2f}B" if abs(x) >= 1e9 else f"${x/1e6:,.0f}M"


def narrate_template(ev: dict) -> str:
    p = [f"**{ev['quarter']} — {ev['intent'].replace('_', ' ').title()}**\n"]
    if "revenue_bridge" in ev:
        t = ev["revenue_bridge"]
        p.append(f"Ads revenue came in at {_b(t['actual'])} vs a plan of {_b(t['plan'])}, "
                 f"a variance of {_b(t['variance'])}. The bridge decomposes as: "
                 f"volume {_b(t['volume'])}, price {_b(t['price'])}, FX {_b(t['fx'])}.")
        geos = ev["revenue_bridge_by_geo"]
        worst = min(geos, key=lambda g: geos[g]["variance"])
        best = max(geos, key=lambda g: geos[g]["variance"])
        p.append(f"{best} was the largest positive contributor ({_b(geos[best]['variance'])}); "
                 f"{worst} was the largest drag ({_b(geos[worst]['variance'])}).")
        if ev.get("event_notes"):
            p.append("Known drivers this period: " + "; ".join(ev["event_notes"]) + ".")
    if "comp_bridge" in ev:
        c = ev["comp_bridge"]
        p.append(f"Compensation varied {_b(c['variance'])} vs plan, of which "
                 f"{_b(c['headcount_effect'])} was headcount (volume) and "
                 f"{_b(c['rate_effect'])} was rate (comp per head).")
    if "efficiency" in ev:
        e = ev["efficiency"]
        p.append(f"Operating margin is {e['operating_margin']*100:.1f}%. "
                 f"R&D is {e['rnd_pct_revenue']*100:.1f}% of revenue, S&M "
                 f"{e['snm_pct_revenue']*100:.1f}%, CapEx {e['capex_pct_revenue']*100:.1f}%. "
                 f"Revenue per head is {_b(e['revenue_per_head'])}. The clearest optimization "
                 f"levers are the lines running above tech-peer benchmarks.")
    if "forecast" in ev:
        f = ev["forecast"]
        series = ", ".join(f"{d}: ${v}B" for d, v in zip(f["future_dates"], f["ensemble_b"]))
        wt = {k: round(float(v), 2) for k, v in f["weights"].items()}
        p.append(f"Six-month revenue outlook (ensemble): {series}. "
                 f"Model weights {wt}, chosen by backtest WAPE.")
    return "\n\n".join(p)


SYSTEM_PROMPT = (
    "You are HELIOS's FP&A CFO assistant. You will be given a JSON 'evidence pack' of "
    "PRE-COMPUTED financial figures. Write a crisp, executive-ready explanation. "
    "RULES: use only numbers present in the evidence pack; never invent or recompute "
    "figures; lead with the answer; quantify every claim; keep it under 180 words."
)


def narrate_llm(ev: dict) -> str:
    """Narrate via Anthropic API if a key is present; else fall back to template."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return narrate_template(ev)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user",
                       "content": f"Evidence pack:\n{json.dumps(ev, default=str, indent=2)}\n\n"
                                  f"Question: {ev['question']}"}])
        return "".join(b.text for b in msg.content if b.type == "text")
    except Exception as e:
        return narrate_template(ev) + f"\n\n_(LLM unavailable: {e}; used template.)_"


def ask(question: str, quarter: str = "2025-Q3", backend: str = "template") -> str:
    df = pd.read_parquet(__import__("pathlib").Path(__file__).resolve().parents[2]
                         / "data" / "gold_monthly.parquet")
    ev = build_evidence(question, quarter, df)
    return narrate_llm(ev) if backend == "llm" else narrate_template(ev)


if __name__ == "__main__":
    for qn in ["Why did revenue change versus plan?",
               "Where are our biggest cost optimization opportunities?",
               "What's the revenue forecast for next two quarters?"]:
        print("Q:", qn)
        print(ask(qn, "2025-Q3"))
        print("-" * 80)
