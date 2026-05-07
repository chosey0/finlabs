from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence


def insert_symbol(
    connection: sqlite3.Connection,
    *,
    market: str,
    symbol: str,
    name: str,
) -> bool:
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO symbols (
            market, symbol, korean_name, raw_source, raw, downloaded_at
        )
        VALUES (?, ?, ?, '', '{}', CURRENT_TIMESTAMP)
        """,
        (market, symbol, name),
    )
    return cursor.rowcount > 0


def upsert_symbols(connection: sqlite3.Connection, records: Iterable[dict[str, object]]) -> int:
    rows = list(records)
    if not rows:
        return 0
    connection.executemany(
        """
        INSERT INTO symbols (
            market, symbol, standard_code, realtime_symbol, korean_name, english_name,
            security_type, currency, exchange_id, exchange_code, exchange_name,
            country_code, listed_date, base_price, lot_size, raw_source, raw,
            downloaded_at, updated_at
        )
        VALUES (
            :market, :symbol, :standard_code, :realtime_symbol, :korean_name, :english_name,
            :security_type, :currency, :exchange_id, :exchange_code, :exchange_name,
            :country_code, :listed_date, :base_price, :lot_size, :raw_source, :raw,
            :downloaded_at, CURRENT_TIMESTAMP
        )
        ON CONFLICT(market, symbol) DO UPDATE SET
            standard_code = excluded.standard_code,
            realtime_symbol = excluded.realtime_symbol,
            korean_name = excluded.korean_name,
            english_name = excluded.english_name,
            security_type = excluded.security_type,
            currency = excluded.currency,
            exchange_id = excluded.exchange_id,
            exchange_code = excluded.exchange_code,
            exchange_name = excluded.exchange_name,
            country_code = excluded.country_code,
            listed_date = excluded.listed_date,
            base_price = excluded.base_price,
            lot_size = excluded.lot_size,
            raw_source = excluded.raw_source,
            raw = excluded.raw,
            downloaded_at = excluded.downloaded_at,
            updated_at = CURRENT_TIMESTAMP
        """,
        rows,
    )
    return len(rows)


def search_symbols(
    connection: sqlite3.Connection,
    *,
    query: str,
    market: str | None = None,
    limit: int = 20,
) -> Sequence[sqlite3.Row]:
    params: dict[str, object] = {
        "exact": query,
        "prefix": f"{query}%",
        "contains": f"%{query}%",
        "limit": limit,
    }
    where = "(symbol LIKE :contains OR korean_name LIKE :contains OR english_name LIKE :contains)"
    if market:
        where = f"market = :market AND {where}"
        params["market"] = market
    return connection.execute(
        f"""
        SELECT market, symbol, realtime_symbol, korean_name, english_name, currency, security_type
        FROM symbols
        WHERE {where}
        ORDER BY
            CASE
                WHEN symbol LIKE :exact THEN 0
                WHEN korean_name LIKE :exact THEN 1
                WHEN english_name LIKE :exact THEN 1
                WHEN symbol LIKE :prefix THEN 2
                WHEN korean_name LIKE :prefix THEN 3
                WHEN english_name LIKE :prefix THEN 3
                WHEN symbol LIKE :contains THEN 4
                WHEN korean_name LIKE :contains THEN 5
                WHEN english_name LIKE :contains THEN 5
                ELSE 6
            END,
            MIN(
                length(symbol),
                length(COALESCE(NULLIF(korean_name, ''), symbol)),
                length(COALESCE(NULLIF(english_name, ''), symbol))
            ),
            market,
            symbol
        LIMIT :limit
        """,
        params,
    ).fetchall()


def find_symbol_markets(connection: sqlite3.Connection, *, symbol: str) -> Sequence[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT market
        FROM symbols
        WHERE symbol = ? COLLATE NOCASE
        ORDER BY market
        """,
        (symbol,),
    ).fetchall()
    return [row["market"] for row in rows]


def insert_ohlcv_bar(
    connection: sqlite3.Connection,
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
) -> bool:
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO ohlcv_bars (
            market, symbol, interval, timestamp, open, high, low, close, volume
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (market, symbol, interval, timestamp, open, high, low, close, volume),
    )
    return cursor.rowcount > 0


def insert_ohlcv_bars(
    connection: sqlite3.Connection,
    records: Iterable[dict[str, object]],
) -> int:
    rows = list(records)
    if not rows:
        return 0
    before = connection.total_changes
    connection.executemany(
        """
        INSERT OR IGNORE INTO ohlcv_bars (
            market, symbol, interval, timestamp, open, high, low, close, volume
        )
        VALUES (
            :market, :symbol, :interval, :timestamp, :open, :high, :low, :close, :volume
        )
        """,
        rows,
    )
    return connection.total_changes - before


def list_ohlcv_bars(
    connection: sqlite3.Connection,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
) -> Sequence[sqlite3.Row]:
    sql = """
        SELECT market, symbol, interval, timestamp, open, high, low, close, volume
        FROM ohlcv_bars
        WHERE market = ? AND symbol = ? AND interval = ?
        ORDER BY timestamp
    """
    params: list[object] = [market, symbol, interval]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return connection.execute(sql, params).fetchall()


def query_daily_ohlcv_bars(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = 20,
) -> Sequence[sqlite3.Row]:
    where = "symbol = ? AND interval = '1d'"
    params: list[object] = [symbol]
    if start is not None:
        where += " AND timestamp >= ?"
        params.append(start)
    if end is not None:
        where += " AND timestamp <= ?"
        params.append(end)

    sql = f"""
        SELECT market, symbol, interval, timestamp, open, high, low, close, volume
        FROM (
            SELECT market, symbol, interval, timestamp, open, high, low, close, volume
            FROM ohlcv_bars
            WHERE {where}
            ORDER BY timestamp DESC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    sql += """
        )
        ORDER BY timestamp
    """
    return connection.execute(sql, params).fetchall()


def insert_realtime_tick(
    connection: sqlite3.Connection,
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
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO realtime_ticks (
            market, symbol, exchange_ts, received_at, received_seq, seq, price, volume
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (market, symbol, exchange_ts, received_at, received_seq, seq, price, volume),
    )
    return cursor.rowcount > 0
