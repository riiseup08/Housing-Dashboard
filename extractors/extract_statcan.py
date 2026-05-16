"""
Extract & clean the New Housing Price Index (NHPI) from Statistics Canada.

Source: Table 18-10-0205-01
URL:    https://www150.statcan.gc.ca/n1/tbl/csv/18100205-eng.zip
Freq:   Monthly (base period 201612=100)
Covers: 27 Census Metropolitan Areas + national composite

Output columns:
    date           — first of month (YYYY-MM-01)
    geo            — geography name (e.g. "Toronto, Ontario")
    geo_code       — DGUID geographic identifier
    nhpi_type      — "Total (house and land)" | "House only" | "Land only"
    index_value    — float, the NHPI reading
"""

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    STATCAN_NHPI_URL,
    STATCAN_NHPI_RAW,
    STATCAN_NHPI_PROCESSED,
    DOWNLOAD_TIMEOUT,
)
from .utils import download_with_retry
from .validators import validate_nhpi_data

logger = logging.getLogger(__name__)


def _download_zip(url: str, dest: Path) -> Path:
    """Download a zip file if it doesn't already exist locally."""
    if dest.exists():
        logger.info(f"Using cached file: {dest.name}")
        return dest

    logger.info(f"Downloading {url} ...")
    content = download_with_retry(url, timeout=DOWNLOAD_TIMEOUT)
    dest.write_bytes(content)
    logger.info(f"Saved {dest.name}")
    return dest


def _unzip_csv(zip_path: Path) -> pd.DataFrame:
    """Extract the main CSV from a Stats Canada zip archive."""
    with zipfile.ZipFile(zip_path) as zf:
        # Stats Canada zips contain the data CSV + a metadata CSV
        csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
        # The data file is the one WITHOUT "MetaData" in the name
        data_file = [f for f in csv_files if "MetaData" not in f][0]
        logger.info(f"Extracting {data_file} from archive")
        with zf.open(data_file) as f:
            return pd.read_csv(f, low_memory=False)


def _clean_nhpi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw Stats Canada NHPI data.

    Raw columns include: REF_DATE, GEO, DGUID, New housing price indexes,
    UOM, UOM_ID, SCALAR_FACTOR, SCALAR_ID, VECTOR, COORDINATE, VALUE, STATUS,
    SYMBOL, TERMINATED, DECIMALS
    """
    logger.info(f"Raw data: {len(df):,} rows, {len(df.columns)} columns")

    # ── Select & rename columns ────────────────────────────────
    col_map = {
        "REF_DATE": "date",
        "GEO": "geo",
        "DGUID": "geo_code",
        "New housing price indexes": "nhpi_type",
        "VALUE": "index_value",
    }
    df = df[list(col_map.keys())].rename(columns=col_map)

    # ── Parse dates ────────────────────────────────────────────
    # REF_DATE comes as "YYYY-MM"; convert to first-of-month date
    df["date"] = pd.Series(pd.to_datetime(df["date"], format="%Y-%m"), dtype="datetime64[ns]")

    # ── Drop rows with missing index values ────────────────────
    before = len(df)
    df = df.dropna(subset=["index_value"])
    dropped = before - len(df)
    if dropped:
        logger.info(f"Dropped {dropped:,} rows with null index values")

    # ── Cast types ─────────────────────────────────────────────
    df["index_value"] = df["index_value"].astype(float)

    # ── Sort for consistency ───────────────────────────────────
    df = df.sort_values(["date", "geo", "nhpi_type"]).reset_index(drop=True)

    logger.info(
        f"Clean data: {len(df):,} rows | "
        f"{df['date'].min():%Y-%m} to {df['date'].max():%Y-%m} | "
        f"{df['geo'].nunique()} geographies"
    )
    return df


def extract_nhpi() -> pd.DataFrame:
    """
    Full extraction pipeline for Statistics Canada NHPI.
    Downloads → unzips → cleans → validates → saves processed CSV → returns DataFrame.
    """
    logger.info("=" * 60)
    logger.info("EXTRACTING: Statistics Canada — New Housing Price Index")
    logger.info("=" * 60)

    zip_path = _download_zip(STATCAN_NHPI_URL, STATCAN_NHPI_RAW)
    raw_df = _unzip_csv(zip_path)
    clean_df = _clean_nhpi(raw_df)

    # Validate data quality
    errors = validate_nhpi_data(clean_df)
    if errors:
        logger.warning("Data validation warnings:")
        for error in errors:
            logger.warning(f"  - {error}")

    # Save processed output
    clean_df.to_csv(STATCAN_NHPI_PROCESSED, index=False)
    logger.info(f"Saved → {STATCAN_NHPI_PROCESSED}")

    return clean_df


# ── Run standalone ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    df = extract_nhpi()
    print(f"\nSample output:\n{df.head(10).to_string(index=False)}")
    print(f"\nNHPI types: {df['nhpi_type'].unique().tolist()}")
    print(f"Geographies: {sorted(df['geo'].unique())[:10]} ...")
