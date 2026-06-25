"""뉴스 RSS 수집, 본문 수집, 분석을 독립 실행하는 CLI를 제공한다."""

from __future__ import annotations

import time
from typing import Annotated, Callable, Sequence

import psycopg
import typer
from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column, Table

from modules.storage.news_intelligence.database import load_env

from .db.init import connect_database, create_schema
from .monitor import CollectRssMonitor, render_dashboard
from .pipeline import (
    DEFAULT_FEED_SOURCES,
    FeedSource,
    OperationResult,
    analyze_articles,
    collect_articles,
    collect_rss,
    extract_entities,
    parse_feed_source,
    run_recorded_operation,
)
from .symbols import NEWS_SYMBOL_MARKETS, update_symbol_masters


app = typer.Typer(no_args_is_help=True, help=__doc__)
DsnOption = Annotated[
    str | None,
    typer.Option(
        "--dsn",
        envvar="INTELLIGENCE_DATABASE_URL",
        help=(
            "Supabase PostgreSQL DSN shared with finlabs_intelligence. "
            "INTELLIGENCE_DATABASE_URL is also supported."
        ),
    ),
]


def _execute(
    *,
    dsn: str | None,
    command: str,
    parameters: dict[str, object],
    operation_factory: Callable[[psycopg.Connection], OperationResult],
) -> OperationResult:
    # Concurrency is owned by the PostgreSQL server, so the old DuckDB file lock
    # is gone; the connection autocommits each statement like DuckDB did.
    with connect_database(dsn) as connection:
        create_schema(connection)
        return run_recorded_operation(
            connection,
            command=command,
            parameters=parameters,
            operation=lambda: operation_factory(connection),
        )


def _print_result(command: str, result: OperationResult) -> None:
    typer.echo(
        f"{command}: processed={result.processed} "
        f"created={result.created} skipped={result.skipped}"
    )


def _source_label(source: FeedSource) -> str:
    return f"{source.publisher} · {source.feed_category or '전체'}"


def _progress_description(sources: Sequence[FeedSource], next_index: int) -> str:
    if next_index < len(sources):
        return _source_label(sources[next_index])
    return ""


def _print_rss_source_summary(
    source_results: Sequence[tuple[FeedSource, OperationResult]],
) -> None:
    """언론사·카테고리별 수집 건수를 표로 출력한다."""

    table = Table(title="언론사·카테고리별 수집 결과")
    table.add_column("언론사")
    table.add_column("카테고리")
    table.add_column("피드 항목", justify="right")
    table.add_column("신규 저장", justify="right")
    table.add_column("중복 제외", justify="right")

    by_publisher: dict[str, list[tuple[FeedSource, OperationResult]]] = {}
    for source, result in source_results:
        by_publisher.setdefault(source.publisher, []).append((source, result))

    for publisher, rows in by_publisher.items():
        for index, (source, result) in enumerate(rows):
            table.add_row(
                publisher if index == 0 else "",
                source.feed_category or "전체",
                str(result.processed),
                str(result.created),
                str(result.skipped),
            )
        if len(rows) > 1:
            table.add_row(
                "",
                "소계",
                str(sum(result.processed for _, result in rows)),
                str(sum(result.created for _, result in rows)),
                str(sum(result.skipped for _, result in rows)),
                style="bold",
            )
        table.add_section()
    table.add_row(
        "합계",
        "",
        str(sum(result.processed for _, result in source_results)),
        str(sum(result.created for _, result in source_results)),
        str(sum(result.skipped for _, result in source_results)),
        style="bold",
    )
    Console().print(table)


