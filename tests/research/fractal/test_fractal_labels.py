import pytest

from research.fractal.labels import (
    FractalLabel,
    FractalLabelConfig,
    compute_fractal_events,
    detect_fractal_events,
    filter_fractal_events,
)


def _ma(length: int) -> tuple[float, ...]:
    return tuple(1.0 for _ in range(length))


def test_fractal_label_config_requires_odd_window():
    with pytest.raises(ValueError, match="odd"):
        FractalLabelConfig(window=20).validate()


def test_compute_fractal_events_uses_centered_odd_window():
    highs = (1.0, 2.0, 5.0, 2.0, 1.0)
    lows = (0.5, 0.4, 0.3, 0.4, 0.5)
    closes = (1.0, 2.0, 5.0, 2.0, 1.0)

    high_events = compute_fractal_events(
        highs,
        lows,
        _ma(len(highs)),
        _ma(len(highs)),
        closes=closes,
        config=FractalLabelConfig(window=5, filtered_when_short_below_long=False),
    )
    low_events = compute_fractal_events(
        highs,
        lows,
        _ma(len(highs)),
        _ma(len(highs)),
        closes=(5.0, 4.0, 1.0, 4.0, 5.0),
        config=FractalLabelConfig(window=5, filtered_when_short_below_long=False),
    )

    assert [(event.index, event.kind, event.label) for event in high_events] == [(2, "high", FractalLabel.HIGH)]
    assert [(event.index, event.kind, event.label) for event in low_events] == [(2, "low", FractalLabel.LOW)]


def test_compute_fractal_events_uses_close_not_high_low_wicks():
    highs = (1.0, 2.0, 100.0, 2.0, 1.0)
    lows = (0.5, 0.4, 0.01, 0.4, 0.5)
    closes = (1.0, 3.0, 2.0, 4.0, 1.0)

    events = compute_fractal_events(
        highs,
        lows,
        _ma(len(highs)),
        _ma(len(highs)),
        closes=closes,
        config=FractalLabelConfig(window=5, filtered_when_short_below_long=False),
    )

    assert [(event.index, event.kind, event.price) for event in events] == []


def test_compute_fractal_events_requires_unique_window_extreme():
    highs = (1.0, 5.0, 5.0, 4.0, 3.0)
    lows = (0.5, 0.4, 0.3, 0.4, 0.5)
    closes = (1.0, 5.0, 5.0, 4.0, 3.0)

    events = compute_fractal_events(
        highs,
        lows,
        _ma(len(highs)),
        _ma(len(highs)),
        closes=closes,
        config=FractalLabelConfig(window=5, filtered_when_short_below_long=False),
    )

    assert events == ()


def test_compute_fractal_events_skips_near_flat_windows():
    highs = (100.0, 100.001, 100.002, 100.001, 100.0)
    lows = (99.999, 99.999, 99.999, 99.999, 99.999)
    closes = (100.0, 100.001, 100.002, 100.001, 100.0)

    events = compute_fractal_events(
        highs,
        lows,
        _ma(len(highs)),
        _ma(len(highs)),
        closes=closes,
        config=FractalLabelConfig(
            window=5,
            filtered_when_short_below_long=False,
            min_window_range_pct=0.001,
        ),
    )

    assert events == ()


def test_detect_fractal_events_returns_raw_events_before_event_filters():
    highs = (100.0, 100.001, 100.002, 100.001, 100.0)
    lows = (99.999, 99.999, 99.998, 99.999, 99.999)
    closes = (100.0, 100.001, 100.002, 100.001, 100.0)

    raw_events = detect_fractal_events(
        highs,
        lows,
        closes=closes,
        config=FractalLabelConfig(window=5, min_window_range_pct=0.001),
    )

    assert [(event.index, event.kind, event.label, event.price) for event in raw_events] == [
        (2, "high", FractalLabel.HIGH, 100.002),
    ]


def test_filter_fractal_events_can_apply_near_flat_without_ma_filtering():
    highs = (100.0, 100.001, 100.002, 100.001, 100.0, 101.0, 105.0, 101.0, 100.0)
    lows = (99.999, 99.999, 99.998, 99.999, 99.999, 99.0, 98.0, 99.0, 100.0)
    closes = (100.0, 100.001, 100.002, 100.001, 100.0, 101.0, 105.0, 101.0, 100.0)
    config = FractalLabelConfig(window=5, min_window_range_pct=0.001)
    raw_events = detect_fractal_events(highs, lows, closes=closes, config=config)

    events = filter_fractal_events(
        raw_events,
        highs=highs,
        lows=lows,
        closes=closes,
        config=config,
        apply_ma_filter=False,
    )

    assert [(event.index, event.kind, event.label) for event in events] == [
        (4, "low", FractalLabel.LOW),
        (6, "high", FractalLabel.HIGH),
    ]
