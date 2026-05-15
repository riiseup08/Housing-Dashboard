# 🚀 Immediate Action Items (Priority Order)

Based on the comprehensive audit, here are the **most critical fixes** to implement right now:

---

## 1. Add Retry Logic to HTTP Requests (30 minutes)

**File:** `extractors/utils.py` (new file)

```python
"""Shared utilities for all extractors."""
import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def get_session_with_retries(
    total_retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: tuple = (429, 500, 502, 503, 504)
) -> requests.Session:
    """
    Create a requests session with automatic retry logic.
    
    Args:
        total_retries: Number of retry attempts
        backoff_factor: Exponential backoff multiplier (1.0 = 1s, 2s, 4s...)
        status_forcelist: HTTP codes that trigger retries
        
    Returns:
        Configured requests.Session object
    """
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_status=False,  # Let us handle errors
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def download_with_retry(url: str, timeout: int = 120) -> bytes:
    """
    Download a file with automatic retries on failure.
    
    Args:
        url: URL to download
        timeout: Request timeout in seconds
        
    Returns:
        Downloaded content as bytes
        
    Raises:
        requests.RequestException: If download fails after all retries
    """
    session = get_session_with_retries()
    logger.info(f"Downloading {url}")
    
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        logger.info(f"Downloaded {len(resp.content) / 1e6:.1f} MB")
        return resp.content
    except requests.Timeout:
        logger.error(f"Timeout downloading {url} after {timeout}s")
        raise
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        raise
```

**Then update all extractors to use it:**

```python
# extract_statcan.py
from .utils import download_with_retry

def _download_zip(url: str, dest: Path) -> Path:
    if dest.exists():
        logger.info(f"Using cached file: {dest.name}")
        return dest
    
    content = download_with_retry(url, timeout=120)
    dest.write_bytes(content)
    logger.info(f"Saved {dest.name}")
    return dest
```

---

## 2. Fix Error Handling in Pipeline (20 minutes)

**File:** `run_pipeline.py:95`

Replace:
```python
        except Exception as e:
            elapsed = time.time() - start
            results[name] = {"status": "failed", "error": str(e), "time": elapsed}
            logger.error(f"FAILED {name}: {e}", exc_info=True)
```

With:
```python
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
```

---

## 3. Create Basic Test Structure (45 minutes)

### Install test dependencies:

```bash
pip install pytest pytest-cov
```

### Update `requirements.txt`:

```
pandas>=2.0
requests>=2.31
duckdb>=0.10
streamlit>=1.30
plotly>=5.18
python-dotenv>=1.0  # For environment variables

# Development dependencies (or create requirements-dev.txt)
pytest>=8.0
pytest-cov>=5.0
```

### Create `tests/test_extract_statcan.py`:

```python
"""Tests for Statistics Canada NHPI extractor."""
import pandas as pd
import pytest
from extractors.extract_statcan import _clean_nhpi


def test_clean_nhpi_basic_structure():
    """Test that cleaning produces expected columns."""
    raw_df = pd.DataFrame({
        'REF_DATE': ['2024-01', '2024-02'],
        'GEO': ['Canada', 'Canada'],
        'DGUID': ['001', '001'],
        'New housing price indexes': ['Total (house and land)', 'Total (house and land)'],
        'VALUE': [120.5, 121.0],
    })
    
    clean_df = _clean_nhpi(raw_df)
    
    # Check columns
    expected_cols = ['date', 'geo', 'geo_code', 'nhpi_type', 'index_value']
    assert list(clean_df.columns) == expected_cols
    
    # Check types
    assert clean_df['date'].dtype == 'datetime64[ns]'
    assert clean_df['index_value'].dtype == 'float64'


def test_clean_nhpi_drops_null_values():
    """Test that rows with null index values are removed."""
    raw_df = pd.DataFrame({
        'REF_DATE': ['2024-01', '2024-02', '2024-03'],
        'GEO': ['Canada', 'Canada', 'Canada'],
        'DGUID': ['001', '001', '001'],
        'New housing price indexes': ['Total (house and land)'] * 3,
        'VALUE': [120.5, None, 122.0],
    })
    
    clean_df = _clean_nhpi(raw_df)
    
    assert len(clean_df) == 2
    assert clean_df['index_value'].notna().all()


def test_clean_nhpi_date_parsing():
    """Test that dates are parsed correctly from YYYY-MM format."""
    raw_df = pd.DataFrame({
        'REF_DATE': ['2024-01'],
        'GEO': ['Canada'],
        'DGUID': ['001'],
        'New housing price indexes': ['Total (house and land)'],
        'VALUE': [120.5],
    })
    
    clean_df = _clean_nhpi(raw_df)
    
    expected_date = pd.Timestamp('2024-01-01')
    assert clean_df['date'].iloc[0] == expected_date


def test_clean_nhpi_sorting():
    """Test that output is sorted correctly."""
    raw_df = pd.DataFrame({
        'REF_DATE': ['2024-02', '2024-01', '2024-03'],
        'GEO': ['Toronto, Ontario', 'Canada', 'Toronto, Ontario'],
        'DGUID': ['002', '001', '002'],
        'New housing price indexes': ['Total (house and land)'] * 3,
        'VALUE': [130.0, 120.0, 131.0],
    })
    
    clean_df = _clean_nhpi(raw_df)
    
    # Should be sorted by date, then geo
    assert clean_df['date'].is_monotonic_increasing
```

