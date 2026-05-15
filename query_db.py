"""
Query the DuckDB housing affordability database.

Usage:
    python query_db.py --list                          # List all tables
    python query_db.py --table dim_geography          # Show table structure and sample
    python query_db.py --query 1                      # Run pre-built query #1
    python query_db.py --sql "SELECT * FROM dim_date LIMIT 5"  # Custom SQL
"""

import argparse
import sys
from pathlib import Path
import duckdb
from config import DB_PATH


def list_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """List all tables in the database."""
    result = conn.execute("""
        SELECT table_name, 
               (SELECT COUNT(*) FROM information_schema.tables t2 
                WHERE t2.table_name = t.table_name) as row_count
        FROM information_schema.tables t
        WHERE table_schema = 'main'
        ORDER BY table_name
    """).fetchall()
    
    print("\n" + "=" * 60)
    print("TABLES IN DATABASE")
    print("=" * 60)
    for table_name, _ in result:
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f"  {table_name:30s} {count:>10,} rows")
    print()


def describe_table(conn: duckdb.DuckDBPyConnection, table_name: str) -> None:
    """Show table structure and sample data."""
    # Get schema
    schema = conn.execute(f"DESCRIBE {table_name}").fetchdf()
    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    
    print("\n" + "=" * 60)
    print(f"TABLE: {table_name} ({count:,} rows)")
    print("=" * 60)
    print("\nSchema:")
    print(schema.to_string(index=False))
    
    # Get sample data
    print(f"\nSample data (first 5 rows):")
    sample = conn.execute(f"SELECT * FROM {table_name} LIMIT 5").fetchdf()
    print(sample.to_string(index=False))
    print()


