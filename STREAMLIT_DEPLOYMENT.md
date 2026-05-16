# 🚀 Streamlit Cloud Deployment Guide

## Overview

This guide walks you through deploying the Canadian Housing Affordability Dashboard to **Streamlit Cloud** with **PostgreSQL** as the database backend.

---

## 📋 Prerequisites

1. **GitHub Account** - Your code must be in a GitHub repository
2. **PostgreSQL Database** - Set up a cloud PostgreSQL instance
3. **Streamlit Cloud Account** - Free at [share.streamlit.io](https://share.streamlit.io)
4. **DeepSeek API Key** - For the AI agent (optional but recommended)

---

## 🗄️ Step 1: Set Up PostgreSQL Database

### Recommended Providers (Free Tiers Available):

#### Option A: Neon (Recommended)
1. Visit [neon.tech](https://neon.tech)
2. Sign up for a free account
3. Create a new project: **housing-affordability**
4. Copy the connection string (format: `postgresql://user:pass@host/dbname`)

#### Option B: Supabase
1. Visit [supabase.com](https://supabase.com)
2. Create a new project
3. Go to **Settings** → **Database** → **Connection String**
4. Copy the URI mode connection string

#### Option C: Railway
1. Visit [railway.app](https://railway.app)
2. Create a new project → Add PostgreSQL
3. Copy the `DATABASE_URL` from the Connect tab

#### Option D: ElephantSQL
1. Visit [elephantsql.com](https://www.elephantsql.com)
2. Create a free "Tiny Turtle" instance
3. Copy the URL from the Details page

### Save Your Connection String
```
Example format:
postgresql://username:password@hostname:5432/databasename
```

---

## 📊 Step 2: Migrate Data to PostgreSQL

Run the migration script locally to populate your PostgreSQL database:

### 2.1 Set Environment Variable

**Windows (PowerShell):**
```powershell
$env:DATABASE_URL="postgresql://user:pass@host:5432/dbname"
```

**Mac/Linux:**
```bash
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
```

### 2.2 Run Migration

```bash
# Make sure you have processed CSV files
python run_pipeline.py

# Migrate data to PostgreSQL
python migrate_to_postgres.py
```

The script will:
- Create PostgreSQL schema
- Load data from `data/processed/*.csv` files
- Verify the migration
- Show row counts for each table

### Expected Output:
```
============================================================
POSTGRESQL MIGRATION
============================================================
Target: your-host.neon.tech
✓ Database connection successful

Creating PostgreSQL schema...
✓ Schema created successfully
Loading data from CSVs...
  NHPI: 12,345 rows
  BOC Rates: 5,678 rows
  Housing Starts: 23,456 rows
Populating dim_geography...
  ✓ Loaded 45 geographies
Populating fact_housing_prices...
  ✓ Loaded 12,345 price records
Populating fact_housing_starts...
  ✓ Loaded 23,456 housing start records
Populating fact_interest_rates...
  ✓ Loaded 5,678 interest rate records

Verifying migration...
  dim_date                       11,323 rows
  dim_geography                       45 rows
  fact_housing_prices             12,345 rows
  fact_housing_starts             23,456 rows
  fact_interest_rates              5,678 rows

✓ Migration completed successfully!
```

---

## 🌐 Step 3: Prepare GitHub Repository

### 3.1 Commit Your Changes

```bash
git add .
git commit -m "Add PostgreSQL support for cloud deployment"
git push origin main
```

### 3.2 Ensure These Files Are in Your Repo

Required files:
- ✅ `dashboard.py`
- ✅ `ai_agent.py`
- ✅ `config.py`
- ✅ `requirements.txt`
- ✅ `README.md`

**Important:** You do NOT need to commit the database file or CSV data files!
- ❌ `data/housing.duckdb` - Not needed (using PostgreSQL)
- ❌ `data/processed/*.csv` - Not needed (data is in PostgreSQL)
- ❌ `data/raw/*` - Not needed

Add to your `.gitignore`:
```
data/
logs/
.env
*.duckdb
*.csv
__pycache__/
.venv/
```

---

## ☁️ Step 4: Deploy to Streamlit Cloud

### 4.1 Create Streamlit Cloud Account

1. Visit [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Authorize Streamlit to access your repositories

### 4.2 Create New App

1. Click **"New app"**
2. Select your repository
3. Set the main file path: `dashboard.py`
4. Click **"Advanced settings"**

### 4.3 Configure Secrets

In the **Advanced settings** → **Secrets** section, add:

```toml
DATABASE_URL = "postgresql://user:password@host:5432/dbname"
DEEPSEEK_API_KEY = "your_deepseek_api_key_here"
```

Replace with your actual values:
- `DATABASE_URL`: Your PostgreSQL connection string from Step 1
- `DEEPSEEK_API_KEY`: Your DeepSeek API key (get one at [platform.deepseek.com](https://platform.deepseek.com))

### 4.4 Deploy

1. Click **"Deploy!"**
2. Wait 2-3 minutes for the app to build and start
3. Your app will be available at: `https://your-app-name.streamlit.app`

---

## 🔍 Step 5: Verify Deployment

Once deployed, check:

1. ✅ Dashboard loads without errors
2. ✅ Data appears in charts (housing prices, interest rates)
3. ✅ Geography dropdown populates correctly
4. ✅ AI Market Agent responds to questions
5. ✅ Maps display correctly

### Test Queries for AI Agent:
- "What are the top 5 most expensive cities?"
- "Show me Toronto's price trends over the last year"
- "How has the bank rate changed since 2020?"

---

## 🔧 Troubleshooting

### Issue: "Database connection failed"

**Solution:** Check your `DATABASE_URL` in Streamlit secrets:
- Ensure no extra quotes or spaces
- Verify the password is URL-encoded if it contains special characters
- Test connection locally first

### Issue: "No data showing in dashboard"

**Solution:** Verify migration completed successfully:
```bash
# Locally test the database
export DATABASE_URL="your_postgresql_url"
python -c "
from sqlalchemy import create_engine, text
import os
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(*) FROM fact_housing_prices'))
    print(f'Rows: {result.scalar()}')
"
```

### Issue: "AI Agent not working"

**Solution:**
- Verify `DEEPSEEK_API_KEY` is set in Streamlit secrets
- Check you have API credits at [platform.deepseek.com](https://platform.deepseek.com)
- Review app logs in Streamlit Cloud dashboard

### Issue: "App is slow"

**Solutions:**
- Check PostgreSQL database location (closer to Streamlit's servers = faster)
- Consider upgrading to a paid PostgreSQL tier for better performance
- Add database indexes if needed (already included in migration script)

---

## 📱 Step 6: Share Your Dashboard

Once deployed, you can share your app:

1. **Public URL**: `https://your-app-name.streamlit.app`
2. **Custom Domain**: Available on Streamlit Cloud paid plans
3. **Embed**: Use iframe to embed in websites

### Make Your App Public

In Streamlit Cloud:
1. Go to app settings
2. Change visibility to **"Public"**
3. Share the URL!

---

## 🔄 Updating Your App

### Update Code
```bash
git add .
git commit -m "Update dashboard features"
git push origin main
```

Streamlit Cloud will automatically redeploy (takes 1-2 minutes).

### Update Data
To refresh data in PostgreSQL:

1. Run extraction pipeline locally:
   ```bash
   python run_pipeline.py
   ```

2. Re-run migration:
   ```bash
   export DATABASE_URL="your_postgresql_url"
   python migrate_to_postgres.py
   ```

The migration script will drop and recreate tables, so all data will be refreshed.

### Update Dependencies
If you modify `requirements.txt`:
- Push changes to GitHub
- Streamlit Cloud will rebuild with new dependencies

---

## 💰 Cost Estimates

### Free Tier Options:

| Service | Free Tier | Limits |
|---------|-----------|--------|
| **Neon** | Free | 3 GB storage, 0.5 GB RAM |
| **Supabase** | Free | 500 MB database, 2 GB bandwidth/month |
| **Railway** | $5 credit/month | ~500 MB database |
| **ElephantSQL** | Free | 20 MB storage (very limited) |
| **Streamlit Cloud** | Free | 1 GB RAM, unlimited public apps |
| **DeepSeek API** | ~$1/month | For typical usage (~1M tokens) |

**Total monthly cost for this dashboard: FREE to $6/month**

---

## 🛡️ Security Best Practices

1. **Never commit secrets** to GitHub
   - Use Streamlit Cloud secrets for `DATABASE_URL`
   - Add `.env` to `.gitignore`

2. **Use read-only database user** (optional but recommended)
   ```sql
   CREATE USER dashboard_reader WITH PASSWORD 'secure_password';
   GRANT CONNECT ON DATABASE housing_affordability TO dashboard_reader;
   GRANT USAGE ON SCHEMA public TO dashboard_reader;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_reader;
   ```

3. **Restrict database access** by IP if your provider supports it

4. **Monitor API usage** for DeepSeek to avoid unexpected charges

---

## 📚 Additional Resources

- [Streamlit Cloud Documentation](https://docs.streamlit.io/streamlit-community-cloud)
- [Neon Documentation](https://neon.tech/docs/introduction)
- [DeepSeek API Docs](https://platform.deepseek.com/docs)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

---

## 🎉 Success!

Your dashboard is now live on Streamlit Cloud with PostgreSQL! 🚀

**Next steps:**
- Share the URL with stakeholders
- Set up a scheduled task to refresh data monthly
- Add custom features or visualizations
- Consider adding authentication for private deployments

---

## 📞 Support

If you encounter issues:
1. Check Streamlit Cloud app logs
2. Review PostgreSQL connection settings
3. Test database connectivity locally
4. Review the troubleshooting section above

**Happy analyzing! 📊🏠**
