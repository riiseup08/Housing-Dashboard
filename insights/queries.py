"""
Query layer for the monthly housing insight digest.

Each function takes an open DuckDB connection and returns a plain dict / list
that can be JSON-serialised and handed to the email template or the LLM.
Keeping SQL here (and not in generate_digest.py) lets the unit tests run
against an in-memory database with a small fixture.
"""
from __future__ import annotations

from typing import Any


def headline_kpis(conn) -> dict[str, Any]:
    """Latest national NHPI, BoC overnight rate, and 12-month housing starts total."""
    nhpi = conn.execute(
        """
        SELECT d.full_date, f.index_value, f.yoy_change_pct, f.mom_change_pct
          FROM fact_housing_prices f
          JOIN dim_date d        ON f.date_key = d.date_key
          JOIN dim_geography g   ON f.geo_key  = g.geo_key
         WHERE g.geo_name = 'Canada'
           AND f.nhpi_type = 'Total (house and land)'
         ORDER BY d.full_date DESC
         LIMIT 1
        """
    ).fetchone()

    rate = conn.execute(
        """
        SELECT d.full_date, f.overnight_target, f.bank_rate
          FROM fact_interest_rates f
          JOIN dim_date d ON f.date_key = d.date_key
         ORDER BY d.full_date DESC
         LIMIT 1
        """
    ).fetchone()

    starts_12m = conn.execute(
        """
        WITH latest AS (
            SELECT MAX(d.full_date) AS d FROM fact_housing_starts f
            JOIN dim_date d ON f.date_key = d.date_key
        )
        SELECT SUM(f.starts_count)
          FROM fact_housing_starts f
          JOIN dim_date d      ON f.date_key = d.date_key
          JOIN dim_geography g ON f.geo_key  = g.geo_key
         WHERE g.geo_name = 'Canada'
           AND d.full_date > (SELECT d FROM latest) - INTERVAL 12 MONTH
        """
    ).fetchone()

    return {
        "nhpi": {
            "as_of": nhpi[0].isoformat() if nhpi and nhpi[0] else None,
            "index": float(nhpi[1]) if nhpi and nhpi[1] is not None else None,
            "yoy_pct": float(nhpi[2]) if nhpi and nhpi[2] is not None else None,
            "mom_pct": float(nhpi[3]) if nhpi and nhpi[3] is not None else None,
        },
        "boc_rate": {
            "as_of": rate[0].isoformat() if rate and rate[0] else None,
            "overnight_target_pct": float(rate[1]) if rate and rate[1] is not None else None,
            "bank_rate_pct": float(rate[2]) if rate and rate[2] is not None else None,
        },
        "housing_starts_12m_total": (
            int(starts_12m[0]) if starts_12m and starts_12m[0] is not None else None
        ),
    }


def cma_movers(conn, n: int = 5) -> dict[str, list[dict]]:
    """Top-N and bottom-N CMAs by YoY price change at the most recent observation."""
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT MAX(d.full_date) AS d FROM fact_housing_prices f
            JOIN dim_date d ON f.date_key = d.date_key
        )
        SELECT g.geo_name, f.yoy_change_pct, f.index_value
          FROM fact_housing_prices f
          JOIN dim_date d      ON f.date_key = d.date_key
          JOIN dim_geography g ON f.geo_key  = g.geo_key
         WHERE g.geo_type   = 'CMA'
           AND f.nhpi_type  = 'Total (house and land)'
           AND d.full_date  = (SELECT d FROM latest)
           AND f.yoy_change_pct IS NOT NULL
         ORDER BY f.yoy_change_pct DESC
        """
    ).fetchall()

    items = [
        {"geo": r[0], "yoy_pct": float(r[1]), "index": float(r[2])}
        for r in rows
    ]
    return {
        "top": items[:n],
        "bottom": list(reversed(items[-n:])) if len(items) >= n else list(reversed(items)),
    }


def rate_context(conn) -> dict[str, Any]:
    """Direction of policy rate over the trailing 30/90/365 days."""
    row = conn.execute(
        """
        WITH latest AS (
            SELECT MAX(d.full_date) AS d FROM fact_interest_rates f
            JOIN dim_date d ON f.date_key = d.date_key
        ),
        cur AS (
            SELECT f.overnight_target AS rate
              FROM fact_interest_rates f
              JOIN dim_date d ON f.date_key = d.date_key
             WHERE d.full_date = (SELECT d FROM latest)
        ),
        prev30 AS (
            SELECT f.overnight_target AS rate
              FROM fact_interest_rates f
              JOIN dim_date d ON f.date_key = d.date_key
             WHERE d.full_date <= (SELECT d FROM latest) - INTERVAL 30 DAY
             ORDER BY d.full_date DESC LIMIT 1
        ),
        prev365 AS (
            SELECT f.overnight_target AS rate
              FROM fact_interest_rates f
              JOIN dim_date d ON f.date_key = d.date_key
             WHERE d.full_date <= (SELECT d FROM latest) - INTERVAL 365 DAY
             ORDER BY d.full_date DESC LIMIT 1
        )
        SELECT (SELECT rate FROM cur),
               (SELECT rate FROM prev30),
               (SELECT rate FROM prev365)
        """
    ).fetchone()

    cur, p30, p365 = row or (None, None, None)
    to_bps = lambda a, b: round((float(a) - float(b)) * 100) if a is not None and b is not None else None
    return {
        "current_pct": float(cur) if cur is not None else None,
        "change_30d_bps": to_bps(cur, p30),
        "change_365d_bps": to_bps(cur, p365),
    }


def starts_trend(conn) -> dict[str, Any]:
    """Latest national 12-month rolling average vs one year prior."""
    row = conn.execute(
        """
        WITH latest AS (
            SELECT MAX(d.full_date) AS d FROM fact_housing_starts f
            JOIN dim_date d ON f.date_key = d.date_key
        )
        SELECT
            (SELECT f.rolling_12m_avg
               FROM fact_housing_starts f
               JOIN dim_date d      ON f.date_key = d.date_key
               JOIN dim_geography g ON f.geo_key  = g.geo_key
              WHERE g.geo_name = 'Canada'
                AND d.full_date = (SELECT d FROM latest)
              ORDER BY f.rolling_12m_avg DESC LIMIT 1),
            (SELECT f.rolling_12m_avg
               FROM fact_housing_starts f
               JOIN dim_date d      ON f.date_key = d.date_key
               JOIN dim_geography g ON f.geo_key  = g.geo_key
              WHERE g.geo_name = 'Canada'
                AND d.full_date <= (SELECT d FROM latest) - INTERVAL 12 MONTH
              ORDER BY d.full_date DESC LIMIT 1)
        """
    ).fetchone()

    cur, prev = row or (None, None)
    pct = None
    if cur is not None and prev not in (None, 0):
        pct = round((float(cur) - float(prev)) / float(prev) * 100, 1)
    return {
        "rolling_12m_avg_current": float(cur) if cur is not None else None,
        "rolling_12m_avg_year_ago": float(prev) if prev is not None else None,
        "yoy_pct": pct,
    }


def collect_all(conn) -> dict[str, Any]:
    """Convenience: every KPI bundle in one dict, ready for templates / LLM."""
    return {
        "headline": headline_kpis(conn),
        "cma_movers": cma_movers(conn),
        "rate_context": rate_context(conn),
        "starts_trend": starts_trend(conn),
    }
