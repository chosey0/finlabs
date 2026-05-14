from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb


@dataclass(frozen=True, slots=True)
class CandleBar:
    market: str
    symbol: str
    interval: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, slots=True)
class CandleSplit:
    train: tuple[CandleBar, ...]
    val: tuple[CandleBar, ...]
    test: tuple[CandleBar, ...]


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
    - daily: ``1d`` or ``daily`` from ``ohlcv_bars``
    - overseas minutes: ``1m``, ``5m``, ``1min``, ``5minutes`` from ``overseas_minute_bars``
    """
    _validate_limit(limit)
    normalized_interval = interval.strip().lower()
    minute_interval = _parse_minute_interval(normalized_interval)

    with duckdb.connect(str(Path(warehouse_path).expanduser()), read_only=True) as connection:
        if normalized_interval in {"1d", "daily"}:
            rows = _load_daily_rows(
                connection,
                market=market,
                symbol=symbol,
                interval="1d",
                limit=limit,
            )
        elif minute_interval is not None:
            rows = _load_minute_rows(
                connection,
                market=market,
                symbol=symbol,
                interval_minutes=minute_interval,
                limit=limit,
            )
        else:
            raise ValueError(
                "unsupported interval. Use '1d' for daily candles or minute intervals like '1m', '5m', '1min'."
            )

    return tuple(rows)


def split_by_date(
    candles: Iterable[CandleBar],
    *,
    train_end: str,
    val_end: str,
) -> CandleSplit:
    """Split candles by timestamp using inclusive train/val boundaries."""
    train: list[CandleBar] = []
    val: list[CandleBar] = []
    test: list[CandleBar] = []

    for candle in sorted(candles, key=lambda item: item.timestamp):
        if candle.timestamp <= train_end:
            train.append(candle)
        elif candle.timestamp <= val_end:
            val.append(candle)
        else:
            test.append(candle)

    return CandleSplit(train=tuple(train), val=tuple(val), test=tuple(test))


def split_by_ratio(
    candles: Iterable[CandleBar],
    *,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
) -> CandleSplit:
    """Split candles by chronological ratio without shuffling.

    This is useful for minute datasets where absolute date boundaries are not known
    before loading the data. The remaining tail becomes the test split.
    """
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")
    if not 0 <= val_ratio < 1:
        raise ValueError("val_ratio must be between 0 and 1")
    if train_ratio + val_ratio >= 1:
        raise ValueError("train_ratio + val_ratio must be less than 1")

    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    train_end_index = int(len(ordered) * train_ratio)
    val_end_index = train_end_index + int(len(ordered) * val_ratio)

    return CandleSplit(
        train=ordered[:train_end_index],
        val=ordered[train_end_index:val_end_index],
        test=ordered[val_end_index:],
    )


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
