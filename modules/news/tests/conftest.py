"""Postgres-backed fixtures for the news pipeline tests.

The news pipeline now shares finlabs_intelligence's Supabase PostgreSQL store, so
these tests require a real Postgres endpoint via ``INTELLIGENCE_TEST_DATABASE_URL``
(a local Postgres or a disposable instance — never production). Each test runs in
its own freshly created schema for isolation, mirroring the per-file isolation
DuckDB used to give for free.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from modules.news.db.init import create_schema

TEST_DSN_ENV = "INTELLIGENCE_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def base_dsn() -> str:
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        pytest.skip(f"set {TEST_DSN_ENV} to a PostgreSQL DSN to run news pipeline tests")
    return dsn


@pytest.fixture()
def news_connection(base_dsn: str, monkeypatch: pytest.MonkeyPatch):
    """Yield an autocommit connection bound to an isolated, schema-loaded space."""

    schema = f"news_{uuid.uuid4().hex[:16]}"
    with psycopg.connect(base_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    scoped = make_conninfo(base_dsn, options=f"-c search_path={schema}")
    # The CLI resolves its DSN from the environment, so point it at this schema
    # too — command-level tests then stay inside the test's isolated space.
    monkeypatch.setenv("INTELLIGENCE_DATABASE_URL", scoped)
    connection = psycopg.connect(scoped, autocommit=True)
    create_schema(connection)
    try:
        yield connection
    finally:
        connection.close()
        with psycopg.connect(base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
