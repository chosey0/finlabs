"""FIFO single-writer transaction boundary over a PostgreSQL connection pool.

Postgres owns durability and cross-process concurrency, so the embedded-file
lock that DuckDB required is replaced by a transaction-scoped advisory lock.
The in-process FIFO queue and bounded backpressure are retained: they preserve
the "one active write transaction at a time" guarantee that the idempotency
state machine assumes, and they keep a slow database round-trip from silently
unbounded-queuing API requests.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

import psycopg
from psycopg_pool import ConnectionPool

from .database import build_pool, resolve_dsn
from .locking import WRITE_LOCK_KEY
from .schema import initialize_schema

T = TypeVar("T")


class WriterQueueFullError(RuntimeError):
    """The bounded write queue has reached capacity."""


class SingleWriter:
    def __init__(
        self,
        dsn: str | None = None,
        *,
        max_pending: int = 64,
        max_size: int = 4,
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be positive")
        self._pool: ConnectionPool = build_pool(resolve_dsn(dsn), max_size=max_size)
        self._max_pending = max_pending
        self._condition = threading.Condition()
        self._next_ticket = 0
        self._serving_ticket = 0
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    def _ensure_schema(self) -> None:
        with self._schema_lock:
            if self._schema_ready:
                return
            with self._pool.connection() as connection:
                initialize_schema(connection)
            self._schema_ready = True

    def execute(self, mutation: Callable[[psycopg.Connection], T]) -> T:
        self._ensure_schema()
        with self._condition:
            if self._next_ticket - self._serving_ticket >= self._max_pending:
                raise WriterQueueFullError("news intelligence write queue is full")
            ticket = self._next_ticket
            self._next_ticket += 1
            self._condition.wait_for(lambda: ticket == self._serving_ticket)
        try:
            with self._pool.connection() as connection:
                # pg_advisory_xact_lock serializes writers across every process
                # and auto-releases when this transaction commits or rolls back.
                connection.execute(
                    "SELECT pg_advisory_xact_lock(%s)", [WRITE_LOCK_KEY]
                )
                try:
                    result = mutation(connection)
                    connection.commit()
                    return result
                except Exception:
                    connection.rollback()
                    raise
        finally:
            with self._condition:
                self._serving_ticket += 1
                self._condition.notify_all()

    def read(self, query: Callable[[psycopg.Connection], T]) -> T:
        self._ensure_schema()
        with self._pool.connection() as connection:
            try:
                return query(connection)
            finally:
                connection.rollback()

    def close(self) -> None:
        self._pool.close()
