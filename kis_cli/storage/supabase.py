from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, unquote

from kis_cli.utils.time import now_kst_iso
from kis_cli.storage.supabase_schema import SUPABASE_TABLE_NAMES, supabase_schema_sql

SUPABASE_DSN_ENV = "KISCLI_SUPABASE_DB_DSN"


@dataclass(frozen=True)
class SupabaseDatabaseInitResult:
    dsn_env: str
    tables: tuple[str, ...]


def init_supabase_database(
    *,
    dsn: str | None = None,
    dsn_env: str = SUPABASE_DSN_ENV,
    connect_factory: Callable[[str], object] | None = None,
) -> SupabaseDatabaseInitResult:
    with connect_supabase(dsn=dsn, dsn_env=dsn_env, connect_factory=connect_factory) as connection:
        for statement in supabase_schema_statements():
            connection.execute(statement)
        commit = getattr(connection, "commit", None)
        if commit is not None:
            commit()

    return SupabaseDatabaseInitResult(dsn_env=dsn_env, tables=SUPABASE_TABLE_NAMES)


def connect_supabase(
    *,
    dsn: str | None = None,
    dsn_env: str = SUPABASE_DSN_ENV,
    connect_factory: Callable[[str], object] | None = None,
):
    resolved_dsn = dsn or os.environ.get(dsn_env)
    if not resolved_dsn:
        raise ValueError(f"missing Supabase PostgreSQL DSN environment variable: {dsn_env}")
    return _connect(normalize_postgres_dsn(resolved_dsn), connect_factory=connect_factory)


def normalize_postgres_dsn(dsn: str) -> str:
    stripped = dsn.strip()
    for scheme in ("postgresql://", "postgres://"):
        if stripped.startswith(scheme):
            return _encode_url_credentials(stripped, scheme)
    return stripped


def supabase_schema_statements() -> tuple[str, ...]:
    return tuple(
        statement.strip()
        for statement in supabase_schema_sql().split(";")
        if statement.strip()
    )


def _connect(dsn: str, *, connect_factory: Callable[[str], object] | None = None):
    if connect_factory is not None:
        return connect_factory(dsn)

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for Supabase/PostgreSQL storage; "
            "install kis-cli with the postgres extra"
        ) from exc

    try:
        return psycopg.connect(dsn)
    except psycopg.Error as exc:
        details = _sanitize_connection_error(str(exc))
        suffix = f" Details: {details}" if details else ""
        raise ValueError(
            "failed to connect to Supabase/PostgreSQL. "
            "Check that the DSN is a valid PostgreSQL connection string."
            f"{suffix}"
        ) from exc


def _encode_url_credentials(dsn: str, scheme: str) -> str:
    rest = dsn[len(scheme):]
    if "@" not in rest:
        return dsn

    userinfo, host_and_path = rest.rsplit("@", 1)
    if ":" not in userinfo:
        return dsn

    username, password = userinfo.split(":", 1)
    encoded_username = quote(unquote(username), safe="")
    encoded_password = quote(unquote(password), safe="")
    return f"{scheme}{encoded_username}:{encoded_password}@{host_and_path}"


def upsert_supabase_symbols(connection, records) -> int:
    rows = list(records)
    if not rows:
        return 0
    stored_at = now_kst_iso()
    statement = """
        INSERT INTO symbols (
            market, symbol, standard_code, realtime_symbol, korean_name, english_name,
            security_type, currency, exchange_id, exchange_code, exchange_name,
            country_code, listed_date, base_price, lot_size, raw_source, raw,
            downloaded_at, created_at, updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s
        )
        ON CONFLICT (market, symbol) DO UPDATE SET
            standard_code = EXCLUDED.standard_code,
            realtime_symbol = EXCLUDED.realtime_symbol,
            korean_name = EXCLUDED.korean_name,
            english_name = EXCLUDED.english_name,
            security_type = EXCLUDED.security_type,
            currency = EXCLUDED.currency,
            exchange_id = EXCLUDED.exchange_id,
            exchange_code = EXCLUDED.exchange_code,
            exchange_name = EXCLUDED.exchange_name,
            country_code = EXCLUDED.country_code,
            listed_date = EXCLUDED.listed_date,
            base_price = EXCLUDED.base_price,
            lot_size = EXCLUDED.lot_size,
            raw_source = EXCLUDED.raw_source,
            raw = EXCLUDED.raw,
            downloaded_at = EXCLUDED.downloaded_at,
            updated_at = EXCLUDED.updated_at
    """
    parameters = [
        (
            row["market"],
            row["symbol"],
            row["standard_code"],
            row["realtime_symbol"],
            row["korean_name"],
            row["english_name"],
            row["security_type"],
            row["currency"],
            row["exchange_id"],
            row["exchange_code"],
            row["exchange_name"],
            row["country_code"],
            _none_if_blank(row["listed_date"]),
            row["base_price"],
            row["lot_size"],
            row["raw_source"],
            row["raw"],
            row["downloaded_at"],
            stored_at,
            stored_at,
        )
        for row in rows
    ]
    _executemany(connection, statement, parameters)
    _commit(connection)
    return len(rows)


def insert_supabase_ohlcv_bars(connection, records) -> int:
    rows = list(records)
    if not rows:
        return 0
    fetched_at = now_kst_iso()
    statement = """
        INSERT INTO ohlcv_bars (
            market, symbol, interval, trade_date, open, high, low, close, volume,
            change, change_rate, amount, fetched_at, created_at, updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (market, symbol, interval, trade_date) DO NOTHING
    """
    inserted = 0
    for row in _deduplicate_ohlcv_rows(rows):
        cursor = connection.execute(
            statement,
            (
                row["market"],
                row["symbol"],
                row["interval"],
                row["timestamp"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                row.get("change"),
                row.get("change_rate"),
                row.get("amount"),
                fetched_at,
                fetched_at,
                fetched_at,
            ),
        )
        inserted += max(int(getattr(cursor, "rowcount", 0)), 0)
    _commit(connection)
    return inserted


def _executemany(connection, statement: str, parameters: list[tuple[object, ...]]) -> None:
    cursor = getattr(connection, "cursor", None)
    if cursor is None:
        for parameter_set in parameters:
            connection.execute(statement, parameter_set)
        return
    with connection.cursor() as cursor_object:
        cursor_object.executemany(statement, parameters)


def _commit(connection) -> None:
    commit = getattr(connection, "commit", None)
    if commit is not None:
        commit()


def _deduplicate_ohlcv_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    deduplicated: dict[tuple[object, object, object, object], dict[str, object]] = {}
    for row in rows:
        deduplicated[(row["market"], row["symbol"], row["interval"], row["timestamp"])] = row
    return list(deduplicated.values())


def _none_if_blank(value: object) -> object | None:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _sanitize_connection_error(message: str) -> str:
    masked = re.sub(
        r"(postgres(?:ql)?://[^:\s/@]+:)([^@\s]+)(@)",
        r"\1********\3",
        message,
    )
    masked = re.sub(
        r"(\bpassword=)([^\s]+)",
        r"\1********",
        masked,
        flags=re.IGNORECASE,
    )
    return masked.strip()
