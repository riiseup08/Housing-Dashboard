from pathlib import Path

import duckdb
import pytest

from load_duckdb import execute_sql_file


def test_execute_sql_file_runs_each_parsed_statement(tmp_path: Path) -> None:
    sql_file = tmp_path / "multi_statement.sql"
    sql_file.write_text(
        """
        CREATE TABLE example (id INTEGER, note VARCHAR);
        INSERT INTO example VALUES (1, 'a; semicolon inside a string');
        -- A semicolon in a comment must not create a statement;
        INSERT INTO example VALUES (2, 'second row');
        """,
        encoding="utf-8",
    )
    conn = duckdb.connect(":memory:")

    try:
        execute_sql_file(conn, sql_file)
        rows = conn.execute(
            "SELECT id, note FROM example ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        (1, "a; semicolon inside a string"),
        (2, "second row"),
    ]


def test_execute_sql_file_reports_failing_statement(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sql_file = tmp_path / "failure.sql"
    sql_file.write_text(
        "CREATE TABLE example (id INTEGER); SELECT * FROM missing_table;",
        encoding="utf-8",
    )
    conn = duckdb.connect(":memory:")

    try:
        with pytest.raises(duckdb.CatalogException):
            execute_sql_file(conn, sql_file)
    finally:
        conn.close()

    assert "statement 2 of 2" in caplog.text
