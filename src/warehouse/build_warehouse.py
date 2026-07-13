"""
ETL / build the HELIOS warehouse.

Pipeline:  run_model (plan, actual, + named scenarios)
        -> tidy CSVs (data/raw)              [extract/stage]
        -> melt into star-schema fact tables [transform]
        -> load SQLite warehouse (data/helios.db) and Parquet gold layer [load]

In production this DAG is the dbt/Airflow job; here it is one runnable script so a
recruiter can `python -m src.warehouse.build_warehouse` and get a populated DB.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd

from config import assumptions as A
from src.generation.model import run_model
from src.scenarios.library import SCENARIO_LIBRARY

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB = DATA / "helios.db"

PL_ACCOUNTS = [
    ("ads_revenue", "PL", "Revenue"), ("cloud_revenue", "PL", "Revenue"),
    ("new_geo_revenue", "PL", "Revenue"), ("device_revenue", "PL", "Revenue"),
    ("revenue", "PL", "Revenue"), ("cogs", "PL", "COGS"),
    ("gross_profit", "PL", "Subtotal"), ("rnd_expense", "PL", "OpEx"),
    ("snm_expense", "PL", "OpEx"), ("gna_expense", "PL", "OpEx"),
    ("operating_income", "PL", "Subtotal"), ("sbc", "PL", "Memo"),
    ("interest_income", "PL", "Below the line"), ("tax", "PL", "Below the line"),
    ("net_income", "PL", "Subtotal"),
    ("platform_operating_income", "PL", "Segment"),
    ("frontier_operating_income", "PL", "Segment"),
]


def _date_key(ts): return int(pd.Timestamp(ts).strftime("%Y%m%d"))


def build():
    DATA.mkdir(exist_ok=True)
    (DATA / "raw").mkdir(exist_ok=True)

    # 1) run all model variants -------------------------------------------------
    frames = {
        "base_plan": run_model(mode="plan"),
        "actual":    run_model(mode="actual"),
    }
    for code, scen in SCENARIO_LIBRARY.items():
        frames[code] = run_model(scenario=scen, mode="plan")

    # canonical, human-readable scenario labels (used by the gold layer + analytics)
    labels = {"base_plan": "Base Plan", "actual": "Reported actuals"}
    labels.update({code: scen.label for code, scen in SCENARIO_LIBRARY.items()})
    for code, df in frames.items():
        df["scenario"] = labels[code]

    long = pd.concat(frames.values(), ignore_index=True)
    long.to_parquet(DATA / "gold_monthly.parquet", index=False)   # gold layer
    long.to_csv(DATA / "raw" / "model_monthly.csv", index=False)

    # 2) connect + create schema ------------------------------------------------
    con = sqlite3.connect(DB)
    con.executescript((ROOT / "sql" / "schema.sql").read_text())

    # 3) dimensions -------------------------------------------------------------
    dim_date = (long[["date", "year", "quarter", "month"]].drop_duplicates()
                .assign(date_key=lambda d: d["date"].map(_date_key),
                        fiscal_period=lambda d: d["date"].map(lambda x: pd.Timestamp(x).strftime("%Y-%m")),
                        date=lambda d: d["date"].astype(str)))
    dim_date.to_sql("dim_date", con, if_exists="append", index=False)

    pd.DataFrame({"geo_key": range(1, len(A.GEOS) + 1), "geo_code": A.GEOS,
                  "geo_name": A.GEOS, "region": A.GEOS}).to_sql(
        "dim_geo", con, if_exists="append", index=False)

    pd.DataFrame({"function_key": range(1, len(A.FUNCTIONS) + 1),
                  "function_code": A.FUNCTIONS,
                  "cost_center": A.FUNCTIONS}).to_sql(
        "dim_function", con, if_exists="append", index=False)

    pd.DataFrame({"segment_key": [1, 2], "segment_code": ["Platform", "Frontier"],
                  "description": ["Ads + Cloud/AI-API engine",
                                  "AR / AI-devices moonshot"]}).to_sql(
        "dim_segment", con, if_exists="append", index=False)

    scen_rows = [("base_plan", "plan", "Annual operating plan / budget"),
                 ("actual", "actual", "Reported actuals")]
    for code, scen in SCENARIO_LIBRARY.items():
        scen_rows.append((code, "scenario", scen.label))
    pd.DataFrame(scen_rows, columns=["scenario_code", "scenario_type", "description"]).assign(
        scenario_key=lambda d: range(1, len(d) + 1)).to_sql(
        "dim_scenario", con, if_exists="append", index=False)

    pd.DataFrame([(c, s, g) for c, s, g in PL_ACCOUNTS],
                 columns=["account_code", "statement", "line_group"]).assign(
        account_key=lambda d: range(1, len(d) + 1), sign=1).to_sql(
        "dim_account", con, if_exists="append", index=False)

    # key lookups
    scen_key = dict(con.execute("SELECT scenario_code, scenario_key FROM dim_scenario").fetchall())
    acct_key = dict(con.execute("SELECT account_code, account_key FROM dim_account").fetchall())
    geo_key = dict(con.execute("SELECT geo_code, geo_key FROM dim_geo").fetchall())
    func_key = dict(con.execute("SELECT function_code, function_key FROM dim_function").fetchall())

    # 4) facts ------------------------------------------------------------------
    def with_keys(df, code):
        df = df.copy()
        df["date_key"] = df["date"].map(_date_key)
        df["scenario_key"] = scen_key[code]
        return df

    pl_rows, bs_rows, cf_rows, drv_rows = [], [], [], []
    for code, df in frames.items():
        df = with_keys(df, code)
        for acct, _, _ in PL_ACCOUNTS:
            sub = df[["date_key", "scenario_key", acct]].rename(columns={acct: "amount"})
            sub["account_key"] = acct_key[acct]
            sub["segment_key"] = (1 if acct == "platform_operating_income"
                                  else 2 if acct == "frontier_operating_income" else None)
            pl_rows.append(sub)
        bs_rows.append(df[["date_key", "scenario_key", "cash", "accounts_receivable",
                           "ppe_net", "other_assets", "total_assets", "accounts_payable",
                           "deferred_revenue", "total_liabilities", "retained_earnings",
                           "paid_in_capital", "total_equity", "balance_check"]])
        cf_rows.append(df[["date_key", "scenario_key", "cfo", "cfi", "cff",
                           "net_change_in_cash", "depreciation", "sbc", "capex"]])
        drv_rows.append(df[["date_key", "scenario_key", "total_mau_m", "cloud_customers",
                            "cloud_arpu_annual", "device_units", "marketing_spend",
                            "gross_logo_adds", "churn_rate", "compute_units",
                            "infra_unit_cost"]])

    pd.concat(pl_rows, ignore_index=True).to_sql("fact_pl", con, if_exists="append", index=False)
    pd.concat(bs_rows, ignore_index=True).to_sql("fact_balance_sheet", con, if_exists="append", index=False)
    pd.concat(cf_rows, ignore_index=True).to_sql("fact_cash_flow", con, if_exists="append", index=False)
    pd.concat(drv_rows, ignore_index=True).to_sql("fact_drivers", con, if_exists="append", index=False)

    # fact_revenue (long over geos)
    rev_rows = []
    for code, df in frames.items():
        df = with_keys(df, code)
        for g in A.GEOS:
            sub = df[["date_key", "scenario_key", f"mau_{g}", f"arpu_{g}",
                      f"fx_{g}", f"adsrev_{g}"]].copy()
            sub.columns = ["date_key", "scenario_key", "mau_millions", "arpu",
                           "fx_rate", "ads_revenue"]
            sub["geo_key"] = geo_key[g]
            rev_rows.append(sub)
    pd.concat(rev_rows, ignore_index=True).to_sql("fact_revenue", con, if_exists="append", index=False)

    # headcount facts (long over functions)
    hc_rows = []
    for code, df in frames.items():
        df = with_keys(df, code)
        for f in A.FUNCTIONS:
            sub = df[["date_key", "scenario_key", f"hc_{f}", f"comp_{f}"]].copy()
            sub.columns = ["date_key", "scenario_key", "headcount", "cash_comp"]
            sub["function_key"] = func_key[f]
            sub["sbc"] = sub["cash_comp"] * A.SBC_PCT[f]
            hc_rows.append(sub)
    pd.concat(hc_rows, ignore_index=True).to_sql("fact_headcount", con, if_exists="append", index=False)

    con.commit()
    con.close()
    print(f"Warehouse built -> {DB}")
    print(f"Scenarios loaded: {list(frames.keys())}")


if __name__ == "__main__":
    build()
