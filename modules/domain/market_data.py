"""Canonical market-data contracts shared across FinLabs layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CandleBar:
    """Broker-agnostic OHLCV candle stored in the warehouse."""

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

