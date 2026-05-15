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
    
    if (df['overnight_target'] < 0).any():
        errors.append("Found negative overnight target rates")
    
    # Check reasonable range (0-20%)
    if df['bank_rate'].max() > 20:
        errors.append(f"Suspiciously high rate: {df['bank_rate'].max()}")
    
    # Overnight target should be less than or equal to bank rate
    rate_mismatch = df[df['overnight_target'] > df['bank_rate']]
    if len(rate_mismatch) > 0:
        errors.append(f"Found {len(rate_mismatch)} rows where overnight > bank rate")
    
    return errors


def validate_housing_starts(df: pd.DataFrame) -> List[str]:
    """Validate housing starts data."""
    errors = []
    
    # Starts count should be non-negative
    if (df['starts_count'] < 0).any():
        negative_count = (df['starts_count'] < 0).sum()
        errors.append(f"Found {negative_count} negative starts counts")
    
    # Check for reasonable maximum (e.g., < 1 million per observation)
    max_starts = df['starts_count'].max()
    if max_starts > 1_000_000:
        errors.append(f"Suspiciously high starts count: {max_starts:,.0f}")
    
    # Canada should be present
    if 'Canada' not in df['geo'].values:
        errors.append("Missing national (Canada) data")
    
    return errors
