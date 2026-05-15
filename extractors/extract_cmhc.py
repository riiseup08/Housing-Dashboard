"""
Extract housing starts data (CMHC) from Statistics Canada.

Source: Table 34-10-0135-01 — Canada Mortgage and Housing Corporation,
        housing starts, all areas, quarterly
URL:    https://www150.statcan.gc.ca/n1/tbl/csv/34100135-eng.zip

Output columns:
    date             — first of quarter (YYYY-MM-01)
    geo              — geography (Canada, provinces, CMAs)
    geo_code         — DGUID geographic identifier
    housing_type     — "Single" | "Semi-detached" | "Row" | "Apartment" | "All types"
    starts_count     — number of housing starts (units)
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
    CMHC_STARTS_URL,
    CMHC_STARTS_RAW,
    CMHC_STARTS_PROCESSED,
    DOWNLOAD_TIMEOUT,
)
from .utils import download_with_retry
from .validators import validate_housing_starts

logger = logging.getLogger(__name__)


def _download_zip(url: str, dest: Path) -> Path:
    """Download a zip file if not already cached."""
    if dest.exists():
        logger.info(f"Using cached file: {dest.name}")
        return dest

    logger.info(f"Downloading {url} ...")
    content = download_with_retry(url, timeout=DOWNLOAD_TIMEOUT)
    dest.write_bytes(content)
    logger.info(f"Saved {dest.name}")
    return dest


def _unzip_csv(zip_path: Path) -> pd.DataFrame:
    """Extract the main data CSV from a Stats Canada zip."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
        data_file = [f for f in csv_files if "MetaData" not in f][0]
        logger.info(f"Extracting {data_file} from archive")
        with zf.open(data_file) as f:
            return pd.read_csv(f, low_memory=False)


def _clean_housing_starts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw housing starts data.

    Raw columns typically include: REF_DATE, GEO, DGUID,
    Type of unit, Housing estimates, UOM, VALUE, STATUS, etc.
    """
    logger.info(f"Raw data: {len(df):,} rows, {len(df.columns)} columns")
    logger.info(f"Columns: {df.columns.tolist()}")

    # ── Identify the type column (varies by table version) ─────
    type_col = None
    for candidate in ["Type of unit", "Type of dwelling", "Housing estimates"]:
        if candidate in df.columns:
            type_col = candidate
            break

    if type_col is None:
        # Fall back: use any column that contains dwelling type info
        logger.warning("Could not find expected type column; listing available:")
        for col in df.columns:
            logger.warning(f"  {col}: {df[col].nunique()} unique values")
        type_col = df.columns[3]  # Usually the 4th column is the classifier

    # ── Select & rename ────────────────────────────────────────
    col_map = {
        "REF_DATE": "date",
        "GEO": "geo",
        "DGUID": "geo_code",
        type_col: "housing_type",
        "VALUE": "starts_count",
    }

    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # ── Parse dates ────────────────────────────────────────────
    # REF_DATE may be "YYYY-MM" or "YYYY" depending on frequency
    df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=False)

    # ── Drop nulls ─────────────────────────────────────────────
    before = len(df)
    df = df.dropna(subset=["starts_count"])
    logger.info(f"Dropped {before - len(df):,} rows with null counts")

    df["starts_count"] = df["starts_count"].astype(float)

    # ── Sort ───────────────────────────────────────────────────
    df = df.sort_values(["date", "geo", "housing_type"]).reset_index(drop=True)

    logger.info(
        f"Clean data: {len(df):,} rows | "
        f"{df['date'].min():%Y-%m} to {df['date'].max():%Y-%m} | "
        f"{df['geo'].nunique()} geographies"
    )
    return df


def extract_housing_starts() -> pd.DataFrame:
    """
    Full extraction pipeline for CMHC Housing Starts.
    Downloads → unzips → cleans → validates → saves processed CSV → returns DataFrame.
    """
    logger.info("=" * 60)
    logger.info("EXTRACTING: CMHC — Housing Starts (via Stats Canada)")
    logger.info("=" * 60)

    zip_path = _download_zip(CMHC_STARTS_URL, CMHC_STARTS_RAW)
    raw_df = _unzip_csv(zip_path)
    clean_df = _clean_housing_starts(raw_df)

    # Validate data quality
    errors = validate_housing_starts(clean_df)
    if errors:
        logger.warning("Data validation warnings:")
        for error in errors:
            logger.warning(f"  - {error}")

    # Save
    clean_df.to_csv(CMHC_STARTS_PROCESSED, index=False)
    logger.info(f"Saved → {CMHC_STARTS_PROCESSED}")

    return clean_df


# ── Run standalone ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    df = extract_housing_starts()
    print(f"\nSample output:\n{df.head(10).to_string(index=False)}")
    print(f"\nHousing types: {df['housing_type'].unique().tolist()}")
