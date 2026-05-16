"""
Migrate Canadian Housing Affordability Data to PostgreSQL
==========================================================
Loads cleaned CSV data into PostgreSQL for cloud deployment.

Usage:
    # Set DATABASE_URL environment variable
    export DATABASE_URL="postgresql://user:password@host:5432/dbname"
    
    # Run migration
    python migrate_to_postgres.py
"""

import logging
import sys
import os
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from config import DATA_PROCESSED, DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def create_postgresql_schema(engine):
    """Create PostgreSQL schema (converted from DuckDB DDL)."""
    logger.info("Creating PostgreSQL schema...")
    
    schema_sql = """
    -- Drop existing tables
    DROP TABLE IF EXISTS fact_housing_prices CASCADE;
    DROP TABLE IF EXISTS fact_housing_starts CASCADE;
    DROP TABLE IF EXISTS fact_interest_rates CASCADE;
    DROP TABLE IF EXISTS dim_date CASCADE;
    DROP TABLE IF EXISTS dim_geography CASCADE;
    
    -- ============================================================
    -- DIMENSION: dim_date
    -- ============================================================
    CREATE TABLE dim_date (
        date_key INTEGER PRIMARY KEY,
        full_date DATE NOT NULL,
        year INTEGER,
        quarter INTEGER,
        month INTEGER,
        month_name VARCHAR(20),
        month_abbrev VARCHAR(3),
        day_of_year INTEGER,
        is_month_start BOOLEAN,
        is_quarter_start BOOLEAN,
        fiscal_year INTEGER
    );
    
    -- Generate date dimension (2000-2030)
    INSERT INTO dim_date (
        date_key, full_date, year, quarter, month, month_name, 
        month_abbrev, day_of_year, is_month_start, is_quarter_start, fiscal_year
    )
    SELECT
        TO_CHAR(d, 'YYYYMMDD')::INTEGER AS date_key,
        d AS full_date,
        EXTRACT(YEAR FROM d)::INTEGER AS year,
        EXTRACT(QUARTER FROM d)::INTEGER AS quarter,
        EXTRACT(MONTH FROM d)::INTEGER AS month,
        TO_CHAR(d, 'Month') AS month_name,
        TO_CHAR(d, 'Mon') AS month_abbrev,
        EXTRACT(DOY FROM d)::INTEGER AS day_of_year,
        (EXTRACT(DAY FROM d) = 1) AS is_month_start,
        (d = DATE_TRUNC('quarter', d)) AS is_quarter_start,
        CASE 
            WHEN EXTRACT(MONTH FROM d) >= 4 THEN EXTRACT(YEAR FROM d)::INTEGER
            ELSE EXTRACT(YEAR FROM d)::INTEGER - 1
        END AS fiscal_year
    FROM generate_series(
        DATE '1948-01-01',
        DATE '2030-12-31',
        INTERVAL '1 day'
    ) AS d;
    
    -- ============================================================
    -- DIMENSION: dim_geography
    -- ============================================================
    CREATE TABLE dim_geography (
        geo_key INTEGER PRIMARY KEY,
        geo_name VARCHAR(100) NOT NULL,
        province VARCHAR(50),
        geo_code VARCHAR(50),
        geo_type VARCHAR(20)
    );
    
    -- ============================================================
    -- FACT: fact_housing_prices
    -- ============================================================
    CREATE TABLE fact_housing_prices (
        date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
        geo_key INTEGER NOT NULL REFERENCES dim_geography(geo_key),
        nhpi_type VARCHAR(100) NOT NULL,
        index_value DOUBLE PRECISION,
        yoy_change_pct DOUBLE PRECISION,
        mom_change_pct DOUBLE PRECISION
    );
    
    CREATE INDEX idx_housing_prices_date ON fact_housing_prices(date_key);
    CREATE INDEX idx_housing_prices_geo ON fact_housing_prices(geo_key);
    
    -- ============================================================
    -- FACT: fact_housing_starts
    -- ============================================================
    CREATE TABLE fact_housing_starts (
        date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
        geo_key INTEGER NOT NULL REFERENCES dim_geography(geo_key),
        housing_type VARCHAR(100) NOT NULL,
        starts_count DOUBLE PRECISION,
        rolling_12m_avg DOUBLE PRECISION
    );
    
    CREATE INDEX idx_housing_starts_date ON fact_housing_starts(date_key);
    CREATE INDEX idx_housing_starts_geo ON fact_housing_starts(geo_key);
    
    -- ============================================================
    -- FACT: fact_interest_rates
    -- ============================================================
    CREATE TABLE fact_interest_rates (
        date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
        bank_rate DOUBLE PRECISION,
        overnight_target DOUBLE PRECISION,
        rate_change DOUBLE PRECISION
    );
    
    CREATE INDEX idx_interest_rates_date ON fact_interest_rates(date_key);
    """
    
    with engine.begin() as conn:
        # Execute each statement separately
        for statement in schema_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    logger.error(f"Error executing: {statement[:100]}...")
                    raise e
    
    logger.info("✓ Schema created successfully")


