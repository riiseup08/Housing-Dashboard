"""
AI Housing Market Agent
========================
LangChain-powered SQL agent using DeepSeek for natural language queries.

Usage:
    from ai_agent import create_housing_agent
    agent = create_housing_agent()
    response = agent.run("What are the top 5 most expensive cities?")
"""

import logging
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from duckdb_engine import ConnectionWrapper
from langchain_community.callbacks import get_openai_callback
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from config import DB_PATH

logger = logging.getLogger(__name__)


class _DuckDBNoReflectDatabase(SQLDatabase):
    """SQLDatabase that skips SQLAlchemy reflection.

    duckdb-engine 0.17 inherits Postgres-style reflection that probes
    `pg_catalog.pg_collation`, which DuckDB 1.5.x doesn't ship. We bypass it
    by querying DuckDB's own `information_schema` for table + column metadata
    and feeding LangChain hand-built CREATE TABLE strings.

    TECH DEBT: This whole class is a workaround. When upgrading the stack:
      1. Check whether `pg_catalog.pg_collation` exists in your DuckDB
         version (`SELECT * FROM pg_catalog.pg_collation LIMIT 1`).
      2. Check whether duckdb-engine has stopped issuing the pg_collation
         query in its column reflection (look for a 0.18+ release that
         references duckdb 1.5/1.6 compatibility).
      If both are OK, delete this class and switch `create_housing_agent`
      back to plain `SQLDatabase(engine)`.
    """

    def __init__(self, engine, duckdb_conn, sample_rows=2):
        self._engine = engine
        self._duckdb_conn = duckdb_conn
        self._sample_rows_in_table_info = sample_rows
        self._schema = None
        self._max_string_length = 300
        self._include_tables = set()
        self._ignore_tables = set()
        self._indexes_in_table_info = False
        self._custom_table_info = None
        self._view_support = False

        tables = duckdb_conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        ).fetchall()
        self._all_tables = {t[0] for t in tables}
        self._usable_tables = set(self._all_tables)

    def get_usable_table_names(self):
        return sorted(self._usable_tables)

    def get_table_info(self, table_names=None, get_col_comments=False):
        names = list(table_names) if table_names else sorted(self._usable_tables)
        missing = set(names) - self._usable_tables
        if missing:
            raise ValueError(f"table_names {missing} not found in database")

        blocks = []
        for tname in sorted(names):
            cols = self._duckdb_conn.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'main' AND table_name = ? "
                "ORDER BY ordinal_position",
                [tname],
            ).fetchall()
            col_lines = [
                f"    {c[0]} {c[1]}" + ("" if c[2] == "YES" else " NOT NULL")
                for c in cols
            ]
            create = f"CREATE TABLE {tname} (\n" + ",\n".join(col_lines) + "\n)"

            sample = ""
            if self._sample_rows_in_table_info:
                try:
                    col_names = [c[0] for c in cols]
                    rows = self._duckdb_conn.execute(
                        f'SELECT * FROM "{tname}" LIMIT {int(self._sample_rows_in_table_info)}'
                    ).fetchall()
                    sample_rows_str = "\n".join(
                        "\t".join(str(v)[:100] for v in r) for r in rows
                    )
                    sample = (
                        f"\n\n/*\n{self._sample_rows_in_table_info} rows from "
                        f"{tname} table:\n{chr(9).join(col_names)}\n{sample_rows_str}\n*/"
                    )
                except Exception:
                    sample = ""

            blocks.append(create + sample)
        return "\n\n".join(blocks)


