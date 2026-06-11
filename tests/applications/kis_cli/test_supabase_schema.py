from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.storage import SupabaseDatabaseInitResult
from kis_cli.storage.supabase import (
    init_supabase_database,
    insert_supabase_ohlcv_bars,
    normalize_postgres_dsn,
    supabase_schema_statements,
    upsert_supabase_symbols,
)
from kis_cli.storage.supabase_schema import SUPABASE_TABLE_NAMES, supabase_schema_sql

runner = CliRunner()


def test_supabase_schema_defines_canonical_market_tables() -> None:
    sql = supabase_schema_sql()

    assert SUPABASE_TABLE_NAMES == ("symbols", "ohlcv_bars")
    assert "CREATE TABLE IF NOT EXISTS symbols" in sql
    assert "CREATE TABLE IF NOT EXISTS ohlcv_bars" in sql
    assert "PRIMARY KEY (market, symbol)" in sql
    assert "PRIMARY KEY (market, symbol, interval, trade_date)" in sql
    assert "raw JSONB NOT NULL DEFAULT '{}'::jsonb" in sql
    assert "downloaded_at TIMESTAMPTZ NOT NULL" in sql
    assert "fetched_at TIMESTAMPTZ NOT NULL" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_interval_date" in sql


def test_supabase_schema_sql_splits_into_executable_statements() -> None:
    statements = supabase_schema_statements()

    assert len(statements) == 6
    assert all(not statement.endswith(";") for statement in statements)
    assert statements[0].startswith("CREATE TABLE IF NOT EXISTS symbols")
    assert statements[3].startswith("CREATE TABLE IF NOT EXISTS ohlcv_bars")


def test_init_supabase_database_requires_dsn(monkeypatch) -> None:
    monkeypatch.delenv("KISCLI_SUPABASE_DB_DSN", raising=False)

    with pytest.raises(ValueError, match="KISCLI_SUPABASE_DB_DSN"):
        init_supabase_database()


def test_init_supabase_database_wraps_invalid_dsn(monkeypatch) -> None:
    class FakePsycopgError(Exception):
        pass

    def fake_connect(dsn: str, **kwargs):
        assert dsn == "Invalid DSN"
        assert kwargs == {"prepare_threshold": None}
        raise FakePsycopgError("missing '=' after 'Invalid' in connection info string")

    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(Error=FakePsycopgError, connect=fake_connect),
    )

    with pytest.raises(ValueError, match="valid PostgreSQL connection string"):
        init_supabase_database(dsn="Invalid DSN")


def test_init_supabase_database_includes_sanitized_connection_details(monkeypatch) -> None:
    class FakePsycopgError(Exception):
        pass

    def fake_connect(dsn: str, **kwargs):
        assert kwargs == {"prepare_threshold": None}
        raise FakePsycopgError(f"could not connect with {dsn} password=secret")

    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(Error=FakePsycopgError, connect=fake_connect),
    )

    with pytest.raises(ValueError) as exc_info:
        init_supabase_database(
            dsn="postgresql://postgres:Army4914!@#$@db.example.supabase.co/postgres"
        )

    message = str(exc_info.value)
    assert "Details:" in message
    assert "Army4914" not in message
    assert "password=secret" not in message
    assert "password=********" in message


def test_normalize_postgres_dsn_url_encodes_raw_password_special_chars() -> None:
    dsn = "postgresql://postgres.example:abc!@#$123@db.example.supabase.co:6543/postgres"

    normalized = normalize_postgres_dsn(dsn)

    assert normalized == (
        "postgresql://postgres.example:abc%21%40%23%24123"
        "@db.example.supabase.co:6543/postgres"
    )


def test_normalize_postgres_dsn_does_not_double_encode_password() -> None:
    dsn = "postgresql://postgres.example:abc%21%40%23%24123@db.example.supabase.co/postgres"

    normalized = normalize_postgres_dsn(dsn)

    assert normalized == dsn


def test_init_supabase_database_passes_normalized_dsn_to_connect_factory(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement: str) -> None:
            pass

        def commit(self) -> None:
            pass

    def connect_factory(dsn: str):
        captured["dsn"] = dsn
        return FakeConnection()

    init_supabase_database(
        dsn="postgresql://postgres.example:abc!@#$123@db.example.supabase.co/postgres",
        connect_factory=connect_factory,
    )

    assert captured["dsn"] == (
        "postgresql://postgres.example:abc%21%40%23%24123"
        "@db.example.supabase.co/postgres"
    )


