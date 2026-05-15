# Streamlit Dashboard Guide

## Overview

The Canadian Housing Affordability Dashboard provides an interactive web interface to explore housing prices, interest rates, and construction activity across Canada.

**Access the dashboard at:** http://localhost:8501

## 🚀 Launch

From the project root directory:

```powershell
streamlit run dashboard.py
```

The dashboard will automatically open in your default browser. If not, navigate to http://localhost:8501.

## 📱 Dashboard Pages

### 1. 📊 Overview

**Purpose:** Quick view of key metrics and recent trends

**Features:**
- Current Canada NHPI with YoY change
- Latest Bank of Canada rate
- Data freshness indicator
- Total data points in database

**Charts:**
- Housing Price Index for major cities (last 12 months)
- Bank of Canada interest rates trend (last 12 months)

**Use Case:** Get a quick snapshot of the housing market and interest rate environment.

---

### 2. 📈 Housing Prices

**Purpose:** Deep dive into New Housing Price Index data

**Controls:**
- **Geography Type:** Country, Province, or CMA
- **Geography Selector:** Choose specific location
- **NHPI Type Filter:** Total (house and land), House only, or Land only
- **Date Range:** Controlled by sidebar (start year)

**Charts:**
1. **NHPI Trend** - Index values over time
2. **Year-over-Year % Change** - Annual growth rates
3. **Month-over-Month % Change** - Short-term volatility

**Features:**
- Multi-series comparison (toggle NHPI types)
- Interactive hover tooltips
- Expandable raw data table
- Downloadable data

**Use Case:** Analyze price trends for specific cities or provinces, compare house vs land prices.

---

### 3. 💰 Interest Rates

**Purpose:** Track Bank of Canada policy rates

**Charts:**
1. **Main Rate Chart** - Bank rate and overnight target over time
2. **Rate Differential** - Difference between bank rate and overnight target
3. **Rate Distribution** - Histogram showing frequency of different rate levels

**Features:**
- Dual-axis visualization
- Area fill under curves
- Historical rate changes visible
- Raw data table available

**Use Case:** Understand monetary policy changes, identify rate hiking/cutting cycles.

---

### 4. 🏗️ Housing Starts

**Purpose:** Analyze construction activity

**Controls:**
- **Geography Type:** Country, Province, or CMA
- **Geography Selector:** Choose location
- **Date Range:** Sidebar start year

**Charts:**
1. **Monthly Housing Starts** - Stacked bar chart (Single vs Multiple units)
2. **Annual Totals** - Grouped bar chart by housing type
3. **Year-over-Year % Change** - Growth trend

**Features:**
- Separate single and multiple unit starts
- Seasonal patterns visible in monthly data
- Annual aggregation for trend analysis

**Use Case:** Track construction activity, identify supply trends, compare single vs multi-family development.

---

### 5. 🔍 Comparative Analysis

**Purpose:** Multi-geography comparison and correlation analysis

**Controls:**
- **Canada Checkbox** - Include national data
- **Province Multi-select** - Choose provinces to compare
- **CMA Multi-select** - Choose cities to compare

**Charts:**
1. **NHPI Comparison** - Multiple geographies on same chart
2. **Year-over-Year Growth** - Compare growth rates
3. **Latest Index Values** - Bar chart of current levels (color-coded)
4. **Correlation with Interest Rates** - Dual-axis chart showing NHPI vs Bank Rate

**Features:**
- Up to 10+ geographies at once
- Pearson correlation coefficient calculated
- Color-coded bar charts (green = high, red = low)
- Unified hover mode (vertical line across all series)

**Use Case:** Compare markets, identify regional divergence, analyze interest rate impact on prices.

---

## 🎨 Interactive Features

### Plotly Charts

All charts are fully interactive:

- **Zoom:** Click and drag to zoom into specific time period
- **Pan:** Hold shift and drag to pan
- **Hover:** Hover over data points for exact values
- **Legend:** Click legend items to show/hide series
- **Reset:** Double-click chart to reset view
- **Download:** Use camera icon to save chart as PNG

### Streamlit Controls

- **Sidebar Settings:** Persist across all pages
- **Page Navigation:** Radio buttons on left sidebar
- **Filters:** Update charts instantly
- **Expandable Sections:** Click "View Raw Data" to show/hide tables
- **Auto-refresh:** Dashboard updates when switching pages

---

## 💡 Usage Tips

### 1. Comparative Market Analysis

**Goal:** Compare Toronto and Vancouver housing trends

**Steps:**
1. Navigate to "🔍 Comparative Analysis"
2. Select "Toronto, Ontario" and "Vancouver, British Columbia" from CMA list
3. Add "Canada" checkbox for benchmark
4. Review NHPI comparison chart
5. Check YoY growth divergence
6. Note correlation with interest rates

### 2. Provincial Policy Impact

**Goal:** Analyze impact of provincial policies on housing starts

