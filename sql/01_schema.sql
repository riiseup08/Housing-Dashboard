-- ============================================================
-- Canadian Housing Affordability — Star Schema DDL
-- Database: DuckDB
-- ============================================================
-- Run order: 01_schema.sql → 02_load_and_transform.sql → 03_analytical_queries.sql

-- ── Drop existing tables (idempotent) ───────────────────────
DROP TABLE IF EXISTS fact_housing_prices;
DROP TABLE IF EXISTS fact_housing_starts;
DROP TABLE IF EXISTS fact_interest_rates;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_geography;
DROP TABLE IF EXISTS stg_nhpi;
DROP TABLE IF EXISTS stg_boc_rates;
DROP TABLE IF EXISTS stg_housing_starts;


-- ============================================================
-- DIMENSION: dim_date
-- Grain: one row per calendar date
-- Generated from a date spine covering 2000-01-01 → 2030-12-31
-- ============================================================
CREATE TABLE dim_date AS
SELECT
    CAST(strftime(d, '%Y%m%d') AS INTEGER)    AS date_key,       -- surrogate key: YYYYMMDD
    d                                          AS full_date,
    EXTRACT(YEAR FROM d)                       AS year,
    EXTRACT(QUARTER FROM d)                    AS quarter,
    EXTRACT(MONTH FROM d)                      AS month,
    strftime(d, '%B')                          AS month_name,     -- "January", "February" …
    strftime(d, '%b')                          AS month_abbrev,   -- "Jan", "Feb" …
    EXTRACT(DOY FROM d)                        AS day_of_year,
    CASE WHEN EXTRACT(DAY FROM d) = 1
         THEN TRUE ELSE FALSE END              AS is_month_start,
    CASE WHEN d = DATE_TRUNC('quarter', d)
         THEN TRUE ELSE FALSE END              AS is_quarter_start,
    -- Fiscal year (Apr-Mar, common in Canadian government)
    CASE WHEN EXTRACT(MONTH FROM d) >= 4
         THEN EXTRACT(YEAR FROM d)
         ELSE EXTRACT(YEAR FROM d) - 1 END     AS fiscal_year
FROM (
    SELECT UNNEST(
        GENERATE_SERIES(DATE '2000-01-01', DATE '2030-12-31', INTERVAL '1 day')
    )::DATE AS d
);

ALTER TABLE dim_date ADD PRIMARY KEY (date_key);


-- ============================================================
-- DIMENSION: dim_geography
-- Grain: one row per unique geographic region
-- Populated during the transform step from source data
-- ============================================================
CREATE TABLE dim_geography (
    geo_key      INTEGER PRIMARY KEY,       -- auto-assigned surrogate
    geo_name     VARCHAR NOT NULL,           -- e.g. "Toronto, Ontario"
    province     VARCHAR,                    -- e.g. "Ontario"
    geo_code     VARCHAR,                    -- DGUID identifier
    geo_type     VARCHAR                     -- "CMA" | "Province" | "Canada"
);


-- ============================================================
-- FACT: fact_housing_prices
-- Grain: one row per (month, geography, NHPI type)
-- Source: Statistics Canada Table 18-10-0205
-- ============================================================
CREATE TABLE fact_housing_prices (
    date_key          INTEGER NOT NULL REFERENCES dim_date(date_key),
    geo_key           INTEGER NOT NULL REFERENCES dim_geography(geo_key),
    nhpi_type         VARCHAR NOT NULL,     -- "Total (house and land)" | "House only" | "Land only"
    index_value       DOUBLE,               -- NHPI reading (base 201612=100)
    yoy_change_pct    DOUBLE,               -- year-over-year % change (calculated)
    mom_change_pct    DOUBLE                -- month-over-month % change (calculated)
);


-- ============================================================
-- FACT: fact_housing_starts
-- Grain: one row per (date, geography, housing type)
-- Source: CMHC via Statistics Canada Table 34-10-0135
-- ============================================================
CREATE TABLE fact_housing_starts (
    date_key          INTEGER NOT NULL REFERENCES dim_date(date_key),
    geo_key           INTEGER NOT NULL REFERENCES dim_geography(geo_key),
    housing_type      VARCHAR NOT NULL,     -- "Single" | "Multiple" | "All types" etc.
    starts_count      DOUBLE,               -- number of units started
    rolling_12m_avg   DOUBLE                -- 12-month rolling average (calculated)
);


-- ============================================================
-- FACT: fact_interest_rates
-- Grain: one row per date (Bank of Canada rate observation)
-- Source: Bank of Canada Valet API
-- ============================================================
CREATE TABLE fact_interest_rates (
    date_key          INTEGER NOT NULL REFERENCES dim_date(date_key),
    bank_rate         DOUBLE,               -- Bank Rate (upper bound)
    overnight_target  DOUBLE,               -- Target overnight rate
    rate_change       DOUBLE                -- basis-point change from previous observation
);


-- Confirm creation
SELECT table_name
FROM   information_schema.tables
WHERE  table_schema = 'main'
ORDER  BY table_name;
