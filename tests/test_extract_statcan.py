"""Tests for Statistics Canada NHPI extractor."""
import pandas as pd
import pytest
from extractors.extract_statcan import _clean_nhpi


class TestCleanNHPI:
    """Test suite for the _clean_nhpi function."""
    
    def test_basic_structure(self):
        """Test that cleaning produces expected columns."""
        raw_df = pd.DataFrame({
            'REF_DATE': ['2024-01', '2024-02'],
            'GEO': ['Canada', 'Canada'],
            'DGUID': ['001', '001'],
            'New housing price indexes': ['Total (house and land)', 'Total (house and land)'],
            'VALUE': [120.5, 121.0],
        })
        
        clean_df = _clean_nhpi(raw_df)
        
        # Check columns exist
        expected_cols = ['date', 'geo', 'geo_code', 'nhpi_type', 'index_value']
        assert list(clean_df.columns) == expected_cols
        
        # Check types (pandas 2.0+ uses datetime64[us], older uses datetime64[ns])
        assert clean_df['date'].dtype.kind == 'M'
        assert clean_df['index_value'].dtype == 'float64'
        assert clean_df['geo'].dtype == 'object'
    
    def test_drops_null_values(self):
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
    
    def test_date_parsing(self):
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
    
    def test_sorting(self):
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
    
    def test_preserves_all_nhpi_types(self):
        """Test that all NHPI type categories are preserved."""
        raw_df = pd.DataFrame({
            'REF_DATE': ['2024-01'] * 3,
            'GEO': ['Canada'] * 3,
            'DGUID': ['001'] * 3,
            'New housing price indexes': [
                'Total (house and land)',
                'House only',
                'Land only'
            ],
            'VALUE': [120.0, 115.0, 105.0],
        })
        
        clean_df = _clean_nhpi(raw_df)
        
        assert len(clean_df) == 3
        assert set(clean_df['nhpi_type']) == {
            'Total (house and land)',
            'House only',
            'Land only'
        }
    
    def test_handles_empty_dataframe(self):
        """Test behavior with empty input."""
        raw_df = pd.DataFrame({
            'REF_DATE': [],
            'GEO': [],
            'DGUID': [],
            'New housing price indexes': [],
            'VALUE': [],
        })
        
        clean_df = _clean_nhpi(raw_df)
        
        assert len(clean_df) == 0
        assert list(clean_df.columns) == ['date', 'geo', 'geo_code', 'nhpi_type', 'index_value']
    
    def test_multiple_geographies(self):
        """Test that multiple geographies are handled correctly."""
        raw_df = pd.DataFrame({
            'REF_DATE': ['2024-01'] * 4,
            'GEO': ['Canada', 'Toronto, Ontario', 'Vancouver, British Columbia', 'Montreal, Quebec'],
            'DGUID': ['001', '002', '003', '004'],
            'New housing price indexes': ['Total (house and land)'] * 4,
            'VALUE': [120.0, 135.0, 145.0, 125.0],
        })
        
        clean_df = _clean_nhpi(raw_df)
        
        assert len(clean_df) == 4
        assert clean_df['geo'].nunique() == 4
        assert 'Canada' in clean_df['geo'].values
        assert 'Toronto, Ontario' in clean_df['geo'].values


class TestNHPIIntegration:
    """Integration tests for full NHPI extraction pipeline."""
    
    @pytest.mark.slow
    def test_sample_data_structure(self):
        """Test that sample processed data has expected structure."""
        # This test requires the processed CSV to exist
        # Run it only if the file exists
        import os
        from config import STATCAN_NHPI_PROCESSED
        
        if not os.path.exists(STATCAN_NHPI_PROCESSED):
            pytest.skip("Processed NHPI file not found")
        
        df = pd.read_csv(STATCAN_NHPI_PROCESSED, parse_dates=['date'])
        
        # Check basic structure
        assert len(df) > 0
        assert set(df.columns) == {'date', 'geo', 'geo_code', 'nhpi_type', 'index_value'}
        
        # Check data quality
        assert df['date'].notna().all()
        assert df['index_value'].notna().all()
        assert (df['index_value'] > 0).all()
        
        # Check expected geographies
        assert 'Canada' in df['geo'].values