### Create `tests/conftest.py`:

```python
"""Pytest configuration and shared fixtures."""
import pytest
import pandas as pd


@pytest.fixture
def sample_nhpi_raw_data():
    """Sample raw NHPI data for testing."""
    return pd.DataFrame({
        'REF_DATE': ['2024-01', '2024-02', '2024-03'],
        'GEO': ['Canada', 'Canada', 'Toronto, Ontario'],
        'DGUID': ['001', '001', '002'],
        'New housing price indexes': ['Total (house and land)'] * 3,
        'VALUE': [120.0, 121.5, 135.0],
    })


@pytest.fixture
def sample_boc_data():
    """Sample Bank of Canada rate data for testing."""
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=3),
        'bank_rate': [5.0, 5.0, 4.75],
        'overnight_target': [4.75, 4.75, 4.50],
    })
```

### Run tests:

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=extractors --cov-report=html

# Run specific test file
pytest tests/test_extract_statcan.py -v
```

---

## 4. Pin Dependency Versions (10 minutes)

Create `requirements-lock.txt`:

```bash
pip freeze > requirements-lock.txt
```

Or manually create with specific versions:

```
# requirements-lock.txt
pandas==2.2.2
requests==2.31.0
urllib3==2.2.1
duckdb==0.10.2
streamlit==1.30.0
plotly==5.18.0
python-dotenv==1.0.1
```

---

## 5. Add Input Validation (30 minutes)

**File:** `extractors/validators.py` (new file)

```python
"""Data validation utilities."""
import logging
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)


