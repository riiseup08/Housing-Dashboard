"""
Pipeline Orchestrator — Canadian Housing Affordability Data Pipeline

Runs all three extraction jobs sequentially, validates outputs,
and prints a summary report.

Usage:
    python run_pipeline.py              # Run all extractors
    python run_pipeline.py --source boc # Run a single extractor
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from config import (
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    LOG_LEVEL,
    LOG_DIR,
    DATA_PROCESSED,
    VALIDATION_MIN_ROWS,
    VALIDATION_MAX_NULL_PCT,
)
from extractors import extract_nhpi, extract_boc_rates, extract_housing_starts

# ── Setup logging ──────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "pipeline.log"),
    ],
)
logger = logging.getLogger("pipeline")


def validate_output(name: str, df, min_rows: int = None) -> bool:
    """Basic data quality checks on extracted data."""
    if min_rows is None:
        min_rows = VALIDATION_MIN_ROWS
    
    checks_passed = True

    if df is None or len(df) == 0:
        logger.error(f"  ✗ {name}: Empty DataFrame!")
        return False

    if len(df) < min_rows:
        logger.warning(f"  ⚠ {name}: Only {len(df)} rows (expected ≥{min_rows})")
        checks_passed = False

    # Check for excessive nulls in any column
    null_pct = df.isnull().mean()
    high_null_cols = null_pct[null_pct > VALIDATION_MAX_NULL_PCT]
    if len(high_null_cols) > 0:
        for col, pct in high_null_cols.items():
            logger.warning(f"  ⚠ {name}: Column '{col}' is {pct:.0%} null")
        checks_passed = False

    # Check for duplicate rows
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        logger.warning(f"  ⚠ {name}: {dup_count:,} duplicate rows")

    if checks_passed:
        logger.info(f"  ✓ {name}: {len(df):,} rows — all checks passed")

    return checks_passed


def run_pipeline(sources: list[str] | None = None) -> dict:
    """Run the full extraction pipeline or a subset of sources.

    Returns the per-source results dict so callers (CI / --strict) can decide
    whether to fail.
    """
    logger.info("=" * 60)
    logger.info("CANADIAN HOUSING AFFORDABILITY DATA PIPELINE")
    logger.info("=" * 60)

    extractors = {
        "statcan": ("Stats Canada NHPI", extract_nhpi),
        "boc": ("Bank of Canada Rates", extract_boc_rates),
        "cmhc": ("CMHC Housing Starts", extract_housing_starts),
    }

    # Validate source arguments
    if sources:
        invalid = set(sources) - set(extractors.keys())
        if invalid:
            logger.error(f"Invalid sources: {invalid}")
            logger.info(f"Valid sources: {list(extractors.keys())}")
            sys.exit(1)
        extractors = {k: v for k, v in extractors.items() if k in sources}
        logger.info(f"Running selected sources: {list(extractors.keys())}")

    results = {}
    total_start = time.time()

    for key, (name, func) in extractors.items():
        start = time.time()
        try:
            df = func()
            elapsed = time.time() - start
            results[name] = {
                "status": "success",
                "rows": len(df),
                "time": elapsed,
                "df": df,
            }
            logger.info(f"Completed {name} in {elapsed:.1f}s")
        except requests.RequestException as e:
            elapsed = time.time() - start
            results[name] = {
                "status": "network_error",
                "error": str(e),
                "time": elapsed,
                "recoverable": True,
            }
            logger.error(f"Network error in {name}: {e}")
        except pd.errors.ParserError as e:
            elapsed = time.time() - start
            results[name] = {
                "status": "parse_error",
                "error": str(e),
                "time": elapsed,
                "recoverable": False,
            }
            logger.error(f"Data parsing error in {name}: {e}")
        except Exception as e:
            elapsed = time.time() - start
            results[name] = {
                "status": "failed",
                "error": str(e),
                "time": elapsed,
                "recoverable": False,
            }
            logger.critical(f"Unexpected error in {name}: {e}", exc_info=True)

    # ── Validation ─────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("DATA VALIDATION")
    logger.info("=" * 60)
    for name, result in results.items():
        if result["status"] == "success":
            result["validation_passed"] = validate_output(name, result["df"])
        else:
            status = result["status"].replace("_", " ").title()
            logger.error(f"  ✗ {name}: {status} — {result.get('error', 'Unknown error')}")

    # ── Summary ────────────────────────────────────────────────
    total_elapsed = time.time() - total_start
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 60)
    for name, result in results.items():
        status = result["status"].upper()
        time_str = f"{result['time']:.1f}s"
        if result["status"] == "success":
            logger.info(f"  {status:8} | {time_str:>6} | {result['rows']:>10,} rows | {name}")
        else:
            logger.info(f"  {status:8} | {time_str:>6} | {'—':>10} rows | {name}")

    logger.info(f"\nTotal time: {total_elapsed:.1f}s")
    logger.info(f"Output dir: {DATA_PROCESSED}")

    # List output files
    logger.info("\nGenerated files:")
    for f in sorted(DATA_PROCESSED.glob("*.csv")):
        size_kb = f.stat().st_size / 1024
        logger.info(f"  {f.name:30} {size_kb:>8.1f} KB")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the housing data pipeline")
    parser.add_argument(
        "--source",
        choices=["statcan", "boc", "cmhc"],
        nargs="+",
        help="Run specific source(s) only",
    )
    parser.add_argument(
        "--load-db",
        action="store_true",
        help="Load data into DuckDB after extraction",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero on any extractor failure or stale data. "
            "Intended for CI; local runs stay lenient by default."
        ),
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=45,
        help="Strict mode: max allowed age of latest fact-table date.",
    )
    args = parser.parse_args()

    # Run extraction pipeline
    results = run_pipeline(args.source)

    # Optionally load to DuckDB
    db_loaded = False
    if args.load_db:
        try:
            from load_duckdb import load_to_duckdb
            logger.info("\n")
            load_to_duckdb()
            db_loaded = True
        except Exception as e:
            logger.error(f"Failed to load data to DuckDB: {e}", exc_info=True)

    # Strict gating for CI: collect any reasons to fail, log them all, then exit.
    if args.strict:
        errors: list[str] = []

        for name, result in results.items():
            if result["status"] != "success":
                errors.append(
                    f"{name}: extractor status={result['status']} "
                    f"({result.get('error', 'unknown error')})"
                )
            elif not result.get("validation_passed", False):
                errors.append(f"{name}: output failed data validation")

        if args.load_db:
            if not db_loaded:
                errors.append("DuckDB load step failed (see traceback above)")
            else:
                from quality import check_freshness
                logger.info("\n" + "=" * 60)
                logger.info("FRESHNESS CHECK")
                logger.info("=" * 60)
                errors.extend(check_freshness(max_age_days=args.max_age_days))

        if errors:
            logger.error("\n" + "=" * 60)
            logger.error("STRICT MODE: %d issue(s) — failing", len(errors))
            logger.error("=" * 60)
            for e in errors:
                logger.error("  ✗ %s", e)
            sys.exit(1)
        logger.info("\n✓ Strict mode: all checks passed")
