"""
Post-load data quality checks.

Run after `load_duckdb.load_to_duckdb()` has rebuilt the warehouse. Each check
returns a list of human-readable error strings (empty list = OK), so callers
can aggregate and decide whether to fail.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import duckdb

from config import DB_PATH

logger = logging.getLogger(__name__)

# Same threshold the dashboard's sidebar uses for its 🟢 stoplight.
DEFAULT_MAX_AGE_DAYS = 45


def check_freshness(
    conn: duckdb.DuckDBPyConnection | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[str]:
    """Verify that each fact table's latest date is within max_age_days of today.

    Mirrors the SQL used by `dashboard._freshness()` so the workflow's
    failure condition lines up with the dashboard's red/yellow indicator.

    Args:
        conn: Optional open DuckDB connection. If None, opens a read-only one
            against DB_PATH.
        max_age_days: Threshold in days.

    Returns:
        List of error strings; empty if all sources are fresh.
    """
    owns_conn = False
    if conn is None:
        if not Path(DB_PATH).exists():
            return [f"DuckDB file not found at {DB_PATH}"]
        conn = duckdb.connect(str(DB_PATH), read_only=True)
        owns_conn = True

    try:
        rows = conn.execute(
            """
            SELECT 'NHPI'           AS source, MAX(d.full_date) AS latest
              FROM fact_housing_prices f JOIN dim_date d ON f.date_key = d.date_key
            UNION ALL
            SELECT 'Interest rates',         MAX(d.full_date)
              FROM fact_interest_rates  f JOIN dim_date d ON f.date_key = d.date_key
            UNION ALL
            SELECT 'Housing starts',         MAX(d.full_date)
              FROM fact_housing_starts  f JOIN dim_date d ON f.date_key = d.date_key
            """
        ).fetchall()
    finally:
        if owns_conn:
            conn.close()

    errors: list[str] = []
    today = datetime.now().date()
    for source, latest in rows:
        if latest is None:
            errors.append(f"{source}: no rows in fact table")
            continue
        age = (today - latest).days
        if age > max_age_days:
            errors.append(
                f"{source} latest data is {latest.isoformat()} "
                f"({age} days old, max {max_age_days})"
            )
        else:
            logger.info("  ✓ %s fresh: %s (%d days old)", source, latest, age)
    return errors
