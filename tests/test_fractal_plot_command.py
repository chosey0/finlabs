import argparse
import json

from research.fractal.data import Candle
from research.fractal.labels import FractalEvent, FractalLabel
from research.fractal.plot import FractalEventSegment, FractalSegmentSelection
from research.fractal import plot_command


class FakeFigure:
    def __init__(self) -> None:
        self.saved: list[tuple[str, object]] = []

    def write_image(self, path):
        self.saved.append(("image", path))

    def write_html(self, path, *, auto_open=False):
        self.saved.append(("html", path, auto_open))


def _fake_segment(transition: str, ordinal: int) -> FractalEventSegment:
    candle = Candle(timestamp="2026-01-01", open=1, high=2, low=0.5, close=1.5)
    start_event = FractalEvent(index=0, label=FractalLabel.HIGH, price=2, kind="high")
    end_event = FractalEvent(index=0, label=FractalLabel.LOW, price=0.5, kind="low")
    return FractalEventSegment(
        transition=transition,
        ordinal=ordinal,
        start_event=start_event,
        end_event=end_event,
        candles=(candle,),
        events=(start_event, end_event),
    )


def _fake_selection() -> FractalSegmentSelection:
    return FractalSegmentSelection(
        raw_event_count=5,
        filtered_event_count=4,
        candidate_segment_count=3,
        skipped_by_gap=0,
        skipped_by_change_pct=0,
        segments=(
            _fake_segment("high_to_low", 1),
            _fake_segment("high_to_low", 2),
            _fake_segment("low_to_high", 1),
        ),
    )


def _install_fake_plotting(monkeypatch, selection: FractalSegmentSelection) -> list[FakeFigure]:
    figures = [FakeFigure() for _ in selection.segments]
    remaining = iter(figures)
    monkeypatch.setattr(plot_command, "select_fractal_event_segments_from_warehouse", lambda *args, **kwargs: selection)
    monkeypatch.setattr(plot_command, "plot_fractal_events", lambda *args, **kwargs: next(remaining))
    return figures


def test_plot_command_writes_one_svg_file_per_segment_by_default(monkeypatch, tmp_path):
    selection = _fake_selection()
    figures = _install_fake_plotting(monkeypatch, selection)
    monkeypatch.setattr(plot_command, "EVENT_PLOTS_DIR", tmp_path / "event_plots")
    monkeypatch.setattr(
        "sys.argv",
        [
            "plot_command",
            "--warehouse-path",
            str(tmp_path / "warehouse.duckdb"),
            "--market",
            "NASDAQ",
            "--symbol",
            "AAPL",
            "--interval",
            "1d",
        ],
    )

    plot_command.main()

    base = tmp_path / "event_plots"
    assert figures[0].saved == [("image", base / "fractal_NASDAQ_AAPL_1d_high_to_low_001.svg")]
    assert figures[1].saved == [("image", base / "fractal_NASDAQ_AAPL_1d_high_to_low_002.svg")]
    assert figures[2].saved == [("image", base / "fractal_NASDAQ_AAPL_1d_low_to_high_001.svg")]
    assert base.exists()
    manifest = json.loads((base / "fractal_NASDAQ_AAPL_1d_manifest.json").read_text())
    assert manifest["summary"] == {
        "raw_events": 5,
        "filtered_events": 4,
        "candidate_segments": 3,
        "saved_segments": 3,
        "skipped_by_gap": 0,
        "skipped_by_change_pct": 0,
    }
    assert [item["transition"] for item in manifest["saved_segments"]] == [
        "high_to_low",
        "high_to_low",
        "low_to_high",
    ]


def test_plot_command_supports_html_output_type(monkeypatch, tmp_path):
    selection = _fake_selection()
    figures = _install_fake_plotting(monkeypatch, selection)
    out_path = tmp_path / "fractal.html"
    monkeypatch.setattr(
        "sys.argv",
        [
            "plot_command",
            "--warehouse-path",
            str(tmp_path / "warehouse.duckdb"),
            "--symbol",
            "AAPL",
            "--type",
            "html",
            "--out",
            str(out_path),
        ],
    )

    plot_command.main()

    assert figures[0].saved == [("html", out_path.with_name("fractal_high_to_low_001.html"), False)]
    assert figures[1].saved == [("html", out_path.with_name("fractal_high_to_low_002.html"), False)]
    assert figures[2].saved == [("html", out_path.with_name("fractal_low_to_high_001.html"), False)]


