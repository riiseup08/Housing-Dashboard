"""
Extract interest rate data from the Bank of Canada Valet API.

Source: Bank of Canada Valet Web Services (no API key required)
URL:    https://www.bankofcanada.ca/valet/observations/{series}/json
Series: V39079 (Bank Rate), V39078 (Target Overnight Rate)

Output columns:
    date              — observation date (YYYY-MM-DD)
    bank_rate         — Bank Rate (upper bound of operating band)
    overnight_target  — Target for the overnight rate
"""

import logging
from pathlib import Path

import pandas as pd
import requests

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    BOC_VALET_BASE,
    BOC_SERIES,
    BOC_START_DATE,
    BOC_PROCESSED,
    API_TIMEOUT,
)
from .utils import get_session_with_retries
from .validators import validate_boc_rates

logger = logging.getLogger(__name__)


def _fetch_series(series_name: str, series_code: str) -> pd.DataFrame:
    """
    Fetch a single series from the Valet API.

    The Valet API returns JSON like:
    {
        "observations": [
            {"d": "2024-01-01", "{series_code}": {"v": "5.00"}},
            ...
        ]
    }
    """
    url = f"{BOC_VALET_BASE}/observations/{series_code}/json"
    params = {"start_date": BOC_START_DATE}

    logger.info(f"Fetching {series_name} ({series_code}) from Valet API ...")
    
    session = get_session_with_retries()
    resp = session.get(url, params=params, timeout=API_TIMEOUT)
    resp.raise_for_status()

    data = resp.json()
    observations = data.get("observations", [])
    logger.info(f"  Received {len(observations):,} observations")

    # Parse into DataFrame
    records = []
    for obs in observations:
        date = obs.get("d")
        value_obj = obs.get(series_code, {})
        value = value_obj.get("v") if isinstance(value_obj, dict) else None
        if date and value:
            records.append({"date": date, series_name: float(value)})

    return pd.DataFrame(records)


def _clean_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate the merged interest rate data."""
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Forward-fill gaps (weekends/holidays have no observations)
    # but keep the original sparse data — filling happens in SQL later
    before = len(df)
    df = df.dropna(subset=["bank_rate", "overnight_target"], how="all")
    logger.info(f"Clean data: {len(df):,} rows (dropped {before - len(df)} empty)")

    logger.info(
        f"  Date range: {df['date'].min():%Y-%m-%d} to {df['date'].max():%Y-%m-%d}"
    )
    return df


def extract_boc_rates() -> pd.DataFrame:
    """
    Full extraction pipeline for Bank of Canada interest rates.
    Fetches multiple series → merges on date → cleans → validates → saves CSV.
    """
    logger.info("=" * 60)
    logger.info("EXTRACTING: Bank of Canada — Interest Rates (Valet API)")
    logger.info("=" * 60)

    # Fetch each series independently, then merge
    frames = {}
    for name, code in BOC_SERIES.items():
        frames[name] = _fetch_series(name, code)

    # Merge all series on date (outer join to keep all dates)
    merged = frames["bank_rate"]
    for name in list(BOC_SERIES.keys())[1:]:
        merged = merged.merge(frames[name], on="date", how="outer")

    clean_df = _clean_rates(merged)

    # Validate data quality
    errors = validate_boc_rates(clean_df)
    if errors:
        logger.warning("Data validation warnings:")
        for error in errors:
            logger.warning(f"  - {error}")

    # Save
    clean_df.to_csv(BOC_PROCESSED, index=False)
    logger.info(f"Saved → {BOC_PROCESSED}")

    return clean_df


# ── Run standalone ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    df = extract_boc_rates()
    print(f"\nSample output:\n{df.tail(10).to_string(index=False)}")
    print(f"\nCurrent Bank Rate: {df['bank_rate'].iloc[-1]}%")
