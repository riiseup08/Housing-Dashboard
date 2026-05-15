-- ============================================================
-- Canadian Housing Affordability — Analytical Queries
-- Portfolio showcase: CTEs, window functions, complex joins
-- ============================================================
-- These queries run against the star schema in DuckDB.
-- Each query is self-contained and well-commented for GitHub.


-- ────────────────────────────────────────────────────────────
-- QUERY 1: Year-over-year price change ranked by city
-- Skills: CTE, RANK() window function, filtering, formatting
-- Question: Which cities had the biggest price swings?
-- ────────────────────────────────────────────────────────────
WITH latest_year AS (
    SELECT
        dg.geo_name,
        dg.province,
        dd.year,
        ROUND(AVG(f.index_value), 1)     AS avg_index,
        ROUND(AVG(f.yoy_change_pct), 2)  AS avg_yoy_pct
    FROM fact_housing_prices f
    JOIN dim_date dd      ON dd.date_key = f.date_key
    JOIN dim_geography dg ON dg.geo_key  = f.geo_key
    WHERE f.nhpi_type = 'Total (house and land)'
      AND dg.geo_type = 'CMA'
      AND dd.year = (SELECT MAX(year) FROM dim_date d2
                     JOIN fact_housing_prices f2 ON d2.date_key = f2.date_key)
    GROUP BY dg.geo_name, dg.province, dd.year
)
SELECT
    geo_name,
    province,
    avg_index,
    avg_yoy_pct,
    RANK() OVER (ORDER BY avg_yoy_pct DESC) AS rank_fastest_growing,
    RANK() OVER (ORDER BY avg_yoy_pct ASC)  AS rank_fastest_cooling
FROM latest_year
ORDER BY avg_yoy_pct DESC;


-- ────────────────────────────────────────────────────────────
-- QUERY 2: Housing affordability ratio over time
-- Skills: multi-table CTE chain, date arithmetic, CASE
-- Question: How do price trends relate to interest rates?
-- ────────────────────────────────────────────────────────────
WITH monthly_national_prices AS (
    -- National average NHPI per month
    SELECT
        dd.year,
        dd.month,
        dd.full_date,
        AVG(f.index_value) AS national_nhpi
    FROM fact_housing_prices f
    JOIN dim_date dd      ON dd.date_key = f.date_key
    JOIN dim_geography dg ON dg.geo_key  = f.geo_key
    WHERE dg.geo_name = 'Canada'
      AND f.nhpi_type = 'Total (house and land)'
      AND dd.is_month_start = TRUE
    GROUP BY dd.year, dd.month, dd.full_date
),
monthly_rates AS (
    -- Average BoC rate per month
    SELECT
        dd.year,
        dd.month,
        ROUND(AVG(r.bank_rate), 2)        AS avg_bank_rate,
        ROUND(AVG(r.overnight_target), 2) AS avg_overnight
    FROM fact_interest_rates r
    JOIN dim_date dd ON dd.date_key = r.date_key
    GROUP BY dd.year, dd.month
)
SELECT
    p.year,
    p.month,
    p.full_date,
    ROUND(p.national_nhpi, 1)    AS nhpi,
    r.avg_bank_rate,
    r.avg_overnight,
    -- Rate environment classification
    CASE
        WHEN r.avg_bank_rate >= 4.0 THEN 'High rate (>=4%)'
        WHEN r.avg_bank_rate >= 2.0 THEN 'Moderate (2-4%)'
        WHEN r.avg_bank_rate >= 0.5 THEN 'Low (0.5-2%)'
        ELSE 'Near-zero (<0.5%)'
    END AS rate_environment,
    -- Price momentum
    ROUND(p.national_nhpi - LAG(p.national_nhpi, 12)
        OVER (ORDER BY p.year, p.month), 1) AS nhpi_12m_change
FROM monthly_national_prices p
LEFT JOIN monthly_rates r
    ON p.year = r.year AND p.month = r.month
ORDER BY p.year, p.month;


