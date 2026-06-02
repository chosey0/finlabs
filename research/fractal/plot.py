from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Sequence

from .data import Candle, load_fractal_candles_from_warehouse
from .labels import (
    FractalEvent,
    FractalLabel,
    FractalLabelConfig,
    compute_fractal_events,
    detect_fractal_events,
    filter_fractal_events,
    moving_average,
)

TransitionType = Literal["high_to_low", "low_to_high"]


@dataclass(frozen=True, slots=True)
class FractalEventSegment:
    transition: TransitionType
    ordinal: int
    start_event: FractalEvent
    end_event: FractalEvent
    candles: tuple[Candle, ...]
    events: tuple[FractalEvent, ...]


@dataclass(frozen=True, slots=True)
class FractalSegmentFigure:
    segment: FractalEventSegment
    figure: Any


def plot_fractal_events(
    candles: Sequence[Candle],
    *,
    events: Sequence[FractalEvent] | None = None,
    label_config: FractalLabelConfig | None = None,
    title: str | None = None,
    max_candles: int | None = None,
    show_filtered: bool = False,
    figure: Any | None = None,
) -> Any:
    """Plot candles with confirmed fractal high/low event markers.

    The function uses Plotly because it supports native candlestick traces,
    browser/notebook interactivity, and in-place figure updates for repeated
    calls in live or near-real-time workflows.

    If ``events`` is omitted, events are computed from the supplied candle
    sequence. Because fractal labels use a centered window, the latest
    ``window // 2`` candles cannot have confirmed labels yet.

    Passing an existing ``figure`` clears and repopulates it, which lets a
    caller reuse the same figure object while polling or streaming new candles.
    """
    if not candles:
        raise ValueError("candles must not be empty")
    if max_candles is not None and max_candles <= 0:
        raise ValueError("max_candles must be positive")

    go = _require_plotly()
    cfg = label_config or FractalLabelConfig()
    cfg.validate()

    ordered = tuple(candles)
    resolved_events = tuple(events) if events is not None else _compute_events(ordered, cfg)

    offset = max(0, len(ordered) - max_candles) if max_candles is not None else 0
    visible_candles = ordered[offset:]
    visible_events = tuple(event for event in resolved_events if offset <= event.index < len(ordered))

    fig = figure if figure is not None else go.Figure()
    fig.data = ()

    x_values = [candle.timestamp for candle in visible_candles]
    fig.add_trace(
        go.Candlestick(
            x=x_values,
            open=[candle.open for candle in visible_candles],
            high=[candle.high for candle in visible_candles],
            low=[candle.low for candle in visible_candles],
            close=[candle.close for candle in visible_candles],
            name="candles",
        )
    )

    _add_event_trace(
        fig,
        go,
        candles=ordered,
        events=visible_events,
        kind="high",
        label=FractalLabel.HIGH,
        name="fractal high",
        color="#d62728",
        symbol="triangle-down",
    )
    _add_event_trace(
        fig,
        go,
        candles=ordered,
        events=visible_events,
        kind="low",
        label=FractalLabel.LOW,
        name="fractal low",
        color="#2ca02c",
        symbol="triangle-up",
    )

    if show_filtered:
        _add_event_trace(
            fig,
            go,
            candles=ordered,
            events=visible_events,
            kind="high",
            label=FractalLabel.FILTERED,
            name="filtered high",
            color="#7f7f7f",
            symbol="x",
        )
        _add_event_trace(
            fig,
            go,
            candles=ordered,
            events=visible_events,
            kind="low",
            label=FractalLabel.FILTERED,
            name="filtered low",
            color="#7f7f7f",
            symbol="x",
        )

    fig.update_layout(
        title=title or "Fractal events",
        xaxis_title="time",
        yaxis_title="price",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    return fig


def plot_fractal_events_from_warehouse(
    warehouse_path: str | Path,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
    label_config: FractalLabelConfig | None = None,
    title: str | None = None,
    max_candles: int | None = None,
    show_filtered: bool = False,
    figure: Any | None = None,
) -> Any:
    """Load candles from the DuckDB warehouse and plot fractal events."""
    candles = load_fractal_candles_from_warehouse(
        warehouse_path,
        market=market,
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    return plot_fractal_events(
        candles,
        label_config=label_config,
        title=title or f"{market.upper()} {symbol.upper()} {interval} fractal events",
        max_candles=max_candles,
        show_filtered=show_filtered,
        figure=figure,
    )


def latest_fractal_event_segments(
    candles: Sequence[Candle],
    *,
    events: Sequence[FractalEvent] | None = None,
    label_config: FractalLabelConfig | None = None,
    max_gap_seconds: float | None = None,
    min_segment_change_pct: float = 3.0,
) -> dict[TransitionType, FractalEventSegment]:
    """Return the latest high→low and low→high confirmed fractal segments."""
    segments: dict[TransitionType, FractalEventSegment] = {}
    for segment in fractal_event_segments(
        candles,
        events=events,
        label_config=label_config,
        max_gap_seconds=max_gap_seconds,
        min_segment_change_pct=min_segment_change_pct,
    ):
        segments[segment.transition] = segment
    return segments


def fractal_event_segments(
    candles: Sequence[Candle],
    *,
    events: Sequence[FractalEvent] | None = None,
    label_config: FractalLabelConfig | None = None,
    max_gap_seconds: float | None = None,
    min_segment_change_pct: float = 3.0,
) -> tuple[FractalEventSegment, ...]:
    """Return all adjacent high→low and low→high confirmed fractal segments.

    The returned sequence is chronological. ``ordinal`` is counted separately
    per transition type so callers can build stable filenames such as
    ``high_to_low_001`` and ``low_to_high_001``.
    """
    if not candles:
        raise ValueError("candles must not be empty")
    if max_gap_seconds is not None and max_gap_seconds <= 0:
        raise ValueError("max_gap_seconds must be positive")
    if min_segment_change_pct < 0:
        raise ValueError("min_segment_change_pct must be non-negative")

    cfg = label_config or FractalLabelConfig()
    cfg.validate()
    ordered = tuple(candles)
    resolved_events = tuple(events) if events is not None else _compute_segment_events(ordered, cfg)
    confirmed_events = tuple(event for event in resolved_events if _is_confirmed_direction_event(event))

    segments: list[FractalEventSegment] = []
    ordinal_by_transition: dict[TransitionType, int] = {"high_to_low": 0, "low_to_high": 0}
    for start_event, end_event in zip(confirmed_events, confirmed_events[1:], strict=False):
        transition = _transition_type(start_event, end_event)
        if transition is None:
            continue
        if _has_large_time_gap(
            ordered,
            start_index=min(start_event.index, end_event.index),
            end_index=max(start_event.index, end_event.index),
            max_gap_seconds=max_gap_seconds,
        ):
            continue
        if _segment_change_pct(start_event, end_event) < min_segment_change_pct:
            continue
        ordinal_by_transition[transition] += 1
        segments.append(
            _make_segment(
                transition=transition,
                ordinal=ordinal_by_transition[transition],
                candles=ordered,
                events=resolved_events,
                start_event=start_event,
                end_event=end_event,
            )
        )

    return tuple(segments)


def plot_fractal_event_segments(
    candles: Sequence[Candle],
    *,
    events: Sequence[FractalEvent] | None = None,
    label_config: FractalLabelConfig | None = None,
    max_gap_seconds: float | None = None,
    min_segment_change_pct: float = 3.0,
    show_filtered: bool = False,
) -> tuple[FractalSegmentFigure, ...]:
    """Plot every high→low and low→high confirmed fractal segment."""
    segments = fractal_event_segments(
        candles,
        events=events,
        label_config=label_config,
        max_gap_seconds=max_gap_seconds,
        min_segment_change_pct=min_segment_change_pct,
    )
    figures: list[FractalSegmentFigure] = []
    for segment in segments:
        title = f"{segment.transition.replace('_', ' ')} segment #{segment.ordinal:03d}"
        figure = plot_fractal_events(
            segment.candles,
            events=segment.events,
            label_config=label_config,
            title=title,
            max_candles=None,
            show_filtered=show_filtered,
        )
        figures.append(FractalSegmentFigure(segment=segment, figure=figure))
    return tuple(figures)


def plot_fractal_event_segments_from_warehouse(
    warehouse_path: str | Path,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
    label_config: FractalLabelConfig | None = None,
    max_gap_seconds: float | None = None,
    min_segment_change_pct: float = 3.0,
    show_filtered: bool = False,
) -> tuple[FractalSegmentFigure, ...]:
    """Load candles and plot every high→low and low→high fractal segment."""
    candles = load_fractal_candles_from_warehouse(
        warehouse_path,
        market=market,
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    figures = plot_fractal_event_segments(
        candles,
        label_config=label_config,
        max_gap_seconds=max_gap_seconds,
        min_segment_change_pct=min_segment_change_pct,
        show_filtered=show_filtered,
    )
    if not figures:
        raise RuntimeError("no confirmed high-to-low or low-to-high fractal segments found")
    return figures


def plot_latest_fractal_event_segments(
    candles: Sequence[Candle],
    *,
    events: Sequence[FractalEvent] | None = None,
    label_config: FractalLabelConfig | None = None,
    max_gap_seconds: float | None = None,
    min_segment_change_pct: float = 3.0,
    show_filtered: bool = False,
) -> dict[TransitionType, Any]:
    """Plot one latest high→low segment and one latest low→high segment."""
    segments = latest_fractal_event_segments(
        candles,
        events=events,
        label_config=label_config,
        max_gap_seconds=max_gap_seconds,
        min_segment_change_pct=min_segment_change_pct,
    )
    figures: dict[TransitionType, Any] = {}
    for transition, segment in segments.items():
        title = f"{transition.replace('_', ' ')} segment"
        figures[transition] = plot_fractal_events(
            segment.candles,
            events=segment.events,
            label_config=label_config,
            title=title,
            max_candles=None,
            show_filtered=show_filtered,
        )
    return figures


def plot_latest_fractal_event_segments_from_warehouse(
    warehouse_path: str | Path,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
    label_config: FractalLabelConfig | None = None,
    max_gap_seconds: float | None = None,
    min_segment_change_pct: float = 3.0,
    show_filtered: bool = False,
) -> dict[TransitionType, Any]:
    """Load candles and plot the latest high→low and low→high segments."""
    candles = load_fractal_candles_from_warehouse(
        warehouse_path,
        market=market,
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    figures = plot_latest_fractal_event_segments(
        candles,
        label_config=label_config,
        max_gap_seconds=max_gap_seconds,
        min_segment_change_pct=min_segment_change_pct,
        show_filtered=show_filtered,
    )
    if not figures:
        raise RuntimeError("no confirmed high-to-low or low-to-high fractal segments found")
    return figures


def _compute_events(candles: Sequence[Candle], config: FractalLabelConfig) -> tuple[FractalEvent, ...]:
    highs = tuple(candle.high for candle in candles)
    lows = tuple(candle.low for candle in candles)
    closes = tuple(candle.close for candle in candles)
    short_ma = moving_average(closes, config.short_ma)
    long_ma = moving_average(closes, config.long_ma)
    return compute_fractal_events(highs, lows, short_ma, long_ma, config=config)


def _compute_segment_events(candles: Sequence[Candle], config: FractalLabelConfig) -> tuple[FractalEvent, ...]:
    highs = tuple(candle.high for candle in candles)
    lows = tuple(candle.low for candle in candles)
    raw_events = detect_fractal_events(highs, lows, config=config)
    return filter_fractal_events(
        raw_events,
        highs=highs,
        lows=lows,
        config=config,
        apply_ma_filter=False,
    )


def _is_confirmed_direction_event(event: FractalEvent) -> bool:
    return (event.kind == "high" and event.label == FractalLabel.HIGH) or (
        event.kind == "low" and event.label == FractalLabel.LOW
    )


def _transition_type(start_event: FractalEvent, end_event: FractalEvent) -> TransitionType | None:
    if start_event.kind == "high" and end_event.kind == "low":
        return "high_to_low"
    if start_event.kind == "low" and end_event.kind == "high":
        return "low_to_high"
    return None


def _segment_change_pct(start_event: FractalEvent, end_event: FractalEvent) -> float:
    denominator = abs(start_event.price)
    if denominator == 0:
        return float("inf") if end_event.price != 0 else 0.0
    return abs(end_event.price - start_event.price) / denominator * 100.0


def _has_large_time_gap(
    candles: Sequence[Candle],
    *,
    start_index: int,
    end_index: int,
    max_gap_seconds: float | None,
) -> bool:
    if max_gap_seconds is None:
        return False
    previous = _parse_timestamp(candles[start_index].timestamp)
    for candle in candles[start_index + 1 : end_index + 1]:
        current = _parse_timestamp(candle.timestamp)
        if (current - previous).total_seconds() > max_gap_seconds:
            return True
        previous = current
    return False


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"unsupported candle timestamp format: {value!r}") from exc


def _make_segment(
    *,
    transition: TransitionType,
    ordinal: int,
    candles: Sequence[Candle],
    events: Sequence[FractalEvent],
    start_event: FractalEvent,
    end_event: FractalEvent,
) -> FractalEventSegment:
    start_index = min(start_event.index, end_event.index)
    end_index = max(start_event.index, end_event.index)
    segment_events = tuple(
        FractalEvent(
            index=event.index - start_index,
            label=event.label,
            price=event.price,
            kind=event.kind,
        )
        for event in events
        if start_index <= event.index <= end_index
    )
    return FractalEventSegment(
        transition=transition,
        ordinal=ordinal,
        start_event=start_event,
        end_event=end_event,
        candles=tuple(candles[start_index : end_index + 1]),
        events=segment_events,
    )


def _add_event_trace(
    fig: Any,
    go: Any,
    *,
    candles: Sequence[Candle],
    events: Sequence[FractalEvent],
    kind: str,
    label: FractalLabel,
    name: str,
    color: str,
    symbol: str,
) -> None:
    selected = tuple(event for event in events if event.kind == kind and event.label == label)
    if not selected:
        return

    fig.add_trace(
        go.Scatter(
            x=[candles[event.index].timestamp for event in selected],
            y=[event.price for event in selected],
            mode="markers",
            name=name,
            marker={"color": color, "symbol": symbol, "size": 10, "line": {"width": 1, "color": "white"}},
            text=[f"{name}<br>index={event.index}<br>price={event.price:g}" for event in selected],
            hoverinfo="text",
        )
    )


def _require_plotly():
    try:
        import plotly.graph_objects as go
    except ImportError as exc:  # pragma: no cover - dependency/environment guard
        raise RuntimeError(
            "plot_fractal_events requires plotly. Install it with `uv add plotly` or `uv sync`."
        ) from exc
    return go
