# 🏠 Canadian Housing Affordability Data Pipeline

A comprehensive ETL pipeline and analytics platform for Canadian housing market data, featuring automated data extraction, DuckDB warehousing, and an interactive Streamlit dashboard.

## 🎯 Features

- **Automated Data Extraction** from 3 authoritative sources:
  - Statistics Canada NHPI (New Housing Price Index)
  - Bank of Canada Valet API (Interest Rates)
  - CMHC Housing Starts (via Statistics Canada)
  
- **Production-Ready Pipeline**:
  - Retry logic with exponential backoff
  - Business rule validation
  - Comprehensive error handling
  - Environment-based configuration
  
- **DuckDB Star Schema Warehouse**:
  - Optimized analytical queries
  - Date and geography dimensions
  - Pre-calculated metrics (YoY/MoM changes, rolling averages)
  
- **Interactive Streamlit Dashboard**:
  - Real-time data visualization
  - Comparative analysis across geographies
  - Interest rate correlation analysis

## 📊 Dashboard

Launch the interactive dashboard:

```powershell
streamlit run dashboard.py
```

**Features:**
- 📊 Overview - Key metrics and recent trends
- 📈 Housing Prices - NHPI analysis by geography
- 💰 Interest Rates - Bank of Canada rates over time
- 🏗️ Housing Starts - Construction activity trends
- 🔍 Comparative Analysis - Multi-geography comparison with rate correlations

## Architecture

```
Stats Canada (NHPI)  ─┐
CMHC (Housing Starts) ─┼──▶  Python ETL  ──▶  DuckDB (Star Schema)  ──▶  Streamlit Dashboard
Bank of Canada (Rates) ─┘       extract/         transform/                   serve/
                              clean/load        analytical SQL
```

## Data Sources

| Source | Dataset | Frequency | Format |
|--------|---------|-----------|--------|
| Statistics Canada | New Housing Price Index (Table 18-10-0205) | Monthly | CSV (zip) |
| Bank of Canada | Policy Interest Rate (Valet API) | Daily | JSON/CSV |
| CMHC | Housing Starts by Province | Monthly | CSV |

## Project Structure

```
Canadian Housing Affordability Data Pipeline/
├── config.py                  # Configuration and paths
├── run_pipeline.py            # Main pipeline orchestrator
├── load_duckdb.py            # DuckDB loading module
├── query_db.py               # CLI query tool
├── dashboard.py              # Streamlit dashboard
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
├── .gitignore                # Git exclusions
│
├── extractors/               # Data extraction modules
│   ├── __init__.py
│   ├── extract_statcan.py   # Stats Canada NHPI
│   ├── extract_boc.py       # Bank of Canada rates
│   ├── extract_cmhc.py      # CMHC housing starts
│   ├── utils.py             # Shared HTTP utilities with retry logic
│   └── validators.py        # Business rule validators
│
├── sql/                      # SQL scripts for DuckDB
│   ├── 01_schema.sql        # Star schema DDL
│   ├── 02_load_and_transform.sql  # Data loading and transformations
│   └── 03_analytical_queries.sql  # Pre-built analytical queries
│
├── tests/                    # Test suite (pytest)
│   ├── conftest.py          # Test fixtures
│   └── test_extract_statcan.py
│
├── data/                     # Data storage
│   ├── raw/                 # Downloaded raw files
│   ├── processed/           # Cleaned CSV files
│   ├── housing.duckdb       # DuckDB database
│   └── pipeline.log         # Pipeline logs
│
└── docs/                     # Documentation
    ├── AUDIT_REPORT.md      # Code quality audit
    ├── QUICK_FIXES.md       # Implementation guide
    ├── FIXES_COMPLETED.md   # Change summary
    └── DUCKDB_GUIDE.md      # Database usage guide
```

## 🗄️ Database Schema

**Star Schema** with 5 tables:

### Dimensions
- **dim_date** (11,323 rows) - Date dimension covering 2000-2030
- **dim_geography** (42 rows) - Provinces and CMAs

### Facts
- **fact_housing_prices** (34,146 rows) - NHPI data with YoY/MoM metrics
- **fact_housing_starts** (19,674 rows) - Construction activity
- **fact_interest_rates** (4,445 rows) - Bank of Canada rates

See [DUCKDB_GUIDE.md](DUCKDB_GUIDE.md) for detailed schema documentation and query examples.

## 🚀 Quick Start

### 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 2. Run the Pipeline

**Extract data only:**
```powershell
python run_pipeline.py
```

**Extract and load to DuckDB:**
```powershell
python run_pipeline.py --load-db
```

