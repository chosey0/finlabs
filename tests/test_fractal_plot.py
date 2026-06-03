from research.fractal.data import Candle
from research.fractal.labels import FractalEvent, FractalLabel
from research.fractal.plot import (
    CANDLE_DECREASING_COLOR,
    CANDLE_INCREASING_COLOR,
    fractal_event_segments,
    latest_fractal_event_segments,
    plot_fractal_event_segments,
    plot_fractal_events,
    plot_fractal_events_from_warehouse,
    plot_latest_fractal_event_segments,
    segment_plot_payload,
    select_fractal_event_segments,
)


def _candles() -> tuple[Candle, ...]:
    return tuple(
        Candle(
            timestamp=f"2026-01-01 09:{30 + index:02d}:00",
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100.5 + index,
        )
        for index in range(5)
    )


def test_plot_fractal_events_returns_plotly_figure_with_event_markers():
    candles = _candles()
    events = (
        FractalEvent(index=1, label=FractalLabel.LOW, price=candles[1].low, kind="low"),
        FractalEvent(index=3, label=FractalLabel.HIGH, price=candles[3].high, kind="high"),
    )

    figure = plot_fractal_events(candles, events=events, title="test")

    assert figure.layout.title.text == "test"
    assert [trace.name for trace in figure.data] == ["candles", "fractal high", "fractal low"]
    assert figure.data[0].increasing.line.color == CANDLE_INCREASING_COLOR
    assert figure.data[0].decreasing.line.color == CANDLE_DECREASING_COLOR
    assert list(figure.data[1].x) == [candles[3].timestamp]
    assert list(figure.data[2].x) == [candles[1].timestamp]


def test_plot_fractal_events_can_reuse_existing_figure_for_live_updates():
    candles = _candles()
    first_events = (FractalEvent(index=1, label=FractalLabel.LOW, price=candles[1].low, kind="low"),)
    second_events = (FractalEvent(index=4, label=FractalLabel.HIGH, price=candles[4].high, kind="high"),)

    figure = plot_fractal_events(candles, events=first_events)
    same_figure = plot_fractal_events(candles, events=second_events, figure=figure, max_candles=3)

    assert same_figure is figure
    assert [trace.name for trace in figure.data] == ["candles", "fractal high"]
    assert list(figure.data[0].x) == [candle.timestamp for candle in candles[-3:]]
    assert list(figure.data[1].x) == [candles[4].timestamp]


