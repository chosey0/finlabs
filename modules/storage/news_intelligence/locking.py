"""Cross-process write serialization for the intelligence PostgreSQL database.

DuckDB needed an OS file lock because every process opened the same embedded
file. PostgreSQL is a shared server, so serialization moves into the database
via a transaction-scoped advisory lock. ``WRITE_LOCK_KEY`` is the fixed lock slot
the single-writer transaction acquires; any other process that tries to write
blocks until the holder's transaction ends.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg

# Stable 64-bit key derived from "news-intel"; shared by every writer process.
WRITE_LOCK_KEY = 0x6E6577732D696E74


@contextmanager
def advisory_write_lock(connection: psycopg.Connection) -> Iterator[None]:
    """Hold the intelligence write lock for the connection's current transaction."""

    connection.execute("SELECT pg_advisory_xact_lock(%s)", [WRITE_LOCK_KEY])
    yield
