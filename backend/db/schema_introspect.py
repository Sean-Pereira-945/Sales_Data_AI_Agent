"""Phase 0 schema discovery.

Connects read-only to CockroachDB and reports, per table:
  - columns, types, nullability
  - row counts
  - indexes
  - 5 sample rows
  - date ranges for temporal columns
  - distinct values for low-cardinality columns
  - a dimension-vs-measure classification (heuristic)

Writes the result to docs/SCHEMA.md. Never modifies data.

Run:  python -m db.schema_introspect
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

from db.session import get_engine, read_only_session

# A column with at most this many distinct values is treated as low-cardinality
# (worth listing its values and a good dashboard filter candidate).
LOW_CARDINALITY_MAX = 40

# Name hints used only to guess measures vs dimensions.
MEASURE_HINTS = ("amount", "price", "cost", "revenue", "total", "qty", "quantity",
                 "sales", "profit", "margin", "discount", "value", "count")

NUMERIC_TYPES = ("INT", "BIGINT", "SMALLINT", "DECIMAL", "NUMERIC", "FLOAT",
                 "REAL", "DOUBLE")
TEMPORAL_TYPES = ("DATE", "TIMESTAMP", "TIMESTAMPTZ", "TIME")


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    role: str = "dimension"          # dimension | measure
    distinct_count: int | None = None
    distinct_values: list[Any] = field(default_factory=list)
    min_value: Any = None
    max_value: Any = None


@dataclass
class TableInfo:
    schema: str
    name: str
    row_count: int
    columns: list[ColumnInfo]
    indexes: list[dict[str, Any]]
    sample_rows: list[dict[str, Any]]


def _type_str(sa_type: Any) -> str:
    return str(sa_type).upper()


def _is_numeric(type_str: str) -> bool:
    return any(t in type_str for t in NUMERIC_TYPES)


def _is_temporal(type_str: str) -> bool:
    return any(t in type_str for t in TEMPORAL_TYPES)


def _classify(col_name: str, type_str: str, is_pk: bool, is_fk: bool) -> str:
    """Heuristic: numeric, non-key, measure-sounding columns are measures."""
    if is_pk or is_fk:
        return "dimension"
    if _is_numeric(type_str) and any(h in col_name.lower() for h in MEASURE_HINTS):
        return "measure"
    if _is_numeric(type_str) and not col_name.lower().endswith("id"):
        return "measure"
    return "dimension"


SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "crdb_internal", "pg_extension")


def list_tables() -> list[tuple[str, str]]:
    """Return (schema, table) for every user table, across all non-system schemas."""
    insp = inspect(get_engine())
    pairs: list[tuple[str, str]] = []
    for schema in insp.get_schema_names():
        if schema in SYSTEM_SCHEMAS:
            continue
        for table in insp.get_table_names(schema=schema):
            pairs.append((schema, table))
    return sorted(pairs)


def _q(schema: str, table: str) -> str:
    """Safely quote a schema-qualified table name."""
    return f'"{schema}"."{table}"'


def _row_count(session, schema: str, table: str) -> int:
    return session.execute(text(f"SELECT COUNT(*) FROM {_q(schema, table)}")).scalar_one()


def _sample_rows(session, schema: str, table: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = session.execute(text(f"SELECT * FROM {_q(schema, table)} LIMIT :n"), {"n": limit})
    return [dict(r) for r in rows.mappings()]


def _distinct_count(session, schema: str, table: str, col: str) -> int:
    return session.execute(
        text(f'SELECT COUNT(DISTINCT "{col}") FROM {_q(schema, table)}')
    ).scalar_one()


def _distinct_values(session, schema: str, table: str, col: str) -> list[Any]:
    rows = session.execute(
        text(f'SELECT DISTINCT "{col}" FROM {_q(schema, table)} ORDER BY 1 LIMIT :n'),
        {"n": LOW_CARDINALITY_MAX},
    )
    return [r[0] for r in rows]


def _min_max(session, schema: str, table: str, col: str) -> tuple[Any, Any]:
    row = session.execute(
        text(f'SELECT MIN("{col}"), MAX("{col}") FROM {_q(schema, table)}')
    ).one()
    return row[0], row[1]


def introspect_table(session, insp, schema: str, table: str) -> TableInfo:
    pk_cols = set(insp.get_pk_constraint(table, schema=schema).get("constrained_columns") or [])
    fk_cols: set[str] = set()
    for fk in insp.get_foreign_keys(table, schema=schema):
        fk_cols.update(fk.get("constrained_columns") or [])

    columns: list[ColumnInfo] = []
    for col in insp.get_columns(table, schema=schema):
        type_str = _type_str(col["type"])
        info = ColumnInfo(
            name=col["name"],
            type=type_str,
            nullable=bool(col.get("nullable", True)),
            role=_classify(col["name"], type_str, col["name"] in pk_cols, col["name"] in fk_cols),
        )
        # Enrich temporal columns with a range, categorical ones with distinct values.
        if _is_temporal(type_str):
            info.min_value, info.max_value = _min_max(session, schema, table, col["name"])
        elif info.role == "dimension" and not _is_numeric(type_str):
            n = _distinct_count(session, schema, table, col["name"])
            info.distinct_count = n
            if n <= LOW_CARDINALITY_MAX:
                info.distinct_values = _distinct_values(session, schema, table, col["name"])
        columns.append(info)

    return TableInfo(
        schema=schema,
        name=table,
        row_count=_row_count(session, schema, table),
        columns=columns,
        indexes=insp.get_indexes(table, schema=schema),
        sample_rows=_sample_rows(session, schema, table),
    )


def introspect_all() -> list[TableInfo]:
    insp = inspect(get_engine())
    tables = list_tables()
    result: list[TableInfo] = []
    with read_only_session() as session:
        for schema, table in tables:
            result.append(introspect_table(session, insp, schema, table))
    return result


# --------------------------- rendering ---------------------------

def _fmt(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (dt.date, dt.datetime, Decimal)):
        return str(v)
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."


def render_markdown(tables: list[TableInfo]) -> str:
    lines: list[str] = []
    lines.append("# Database Schema — Discovery (Phase 0)\n")
    lines.append(f"_Generated {dt.datetime.now().isoformat(timespec='seconds')}. "
                 "Read-only introspection; no data was modified._\n")
    lines.append(f"**Tables found:** {len(tables)}\n")

    for t in tables:
        lines.append(f"\n## `{t.schema}.{t.name}`  —  {t.row_count:,} rows\n")

        lines.append("### Columns\n")
        lines.append("| column | type | null | role | notes |")
        lines.append("|---|---|---|---|---|")
        for c in t.columns:
            notes = ""
            if c.min_value is not None or c.max_value is not None:
                notes = f"range: {_fmt(c.min_value)} → {_fmt(c.max_value)}"
            elif c.distinct_count is not None:
                notes = f"{c.distinct_count} distinct"
                if c.distinct_values:
                    vals = ", ".join(_fmt(v) for v in c.distinct_values[:12])
                    notes += f": {vals}"
                    if len(c.distinct_values) >= LOW_CARDINALITY_MAX:
                        notes += ", ..."
            lines.append(f"| {c.name} | {c.type} | {'Y' if c.nullable else 'N'} "
                         f"| {c.role} | {notes} |")

        if t.indexes:
            lines.append("\n### Indexes\n")
            for ix in t.indexes:
                cols = ", ".join(ix.get("column_names") or [])
                uniq = " (unique)" if ix.get("unique") else ""
                lines.append(f"- `{ix.get('name')}`{uniq}: {cols}")

        lines.append("\n### Sample rows\n")
        if t.sample_rows:
            cols = list(t.sample_rows[0].keys())
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "|".join("---" for _ in cols) + "|")
            for row in t.sample_rows:
                lines.append("| " + " | ".join(_fmt(row[c]) for c in cols) + " |")
        else:
            lines.append("_(no rows)_")

    # Dimension / measure summary
    lines.append("\n## Dimensions vs. measures (heuristic)\n")
    for t in tables:
        dims = [c.name for c in t.columns if c.role == "dimension"]
        meas = [c.name for c in t.columns if c.role == "measure"]
        lines.append(f"- **{t.schema}.{t.name}** — measures: {', '.join(meas) or '—'}; "
                     f"dimensions: {', '.join(dims) or '—'}")

    return "\n".join(lines) + "\n"


def main() -> int:
    tables = introspect_all()
    if not tables or all(t.row_count == 0 for t in tables):
        print("No sales data found in the database (no tables, or all tables empty). "
              "Stopping as instructed.")
        return 1

    out = Path(__file__).resolve().parents[2] / "docs" / "SCHEMA.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(tables), encoding="utf-8")
    print(f"Wrote {out} — {len(tables)} tables, "
          f"{sum(t.row_count for t in tables):,} total rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