def test_plot_fractal_events_from_warehouse_uses_loaded_duckdb_candles(tmp_path):
    import duckdb

    db_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE ohlcv_bars (
                market VARCHAR,
                symbol VARCHAR,
                interval VARCHAR,
                timestamp VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            )
            """
        )
        connection.executemany(
            "INSERT INTO ohlcv_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("NASDAQ", "AAPL", "1d", "2026-01-02", 2, 3, 1, 2.5, 20),
                ("NASDAQ", "AAPL", "1d", "2026-01-01", 1, 2, 0.5, 1.5, 10),
            ],
        )

    figure = plot_fractal_events_from_warehouse(
        db_path,
        market="NASDAQ",
        symbol="AAPL",
        interval="1d",
    )

    assert [trace.name for trace in figure.data] == ["candles"]
    assert list(figure.data[0].x) == ["2026-01-01", "2026-01-02"]


def test_latest_fractal_event_segments_returns_latest_transition_segments():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.LOW, price=candles[0].low, kind="low"),
        FractalEvent(index=1, label=FractalLabel.HIGH, price=candles[1].high, kind="high"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=candles[2].low, kind="low"),
        FractalEvent(index=3, label=FractalLabel.HIGH, price=candles[3].high, kind="high"),
        FractalEvent(index=4, label=FractalLabel.LOW, price=candles[4].low, kind="low"),
    )

    segments = latest_fractal_event_segments(candles, events=events, min_segment_change_pct=0, min_followthrough_change_pct=0)

    assert sorted(segments) == ["high_to_low", "low_to_high"]
    assert [candle.timestamp for candle in segments["high_to_low"].candles] == [
        candles[1].timestamp,
        candles[2].timestamp,
    ]
    assert [candle.timestamp for candle in segments["low_to_high"].candles] == [
        candles[2].timestamp,
        candles[3].timestamp,
    ]
    assert [event.index for event in segments["low_to_high"].events] == [0, 1]
    assert segments["high_to_low"].ordinal == 1
    assert segments["low_to_high"].ordinal == 2


def test_fractal_event_segments_returns_all_transition_segments_chronologically():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.LOW, price=candles[0].low, kind="low"),
        FractalEvent(index=1, label=FractalLabel.HIGH, price=candles[1].high, kind="high"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=candles[2].low, kind="low"),
        FractalEvent(index=3, label=FractalLabel.HIGH, price=candles[3].high, kind="high"),
        FractalEvent(index=4, label=FractalLabel.LOW, price=candles[4].low, kind="low"),
    )

    segments = fractal_event_segments(candles, events=events, min_segment_change_pct=0, min_followthrough_change_pct=0)

    assert [(segment.transition, segment.ordinal) for segment in segments] == [
        ("low_to_high", 1),
        ("high_to_low", 1),
        ("low_to_high", 2),
    ]
    assert [[candle.timestamp for candle in segment.candles] for segment in segments] == [
        [candles[0].timestamp, candles[1].timestamp],
        [candles[1].timestamp, candles[2].timestamp],
        [candles[2].timestamp, candles[3].timestamp],
    ]


def test_fractal_event_segments_skips_segments_with_large_time_gap():
    candles = (
        Candle(timestamp="2026-04-24 19:58:00", open=1, high=2, low=0.5, close=1.5),
        Candle(timestamp="2026-04-27 04:00:00", open=2, high=3, low=1.5, close=2.5),
        Candle(timestamp="2026-04-27 04:01:00", open=2.5, high=4, low=2, close=3.5),
        Candle(timestamp="2026-04-27 04:02:00", open=3.5, high=5, low=3, close=4.5),
    )
    events = (
        FractalEvent(index=0, label=FractalLabel.LOW, price=candles[0].low, kind="low"),
        FractalEvent(index=1, label=FractalLabel.HIGH, price=candles[1].high, kind="high"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=candles[2].low, kind="low"),
        FractalEvent(index=3, label=FractalLabel.HIGH, price=candles[3].high, kind="high"),
    )

    segments = fractal_event_segments(candles, events=events, max_gap_seconds=5 * 60, min_segment_change_pct=0, min_followthrough_change_pct=0)

    assert [(segment.transition, segment.ordinal) for segment in segments] == [("high_to_low", 1)]
    assert [candle.timestamp for candle in segments[0].candles] == [
        candles[1].timestamp,
        candles[2].timestamp,
    ]


def test_fractal_event_segments_skips_segments_below_min_change_pct():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.LOW, price=100, kind="low"),
        FractalEvent(index=1, label=FractalLabel.HIGH, price=102.9, kind="high"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=96, kind="low"),
        FractalEvent(index=4, label=FractalLabel.HIGH, price=105, kind="high"),
    )

    segments = fractal_event_segments(
        candles,
        events=events,
        min_segment_change_pct=3,
        min_followthrough_change_pct=0,
    )

    assert [(segment.transition, segment.ordinal) for segment in segments] == [("high_to_low", 1)]


def test_fractal_event_segments_uses_next_event_followthrough_change_pct():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.HIGH, price=100, kind="high"),
        FractalEvent(index=1, label=FractalLabel.LOW, price=90, kind="low"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=80, kind="low"),
        FractalEvent(index=4, label=FractalLabel.HIGH, price=100, kind="high"),
    )

    segments = fractal_event_segments(candles, events=events, min_followthrough_change_pct=5)

    assert [(segment.transition, segment.ordinal) for segment in segments] == [("high_to_low", 1)]
    assert [candle.timestamp for candle in segments[0].candles] == [
        candles[0].timestamp,
        candles[1].timestamp,
    ]
    assert segments[0].confirmation_event == events[2]
    assert [candle.timestamp for candle in segments[0].followthrough_candles] == [
        candles[1].timestamp,
        candles[2].timestamp,
    ]


def test_segment_plot_payload_can_include_followthrough_with_background_regions():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.HIGH, price=100, kind="high"),
        FractalEvent(index=1, label=FractalLabel.LOW, price=90, kind="low"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=80, kind="low"),
        FractalEvent(index=4, label=FractalLabel.HIGH, price=100, kind="high"),
    )
    segment = fractal_event_segments(candles, events=events, min_followthrough_change_pct=5)[0]

    plot_candles, plot_events, regions = segment_plot_payload(segment, include_followthrough=True)

    assert [candle.timestamp for candle in plot_candles] == [
        candles[0].timestamp,
        candles[1].timestamp,
        candles[2].timestamp,
    ]
    assert [(event.index, event.kind) for event in plot_events] == [
        (0, "high"),
        (1, "low"),
        (2, "low"),
    ]
    assert [region.label for region in regions] == ["segment", "followthrough"]


def test_select_fractal_event_segments_returns_selection_summary():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.LOW, price=100, kind="low"),
        FractalEvent(index=1, label=FractalLabel.HIGH, price=102.9, kind="high"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=96, kind="low"),
        FractalEvent(index=4, label=FractalLabel.HIGH, price=105, kind="high"),
    )

    selection = select_fractal_event_segments(
        candles,
        events=events,
        min_segment_change_pct=3,
        min_followthrough_change_pct=0,
    )

    assert selection.raw_event_count == 4
    assert selection.filtered_event_count == 4
    assert selection.candidate_segment_count == 2
    assert selection.skipped_by_gap == 0
    assert selection.skipped_by_change_pct == 1
    assert selection.saved_segment_count == 1


def test_plot_latest_fractal_event_segments_returns_one_figure_per_transition():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.HIGH, price=candles[0].high, kind="high"),
        FractalEvent(index=1, label=FractalLabel.LOW, price=candles[1].low, kind="low"),
        FractalEvent(index=2, label=FractalLabel.HIGH, price=candles[2].high, kind="high"),
        FractalEvent(index=3, label=FractalLabel.LOW, price=candles[3].low, kind="low"),
        FractalEvent(index=4, label=FractalLabel.HIGH, price=candles[4].high, kind="high"),
    )

    figures = plot_latest_fractal_event_segments(candles, events=events, min_segment_change_pct=0, min_followthrough_change_pct=0)

    assert sorted(figures) == ["high_to_low", "low_to_high"]
    assert list(figures["high_to_low"].data[0].x) == [
        candles[2].timestamp,
        candles[3].timestamp,
    ]
    assert list(figures["low_to_high"].data[0].x) == [
        candles[1].timestamp,
        candles[2].timestamp,
    ]


def test_plot_fractal_event_segments_returns_one_figure_per_segment():
    candles = _candles()
    events = (
        FractalEvent(index=0, label=FractalLabel.LOW, price=candles[0].low, kind="low"),
        FractalEvent(index=1, label=FractalLabel.HIGH, price=candles[1].high, kind="high"),
        FractalEvent(index=2, label=FractalLabel.LOW, price=candles[2].low, kind="low"),
        FractalEvent(index=4, label=FractalLabel.HIGH, price=candles[4].high, kind="high"),
    )

    segment_figures = plot_fractal_event_segments(candles, events=events, min_segment_change_pct=0, min_followthrough_change_pct=0)

    assert [(item.segment.transition, item.segment.ordinal) for item in segment_figures] == [
        ("low_to_high", 1),
        ("high_to_low", 1),
    ]
    assert [item.figure.layout.title.text for item in segment_figures] == [
        "low to high segment #001",
        "high to low segment #001",
    ]
