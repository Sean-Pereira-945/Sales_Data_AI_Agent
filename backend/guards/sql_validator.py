"""Validator for agent-generated SQL (CLAUDE.md security rules).

The LLM may write SQL, but nothing it writes reaches the database until it passes
this guard. Parsing is done with **sqlglot** (a real SQL parser), never regex, so
comment tricks and stacked statements can't slip through.

Guarantees enforced here:
  * single statement only
  * read-only: the statement must be a SELECT / WITH … SELECT / set-operation
    (UNION etc.) — any DDL/DML (DROP, INSERT, UPDATE, DELETE, CREATE, ALTER,
    SET, SELECT … INTO, …) is rejected
  * table whitelist: only `mart.*` and read-only `olist.*`; system catalogs
    (pg_catalog, information_schema, crdb_internal) and other databases/schemas
    are rejected — this is what blocks "UNION INTO system tables"
  * column whitelist (defense in depth): every referenced column must be a known
    column of an allowed table (or a CTE / alias defined in the query)
  * a LIMIT is always present and never exceeds the configured maximum

`statement_timeout` is applied separately at execution time (see agent executor /
services). A dedicated read-only DB role is the recommended outer boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.config import get_settings

# --------------------------------------------------------------------------- #
# Whitelists (derived from docs/SCHEMA.md + the mart reporting layer)
# --------------------------------------------------------------------------- #
ALLOWED_COLUMNS: dict[tuple[str, str], set[str]] = {
    ("mart", "order_facts"): {
        "order_id", "purchase_date", "purchase_month", "customer_unique_id",
        "customer_state", "status", "items_gmv", "freight", "n_items",
        "payment_value", "main_payment_type", "max_installments", "review_score",
        "delivery_days", "estimated_days", "delay_days", "is_late", "delay_bucket",
    },
    ("mart", "order_item_facts"): {
        "order_id", "purchase_date", "purchase_month", "customer_state", "status",
        "product_id", "category", "seller_id", "seller_state", "price", "freight_value",
    },
    ("mart", "daily_sales"): {
        "date", "purchase_month", "customer_state", "category", "status",
        "gmv", "orders", "items", "freight",
    },
    ("olist", "customers"): {"customer_id", "customer_unique_id", "zip_code_prefix", "city", "state"},
    ("olist", "geolocation_points"): {"point_id", "zip_code_prefix", "latitude", "longitude", "city", "state", "in_brazil"},
    ("olist", "geolocations"): {"zip_code_prefix", "latitude", "longitude", "city", "state", "point_count"},
    ("olist", "order_items"): {"order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_at", "price", "freight_value"},
    ("olist", "order_payments"): {"order_id", "payment_sequential", "payment_type", "installments", "payment_value"},
    ("olist", "order_reviews"): {"order_id", "review_id"},
    ("olist", "orders"): {"order_id", "customer_id", "order_status", "purchased_at", "approved_at", "delivered_carrier_at", "delivered_customer_at", "estimated_delivery_date"},
    ("olist", "product_categories"): {"category_id", "category_name_pt", "category_name_en"},
    ("olist", "products"): {"product_id", "category_id", "name_length", "description_length", "photos_qty", "weight_g", "length_cm", "height_cm", "width_cm"},
    ("olist", "reviews"): {"review_id", "score", "comment_title", "comment_message", "created_date", "answered_at"},
    ("olist", "sellers"): {"seller_id", "zip_code_prefix", "city", "state"},
}

ALLOWED_TABLES: set[tuple[str, str]] = set(ALLOWED_COLUMNS)
ALLOWED_SCHEMAS: set[str] = {schema for schema, _ in ALLOWED_TABLES}
# Base names are unique across mart+olist, so an unqualified table can be resolved.
_BASE_TO_SCHEMA: dict[str, str] = {name: schema for schema, name in ALLOWED_TABLES}
_ALL_COLUMNS: set[str] = {c for cols in ALLOWED_COLUMNS.values() for c in cols}

# Node types that must never appear anywhere in the tree.
_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command, exp.Set, exp.Use, exp.Into, exp.Merge,
)
_ALLOWED_ROOT = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)


@dataclass
class ValidationResult:
    ok: bool
    sql: str = ""                 # sanitized SQL (comments stripped, LIMIT enforced)
    reason: str | None = None
    tables: list[str] = field(default_factory=list)


def _reject(reason: str) -> ValidationResult:
    return ValidationResult(ok=False, reason=reason)


def _table_key(t: exp.Table) -> tuple[str | None, str, str | None]:
    """(schema, name, catalog) lowercased; None where absent."""
    schema = t.db.lower() if t.db else None
    catalog = t.catalog.lower() if t.catalog else None
    return schema, t.name.lower(), catalog


def validate_sql(sql: str, max_limit: int | None = None) -> ValidationResult:
    """Validate and sanitize a single read-only statement. See module docstring."""
    if max_limit is None:
        max_limit = get_settings().sql_max_limit

    sql = (sql or "").strip()
    if not sql:
        return _reject("empty query")

    # 1) Parse. More than one statement (stacked / comment-smuggled) is rejected.
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception as exc:  # noqa: BLE001 - surface the parse error to the generator
        return _reject(f"could not parse SQL: {exc}")
    statements = [s for s in statements if s is not None]
    if len(statements) == 0:
        return _reject("no statement found")
    if len(statements) > 1:
        return _reject("only a single statement is allowed")

    expr = statements[0]

    # 2) Read-only root + no forbidden nodes anywhere.
    if not isinstance(expr, _ALLOWED_ROOT):
        return _reject(f"only SELECT/WITH queries are allowed, got {type(expr).__name__}")
    for node in expr.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            return _reject(f"disallowed statement element: {type(node).__name__}")

    # 3) Table whitelist (excluding CTE names, which are local).
    cte_names = {c.alias_or_name.lower() for c in expr.find_all(exp.CTE)}
    referenced: list[str] = []
    for t in expr.find_all(exp.Table):
        schema, name, catalog = _table_key(t)
        if catalog is not None:
            return _reject(f"cross-database reference not allowed: {catalog}.{schema}.{name}")
        if schema is None and name in cte_names:
            continue  # reference to a CTE defined in this query
        if schema is None:
            schema = _BASE_TO_SCHEMA.get(name)
            if schema is None:
                return _reject(f"unknown or non-whitelisted table: {name}")
        if (schema, name) not in ALLOWED_TABLES:
            return _reject(f"table not in whitelist: {schema}.{name}")
        referenced.append(f"{schema}.{name}")

    if not referenced:
        return _reject("query references no whitelisted table")

    # 4) Column whitelist (defense in depth). Allowed = known columns of any
    #    whitelisted table, plus names introduced locally (CTEs, aliases).
    local_names = set(cte_names)
    for alias in expr.find_all(exp.Alias):
        if alias.alias:
            local_names.add(alias.alias.lower())
    for ta in expr.find_all(exp.TableAlias):
        if ta.name:
            local_names.add(ta.name.lower())
    allowed_cols = _ALL_COLUMNS | local_names
    for col in expr.find_all(exp.Column):
        cname = col.name.lower()
        if cname and cname != "*" and cname not in allowed_cols:
            return _reject(f"column not in whitelist: {col.sql()}")

    # 5) Enforce LIMIT (present and ≤ max).
    limit = expr.args.get("limit")
    if limit is None:
        expr = expr.limit(max_limit)
    else:
        try:
            current = int(limit.expression.name)
        except (AttributeError, ValueError):
            current = max_limit + 1
        if current <= 0 or current > max_limit:
            expr = expr.limit(max_limit)

    return ValidationResult(
        ok=True,
        sql=expr.sql(dialect="postgres", comments=False),
        tables=sorted(set(referenced)),
    )
