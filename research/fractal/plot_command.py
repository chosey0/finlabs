from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any, Literal, cast

from kis_cli.storage.warehouse import default_warehouse_file

from .labels import FractalEvent, FractalLabelConfig
from .plot import (
    FractalEventSegment,
    FractalSegmentSelection,
    plot_fractal_events,
    segment_plot_payload,
    select_fractal_event_segments_from_warehouse,
)

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
    parser.add_argument("--max-candles", type=int, default=300, help="Deprecated. Segment plots always use full segment length.")
    parser.add_argument("--window", type=int, default=21)
    parser.add_argument("--short-ma", type=int, default=20)
    parser.add_argument("--long-ma", type=int, default=120)
    parser.add_argument("--min-window-range-pct", type=float, default=1e-6)
    parser.add_argument(
        "--min-segment-change-pct",
        type=float,
        default=0.0,
        help=(
            "Legacy start/end segment change filter. Defaults to 0, which disables this temporary filter."
        ),
    )
    parser.add_argument(
        "--min-followthrough-change-pct",
        type=float,
        default=5.0,
        help=(
            "Require the segment end event to move at least this percentage to the next fractal event. "
            "Defaults to 5."
        ),
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
        "--include-followthrough",
        action="store_true",
        help=(
            "Extend each plot from the segment end event to the next fractal event, "
            "with a distinct background for the follow-through interval."
        ),
    )
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
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit with a non-zero status when no segment passes the filters.",
    )
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
    if args.min_followthrough_change_pct < 0:
        raise ValueError("--min-followthrough-change-pct must be non-negative")

    max_gap_seconds = _resolve_max_gap_seconds(args)
    selection = select_fractal_event_segments_from_warehouse(
        args.warehouse_path,
        market=args.market,
        symbol=args.symbol,
        interval=args.interval,
        label_config=label_config,
        max_gap_seconds=max_gap_seconds,
        min_segment_change_pct=args.min_segment_change_pct,
        min_followthrough_change_pct=args.min_followthrough_change_pct,
    )
    if not selection.segments:
        _print_summary(selection)
        _print_no_segments_message(args)
        if args.fail_on_empty:
            raise SystemExit(1)
        return

    saved_segments: list[dict[str, Any]] = []
    for segment in selection.segments:
        out_path = _with_segment_suffix(output_base, segment=segment, output_type=output_type)
        plot_candles, plot_events, background_regions = segment_plot_payload(
            segment,
            include_followthrough=args.include_followthrough,
        )
        figure = plot_fractal_events(
            plot_candles,
            events=plot_events,
            label_config=label_config,
            title=f"{args.market.upper()} {args.symbol.upper()} {args.interval} {segment.transition} #{segment.ordinal:03d}",
            max_candles=None,
            show_filtered=args.show_filtered,
            background_regions=background_regions,
        )
        save_figure(figure, out_path, output_type=output_type)
        saved_segments.append(_segment_manifest_entry(segment, out_path=out_path))
        if args.open:
            webbrowser.open(out_path.resolve().as_uri())
        print(out_path)

    manifest_path = _with_manifest_suffix(output_base)
    _write_manifest(
        manifest_path,
        args=args,
        output_type=output_type,
        max_gap_seconds=max_gap_seconds,
        label_config=label_config,
        selection=selection,
        saved_segments=saved_segments,
    )
    _print_summary(selection)
    print(manifest_path)


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


def _with_manifest_suffix(path: Path) -> Path:
    return path.with_name(f"{path.stem}_manifest.json")


def _write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_type: OutputType,
    max_gap_seconds: float | None,
    label_config: FractalLabelConfig,
    selection: FractalSegmentSelection,
    saved_segments: list[dict[str, Any]],
) -> None:
    payload = {
        "market": args.market,
        "symbol": args.symbol,
        "interval": args.interval,
        "warehouse_path": str(args.warehouse_path),
        "output_type": output_type,
        "include_followthrough": args.include_followthrough,
        "label_config": {
            "window": label_config.window,
            "short_ma": label_config.short_ma,
            "long_ma": label_config.long_ma,
            "filtered_when_short_below_long": label_config.filtered_when_short_below_long,
            "min_window_range_pct": label_config.min_window_range_pct,
        },
        "segment_filters": {
            "max_gap_minutes": None if max_gap_seconds is None else max_gap_seconds / 60,
            "min_segment_change_pct": args.min_segment_change_pct,
            "min_followthrough_change_pct": args.min_followthrough_change_pct,
        },
        "summary": _summary_payload(selection),
        "saved_segments": saved_segments,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _segment_manifest_entry(segment: FractalEventSegment, *, out_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "transition": segment.transition,
        "ordinal": segment.ordinal,
        "output_path": str(out_path),
        "start": {
            "index": segment.start_event.index,
            "timestamp": segment.candles[0].timestamp,
            "kind": segment.start_event.kind,
            "price": segment.start_event.price,
        },
        "end": {
            "index": segment.end_event.index,
            "timestamp": segment.candles[-1].timestamp,
            "kind": segment.end_event.kind,
            "price": segment.end_event.price,
        },
        "candle_count": len(segment.candles),
        "change_pct": _segment_change_pct(segment),
    }
    if segment.confirmation_event is not None and segment.followthrough_candles:
        payload["confirmation"] = {
            "index": segment.confirmation_event.index,
            "timestamp": segment.followthrough_candles[-1].timestamp,
            "kind": segment.confirmation_event.kind,
            "price": segment.confirmation_event.price,
            "followthrough_candle_count": len(segment.followthrough_candles),
            "followthrough_change_pct": _event_change_pct(segment.end_event, segment.confirmation_event),
        }
    return payload


def _segment_change_pct(segment: FractalEventSegment) -> float:
    return _event_change_pct(segment.start_event, segment.end_event)


def _event_change_pct(start_event: FractalEvent, end_event: FractalEvent) -> float:
    denominator = abs(start_event.price)
    if denominator == 0:
        return float("inf") if end_event.price != 0 else 0.0
    return abs(end_event.price - start_event.price) / denominator * 100.0


def _summary_payload(selection: FractalSegmentSelection) -> dict[str, int]:
    return {
        "raw_events": selection.raw_event_count,
        "filtered_events": selection.filtered_event_count,
        "candidate_segments": selection.candidate_segment_count,
        "saved_segments": selection.saved_segment_count,
        "skipped_by_gap": selection.skipped_by_gap,
        "skipped_by_change_pct": selection.skipped_by_change_pct,
    }


def _print_summary(selection: FractalSegmentSelection) -> None:
    summary = _summary_payload(selection)
    print(
        "summary "
        f"raw_events={summary['raw_events']} "
        f"filtered_events={summary['filtered_events']} "
        f"candidate_segments={summary['candidate_segments']} "
        f"saved_segments={summary['saved_segments']} "
        f"skipped_by_gap={summary['skipped_by_gap']} "
        f"skipped_by_change_pct={summary['skipped_by_change_pct']}"
    )


def _print_no_segments_message(args: argparse.Namespace) -> None:
    print(
        "no segments saved: no high-to-low or low-to-high segment passed the current filters. "
        "Try lowering --min-followthrough-change-pct or relaxing --max-gap-minutes.",
        file=sys.stderr,
    )
    print(
        f"current filters: min_segment_change_pct={args.min_segment_change_pct:g} "
        f"min_followthrough_change_pct={args.min_followthrough_change_pct:g} "
        f"max_gap_minutes={args.max_gap_minutes if args.max_gap_minutes is not None else 'auto'}",
        file=sys.stderr,
    )


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
