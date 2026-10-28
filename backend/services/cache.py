"""Tiny in-process TTL cache keyed by a hash of (sql + params).

Phase 1 uses this for dashboard query results. It is deliberately simple and
dependency-free; a later phase can swap the backend for Redis behind the same
``get`` / ``set`` / ``cached`` interface without touching call sites.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any

DEFAULT_TTL_SECONDS = 300


def make_key(sql: str, params: dict[str, Any] | None = None) -> str:
    """Stable cache key from a SQL string and its bound parameters."""
    payload = json.dumps(
        {"sql": " ".join(sql.split()), "params": params or {}},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TTLCache:
    """Thread-safe dict with per-entry expiry."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            hit = self._store.get(key)
            if hit is None:
                return None
            expires_at, value = hit
            if now >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = self._ttl if ttl_seconds is None else ttl_seconds
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def cached(
        self,
        sql: str,
        params: dict[str, Any] | None,
        loader: Callable[[], Any],
        ttl_seconds: int | None = None,
    ) -> Any:
        """Return the cached result for (sql, params) or compute and store it."""
        key = make_key(sql, params)
        hit = self.get(key)
        if hit is not None:
            return hit
        value = loader()
        self.set(key, value, ttl_seconds)
        return value


# Shared instance used by the dashboard query layer.
query_cache = TTLCache()
