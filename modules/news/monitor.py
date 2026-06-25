"""collect-rss 실행 현황을 집계하고 Rich 라이브 대시보드로 렌더링한다.

집계 상태(`CollectRssMonitor`)는 Rich에 의존하지 않아 단위 테스트가 쉽고,
렌더링(`render_dashboard`)만 Rich 위젯을 만든다. 상태는 `collect_rss`의
``on_source_result`` 콜백이 소스 완료마다 갱신한다.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .pipeline import FeedSource, OperationResult

# 배경은 터미널 그대로 두고, 글씨만 흰 배경에서 대비가 분명한 진한 색으로 칠한다.
# 색 없는(터미널 기본 전경색) 텍스트나 밝은 회색(`dim`)·`yellow`는 흰 배경에서
# 묻히므로 쓰지 않는다.

# (기호, 전경색) — 소스 그룹 상태 표시.
_STATUS: dict[str, tuple[str, str]] = {
    "pending": ("⏳ 대기", "black"),
    "running": ("… 수집", "magenta"),
    "ok": ("✓ 완료", "bold green"),
    "partial": ("⚠ 일부", "bold magenta"),
    "error": ("✗ 실패", "bold red"),
}


@dataclass
class PublisherProgress:
    """한 언론사의 현재 사이클 집계."""

    publisher: str
    total_sources: int
    done_sources: int = 0
    processed: int = 0
    created: int = 0
    skipped: int = 0
    errors: int = 0

    @property
    def status(self) -> str:
        if self.done_sources < self.total_sources:
            return "running" if self.done_sources else "pending"
        if self.errors == 0:
            return "ok"
        if self.created == 0 and self.errors >= self.total_sources:
            return "error"
        return "partial"


class CollectRssMonitor:
    """collect-rss 사이클의 언론사별·세션 누적 집계를 보관한다."""

    def __init__(self, *, error_history: int = 8) -> None:
        self.cycles = 0
        self.publishers: dict[str, PublisherProgress] = {}
        self.session_processed = 0
        self.session_created = 0
        self.session_skipped = 0
        self.session_errors = 0
        self.recent_errors: deque[str] = deque(maxlen=error_history)
        self._started_at: float | None = None
        self._cycle_started_at: float | None = None

    def begin_cycle(
        self, sources: Sequence[FeedSource], *, now: float | None = None
    ) -> None:
        """새 수집 사이클을 시작하고 언론사별 진행 상태를 초기화한다."""

        self.cycles += 1
        counts: dict[str, int] = {}
        for source in sources:
            counts[source.publisher] = counts.get(source.publisher, 0) + 1
        self.publishers = {
            publisher: PublisherProgress(publisher, total)
            for publisher, total in counts.items()
        }
        timestamp = now if now is not None else time.monotonic()
        if self._started_at is None:
            self._started_at = timestamp
        self._cycle_started_at = timestamp

    def record_source(self, source: FeedSource, result: OperationResult) -> None:
        """소스 하나의 수집 결과를 언론사·세션 집계에 반영한다."""

        progress = self.publishers.get(source.publisher)
        if progress is None:
            progress = PublisherProgress(source.publisher, 0)
            self.publishers[source.publisher] = progress
        if progress.done_sources >= progress.total_sources:
            progress.total_sources = progress.done_sources + 1
        progress.done_sources += 1
        progress.processed += result.processed
        progress.created += result.created
        progress.skipped += result.skipped
        progress.errors += len(result.errors)
        for message in result.errors:
            self.recent_errors.append(message)
        self.session_processed += result.processed
        self.session_created += result.created
        self.session_skipped += result.skipped
        self.session_errors += len(result.errors)

    @property
    def sources_total(self) -> int:
        return sum(p.total_sources for p in self.publishers.values())

    @property
    def sources_done(self) -> int:
        return sum(p.done_sources for p in self.publishers.values())

    @property
    def cycle_processed(self) -> int:
        return sum(p.processed for p in self.publishers.values())

    @property
    def cycle_created(self) -> int:
        return sum(p.created for p in self.publishers.values())

    @property
    def cycle_skipped(self) -> int:
        return sum(p.skipped for p in self.publishers.values())

    @property
    def cycle_errors(self) -> int:
        return sum(p.errors for p in self.publishers.values())

    def elapsed_seconds(self, *, now: float | None = None) -> float:
        if self._started_at is None:
            return 0.0
        timestamp = now if now is not None else time.monotonic()
        return max(0.0, timestamp - self._started_at)


def _fmt_seconds(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def render_dashboard(
    monitor: CollectRssMonitor,
    *,
    status_line: str,
    elapsed_seconds: float,
) -> Group:
    """현재 집계 상태를 Rich 대시보드(Group)로 렌더링한다."""

    header = Text()
    header.append("FINLABS · collect-rss 라이브 모니터\n", style="bold black")
    header.append(f"{status_line}   ", style="bold magenta")
    header.append(
        f"사이클 {monitor.cycles}   경과 {_fmt_seconds(elapsed_seconds)}\n",
        style="black",
    )
    header.append("세션 누적  ", style="bold black")
    header.append(f"수집 {monitor.session_processed}", style="black")
    header.append("  ")
    header.append(f"적재 {monitor.session_created}", style="bold green")
    header.append("  ")
    header.append(f"중복 {monitor.session_skipped}", style="black")
    header.append("  ")
    header.append(
        f"실패 {monitor.session_errors}",
        style="bold red" if monitor.session_errors else "black",
    )

    table = Table(expand=True, header_style="bold black", border_style="black")
    table.add_column("언론사")
    table.add_column("소스", justify="right")
    table.add_column("피드 항목", justify="right")
    table.add_column("신규 적재", justify="right")
    table.add_column("중복", justify="right")
    table.add_column("실패", justify="right")
    table.add_column("상태")

    for publisher in sorted(monitor.publishers):
        progress = monitor.publishers[publisher]
        symbol, style = _STATUS[progress.status]
        table.add_row(
            Text(publisher, style="bold black"),
            Text(f"{progress.done_sources}/{progress.total_sources}", style="black"),
            Text(str(progress.processed), style="black"),
            Text(str(progress.created), style="bold green"),
            Text(str(progress.skipped), style="black"),
            Text(str(progress.errors), style="bold red") if progress.errors else "·",
            Text(symbol, style=style),
        )
    if monitor.publishers:
        table.add_section()
        table.add_row(
            Text("합계", style="bold black"),
            Text(f"{monitor.sources_done}/{monitor.sources_total}", style="bold black"),
            Text(str(monitor.cycle_processed), style="bold black"),
            Text(str(monitor.cycle_created), style="bold green"),
            Text(str(monitor.cycle_skipped), style="bold black"),
            Text(str(monitor.cycle_errors), style="bold red")
            if monitor.cycle_errors
            else "·",
            "",
        )

    renderables: list[object] = [Panel(header, border_style="black"), table]
    if monitor.recent_errors:
        error_text = Text(
            "\n".join(f"• {message}" for message in monitor.recent_errors),
            style="red",
        )
        renderables.append(
            Panel(error_text, title="최근 실패", border_style="red", title_align="left")
        )
    return Group(*renderables)