**Extract specific sources:**
```powershell
## 🔧 Configuration

Create a `.env` file from the template:

```powershell
cp .env.example .env
```

**Key variables:**
- `PIPELINE_ENV` - Environment (development/production)
- `DOWNLOAD_TIMEOUT` - HTTP timeout for downloads
- `DATA_RAW` - Raw data directory
- `DATA_PROCESSED` - Processed data directory
- `DB_PATH` - DuckDB database path
- `LOG_LEVEL` - Logging level (INFO/DEBUG/WARNING)

## 📈 Data Pipeline Flow

```
┌─────────────────┐
│  Data Sources   │
├─────────────────┤
│ Stats Canada    │──┐
│ Bank of Canada  │──┼──> [Extract] ──> [Clean] ──> [Validate] ──> [CSV]
│ CMHC            │──┘                                                │
└─────────────────┘                                                   │
                                                                      ▼
                                                            ┌──────────────────┐
                                                            │   DuckDB Load    │
                                                            ├──────────────────┤
                                                            │ 1. Create Schema │
                                                            │ 2. Load Data     │
                                                            │ 3. Transform     │
                                                            └────────┬─────────┘
                                                                     │
                                    ┌────────────────────────────────┼─────────────────────┐
                                    ▼                                ▼                     ▼
                              ┌──────────┐                    ┌──────────┐         ┌──────────┐
                              │ Query CLI│                    │ Dashboard│         │  Python  │
                              └──────────┘                    └──────────┘         │   API    │
                                                                                    └──────────┘
```

## 🧪 Testing

Run the test suite:

```powershell
# Run all tests
pytest -v

# Run with coverage
pytest --cov=extractors --cov-report=html

# Run specific test file
pytest tests/test_extract_statcan.py -v
```

## 📊 Sample Queries

**Recent housing price trends:**
```sql
SELECT 
    d.year || '-' || LPAD(d.month::VARCHAR, 2, '0') as year_month,
    g.geo_name,
    hp.index_value,
    hp.yoy_change_pct
FROM fact_housing_prices hp
JOIN dim_date d ON hp.date_key = d.date_key
JOIN dim_geography g ON hp.geo_key = g.geo_key
WHERE g.geo_name IN ('Canada', 'Toronto, Ontario', 'Vancouver, British Columbia')
  AND d.year >= 2023
  AND hp.nhpi_type = 'Total (house and land)'
ORDER BY d.full_date;
```

**Interest rate impact analysis:**
```sql
SELECT 
    d.year,
    AVG(ir.bank_rate) as avg_rate,
    AVG(hp.yoy_change_pct) as avg_price_growth
FROM dim_date d
LEFT JOIN fact_interest_rates ir ON d.date_key = ir.date_key
LEFT JOIN fact_housing_prices hp ON d.date_key = hp.date_key
WHERE d.is_month_start = TRUE
GROUP BY d.year
ORDER BY d.year;
```

## 🛡️ Error Handling

The pipeline implements robust error handling:

- **Retry Logic**: 3 attempts with exponential backoff for network requests
- **Data Validation**: Business rules check for anomalies (e.g., negative rates, out-of-range values)
- **Specific Exceptions**: NetworkError, ParseError, ValidationError with recoverable flags
- **Logging**: Comprehensive logs in `data/pipeline.log`

## 📝 Data Sources

- **Statistics Canada Table 18-10-0205**: New Housing Price Index (NHPI)
  - Coverage: 1981-present, monthly
  - Geographies: 10 provinces + 27 CMAs
  - Base year: 2016 = 100

- **Bank of Canada Valet API**: Policy Interest Rates
  - Series: V39079 (Bank Rate), V39078 (Overnight Target)
  - Coverage: 2009-present, daily
  
- **Statistics Canada Table 34-10-0135**: Housing Starts
  - Coverage: 1948-present, monthly
  - Types: Single, Multiple

## 🤝 Contributing

1. Run tests: `pytest -v`
2. Follow existing code style
3. Update documentation
4. Ensure audit score remains ≥85/100

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- Statistics Canada for NHPI and housing starts data
- Bank of Canada for interest rate data
- DuckDB team for the excellent analytical database
- Streamlit for the dashboard framework
python run_pipeline.py

# 3. Check the output
ls data/processed/
```

## Tech Stack

- **Python 3.10+** — extraction & orchestration
- **pandas** — data cleaning & transformation
- **DuckDB** — analytical SQL warehouse (Phase 2)
- **Streamlit** — interactive dashboard (Phase 3)

## License

Open data used under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).
