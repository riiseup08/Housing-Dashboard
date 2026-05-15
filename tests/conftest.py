"""Pytest configuration and shared fixtures."""
import pandas as pd
import pytest


@pytest.fixture
def sample_nhpi_raw_data():
    """Sample raw NHPI data from Statistics Canada format."""
    return pd.DataFrame({
        'REF_DATE': ['2024-01', '2024-02', '2024-03'],
        'GEO': ['Canada', 'Canada', 'Toronto, Ontario'],
        'DGUID': ['001', '001', '002'],
        'New housing price indexes': ['Total (house and land)'] * 3,
        'VALUE': [120.0, 121.5, 135.0],
        'UOM': ['Index'] * 3,
        'UOM_ID': [1] * 3,
        'SCALAR_FACTOR': ['units'] * 3,
        'SCALAR_ID': [0] * 3,
        'VECTOR': ['v123', 'v123', 'v124'],
        'COORDINATE': [1.0, 1.0, 1.0],
        'STATUS': ['', '', ''],
        'SYMBOL': ['', '', ''],
        'TERMINATED': ['', '', ''],
        'DECIMALS': [1, 1, 1],
    })


@pytest.fixture
def sample_nhpi_clean_data():
    """Sample cleaned NHPI data."""
    return pd.DataFrame({
        'date': pd.to_datetime(['2024-01-01', '2024-02-01', '2024-03-01']),
        'geo': ['Canada', 'Canada', 'Toronto, Ontario'],
        'geo_code': ['001', '001', '002'],
        'nhpi_type': ['Total (house and land)'] * 3,
        'index_value': [120.0, 121.5, 135.0],
    })


@pytest.fixture
def sample_boc_raw_data():
    """Sample Bank of Canada rate data from Valet API format."""
    return {
        'observations': [
            {'d': '2024-01-01', 'V39079': {'v': '5.00'}, 'V39078': {'v': '4.75'}},
            {'d': '2024-01-02', 'V39079': {'v': '5.00'}, 'V39078': {'v': '4.75'}},
            {'d': '2024-01-03', 'V39079': {'v': '4.75'}, 'V39078': {'v': '4.50'}},
        ]
    }


@pytest.fixture
def sample_boc_clean_data():
    """Sample cleaned Bank of Canada rate data."""
    return pd.DataFrame({
        'date': pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-03']),
        'bank_rate': [5.0, 5.0, 4.75],
        'overnight_target': [4.75, 4.75, 4.50],
    })


@pytest.fixture
def sample_housing_starts_raw_data():
    """Sample raw housing starts data from CMHC format."""
    return pd.DataFrame({
        'REF_DATE': ['2024-01', '2024-02', '2024-03'],
        'GEO': ['Canada', 'Canada', 'Ontario'],
        'DGUID': ['001', '001', '002'],
        'Type of unit': ['All types', 'All types', 'Single'],
        'VALUE': [25000.0, 26500.0, 8000.0],
        'UOM': ['Number'] * 3,
        'STATUS': ['', '', ''],
    })


@pytest.fixture
def sample_housing_starts_clean_data():
    """Sample cleaned housing starts data."""
    return pd.DataFrame({
        'date': pd.to_datetime(['2024-01-01', '2024-02-01', '2024-03-01']),
        'geo': ['Canada', 'Canada', 'Ontario'],
        'geo_code': ['001', '001', '002'],
        'housing_type': ['All types', 'All types', 'Single'],
        'starts_count': [25000.0, 26500.0, 8000.0],
    })


# Pytest configuration
def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