@app.command("update-symbols")
def update_symbols_command(
    dsn: DsnOption = None,
    market: Annotated[
        list[str] | None,
        typer.Option(
            "--market",
            help=(
                "Repeatable market. Defaults to KOSPI, KOSDAQ, NASDAQ, NYSE, and AMEX."
            ),
        ),
    ] = None,
) -> None:
    """KIS 국내·해외 종목 마스터를 뉴스 DB에 분리 저장한다."""

    markets = tuple(market or NEWS_SYMBOL_MARKETS)

    try:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("다운로드 중…", total=len(markets))
            completed: list[tuple[str, int]] = []

            def on_market_downloaded(mkt: str, count: int) -> None:
                completed.append((mkt, count))
                next_desc = (
                    f"다운로드 중 · {markets[len(completed)]}"
                    if len(completed) < len(markets)
                    else "저장 중…"
                )
                progress.update(task, advance=1, description=next_desc)

            def update(connection: psycopg.Connection) -> OperationResult:
                downloaded, stored = update_symbol_masters(
                    connection,
                    markets=markets,
                    on_market_downloaded=on_market_downloaded,
                )
                progress.update(task, description="완료")
                return OperationResult(
                    processed=downloaded,
                    created=stored,
                    skipped=downloaded - stored,
                )

            result = _execute(
                dsn=dsn,
                command="update-symbols",
                parameters={"markets": list(markets)},
                operation_factory=update,
            )
    except (OSError, RuntimeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    _print_result("update-symbols", result)


@app.command("collect-rss")
def collect_rss_command(
    dsn: DsnOption = None,
    feed: Annotated[
        list[str] | None,
        typer.Option(
            "--feed",
            help="Repeatable publisher=URL override. Defaults to configured feeds.",
        ),
    ] = None,
) -> None:
    """RSS 항목을 수집해 Supabase PostgreSQL에 멱등하게 저장한다."""

    try:
        sources = (
            tuple(parse_feed_source(value) for value in feed)
            if feed
            else DEFAULT_FEED_SOURCES
        )
        source_results: list[tuple[FeedSource, OperationResult]] = []
        with Progress(
            TextColumn(
                "[progress.description]{task.fields[status]}",
                table_column=Column(width=9, no_wrap=True),
            ),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task(
                _progress_description(sources, 0),
                total=len(sources),
                status="수집 중",
            )

            def record_source_result(
                source: FeedSource,
                result: OperationResult,
            ) -> None:
                source_results.append((source, result))
                finished = len(source_results)
                progress.update(
                    task,
                    advance=1,
                    description=_progress_description(sources, finished),
                    status="수집 중" if finished < len(sources) else "수집 완료",
                )

            result = _execute(
                dsn=dsn,
                command="collect-rss",
                parameters={"feeds": [source.url for source in sources]},
                operation_factory=lambda connection: collect_rss(
                    connection,
                    sources=sources,
                    on_source_result=record_source_result,
                ),
            )
    except (RuntimeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    _print_rss_source_summary(source_results)
    if result.errors:
        console = Console(stderr=True)
        for msg in result.errors:
            console.print(f"[yellow]경고: 피드 파싱 실패 — {msg}[/yellow]")
    _print_result("collect-rss", result)


@app.command("monitor")
def monitor_command(
    dsn: DsnOption = None,
    feed: Annotated[
        list[str] | None,
        typer.Option(
            "--feed",
            help="Repeatable publisher=URL override. Defaults to configured feeds.",
        ),
    ] = None,
    interval: Annotated[
        int | None,
        typer.Option(
            "--interval",
            min=1,
            help="초 단위 반복 간격. 생략하면 1회만 실행하고 종료합니다.",
        ),
    ] = None,
) -> None:
    """collect-rss를 실행하며 수집·적재·성공·실패 현황을 Rich 라이브 대시보드로 표시한다."""

    try:
        sources = (
            tuple(parse_feed_source(value) for value in feed)
            if feed
            else DEFAULT_FEED_SOURCES
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    monitor = CollectRssMonitor()
    console = Console()

    def refresh(live: Live, status_line: str) -> None:
        live.update(
            render_dashboard(
                monitor,
                status_line=status_line,
                elapsed_seconds=monitor.elapsed_seconds(),
            )
        )

    parameters = {"feeds": [source.url for source in sources]}
    try:
        with connect_database(dsn) as connection:
            create_schema(connection)
            with Live(console=console, refresh_per_second=8) as live:
                # The on_source_result callback fires on the main thread as each
                # publisher group finishes, so updating Live here is safe.
                def on_source_result(source: FeedSource, result: OperationResult) -> None:
                    monitor.record_source(source, result)
                    refresh(live, "수집 중…")

                while True:
                    monitor.begin_cycle(sources)
                    refresh(live, "수집 중…")
                    run_recorded_operation(
                        connection,
                        command="collect-rss",
                        parameters=parameters,
                        operation=lambda: collect_rss(
                            connection,
                            sources=sources,
                            on_source_result=on_source_result,
                        ),
                    )
                    if interval is None:
                        refresh(live, "완료")
                        break
                    deadline = time.monotonic() + interval
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        refresh(live, f"다음 실행까지 {int(remaining) + 1}s")
                        time.sleep(min(0.5, remaining))
    except KeyboardInterrupt:
        console.print("[dim]모니터를 종료합니다.[/dim]")
    except (RuntimeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error


def _article_label(item: object, *, width: int = 48) -> str:
    publisher = getattr(item, "publisher", "")
    title = getattr(item, "title", "")
    if len(title) > width:
        title = f"{title[: width - 1]}…"
    return f"{publisher} · {title}"


def _article_progress_description(
    pending: Sequence[object],
    next_index: int,
) -> str:
    if next_index < len(pending):
        return _article_label(pending[next_index])
    return ""


@app.command("collect-articles")
def collect_articles_command(
    dsn: DsnOption = None,
    limit: Annotated[int, typer.Option(min=1)] = 100,
    all_items: Annotated[
        bool,
        typer.Option("--all", help="미수집·재처리 대상 전체를 수집합니다."),
    ] = False,
) -> None:
    """RSS 기사 링크에서 본문을 수집해 저장한다."""

    _collect_articles_with_progress(dsn, None if all_items else limit)


def _collect_articles_with_progress(dsn: str | None, limit: int | None) -> None:
    """언론사 페이지 본문 수집 진행 상황과 결과를 출력한다."""

    with Progress(
        TextColumn(
            "[progress.description]{task.fields[status]}",
            table_column=Column(width=9, no_wrap=True),
        ),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task("", total=None, status="조회 중")
        pending_items: list[object] = []
        finished = 0

        def on_pending(items: Sequence[object]) -> None:
            pending_items.extend(items)
            progress.update(
                task,
                total=len(pending_items),
                description=_article_progress_description(pending_items, 0),
                status="수집 중" if pending_items else "수집 완료",
            )

        def on_item_result(item: object, item_result: OperationResult) -> None:
            nonlocal finished
            finished += 1
            progress.update(
                task,
                advance=1,
                description=_article_progress_description(pending_items, finished),
                status=(
                    "수집 중" if finished < len(pending_items) else "수집 완료"
                ),
            )

        result = _execute(
            dsn=dsn,
            command="collect-articles",
            parameters={"limit": limit, "all": limit is None},
            operation_factory=lambda connection: collect_articles(
                connection,
                limit=limit,
                on_pending=on_pending,
                on_item_result=on_item_result,
            ),
        )
    if result.errors:
        console = Console(stderr=True)
        for msg in result.errors:
            console.print(f"[yellow]경고: 본문 수집 실패 — {msg}[/yellow]")
    _print_result("collect-articles", result)


@app.command("analyze")
def analyze_command(
    dsn: DsnOption = None,
    limit: Annotated[int, typer.Option(min=1)] = 100,
    all_items: Annotated[
        bool,
        typer.Option("--all", help="미분석·재처리 대상 전체를 처리합니다."),
    ] = False,
) -> None:
    """아직 분석되지 않은 기사에 결정적 기본 통계를 계산한다."""

    _analyze_with_progress(dsn, None if all_items else limit)


def _analyze_with_progress(dsn: str | None, limit: int | None) -> None:
    """기사 기본 통계 분석 진행 상황과 결과를 출력한다."""

    with Progress(
        TextColumn(
            "[progress.description]{task.fields[status]}",
            table_column=Column(width=9, no_wrap=True),
        ),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task("", total=None, status="조회 중")
        pending_count = 0
        finished = 0

        def on_pending(items: tuple[tuple[object, str], ...]) -> None:
            nonlocal pending_count
            pending_count = len(items)
            progress.update(
                task,
                total=pending_count,
                status="분석 중" if pending_count else "분석 완료",
            )

        def on_item_result(
            article: object,
            title: str,
            item_result: OperationResult,
        ) -> None:
            nonlocal finished
            finished += 1
            display_title = title if len(title) <= 60 else f"{title[:59]}…"
            progress.update(
                task,
                advance=1,
                description="" if finished >= pending_count else display_title,
                status="분석 중" if finished < pending_count else "분석 완료",
            )

        result = _execute(
            dsn=dsn,
            command="analyze",
            parameters={"limit": limit, "all": limit is None},
            operation_factory=lambda connection: analyze_articles(
                connection,
                limit=limit,
                on_pending=on_pending,
                on_item_result=on_item_result,
            ),
        )
    _print_result("analyze", result)


@app.command("extract-entities")
def extract_entities_command(
    dsn: DsnOption = None,
    limit: Annotated[int, typer.Option(min=1)] = 100,
    all_items: Annotated[
        bool,
        typer.Option("--all", help="미추출·재처리 대상 전체를 처리합니다."),
    ] = False,
) -> None:
    """종목 마스터 어휘집으로 기사별 종목 entity를 추출한다."""

    _extract_entities_with_progress(dsn, None if all_items else limit)


def _extract_entities_with_progress(dsn: str | None, limit: int | None) -> None:
    """기사별 종목 entity 추출 진행 상황과 결과를 출력한다."""

    try:
        with Progress(
            TextColumn(
                "[progress.description]{task.fields[status]}",
                table_column=Column(width=9, no_wrap=True),
            ),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task("", total=None, status="조회 중")
            pending_count = 0
            finished = 0

            def on_pending(
                items: tuple[tuple[object, str], ...],
            ) -> None:
                nonlocal pending_count
                pending_count = len(items)
                progress.update(
                    task,
                    total=pending_count,
                    status="추출 중" if pending_count else "추출 완료",
                )

            def on_item_result(
                article: object,
                title: str,
                item_result: OperationResult,
            ) -> None:
                nonlocal finished
                finished += 1
                display_title = title if len(title) <= 60 else f"{title[:59]}…"
                progress.update(
                    task,
                    advance=1,
                    description="" if finished >= pending_count else display_title,
                    status="추출 중" if finished < pending_count else "추출 완료",
                )

            result = _execute(
                dsn=dsn,
                command="extract-entities",
                parameters={"limit": limit, "all": limit is None},
                operation_factory=lambda connection: extract_entities(
                    connection,
                    limit=limit,
                    on_pending=on_pending,
                    on_item_result=on_item_result,
                ),
            )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    _print_result("extract-entities", result)


def main() -> None:
    # Load .env before Typer resolves --dsn from INTELLIGENCE_DATABASE_URL so a
    # developer DSN in the file is honored without exporting it to the shell.
    load_env()
    app()


if __name__ == "__main__":
    main()
