"""PostgreSQL connection management for news intelligence.

The intelligence store is a PostgreSQL server (e.g. Supabase, RDS, or a
self-hosted instance). Concurrency is owned by the database server, so callers
connect through a small pooled factory instead of opening an embedded file per
call. The data-source name (DSN) is a standard libpq connection string resolved
from an explicit value or the ``INTELLIGENCE_DATABASE_URL`` environment variable.
"""

from __future__ import annotations

import os

import psycopg
from psycopg_pool import ConnectionPool

DSN_ENV_VAR = "INTELLIGENCE_DATABASE_URL"


def load_env() -> None:
    """Load a local ``.env`` into the process environment for entrypoints.

    Call this only from entrypoints (the API runtime, scripts) — never at import
    time of a library module, or tests that import storage would silently inherit
    a developer ``.env`` DSN. ``override=False`` keeps already-exported variables
    (shell/CI) authoritative over the file.
    """

    from dotenv import load_dotenv

    # interpolate=False keeps a literal "$" in values (e.g. a DB password) from
    # being treated as shell-style variable expansion.
    load_dotenv(override=False, interpolate=False)

# Connections are pinned to the Korean-equity domain timezone so timestamptz
# values round-trip as +09:00 aware datetimes, independent of the host or the
# server's configured timezone. (DuckDB previously rendered in the host's local
# timezone; this makes that KST behaviour explicit and deterministic.)
_SESSION_TIMEZONE = "Asia/Seoul"


def resolve_dsn(explicit: str | None = None) -> str:
    """Return the PostgreSQL connection string or raise when it is missing."""

    dsn = explicit or os.environ.get(DSN_ENV_VAR)
    if not dsn:
        raise RuntimeError(
            "PostgreSQL connection string is required; pass an explicit dsn or set "
            f"{DSN_ENV_VAR}"
        )
    return dsn


def _configure(connection: psycopg.Connection) -> None:
    # A plain SET inside an uncommitted transaction is reverted by a later
    # rollback (e.g. the pool's between-use reset), so commit it to make the
    # session timezone durable for the connection's whole lifetime.
    connection.execute(f"SET TIME ZONE '{_SESSION_TIMEZONE}'")
    connection.commit()


def build_pool(
    dsn: str,
    *,
    min_size: int = 1,
    max_size: int = 4,
) -> ConnectionPool:
    """Create an opened connection pool with deterministic session settings."""

    return ConnectionPool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        kwargs={"autocommit": False},
        configure=_configure,
        open=True,
    )


def connect(dsn: str) -> psycopg.Connection:
    """Open a single short-lived connection with deterministic session settings."""

    connection = psycopg.connect(dsn, autocommit=False)
    _configure(connection)
    return connection
