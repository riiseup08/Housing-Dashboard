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

# Dataset-specific freshness thresholds
# NHPI and Housing Starts are published less frequently than interest rates
FRESHNESS_THRESHOLDS = {
    "Interest rates": 45,   # Bank of Canada updates frequently
    "NHPI": 90,             # Statistics Canada publishes monthly with ~2-3 month lag
    # Quarterly series: REF_DATE is the quarter's FIRST month, so the newest
    # published point (e.g. Q1 dated Jan 1) is already ~180-240 days "old" during
    # the window before the next quarter releases (~2 months after quarter end).
    # 250 covers that full cycle without false-failing; a genuine StatCan outage
    # still trips it after roughly one missed quarter.
    "Housing starts": 250,  # CMHC quarterly data, dated at quarter start
}

DEFAULT_MAX_AGE_DAYS = 45  # Fallback for unlisted sources


def check_freshness(
    conn: duckdb.DuckDBPyConnection | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[str]:
    """Verify that each fact table's latest date is within max_age_days of today.

    Mirrors the SQL used by `dashboard._freshness()` so the workflow's
    failure condition lines up with the dashboard's red/yellow indicator.

    Note: Uses dataset-specific thresholds from FRESHNESS_THRESHOLDS dict,
    falling back to max_age_days parameter for unlisted sources.

    Args:
        conn: Optional open DuckDB connection. If None, opens a read-only one
            against DB_PATH.
        max_age_days: Default threshold in days for sources not in FRESHNESS_THRESHOLDS.

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
        # Use dataset-specific threshold if available, otherwise use default
        threshold = FRESHNESS_THRESHOLDS.get(source, max_age_days)
        if age > threshold:
            errors.append(
                f"{source} latest data is {latest.isoformat()} "
                f"({age} days old, max {threshold})"
            )
        else:
            logger.info("  ✓ %s fresh: %s (%d days old, threshold %d)", 
                       source, latest, age, threshold)
    return errors
