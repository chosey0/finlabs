from __future__ import annotations

import csv
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from uuid import uuid4

from kis_cli.utils.time import now_kst_iso


def insert_symbol(
    connection,
    *,
    market: str,
    symbol: str,
    name: str,
) -> bool:
    before = _count_rows(connection, "symbols")
    stored_at = now_kst_iso()
    connection.execute(
        """
        INSERT INTO symbols (
            market, symbol, korean_name, raw_source, raw, downloaded_at, created_at, updated_at
        )
        VALUES (?, ?, ?, '', '{}', ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [market, symbol, name, stored_at, stored_at, stored_at],
    )
    return _count_rows(connection, "symbols") > before


def upsert_symbols(connection, records: Iterable[dict[str, object]]) -> int:
    rows = list(records)
    if not rows:
        return 0
    stored_at = now_kst_iso()
    temp_table = f"tmp_symbols_{uuid4().hex}"
    connection.execute(
        f"""
        CREATE TEMP TABLE "{temp_table}" (
            market VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            standard_code VARCHAR,
            realtime_symbol VARCHAR,
            korean_name VARCHAR,
            english_name VARCHAR,
            security_type VARCHAR,
            currency VARCHAR,
            exchange_id VARCHAR,
            exchange_code VARCHAR,
            exchange_name VARCHAR,
            country_code VARCHAR,
            listed_date VARCHAR,
            base_price BIGINT,
            lot_size BIGINT,
            raw_source VARCHAR NOT NULL,
            raw VARCHAR NOT NULL,
            downloaded_at VARCHAR NOT NULL
        )
        """
    )
    csv_path = _write_symbol_staging_csv(rows)
    transaction_started = False
    try:
        connection.execute(
            f"""
            COPY "{temp_table}"
            FROM {_quote_literal(str(csv_path))}
            (FORMAT CSV, HEADER false, NULL '\\N')
            """
        )
        connection.execute("BEGIN TRANSACTION")
        transaction_started = True
        connection.execute(
            f"""
            DELETE FROM symbols
            WHERE market IN (SELECT DISTINCT market FROM "{temp_table}")
            """
        )
        connection.execute(
            f"""
            INSERT INTO symbols (
                market, symbol, standard_code, realtime_symbol, korean_name, english_name,
                security_type, currency, exchange_id, exchange_code, exchange_name,
                country_code, listed_date, base_price, lot_size, raw_source, raw,
                downloaded_at, created_at, updated_at
            )
            SELECT
                market, symbol, standard_code, realtime_symbol, korean_name, english_name,
                security_type, currency, exchange_id, exchange_code, exchange_name,
                country_code, listed_date, base_price, lot_size, raw_source, raw::JSON,
                downloaded_at, {_quote_literal(stored_at)}, {_quote_literal(stored_at)}
            FROM (
                SELECT *,
                    row_number() OVER (
                        PARTITION BY market, symbol
                        ORDER BY downloaded_at DESC
                    ) AS row_number
                FROM "{temp_table}"
            )
            WHERE row_number = 1
            """
        )
        connection.execute("COMMIT")
    except Exception:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute(f'DROP TABLE IF EXISTS "{temp_table}"')
        csv_path.unlink(missing_ok=True)
    return len(rows)


def _write_symbol_staging_csv(rows: Sequence[dict[str, object]]) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        prefix="kis-cli-symbols-",
        suffix=".csv",
        delete=False,
    ) as file:
        writer = csv.writer(file)
        for row in rows:
            writer.writerow(
                [
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
                    row["listed_date"],
                    _csv_value(row["base_price"]),
                    _csv_value(row["lot_size"]),
                    row["raw_source"],
                    row["raw"],
                    row["downloaded_at"],
                ]
            )
        return Path(file.name)


def _csv_value(value: object) -> object:
    return r"\N" if value is None else value


def _write_ohlcv_staging_csv(rows: Sequence[dict[str, object]]) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        prefix="kis-cli-ohlcv-",
        suffix=".csv",
        delete=False,
    ) as file:
        writer = csv.writer(file)
        for row in rows:
            writer.writerow(
                [
                    row["market"],
                    row["symbol"],
                    row["interval"],
                    row["timestamp"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    _csv_value(row.get("change")),
                    _csv_value(row.get("change_rate")),
                    _csv_value(row.get("amount")),
                ]
            )
        return Path(file.name)


def search_symbols(
    connection,
    *,
    query: str,
    market: str | None = None,
    limit: int = 20,
) -> Sequence[dict[str, object]]:
    exact = query
    prefix = f"{query}%"
    contains = f"%{query}%"
    params: list[object] = [contains, contains, contains]
    where = "(symbol ILIKE ? OR korean_name ILIKE ? OR english_name ILIKE ?)"
    if market:
        where = f"market = ? AND {where}"
        params.insert(0, market)
    params.extend([exact, exact, exact, prefix, prefix, prefix, contains, contains, contains, limit])
    rows = connection.execute(
        f"""
        SELECT market, symbol, realtime_symbol, korean_name, english_name, currency, security_type
        FROM symbols
        WHERE {where}
        ORDER BY
            CASE
                WHEN symbol ILIKE ? THEN 0
                WHEN korean_name ILIKE ? THEN 1
                WHEN english_name ILIKE ? THEN 1
                WHEN symbol ILIKE ? THEN 2
                WHEN korean_name ILIKE ? THEN 3
                WHEN english_name ILIKE ? THEN 3
                WHEN symbol ILIKE ? THEN 4
                WHEN korean_name ILIKE ? THEN 5
                WHEN english_name ILIKE ? THEN 5
                ELSE 6
            END,
            LEAST(
                length(symbol),
                length(COALESCE(NULLIF(korean_name, ''), symbol)),
                length(COALESCE(NULLIF(english_name, ''), symbol))
            ),
            market,
            symbol
        LIMIT ?
        """,
        params,
    )
    return _dict_rows(rows)


def find_symbol_markets(connection, *, symbol: str) -> Sequence[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT market
        FROM symbols
        WHERE lower(symbol) = lower(?)
        ORDER BY market
        """,
        [symbol],
    ).fetchall()
    return [row[0] for row in rows]