def test_plot_command_appends_selected_suffix_for_suffixless_out_path(monkeypatch, tmp_path):
    selection = _fake_selection()
    figures = _install_fake_plotting(monkeypatch, selection)
    out_path = tmp_path / "fractal_AAPL_1d"
    monkeypatch.setattr(
        "sys.argv",
        [
            "plot_command",
            "--warehouse-path",
            str(tmp_path / "warehouse.duckdb"),
            "--symbol",
            "AAPL",
            "--type",
            "png",
            "--out",
            str(out_path),
        ],
    )

    plot_command.main()

    assert figures[0].saved == [("image", tmp_path / "fractal_AAPL_1d_high_to_low_001.png")]
    assert figures[1].saved == [("image", tmp_path / "fractal_AAPL_1d_high_to_low_002.png")]
    assert figures[2].saved == [("image", tmp_path / "fractal_AAPL_1d_low_to_high_001.png")]


def test_plot_command_overrides_out_suffix_with_selected_type(monkeypatch, tmp_path):
    selection = _fake_selection()
    figures = _install_fake_plotting(monkeypatch, selection)
    out_path = tmp_path / "fractal.html"
    monkeypatch.setattr(
        "sys.argv",
        [
            "plot_command",
            "--warehouse-path",
            str(tmp_path / "warehouse.duckdb"),
            "--symbol",
            "AAPL",
            "--type",
            "pdf",
            "--out",
            str(out_path),
        ],
    )

    plot_command.main()

    assert figures[0].saved == [("image", tmp_path / "fractal_high_to_low_001.pdf")]
    assert figures[1].saved == [("image", tmp_path / "fractal_high_to_low_002.pdf")]
    assert figures[2].saved == [("image", tmp_path / "fractal_low_to_high_001.pdf")]


def test_plot_command_rejects_even_window(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        [
            "plot_command",
            "--warehouse-path",
            str(tmp_path / "missing.duckdb"),
            "--symbol",
            "AAPL",
            "--window",
            "20",
        ],
    )

    try:
        plot_command.main()
    except ValueError as exc:
        assert "odd" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("even window should fail before querying DuckDB")


def test_plot_command_rejects_negative_min_segment_change_pct(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        [
            "plot_command",
            "--warehouse-path",
            str(tmp_path / "missing.duckdb"),
            "--symbol",
            "AAPL",
            "--min-segment-change-pct",
            "-1",
        ],
    )

    try:
        plot_command.main()
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("negative min segment change should fail before querying DuckDB")


def test_resolve_output_path_defaults_to_event_plots_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(plot_command, "EVENT_PLOTS_DIR", tmp_path)
    args = argparse.Namespace(out=None, market="NASDAQ", symbol="RKLB", interval="1m", type="svg")

    path = plot_command._resolve_output_path(args)

    assert path == tmp_path / "fractal_NASDAQ_RKLB_1m.svg"


def test_resolve_output_path_uses_selected_type(monkeypatch, tmp_path):
    monkeypatch.setattr(plot_command, "EVENT_PLOTS_DIR", tmp_path)
    args = argparse.Namespace(out=None, market="NASDAQ", symbol="RKLB", interval="1m", type="html")

    path = plot_command._resolve_output_path(args)

    assert path == tmp_path / "fractal_NASDAQ_RKLB_1m.html"


def test_resolve_max_gap_seconds_defaults_to_five_times_minute_interval():
    args = argparse.Namespace(interval="1m", max_gap_minutes=None)

    assert plot_command._resolve_max_gap_seconds(args) == 5 * 60


def test_resolve_max_gap_seconds_is_disabled_for_daily_interval():
    args = argparse.Namespace(interval="1d", max_gap_minutes=None)

    assert plot_command._resolve_max_gap_seconds(args) is None


def test_interval_to_minutes_accepts_daily_interval_aliases():
    assert plot_command._interval_to_minutes("1d") is None
    assert plot_command._interval_to_minutes("daily") is None


def test_resolve_max_gap_seconds_uses_explicit_value():
    args = argparse.Namespace(interval="1m", max_gap_minutes=30)

    assert plot_command._resolve_max_gap_seconds(args) == 30 * 60