def load_data_to_postgresql(engine):
    """Load CSV data into PostgreSQL tables."""
    logger.info("Loading data from CSVs...")
    
    # Check required CSV files
    required_files = {
        'nhpi': DATA_PROCESSED / "nhpi_clean.csv",
        'boc': DATA_PROCESSED / "boc_rates_clean.csv",
        'starts': DATA_PROCESSED / "housing_starts_clean.csv"
    }
    
    for name, path in required_files.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {name} CSV: {path}\n"
                f"Run the extraction pipeline first: python run_pipeline.py"
            )
    
    # Load CSVs
    logger.info("Reading CSVs...")
    df_nhpi = pd.read_csv(required_files['nhpi'], parse_dates=['date'])
    df_boc = pd.read_csv(required_files['boc'], parse_dates=['date'])
    df_starts = pd.read_csv(required_files['starts'], parse_dates=['date'])
    
    logger.info(f"  NHPI: {len(df_nhpi):,} rows")
    logger.info(f"  BOC Rates: {len(df_boc):,} rows")
    logger.info(f"  Housing Starts: {len(df_starts):,} rows")
    
    # ── Step 1: Populate dim_geography ──
    logger.info("Populating dim_geography...")
    
    # Combine unique geographies
    geos_nhpi = df_nhpi[['geo', 'geo_code']].drop_duplicates()
    geos_nhpi.columns = ['geo_name', 'geo_code']
    
    geos_starts = df_starts[['geo', 'geo_code']].drop_duplicates()
    geos_starts.columns = ['geo_name', 'geo_code']
    
    all_geos = pd.concat([geos_nhpi, geos_starts]).drop_duplicates()
    
    # Extract province and classify type
    def classify_geo(geo_name):
        if geo_name == 'Canada':
            return None, 'Canada'
        elif ',' in geo_name:
            province = geo_name.split(',')[1].strip()
            return province, 'CMA'
        else:
            return geo_name, 'Province'
    
    all_geos['province'], all_geos['geo_type'] = zip(*all_geos['geo_name'].map(classify_geo))
    all_geos = all_geos.sort_values(['geo_type', 'geo_name']).reset_index(drop=True)
    all_geos['geo_key'] = range(1, len(all_geos) + 1)
    
    # Reorder columns
    all_geos = all_geos[['geo_key', 'geo_name', 'province', 'geo_code', 'geo_type']]
    
    # Write to database
    all_geos.to_sql('dim_geography', engine, if_exists='append', index=False)
    logger.info(f"  ✓ Loaded {len(all_geos)} geographies")
    
    # ── Step 2: Populate fact_housing_prices ──
    logger.info("Populating fact_housing_prices...")
    
    # Join with dimensions
    df_prices = df_nhpi.copy()
    df_prices['date_key'] = df_prices['date'].dt.strftime('%Y%m%d').astype(int)
    
    # Merge with geography
    df_prices = df_prices.merge(
        all_geos[['geo_key', 'geo_name']],
        left_on='geo',
        right_on='geo_name',
        how='left'
    )
    
    # Calculate YoY and MoM changes
    df_prices = df_prices.sort_values(['geo', 'nhpi_type', 'date'])
    df_prices['yoy_change_pct'] = df_prices.groupby(['geo', 'nhpi_type'])['index_value'].pct_change(12) * 100
    df_prices['mom_change_pct'] = df_prices.groupby(['geo', 'nhpi_type'])['index_value'].pct_change() * 100
    
    # Select final columns
    fact_prices = df_prices[[
        'date_key', 'geo_key', 'nhpi_type', 'index_value', 
        'yoy_change_pct', 'mom_change_pct'
    ]].dropna(subset=['geo_key'])
    
    fact_prices.to_sql('fact_housing_prices', engine, if_exists='append', index=False)
    logger.info(f"  ✓ Loaded {len(fact_prices):,} price records")
    
    # ── Step 3: Populate fact_housing_starts ──
    logger.info("Populating fact_housing_starts...")
    
    df_starts_fact = df_starts.copy()
    df_starts_fact['date_key'] = df_starts_fact['date'].dt.strftime('%Y%m%d').astype(int)
    
    # Merge with geography
    df_starts_fact = df_starts_fact.merge(
        all_geos[['geo_key', 'geo_name']],
        left_on='geo',
        right_on='geo_name',
        how='left'
    )
    
    # Calculate 12-month rolling average
    df_starts_fact = df_starts_fact.sort_values(['geo', 'housing_type', 'date'])
    df_starts_fact['rolling_12m_avg'] = df_starts_fact.groupby(['geo', 'housing_type'])['starts_count'].transform(
        lambda x: x.rolling(12, min_periods=1).mean()
    )
    
    fact_starts = df_starts_fact[[
        'date_key', 'geo_key', 'housing_type', 'starts_count', 'rolling_12m_avg'
    ]].dropna(subset=['geo_key'])
    
    fact_starts.to_sql('fact_housing_starts', engine, if_exists='append', index=False)
    logger.info(f"  ✓ Loaded {len(fact_starts):,} housing start records")
    
    # ── Step 4: Populate fact_interest_rates ──
    logger.info("Populating fact_interest_rates...")
    
    df_rates = df_boc.copy()
    df_rates['date_key'] = df_rates['date'].dt.strftime('%Y%m%d').astype(int)
    
    # Calculate rate change
    df_rates = df_rates.sort_values('date')
    df_rates['rate_change'] = df_rates['bank_rate'].diff()
    
    fact_rates = df_rates[['date_key', 'bank_rate', 'overnight_target', 'rate_change']]
    
    fact_rates.to_sql('fact_interest_rates', engine, if_exists='append', index=False)
    logger.info(f"  ✓ Loaded {len(fact_rates):,} interest rate records")


def verify_migration(engine):
    """Verify data was loaded correctly."""
    logger.info("\nVerifying migration...")
    
    tables = [
        'dim_date', 'dim_geography', 
        'fact_housing_prices', 'fact_housing_starts', 'fact_interest_rates'
    ]
    
    with engine.connect() as conn:
        for table in tables:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            logger.info(f"  {table:30s} {count:>10,} rows")
    
    logger.info("\n✓ Migration completed successfully!")


def main():
    """Main migration function."""
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable not set!")
        logger.error("Example: export DATABASE_URL='postgresql://user:pass@host:5432/dbname'")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("POSTGRESQL MIGRATION")
    logger.info("=" * 60)
    logger.info(f"Target: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'localhost'}")
    
    # Create SQLAlchemy engine
    engine = create_engine(DATABASE_URL)
    
    try:
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✓ Database connection successful\n")
        
        # Run migration
        create_postgresql_schema(engine)
        load_data_to_postgresql(engine)
        verify_migration(engine)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
