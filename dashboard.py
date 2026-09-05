"""
Canadian Housing Market Conditions Dashboard
==========================================
Interactive Streamlit dashboard for exploring housing prices, interest rates, and construction activity.

Usage:
    streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text

# Load environment variables BEFORE importing config
from dotenv import load_dotenv
load_dotenv()  # Reload .env file explicitly

from config import DB_PATH, DB_TYPE, DB_CONNECTION_STRING
from dashboard_metrics import price_volatility, quarterly_starts_metrics, freshness_label


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Canadian Housing Market Conditions Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# AGENT CHART HELPER
# ============================================================
def _render_agent_chart(df: pd.DataFrame) -> None:
    """Auto-pick a Plotly chart based on the columns the agent returned.

    Heuristic:
      - If first column is datetime-like → line chart, with optional color by
        a second categorical column.
      - Else if a single categorical + single numeric → bar chart.
      - Else if 2+ numerics with a categorical → grouped bar.
      - Fallback: just show the table (caller handles that).
    """
    if df is None or df.empty or len(df.columns) < 2:
        st.dataframe(df, use_container_width=True)
        return

    df = df.copy()
    x_col = df.columns[0]

    # Try to coerce the first column to datetime when it looks date-ish.
    if df[x_col].dtype == object:
        try:
            coerced = pd.to_datetime(df[x_col], errors="raise")
            df[x_col] = coerced
        except Exception:
            pass

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = [c for c in df.columns if c != x_col and c not in numeric_cols]
    is_time = pd.api.types.is_datetime64_any_dtype(df[x_col])

    if is_time and numeric_cols:
        # If there's a categorical series column, plot one line per category
        # of the first numeric. Otherwise, plot every numeric column — and
        # split index-like vs percent-like onto dual axes when both are present.
        if cat_cols:
            y_col = numeric_cols[0]
            fig = px.line(df, x=x_col, y=y_col, color=cat_cols[0],
                          title=f"{y_col} over {x_col}")
            fig.update_layout(hovermode="x unified", height=450)
            st.plotly_chart(fig, use_container_width=True)
            return

        pct_cols = [c for c in numeric_cols if any(
            tok in c.lower() for tok in ("pct", "percent", "rate", "change")
        )]
        level_cols = [c for c in numeric_cols if c not in pct_cols]

        fig = go.Figure()
        for c in level_cols:
            fig.add_trace(go.Scatter(x=df[x_col], y=df[c], name=c, yaxis="y1"))
        for c in pct_cols:
            fig.add_trace(go.Scatter(x=df[x_col], y=df[c], name=c, yaxis="y2"))

        layout = dict(
            title=", ".join(numeric_cols) + f" over {x_col}",
            xaxis=dict(title=x_col),
            yaxis=dict(title=" / ".join(level_cols) if level_cols else None,
                       side="left"),
            hovermode="x unified",
            height=450,
        )
        if pct_cols and level_cols:
            layout["yaxis2"] = dict(
                title=" / ".join(pct_cols), side="right", overlaying="y",
                showgrid=False,
            )
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
        return

    if numeric_cols and not is_time:
        y_col = numeric_cols[0]
        # Top-N bar chart sorted desc
        plot_df = df.sort_values(y_col, ascending=False).head(30)
        color = cat_cols[0] if cat_cols else None
        fig = px.bar(plot_df, x=x_col, y=y_col, color=color,
                     title=f"{y_col} by {x_col}")
        fig.update_layout(height=450, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)
        return

    st.dataframe(df, use_container_width=True)


# ============================================================
# DATABASE CONNECTION
# ============================================================
@st.cache_resource
def get_connection():
    """Create a cached database connection (DuckDB or PostgreSQL)."""
    if DB_TYPE == 'duckdb':
        import duckdb
        if not Path(DB_PATH).exists():
            st.error(f"Database not found at {DB_PATH}. Run `python run_pipeline.py --load-db` first.")
            st.stop()
        # Return DuckDB connection for backward compatibility
        return duckdb.connect(str(DB_PATH), read_only=True)
    else:
        # PostgreSQL - return SQLAlchemy engine
        engine = create_engine(DB_CONNECTION_STRING)
        # Test connection
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception as e:
            st.error(f"Database connection failed: {e}")
            st.stop()


def execute_query(query, params=None):
    """Execute SQL query and return DataFrame (works with both DuckDB and PostgreSQL)."""
    conn = get_connection()
    
    if DB_TYPE == 'duckdb':
        # DuckDB connection
        if params:
            return conn.execute(query, params).fetchdf()
        else:
            return conn.execute(query).fetchdf()
    else:
        # PostgreSQL SQLAlchemy engine
        if params:
            # Convert positional parameters (?) to named parameters for SQLAlchemy
            # This is a simple conversion - may need adjustment for complex queries
            query_pg = query
            if '?' in query:
                # Replace ? with :param1, :param2, etc.
                param_dict = {}
                for i, param in enumerate(params, 1):
                    param_name = f'param{i}'
                    query_pg = query_pg.replace('?', f':{param_name}', 1)
                    param_dict[param_name] = param
                return pd.read_sql_query(text(query_pg), conn, params=param_dict)
            else:
                return pd.read_sql_query(text(query), conn, params=params)
        else:
            return pd.read_sql_query(text(query), conn)


conn = get_connection()


# ============================================================
# DATA LOADING FUNCTIONS
# ============================================================
@st.cache_data(ttl=3600)
def load_geographies():
    """Load all geographies from the database."""
    return execute_query("""
        SELECT DISTINCT geo_name, geo_type 
        FROM dim_geography 
        ORDER BY geo_type, geo_name
    """)


@st.cache_data(ttl=3600)
def load_housing_prices(geography='Canada', start_year=2015):
    """Load housing price data for a specific geography."""
    return execute_query("""
        SELECT
            d.full_date,
            d.year,
            d.month,
            d.month_name,
            hp.nhpi_type,
            hp.index_value,
            hp.yoy_change_pct,
            hp.mom_change_pct
        FROM fact_housing_prices hp
        JOIN dim_date d ON hp.date_key = d.date_key
        JOIN dim_geography g ON hp.geo_key = g.geo_key
        WHERE g.geo_name = ?
          AND d.year >= ?
          AND d.is_month_start = TRUE
        ORDER BY d.full_date, hp.nhpi_type
    """, [geography, start_year])


@st.cache_data(ttl=3600)
def load_interest_rates(start_year=2015):
    """Load Bank of Canada interest rates."""
    return execute_query("""
        SELECT
            d.full_date,
            d.year,
            d.month,
            ir.bank_rate,
            ir.overnight_target,
            ir.rate_change
        FROM fact_interest_rates ir
        JOIN dim_date d ON ir.date_key = d.date_key
        WHERE d.year >= ?
        ORDER BY d.full_date
    """, [start_year])


@st.cache_data(ttl=3600)
def load_housing_starts(geography='Canada', start_year=2015):
    """Load housing starts data."""
    frame = execute_query("""
        SELECT d.full_date, d.year, d.month, d.month_name,
               hs.housing_type, hs.starts_count
        FROM fact_housing_starts hs
        JOIN dim_date d ON hs.date_key = d.date_key
        JOIN dim_geography g ON hs.geo_key = g.geo_key
        WHERE g.geo_name = ? AND d.year >= ?
        ORDER BY d.full_date, hs.housing_type
    """, [geography, start_year - 1])
    return quarterly_starts_metrics(frame, start_year)


@st.cache_data(ttl=3600)
def load_comparative_prices(geographies, nhpi_type='Total (house and land)', start_year=2015):
    """Load housing prices for multiple geographies."""
    # Use a positional placeholder per geography so DuckDB does the quoting.
    placeholders = ", ".join("?" for _ in geographies)
    params = list(geographies) + [nhpi_type, start_year]
    return execute_query(f"""
        SELECT
            d.full_date,
            d.year,
            g.geo_name,
            hp.index_value,
            hp.yoy_change_pct
        FROM fact_housing_prices hp
        JOIN dim_date d ON hp.date_key = d.date_key
        JOIN dim_geography g ON hp.geo_key = g.geo_key
        WHERE g.geo_name IN ({placeholders})
          AND hp.nhpi_type = ?
          AND d.year >= ?
          AND d.is_month_start = TRUE
        ORDER BY g.geo_name, d.full_date
    """, params)


# Geographic coordinates for mapping
GEO_COORDINATES = {
    # Provinces
    'Alberta': {'lat': 53.9333, 'lon': -116.5765},
    'British Columbia': {'lat': 53.7267, 'lon': -127.6476},
    'Manitoba': {'lat': 53.7609, 'lon': -98.8139},
    'New Brunswick': {'lat': 46.5653, 'lon': -66.4619},
    'Newfoundland and Labrador': {'lat': 53.1355, 'lon': -57.6604},
    'Nova Scotia': {'lat': 44.6820, 'lon': -63.7443},
    'Ontario': {'lat': 51.2538, 'lon': -85.3232},
    'Prince Edward Island': {'lat': 46.5107, 'lon': -63.4168},
    'Quebec': {'lat': 52.9399, 'lon': -73.5491},
    'Saskatchewan': {'lat': 52.9399, 'lon': -106.4509},
    # Major CMAs
    'Toronto, Ontario': {'lat': 43.6532, 'lon': -79.3832},
    'Montréal, Quebec': {'lat': 45.5017, 'lon': -73.5673},
    'Vancouver, British Columbia': {'lat': 49.2827, 'lon': -123.1207},
    'Calgary, Alberta': {'lat': 51.0447, 'lon': -114.0719},
    'Edmonton, Alberta': {'lat': 53.5461, 'lon': -113.4938},
    'Ottawa-Gatineau, Ontario/Quebec': {'lat': 45.4215, 'lon': -75.6972},
    'Winnipeg, Manitoba': {'lat': 49.8951, 'lon': -97.1384},
    'Quebec, Quebec': {'lat': 46.8139, 'lon': -71.2080},
    'Hamilton, Ontario': {'lat': 43.2557, 'lon': -79.8711},
    'Kitchener-Cambridge-Waterloo, Ontario': {'lat': 43.4516, 'lon': -80.4925},
    'London, Ontario': {'lat': 42.9849, 'lon': -81.2453},
    'Victoria, British Columbia': {'lat': 48.4284, 'lon': -123.3656},
    'Halifax, Nova Scotia': {'lat': 44.6488, 'lon': -63.5752},
    'Oshawa, Ontario': {'lat': 43.8971, 'lon': -78.8658},
    'Windsor, Ontario': {'lat': 42.3149, 'lon': -83.0364},
    'Saskatoon, Saskatchewan': {'lat': 52.1332, 'lon': -106.6700},
    'Regina, Saskatchewan': {'lat': 50.4452, 'lon': -104.6189},
    'St. John\'s, Newfoundland and Labrador': {'lat': 47.5615, 'lon': -52.7126},
}


@st.cache_data(ttl=3600)
def load_latest_geographic_data():
    """Load latest housing data for all geographies with coordinates."""
    df = execute_query("""
        WITH latest_data AS (
            SELECT 
                g.geo_name,
                g.geo_type,
                hp.index_value,
                hp.yoy_change_pct,
                d.full_date,
                ROW_NUMBER() OVER (PARTITION BY g.geo_name ORDER BY d.full_date DESC) as rn
            FROM fact_housing_prices hp
            JOIN dim_date d ON hp.date_key = d.date_key
            JOIN dim_geography g ON hp.geo_key = g.geo_key
            WHERE hp.nhpi_type = 'Total (house and land)'
              AND d.is_month_start = TRUE
        )
        SELECT geo_name, geo_type, index_value, yoy_change_pct, full_date
        FROM latest_data
        WHERE rn = 1
    """)
    
    # Add coordinates
    df['lat'] = df['geo_name'].map(lambda x: GEO_COORDINATES.get(x, {}).get('lat'))
    df['lon'] = df['geo_name'].map(lambda x: GEO_COORDINATES.get(x, {}).get('lon'))
    
    return df[df['lat'].notna()]  # Filter out entries without coordinates


@st.cache_data(ttl=3600)
def load_latest_metrics():
    """Load latest metrics for the dashboard overview."""
    return execute_query("""
        WITH latest_date AS (
            SELECT MAX(d.full_date) as max_date
            FROM fact_housing_prices hp
            JOIN dim_date d ON hp.date_key = d.date_key
        )
        SELECT 
            (SELECT ROUND(CAST(index_value AS NUMERIC), 1)
             FROM fact_housing_prices hp
             JOIN dim_date d ON hp.date_key = d.date_key
             JOIN dim_geography g ON hp.geo_key = g.geo_key
             WHERE g.geo_name = 'Canada' 
               AND hp.nhpi_type = 'Total (house and land)'
               AND d.full_date = (SELECT max_date FROM latest_date)) as canada_nhpi,
            
            (SELECT ROUND(CAST(yoy_change_pct AS NUMERIC), 2)
             FROM fact_housing_prices hp
             JOIN dim_date d ON hp.date_key = d.date_key
             JOIN dim_geography g ON hp.geo_key = g.geo_key
             WHERE g.geo_name = 'Canada' 
               AND hp.nhpi_type = 'Total (house and land)'
               AND d.full_date = (SELECT max_date FROM latest_date)) as canada_yoy,
            
            (SELECT ROUND(CAST(bank_rate AS NUMERIC), 2)
             FROM fact_interest_rates ir
             JOIN dim_date d ON ir.date_key = d.date_key
             ORDER BY d.full_date DESC
             LIMIT 1) as latest_bank_rate,
            
            (SELECT max_date FROM latest_date) as data_date
    """)


# ============================================================
# DASHBOARD HEADER
# ============================================================
st.title("🏠 Canadian Housing Market Conditions Dashboard")
st.markdown(
    "**Price movement, financing conditions, and construction activity**  \n"
    "NHPI is a relative index, so this dashboard does not calculate "
    "price-to-income or mortgage-payment affordability."
)
st.markdown("---")


# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("Settings")

# Load geographies
geographies_df = load_geographies()
provinces = geographies_df[geographies_df['geo_type'] == 'Province']['geo_name'].tolist()
cmas = geographies_df[geographies_df['geo_type'] == 'CMA']['geo_name'].tolist()

# Page selection
page = st.sidebar.radio(
    "📍 Navigation",
    ["📊 Overview", "📈 Housing Prices", "💰 Interest Rates", "🏗️ Housing Starts", "🔍 Comparative Analysis", "🗺️ Geographic Map", "🤖 AI Market Agent"]
)

st.sidebar.markdown("---")

# Date range selector
st.sidebar.subheader("⏱️ Time Range")
current_year = datetime.now().year
start_year = st.sidebar.slider(
    "Start Year",
    min_value=2000,
    max_value=current_year,
    value=2000,
    step=1,
    help="Select the starting year for analysis. Housing prices & starts available from 2000. Interest rates from 2009."
)

# Show selected range
years_selected = current_year - start_year + 1
st.sidebar.info(f"📊 Analyzing **{years_selected} years** of data ({start_year}-{current_year})")

# Add data availability note
if start_year < 2009:
    st.sidebar.warning("⚠️ Interest rates data only available from 2009 onwards")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Data Freshness")


@st.cache_data(ttl=3600)
def _freshness():
    """Latest covered month per fact table + DB file mtime."""
    rows = execute_query("""
        SELECT 'NHPI' AS source, MAX(d.full_date) AS latest
          FROM fact_housing_prices f JOIN dim_date d ON f.date_key = d.date_key
        UNION ALL
        SELECT 'Interest rates', MAX(d.full_date)
          FROM fact_interest_rates f JOIN dim_date d ON f.date_key = d.date_key
        UNION ALL
        SELECT 'Housing starts', MAX(d.full_date)
          FROM fact_housing_starts f JOIN dim_date d ON f.date_key = d.date_key
    """)
    if DB_TYPE == 'duckdb':
        db_mtime = datetime.fromtimestamp(Path(DB_PATH).stat().st_mtime)
    else:
        db_mtime = None  # A query timestamp is not the database build time
    return rows, db_mtime


_fresh_rows, _db_mtime = _freshness()
for _, row in _fresh_rows.iterrows():
    st.sidebar.markdown(freshness_label(row['source'], row['latest']))
if _db_mtime is not None:
    st.sidebar.caption(f"DB file updated {_db_mtime.strftime('%Y-%m-%d %H:%M')}")

st.sidebar.markdown("---")
st.sidebar.markdown("### Data Sources")
st.sidebar.markdown("- **NHPI**: Statistics Canada Table 18-10-0205")
st.sidebar.markdown("- **Interest Rates**: Bank of Canada Valet API")
st.sidebar.markdown("- **Housing Starts**: Statistics Canada Table 34-10-0135")


# ============================================================
# PAGE: OVERVIEW
# ============================================================
if page == "📊 Overview":
    st.header("Key Metrics")
    
    # Add brief explanation
    st.markdown("""
    <div style='background-color: #f0f2f6; padding: 15px; border-radius: 5px; margin-bottom: 20px;'>
    <b>📌 Quick Guide:</b><br>
    • <b>NHPI</b> = New Housing Price Index (baseline 2016=100). Values above 100 = more expensive than 2016.<br>
    • <b>YoY</b> = Year-over-Year change. Positive = prices rising, Negative = prices falling.<br>
    • <b>Bank Rate</b> = Policy rate that affects mortgage costs. Higher rates = more expensive borrowing.
    </div>
    """, unsafe_allow_html=True)
    
    # Load latest metrics
    metrics = load_latest_metrics()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="🏠 Housing Price Index (Canada)",
            value=f"{metrics['canada_nhpi'].iloc[0]}",
            delta=f"{metrics['canada_yoy'].iloc[0]}% YoY",
            help="New Housing Price Index (2016=100). Annual change shows market direction.",
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            label="💰 Bank of Canada Rate",
            value=f"{metrics['latest_bank_rate'].iloc[0]}%",
            help="Current policy interest rate set by Bank of Canada. Higher rates = more expensive mortgages."
        )
    
    with col3:
        data_date = pd.to_datetime(metrics['data_date'].iloc[0])
        st.metric(
            label="📅 Latest Data",
            value=data_date.strftime("%b %Y"),
            help="Most recent month with available housing price data."
        )
    
    with col4:
        # Get housing starts for Canada in last 12 months
        recent_starts_df = execute_query("""
            WITH quarters AS (
                SELECT d.full_date, hs.starts_count
                FROM fact_housing_starts hs
                JOIN dim_date d ON hs.date_key = d.date_key
                JOIN dim_geography g ON hs.geo_key = g.geo_key
                WHERE g.geo_name = 'Canada' AND hs.housing_type = 'Total units'
            ), latest AS (SELECT MAX(full_date) AS last_date FROM quarters)
            SELECT CASE WHEN COUNT(*) = 4 AND COUNT(DISTINCT full_date) = 4
                        THEN SUM(starts_count) END AS total,
                   MAX(full_date) AS data_date
            FROM quarters, latest
            WHERE full_date > last_date - INTERVAL '12 months'
        """)
        recent_starts = recent_starts_df.iloc[0]['total']
        st.metric(
            label="🏗️ Housing Starts (4 quarters)",
            value=f"{int(recent_starts):,}" if pd.notna(recent_starts) else "N/A",
            help="Total units over the latest four reported quarters; components are not added to totals."
        )
        starts_date = recent_starts_df.iloc[0]['data_date']
        if pd.notna(starts_date):
            quarter = pd.Timestamp(starts_date).to_period('Q')
            st.caption(f"Through {quarter}")
    
    st.markdown("---")
    
    # Recent trends
    st.subheader("Trends in Selected Time Range")
    st.markdown("*Compare housing price movements and interest rate changes across major markets*")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Housing prices for major cities
        major_cities = ['Canada', 'Toronto, Ontario', 'Vancouver, British Columbia', 'Montréal, Quebec']
        df_cities = load_comparative_prices(major_cities, start_year=start_year)
        
        fig = px.line(
            df_cities,
            x='full_date',
            y='index_value',
            color='geo_name',
            title='Housing Price Index - Major Cities (Total House & Land)',
            labels={'full_date': 'Date', 'index_value': 'NHPI (2016=100)', 'geo_name': 'Geography'}
        )
        fig.update_layout(hovermode='x unified', height=450)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Interest rates
        df_rates = load_interest_rates(start_year=start_year)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_rates['full_date'],
            y=df_rates['bank_rate'],
            mode='lines',
            name='Bank Rate',
            line=dict(color='#FF6B6B', width=2)
        ))
        fig.add_trace(go.Scatter(
            x=df_rates['full_date'],
            y=df_rates['overnight_target'],
            mode='lines',
            name='Overnight Target',
            line=dict(color='#4ECDC4', width=2)
        ))
        fig.update_layout(
            title='Bank of Canada Interest Rates (Policy Rates)',
            xaxis_title='Date',
            yaxis_title='Rate (%)',
            hovermode='x unified',
            height=450
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Add correlation analysis
    st.markdown("---")
    st.subheader("📊 Housing Prices vs Interest Rates")
    
    # Merge data for correlation
    df_canada_prices = df_cities[df_cities['geo_name'] == 'Canada'][['full_date', 'index_value']].copy()
    df_merged = pd.merge(df_canada_prices, df_rates[['full_date', 'bank_rate', 'overnight_target']], on='full_date', how='inner')
    
    # Create dual-axis chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_merged['full_date'],
        y=df_merged['index_value'],
        name='Housing Price Index',
        yaxis='y1',
        line=dict(color='#FF6B6B', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=df_merged['full_date'],
        y=df_merged['bank_rate'],
        name='Bank Rate',
        yaxis='y2',
        line=dict(color='#4ECDC4', width=2)
    ))
    fig.update_layout(
        title='Housing Prices vs Interest Rates (Inverse Relationship)',
        xaxis=dict(title='Date'),
        yaxis=dict(title='NHPI (2016=100)', side='left', showgrid=False),
        yaxis2=dict(title='Interest Rate (%)', side='right', overlaying='y', showgrid=True),
        hovermode='x unified',
        height=450,
        legend=dict(x=0.02, y=0.98)
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Calculate correlation
    if len(df_merged) > 0:
        correlation = df_merged['index_value'].corr(df_merged['bank_rate'])
        st.info(f"📈 **Correlation coefficient**: {correlation:.3f} ({'Negative' if correlation < 0 else 'Positive'} relationship - When rates {'rise, prices tend to fall' if correlation < 0 else 'rise, prices tend to rise'})")
    
    # Add market insights
    st.markdown("---")
    st.subheader("📈 Market Insights (Past 24 Months)")
    
    col1, col2, col3 = st.columns(3)
    
    # Calculate insights from the data
    latest_canada = df_cities[df_cities['geo_name'] == 'Canada'].sort_values('full_date').iloc[-1]
    canada_24mo_ago = df_cities[df_cities['geo_name'] == 'Canada'].sort_values('full_date').iloc[0]
    total_change = latest_canada['index_value'] - canada_24mo_ago['index_value']
    
    with col1:
        st.markdown(f"""
        <div style='background-color: {"#d4edda" if total_change > 0 else "#f8d7da"}; padding: 15px; border-radius: 5px;'>
        <h4 style='margin: 0;'>🏠 Canada Price Change</h4>
        <h2 style='margin: 10px 0;'>{total_change:+.1f} pts</h2>
        <p style='margin: 0; font-size: 0.9em;'>Index moved from {canada_24mo_ago['index_value']:.1f} to {latest_canada['index_value']:.1f}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        # Interest rate change
        rate_now = df_rates['bank_rate'].iloc[-1]
        rate_24mo = df_rates['bank_rate'].iloc[0]
        rate_change = rate_now - rate_24mo
        st.markdown(f"""
        <div style='background-color: {"#fff3cd" if rate_change != 0 else "#e2e3e5"}; padding: 15px; border-radius: 5px;'>
        <h4 style='margin: 0;'>💰 Bank Rate Change</h4>
        <h2 style='margin: 10px 0;'>{rate_change:+.2f}%</h2>
        <p style='margin: 0; font-size: 0.9em;'>From {rate_24mo:.2f}% to {rate_now:.2f}%</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        # Most volatile market
        volatility = df_cities.groupby('geo_name')['yoy_change_pct'].std().sort_values(ascending=False)
        most_volatile = volatility.index[0]
        vol_value = volatility.iloc[0]
        st.markdown(f"""
        <div style='background-color: #cfe2ff; padding: 15px; border-radius: 5px;'>
        <h4 style='margin: 0;'>📊 Most Volatile Market</h4>
        <h2 style='margin: 10px 0; font-size: 1.3em;'>{most_volatile}</h2>
        <p style='margin: 0; font-size: 0.9em;'>Std Dev: {vol_value:.2f}% (higher = more volatile)</p>
        </div>
        """, unsafe_allow_html=True)


# ============================================================
# PAGE: HOUSING PRICES
# ============================================================
elif page == "📈 Housing Prices":
    st.header("Housing Price Analysis")
    
    # Geography selector
    geo_type = st.selectbox("Geography Type", ["Country", "Province", "CMA"])
    
    if geo_type == "Country":
        selected_geo = "Canada"
    elif geo_type == "Province":
        selected_geo = st.selectbox("Select Province", provinces)
    else:
        selected_geo = st.selectbox("Select CMA", cmas)
    
    # Load data
    df_prices = load_housing_prices(selected_geo, start_year)
    
    if df_prices.empty:
        st.warning(f"No data available for {selected_geo}")
    else:
        # Filter by NHPI type
        nhpi_filter = st.multiselect(
            "NHPI Type",
            options=df_prices['nhpi_type'].unique(),
            default=['Total (house and land)']
        )
        
        df_filtered = df_prices[df_prices['nhpi_type'].isin(nhpi_filter)]
        
        # Main chart - Index values
        st.subheader(f"New Housing Price Index - {selected_geo}")
        fig = px.line(
            df_filtered,
            x='full_date',
            y='index_value',
            color='nhpi_type',
            title=f'NHPI Trend ({start_year}-Present)',
            labels={'full_date': 'Date', 'index_value': 'Index (2016=100)', 'nhpi_type': 'Type'}
        )
        fig.update_layout(hovermode='x unified', height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # YoY change
            st.subheader("Year-over-Year % Change")
            fig = px.line(
                df_filtered,
                x='full_date',
                y='yoy_change_pct',
                color='nhpi_type',
                labels={'full_date': 'Date', 'yoy_change_pct': 'YoY Change (%)', 'nhpi_type': 'Type'}
            )
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.update_layout(hovermode='x unified', height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # MoM change
            st.subheader("Month-over-Month % Change")
            fig = px.line(
                df_filtered,
                x='full_date',
                y='mom_change_pct',
                color='nhpi_type',
                labels={'full_date': 'Date', 'mom_change_pct': 'MoM Change (%)', 'nhpi_type': 'Type'}
            )
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.update_layout(hovermode='x unified', height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        # Additional analysis
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            # Price distribution by year
            st.subheader("Annual Price Distribution")
            recent_years = df_filtered[df_filtered['year'] >= current_year - 5]
            if len(recent_years) > 0:
                fig = px.box(
                    recent_years,
                    x='year',
                    y='index_value',
                    color='nhpi_type',
                    title='Price Range by Year (Last 5 Years)',
                    labels={'year': 'Year', 'index_value': 'NHPI', 'nhpi_type': 'Type'}
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Volatility chart (rolling std)
            st.subheader("Price Volatility")
            volatility = price_volatility(df_filtered)
            fig = px.line(
                volatility.dropna(subset=['rolling_std']),
                x='full_date',
                y='rolling_std',
                color='nhpi_type',
                title='12-Month Rolling Volatility',
                labels={'full_date': 'Date', 'rolling_std': 'Std Dev', 'nhpi_type': 'Type'}
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        # Data table
        with st.expander("View Raw Data"):
            st.dataframe(
                df_filtered.sort_values('full_date', ascending=False),
                use_container_width=True
            )


# ============================================================
# PAGE: INTEREST RATES
# ============================================================
elif page == "💰 Interest Rates":
    st.header("Interest Rate Analysis")
    
    df_rates = load_interest_rates(start_year)
    
    # Main chart
    st.subheader("Bank of Canada Rates")
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_rates['full_date'],
        y=df_rates['bank_rate'],
        mode='lines',
        name='Bank Rate',
        line=dict(color='#FF6B6B', width=2),
        fill='tozeroy'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_rates['full_date'],
        y=df_rates['overnight_target'],
        mode='lines',
        name='Overnight Target',
        line=dict(color='#4ECDC4', width=2)
    ))
    
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='Rate (%)',
        hovermode='x unified',
        height=500
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Rate differential
        st.subheader("Rate Differential")
        fig = px.line(
            df_rates,
            x='full_date',
            y='rate_change',
            title='Bank Rate - Overnight Target',
            labels={'full_date': 'Date', 'rate_change': 'Differential (%)'}
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Rate distribution
        st.subheader("Rate Distribution")
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=df_rates['bank_rate'], name='Bank Rate', opacity=0.7))
        fig.add_trace(go.Histogram(x=df_rates['overnight_target'], name='Overnight Target', opacity=0.7))
        fig.update_layout(
            barmode='overlay',
            xaxis_title='Rate (%)',
            yaxis_title='Frequency',
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Additional analysis
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        # Rate change momentum (calculate day-over-day change)
        st.subheader("Rate Change Momentum")
        df_rates_sorted = df_rates.sort_values('full_date')
        df_rates_sorted['bank_rate_change'] = df_rates_sorted['bank_rate'].diff()
        
        fig = px.bar(
            df_rates_sorted[df_rates_sorted['bank_rate_change'] != 0],
            x='full_date',
            y='bank_rate_change',
            title='Bank Rate Changes Over Time',
            labels={'full_date': 'Date', 'bank_rate_change': 'Change (%)'},
            color='bank_rate_change',
            color_continuous_scale=['red', 'yellow', 'green']
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Cumulative rate change
        st.subheader("Cumulative Rate Change")
        df_rates_sorted['cumulative_change'] = (df_rates_sorted['bank_rate'] - df_rates_sorted['bank_rate'].iloc[0])
        
        fig = px.area(
            df_rates_sorted,
            x='full_date',
            y='cumulative_change',
            title=f'Total Change Since {df_rates_sorted["full_date"].min().strftime("%Y-%m-%d")}',
            labels={'full_date': 'Date', 'cumulative_change': 'Cumulative Change (%)'}
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    # Rate statistics summary
    st.markdown("---")
    st.subheader("📊 Rate Statistics Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Average Bank Rate", f"{df_rates['bank_rate'].mean():.2f}%")
    with col2:
        st.metric("Current Bank Rate", f"{df_rates['bank_rate'].iloc[-1]:.2f}%")
    with col3:
        st.metric("Highest Rate", f"{df_rates['bank_rate'].max():.2f}%")
    with col4:
        st.metric("Lowest Rate", f"{df_rates['bank_rate'].min():.2f}%")
    
    # Data table
    with st.expander("View Raw Data"):
        st.dataframe(
            df_rates.sort_values('full_date', ascending=False),
            use_container_width=True
        )


# ============================================================
# PAGE: HOUSING STARTS
# ============================================================
elif page == "🏗️ Housing Starts":
    st.header("Housing Starts Analysis")
    
    # Geography selector
    geo_type = st.selectbox("Geography Type", ["Country", "Province", "CMA"])
    
    if geo_type == "Country":
        selected_geo = "Canada"
    elif geo_type == "Province":
        selected_geo = st.selectbox("Select Province", provinces)
    else:
        selected_geo = st.selectbox("Select CMA", cmas)
    
    df_starts = load_housing_starts(selected_geo, start_year)
    if df_starts.attrs.get('excluded_ambiguous_rows', 0):
        st.warning("Some historical quarters have multiple observations per dwelling type. These ambiguous records are excluded; trends and annual totals may have gaps.")
    st.caption("Quarterly observations. Dates mark the start of each quarter; annual totals may cover only part of a year.")
    # Total units and Multiples overlap with their component dwelling types.
    components = ['Single-detached', 'Semi-detached', 'Row', 'Apartment and other unit type']
    available = [kind for kind in components if kind in df_starts['housing_type'].unique()]
    if available:
        df_starts = df_starts[df_starts['housing_type'].isin(available)]
    
    if df_starts.empty:
        st.warning(f"No data available for {selected_geo}")
    else:
        # Main chart - Housing starts
        st.subheader(f"Housing Starts - {selected_geo}")
        fig = px.bar(
            df_starts,
            x='full_date',
            y='starts_count',
            color='housing_type',
            title=f'Quarterly Housing Starts ({start_year}-Present)',
            labels={'full_date': 'Date', 'starts_count': 'Units', 'housing_type': 'Type'},
            barmode='stack'
        )
        fig.update_layout(hovermode='x unified', height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Total by year
            st.subheader("Annual Housing Starts")
            df_annual = df_starts.groupby(['year', 'housing_type'])['starts_count'].sum().reset_index()
            fig = px.bar(
                df_annual,
                x='year',
                y='starts_count',
                color='housing_type',
                title='Total Units by Year',
                labels={'year': 'Year', 'starts_count': 'Total Units', 'housing_type': 'Type'},
                barmode='group'
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Rolling 12-month average
            st.subheader("Four-Quarter Rolling Average")
            fig = px.line(
                df_starts[df_starts['rolling_12m_avg'].notna()],
                x='full_date',
                y='rolling_12m_avg',
                color='housing_type',
                title='Average Quarterly Starts (Four Quarters)',
                labels={'full_date': 'Date', 'rolling_12m_avg': 'Avg Units', 'housing_type': 'Type'}
            )
            fig.update_layout(hovermode='x unified', height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        # YoY change chart
        st.subheader("Year-over-Year % Change")
        fig = px.line(
            df_starts[df_starts['yoy_change_pct'].notna()],
            x='full_date',
            y='yoy_change_pct',
            color='housing_type',
            labels={'full_date': 'Date', 'yoy_change_pct': 'YoY Change (%)', 'housing_type': 'Type'}
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(hovermode='x unified', height=400)
        st.plotly_chart(fig, use_container_width=True)
        
        # Additional analysis
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            # Housing type distribution
            st.subheader("Housing Type Distribution")
            df_type_totals = df_starts.groupby('housing_type')['starts_count'].sum().reset_index()
            fig = px.pie(
                df_type_totals,
                values='starts_count',
                names='housing_type',
                title=f'Total Starts by Type ({start_year}-Present)',
                hole=0.4
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Seasonality analysis
            st.subheader("Seasonality Pattern")
            df_starts_monthly = df_starts.copy()
            df_starts_monthly['month_num'] = (df_starts_monthly['month'] - 1) // 3 + 1
            df_starts_monthly['month_name'] = 'Q' + df_starts_monthly['month_num'].astype(str)
            df_seasonal = df_starts_monthly.groupby(['month_num', 'month_name'])['starts_count'].mean().reset_index()
            df_seasonal = df_seasonal.sort_values('month_num')
            
            fig = px.bar(
                df_seasonal,
                x='month_name',
                y='starts_count',
                title='Average Starts by Quarter and Dwelling Type',
                labels={'month_name': 'Quarter', 'starts_count': 'Avg Units'}
            )
            fig.update_layout(height=400, xaxis={'categoryorder': 'array', 'categoryarray': df_seasonal['month_name'].tolist()})
            st.plotly_chart(fig, use_container_width=True)
        
        # Market share trends
        st.markdown("---")
        st.subheader("Market Share Trends Over Time")
        df_market_share = df_starts.copy()
        df_market_share['total_by_date'] = df_market_share.groupby('full_date')['starts_count'].transform('sum')
        df_market_share['market_share'] = (df_market_share['starts_count'] / df_market_share['total_by_date'] * 100)
        
        fig = px.area(
            df_market_share,
            x='full_date',
            y='market_share',
            color='housing_type',
            title='Housing Type Market Share (%)',
            labels={'full_date': 'Date', 'market_share': 'Market Share (%)', 'housing_type': 'Type'}
        )
        fig.update_layout(hovermode='x unified', height=450)
        st.plotly_chart(fig, use_container_width=True)
        
        # Data table
        with st.expander("View Raw Data"):
            st.dataframe(
                df_starts.sort_values('full_date', ascending=False),
                use_container_width=True
            )


# ============================================================
# PAGE: COMPARATIVE ANALYSIS
# ============================================================
elif page == "🔍 Comparative Analysis":
    st.header("Comparative Analysis")
    
    # Geography selection
    st.subheader("Select Geographies to Compare")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        compare_canada = st.checkbox("Canada", value=True)
    with col2:
        compare_provinces = st.multiselect("Provinces", provinces, default=["Ontario", "British Columbia"])
    with col3:
        compare_cmas = st.multiselect(
            "CMAs", 
            cmas, 
            default=["Toronto, Ontario", "Vancouver, British Columbia"]
        )
    
    # Build list of selected geographies
    selected_geos = []
    if compare_canada:
        selected_geos.append("Canada")
    selected_geos.extend(compare_provinces)
    selected_geos.extend(compare_cmas)
    
    if not selected_geos:
        st.warning("Please select at least one geography to compare.")
    else:
        # Load comparative data
        df_compare = load_comparative_prices(selected_geos, start_year=start_year)
        
        # Main comparison chart
        st.subheader("Housing Price Index Comparison")
        fig = px.line(
            df_compare,
            x='full_date',
            y='index_value',
            color='geo_name',
            title='NHPI Comparison (Total House and Land)',
            labels={'full_date': 'Date', 'index_value': 'Index (2016=100)', 'geo_name': 'Geography'}
        )
        fig.update_layout(hovermode='x unified', height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # YoY growth comparison
            st.subheader("Year-over-Year Growth Comparison")
            fig = px.line(
                df_compare,
                x='full_date',
                y='yoy_change_pct',
                color='geo_name',
                labels={'full_date': 'Date', 'yoy_change_pct': 'YoY Change (%)', 'geo_name': 'Geography'}
            )
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.update_layout(hovermode='x unified', height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Growth rate heatmap (recent 12 months)
            st.subheader("Recent Growth Rate Heatmap")
            df_recent = df_compare[df_compare['full_date'] >= df_compare['full_date'].max() - pd.DateOffset(months=12)]
            df_pivot = df_recent.pivot_table(
                values='yoy_change_pct',
                index='geo_name',
                columns=df_recent['full_date'].dt.to_period('M').astype(str),
                aggfunc='mean'
            )
            if not df_pivot.empty:
                fig = px.imshow(
                    df_pivot,
                    labels=dict(x="Month", y="Geography", color="YoY %"),
                    title='YoY Growth Rate by Region (Last 12 Months)',
                    color_continuous_scale='RdYlGn',
                    aspect='auto'
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
        
        # Regional performance ranking
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            # Top performers
            st.subheader("🏆 Top Performers (12-Month Growth)")
            df_latest = df_compare.sort_values('full_date').groupby('geo_name').tail(1)
            df_top = df_latest.nlargest(5, 'yoy_change_pct')[['geo_name', 'yoy_change_pct', 'index_value']]
            df_top.columns = ['Geography', 'YoY Growth %', 'Current Index']
            st.dataframe(df_top.reset_index(drop=True), use_container_width=True)
        
        with col2:
            # Latest values comparison
            st.subheader("Latest Index Values (Ranked)")
            df_latest = df_compare.sort_values('full_date').groupby('geo_name').tail(1)
            fig = px.bar(
                df_latest.sort_values('index_value', ascending=False).head(10),
                x='geo_name',
                y='index_value',
                title='Current NHPI by Geography',
                labels={'geo_name': 'Geography', 'index_value': 'Index (2016=100)'},
                color='index_value',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        # Correlation with interest rates
        st.subheader("Correlation with Interest Rates")
        
        df_rates = load_interest_rates(start_year)
        
        # Merge Canada prices with rates
        df_canada = df_compare[df_compare['geo_name'] == 'Canada'].copy()
        df_merged = pd.merge(
            df_canada,
            df_rates[['full_date', 'bank_rate']],
            on='full_date',
            how='inner'
        )
        
        if not df_merged.empty:
            fig = go.Figure()
            
            # Add NHPI on primary y-axis
            fig.add_trace(go.Scatter(
                x=df_merged['full_date'],
                y=df_merged['index_value'],
                name='Canada NHPI',
                line=dict(color='#4ECDC4', width=2),
                yaxis='y'
            ))
            
            # Add bank rate on secondary y-axis
            fig.add_trace(go.Scatter(
                x=df_merged['full_date'],
                y=df_merged['bank_rate'],
                name='Bank Rate',
                line=dict(color='#FF6B6B', width=2),
                yaxis='y2'
            ))
            
            fig.update_layout(
                title='Canada Housing Prices vs Bank Rate',
                xaxis=dict(title='Date'),
                yaxis=dict(title='NHPI (2016=100)', side='left'),
                yaxis2=dict(title='Bank Rate (%)', side='right', overlaying='y'),
                hovermode='x unified',
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Correlation coefficient
            corr = df_merged['index_value'].corr(df_merged['bank_rate'])
            st.metric(
                label="Correlation (NHPI vs Bank Rate)",
                value=f"{corr:.3f}",
                help="Pearson correlation coefficient. -1 = perfect negative correlation, 0 = no correlation, 1 = perfect positive correlation"
            )


# ============================================================
# PAGE: GEOGRAPHIC MAP
# ============================================================
elif page == "🗺️ Geographic Map":
    st.header("Geographic Heat Map Analysis")
    
    st.markdown("""
    Compare housing-market price movement across Canadian provinces and major cities.
    Bubble size represents housing price index level, color represents year-over-year growth rate.
    """)
    
    # Load latest geographic data
    df_geo = load_latest_geographic_data()
    
    if df_geo.empty:
        st.warning("No geographic data available with coordinates.")
    else:
        # Display latest data date
        st.info(f"📅 Displaying data as of: **{df_geo['full_date'].max().strftime('%B %Y')}**")
        
        # Interactive map
        st.subheader("Housing Price Index Map")
        
        # Create scatter map
        fig = px.scatter_geo(
            df_geo,
            lat='lat',
            lon='lon',
            size='index_value',
            color='yoy_change_pct',
            hover_name='geo_name',
            hover_data={
                'index_value': ':.1f',
                'yoy_change_pct': ':.2f',
                'geo_type': True,
                'lat': False,
                'lon': False
            },
            color_continuous_scale='RdYlGn',
            size_max=50,
            title='Housing Prices Across Canada',
            labels={
                'index_value': 'NHPI',
                'yoy_change_pct': 'YoY Growth %',
                'geo_type': 'Type'
            }
        )
        
        # Focus on Canada
        fig.update_geos(
            scope='north america',
            center=dict(lat=56, lon=-96),
            projection_scale=2.5,
            visible=True,
            showcountries=True,
            showcoastlines=True,
            showland=True,
            landcolor='rgb(243, 243, 243)',
            coastlinecolor='rgb(204, 204, 204)',
        )
        
        fig.update_layout(height=700)
        st.plotly_chart(fig, use_container_width=True)
        
        # Regional comparison tables
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏆 Highest Price Index")
            top_prices = df_geo.nlargest(5, 'index_value')[['geo_name', 'index_value', 'yoy_change_pct']]
            top_prices.columns = ['Geography', 'NHPI', 'YoY Growth %']
            st.dataframe(top_prices.reset_index(drop=True), use_container_width=True)
        
        with col2:
            st.subheader("📈 Fastest Growing Markets")
            top_growth = df_geo.nlargest(5, 'yoy_change_pct')[['geo_name', 'index_value', 'yoy_change_pct']]
            top_growth.columns = ['Geography', 'NHPI', 'YoY Growth %']
            st.dataframe(top_growth.reset_index(drop=True), use_container_width=True)
        
        # Provinces vs CMAs comparison
        st.markdown("---")
        st.subheader("Provinces vs Major Cities")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Province average
            df_provinces = df_geo[df_geo['geo_type'] == 'Province']
            fig = px.bar(
                df_provinces.sort_values('index_value', ascending=True),
                y='geo_name',
                x='index_value',
                orientation='h',
                title='Provincial Housing Price Index',
                labels={'geo_name': 'Province', 'index_value': 'NHPI'},
                color='yoy_change_pct',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Top CMAs
            df_cmas = df_geo[df_geo['geo_type'] == 'CMA'].nlargest(10, 'index_value')
            fig = px.bar(
                df_cmas.sort_values('index_value', ascending=True),
                y='geo_name',
                x='index_value',
                orientation='h',
                title='Top 10 CMAs by Price Index',
                labels={'geo_name': 'City', 'index_value': 'NHPI'},
                color='yoy_change_pct',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE: AI MARKET AGENT
# ============================================================
elif page == "🤖 AI Market Agent":
    st.header("🤖 AI Housing Market Assistant (Powered by DeepSeek)")
    
    st.markdown("""
    <div style='background-color: #f0f8ff; padding: 20px; border-radius: 10px; border-left: 5px solid #4CAF50;'>
    <h3>🤖 Your Personal Housing Market Analyst</h3>
    <p>Powered by <b>LangChain + DeepSeek</b>, this AI agent understands natural language and dynamically queries the database to answer your questions!</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Check for API key
    api_key = os.getenv('DEEPSEEK_API_KEY')
    
    if not api_key:
        st.error("""
        ⚠️ **DeepSeek API Key Required**
        
        To use the AI agent, you need to:
        1. Get a free API key from [DeepSeek Platform](https://platform.deepseek.com)
        2. Add it to your `.env` file: `DEEPSEEK_API_KEY=your_key_here`
        3. Restart the dashboard
        
        **Why DeepSeek?** It's one of the most cost-effective LLMs (~$0.14 per million tokens) with excellent performance!
        """)
        
        st.info("""
        **Alternative**: You can still use the manual analysis on other dashboard pages:
        - 📊 **Overview**: Market summary
        - 🗺️ **Geographic Map**: Spatial visualization
        - 🔍 **Comparative Analysis**: Multi-region comparison
        """)
    else:
        st.markdown("---")
        
        # Quick stats for context
        col1, col2, col3, col4 = st.columns(4)
        metrics = load_latest_metrics()
        
        with col1:
            st.metric("Canada NHPI", f"{metrics.iloc[0]['canada_nhpi']:.1f}")
        with col2:
            st.metric("YoY Change", f"{metrics.iloc[0]['canada_yoy']:.2f}%")
        with col3:
            st.metric("Bank Rate", f"{metrics.iloc[0]['latest_bank_rate']:.2f}%")
        with col4:
            st.metric("Data Date", metrics.iloc[0]['data_date'].strftime('%Y-%m'))
        
        st.markdown("---")
        
        # Sample questions
        st.subheader("💡 Sample Questions")
        
        sample_questions = [
            "What are the top 3 most expensive cities in Canada?",
            "Show me the trend in bank rates over the past 2 years",
            "How does Vancouver compare to Toronto in housing price growth?",
            "Which provinces have the most affordable housing?",
            "What is the correlation between interest rates and housing prices?",
            "Show me monthly housing starts in Ontario for the last year"
        ]
        
        def _pick_sample(q: str) -> None:
            # Runs before the rest of the page re-renders, so the text_area
            # below picks up the new value from session_state.
            st.session_state['user_query_input'] = q
            st.session_state['trigger_query'] = True

        col1, col2, col3 = st.columns(3)
        for idx, question in enumerate(sample_questions):
            col = [col1, col2, col3][idx % 3]
            with col:
                st.button(
                    f"❓ {question}",
                    key=f"q_{idx}",
                    use_container_width=True,
                    on_click=_pick_sample,
                    args=(question,),
                )

        st.markdown("---")

        # Query interface
        st.subheader("🔍 Ask Your Question")
        user_query = st.text_area(
            "Enter your question:",
            height=100,
            placeholder="E.g., What are the top 5 cities with the highest year-over-year price growth?",
            key="user_query_input",
        )
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            analyze_button = st.button("🚀 Ask AI Agent", type="primary", use_container_width=True)
        with col2:
            show_steps = st.checkbox("Show reasoning", value=False, help="Display the AI's thought process and SQL queries")
        with col3:
            if st.button("🧹 Clear chat", help="Forget the previous Q/A so the next question starts fresh"):
                st.session_state['chat_history'] = []
                st.rerun()
        
        # Trigger analysis
        should_analyze = analyze_button or st.session_state.get('trigger_query', False)
        
        if should_analyze:
            st.session_state['trigger_query'] = False  # Reset trigger
            
            if user_query.strip():
                with st.spinner("🤖 AI Agent is thinking and querying the database..."):
                    try:
                        # Import and create agent
                        from ai_agent import create_housing_agent, query_agent
                        
                        # Initialize agent (cached in session state). Pass the
                        # dashboard's existing DuckDB connection so the agent
                        # piggybacks on it instead of opening a second one
                        # with a conflicting config. We key the cache on a
                        # hash of ai_agent.py so editing the agent code or
                        # prompt invalidates the cached instance without
                        # needing a full Streamlit restart.
                        import hashlib
                        agent_src = Path(__file__).parent / "ai_agent.py"
                        version = hashlib.md5(agent_src.read_bytes()).hexdigest()
                        if st.session_state.get('agent_version') != version:
                            st.session_state['agent'] = create_housing_agent(
                                verbose=show_steps,
                                duckdb_conn=conn,
                            )
                            st.session_state['agent_version'] = version
                        
                        # Build a question that includes recent Q/A so the
                        # agent can answer follow-ups like "and Vancouver?".
                        chat_history = st.session_state.setdefault('chat_history', [])
                        if chat_history:
                            history_block = "\n".join(
                                f"User: {q}\nAssistant: {a}"
                                for q, a in chat_history[-3:]
                            )
                            framed_query = (
                                f"Previous conversation (for context only):\n"
                                f"{history_block}\n\n"
                                f"New question: {user_query}"
                            )
                        else:
                            framed_query = user_query

                        # Query the agent (passing conn enables auto-charting)
                        result = query_agent(
                            st.session_state['agent'],
                            framed_query,
                            duckdb_conn=conn,
                        )
                        if result['success']:
                            chat_history.append((user_query, result['answer']))
                            # Keep only the last 5 turns to bound prompt size.
                            del chat_history[:-5]

                        if result['success']:
                            st.markdown("---")
                            st.markdown("## 🎯 AI Agent Response")

                            # Display the answer
                            st.markdown(result['answer'])

                            # Show token usage if the callback captured it
                            usage = result.get('usage')
                            if usage:
                                st.caption(
                                    f"🔢 Tokens: {usage['total_tokens']:,} "
                                    f"(prompt {usage['prompt_tokens']:,} / "
                                    f"completion {usage['completion_tokens']:,})"
                                    + (f" · ~${usage['total_cost']:.4f}"
                                       if usage['total_cost'] else "")
                                )

                            # Auto-render a chart from the SQL the agent ran
                            df_result = result.get('dataframe')
                            if df_result is not None and not df_result.empty:
                                st.markdown("### 📊 Visualization")
                                _render_agent_chart(df_result)
                                with st.expander("View data table"):
                                    st.dataframe(df_result, use_container_width=True)
                                if result.get('sql'):
                                    with st.expander("View SQL"):
                                        st.code(result['sql'], language="sql")
                            
                            # Show intermediate steps if requested
                            if show_steps and result['steps']:
                                st.markdown("---")
                                st.markdown("### 🔧 Agent Reasoning Steps")
                                
                                with st.expander("👁️ View detailed reasoning and SQL queries", expanded=False):
                                    for idx, (action, observation) in enumerate(result['steps'], 1):
                                        st.markdown(f"**Step {idx}:**")
                                        st.code(str(action), language="text")
                                        if observation:
                                            st.markdown("**Result:**")
                                            st.code(str(observation)[:500], language="text")  # Limit output length
                                        st.markdown("---")
                            
                            # Success message
                            st.success("✅ Analysis complete! Ask another question to explore more.")
                        else:
                            st.error(f"❌ Error: {result['answer']}")
                            st.info("💡 Try rephrasing your question or check the database connection.")
                    
                    except ImportError as e:
                        st.error(f"""
                        ❌ **Import Error: {str(e)}**
                        
                        The AI agent dependencies are not available in your current Python environment.
                        
                        **Solution:**
                        1. Stop Streamlit (Ctrl+C)
                        2. Activate your virtual environment:
                           ```powershell
                           .venv\\Scripts\\Activate.ps1
                           ```
                        3. Install packages:
                           ```powershell
                           uv pip install langchain langchain-community langchain-openai sqlalchemy
                           ```
                        4. Restart Streamlit from the activated environment:
                           ```powershell
                           streamlit run dashboard.py
                           ```
                        """)
                    except Exception as e:
                        error_msg = str(e)
                        st.error(f"❌ Error: {error_msg}")
                        
                        # Provide specific help for connection errors
                        if "being used by another process" in error_msg or "Connection Error" in error_msg:
                            st.warning("""
                            **🔧 Database Connection Conflict**
                            
                            The AI agent cannot access the database because Streamlit is running from a different Python environment.
                            
                            **Solution:**
                            1. Stop Streamlit (Ctrl+C in the terminal)
                            2. Run the provided startup script:
                               ```powershell
                               .\\start_dashboard.bat
                               ```
                            
                            This ensures Streamlit runs from the .venv environment where all packages are installed.
                            """)
                        else:
                            st.info("💡 Please try again or check your API key configuration.")
            else:
                st.warning("Please enter a question to analyze.")
        
        # Additional tips
        st.markdown("---")
        st.markdown("""
        <div style='background-color: #fff3cd; padding: 15px; border-radius: 5px;'>
        <b>💡 How It Works:</b><br>
        • The AI agent uses <b>LangChain</b> to understand your natural language question<br>
        • It analyzes the database schema and writes SQL queries dynamically<br>
        • <b>DeepSeek LLM</b> powers the reasoning (cost-effective and smart!)<br>
        • You get conversational answers with data-driven insights<br><br>
        <b>🛠️ Pro Tips:</b><br>
        • Be specific: "Compare Toronto and Vancouver prices in 2024"<br>
        • Ask complex questions: "Which city had the highest growth when rates were below 2%?"<br>
        • Request visualizations: "Show me a trend of..." (agent can guide you to relevant pages)<br>
        • Check 'Show reasoning' to see the SQL queries generated
        </div>
        """, unsafe_allow_html=True)
        
        # Schema reference
        with st.expander("📊 Database Schema Reference"):
            st.markdown("""
            **Available Tables:**
            - `fact_housing_prices`: Price index data with yoy_change_pct, mom_change_pct
            - `fact_interest_rates`: Bank rates with bank_rate, overnight_target
            - `fact_housing_starts`: Construction data with starts_count, rolling_12m_avg
            - `dim_date`: Date dimension with full_date, year, month, quarter
            - `dim_geography`: Geography dimension with geo_name, geo_type, province
            
            **Key Relationships:**
            - Join fact tables to dim_date via `date_key`
            - Join housing facts to dim_geography via `geo_key`
            - Filter monthly data: `d.is_month_start = TRUE`
            """)


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.9em;'>
    Data sources: Statistics Canada (NHPI, Housing Starts) | Bank of Canada (Interest Rates)<br>
    Last updated: {}<br>
    Built with Streamlit | Powered by DuckDB
    </div>
    """.format(datetime.now().strftime("%Y-%m-%d %H:%M")),
    unsafe_allow_html=True
)
