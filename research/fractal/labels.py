from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Sequence


class FractalLabel(IntEnum):
    LOW = 0
    HIGH = 1
    FILTERED = 2


@dataclass(frozen=True, slots=True)
class FractalLabelConfig:
    """Configuration for lagging fractal label generation.

    A candle is a fractal high when its high is the unique maximum in an odd,
    centered rolling window. It is a fractal low when its low is the unique
    minimum in the same centered window. Near-flat windows are skipped.

    This deliberately uses future candles inside the label window. Use it for
    supervised labels, not as a live signal.
    """

    window: int = 21
    short_ma: int = 20
    long_ma: int = 120
    filtered_when_short_below_long: bool = True
    min_window_range_pct: float = 1e-6

    def validate(self) -> None:
        if self.window < 3:
            raise ValueError("window must be at least 3")
        if self.window % 2 == 0:
            raise ValueError("window must be odd for centered fractal labels")
        if self.short_ma <= 0:
            raise ValueError("short_ma must be positive")
        if self.long_ma <= 0:
            raise ValueError("long_ma must be positive")
        if self.min_window_range_pct < 0:
            raise ValueError("min_window_range_pct must be non-negative")


@dataclass(frozen=True, slots=True)
class FractalEvent:
    index: int
    label: FractalLabel
    price: float
    kind: str


def compute_fractal_events(
    highs: Sequence[float],
    lows: Sequence[float],
    short_ma: Sequence[float | None],
    long_ma: Sequence[float | None],
    *,
    config: FractalLabelConfig | None = None,
) -> tuple[FractalEvent, ...]:
    """Return labeled centered-window fractal events in chronological order.

    This is the compatibility wrapper used by supervised-label workflows. It
    first detects raw unique high/low extrema, then applies event-level filters
    such as near-flat window removal and optional MA-based filtering.
    """
    cfg = config or FractalLabelConfig()
    cfg.validate()
    _validate_equal_lengths(highs, lows, short_ma, long_ma)

    raw_events = detect_fractal_events(highs, lows, config=cfg)
    return filter_fractal_events(
        raw_events,
        highs=highs,
        lows=lows,
        short_ma=short_ma,
        long_ma=long_ma,
        config=cfg,
        apply_ma_filter=True,
        drop_filtered=False,
    )


def detect_fractal_events(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    config: FractalLabelConfig | None = None,
) -> tuple[FractalEvent, ...]:
    """Detect raw centered-window fractal high/low events.

    Raw detection deliberately does not apply MA filtering or near-flat window
    filtering. A raw high is the unique maximum in the centered window. A raw
    low is the unique minimum in the centered window.
    """
    cfg = config or FractalLabelConfig()
    cfg.validate()
    _validate_equal_lengths(highs, lows)

    half_window = cfg.window // 2
    events: list[FractalEvent] = []

    for index in range(half_window, len(highs) - half_window):
        start = index - half_window
        stop = start + cfg.window
        high_window = highs[start:stop]
        low_window = lows[start:stop]
        max_high = max(high_window)
        min_low = min(low_window)

        if highs[index] == max_high and _is_unique(high_window, highs[index]):
            events.append(
                FractalEvent(
                    index=index,
                    label=FractalLabel.HIGH,
                    price=float(highs[index]),
                    kind="high",
                )
            )

        if lows[index] == min_low and _is_unique(low_window, lows[index]):
            events.append(
                FractalEvent(
                    index=index,
                    label=FractalLabel.LOW,
                    price=float(lows[index]),
                    kind="low",
                )
            )

    return tuple(sorted(events, key=lambda event: (event.index, event.kind)))


def filter_fractal_events(
    events: Sequence[FractalEvent],
    *,
    highs: Sequence[float],
    lows: Sequence[float],
    short_ma: Sequence[float | None] | None = None,
    long_ma: Sequence[float | None] | None = None,
    config: FractalLabelConfig | None = None,
    apply_ma_filter: bool = True,
    drop_filtered: bool = False,
) -> tuple[FractalEvent, ...]:
    """Apply event-level filters to raw fractal events.

    Event-level filters decide whether a detected fractal point itself is
    usable. Segment-level filters such as start/end percentage change and
    timestamp gaps are applied later by segment construction.
    """
    cfg = config or FractalLabelConfig()
    cfg.validate()
    _validate_equal_lengths(highs, lows)
    if apply_ma_filter:
        if short_ma is None or long_ma is None:
            raise ValueError("short_ma and long_ma are required when apply_ma_filter=True")
        _validate_equal_lengths(highs, lows, short_ma, long_ma)

    filtered: list[FractalEvent] = []
    for event in events:
        if event.index < 0 or event.index >= len(highs):
            raise ValueError(f"event index out of range: {event.index}")
        if _is_near_flat_window(event.index, highs, lows, config=cfg):
            continue

        label = event.label
        if apply_ma_filter:
            if event.kind == "high":
                default = FractalLabel.HIGH
            elif event.kind == "low":
                default = FractalLabel.LOW
            else:
                raise ValueError(f"unsupported fractal event kind: {event.kind!r}")
            label = _label_for_ma(
                event.index,
                short_ma or (),
                long_ma or (),
                config=cfg,
                default=default,
            )
            if drop_filtered and label == FractalLabel.FILTERED:
                continue

        filtered.append(
            FractalEvent(
                index=event.index,
                label=label,
                price=event.price,
                kind=event.kind,
            )
        )

    return tuple(sorted(filtered, key=lambda item: (item.index, item.kind)))


def moving_average(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    if window <= 0:
        raise ValueError("window must be positive")

    result: list[float | None] = []
    running_sum = 0.0
    for index, value in enumerate(values):
        running_sum += float(value)
        if index >= window:
            running_sum -= float(values[index - window])
        if index + 1 < window:
            result.append(None)
        else:
            result.append(running_sum / window)
    return tuple(result)


def _label_for_ma(
    index: int,
    short_ma: Sequence[float | None],
    long_ma: Sequence[float | None],
    *,
    config: FractalLabelConfig,
    default: FractalLabel,
) -> FractalLabel:
    if not config.filtered_when_short_below_long:
        return default

    short_value = short_ma[index]
    long_value = long_ma[index]
    if short_value is None or long_value is None:
        return FractalLabel.FILTERED
    if short_value < long_value:
        return FractalLabel.FILTERED
    return default


def _is_near_flat_window(
    index: int,
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    config: FractalLabelConfig,
) -> bool:
    half_window = config.window // 2
    start = index - half_window
    stop = start + config.window
    if start < 0 or stop > len(highs):
        return True
    max_high = max(highs[start:stop])
    min_low = min(lows[start:stop])
    reference_price = max(
        abs(float(highs[index])),
        abs(float(lows[index])),
        1.0,
    )
    window_range_pct = (float(max_high) - float(min_low)) / reference_price
    return window_range_pct <= config.min_window_range_pct


def _validate_equal_lengths(*items: Sequence[object]) -> None:
    lengths = {len(item) for item in items}
    if len(lengths) != 1:
        raise ValueError("all input sequences must have the same length")


def _is_unique(values: Sequence[float], target: float) -> bool:
    return sum(1 for value in values if value == target) == 1
