# DuckDB Query Guide

## Overview

The pipeline loads data into a DuckDB star schema with 5 tables:
- **dim_date** (11,323 rows) - Date dimension covering 2000-2030
- **dim_geography** (42 rows) - Provinces and Census Metropolitan Areas (CMAs)
- **fact_housing_prices** (34,146 rows) - New Housing Price Index (NHPI) data
- **fact_housing_starts** (19,674 rows) - Monthly housing construction starts
- **fact_interest_rates** (4,445 rows) - Bank of Canada rates

Database file: `data/housing.duckdb`

## Loading Data

Run the pipeline with the `--load-db` flag to extract CSVs and load them into DuckDB:

```powershell
python run_pipeline.py --load-db
```

This will:
1. Extract data from all 3 sources (Stats Canada NHPI, Bank of Canada, CMHC)
2. Clean and validate the data
3. Save CSVs to `data/processed/`
4. Execute SQL scripts to create star schema
5. Load and transform data into DuckDB tables

## Querying the Database

### Using the Query Tool

The `query_db.py` utility provides several ways to interact with the database:

**List all tables:**
```powershell
python query_db.py --list
```

**Describe a table (schema + sample data):**
```powershell
python query_db.py --table dim_geography
python query_db.py --table fact_housing_prices
```

**Run pre-built analytical queries:**
```powershell
# Query 1: Recent housing price trends (last 12 months)
python query_db.py --query 1

# Query 2: Interest rates vs housing prices
python query_db.py --query 2

# Query 3: Top 5 cities by housing starts
python query_db.py --query 3

# Query 4: Provincial housing price growth YoY
python query_db.py --query 4

# Query 5: Interest rate impact on housing starts
python query_db.py --query 5
```

**Execute custom SQL:**
```powershell
python query_db.py --sql "SELECT * FROM dim_date WHERE year = 2025 LIMIT 5"
python query_db.py --sql "SELECT geo_name, geo_type FROM dim_geography ORDER BY geo_name"
```

### Pre-Built Queries

#### Query 1: Recent Housing Price Trends
Shows monthly NHPI values and year-over-year/month-over-month changes for major cities over the last 12 months.

**Example output:**
```
year_month                    geo_name  index_value  yoy_change_pct  mom_change_pct
   2026-03                      Canada        121.6           -2.33           -0.25
   2026-03            Montréal, Quebec        159.0            3.31            0.13
   2026-03            Toronto, Ontario        107.1           -4.88           -0.93
   2026-03 Vancouver, British Columbia        124.6           -2.50           -0.32
```

#### Query 2: Interest Rates vs Housing Prices
Correlates Bank of Canada rates with national housing price changes on a monthly basis since 2020.

#### Query 3: Top 5 Cities by Housing Starts
Ranks CMAs by total housing starts in the last year, showing construction activity.

#### Query 4: Provincial Housing Price Growth
Shows the latest housing price index and annual growth rate for each province.

#### Query 5: Interest Rate Impact on Housing Starts
Aggregates by year to show the relationship between average interest rates, housing starts, and price changes.

## Schema Details

### Dimensions

**dim_date:**
- `date_key` (PK): YYYYMMDD integer
- `full_date`: Date value
- `year`, `quarter`, `month`: Date components
- `month_name`, `month_abbrev`: Month labels
- `is_month_start`, `is_quarter_start`: Boolean flags
- `fiscal_year`: Canadian fiscal year (Apr-Mar)

**dim_geography:**
- `geo_key` (PK): Surrogate key
- `geo_name`: "Canada", "Ontario", "Toronto, Ontario", etc.
- `geo_type`: "Country", "Province", or "CMA"
- `province`: Province name (for CMAs)

### Facts

**fact_housing_prices:**
- `date_key` (FK to dim_date)
- `geo_key` (FK to dim_geography)
- `nhpi_type`: "Total (house and land)", "House only", or "Land only"
- `index_value`: NHPI (2016=100 baseline)
- `yoy_change_pct`: Year-over-year % change
- `mom_change_pct`: Month-over-month % change

**fact_housing_starts:**
- `date_key` (FK to dim_date)
- `geo_key` (FK to dim_geography)
- `housing_type`: "Single" or "Multiple"
- `housing_starts`: Number of units
- `yoy_change_pct`: Year-over-year % change

**fact_interest_rates:**
- `date_key` (FK to dim_date)
- `bank_rate`: Bank of Canada rate (%)
- `overnight_target`: Overnight target rate (%)
- `rate_diff`: Difference between rates

## Example Queries

### Find cities with highest price growth
```sql
SELECT 
    g.geo_name,
    ROUND(AVG(hp.yoy_change_pct), 2) as avg_yoy_growth
FROM fact_housing_prices hp
JOIN dim_geography g ON hp.geo_key = g.geo_key
JOIN dim_date d ON hp.date_key = d.date_key
WHERE g.geo_type = 'CMA' 
  AND d.year = 2025
  AND hp.nhpi_type = 'Total (house and land)'
GROUP BY g.geo_name
ORDER BY avg_yoy_growth DESC
LIMIT 10;
```

### Compare interest rates and housing starts
```sql
SELECT 
    d.year,
    d.month_name,
    AVG(ir.bank_rate) as avg_rate,
    SUM(hs.housing_starts) as total_starts
FROM dim_date d
LEFT JOIN fact_interest_rates ir ON d.date_key = ir.date_key
LEFT JOIN fact_housing_starts hs ON d.date_key = hs.date_key
WHERE d.year >= 2020 AND d.is_month_start = TRUE
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;
```

### Provincial housing prices over time
```sql
SELECT 
    d.year,
    g.geo_name,
    AVG(hp.index_value) as avg_index
FROM fact_housing_prices hp
JOIN dim_geography g ON hp.geo_key = g.geo_key
JOIN dim_date d ON hp.date_key = d.date_key
WHERE g.geo_type = 'Province'
  AND hp.nhpi_type = 'Total (house and land)'
  AND d.is_month_start = TRUE
GROUP BY d.year, g.geo_name
ORDER BY d.year, g.geo_name;
```

## Connecting from Python

```python
import duckdb

# Connect to database
conn = duckdb.connect('data/housing.duckdb', read_only=True)

# Run a query
result = conn.execute("""
    SELECT geo_name, AVG(index_value) as avg_nhpi
    FROM fact_housing_prices hp
    JOIN dim_geography g ON hp.geo_key = g.geo_key
    WHERE g.geo_type = 'Province'
    GROUP BY geo_name
""").fetchdf()

print(result)
conn.close()
```

## Connecting from Other Tools

DuckDB can be accessed from:
- **DBeaver** (supports DuckDB via JDBC driver)
- **DataGrip** (JetBrains IDE with DuckDB support)
- **Jupyter notebooks** (using `duckdb` Python package)
- **R** (using `duckdb` R package)
- **CLI**: `duckdb data/housing.duckdb` (install DuckDB CLI separately)

## Next Steps

After exploring the data, you can:
1. Build a **Streamlit dashboard** to visualize trends (see `docs/` for design ideas)
2. Add more **analytical queries** to `sql/03_analytical_queries.sql`
3. Create **materialized views** for frequently-used aggregations
4. Export results to **Excel/CSV** for reports
5. Set up **scheduled refreshes** of the pipeline