def validate_schema(df: pd.DataFrame, expected_columns: dict[str, str]) -> List[str]:
    """
    Validate DataFrame schema against expected structure.
    
    Args:
        df: DataFrame to validate
        expected_columns: Dict mapping column names to expected dtypes
        
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    # Check for missing columns
    missing = set(expected_columns.keys()) - set(df.columns)
    if missing:
        errors.append(f"Missing columns: {missing}")
    
    # Check data types
    for col, expected_dtype in expected_columns.items():
        if col in df.columns:
            actual_dtype = str(df[col].dtype)
            if not actual_dtype.startswith(expected_dtype):
                errors.append(f"Column '{col}' has type {actual_dtype}, expected {expected_dtype}")
    
    return errors


def validate_nhpi_data(df: pd.DataFrame) -> List[str]:
    """
    Validate cleaned NHPI data against business rules.
    
    Args:
        df: Cleaned NHPI DataFrame
        
    Returns:
        List of validation errors
    """
    errors = []
    
    # Index values should be positive
    if (df['index_value'] <= 0).any():
        negative_count = (df['index_value'] <= 0).sum()
        errors.append(f"Found {negative_count} non-positive index values")
    
    # Canada should be present
    if 'Canada' not in df['geo'].values:
        errors.append("Missing national (Canada) data")
    
    # Check for reasonable index range (50-300)
    max_index = df['index_value'].max()
    if max_index > 300:
        errors.append(f"Suspiciously high index value: {max_index}")
    
    min_index = df['index_value'].min()
    if min_index < 50:
        errors.append(f"Suspiciously low index value: {min_index}")
    
    # Check for date gaps
    df_sorted = df.sort_values('date')
    date_diff = df_sorted['date'].diff()
    large_gaps = date_diff[date_diff > pd.Timedelta(days=35)]
    if len(large_gaps) > 0:
        errors.append(f"Found {len(large_gaps)} gaps in monthly time series")
    
    return errors


def validate_boc_rates(df: pd.DataFrame) -> List[str]:
    """Validate Bank of Canada rate data."""
    errors = []
    
    # Rates should be non-negative
    if (df['bank_rate'] < 0).any():
        errors.append("Found negative bank rates")
    
    # Check reasonable range (0-20%)
    if df['bank_rate'].max() > 20:
        errors.append(f"Suspiciously high rate: {df['bank_rate'].max()}")
    
    # Overnight target should be less than bank rate
    rate_mismatch = df[df['overnight_target'] > df['bank_rate']]
    if len(rate_mismatch) > 0:
        errors.append(f"Found {len(rate_mismatch)} rows where overnight > bank rate")
    
    return errors
```

**Then add to extractors:**

```python
# In extract_statcan.py
from .validators import validate_nhpi_data

def extract_nhpi() -> pd.DataFrame:
    # ... existing code ...
    clean_df = _clean_nhpi(raw_df)
    
    # Validate before saving
    errors = validate_nhpi_data(clean_df)
    if errors:
        logger.warning("Data validation warnings:")
        for error in errors:
            logger.warning(f"  - {error}")
    
    clean_df.to_csv(STATCAN_NHPI_PROCESSED, index=False)
    return clean_df
```

---

## 6. Add Environment Configuration (20 minutes)

**File:** `.env.example` (new file)

```bash
# Environment Configuration

# Pipeline environment (development, staging, production)
PIPELINE_ENV=development

# Timeouts (seconds)
DOWNLOAD_TIMEOUT=120
API_TIMEOUT=60

# Data paths (optional overrides)
# DATA_RAW=/mnt/data/housing-pipeline/raw
# DATA_PROCESSED=/mnt/data/housing-pipeline/processed

# Logging
LOG_LEVEL=INFO
LOG_DIR=logs

# Validation settings
VALIDATION_MIN_ROWS=100
VALIDATION_MAX_NULL_PCT=0.30
```

**File:** `config.py` (updates)

```python
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── Environment ─────────────────────────────────────────────
ENV = os.getenv('PIPELINE_ENV', 'development')

# ── Project Paths ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent

# Allow environment override
DATA_RAW = Path(os.getenv('DATA_RAW', PROJECT_ROOT / "data" / "raw"))
DATA_PROCESSED = Path(os.getenv('DATA_PROCESSED', PROJECT_ROOT / "data" / "processed"))
LOG_DIR = Path(os.getenv('LOG_DIR', PROJECT_ROOT / "logs"))

# Create directories
DATA_RAW.mkdir(parents=True, exist_ok=True)
DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Timeouts ───────────────────────────────────────────────
DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', '120'))
API_TIMEOUT = int(os.getenv('API_TIMEOUT', '60'))

# ── Logging ────────────────────────────────────────────────
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Validation ─────────────────────────────────────────────
VALIDATION_MIN_ROWS = int(os.getenv('VALIDATION_MIN_ROWS', '100'))
VALIDATION_MAX_NULL_PCT = float(os.getenv('VALIDATION_MAX_NULL_PCT', '0.30'))
```

---

## 7. Add Command Validation (10 minutes)

**File:** `run_pipeline.py` (add after line 80)

```python
def run_pipeline(sources: list[str] | None = None):
    """Run the full extraction pipeline or a subset of sources."""
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
```

---

## Summary Checklist

- [ ] **1. Add retry logic** → Create `extractors/utils.py` with retry-enabled session
- [ ] **2. Fix error handling** → Update `run_pipeline.py` exception handling
- [ ] **3. Create tests** → Add pytest framework and basic test suite
- [ ] **4. Pin versions** → Create `requirements-lock.txt`
- [ ] **5. Add validation** → Create `extractors/validators.py` with business rules
- [ ] **6. Environment config** → Add `.env.example` and update `config.py`
- [ ] **7. Command validation** → Add source validation to `run_pipeline.py`

**Estimated Total Time:** 2-3 hours  
**Impact:** Transforms from prototype to production-ready code

---

## Quick Commands

```bash
# Install dev dependencies
pip install pytest pytest-cov python-dotenv

# Run tests
pytest -v

# Run with coverage
pytest --cov=extractors --cov-report=html

# Create environment file
cp .env.example .env

# Run pipeline with validation
python run_pipeline.py
```

---

See `AUDIT_REPORT.md` for the complete analysis and long-term roadmap.