def create_housing_agent(temperature=0.1, verbose=True, duckdb_conn=None):
    """
    Create a SQL agent for housing market analysis.

    Args:
        temperature: LLM temperature (0.0-1.0). Lower = more focused.
        verbose: Show agent reasoning steps.
        duckdb_conn: Optional existing duckdb.DuckDBPyConnection. If provided,
            the agent piggybacks on it via .cursor() so we do not open a second
            connection to the file (which DuckDB rejects when configurations
            differ — e.g. dashboard opened it read_only).

    Returns:
        SQL agent executor
    """
    # Check for DeepSeek API key
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        raise ValueError(
            "DEEPSEEK_API_KEY not found. Please set it in your .env file:\n"
            "DEEPSEEK_API_KEY=your_api_key_here"
        )

    if duckdb_conn is None:
        # Standalone use (CLI / tests): open our own read-only connection.
        import duckdb
        duckdb_conn = duckdb.connect(str(DB_PATH), read_only=True)

    # Share the caller's open connection. cursor() returns an independent
    # DuckDBPyConnection bound to the same database — no second file open,
    # so no "different configuration" conflict. We wrap it in duckdb-engine's
    # ConnectionWrapper so SQLAlchemy gets the DBAPI shape it expects.
    engine = create_engine(
        "duckdb:///:memory:",
        creator=lambda: ConnectionWrapper(duckdb_conn.cursor()),
        poolclass=StaticPool,
    )
    # Use a no-reflection subclass: duckdb-engine 0.17's Postgres-style
    # reflection probes pg_catalog.pg_collation, which DuckDB 1.5.x lacks.
    db = _DuckDBNoReflectDatabase(engine, duckdb_conn)
    
    # Initialize DeepSeek LLM (OpenAI-compatible API)
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=api_key,
        openai_api_base="https://api.deepseek.com",
        temperature=temperature,
        max_tokens=2000
    )
    
    # Create SQL agent with custom instructions
    prefix = """You are a Canadian housing market analyst with access to a DuckDB database containing:

**Tables:**
1. **dim_date**: Date dimension with full_date, year, quarter, month, etc.
2. **dim_geography**: Geography dimension with geo_name, geo_type (Province/CMA), province
3. **fact_housing_prices**: Housing price index data with index_value, yoy_change_pct, mom_change_pct
4. **fact_interest_rates**: Bank of Canada rates with bank_rate, overnight_target, rate_change
5. **fact_housing_starts**: Construction activity with starts_count, rolling_12m_avg

**Key Columns:**
- Join tables using date_key and geo_key
- Use d.full_date for dates (DATE type)
- Use d.is_month_start = TRUE for monthly data
- NHPI baseline is 2016=100 (higher = more expensive)

**Guidelines:**
- Always filter on d.is_month_start = TRUE for monthly trends
- Use proper JOINs between fact and dimension tables
- For "latest" data, use ORDER BY d.full_date DESC LIMIT N
- Format numbers nicely (ROUND for decimals)
- Provide context with your answers (not just raw numbers)
- For geographic queries, remember geo_name includes city and province (e.g., 'Toronto, Ontario')

**Chart-friendly output (important):**
The UI auto-renders a chart from your final SELECT, so structure your final query so it plots well:
- Include the dimension you're showing on the X axis as the FIRST column (e.g. d.full_date for trends, g.geo_name for rankings).
- If you're comparing multiple series, include the series label as a column (e.g. g.geo_name) and the numeric measure as another column.
- Keep result sets reasonably small (≤ ~500 rows) and ORDER BY the X axis.
- Alias columns with snake_case names so they read well as axis labels.

Answer the user's question using SQL queries. Be conversational and insightful.
"""
    
    agent_executor = create_sql_agent(
        llm=llm,
        db=db,
        agent_type="openai-tools",
        verbose=verbose,
        handle_parsing_errors=True,
        prefix=prefix,
        # Needed so query_agent can recover the SQL the agent ran and
        # re-execute it for the chart. Without this, intermediate_steps
        # is dropped from the AgentExecutor's output.
        agent_executor_kwargs={"return_intermediate_steps": True},
    )
    
    return agent_executor


def _extract_last_sql(steps):
    """Pull the final sql_db_query the agent executed (if any)."""
    last_sql = None
    for action, _obs in steps:
        tool = getattr(action, "tool", "")
        if tool in ("sql_db_query", "sql_db_query_checker"):
            tool_input = getattr(action, "tool_input", None)
            if isinstance(tool_input, dict):
                q = tool_input.get("query")
            else:
                q = tool_input
            if isinstance(q, str) and q.strip().lower().startswith(("select", "with")):
                last_sql = q
    return last_sql