def run_query(conn: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Execute custom SQL query."""
    try:
        result = conn.execute(sql).fetchdf()
        print("\n" + "=" * 60)
        print("QUERY RESULTS")
        print("=" * 60)
        print(result.to_string(index=False))
        print(f"\nRows returned: {len(result):,}")
        print()
    except Exception as e:
        print(f"\nError executing query: {e}\n")
        sys.exit(1)


def run_predefined_query(conn: duckdb.DuckDBPyConnection, query_num: int) -> None:
    """Run a pre-built analytical query."""
    queries = {
        1: {
            "name": "Recent Housing Price Trends (Last 12 Months)",
            "sql": """
                SELECT 
                    CONCAT(d.year, '-', LPAD(CAST(d.month AS VARCHAR), 2, '0')) as year_month,
                    g.geo_name,
                    ROUND(hp.index_value, 1) as index_value,
                    ROUND(hp.yoy_change_pct, 2) as yoy_change_pct,
                    ROUND(hp.mom_change_pct, 2) as mom_change_pct
                FROM fact_housing_prices hp
                JOIN dim_date d ON hp.date_key = d.date_key
                JOIN dim_geography g ON hp.geo_key = g.geo_key
                WHERE g.geo_name IN ('Canada', 'Toronto, Ontario', 'Vancouver, British Columbia', 'Montréal, Quebec')
                  AND d.full_date >= (
                      SELECT DATE_TRUNC('month', MAX(d2.full_date)) - INTERVAL '12 months'
                      FROM fact_housing_prices hp2
                      JOIN dim_date d2 ON hp2.date_key = d2.date_key
                  )
                  AND hp.nhpi_type = 'Total (house and land)'
                ORDER BY g.geo_name, d.full_date
            """
        },
        2: {
            "name": "Interest Rates vs Housing Prices (Monthly)",
            "sql": """
                SELECT 
                    CONCAT(d.year, '-', LPAD(CAST(d.month AS VARCHAR), 2, '0')) as year_month,
                    AVG(ir.bank_rate) as avg_bank_rate,
                    AVG(hp.index_value) as avg_canada_nhpi,
                    AVG(hp.yoy_change_pct) as avg_price_yoy_change
                FROM dim_date d
                LEFT JOIN fact_interest_rates ir ON d.date_key = ir.date_key
                LEFT JOIN fact_housing_prices hp 
                    ON d.date_key = hp.date_key 
                    AND hp.geo_key = (SELECT geo_key FROM dim_geography WHERE geo_name = 'Canada')
                    AND hp.nhpi_type = 'Total (house and land)'
                WHERE d.full_date >= '2020-01-01' AND d.is_month_start = TRUE
                GROUP BY d.year, d.month
                ORDER BY d.year, d.month
            """
        },
        3: {
            "name": "Top 5 Cities by Housing Starts (Last Year)",
            "sql": """
                SELECT 
                    g.geo_name,
                    SUM(hs.housing_starts) as total_starts,
                    AVG(hs.housing_starts) as avg_monthly_starts
                FROM fact_housing_starts hs
                JOIN dim_geography g ON hs.geo_key = g.geo_key
                JOIN dim_date d ON hs.date_key = d.date_key
                WHERE d.full_date >= (SELECT MAX(full_date) - INTERVAL '12 months' FROM dim_date)
                  AND g.geo_type = 'CMA'
                GROUP BY g.geo_name
                ORDER BY total_starts DESC
                LIMIT 5
            """
        },
        4: {
            "name": "Provincial Housing Price Growth YoY",
            "sql": """
                SELECT 
                    g.geo_name,
                    hp.index_value as latest_index,
                    hp.yoy_change_pct as annual_growth_pct,
                    d.full_date as as_of_date
                FROM fact_housing_prices hp
                JOIN dim_geography g ON hp.geo_key = g.geo_key
                JOIN dim_date d ON hp.date_key = d.date_key
                WHERE g.geo_type = 'Province'
                  AND hp.nhpi_type = 'Total (house and land)'
                  AND d.full_date = (SELECT MAX(d2.full_date) 
                                     FROM fact_housing_prices hp2 
                                     JOIN dim_date d2 ON hp2.date_key = d2.date_key)
                ORDER BY hp.yoy_change_pct DESC
            """
        },
        5: {
            "name": "Interest Rate Impact on Housing Starts",
            "sql": """
                SELECT 
                    d.year,
                    AVG(ir.bank_rate) as avg_bank_rate,
                    SUM(CASE WHEN g.geo_name = 'Canada' THEN hs.housing_starts ELSE 0 END) as canada_starts,
                    AVG(CASE WHEN g2.geo_name = 'Canada' AND hp.nhpi_type = 'Total (house and land)' 
                        THEN hp.yoy_change_pct END) as avg_price_change
                FROM dim_date d
                LEFT JOIN fact_interest_rates ir ON d.date_key = ir.date_key
                LEFT JOIN fact_housing_starts hs ON d.date_key = hs.date_key
                LEFT JOIN dim_geography g ON hs.geo_key = g.geo_key
                LEFT JOIN fact_housing_prices hp ON d.date_key = hp.date_key
                LEFT JOIN dim_geography g2 ON hp.geo_key = g2.geo_key
                WHERE d.year >= 2015 AND d.is_month_start = TRUE
                GROUP BY d.year
                ORDER BY d.year
            """
        }
    }
    
    if query_num not in queries:
        print(f"\nError: Query #{query_num} not found.")
        print("\nAvailable queries:")
        for num, info in queries.items():
            print(f"  {num}. {info['name']}")
        print()
        sys.exit(1)
    
    query_info = queries[query_num]
    print("\n" + "=" * 60)
    print(f"QUERY #{query_num}: {query_info['name']}")
    print("=" * 60)
    print("\nSQL:")
    print(query_info['sql'])
    
    run_query(conn, query_info['sql'])


def main():
    parser = argparse.ArgumentParser(
        description="Query the Canadian Housing Affordability DuckDB database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query_db.py --list
  python query_db.py --table dim_geography
  python query_db.py --query 1
  python query_db.py --sql "SELECT COUNT(*) FROM fact_housing_prices"
        """
    )
    
    parser.add_argument("--list", action="store_true", 
                       help="List all tables")
    parser.add_argument("--table", metavar="TABLE_NAME",
                       help="Describe a table (schema + sample data)")
    parser.add_argument("--query", type=int, metavar="N",
                       help="Run pre-built query #N (1-5)")
    parser.add_argument("--sql", metavar="SQL",
                       help="Execute custom SQL query")
    parser.add_argument("--db", metavar="PATH", default=DB_PATH,
                       help=f"Path to DuckDB file (default: {DB_PATH})")
    
    args = parser.parse_args()
    
    # Check if database exists
    if not Path(args.db).exists():
        print(f"\nError: Database not found at {args.db}")
        print("Run 'python run_pipeline.py --load-db' first to create it.\n")
        sys.exit(1)
    
    # Connect to database
    conn = duckdb.connect(str(args.db), read_only=True)
    
    try:
        if args.list:
            list_tables(conn)
        elif args.table:
            describe_table(conn, args.table)
        elif args.query:
            run_predefined_query(conn, args.query)
        elif args.sql:
            run_query(conn, args.sql)
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