def test_init_supabase_database_executes_schema_with_dsn(monkeypatch) -> None:
    executed: list[str] = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement: str) -> None:
            executed.append(statement)

        def commit(self) -> None:
            executed.append("COMMIT")

    def connect_factory(dsn: str):
        assert dsn == "postgresql://example"
        return FakeConnection()

    monkeypatch.setenv("KISCLI_SUPABASE_DB_DSN", "postgresql://example")

    result = init_supabase_database(connect_factory=connect_factory)

    assert result == SupabaseDatabaseInitResult(
        dsn_env="KISCLI_SUPABASE_DB_DSN",
        tables=("symbols", "ohlcv_bars"),
    )
    assert executed[:-1] == list(supabase_schema_statements())
    assert executed[-1] == "COMMIT"


def test_db_init_supabase_command_reports_schema(monkeypatch) -> None:
    def fake_init_supabase_database(*, dsn=None):
        assert dsn is None
        return SupabaseDatabaseInitResult(
            dsn_env="KISCLI_SUPABASE_DB_DSN",
            tables=("symbols", "ohlcv_bars"),
        )

    monkeypatch.setenv("KISCLI_SUPABASE_DB_DSN", "postgresql://env")
    monkeypatch.setattr("kis_cli.cli.db.init_supabase_database", fake_init_supabase_database)

    result = runner.invoke(app, ["db", "init", "--store", "supabase"])

    assert result.exit_code == 0
    assert "Supabase schema initialized" in result.output
    assert "KISCLI_SUPABASE_DB_DSN" in result.output
    assert "symbols, ohlcv_bars" in result.output


def test_db_init_supabase_prompts_for_missing_dsn(tmp_path, monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_init_supabase_database(*, dsn=None):
        captured["dsn"] = dsn
        return SupabaseDatabaseInitResult(
            dsn_env="KISCLI_SUPABASE_DB_DSN",
            tables=("symbols", "ohlcv_bars"),
        )

    monkeypatch.delenv("KISCLI_SUPABASE_DB_DSN", raising=False)
    monkeypatch.setattr("kis_cli.cli.common.default_config_file", lambda: tmp_path / "config.yaml")
    monkeypatch.setattr("kis_cli.cli.db.init_supabase_database", fake_init_supabase_database)

    result = runner.invoke(
        app,
        ["db", "init", "--store", "supabase"],
        input="postgresql://prompted\n",
    )

    assert result.exit_code == 0
    assert captured["dsn"] == "postgresql://prompted"
    assert "Supabase PostgreSQL DSN" in result.output
    assert "postgresql://prompted" not in result.output


def test_db_init_supabase_reuses_prompted_dsn_from_profiles_env(tmp_path, monkeypatch) -> None:
    captured: list[str | None] = []

    def fake_init_supabase_database(*, dsn=None):
        captured.append(dsn)
        return SupabaseDatabaseInitResult(
            dsn_env="KISCLI_SUPABASE_DB_DSN",
            tables=("symbols", "ohlcv_bars"),
        )

    monkeypatch.delenv("KISCLI_SUPABASE_DB_DSN", raising=False)
    monkeypatch.setattr("kis_cli.cli.common.default_config_file", lambda: tmp_path / "config.yaml")
    monkeypatch.setattr("kis_cli.cli.db.init_supabase_database", fake_init_supabase_database)

    first = runner.invoke(
        app,
        ["db", "init", "--store", "supabase"],
        input="postgresql://postgres:Army4914!@#$@db.example.supabase.co:6543/postgres\n",
    )

    assert first.exit_code == 0
    env = (tmp_path / "profiles.env").read_text(encoding="utf-8")
    assert 'KISCLI_SUPABASE_DB_DSN="postgresql://postgres:Army4914!@#$@db.example.supabase.co:6543/postgres"' in env
    assert captured == ["postgresql://postgres:Army4914!@#$@db.example.supabase.co:6543/postgres"]

    monkeypatch.delenv("KISCLI_SUPABASE_DB_DSN", raising=False)
    second = runner.invoke(app, ["db", "init", "--store", "supabase"])

    assert second.exit_code == 0
    assert "Supabase PostgreSQL DSN" not in second.output
    assert captured == [
        "postgresql://postgres:Army4914!@#$@db.example.supabase.co:6543/postgres",
        None,
    ]
    assert "KISCLI_SUPABASE_DB_DSN" in os.environ


def test_db_init_supabase_rejects_path() -> None:
    result = runner.invoke(
        app,
        ["db", "init", "--store", "supabase", "--path", "warehouse.duckdb"],
    )

    assert result.exit_code != 0
    assert "--path is only valid with --store duckdb" in result.output


def test_upsert_supabase_symbols_executes_conflict_update() -> None:
    executed: list[tuple[str, tuple[object, ...] | None]] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, statement: str, parameters: list[tuple[object, ...]]) -> None:
            for parameter_set in parameters:
                executed.append((statement, parameter_set))

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self) -> None:
            executed.append(("COMMIT", None))

    stored = upsert_supabase_symbols(
        FakeConnection(),
        [
            {
                "market": "NASDAQ",
                "symbol": "AAPL",
                "standard_code": None,
                "realtime_symbol": "DNASAAPL",
                "korean_name": "애플",
                "english_name": "Apple Inc.",
                "security_type": "stock",
                "currency": "USD",
                "exchange_id": "NAS",
                "exchange_code": "NAS",
                "exchange_name": "NASDAQ",
                "country_code": "US",
                "listed_date": None,
                "base_price": None,
                "lot_size": None,
                "raw_source": "nasmst.cod",
                "raw": '{"symbol": "AAPL"}',
                "downloaded_at": "2026-05-07T00:00:00+09:00",
            }
        ],
    )

    assert stored == 1
    assert "ON CONFLICT (market, symbol) DO UPDATE" in executed[0][0]
    assert executed[0][1][0:2] == ("NASDAQ", "AAPL")
    assert executed[-1] == ("COMMIT", None)


