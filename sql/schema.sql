-- =====================================================================
-- HELIOS FP&A WAREHOUSE  -- dimensional (star) schema
-- =====================================================================
-- Why a star schema rather than strict 3NF: this is an analytical / FP&A
-- workload (slice P&L by segment x geo x scenario x period). A Kimball-style
-- dimensional model is the industry-standard choice for BI/FP&A marts -- it
-- keeps facts additive and joins shallow, which is exactly what dashboards and
-- variance queries need. Operational 3NF would be correct for a transactional
-- source system; this is the gold layer that source feeds into.
-- Types are kept generic so the same DDL runs on SQLite (portable demo) and
-- Postgres (production).
-- =====================================================================

DROP TABLE IF EXISTS fact_pl;
DROP TABLE IF EXISTS fact_revenue;
DROP TABLE IF EXISTS fact_headcount;
DROP TABLE IF EXISTS fact_balance_sheet;
DROP TABLE IF EXISTS fact_cash_flow;
DROP TABLE IF EXISTS fact_drivers;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_geo;
DROP TABLE IF EXISTS dim_function;
DROP TABLE IF EXISTS dim_segment;
DROP TABLE IF EXISTS dim_scenario;
DROP TABLE IF EXISTS dim_account;

-- ---------------------- DIMENSIONS ----------------------
CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,   -- yyyymmdd
    date          TEXT NOT NULL,
    year          INTEGER NOT NULL,
    quarter       TEXT NOT NULL,         -- e.g. 2024-Q3
    month         INTEGER NOT NULL,
    fiscal_period TEXT NOT NULL
);

CREATE TABLE dim_geo (
    geo_key   INTEGER PRIMARY KEY,
    geo_code  TEXT NOT NULL UNIQUE,      -- NA, EU, APAC, LATAM, ROW
    geo_name  TEXT NOT NULL,
    region    TEXT
);

CREATE TABLE dim_function (
    function_key  INTEGER PRIMARY KEY,
    function_code TEXT NOT NULL UNIQUE,  -- Engineering, Research, ...
    cost_center   TEXT
);

CREATE TABLE dim_segment (
    segment_key  INTEGER PRIMARY KEY,
    segment_code TEXT NOT NULL UNIQUE,   -- Platform, Frontier
    description  TEXT
);

CREATE TABLE dim_scenario (
    scenario_key  INTEGER PRIMARY KEY,
    scenario_code TEXT NOT NULL UNIQUE,  -- base_plan, actual, hiring_freeze, ...
    scenario_type TEXT NOT NULL,         -- plan | actual | scenario
    description   TEXT
);

CREATE TABLE dim_account (
    account_key  INTEGER PRIMARY KEY,
    account_code TEXT NOT NULL UNIQUE,   -- revenue, cogs, rnd_expense, ...
    statement    TEXT NOT NULL,          -- PL | BS | CF
    line_group   TEXT,                   -- Revenue, OpEx, Assets, ...
    sign         INTEGER DEFAULT 1       -- +1 inflow / -1 outflow for display
);

-- ---------------------- FACTS ----------------------
-- Grain: one row per date x scenario x account (long/tidy "ledger" of the P&L)
CREATE TABLE fact_pl (
    date_key     INTEGER NOT NULL REFERENCES dim_date(date_key),
    scenario_key INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    segment_key  INTEGER          REFERENCES dim_segment(segment_key),
    account_key  INTEGER NOT NULL REFERENCES dim_account(account_key),
    amount       REAL NOT NULL
);
CREATE INDEX ix_pl ON fact_pl(date_key, scenario_key, account_key);

-- Grain: one row per date x scenario x geo  (revenue + usage drivers)
CREATE TABLE fact_revenue (
    date_key      INTEGER NOT NULL REFERENCES dim_date(date_key),
    scenario_key  INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    geo_key       INTEGER NOT NULL REFERENCES dim_geo(geo_key),
    mau_millions  REAL,
    arpu          REAL,
    fx_rate       REAL,
    ads_revenue   REAL
);

-- Grain: one row per date x scenario x function
CREATE TABLE fact_headcount (
    date_key      INTEGER NOT NULL REFERENCES dim_date(date_key),
    scenario_key  INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    function_key  INTEGER NOT NULL REFERENCES dim_function(function_key),
    headcount     REAL,
    cash_comp     REAL,
    sbc           REAL
);

-- Grain: one row per date x scenario
CREATE TABLE fact_balance_sheet (
    date_key            INTEGER NOT NULL REFERENCES dim_date(date_key),
    scenario_key        INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    cash                REAL, accounts_receivable REAL, ppe_net REAL,
    other_assets        REAL, total_assets REAL,
    accounts_payable    REAL, deferred_revenue REAL, total_liabilities REAL,
    retained_earnings   REAL, paid_in_capital REAL, total_equity REAL,
    balance_check       REAL
);

CREATE TABLE fact_cash_flow (
    date_key      INTEGER NOT NULL REFERENCES dim_date(date_key),
    scenario_key  INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    cfo REAL, cfi REAL, cff REAL, net_change_in_cash REAL,
    depreciation REAL, sbc REAL, capex REAL
);

-- Grain: one row per date x scenario  (model drivers for forecasting/ML)
CREATE TABLE fact_drivers (
    date_key        INTEGER NOT NULL REFERENCES dim_date(date_key),
    scenario_key    INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    total_mau_m     REAL, cloud_customers REAL, cloud_arpu_annual REAL,
    device_units    REAL, marketing_spend REAL, gross_logo_adds REAL,
    churn_rate      REAL, compute_units REAL, infra_unit_cost REAL
);
