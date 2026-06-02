from __future__ import annotations

from .data import FractalSample, build_fractal_samples, load_fractal_candles_from_warehouse
from .labels import FractalLabel, FractalLabelConfig, compute_fractal_events, detect_fractal_events, filter_fractal_events
from .model import CNN1D, CNN1DConfig, require_torch
from .plot import (
    FractalEventSegment,
    FractalSegmentFigure,
    FractalSegmentSelection,
    fractal_event_segments,
    latest_fractal_event_segments,
    plot_fractal_event_segments,
    plot_fractal_event_segments_from_warehouse,
    plot_fractal_events,
    plot_fractal_events_from_warehouse,
    plot_latest_fractal_event_segments,
    plot_latest_fractal_event_segments_from_warehouse,
    select_fractal_event_segments,
    select_fractal_event_segments_from_warehouse,
)

__all__ = [
    "CNN1D",
    "CNN1DConfig",
    "FractalLabel",
    "FractalLabelConfig",
    "FractalSample",
    "FractalEventSegment",
    "FractalSegmentFigure",
    "FractalSegmentSelection",
    "fractal_event_segments",
    "latest_fractal_event_segments",
    "load_fractal_candles_from_warehouse",
    "plot_fractal_event_segments",
    "plot_fractal_event_segments_from_warehouse",
    "plot_fractal_events",
    "plot_fractal_events_from_warehouse",
    "plot_latest_fractal_event_segments",
    "plot_latest_fractal_event_segments_from_warehouse",
    "select_fractal_event_segments",
    "select_fractal_event_segments_from_warehouse",
    "build_fractal_samples",
    "compute_fractal_events",
    "detect_fractal_events",
    "filter_fractal_events",
    "require_torch",
]
