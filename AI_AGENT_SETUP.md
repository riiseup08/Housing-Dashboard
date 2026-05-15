# 🤖 AI Agent Setup Guide

## Overview

The Canadian Housing Affordability Dashboard now includes an **AI-powered market analyst** that uses:
- **LangChain** - Framework for building LLM applications
- **DeepSeek** - Cost-effective, high-performance large language model
- **SQL Agent** - Dynamically generates and executes SQL queries based on natural language

---

## 🚀 Quick Start

### 1. Install Dependencies

All required packages are in `requirements.txt`:

```bash
pip install -r requirements.txt
```

Specifically installs:
- `langchain>=0.1.0`
- `langchain-community>=0.0.20`
- `langchain-openai>=0.0.5`
- `sqlalchemy>=2.0`

### 2. Get DeepSeek API Key

1. Visit [DeepSeek Platform](https://platform.deepseek.com)
2. Sign up for a free account
3. Navigate to API Keys section
4. Create a new API key

**Cost:** DeepSeek is extremely affordable (~$0.14 per million input tokens, ~$0.28 per million output tokens)

### 3. Configure Environment

Add your API key to `.env` file:

```bash
# Create .env if it doesn't exist
cp .env.example .env

# Add your API key
echo "DEEPSEEK_API_KEY=your_actual_api_key_here" >> .env
```

### 4. Start Dashboard

```bash
streamlit run dashboard.py
```

Navigate to **🤖 AI Market Agent** page!

---

## 💬 How to Use

### Sample Questions

The AI agent understands natural language questions like:

**Simple Queries:**
- "What are the top 3 most expensive cities?"
- "Show me the current bank rate"
- "Which provinces have affordable housing?"

**Complex Analyses:**
- "Compare Toronto and Vancouver price growth over the past 2 years"
- "What is the correlation between interest rates and housing prices since 2020?"
- "Show me monthly housing starts in Ontario when bank rates were below 2%"

**Trend Analysis:**
- "How have interest rates changed in the last year?"
- "Which city had the fastest price growth in 2023?"
- "What's the average housing price index across all provinces?"

### Features

✅ **Natural Language Understanding** - Ask questions in plain English  
✅ **Dynamic SQL Generation** - Agent writes optimized queries automatically  
✅ **Schema Awareness** - Understands your database structure  
✅ **Conversational Context** - Maintains conversation history  
✅ **Reasoning Transparency** - Optional "Show reasoning" mode displays SQL queries  

---

## 🛠️ Technical Details

### Architecture

```
User Question
    ↓
LangChain Agent (DeepSeek LLM)
    ↓
SQL Query Generator
    ↓
DuckDB Database
    ↓
Natural Language Response
```

### Database Schema

The agent has access to:

**Fact Tables:**
- `fact_housing_prices` - NHPI data with YoY/MoM changes
- `fact_interest_rates` - Bank of Canada rates
- `fact_housing_starts` - Construction activity

**Dimension Tables:**
- `dim_date` - Date attributes (year, month, quarter)
- `dim_geography` - Provinces and CMAs

**Key Columns:**
- Join using `date_key` and `geo_key`
- Filter monthly data: `d.is_month_start = TRUE`
- NHPI baseline: 2016 = 100

### Agent Configuration

Located in `ai_agent.py`:

```python
from ai_agent import create_housing_agent, query_agent

# Create agent
agent = create_housing_agent(
    temperature=0.1,    # Lower = more focused
    verbose=True        # Show reasoning steps
)

# Query
result = query_agent(agent, "Your question here")
```

**Parameters:**
- `temperature` - Controls randomness (0.0-1.0, default 0.1)
- `verbose` - Display agent's thought process
- `max_iterations` - Max reasoning steps (default 15)
- `max_execution_time` - Timeout in seconds (default 60)

---

## 🧪 Testing

Test the agent from command line:

```bash
python ai_agent.py
```

This runs 3 sample queries and displays results.

---

## 🐛 Troubleshooting

### Error: "DEEPSEEK_API_KEY not found"

**Solution:** Add API key to `.env` file and restart dashboard

```bash
# Check if .env exists
ls .env

# Verify API key is set
grep DEEPSEEK_API_KEY .env
```

### Error: "No module named 'langchain'"

**Solution:** Install dependencies

```bash
pip install -r requirements.txt
```

### Error: "Unable to connect to DeepSeek"

**Possible causes:**
1. Invalid API key
2. Network connectivity issues
3. API rate limits exceeded

**Solution:** 
- Verify API key at https://platform.deepseek.com
- Check internet connection
- Wait a few minutes if rate limited

### Agent gives wrong answers

**Tips:**
- Be specific in your questions
- Use exact geography names (e.g., "Toronto, Ontario" not "Toronto")
- Enable "Show reasoning" to see SQL queries
- Rephrase if needed

---

## 📊 Cost Estimates

DeepSeek pricing (as of 2024):
- **Input:** $0.14 per million tokens
- **Output:** $0.28 per million tokens

**Example costs:**
- Simple question (200 tokens): ~$0.0001
- Complex analysis (2000 tokens): ~$0.001
- 1000 queries per month: ~$0.50

**Comparison:**
- OpenAI GPT-4: ~10x more expensive
- Claude: ~5x more expensive
- DeepSeek: Most cost-effective option

---

## 🔒 Security

**API Key Protection:**
- Never commit `.env` file to version control
- `.gitignore` already excludes `.env`
- Store keys securely
- Rotate keys periodically

**Database Access:**
- Agent has READ-ONLY access to DuckDB
- No data modification possible
- SQL injection protection via parameterized queries

---

## 🚀 Advanced Usage

### Custom Agent Creation

```python
from ai_agent import create_housing_agent

# Custom temperature for creative responses
creative_agent = create_housing_agent(temperature=0.7)

# Silent mode (no console output)
silent_agent = create_housing_agent(verbose=False)
```

### Programmatic Queries

```python
from ai_agent import create_housing_agent, query_agent

agent = create_housing_agent()

questions = [
    "Top 5 cities by price",
    "Average bank rate in 2023",
    "Compare Vancouver vs Calgary"
]

for q in questions:
    result = query_agent(agent, q)
    print(f"Q: {q}")
    print(f"A: {result['answer']}\n")
```

### Integration with Other Tools

The agent can be imported into Jupyter notebooks or other Python scripts:

```python
# In Jupyter notebook
from ai_agent import create_housing_agent, query_agent
import pandas as pd

agent = create_housing_agent(verbose=False)
result = query_agent(agent, "Show me top 3 expensive cities")
print(result['answer'])
```

---

## 📚 Resources

- **DeepSeek Docs:** https://platform.deepseek.com/docs
- **LangChain Docs:** https://python.langchain.com/docs
- **SQL Agent Guide:** https://python.langchain.com/docs/use_cases/sql
- **DuckDB Docs:** https://duckdb.org/docs/

---

## 🎯 Next Steps

1. **Test sample questions** - Try the pre-built examples
2. **Ask complex queries** - Combine multiple conditions
3. **Export insights** - Copy/paste responses for reports
4. **Explore reasoning** - Enable "Show reasoning" to learn SQL
5. **Integrate workflows** - Use programmatically in scripts

---

## 💡 Tips for Best Results

✅ **Do:**
- Be specific about geographies and time periods
- Use proper city names ("Toronto, Ontario")
- Ask one clear question at a time
- Check "Show reasoning" to verify SQL

❌ **Don't:**
- Ask multiple unrelated questions in one query
- Use ambiguous terms ("recent" → specify dates)
- Expect real-time data (data is from pipeline runs)
- Ask about data outside the database scope

---

## 🤝 Contributing

Found a bug or have a suggestion?
1. Check existing issues in the repository
2. Test with verbose mode enabled
3. Share the SQL query that was generated
4. Provide example question and expected output

---

**Happy Analyzing! 🎉**
