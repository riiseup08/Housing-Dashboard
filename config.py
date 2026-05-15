"""
Configuration for the Canadian Housing Affordability Data Pipeline.
All data source URLs, file paths, and settings in one place.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# ── Environment ─────────────────────────────────────────────
ENV = os.getenv('PIPELINE_ENV', 'development')

# ── Project Paths ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent

# Allow environment override
DATA_RAW = Path(os.getenv('DATA_RAW', PROJECT_ROOT / "data" / "raw"))
DATA_PROCESSED = Path(os.getenv('DATA_PROCESSED', PROJECT_ROOT / "data" / "processed"))
DB_PATH = Path(os.getenv('DB_PATH', PROJECT_ROOT / "data" / "housing.duckdb"))
LOG_DIR = Path(os.getenv('LOG_DIR', PROJECT_ROOT / "logs"))

# Ensure directories exist
DATA_RAW.mkdir(parents=True, exist_ok=True)
DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Statistics Canada ──────────────────────────────────────────
# New Housing Price Index (NHPI) — Table 18-10-0205
# Monthly index (base 201612=100) for 27 CMAs + national
STATCAN_NHPI_URL = (
    "https://www150.statcan.gc.ca/n1/tbl/csv/18100205-eng.zip"
)
STATCAN_NHPI_RAW = DATA_RAW / "18100205-eng.zip"
STATCAN_NHPI_CSV = DATA_RAW / "18100205.csv"
STATCAN_NHPI_PROCESSED = DATA_PROCESSED / "nhpi_clean.csv"

# ── Bank of Canada ─────────────────────────────────────────────
# Valet API — no API key required
# Series: V39079 = Bank Rate (target overnight rate upper bound)
# Series: V39078 = Target overnight rate
BOC_VALET_BASE = "https://www.bankofcanada.ca/valet"
BOC_SERIES = {
    "bank_rate": "V39079",
    "overnight_target": "V39078",
}
BOC_START_DATE = "2000-01-01"
BOC_PROCESSED = DATA_PROCESSED / "boc_rates_clean.csv"

# ── Network Timeouts ───────────────────────────────────────────
DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', '120'))
API_TIMEOUT = int(os.getenv('API_TIMEOUT', '60'))

# ── CMHC ───────────────────────────────────────────────────────
# Housing starts from the CMHC data portal
# Table: Housing Starts — Canada, Provinces, CMAs
CMHC_STARTS_URL = (
    "https://www150.statcan.gc.ca/n1/tbl/csv/34100135-eng.zip"
)
CMHC_STARTS_RAW = DATA_RAW / "34100135-eng.zip"
CMHC_STARTS_CSV = DATA_RAW / "34100135.csv"
CMHC_STARTS_PROCESSED = DATA_PROCESSED / "housing_starts_clean.csv"

# ── Logging ────────────────────────────────────────────────────
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Validation Thresholds ──────────────────────────────────────
VALIDATION_MIN_ROWS = int(os.getenv('VALIDATION_MIN_ROWS', '100'))
VALIDATION_MAX_NULL_PCT = float(os.getenv('VALIDATION_MAX_NULL_PCT', '0.30'))
