"""Broker-agnostic warehouse read repositories.

This module is the single source of SELECT SQL for candle reads. CLI,
dashboard, and research callers should route through orchestration/query rather
than duplicating SQL against warehouse tables.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from modules.domain.market_data import CandleBar


def load_candles(
    warehouse_path: str | Path,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
) -> tuple[CandleBar, ...]:
    """Load OHLCV candles from a DuckDB warehouse in timestamp order.

    Supported intervals:
    - daily family from ``ohlcv_bars``: ``1d``/``daily``, ``1w``, ``1mo``
    - overseas minutes: ``1m``, ``5m``, ``1min``, ``5minutes`` from
      ``overseas_minute_bars``
    """

    _validate_limit(limit)
    normalized_interval = interval.strip().lower()
    minute_interval = _parse_minute_interval(normalized_interval)
    daily_interval = "1d" if normalized_interval == "daily" else normalized_interval

    with duckdb.connect(str(Path(warehouse_path).expanduser()), read_only=True) as connection:
        if daily_interval in {"1d", "1w", "1mo"}:
            return _load_daily_rows(
                connection,
                market=market,
                symbol=symbol,
                interval=daily_interval,
                limit=limit,
            )
        if minute_interval is not None:
            return _load_minute_rows(
                connection,
                market=market,
                symbol=symbol,
                interval_minutes=minute_interval,
                limit=limit,
            )

    raise ValueError(
        "unsupported interval. Use '1d' for daily candles or minute intervals like '1m', '5m', '1min'."
    )


def list_available_series(warehouse_path: str | Path) -> list[dict[str, str]]:
    """Return distinct (market, symbol, interval) series stored in the warehouse."""

    path = Path(warehouse_path).expanduser()
    if not path.exists():
        return []

    with duckdb.connect(str(path), read_only=True) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        series: list[dict[str, str]] = []
        if "ohlcv_bars" in tables:
            rows = connection.execute(
                "SELECT DISTINCT market, symbol, interval FROM ohlcv_bars"
            ).fetchall()
            series.extend({"market": m, "symbol": s, "interval": i} for m, s, i in rows)
        if "overseas_minute_bars" in tables:
            rows = connection.execute(
                "SELECT DISTINCT market, symbol, interval_minutes FROM overseas_minute_bars"
            ).fetchall()
            series.extend(
                {"market": m, "symbol": s, "interval": f"{int(mins)}m"} for m, s, mins in rows
            )
    return sorted(series, key=lambda r: (r["symbol"], r["interval"]))


def _validate_limit(limit: int | None) -> None:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")


def _parse_minute_interval(interval: str) -> int | None:
    match = re.fullmatch(r"(\d+)\s*(m|min|minute|minutes)", interval)
    if match is None:
        return None
    interval_minutes = int(match.group(1))
    if interval_minutes <= 0:
        raise ValueError("minute interval must be positive")
    return interval_minutes


def _load_daily_rows(
    connection,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None,
) -> tuple[CandleBar, ...]:
    query = """
        SELECT market, symbol, interval, timestamp, open, high, low, close, volume
        FROM ohlcv_bars
        WHERE market = ? AND lower(symbol) = lower(?) AND interval = ?
        ORDER BY timestamp ASC
    """
    params: list[object] = [market, symbol, interval]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    rows = connection.execute(query, params).fetchall()
    return tuple(
        CandleBar(
            market=str(row[0]),
            symbol=str(row[1]),
            interval=str(row[2]),
            timestamp=str(row[3]),
            open=float(row[4]),
            high=float(row[5]),
            low=float(row[6]),
            close=float(row[7]),
            volume=int(row[8]),
        )
        for row in rows
    )


def _load_minute_rows(
    connection,
    *,
    market: str,
    symbol: str,
    interval_minutes: int,
    limit: int | None,
) -> tuple[CandleBar, ...]:
    query = """
        SELECT
            market,
            symbol,
            interval_minutes,
            local_date || ' ' || local_time AS timestamp,
            open,
            high,
            low,
            close,
            volume
        FROM overseas_minute_bars
        WHERE market = ? AND lower(symbol) = lower(?) AND interval_minutes = ?
        ORDER BY local_date ASC, local_time ASC
    """
    params: list[object] = [market, symbol, interval_minutes]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    rows = connection.execute(query, params).fetchall()
    return tuple(
        CandleBar(
            market=str(row[0]),
            symbol=str(row[1]),
            interval=f"{int(row[2])}m",
            timestamp=str(row[3]),
            open=float(row[4]),
            high=float(row[5]),
            low=float(row[6]),
            close=float(row[7]),
            volume=int(row[8]),
        )
        for row in rows
    )

