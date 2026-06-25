"""collect-rss 라이브 모니터 집계 상태의 회귀 동작을 검증한다."""

from __future__ import annotations

import io

from rich.console import Console

from modules.news.monitor import CollectRssMonitor, render_dashboard
from modules.news.pipeline import FeedSource, OperationResult
from modules.news.rss.parsers import PARSERS


def _source(publisher: str, slug: str) -> FeedSource:
    return FeedSource(publisher, f"https://example.com/{slug}", PARSERS[publisher])


def _ok(processed: int, created: int) -> OperationResult:
    return OperationResult(processed=processed, created=created, skipped=processed - created)


def test_begin_cycle_seeds_publisher_totals_from_sources():
    monitor = CollectRssMonitor()
    monitor.begin_cycle(
        (_source("edaily", "a"), _source("donga", "b"), _source("donga", "c")),
        now=100.0,
    )

    assert monitor.cycles == 1
    assert monitor.publishers["edaily"].total_sources == 1
    assert monitor.publishers["donga"].total_sources == 2
    assert monitor.sources_done == 0
    assert monitor.publishers["donga"].status == "pending"


def test_record_source_rolls_up_publisher_and_session_totals():
    monitor = CollectRssMonitor()
    donga_a, donga_b = _source("donga", "a"), _source("donga", "b")
    monitor.begin_cycle((donga_a, donga_b), now=0.0)

    monitor.record_source(donga_a, _ok(processed=50, created=3))
    assert monitor.publishers["donga"].status == "running"

    monitor.record_source(donga_b, _ok(processed=40, created=0))

    progress = monitor.publishers["donga"]
    assert (progress.done_sources, progress.processed, progress.created, progress.skipped) == (
        2,
        90,
        3,
        87,
    )
    assert progress.status == "ok"
    assert (monitor.session_processed, monitor.session_created, monitor.session_skipped) == (
        90,
        3,
        87,
    )
    assert monitor.cycle_processed == 90 and monitor.cycle_created == 3


def test_failed_feed_marks_error_and_records_recent_message():
    monitor = CollectRssMonitor()
    source = _source("donga", "down")
    monitor.begin_cycle((source,), now=0.0)

    monitor.record_source(
        source,
        OperationResult(processed=0, created=0, skipped=0, errors=("donga: bozo feed",)),
    )

    assert monitor.publishers["donga"].status == "error"
    assert monitor.session_errors == 1
    assert list(monitor.recent_errors) == ["donga: bozo feed"]


def test_partial_status_when_some_sources_fail_but_others_store():
    monitor = CollectRssMonitor()
    a, b = _source("donga", "a"), _source("donga", "b")
    monitor.begin_cycle((a, b), now=0.0)

    monitor.record_source(a, _ok(processed=50, created=2))
    monitor.record_source(
        b, OperationResult(processed=0, created=0, skipped=0, errors=("donga: timeout",))
    )

    assert monitor.publishers["donga"].status == "partial"


def test_new_cycle_resets_publisher_view_but_keeps_session_totals():
    monitor = CollectRssMonitor()
    source = _source("edaily", "a")

    monitor.begin_cycle((source,), now=0.0)
    monitor.record_source(source, _ok(processed=10, created=10))
    monitor.begin_cycle((source,), now=60.0)

    assert monitor.cycles == 2
    assert monitor.publishers["edaily"].created == 0  # current-cycle view reset
    assert monitor.session_created == 10  # session total preserved
    assert monitor.elapsed_seconds(now=90.0) == 90.0


def test_recent_errors_are_bounded():
    monitor = CollectRssMonitor(error_history=2)
    source = _source("donga", "x")
    monitor.begin_cycle((source,), now=0.0)
    for index in range(3):
        monitor.record_source(
            source,
            OperationResult(processed=0, created=0, skipped=0, errors=(f"e{index}",)),
        )

    assert list(monitor.recent_errors) == ["e1", "e2"]


def test_render_dashboard_emits_publisher_rows_and_totals():
    monitor = CollectRssMonitor()
    source = _source("donga", "a")
    monitor.begin_cycle((source,), now=0.0)
    monitor.record_source(source, _ok(processed=50, created=4))

    console = Console(file=io.StringIO(), width=120, color_system=None)
    console.print(render_dashboard(monitor, status_line="수집 중…", elapsed_seconds=1.0))
    output = console.file.getvalue()

    assert "라이브 모니터" in output
    assert "donga" in output
    assert "적재" in output
    assert "4" in output