def insert_ohlcv_bar(
    connection,
    *,
    market: str,
    symbol: str,
    interval: str,
    timestamp: str,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    change: float | None = None,
    change_rate: float | None = None,
    amount: float | None = None,
) -> bool:
    before = _count_rows(connection, "ohlcv_bars")
    stored_at = now_kst_iso()
    connection.execute(
        """
        INSERT INTO ohlcv_bars (
            market, symbol, interval, timestamp, open, high, low, close, volume,
            change, change_rate, amount, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [
            market,
            symbol,
            interval,
            timestamp,
            open,
            high,
            low,
            close,
            volume,
            change,
            change_rate,
            amount,
            stored_at,
        ],
    )
    return _count_rows(connection, "ohlcv_bars") > before


def insert_ohlcv_bars(
    connection,
    records: Iterable[dict[str, object]],
) -> int:
    rows = list(records)
    if not rows:
        return 0
    stored_at = now_kst_iso()
    temp_table = f"tmp_ohlcv_bars_{uuid4().hex}"
    connection.execute(
        f"""
        CREATE TEMP TABLE "{temp_table}" (
            market VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            interval VARCHAR NOT NULL,
            timestamp VARCHAR NOT NULL,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume BIGINT NOT NULL,
            change DOUBLE,
            change_rate DOUBLE,
            amount DOUBLE
        )
        """
    )
    csv_path = _write_ohlcv_staging_csv(rows)
    transaction_started = False
    try:
        connection.execute(
            f"""
            COPY "{temp_table}"
            FROM {_quote_literal(str(csv_path))}
            (FORMAT CSV, HEADER false, NULLSTR '\\N')
            """
        )
        connection.execute("BEGIN TRANSACTION")
        transaction_started = True
        inserted = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT *,
                    row_number() OVER (
                        PARTITION BY market, symbol, interval, timestamp
                        ORDER BY timestamp DESC
                    ) AS row_number
                FROM "{temp_table}"
            ) source
            WHERE row_number = 1
                AND NOT EXISTS (
                    SELECT 1
                    FROM ohlcv_bars target
                    WHERE target.market = source.market
                        AND target.symbol = source.symbol
                        AND target.interval = source.interval
                        AND target.timestamp = source.timestamp
                )
            """
        ).fetchone()[0]
        connection.execute(
            f"""
            INSERT INTO ohlcv_bars (
                market, symbol, interval, timestamp, open, high, low, close, volume,
                change, change_rate, amount, created_at
            )
            SELECT
                market, symbol, interval, timestamp, open, high, low, close, volume,
                change, change_rate, amount,
                {_quote_literal(stored_at)}
            FROM (
                SELECT *,
                    row_number() OVER (
                        PARTITION BY market, symbol, interval, timestamp
                        ORDER BY timestamp DESC
                    ) AS row_number
                FROM "{temp_table}"
            ) source
            WHERE row_number = 1
                AND NOT EXISTS (
                    SELECT 1
                    FROM ohlcv_bars target
                    WHERE target.market = source.market
                        AND target.symbol = source.symbol
                        AND target.interval = source.interval
                        AND target.timestamp = source.timestamp
                )
            """
        )
        connection.execute("COMMIT")
    except Exception:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute(f'DROP TABLE IF EXISTS "{temp_table}"')
        csv_path.unlink(missing_ok=True)
    return int(inserted)


def list_ohlcv_bars(
    connection,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
) -> Sequence[dict[str, object]]:
    sql = """
        SELECT market, symbol, interval, timestamp, open, high, low, close, volume,
            change, change_rate, amount
        FROM ohlcv_bars
        WHERE market = ? AND symbol = ? AND interval = ?
        ORDER BY timestamp DESC
    """
    params: list[object] = [market, symbol, interval]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return _dict_rows(connection.execute(sql, params))


def query_daily_ohlcv_bars(
    connection,
    *,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = 20,
) -> Sequence[dict[str, object]]:
    where = "symbol = ? AND interval = '1d'"
    params: list[object] = [symbol]
    if start is not None:
        where += " AND timestamp >= ?"
        params.append(start)
    if end is not None:
        where += " AND timestamp <= ?"
        params.append(end)

    sql = f"""
        SELECT market, symbol, interval, timestamp, open, high, low, close, volume,
            change, change_rate, amount
        FROM ohlcv_bars
        WHERE {where}
        ORDER BY timestamp DESC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return _dict_rows(connection.execute(sql, params))


def insert_realtime_tick(
    connection,
    *,
    market: str,
    symbol: str,
    exchange_ts: str,
    received_at: str,
    received_seq: int,
    seq: int,
    price: float,
    volume: int,
) -> bool:
    before = _count_rows(connection, "realtime_ticks")
    stored_at = now_kst_iso()
    connection.execute(
        """
        INSERT INTO realtime_ticks (
            market, symbol, exchange_ts, received_at, received_seq, seq, price, volume, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [market, symbol, exchange_ts, received_at, received_seq, seq, price, volume, stored_at],
    )
    return _count_rows(connection, "realtime_ticks") > before


def _count_rows(connection, table_name: str) -> int:
    return connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]


def _dict_rows(cursor) -> list[dict[str, object]]:
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