def query_agent(agent, question, duckdb_conn=None):
    """
    Query the agent with error handling.

    Args:
        agent: SQL agent executor
        question: User's natural language question
        duckdb_conn: Optional DuckDB connection. If provided, the last SQL
            query the agent ran is re-executed against it to return a
            DataFrame the UI can chart.

    Returns:
        dict with 'answer', 'steps', 'success', 'sql', 'dataframe', 'usage'.
        'usage' is {'prompt_tokens', 'completion_tokens', 'total_tokens',
        'total_cost'} when the callback could attribute them, else None.
    """
    try:
        with get_openai_callback() as cb:
            result = agent.invoke({"input": question})
        steps = result.get('intermediate_steps', [])

        sql = None
        df = None
        if duckdb_conn is not None:
            sql = _extract_last_sql(steps)
            if sql:
                try:
                    df = duckdb_conn.cursor().execute(sql).fetchdf()
                except Exception:
                    # The agent's SQL didn't replay cleanly (e.g. it created
                    # a temp object during reasoning). Log it so we can see
                    # why a chart was skipped; the text answer is fine.
                    logger.exception("Failed to re-execute agent SQL: %s", sql)
                    df = None

        usage = {
            'prompt_tokens': cb.prompt_tokens,
            'completion_tokens': cb.completion_tokens,
            'total_tokens': cb.total_tokens,
            'total_cost': cb.total_cost,
        } if cb.total_tokens else None

        return {
            'success': True,
            'answer': result.get('output', 'No answer generated.'),
            'steps': steps,
            'sql': sql,
            'dataframe': df,
            'usage': usage,
        }
    except Exception as e:
        logger.exception("Agent query failed for question: %r", question)
        return {
            'success': False,
            'answer': f"Error: {str(e)}",
            'steps': [],
            'sql': None,
            'dataframe': None,
            'usage': None,
        }


# Schema information for reference
SCHEMA_INFO = """
## Database Schema

### dim_date
- date_key (INTEGER, PK): Format YYYYMMDD
- full_date (DATE): Actual date
- year, quarter, month, month_name, month_abbrev
- day_of_year, is_month_start, is_quarter_start
- fiscal_year

### dim_geography  
- geo_key (INTEGER, PK)
- geo_name (VARCHAR): Full name (e.g., "Toronto, Ontario")
- geo_type (VARCHAR): "Province", "CMA", or "Country"
- province (VARCHAR): Province name

### fact_housing_prices
- date_key, geo_key (FKs)
- nhpi_type (VARCHAR): "Total (house and land)", "House only", "Land only"
- index_value (DECIMAL): Price index (2016=100)
- yoy_change_pct (DECIMAL): Year-over-year % change
- mom_change_pct (DECIMAL): Month-over-month % change

### fact_interest_rates
- date_key (FK)
- bank_rate (DECIMAL): Bank of Canada policy rate
- overnight_target (DECIMAL): Target overnight rate
- rate_change (DECIMAL): Difference between the two

### fact_housing_starts
- date_key, geo_key (FKs)
- housing_type (VARCHAR): "Total units", "Single-detached", etc.
- starts_count (DECIMAL): Number of units (in thousands)
- rolling_12m_avg (DECIMAL): 12-month rolling average
"""


if __name__ == "__main__":
    # Test the agent
    print("Initializing AI Housing Market Agent...")
    
    try:
        agent = create_housing_agent(verbose=True)
        
        # Test questions
        test_questions = [
            "What are the top 3 most expensive cities in Canada?",
            "Show me the trend in bank rates over the past year",
            "Compare Toronto and Vancouver housing prices"
        ]
        
        for q in test_questions:
            print(f"\n{'='*60}")
            print(f"Q: {q}")
            print('='*60)
            result = query_agent(agent, q)
            print(f"A: {result['answer']}")
            
    except ValueError as e:
        print(f"\n❌ {e}")
        print("\nTo use the agent, set your DeepSeek API key:")
        print("  1. Get a key from https://platform.deepseek.com")
        print("  2. Add to .env: DEEPSEEK_API_KEY=your_key_here")
