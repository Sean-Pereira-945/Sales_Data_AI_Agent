"""Security tests for the agent's SQL guard (guards/sql_validator.py)."""
from __future__ import annotations

import pytest

from guards.sql_validator import validate_sql

MAX = 200


# ----------------------------- rejections ----------------------------------- #
@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE mart.order_facts",
        "DELETE FROM mart.order_facts",
        "UPDATE mart.order_facts SET status = 'x'",
        "INSERT INTO mart.order_facts VALUES (1)",
        "TRUNCATE mart.order_facts",
        "ALTER TABLE mart.order_facts ADD COLUMN x INT",
        "CREATE TABLE evil AS SELECT * FROM mart.order_facts",
        "GRANT SELECT ON mart.order_facts TO public",
    ],
)
def test_rejects_write_and_ddl(sql):
    assert validate_sql(sql, MAX).ok is False


def test_rejects_multiple_statements():
    r = validate_sql("SELECT 1 FROM mart.order_facts; DROP TABLE mart.order_facts", MAX)
    assert not r.ok and "single statement" in r.reason


def test_rejects_comment_smuggled_second_statement():
    r = validate_sql("SELECT * FROM mart.order_facts; -- hi\nDELETE FROM mart.order_facts", MAX)
    assert not r.ok


def test_rejects_select_into_write():
    assert not validate_sql("SELECT * INTO evil FROM mart.order_facts", MAX).ok


def test_rejects_non_whitelisted_table():
    r = validate_sql("SELECT * FROM olist.secret_payroll LIMIT 5", MAX)
    assert not r.ok and "whitelist" in r.reason


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM information_schema.tables LIMIT 5",
        "SELECT * FROM pg_catalog.pg_tables LIMIT 5",
        "SELECT * FROM crdb_internal.tables LIMIT 5",
    ],
)
def test_rejects_system_catalogs(sql):
    assert validate_sql(sql, MAX).ok is False


def test_rejects_union_into_system_tables():
    sql = ("SELECT order_id FROM mart.order_facts "
           "UNION SELECT table_name FROM information_schema.tables")
    assert validate_sql(sql, MAX).ok is False


def test_rejects_cross_database_reference():
    assert not validate_sql("SELECT * FROM otherdb.mart.order_facts LIMIT 5", MAX).ok


def test_rejects_unknown_column():
    r = validate_sql("SELECT password FROM mart.order_facts LIMIT 5", MAX)
    assert not r.ok and "column" in r.reason


def test_rejects_empty():
    assert not validate_sql("   ", MAX).ok


# ----------------------------- acceptances ---------------------------------- #
def test_accepts_aggregate_and_strips_comments():
    r = validate_sql(
        "SELECT category, SUM(gmv) AS g /* note */ FROM mart.daily_sales "
        "GROUP BY category ORDER BY g DESC LIMIT 10",
        MAX,
    )
    assert r.ok
    assert "/* note */" not in r.sql  # comments stripped on re-render
    assert "mart.daily_sales" in r.tables


def test_injects_limit_when_missing():
    r = validate_sql("SELECT customer_state, COUNT(*) FROM mart.order_facts GROUP BY 1", MAX)
    assert r.ok and "LIMIT 200" in r.sql.upper()


def test_clamps_oversized_limit():
    r = validate_sql("SELECT * FROM mart.order_facts LIMIT 999999", MAX)
    assert r.ok and "LIMIT 200" in r.sql.upper()


def test_keeps_small_limit():
    r = validate_sql("SELECT * FROM mart.order_facts LIMIT 5", MAX)
    assert r.ok and "LIMIT 5" in r.sql.upper()


def test_accepts_cte():
    r = validate_sql(
        "WITH s AS (SELECT seller_id, SUM(price) p FROM mart.order_item_facts GROUP BY seller_id) "
        "SELECT seller_id, p FROM s ORDER BY p DESC LIMIT 10",
        MAX,
    )
    assert r.ok


def test_accepts_read_only_olist():
    r = validate_sql("SELECT order_status, COUNT(*) FROM olist.orders GROUP BY 1 LIMIT 10", MAX)
    assert r.ok