**Steps:**
1. Navigate to "🏗️ Housing Starts"
2. Select "Province" → "Ontario"
3. Set start year to 2015
4. Review annual totals chart
5. Identify policy change dates (external research)
6. Correlate with YoY change chart

### 3. Interest Rate Sensitivity

**Goal:** Determine if specific markets are more rate-sensitive

**Steps:**
1. Navigate to "🔍 Comparative Analysis"
2. Select multiple CMAs
3. Scroll to correlation chart
4. Compare correlation coefficients (shown below chart)
5. Higher negative correlation = more rate-sensitive

### 4. Data Export for Reports

**Steps:**
1. Navigate to desired page
2. Configure filters as needed
3. Expand "View Raw Data"
4. Click "Download" button (appears on hover over table)
5. Export as CSV for Excel/PowerPoint

---

## 📊 Key Metrics Explained

### NHPI (New Housing Price Index)
- **Base Year:** 2016 = 100
- **Interpretation:** 120 = 20% more expensive than 2016
- **Components:** Total (house and land), House only, Land only

### YoY Change %
- **Calculation:** (Current - 12 months ago) / 12 months ago × 100
- **Interpretation:** Positive = price increase, Negative = price decrease
- **Threshold:** >5% = hot market, <-5% = cooling market

### MoM Change %
- **Calculation:** (Current - Previous month) / Previous month × 100
- **Use:** Short-term volatility indicator
- **Seasonality:** Expect variation due to weather/holidays

### Bank Rate
- **Definition:** Rate charged to commercial banks by Bank of Canada
- **Range (2009-2026):** 0.25% to 5.0%
- **Impact:** Higher rates → increased borrowing costs → housing demand pressure

### Housing Starts
- **Definition:** Number of new residential construction projects begun
- **Types:** Single (detached homes), Multiple (condos/apartments)
- **Leading Indicator:** Predicts future housing supply

---

## 🔧 Troubleshooting

### Dashboard won't load
```
ERROR: Database not found at data/housing.duckdb
```
**Solution:** Run `python run_pipeline.py --load-db` first to create database.

### No data for selected geography
```
WARNING: No data available for [Geography Name]
```
**Solution:** Some CMAs only have housing starts data, not NHPI. Try a different geography or switch to Housing Starts page.

### Charts are slow to render
**Cause:** Large date range with many geographies.

**Solution:** 
- Increase start year in sidebar (e.g., 2020 instead of 2000)
- Select fewer geographies in comparative analysis
- Close other browser tabs

### Port 8501 already in use
```
ERROR: Port 8501 is already in use
```
**Solution:** 
- Close other Streamlit instances
- Or specify different port: `streamlit run dashboard.py --server.port 8502`

---

## 🎓 Best Practices

### Performance
- Start with recent data (2015+) for faster initial load
- Use 3-5 geographies max in comparative analysis
- Close "View Raw Data" sections when not needed

### Analysis
- Always check data freshness (shown on Overview page)
- Compare similar geography types (Province vs Province, not Province vs CMA)
- Consider seasonality when analyzing MoM changes
- Use YoY for trend analysis (removes seasonality)

### Presentation
- Use screenshot tool (Snip & Sketch on Windows) to capture charts
- Download raw data tables for Excel pivot tables
- Note data sources and base year in reports

---

## 🔄 Data Refresh

The dashboard reads from the DuckDB database. To update with latest data:

1. **Re-run pipeline:**
   ```powershell
   python run_pipeline.py --load-db
   ```

2. **Refresh dashboard:**
   - Dashboard will auto-detect new data on page navigation
   - Or press `R` in browser to force full reload
   - Or restart dashboard: `Ctrl+C` then `streamlit run dashboard.py`

**Recommended Refresh Frequency:**
- **NHPI:** Monthly (Stats Canada releases ~10th of each month)
- **Interest Rates:** Daily (if rate changes expected)
- **Housing Starts:** Monthly (Stats Canada releases ~15th of each month)

---

## 🚀 Advanced Features (Coming Soon)

- [ ] Export custom reports to PDF
- [ ] Forecasting with trend lines
- [ ] Seasonally adjusted data toggle
- [ ] Custom date range picker (not just start year)
- [ ] Province-level map visualization
- [ ] Downloadable dashboard as HTML
- [ ] Email alerts for rate changes
- [ ] API endpoint for programmatic access

---

## 📚 Related Documentation

- **Database Schema:** See [DUCKDB_GUIDE.md](DUCKDB_GUIDE.md)
- **Data Sources:** See [README.md](README.md#data-sources)
- **Pipeline Usage:** See [README.md](README.md#quick-start)
- **Query Examples:** See [sql/03_analytical_queries.sql](sql/03_analytical_queries.sql)

---

## 🆘 Support

**Issues:**
- Check terminal output where dashboard is running for error messages
- Verify database exists: `ls data/housing.duckdb`
- Check pipeline logs: `cat data/pipeline.log`

**Questions:**
- Review data dictionary in `docs/`
- Check SQL queries in `sql/` folder
- Consult Statistics Canada documentation for NHPI methodology
