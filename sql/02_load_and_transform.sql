-- ============================================================
-- Canadian Housing Affordability — Load & Transform
-- Reads cleaned CSVs → stages → populates star schema
-- ============================================================
-- Prerequisite: run 01_schema.sql first
-- CSV paths are relative — run from the project root


-- ════════════════════════════════════════════════════════════
-- STEP 1: Load CSVs into staging tables
-- ════════════════════════════════════════════════════════════

CREATE OR REPLACE TABLE stg_nhpi AS
SELECT * FROM read_csv_auto('data/processed/nhpi_clean.csv',
    header = true, dateformat = '%Y-%m-%d');

CREATE OR REPLACE TABLE stg_boc_rates AS
SELECT * FROM read_csv_auto('data/processed/boc_rates_clean.csv',
    header = true, dateformat = '%Y-%m-%d');

CREATE OR REPLACE TABLE stg_housing_starts AS
SELECT * FROM read_csv_auto('data/processed/housing_starts_clean.csv',
    header = true, dateformat = '%Y-%m-%d');


-- Quick row counts to verify loads
SELECT 'stg_nhpi' AS source, COUNT(*) AS rows FROM stg_nhpi
UNION ALL
SELECT 'stg_boc_rates', COUNT(*) FROM stg_boc_rates
UNION ALL
SELECT 'stg_housing_starts', COUNT(*) FROM stg_housing_starts;


-- ════════════════════════════════════════════════════════════
-- STEP 2: Populate dim_geography
-- Merge unique geographies from NHPI and housing starts
-- ════════════════════════════════════════════════════════════

DELETE FROM dim_geography;

INSERT INTO dim_geography (geo_key, geo_name, province, geo_code, geo_type)
WITH all_geos AS (
    SELECT DISTINCT
        geo        AS geo_name,
        geo_code
    FROM stg_nhpi
    UNION
    SELECT DISTINCT
        geo        AS geo_name,
        geo_code
    FROM stg_housing_starts
),
enriched AS (
    SELECT
        geo_name,
        geo_code,
        -- Extract province from "City, Province" format
        CASE
            WHEN geo_name = 'Canada' THEN NULL
            WHEN POSITION(',' IN geo_name) > 0
                THEN TRIM(SPLIT_PART(geo_name, ',', 2))
            ELSE geo_name
        END AS province,
        -- Classify geography type
        CASE
            WHEN geo_name = 'Canada' THEN 'Canada'
            WHEN POSITION(',' IN geo_name) > 0 THEN 'CMA'
            ELSE 'Province'
        END AS geo_type
    FROM all_geos
)
SELECT
    ROW_NUMBER() OVER (ORDER BY geo_type, geo_name) AS geo_key,
    geo_name,
    province,
    geo_code,
    geo_type
FROM enriched;

-- Verify
SELECT geo_type, COUNT(*) AS count
FROM dim_geography
GROUP BY geo_type
ORDER BY geo_type;


-- ════════════════════════════════════════════════════════════
-- STEP 3: Populate fact_housing_prices
-- Join to dimensions + compute YoY and MoM changes
-- ════════════════════════════════════════════════════════════

DELETE FROM fact_housing_prices;

INSERT INTO fact_housing_prices
WITH joined AS (
    SELECT
        dd.date_key,
        dg.geo_key,
        s.nhpi_type,
        s.index_value,
        s.date AS full_date
    FROM stg_nhpi s
    JOIN dim_date dd
        ON dd.full_date = s.date::DATE
    JOIN dim_geography dg
        ON dg.geo_name = s.geo
)
SELECT
    date_key,
    geo_key,
    nhpi_type,
    index_value,
    -- Year-over-year % change (same month, prior year)
    ROUND(
        (index_value - LAG(index_value, 12) OVER w)
        / NULLIF(LAG(index_value, 12) OVER w, 0) * 100
    , 2) AS yoy_change_pct,
    -- Month-over-month % change
    ROUND(
        (index_value - LAG(index_value, 1) OVER w)
        / NULLIF(LAG(index_value, 1) OVER w, 0) * 100
    , 2) AS mom_change_pct
FROM joined
WINDOW w AS (PARTITION BY geo_key, nhpi_type ORDER BY date_key);


-- ════════════════════════════════════════════════════════════
-- STEP 4: Populate fact_housing_starts
-- Join to dimensions + compute 12-month rolling average
-- ════════════════════════════════════════════════════════════

DELETE FROM fact_housing_starts;

INSERT INTO fact_housing_starts
WITH joined AS (
    SELECT
        dd.date_key,
        dg.geo_key,
        s.housing_type,
        s.starts_count
    FROM stg_housing_starts s
    JOIN dim_date dd
        ON dd.full_date = s.date::DATE
    JOIN dim_geography dg
        ON dg.geo_name = s.geo
)
SELECT
    date_key,
    geo_key,
    housing_type,
    starts_count,
    -- 12-month rolling average (smooths seasonality)
    ROUND(
        AVG(starts_count) OVER (
            PARTITION BY geo_key, housing_type
            ORDER BY date_key
            ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
        )
    , 1) AS rolling_12m_avg
FROM joined;


-- ════════════════════════════════════════════════════════════
-- STEP 5: Populate fact_interest_rates
-- Join to date dimension + compute rate change
-- ════════════════════════════════════════════════════════════

DELETE FROM fact_interest_rates;

INSERT INTO fact_interest_rates
WITH joined AS (
    SELECT
        dd.date_key,
        s.bank_rate,
        s.overnight_target
    FROM stg_boc_rates s
    JOIN dim_date dd
        ON dd.full_date = s.date::DATE
)
SELECT
    date_key,
    bank_rate,
    overnight_target,
    -- Basis-point change from previous observation
    ROUND(
        (bank_rate - LAG(bank_rate) OVER (ORDER BY date_key)) * 100
    , 0) AS rate_change
FROM joined;


-- ════════════════════════════════════════════════════════════
-- STEP 6: Validation summary
-- ════════════════════════════════════════════════════════════

SELECT '--- WAREHOUSE SUMMARY ---' AS info;

SELECT 'dim_date' AS table_name, COUNT(*) AS rows FROM dim_date
UNION ALL
SELECT 'dim_geography', COUNT(*) FROM dim_geography
UNION ALL
SELECT 'fact_housing_prices', COUNT(*) FROM fact_housing_prices
UNION ALL
SELECT 'fact_housing_starts', COUNT(*) FROM fact_housing_starts
UNION ALL
SELECT 'fact_interest_rates', COUNT(*) FROM fact_interest_rates;

-- Verify referential integrity
SELECT 'Orphan price rows (no date match)' AS check_name,
       COUNT(*) AS issues
FROM fact_housing_prices f
WHERE NOT EXISTS (SELECT 1 FROM dim_date d WHERE d.date_key = f.date_key)
UNION ALL
SELECT 'Orphan price rows (no geo match)',
       COUNT(*)
FROM fact_housing_prices f
WHERE NOT EXISTS (SELECT 1 FROM dim_geography g WHERE g.geo_key = f.geo_key)
UNION ALL
SELECT 'Orphan starts rows (no date match)',
       COUNT(*)
FROM fact_housing_starts f
WHERE NOT EXISTS (SELECT 1 FROM dim_date d WHERE d.date_key = f.date_key)
UNION ALL
SELECT 'Orphan rate rows (no date match)',
       COUNT(*)
FROM fact_interest_rates f
WHERE NOT EXISTS (SELECT 1 FROM dim_date d WHERE d.date_key = f.date_key);
