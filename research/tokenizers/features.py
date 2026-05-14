from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable

from research.tokenizers.data import CandleBar


@dataclass(frozen=True, slots=True)
class VolumeContext:
    mean: float
    std: float


@dataclass(frozen=True, slots=True)
class FeatureVector:
    body_ratio: float
    upper_ratio: float
    lower_ratio: float
    close_position: float
    range_return: float
    direction: float
    volume_state: float

    def as_tuple(self) -> tuple[float, float, float, float, float, float, float]:
        return (
            self.body_ratio,
            self.upper_ratio,
            self.lower_ratio,
            self.close_position,
            self.range_return,
            self.direction,
            self.volume_state,
        )


def build_volume_context(candles: Iterable[CandleBar]) -> VolumeContext:
    volumes = [float(candle.volume) for candle in candles]
    if not volumes:
        return VolumeContext(mean=0.0, std=0.0)

    mean = sum(volumes) / len(volumes)
    variance = sum((volume - mean) ** 2 for volume in volumes) / len(volumes)
    return VolumeContext(mean=mean, std=sqrt(variance))


def extract_features(candle: CandleBar, volume_context: VolumeContext | None = None) -> FeatureVector:
    """Convert one OHLCV candle into a deterministic 7D feature vector."""
    total_range = max(candle.high - candle.low, 0.0)
    if total_range == 0.0:
        body_ratio = 0.0
        upper_ratio = 0.0
        lower_ratio = 0.0
        close_position = 0.5
    else:
        body_top = max(candle.open, candle.close)
        body_bottom = min(candle.open, candle.close)
        body_ratio = abs(candle.close - candle.open) / total_range
        upper_ratio = max(candle.high - body_top, 0.0) / total_range
        lower_ratio = max(body_bottom - candle.low, 0.0) / total_range
        close_position = (candle.close - candle.low) / total_range

    range_return = 0.0 if candle.open == 0.0 else total_range / abs(candle.open)
    direction = _direction(candle.open, candle.close)
    volume_state = _volume_state(candle.volume, volume_context)

    return FeatureVector(
        body_ratio=body_ratio,
        upper_ratio=upper_ratio,
        lower_ratio=lower_ratio,
        close_position=close_position,
        range_return=range_return,
        direction=direction,
        volume_state=volume_state,
    )


def extract_features_batch(
    candles: Iterable[CandleBar],
    volume_context: VolumeContext | None = None,
) -> tuple[FeatureVector, ...]:
    context = volume_context
    candle_tuple = tuple(candles)
    if context is None:
        context = build_volume_context(candle_tuple)
    return tuple(extract_features(candle, context) for candle in candle_tuple)


def _direction(open_price: float, close_price: float) -> float:
    if close_price > open_price:
        return 1.0
    if close_price < open_price:
        return -1.0
    return 0.0


def _volume_state(volume: int, volume_context: VolumeContext | None) -> float:
    if volume_context is None or volume_context.std == 0.0:
        return 0.0
    return (float(volume) - volume_context.mean) / volume_context.std