def test_upsert_supabase_symbols_wraps_write_errors() -> None:
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, statement: str, parameters: list[tuple[object, ...]]) -> None:
            raise RuntimeError('prepared statement "_pg3_0" already exists')

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    with pytest.raises(ValueError, match="failed to write to Supabase/PostgreSQL") as exc_info:
        upsert_supabase_symbols(
            FakeConnection(),
            [
                {
                    "market": "NASDAQ",
                    "symbol": "AAPL",
                    "standard_code": None,
                    "realtime_symbol": "DNASAAPL",
                    "korean_name": "애플",
                    "english_name": "Apple Inc.",
                    "security_type": "stock",
                    "currency": "USD",
                    "exchange_id": "NAS",
                    "exchange_code": "NAS",
                    "exchange_name": "NASDAQ",
                    "country_code": "US",
                    "listed_date": None,
                    "base_price": None,
                    "lot_size": None,
                    "raw_source": "nasmst.cod",
                    "raw": '{"symbol": "AAPL"}',
                    "downloaded_at": "2026-05-07T00:00:00+09:00",
                }
            ],
        )

    assert "prepared statements are disabled automatically" in str(exc_info.value)


def test_insert_supabase_ohlcv_bars_uses_trade_date_conflict_key() -> None:
    executed: list[tuple[str, tuple[object, ...] | None]] = []

    class FakeCursor:
        rowcount = 1

    class FakeConnection:
        def execute(self, statement: str, parameters: tuple[object, ...]):
            executed.append((statement, parameters))
            return FakeCursor()

        def commit(self) -> None:
            executed.append(("COMMIT", None))

    inserted = insert_supabase_ohlcv_bars(
        FakeConnection(),
        [
            {
                "market": "NASDAQ",
                "symbol": "AAPL",
                "interval": "1d",
                "timestamp": "2026-05-07",
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 107.0,
                "volume": 1000,
                "change": 7.0,
                "change_rate": 7.0,
                "amount": 107000.0,
            }
        ],
    )

    assert inserted == 1
    assert "trade_date" in executed[0][0]
    assert "ON CONFLICT (market, symbol, interval, trade_date) DO NOTHING" in executed[0][0]
    assert executed[0][1][0:4] == ("NASDAQ", "AAPL", "1d", "2026-05-07")
    assert executed[-1] == ("COMMIT", None)
