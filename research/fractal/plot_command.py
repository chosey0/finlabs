from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path
from typing import Any, Literal, cast

from kis_cli.storage.warehouse import default_warehouse_file

from .labels import FractalLabelConfig
from .plot import FractalEventSegment, plot_fractal_event_segments_from_warehouse

EVENT_PLOTS_DIR = Path(__file__).resolve().parent / "event_plots"
OutputType = Literal["svg", "png", "html", "pdf"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot all high-to-low and low-to-high fractal segments from the local DuckDB warehouse.",
    )
    parser.add_argument("--warehouse-path", type=Path, default=default_warehouse_file())
    parser.add_argument("--market", default="NASDAQ")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m", help="Candle interval, for example 1m or 1d.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--max-candles", type=int, default=300, help="Deprecated. Segment plots always use full segment length.")
    parser.add_argument("--window", type=int, default=21)
    parser.add_argument("--short-ma", type=int, default=20)
    parser.add_argument("--long-ma", type=int, default=120)
    parser.add_argument("--min-window-range-pct", type=float, default=1e-6)
    parser.add_argument(
        "--min-segment-change-pct",
        type=float,
        default=3.0,
        help="Skip segments whose start/end event price change is below this percentage. Defaults to 3.",
    )
    parser.add_argument(
        "--max-gap-minutes",
        type=float,
        help=(
            "Skip segments that contain a larger adjacent candle timestamp gap. "
            "Defaults to interval_minutes * 5 for minute intervals; disabled for daily intervals."
        ),
    )
    parser.add_argument("--show-filtered", action="store_true")
    parser.add_argument(
        "--type",
        choices=["svg", "png", "html", "pdf"],
        default="svg",
        help="Output format. Defaults to svg.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output base path. Segment files are written with _{transition}_{ordinal:03d} suffixes.",
    )
    parser.add_argument("--open", action="store_true", help="Open generated files after saving.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_type = _normalize_output_type(args.type)
    output_base = _resolve_output_base(args, output_type=output_type)
    output_base.parent.mkdir(parents=True, exist_ok=True)

    label_config = FractalLabelConfig(
        window=args.window,
        short_ma=args.short_ma,
        long_ma=args.long_ma,
        min_window_range_pct=args.min_window_range_pct,
    )
    label_config.validate()
    if args.min_segment_change_pct < 0:
        raise ValueError("--min-segment-change-pct must be non-negative")

    segment_figures = plot_fractal_event_segments_from_warehouse(
        args.warehouse_path,
        market=args.market,
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
        label_config=label_config,
        max_gap_seconds=_resolve_max_gap_seconds(args),
        min_segment_change_pct=args.min_segment_change_pct,
        show_filtered=args.show_filtered,
    )

    for segment_figure in segment_figures:
        out_path = _with_segment_suffix(output_base, segment=segment_figure.segment, output_type=output_type)
        save_figure(segment_figure.figure, out_path, output_type=output_type)
        if args.open:
            webbrowser.open(out_path.resolve().as_uri())
        print(out_path)


def save_figure(fig: Any, out_path: Path, *, output_type: OutputType) -> None:
    if output_type == "html":
        fig.write_html(out_path, auto_open=False)
        return
    fig.write_image(out_path)


def _resolve_output_path(args: argparse.Namespace) -> Path:
    """Backward-compatible helper for callers that need the normalized base path."""
    output_type = _normalize_output_type(args.type)
    return _resolve_output_base(args, output_type=output_type)


def _resolve_max_gap_seconds(args: argparse.Namespace) -> float | None:
    if args.max_gap_minutes is not None:
        if args.max_gap_minutes <= 0:
            raise ValueError("--max-gap-minutes must be positive")
        return args.max_gap_minutes * 60

    interval_minutes = _interval_to_minutes(args.interval)
    if interval_minutes is None:
        return None
    return interval_minutes * 5 * 60


def _interval_to_minutes(interval: str) -> int | None:
    normalized = interval.strip().lower()
    if normalized in {"1d", "d", "daily"}:
        return None
    if normalized.endswith("m"):
        value = normalized[:-1]
        if value.isdigit() and int(value) > 0:
            return int(value)
    if normalized.isdigit() and int(normalized) > 0:
        return int(normalized)
    return None


def _resolve_output_base(args: argparse.Namespace, *, output_type: OutputType) -> Path:
    if args.out is not None:
        out_path = args.out.expanduser()
        if out_path.suffix:
            return _with_output_suffix(out_path, output_type=output_type)
        return out_path.with_suffix(f".{output_type}")
    file_name = f"fractal_{args.market}_{args.symbol}_{args.interval}.{output_type}"
    return EVENT_PLOTS_DIR / file_name


def _with_segment_suffix(path: Path, *, segment: FractalEventSegment, output_type: OutputType) -> Path:
    return path.with_name(f"{path.stem}_{segment.transition}_{segment.ordinal:03d}.{output_type}")


def _with_output_suffix(path: Path, *, output_type: OutputType) -> Path:
    expected_suffix = f".{output_type}"
    if path.suffix.lower() == expected_suffix:
        return path
    return path.with_suffix(expected_suffix)


def _normalize_output_type(value: str) -> OutputType:
    normalized = value.lower().lstrip(".")
    if normalized not in {"svg", "png", "html", "pdf"}:
        raise ValueError("--type must be one of: svg, png, html, pdf")
    return cast(OutputType, normalized)


if __name__ == "__main__":
    main()
