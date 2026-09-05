"""Pure transformations for dashboard charts; no Streamlit side effects."""

import pandas as pd

from quality import DEFAULT_MAX_AGE_DAYS, FRESHNESS_THRESHOLDS


def price_volatility(frame):
    """Compute a separate 12-observation standard deviation per NHPI series."""
    result = frame.sort_values(['nhpi_type', 'full_date']).copy()
    result['rolling_std'] = result.groupby('nhpi_type')['index_value'].transform(
        lambda values: values.rolling(12, min_periods=12).std()
    )
    return result


def quarterly_starts_metrics(frame, start_year):
    """Match the same quarter last year before applying the display filter.

    Reindexing makes missing quarters explicit: neither YoY nor a full-year
    average silently substitutes an older observation for a missing quarter.
    """
    result = frame.copy()
    result['full_date'] = pd.to_datetime(result['full_date'])
    quarters = result['full_date'].dt.to_period('Q')
    ambiguous = result.assign(quarter=quarters).duplicated(['housing_type', 'quarter'], keep=False)
    excluded = int(ambiguous.sum())
    result = result.loc[~ambiguous].copy()
    result['yoy_change_pct'] = float('nan')
    result['rolling_12m_avg'] = float('nan')
    for _, group in result.groupby('housing_type'):
        periods = group['full_date'].dt.to_period('Q')
        values = pd.Series(group['starts_count'].to_numpy(), index=periods)
        values = values.reindex(pd.period_range(periods.min(), periods.max(), freq='Q'))
        previous = values.shift(4).replace(0, float('nan'))
        yoy = (values - previous) / previous * 100
        average = values.rolling(4, min_periods=4).mean()
        result.loc[group.index, 'yoy_change_pct'] = yoy.reindex(periods).to_numpy()
        result.loc[group.index, 'rolling_12m_avg'] = average.reindex(periods).to_numpy()
    result = result[result['full_date'].dt.year >= start_year].sort_values('full_date')
    result.attrs['excluded_ambiguous_rows'] = excluded
    return result


def freshness_label(source, latest, today=None):
    """Use the pipeline's publication-specific thresholds and handle no data."""
    if pd.isna(latest):
        return f'🔴 **{source}**: No data'
    latest = pd.Timestamp(latest)
    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    age = (today - latest.normalize()).days
    threshold = FRESHNESS_THRESHOLDS.get(source, DEFAULT_MAX_AGE_DAYS)
    icon = '🟢' if age <= threshold else '🔴'
    return (f"{icon} **{source}**: {latest.strftime('%b %Y')} "
            f'_(age: {age}d; limit: {threshold}d)_')