-- ────────────────────────────────────────────────────────────
-- QUERY 3: Provincial housing starts composition
-- Skills: PIVOT-style aggregation, CASE expressions, %
-- Question: What's the mix of housing types by province?
-- ────────────────────────────────────────────────────────────
WITH provincial_starts AS (
    SELECT
        dg.province,
        f.housing_type,
        SUM(f.starts_count) AS total_starts
    FROM fact_housing_starts f
    JOIN dim_date dd      ON dd.date_key = f.date_key
    JOIN dim_geography dg ON dg.geo_key  = f.geo_key
    WHERE dg.geo_type = 'Province'
      AND dd.year >= 2020
    GROUP BY dg.province, f.housing_type
),
province_totals AS (
    SELECT
        province,
        SUM(total_starts) AS grand_total
    FROM provincial_starts
    GROUP BY province
)
SELECT
    ps.province,
    ps.housing_type,
    ROUND(ps.total_starts, 0) AS units_started,
    ROUND(ps.total_starts / pt.grand_total * 100, 1) AS pct_of_province,
    -- Visual bar (text-based sparkline for GitHub display)
    REPEAT('█', CAST(ps.total_starts / pt.grand_total * 20 AS INTEGER)) AS bar
FROM provincial_starts ps
JOIN province_totals pt ON pt.province = ps.province
WHERE pt.grand_total > 0
ORDER BY ps.province, ps.total_starts DESC;


-- ────────────────────────────────────────────────────────────
-- QUERY 4: Rate hike impact analysis
-- Skills: LEAD/LAG across tables, conditional aggregation
-- Question: What happened to prices 6 & 12 months after
--           each BoC rate hike?
-- ────────────────────────────────────────────────────────────
WITH rate_changes AS (
    -- Identify dates where the rate increased
    SELECT
        dd.full_date    AS hike_date,
        r.bank_rate     AS new_rate,
        LAG(r.bank_rate) OVER (ORDER BY dd.full_date) AS old_rate,
        r.rate_change   AS bps_change
    FROM fact_interest_rates r
    JOIN dim_date dd ON dd.date_key = r.date_key
    WHERE r.rate_change > 0
),
hike_events AS (
    SELECT
        hike_date,
        old_rate,
        new_rate,
        bps_change,
        -- Find corresponding NHPI at hike date, +6m, +12m
        hike_date + INTERVAL '6 months'  AS plus_6m_date,
        hike_date + INTERVAL '12 months' AS plus_12m_date
    FROM rate_changes
),
price_at_hike AS (
    SELECT
        h.hike_date,
        h.old_rate,
        h.new_rate,
        h.bps_change,
        p_now.index_value  AS nhpi_at_hike,
        p_6m.index_value   AS nhpi_6m_later,
        p_12m.index_value  AS nhpi_12m_later
    FROM hike_events h
    -- NHPI at hike month (national, total)
    LEFT JOIN fact_housing_prices p_now
        ON p_now.date_key = CAST(strftime(DATE_TRUNC('month', h.hike_date), '%Y%m%d') AS INTEGER)
       AND p_now.geo_key  = (SELECT geo_key FROM dim_geography WHERE geo_name = 'Canada' LIMIT 1)
       AND p_now.nhpi_type = 'Total (house and land)'
    -- NHPI 6 months later
    LEFT JOIN fact_housing_prices p_6m
        ON p_6m.date_key = CAST(strftime(DATE_TRUNC('month', h.plus_6m_date), '%Y%m%d') AS INTEGER)
       AND p_6m.geo_key  = p_now.geo_key
       AND p_6m.nhpi_type = 'Total (house and land)'
    -- NHPI 12 months later
    LEFT JOIN fact_housing_prices p_12m
        ON p_12m.date_key = CAST(strftime(DATE_TRUNC('month', h.plus_12m_date), '%Y%m%d') AS INTEGER)
       AND p_12m.geo_key  = p_now.geo_key
       AND p_12m.nhpi_type = 'Total (house and land)'
)
SELECT
    hike_date,
    old_rate || '% → ' || new_rate || '%' AS rate_move,
    bps_change || ' bps'                  AS magnitude,
    ROUND(nhpi_at_hike, 1)                AS nhpi_at_hike,
    ROUND(nhpi_6m_later, 1)               AS nhpi_6m_later,
    ROUND(nhpi_12m_later, 1)              AS nhpi_12m_later,
    -- % change after 6 and 12 months
    ROUND((nhpi_6m_later - nhpi_at_hike) / NULLIF(nhpi_at_hike, 0) * 100, 2)
        AS pct_chg_6m,
    ROUND((nhpi_12m_later - nhpi_at_hike) / NULLIF(nhpi_at_hike, 0) * 100, 2)
        AS pct_chg_12m
