# Canadian Housing Market Data Pipeline

An automated ETL and analytics project for exploring Canadian housing-market
conditions. It combines housing prices, interest rates, and construction
activity in a DuckDB warehouse and presents them in an interactive Streamlit
dashboard.

> **Scope note:** The current sources describe important *drivers* of housing
> affordability, but they do not measure affordability directly. The New
> Housing Price Index is an index—not a dollar home price—and the warehouse
> does not yet contain household income. A defensible price-to-income or
> mortgage-payment-to-income metric therefore requires additional sources.

## What it includes

- Automated extraction from three authoritative public sources
- Retry logic, timeouts, validation, and strict CI failure gates
- DuckDB star schema with date and geography dimensions
- Year-over-year, month-over-month, and rolling metrics
- Interactive Streamlit dashboard and query CLI
- Weekly scheduled refresh and source-specific freshness checks
- Monthly AI-assisted market digest
- Optional PostgreSQL deployment path

## Data sources

| Publisher | Dataset | Frequency | Role |
|---|---|---:|---|
| Statistics Canada | New Housing Price Index, table 18-10-0205 | Monthly | Price movement |
| Bank of Canada | Valet API policy-rate series | Daily | Financing conditions |
| Statistics Canada / CMHC | Housing starts, table 34-10-0135 | Quarterly | New supply |

The next affordability-focused expansion should add a dollar-denominated home
price or benchmark-price series and a geography-compatible household-income
series. Until then, dashboard labels deliberately refer to market conditions
rather than claiming to calculate household affordability.

## Architecture

```text
Statistics Canada ─┐
Bank of Canada ────┼──> Python extraction and validation
CMHC / StatCan ────┘              │
                                  v
                         Processed CSV files
                                  │
                                  v
                         DuckDB star schema
                           │             │
                           v             v
                    Streamlit app    Insight digest
```

Warehouse tables:

- `dim_date`
- `dim_geography`
- `fact_housing_prices`
- `fact_housing_starts`
- `fact_interest_rates`

Warehouse rebuilds run inside a transaction so a failed transform does not
leave a partially rebuilt schema.

## Quick start

Python 3.11 or 3.12 is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Extract all sources and rebuild DuckDB:

```powershell
python run_pipeline.py --load-db
```

Run one or more sources:

```powershell
python run_pipeline.py --source boc
python run_pipeline.py --source statcan cmhc
```

Use strict mode to fail on extraction errors, validation failures, database
load failures, or stale warehouse data:

```powershell
python run_pipeline.py --load-db --strict
```

Launch the dashboard:

```powershell
streamlit run dashboard.py
```

Run the tests:

```powershell
python -m pytest
python -m pytest -m "not slow"
```

## Project structure

```text
.
├── config.py                 Central configuration and paths
├── run_pipeline.py           Extraction orchestration and validation
├── load_duckdb.py            Transactional warehouse rebuild
├── quality.py                Post-load freshness checks
├── dashboard.py              Streamlit application
├── query_db.py               Query CLI
├── extractors/               Source-specific extraction and cleaning
├── insights/                 Digest queries and generation
├── sql/                      Schema, transforms, and analytical SQL
├── tests/                    Unit and integration tests
├── data/processed/           Versioned clean extracts
└── .github/workflows/        CI, refresh, and digest automation
```

## Configuration

Copy `.env.example` to `.env`. Common settings include:

| Variable | Purpose |
|---|---|
| `PIPELINE_ENV` | Environment name |
| `DATA_RAW` / `DATA_PROCESSED` | Data directories |
| `DB_PATH` | Local DuckDB path |
| `DATABASE_URL` | Optional PostgreSQL connection |
| `DOWNLOAD_TIMEOUT` / `API_TIMEOUT` | Network timeouts |
| `LOG_LEVEL` | Logging verbosity |
| `DEEPSEEK_API_KEY` | Optional digest generation |

The monthly email workflow also expects GitHub Actions secrets named
`GMAIL_USER`, `GMAIL_APP_PASSWORD`, and `DIGEST_RECIPIENT`.

## Data-quality behavior

Extraction outputs are checked for minimum row counts, excessive nulls, and
duplicate rows. Strict mode treats failed output validation as a pipeline
failure. After loading, each dataset is checked against a source-specific
freshness threshold because daily, monthly, and quarterly publications should
not share one blanket threshold.

## Testing and automation

- `ci.yml` runs the fast test suite on every push and pull request.
- `refresh.yml` refreshes data weekly, rebuilds the warehouse, performs strict
  checks, runs tests, generates the digest, and optionally migrates PostgreSQL.
- `monthly_email.yml` sends the latest generated digest using repository
  secrets.

## Known limitations

- NHPI measures relative price movement and cannot be interpreted as a home
  price in dollars.
- Housing-start observations are quarterly and dated at the beginning of the
  quarter.
- Geographic coverage differs across sources.
- The dashboard compares housing starts with the same quarter a year earlier
  and calculates a four-quarter average only when all four quarters are present.
  These calculations include history before the selected display year.
- Historical starts can contain multiple observations for one geography,
  dwelling type, and quarter. The dashboard excludes these ambiguous records
  with a visible warning rather than choosing or summing them. Resolving the
  missing source dimensions in the extractor remains necessary for full history.
- Starts charts use non-overlapping dwelling categories. The overview uses only
  `Total units` across the latest four reported quarters, avoiding double counts.
- Dashboard freshness indicators use the same source-specific limits as CI.
  The warehouse's stored rolling metric and digest are separate from the
  corrected dashboard calculation and still require a follow-up review.
- The current dashboard is a housing-market conditions dashboard; direct
  affordability ratios remain planned work.

## Roadmap

1. Add compatible dollar home-price and household-income sources.
2. Define mortgage-payment-to-income and price-to-income metrics with explicit
   assumptions.
3. Add extractor contract tests and warehouse transformation tests.
4. Publish a methodology page covering revisions, geography matching, and
   source limitations.
