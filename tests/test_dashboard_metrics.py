import pandas as pd
import pytest

from dashboard_metrics import freshness_label, price_volatility, quarterly_starts_metrics


def starts(values, dates=None):
    return pd.DataFrame({
        'full_date': pd.date_range('2023-01-01', periods=len(values), freq='QS') if dates is None else pd.to_datetime(dates),
        'housing_type': ['Total units'] * len(values),
        'starts_count': values,
    })


def test_quarterly_metrics_keep_prior_year_before_display_filter():
    result = quarterly_starts_metrics(starts([100, 200, 300, 400, 150]), 2024)
    assert len(result) == 1
    assert result.iloc[0].yoy_change_pct == 50
    assert result.iloc[0].rolling_12m_avg == 262.5


def test_missing_quarter_is_not_replaced_by_older_observation():
    frame = starts([100, 200, 400, 150, 250, 350],
                   ['2023-01-01', '2023-04-01', '2023-10-01',
                    '2024-01-01', '2024-04-01', '2024-07-01'])
    result = quarterly_starts_metrics(frame, 2024)
    assert result.iloc[0].yoy_change_pct == 50
    assert pd.isna(result.iloc[0].rolling_12m_avg)
    assert pd.isna(result.iloc[-1].yoy_change_pct)
    assert result.iloc[-1].rolling_12m_avg == 287.5


def test_zero_baseline_and_duplicate_quarters():
    result = quarterly_starts_metrics(starts([0, 1, 2, 3, 4]), 2024)
    assert pd.isna(result.iloc[0].yoy_change_pct)
    frame = starts([1, 2], ['2024-01-01', '2024-01-01'])
    result = quarterly_starts_metrics(frame, 2024)
    assert result.empty
    assert result.attrs['excluded_ambiguous_rows'] == 2


def test_volatility_is_sorted_and_keeps_series_separate():
    frame = pd.DataFrame({
        'full_date': list(pd.date_range('2023-01-01', periods=12, freq='MS')) * 2,
        'nhpi_type': ['House'] * 12 + ['Land'] * 12,
        'index_value': list(range(12)) + [100] * 12,
    }).sample(frac=1, random_state=1)
    result = price_volatility(frame).dropna(subset=['rolling_std'])
    assert len(result) == 2
    assert result.set_index('nhpi_type').loc['Land', 'rolling_std'] == 0
    assert result.set_index('nhpi_type').loc['House', 'rolling_std'] == pytest.approx(pd.Series(range(12)).std())
    assert 'rolling_std' not in frame


def test_empty_metrics():
    assert quarterly_starts_metrics(starts([]), 2024).empty


def test_freshness_respects_source_cadence_and_missing_data():
    assert freshness_label('Housing starts', '2026-01-01', '2026-07-01').startswith('🟢')
    assert freshness_label('NHPI', '2026-01-01', '2026-07-01').startswith('🔴')
    assert 'No data' in freshness_label('NHPI', None)
    assert freshness_label('NHPI', '2026-01-01', '2026-04-01').startswith('🟢')
