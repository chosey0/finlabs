from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .labels import FractalEvent, FractalLabelConfig, compute_fractal_events, moving_average


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass(frozen=True, slots=True)
class FractalSample:
    """A single supervised sample ending at a labeled fractal candle."""

    features: np.ndarray
    label: int
    event: FractalEvent


FEATURE_COLUMNS = ("open", "high", "low", "close", "short_ma", "long_ma")


def load_fractal_candles_from_warehouse(
    warehouse_path: str | Path,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
) -> tuple[Candle, ...]:
    """Load DuckDB OHLCV candles and convert them to fractal ``Candle`` objects.

    This delegates the actual DuckDB query to ``research.tokenizers.data`` so
    fractal research does not duplicate warehouse SQL. Returned candles preserve
    the tokenizers loader's chronological order.
    """
    from research.tokenizers.data import load_candles

    bars = load_candles(
        warehouse_path,
        market=market,
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    return tuple(
        Candle(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=float(bar.volume),
        )
        for bar in bars
    )


def build_fractal_samples(
    candles: Iterable[Candle],
    *,
    max_len: int = 20,
    label_config: FractalLabelConfig | None = None,
    standardize: bool = True,
) -> tuple[FractalSample, ...]:
    """Build samples from OHLC candles.

    Each sample contains candles up to and including the fractal event candle.
    The label itself is computed with a centered window, so label generation
    uses future candles while the model input does not.
    """
    if max_len < 2:
        raise ValueError("max_len must be at least 2")

    ordered = tuple(candles)
    if len(ordered) < max_len:
        return ()

    cfg = label_config or FractalLabelConfig()
    cfg.validate()

    opens = tuple(candle.open for candle in ordered)
    highs = tuple(candle.high for candle in ordered)
    lows = tuple(candle.low for candle in ordered)
    closes = tuple(candle.close for candle in ordered)
    short_ma = moving_average(closes, cfg.short_ma)
    long_ma = moving_average(closes, cfg.long_ma)

    events = compute_fractal_events(highs, lows, short_ma, long_ma, closes=closes, config=cfg)
    samples: list[FractalSample] = []

    for event in events:
        if event.index + 1 < 2:
            continue

        start = max(0, event.index + 1 - max_len)
        features = _feature_array(
            opens[start : event.index + 1],
            highs[start : event.index + 1],
            lows[start : event.index + 1],
            closes[start : event.index + 1],
            short_ma[start : event.index + 1],
            long_ma[start : event.index + 1],
        )
        if features.shape[0] < 2:
            continue
        if standardize:
            features = standardize_features(features)
        samples.append(FractalSample(features=features, label=int(event.label), event=event))

    return tuple(samples)


def pad_feature_batch(samples: Sequence[FractalSample], *, padding_value: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pad variable-length feature arrays to a dense batch."""
    if not samples:
        raise ValueError("samples must not be empty")

    batch_size = len(samples)
    max_len = max(sample.features.shape[0] for sample in samples)
    feature_dim = samples[0].features.shape[1]

    data = np.full((batch_size, max_len, feature_dim), padding_value, dtype=np.float32)
    labels = np.empty(batch_size, dtype=np.int64)
    lengths = np.empty(batch_size, dtype=np.int64)

    for index, sample in enumerate(samples):
        if sample.features.shape[1] != feature_dim:
            raise ValueError("all samples must have the same feature dimension")
        length = sample.features.shape[0]
        data[index, :length, :] = sample.features
        labels[index] = sample.label
        lengths[index] = length

    return data, labels, lengths


def standardize_features(features: np.ndarray) -> np.ndarray:
    """Standardize each sample independently, matching the old Fractal project."""
    values = np.asarray(features, dtype=np.float32)
    mean = values.mean(axis=0, keepdims=True)
    std = values.std(axis=0, keepdims=True)
    std = np.where(std == 0, 1.0, std)
    return (values - mean) / std


def _feature_array(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    short_ma: Sequence[float | None],
    long_ma: Sequence[float | None],
) -> np.ndarray:
    rows: list[tuple[float, float, float, float, float, float]] = []
    for values in zip(opens, highs, lows, closes, short_ma, long_ma, strict=True):
        open_, high, low, close, short_value, long_value = values
        rows.append(
            (
                float(open_),
                float(high),
                float(low),
                float(close),
                float(short_value if short_value is not None else close),
                float(long_value if long_value is not None else close),
            )
        )
    return np.asarray(rows, dtype=np.float32)
