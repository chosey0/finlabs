from __future__ import annotations

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
    """Load OHLCV candles from a DuckDB warehouse in timestamp order."""
    query = """
        SELECT market, symbol, interval, timestamp, open, high, low, close, volume
        FROM ohlcv_bars
        WHERE market = ? AND symbol = ? AND interval = ?
        ORDER BY timestamp ASC
    """
    params: list[object] = [market, symbol, interval]
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        query += " LIMIT ?"
        params.append(limit)

    with duckdb.connect(str(Path(warehouse_path).expanduser()), read_only=True) as connection:
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
