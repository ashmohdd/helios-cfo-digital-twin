"""
HELIOS integrated operating model.

run_model() walks month by month and builds a fully articulated three-statement
model from the driver assumptions:

    drivers  ->  P&L  ->  Balance Sheet  ->  Cash Flow

The balance sheet balances *by construction*. Walking the deltas:

    d_assets = d_cash + d_AR + d_PPE
    d_cash   = NI + dep + sbc - d_AR + d_AP + d_deferred - capex      (indirect CFS)
    d_PPE    = capex - dep
  => d_assets = NI + sbc + d_AP + d_deferred
    d_L+E    = (d_AP + d_deferred) + (NI + sbc)                       (RE += NI, APIC += SBC)
  => d_assets == d_(L+E)   -> ties every period.

This articulation is the thing a senior FP&A interviewer checks first.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from config.assumptions import *  # noqa: F401,F403
from config import assumptions as A


def _month_index(n):
    base = pd.Timestamp(f"{A.START_YEAR}-01-01")
    return [base + pd.DateOffset(months=i) for i in range(n)]


def run_model(scenario: A.ScenarioOverrides | None = None,
              mode: str = "plan",
              seed: int | None = None) -> pd.DataFrame:
    """
    Return a tidy monthly DataFrame with drivers, P&L, BS and CFS line items.

    mode : "plan"   -> deterministic budget
           "actual" -> plan + realistic noise + injected events
    """
    if scenario is None:
        scenario = A.ScenarioOverrides()
    rng = np.random.default_rng(A.RANDOM_SEED if seed is None else seed)
    n = A.N_YEARS * A.PERIODS_PER_YEAR
    dates = _month_index(n)
    rows = []

    # ----- opening balance-sheet state -----
    cash = A.STARTING_CASH
    ar = 0.0
    ap = 0.0
    deferred = 0.0
    ppe_net = 0.0
    accumulated_capex_layers = []      # (amount, months_remaining) for straight-line dep
    other_assets = 1.2e10              # goodwill / intangibles / investments (held constant)
    retained_earnings = None           # set after first period's opening BS is sized
    paid_in_capital = None
    opening_set = False

    # ----- opening operating state -----
    mau = dict(A.GEO_START_MAU)
    arpu = dict(A.GEO_START_ARPU)
    cloud_customers = float(A.CLOUD_START_CUSTOMERS)
    cloud_arpu_annual = A.CLOUD_START_ARPU_ANNUAL
    device_units = float(A.DEVICE_START_UNITS)
    device_bom = A.DEVICE_BOM
    infra_unit_cost = A.INFRA_UNIT_COST
    headcount = {f: float(A.START_HEADCOUNT[f]) for f in A.FUNCTIONS}
    mkt_spend = A.MKT_SPEND_START
    fx = dict(A.GEO_FX_BASE)

    # new-geo expansion ramp state
    new_geo_units = 0.0

    m_growth = (1 + 0.0)  # placeholder

    for t in range(n):
        d = dates[t]
        month = d.month
        year = d.year
        season = A.SEASONALITY[month]

        # ---- scenario + actual adjustments to growth knobs ----
        macro = scenario.macro_index
        noise = lambda key: (1 + rng.normal(0, A.ACTUAL_NOISE[key]) if mode == "actual" else 1.0)

        # injected events (actual only)
        event_mau_mult = {g: 1.0 for g in A.GEOS}
        event_arpu_mult = {g: 1.0 for g in A.GEOS}
        event_fx_mult = {g: 1.0 for g in A.GEOS}
        event_cloud_mult = 1.0
        event_hc_mult = {f: 1.0 for f in A.FUNCTIONS}
        event_notes = []
        if mode == "actual":
            for ev in A.INJECTED_EVENTS:
                if ev["period"] == t:
                    if ev["kind"] == "demand_miss":      # soft ad demand -> pricing
                        event_arpu_mult[ev["geo"]] *= (1 + ev["magnitude"])
                    elif ev["kind"] == "fx_shock":       # currency move -> FX
                        event_fx_mult[ev["geo"]] *= (1 + ev["magnitude"])
                    elif ev["kind"] == "hiring_overrun":
                        event_hc_mult[ev["function"]] *= (1 + ev["magnitude"])
                    elif ev["kind"] == "cloud_upside":
                        event_cloud_mult *= (1 + ev["magnitude"])
                    event_notes.append(ev["note"])

        # ============================ DRIVERS ============================ #
        # ---- ads revenue by geo (drivers perturbed in actual so bridges decompose) ----
        ads_rev = 0.0
        geo_detail = {}
        mau_noise = lambda: (1 + rng.normal(0, A.ACTUAL_NOISE["revenue"] * 0.4) if mode == "actual" else 1.0)
        arpu_noise = lambda: (1 + rng.normal(0, A.ACTUAL_NOISE["revenue"] * 0.7) if mode == "actual" else 1.0)
        for g in A.GEOS:
            mg = (1 + A.GEO_MAU_GROWTH[g]) ** (1 / 12)
            ag = (1 + A.GEO_ARPU_GROWTH[g] + scenario.arpu_shock) ** (1 / 12)
            mau[g] *= mg * mau_noise() * event_mau_mult[g]
            arpu[g] *= ag * arpu_noise() * event_arpu_mult[g]
            fx[g] = A.GEO_FX_BASE[g] * event_fx_mult[g] * (
                1 + rng.normal(0, A.FX_VOL) if mode == "actual" else 1.0)
            eff_arpu = arpu[g] * season * fx[g] * macro
            rev_g = mau[g] * 1e6 * eff_arpu / 12.0
            ads_rev += rev_g
            geo_detail[g] = dict(mau=mau[g], arpu=arpu[g] * season * macro, fx=fx[g], rev=rev_g)

        # ---- cloud / AI-API revenue ----
        # marketing response -> gross logo adds
        spend_eff = mkt_spend * scenario.marketing_spend_mult * noise("marketing")
        response = 1 + A.MKT_RESPONSE_ALPHA * np.log1p(spend_eff / A.MKT_REFERENCE_SPEND)
        gross_adds = A.CLOUD_GROSS_LOGO_ADDS_BASE * response * macro
        churn = (A.CLOUD_MONTHLY_CHURN + scenario.churn_add)
        cloud_customers = cloud_customers * (1 - churn) + gross_adds
        cloud_arpu_annual *= (1 + A.CLOUD_NET_EXPANSION)
        cloud_rev = cloud_customers * cloud_arpu_annual / 12.0 * macro * event_cloud_mult
        if scenario.product_launch:
            ramp = min(1.0, t / 12.0)
            cloud_rev *= (1 + 0.18 * ramp)   # new product accretes to platform revenue

        # ---- new-geo expansion (international) ----
        new_geo_rev = 0.0
        if scenario.new_geo:
            ramp = min(1.0, max(0.0, t) / scenario.new_geo_ramp_months)
            new_geo_units = 95.0 * ramp                     # MAU in millions, ramping
            new_geo_rev = new_geo_units * 1e6 * 2.4 * season / 12.0   # low ARPU emerging mkt

        # ---- devices revenue ----
        device_units *= (1 + A.DEVICE_UNIT_GROWTH)
        device_bom *= (1 - A.DEVICE_BOM_LEARNING)
        device_rev = device_units * A.DEVICE_ASP

        revenue = ads_rev + cloud_rev + new_geo_rev + device_rev
        platform_rev = ads_rev + cloud_rev + new_geo_rev
        frontier_rev = device_rev

        # ============================ HEADCOUNT -> COMP ============================ #
        comp_cash = {f: 0.0 for f in A.FUNCTIONS}
        sbc = {f: 0.0 for f in A.FUNCTIONS}
        for f in A.FUNCTIONS:
            g_annual = A.HEADCOUNT_GROWTH[f]
            if scenario.headcount_freeze:
                g_annual = 0.0
            g_annual *= scenario.headcount_growth_mult.get(f, 1.0)
            headcount[f] *= (1 + g_annual) ** (1 / 12)
            headcount[f] *= event_hc_mult[f] * noise("headcount")
            comp_cash[f] = headcount[f] * A.AVG_CASH_COMP[f] / 12.0
            sbc[f] = comp_cash[f] * A.SBC_PCT[f]
        total_sbc = sum(sbc.values())

        # ============================ COGS / OPEX ============================ #
        compute_units = (sum(mau[g] for g in A.GEOS) * 1e6 * A.COMPUTE_PER_MAU
                         + cloud_rev * A.COMPUTE_PER_CLOUD_DOLLAR * 1e6)
        infra_unit_cost *= (1 - A.INFRA_EFFICIENCY_GAIN)
        infra_cost = compute_units * infra_unit_cost / 1e6 * noise("infra")
        content_payments = (ads_rev + cloud_rev) * A.CONTENT_PAYMENTS_PCT
        device_cogs = device_units * device_bom

        # capex & depreciation
        capex = revenue * A.CAPEX_PCT_OF_REVENUE * scenario.capex_mult
        accumulated_capex_layers.append([capex, A.PPE_USEFUL_LIFE_MONTHS])
        depreciation = 0.0
        for layer in accumulated_capex_layers:
            if layer[1] > 0:
                depreciation += layer[0] / A.PPE_USEFUL_LIFE_MONTHS
                layer[1] -= 1
        dep_cogs = depreciation * A.DEP_ALLOC_COGS
        dep_opex = depreciation - dep_cogs

        # distribute comp into P&L lines
        pl_comp = {"R_and_D": 0.0, "S_and_M": 0.0, "G_and_A": 0.0, "COGS": 0.0}
        for f in A.FUNCTIONS:
            for line, share in A.FUNCTION_TO_PL[f].items():
                pl_comp[line] += comp_cash[f] * share

        cogs = infra_cost + content_payments + device_cogs + dep_cogs + pl_comp["COGS"]
        gross_profit = revenue - cogs

        rnd = pl_comp["R_and_D"] + dep_opex * 0.5 + (total_sbc * 0.45)
        snm = pl_comp["S_and_M"] + spend_eff + (total_sbc * 0.25)
        gna = pl_comp["G_and_A"] + dep_opex * 0.5 + (total_sbc * 0.30)
        opex = rnd + snm + gna
        operating_income = gross_profit - opex

        interest_income = cash * (A.INTEREST_INCOME_RATE_ANNUAL / 12.0)
        pretax = operating_income + interest_income
        tax = max(0.0, pretax) * A.TAX_RATE
        net_income = pretax - tax

        # segment operating income (Frontier loses money on purpose)
        frontier_opex = (rnd * 0.45 + snm * 0.10 + gna * 0.12)
        frontier_cogs = device_cogs + dep_cogs * 0.15
        frontier_oi = frontier_rev - frontier_cogs - frontier_opex
        platform_oi = operating_income - frontier_oi

        # ============================ BALANCE SHEET ============================ #
        new_ar = revenue * (A.DSO_DAYS / 30.4)
        cash_costs = cogs + opex - dep_cogs - dep_opex - total_sbc   # cash operating costs
        new_ap = cash_costs * (A.DPO_DAYS / 30.4)
        new_deferred = cloud_rev * A.CLOUD_DEFERRED_REV_PCT * 3.0     # ~quarter of upfront
        new_ppe = ppe_net + capex - depreciation

        d_ar = new_ar - ar
        d_ap = new_ap - ap
        d_def = new_deferred - deferred

        # ============================ CASH FLOW (indirect) ============================ #
        cfo = net_income + depreciation + total_sbc - d_ar + d_ap + d_def
        cfi = -capex
        cff = 0.0
        net_cf = cfo + cfi + cff

        cash += net_cf
        ar, ap, deferred, ppe_net = new_ar, new_ap, new_deferred, new_ppe

        total_assets = cash + ar + ppe_net + other_assets
        total_liabilities = ap + deferred
        if not opening_set:
            # size opening equity so the very first balance sheet ties
            equity_needed = total_assets - total_liabilities
            paid_in_capital = equity_needed * 0.6
            retained_earnings = equity_needed * 0.4
            opening_set = True
        else:
            retained_earnings += net_income
            paid_in_capital += total_sbc
        total_equity = retained_earnings + paid_in_capital
        balance_check = total_assets - (total_liabilities + total_equity)

        # grow marketing spend along plan path
        mkt_spend *= (1 + A.MKT_SPEND_GROWTH)

        rows.append(dict(
            date=d, year=year, month=month,
            quarter=f"{year}-Q{(month-1)//3 + 1}",
            mode=mode, scenario=scenario.label,
            # revenue
            ads_revenue=ads_rev, cloud_revenue=cloud_rev, new_geo_revenue=new_geo_rev,
            device_revenue=device_rev, revenue=revenue,
            platform_revenue=platform_rev, frontier_revenue=frontier_rev,
            # drivers
            total_mau_m=sum(mau[g] for g in A.GEOS), cloud_customers=cloud_customers,
            cloud_arpu_annual=cloud_arpu_annual, device_units=device_units,
            marketing_spend=spend_eff, gross_logo_adds=gross_adds, churn_rate=churn,
            compute_units=compute_units, infra_unit_cost=infra_unit_cost,
            # P&L
            cogs=cogs, gross_profit=gross_profit,
            rnd_expense=rnd, snm_expense=snm, gna_expense=gna, opex=opex,
            operating_income=operating_income, sbc=total_sbc,
            interest_income=interest_income, tax=tax, net_income=net_income,
            platform_operating_income=platform_oi, frontier_operating_income=frontier_oi,
            depreciation=depreciation, capex=capex,
            # headcount
            headcount_total=sum(headcount.values()),
            **{f"hc_{f}": headcount[f] for f in A.FUNCTIONS},
            **{f"comp_{f}": comp_cash[f] for f in A.FUNCTIONS},
            # balance sheet
            cash=cash, accounts_receivable=ar, accounts_payable=ap,
            deferred_revenue=deferred, ppe_net=ppe_net, other_assets=other_assets,
            total_assets=total_assets, total_liabilities=total_liabilities,
            retained_earnings=retained_earnings, paid_in_capital=paid_in_capital,
            total_equity=total_equity, balance_check=balance_check,
            # cash flow
            cfo=cfo, cfi=cfi, cff=cff, net_change_in_cash=net_cf,
            event_notes="; ".join(event_notes),
            # per-geo detail (for price/volume/mix/FX variance bridges)
            **{f"mau_{g}": geo_detail[g]["mau"] for g in A.GEOS},
            **{f"arpu_{g}": geo_detail[g]["arpu"] for g in A.GEOS},
            **{f"fx_{g}": geo_detail[g]["fx"] for g in A.GEOS},
            **{f"adsrev_{g}": geo_detail[g]["rev"] for g in A.GEOS},
        ))

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run_model(mode="actual")
    worst = df["balance_check"].abs().max()
    print(f"Periods: {len(df)}  |  worst balance-sheet imbalance: ${worst:,.6f}")
    print(df.groupby("year")[["revenue", "operating_income", "net_income",
                              "frontier_operating_income"]].sum().round(0))