FROM price_at_hike
WHERE nhpi_at_hike IS NOT NULL
ORDER BY hike_date;


-- ────────────────────────────────────────────────────────────
-- QUERY 5: City tier classification (percentile-based)
-- Skills: NTILE, CASE, subquery, percentile analysis
-- Question: Which cities are in the top/bottom price tiers?
-- ────────────────────────────────────────────────────────────
WITH city_latest AS (
    SELECT
        dg.geo_name,
        dg.province,
        MAX(f.index_value) AS latest_nhpi,
        MAX(f.yoy_change_pct) AS latest_yoy
    FROM fact_housing_prices f
    JOIN dim_date dd      ON dd.date_key = f.date_key
    JOIN dim_geography dg ON dg.geo_key  = f.geo_key
    WHERE f.nhpi_type = 'Total (house and land)'
      AND dg.geo_type = 'CMA'
      AND dd.year = (SELECT MAX(year) FROM dim_date d2
                     JOIN fact_housing_prices f2 ON d2.date_key = f2.date_key)
    GROUP BY dg.geo_name, dg.province
),
tiered AS (
    SELECT
        geo_name,
        province,
        ROUND(latest_nhpi, 1) AS nhpi,
        ROUND(latest_yoy, 2) AS yoy_pct,
        NTILE(4) OVER (ORDER BY latest_nhpi) AS price_quartile,
        NTILE(4) OVER (ORDER BY latest_yoy) AS growth_quartile
    FROM city_latest
)
SELECT
    geo_name,
    province,
    nhpi,
    yoy_pct,
    CASE price_quartile
        WHEN 4 THEN 'Premium'
        WHEN 3 THEN 'Above average'
        WHEN 2 THEN 'Below average'
        WHEN 1 THEN 'Affordable'
    END AS price_tier,
    CASE growth_quartile
        WHEN 4 THEN 'Hot market'
        WHEN 3 THEN 'Warming'
        WHEN 2 THEN 'Cooling'
        WHEN 1 THEN 'Cold market'
    END AS growth_tier
FROM tiered
ORDER BY nhpi DESC;


-- ────────────────────────────────────────────────────────────
-- QUERY 6: Rolling correlation — rates vs prices
-- Skills: window frames, statistical functions, advanced CTE
-- Question: How tightly do interest rates predict price moves?
-- ────────────────────────────────────────────────────────────
WITH monthly_series AS (
    SELECT
        dd.year,
        dd.month,
        dd.full_date,
        -- National NHPI
        AVG(CASE WHEN dg.geo_name = 'Canada'
                  AND f.nhpi_type = 'Total (house and land)'
             THEN f.index_value END) AS nhpi
    FROM fact_housing_prices f
    JOIN dim_date dd      ON dd.date_key = f.date_key
    JOIN dim_geography dg ON dg.geo_key  = f.geo_key
    WHERE dd.is_month_start = TRUE
    GROUP BY dd.year, dd.month, dd.full_date
),
with_rates AS (
    SELECT
        ms.year,
        ms.month,
        ms.full_date,
        ms.nhpi,
        r.avg_rate
    FROM monthly_series ms
    LEFT JOIN (
        SELECT dd.year, dd.month, AVG(ir.bank_rate) AS avg_rate
        FROM fact_interest_rates ir
        JOIN dim_date dd ON dd.date_key = ir.date_key
        GROUP BY dd.year, dd.month
    ) r ON r.year = ms.year AND r.month = ms.month
    WHERE ms.nhpi IS NOT NULL AND r.avg_rate IS NOT NULL
)
SELECT
    year,
    month,
    full_date,
    ROUND(nhpi, 1) AS nhpi,
    ROUND(avg_rate, 2) AS bank_rate,
    -- 12-month rolling correlation (Pearson)
    ROUND(
        CORR(nhpi, avg_rate) OVER (
            ORDER BY year, month
            ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
        )
    , 3) AS rolling_12m_correlation,
    -- 24-month rolling correlation
    ROUND(
        CORR(nhpi, avg_rate) OVER (
            ORDER BY year, month
            ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        )
    , 3) AS rolling_24m_correlation
