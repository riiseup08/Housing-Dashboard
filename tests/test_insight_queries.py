"""Unit tests for `insights.queries` against a tiny in-memory DuckDB fixture."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from insights import queries
from insights import generate_digest


@pytest.fixture
def conn():
    """Build a minimal star schema with enough rows to exercise every query."""
    c = duckdb.connect(":memory:")
    c.execute(
        """
        CREATE TABLE dim_date AS
        SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key, d AS full_date
          FROM (SELECT UNNEST(GENERATE_SERIES(DATE '2023-01-01', DATE '2024-06-30', INTERVAL '1 day'))::DATE AS d);

        CREATE TABLE dim_geography (
            geo_key INTEGER PRIMARY KEY,
            geo_name VARCHAR, province VARCHAR, geo_code VARCHAR, geo_type VARCHAR
        );
        INSERT INTO dim_geography VALUES
            (1, 'Canada',            NULL,      '001', 'Canada'),
            (2, 'Toronto, Ontario',  'Ontario', '002', 'CMA'),
            (3, 'Calgary, Alberta',  'Alberta', '003', 'CMA');

        CREATE TABLE fact_housing_prices (
            date_key INTEGER, geo_key INTEGER, nhpi_type VARCHAR,
            index_value DOUBLE, yoy_change_pct DOUBLE, mom_change_pct DOUBLE
        );
        -- Latest month: June 2024. National total: index 125, YoY +3.0
        INSERT INTO fact_housing_prices VALUES
            (20240601, 1, 'Total (house and land)', 125.0,  3.0, 0.4),
            (20240601, 2, 'Total (house and land)', 140.0,  5.5, 0.6),
            (20240601, 3, 'Total (house and land)', 110.0, -1.2, -0.2);

        CREATE TABLE fact_interest_rates (
            date_key INTEGER, bank_rate DOUBLE, overnight_target DOUBLE, rate_change DOUBLE
        );
        INSERT INTO fact_interest_rates VALUES
            (20230515, 4.75, 4.50, 0.0),
            (20240501, 5.25, 5.00, 0.0),
            (20240601, 5.00, 4.75, -25);

        CREATE TABLE fact_housing_starts (
            date_key INTEGER, geo_key INTEGER, housing_type VARCHAR,
            starts_count DOUBLE, rolling_12m_avg DOUBLE
        );
        -- Need 12+ months of Canada starts so the trailing-12 sum has substance.
        INSERT INTO fact_housing_starts
        SELECT date_key, 1, 'All types', 20000.0, 240000.0
          FROM dim_date
         WHERE full_date BETWEEN DATE '2023-07-01' AND DATE '2024-06-01'
           AND EXTRACT(DAY FROM full_date) = 1;
        -- One year ago observation with a smaller rolling avg
        INSERT INTO fact_housing_starts VALUES
            (20230601, 1, 'All types', 18000.0, 220000.0);
        """
    )
    yield c
    c.close()


def test_headline_kpis(conn):
    h = queries.headline_kpis(conn)
    assert h["nhpi"]["index"] == 125.0
    assert h["nhpi"]["yoy_pct"] == 3.0
    assert h["nhpi"]["as_of"] == "2024-06-01"
    assert h["boc_rate"]["overnight_target_pct"] == 4.75
    assert h["housing_starts_12m_total"] is not None and h["housing_starts_12m_total"] > 0


def test_cma_movers(conn):
    m = queries.cma_movers(conn, n=2)
    assert m["top"][0]["geo"] == "Toronto, Ontario"
    assert m["top"][0]["yoy_pct"] == 5.5
    assert m["bottom"][0]["geo"] == "Calgary, Alberta"
    assert m["bottom"][0]["yoy_pct"] == -1.2


def test_rate_context(conn):
    r = queries.rate_context(conn)
    assert r["current_pct"] == 4.75
    # 30-day prior point is 2024-05-01 at 5.00, current 4.75 → -25 bps
    assert r["change_30d_bps"] == -25
    # 365-day prior point is 2023-05-15 at 4.50, current 4.75 → +25 bps
    assert r["change_365d_bps"] == 25


def test_starts_trend(conn):
    s = queries.starts_trend(conn)
    assert s["rolling_12m_avg_current"] == 240000.0
    assert s["rolling_12m_avg_year_ago"] == 220000.0
    # (240000 - 220000) / 220000 * 100 ≈ 9.1
    assert s["yoy_pct"] == pytest.approx(9.1, abs=0.1)


def test_collect_all(conn):
    out = queries.collect_all(conn)
    assert set(out.keys()) == {"headline", "cma_movers", "rate_context", "starts_trend"}


def test_llm_narrative_falls_back_when_provider_fails(monkeypatch):
    stats = {
        "headline": {
            "nhpi": {"as_of": "2026-06-01", "yoy_pct": -1.0, "index": 120.0},
            "boc_rate": {"overnight_target_pct": 2.5},
            "housing_starts_12m_total": 200_000,
        },
        "cma_movers": {"top": [], "bottom": []},
        "rate_context": {"change_30d_bps": 0},
        "starts_trend": {"yoy_pct": 1.5},
    }

    class FailingCompletions:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("provider unavailable")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type(
                "Chat", (), {"completions": FailingCompletions()}
            )()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    sections = generate_digest._llm_narrative(stats)

    assert [section["title"] for section in sections] == [
        "What moved",
        "Affordability lens",
        "What to watch next",
    ]
