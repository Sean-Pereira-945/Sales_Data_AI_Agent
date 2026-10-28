"""Build / rebuild the `mart.*` reporting tables from `db/views.sql`.

This is the one deliberately *read-write* path in the backend (it creates the
reporting layer). The dashboard API and the agent never run DDL; they only read
from `mart.*`.

Run:  python -m db.refresh_mart
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from db.session import get_engine

VIEWS_SQL = Path(__file__).with_name("views.sql")

# CockroachDB serialization failure (SQLSTATE 40001) — safe to retry.
RETRYABLE = "40001"
MAX_RETRIES = 3


def _statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements.

    The script intentionally contains no semicolons inside statements (no
    PL/pgSQL, no string literals with ';'), so a naive split is correct here.
    """
    out: list[str] = []
    for raw in sql.split(";"):
        # Drop comment-only / blank fragments.
        lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        if lines:
            out.append("\n".join(lines).strip())
    return out


def _execute_with_retry(conn, statement: str) -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            conn.execute(text(statement))
            return
        except OperationalError as exc:  # pragma: no cover - needs live contention
            if RETRYABLE in str(exc) and attempt < MAX_RETRIES:
                time.sleep(0.5 * attempt)
                continue
            raise


def refresh() -> None:
    sql = VIEWS_SQL.read_text(encoding="utf-8")
    statements = _statements(sql)
    # DDL + CTAS run most reliably statement-by-statement in autocommit.
    engine = get_engine().execution_options(isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        for i, stmt in enumerate(statements, 1):
            head = stmt.splitlines()[0][:70]
            print(f"[{i}/{len(statements)}] {head} ...")
            _execute_with_retry(conn, stmt)
    print(f"Done. Rebuilt mart.* from {VIEWS_SQL.name} ({len(statements)} statements).")


if __name__ == "__main__":
    refresh()
