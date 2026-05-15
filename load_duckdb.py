"""
DuckDB Transformation Layer
Loads cleaned CSV data into a star schema for analytical queries.
"""
import logging
from pathlib import Path

import duckdb

from config import DB_PATH, DATA_PROCESSED

logger = logging.getLogger(__name__)


def get_connection(db_path: Path = None) -> duckdb.DuckDBPyConnection:
    """
    Get or create a DuckDB connection.
    
    Args:
        db_path: Path to DuckDB database file (default: from config)
        
    Returns:
        DuckDB connection object
    """
    if db_path is None:
        db_path = DB_PATH
    
    logger.info(f"Connecting to DuckDB: {db_path}")
    return duckdb.connect(str(db_path))


def execute_sql_file(conn: duckdb.DuckDBPyConnection, sql_file: Path) -> None:
    """
    Execute a SQL file in DuckDB.
    
    Args:
        conn: DuckDB connection
        sql_file: Path to SQL file
    """
    logger.info(f"Executing SQL file: {sql_file.name}")
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    # DuckDB can execute entire SQL scripts at once
    try:
        conn.execute(sql_script)
    except Exception as e:
        logger.error(f"Error executing {sql_file.name}: {e}")
        raise


def load_to_duckdb(sql_dir: Path = None) -> dict:
    """
    Load CSV data into DuckDB star schema.
    
    Executes SQL scripts in order:
    1. 01_schema.sql - Create tables
    2. 02_load_and_transform.sql - Load data from CSVs
    
    Args:
        sql_dir: Directory containing SQL scripts (default: PROJECT_ROOT/sql)
        
    Returns:
        Dictionary with table names and row counts
    """
    logger.info("=" * 60)
    logger.info("LOADING DATA TO DUCKDB")
    logger.info("=" * 60)
    
    if sql_dir is None:
        from config import PROJECT_ROOT
        sql_dir = PROJECT_ROOT / "sql"
    
    # Check that CSVs exist
    required_csvs = [
        DATA_PROCESSED / "nhpi_clean.csv",
        DATA_PROCESSED / "boc_rates_clean.csv",
        DATA_PROCESSED / "housing_starts_clean.csv",
    ]
    
    missing = [csv for csv in required_csvs if not csv.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required CSV files: {[str(f) for f in missing]}\n"
            f"Run the extraction pipeline first: python run_pipeline.py"
        )
    
    # Connect to DuckDB
    conn = get_connection()
    
    try:
        # Execute SQL scripts in order
        sql_files = [
            sql_dir / "01_schema.sql",
            sql_dir / "02_load_and_transform.sql",
        ]
        
        for sql_file in sql_files:
            if not sql_file.exists():
                raise FileNotFoundError(f"SQL file not found: {sql_file}")
            execute_sql_file(conn, sql_file)
        
        # Get row counts
        logger.info("\nVerifying data load...")
        tables = {
            "dim_date": "SELECT COUNT(*) FROM dim_date",
            "dim_geography": "SELECT COUNT(*) FROM dim_geography",
            "fact_housing_prices": "SELECT COUNT(*) FROM fact_housing_prices",
            "fact_housing_starts": "SELECT COUNT(*) FROM fact_housing_starts",
            "fact_interest_rates": "SELECT COUNT(*) FROM fact_interest_rates",
        }
        
        results = {}
        for table_name, query in tables.items():
            try:
                count = conn.execute(query).fetchone()[0]
                results[table_name] = count
                logger.info(f"  {table_name:25} {count:>10,} rows")
            except Exception as e:
                logger.warning(f"  {table_name:25} Error: {e}")
                results[table_name] = 0
        
        logger.info(f"\nDatabase saved to: {DB_PATH}")
        
        return results
    
    finally:
        conn.close()


def run_analytical_query(query_name: str, sql_dir: Path = None) -> list:
    """
    Run a specific analytical query from 03_analytical_queries.sql
    
    Args:
        query_name: Name of the query to run
        sql_dir: Directory containing SQL scripts
        
    Returns:
        List of result rows
    """
    if sql_dir is None:
        from config import PROJECT_ROOT
        sql_dir = PROJECT_ROOT / "sql"
    
    conn = get_connection()
    
    try:
        # For now, just test connection
        result = conn.execute("SELECT COUNT(*) FROM fact_housing_prices").fetchone()
        logger.info(f"Query test: {result}")
        return result
    finally:
        conn.close()


def get_table_info(table_name: str = None) -> dict:
    """
    Get information about tables in the DuckDB database.
    
    Args:
        table_name: Specific table to query (None for all tables)
        
    Returns:
        Dictionary with table information
    """
    conn = get_connection()
    
    try:
        if table_name:
            # Get info for specific table
            schema = conn.execute(
                f"DESCRIBE {table_name}"
            ).fetchall()
            return {table_name: schema}
        else:
            # Get all tables
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
            return {"tables": [t[0] for t in tables]}
    finally:
        conn.close()


if __name__ == "__main__":
    # Test loading
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    
    results = load_to_duckdb()
    print("\nLoad complete!")
    print(f"Total fact rows: {sum(v for k, v in results.items() if k.startswith('fact_')):,}")
