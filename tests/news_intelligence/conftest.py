"""Postgres-backed fixtures for news-intelligence storage tests.

The intelligence store is PostgreSQL, so these tests require a real Postgres
endpoint supplied through ``INTELLIGENCE_TEST_DATABASE_URL`` (a local Postgres or
a disposable hosted instance — never production). Each test runs in its own
freshly created schema so data is isolated without a separate database,
mirroring the per-file isolation DuckDB used to get for free.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

TEST_DSN_ENV = "INTELLIGENCE_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def base_dsn() -> str:
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        pytest.skip(
            f"set {TEST_DSN_ENV} to a PostgreSQL DSN to run intelligence "
            "storage tests"
        )
    return dsn


@pytest.fixture()
def intelligence_dsn(base_dsn: str, monkeypatch: pytest.MonkeyPatch) -> str:
    schema = f"it_{uuid.uuid4().hex[:16]}"
    with psycopg.connect(base_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    scoped = make_conninfo(base_dsn, options=f"-c search_path={schema}")
    # Code paths that read the DSN from the environment (resolve_dsn) must see the
    # isolated schema too, so the whole app graph stays inside this test's space.
    monkeypatch.setenv("INTELLIGENCE_DATABASE_URL", scoped)
    try:
        yield scoped
    finally:
        with psycopg.connect(base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
