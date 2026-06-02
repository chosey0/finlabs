import argparse

from research.fractal.data import Candle
from research.fractal.labels import FractalEvent, FractalLabel
from research.fractal.plot import FractalEventSegment, FractalSegmentFigure
from research.fractal import plot_command


class FakeFigure:
    def __init__(self) -> None:
        self.saved: list[tuple[str, object]] = []

    def write_image(self, path):
        self.saved.append(("image", path))

    def write_html(self, path, *, auto_open=False):
        self.saved.append(("html", path, auto_open))


def _fake_segment_figure(transition: str, ordinal: int) -> FractalSegmentFigure:
    candle = Candle(timestamp="2026-01-01", open=1, high=2, low=0.5, close=1.5)
    start_event = FractalEvent(index=0, label=FractalLabel.HIGH, price=2, kind="high")
    end_event = FractalEvent(index=0, label=FractalLabel.LOW, price=0.5, kind="low")
    segment = FractalEventSegment(
        transition=transition,
        ordinal=ordinal,
        start_event=start_event,
        end_event=end_event,
        candles=(candle,),
        events=(start_event, end_event),
    )
    return FractalSegmentFigure(segment=segment, figure=FakeFigure())


def _fake_segment_figures() -> tuple[FractalSegmentFigure, ...]:
    return (
        _fake_segment_figure("high_to_low", 1),
        _fake_segment_figure("high_to_low", 2),
        _fake_segment_figure("low_to_high", 1),
    )


def test_plot_command_writes_one_svg_file_per_segment_by_default(monkeypatch, tmp_path):
    segment_figures = _fake_segment_figures()
    monkeypatch.setattr(plot_command, "EVENT_PLOTS_DIR", tmp_path / "event_plots")
    monkeypatch.setattr(plot_command, "plot_fractal_event_segments_from_warehouse", lambda *args, **kwargs: segment_figures)
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
    assert segment_figures[0].figure.saved == [("image", base / "fractal_NASDAQ_AAPL_1d_high_to_low_001.svg")]
    assert segment_figures[1].figure.saved == [("image", base / "fractal_NASDAQ_AAPL_1d_high_to_low_002.svg")]
    assert segment_figures[2].figure.saved == [("image", base / "fractal_NASDAQ_AAPL_1d_low_to_high_001.svg")]
    assert base.exists()


def test_plot_command_supports_html_output_type(monkeypatch, tmp_path):
    segment_figures = _fake_segment_figures()
    out_path = tmp_path / "fractal.html"
    monkeypatch.setattr(plot_command, "plot_fractal_event_segments_from_warehouse", lambda *args, **kwargs: segment_figures)
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

    assert segment_figures[0].figure.saved == [("html", out_path.with_name("fractal_high_to_low_001.html"), False)]
    assert segment_figures[1].figure.saved == [("html", out_path.with_name("fractal_high_to_low_002.html"), False)]
    assert segment_figures[2].figure.saved == [("html", out_path.with_name("fractal_low_to_high_001.html"), False)]


def test_plot_command_appends_selected_suffix_for_suffixless_out_path(monkeypatch, tmp_path):
    segment_figures = _fake_segment_figures()
    out_path = tmp_path / "fractal_AAPL_1d"
    monkeypatch.setattr(plot_command, "plot_fractal_event_segments_from_warehouse", lambda *args, **kwargs: segment_figures)
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

    assert segment_figures[0].figure.saved == [("image", tmp_path / "fractal_AAPL_1d_high_to_low_001.png")]
    assert segment_figures[1].figure.saved == [("image", tmp_path / "fractal_AAPL_1d_high_to_low_002.png")]
    assert segment_figures[2].figure.saved == [("image", tmp_path / "fractal_AAPL_1d_low_to_high_001.png")]


def test_plot_command_overrides_out_suffix_with_selected_type(monkeypatch, tmp_path):
    segment_figures = _fake_segment_figures()
    out_path = tmp_path / "fractal.html"
    monkeypatch.setattr(plot_command, "plot_fractal_event_segments_from_warehouse", lambda *args, **kwargs: segment_figures)
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

    assert segment_figures[0].figure.saved == [("image", tmp_path / "fractal_high_to_low_001.pdf")]
    assert segment_figures[1].figure.saved == [("image", tmp_path / "fractal_high_to_low_002.pdf")]
    assert segment_figures[2].figure.saved == [("image", tmp_path / "fractal_low_to_high_001.pdf")]


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
