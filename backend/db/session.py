"""Database engine/session factory for CockroachDB.

Phase 0 is strictly read-only: we open connections with a default-read-only
transaction so introspection can never modify data, even by accident.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    """Create (once) and return the SQLAlchemy engine for CockroachDB."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            # Surface the connection early if the cert/URL is wrong.
            connect_args={"connect_timeout": 10},
        )
    return _engine


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


@contextmanager
def read_only_session() -> Iterator[Session]:
    """Yield a session pinned to a READ ONLY transaction.

    Any attempt to write inside this block raises at the DB level, which is the
    safety guarantee we want for schema discovery and for agent-generated SQL.
    """
    engine = get_engine()
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
            session.rollback()  # never persist anything from a read-only path
        except Exception:
            session.rollback()
            raise