FROM with_rates
ORDER BY year, month;


-- ────────────────────────────────────────────────────────────
-- QUERY 7: Land vs house price divergence
-- Skills: PIVOT via conditional aggregation, ratio analysis
-- Question: Are land prices growing faster than house prices?
-- ────────────────────────────────────────────────────────────
WITH pivoted AS (
    SELECT
        dd.year,
        dg.geo_name,
        dg.province,
        AVG(CASE WHEN f.nhpi_type = 'House only'
             THEN f.index_value END)                AS house_index,
        AVG(CASE WHEN f.nhpi_type = 'Land only'
             THEN f.index_value END)                AS land_index,
        AVG(CASE WHEN f.nhpi_type = 'Total (house and land)'
             THEN f.index_value END)                AS total_index
    FROM fact_housing_prices f
    JOIN dim_date dd      ON dd.date_key = f.date_key
    JOIN dim_geography dg ON dg.geo_key  = f.geo_key
    WHERE dg.geo_type = 'CMA'
    GROUP BY dd.year, dg.geo_name, dg.province
)
SELECT
    year,
    geo_name,
    province,
    ROUND(house_index, 1) AS house_idx,
    ROUND(land_index, 1)  AS land_idx,
    ROUND(total_index, 1) AS total_idx,
    -- Land-to-house ratio (>1 means land growing faster)
    ROUND(land_index / NULLIF(house_index, 0), 3) AS land_house_ratio,
    -- Year-over-year change in the ratio
    ROUND(
        (land_index / NULLIF(house_index, 0))
        - LAG(land_index / NULLIF(house_index, 0))
            OVER (PARTITION BY geo_name ORDER BY year)
    , 3) AS ratio_yoy_change
FROM pivoted
WHERE house_index IS NOT NULL AND land_index IS NOT NULL
ORDER BY year DESC, geo_name;


-- ────────────────────────────────────────────────────────────
-- QUERY 8: Executive summary — dashboard-ready KPIs
-- Skills: UNION ALL, conditional aggregation, date functions
-- Question: What are the headline numbers right now?
-- ────────────────────────────────────────────────────────────
WITH latest_month AS (
    SELECT MAX(dd.full_date) AS max_date
    FROM fact_housing_prices f
    JOIN dim_date dd ON dd.date_key = f.date_key
)
SELECT 'National NHPI (latest)' AS metric,
       ROUND(AVG(f.index_value), 1)::VARCHAR AS value
FROM fact_housing_prices f
JOIN dim_date dd      ON dd.date_key = f.date_key
JOIN dim_geography dg ON dg.geo_key  = f.geo_key
CROSS JOIN latest_month lm
WHERE dd.full_date = lm.max_date
  AND dg.geo_name = 'Canada'
  AND f.nhpi_type = 'Total (house and land)'

UNION ALL

SELECT 'National YoY change',
       ROUND(AVG(f.yoy_change_pct), 2) || '%'
FROM fact_housing_prices f
JOIN dim_date dd      ON dd.date_key = f.date_key
JOIN dim_geography dg ON dg.geo_key  = f.geo_key
CROSS JOIN latest_month lm
WHERE dd.full_date = lm.max_date
  AND dg.geo_name = 'Canada'
  AND f.nhpi_type = 'Total (house and land)'

UNION ALL

SELECT 'Current Bank Rate',
       ROUND(r.bank_rate, 2) || '%'
FROM fact_interest_rates r
JOIN dim_date dd ON dd.date_key = r.date_key
ORDER BY dd.full_date DESC
LIMIT 1

UNION ALL

SELECT 'Cities tracked',
       COUNT(DISTINCT geo_name)::VARCHAR
FROM dim_geography
WHERE geo_type = 'CMA';
