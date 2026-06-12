"""뉴스 RSS 수집, 본문 수집, 분석을 독립 실행하는 CLI를 제공한다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Callable, Sequence

import duckdb
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .db.init import DEFAULT_DB_PATH, connect_database, create_schema
from .db.locking import single_writer_lock
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
DbPathOption = Annotated[
    Path,
    typer.Option(
        "--db-path",
        envvar="NEWS_DB_PATH",
        help="DuckDB path. NEWS_DB_PATH is also supported.",
    ),
]


def _default_db_path() -> Path:
    return Path(os.environ.get("NEWS_DB_PATH", DEFAULT_DB_PATH))


def _execute(
    *,
    db_path: Path,
    command: str,
    parameters: dict[str, object],
    operation_factory: Callable[[duckdb.DuckDBPyConnection], OperationResult],
) -> OperationResult:
    with single_writer_lock(db_path):
        with connect_database(db_path) as connection:
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
        return f"수집 중 · {_source_label(sources[next_index])}"
    return "수집 완료"


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
    db_path: DbPathOption = _default_db_path(),
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

            def update(connection: duckdb.DuckDBPyConnection) -> OperationResult:
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
                db_path=db_path,
                command="update-symbols",
                parameters={"markets": list(markets)},
                operation_factory=update,
            )
    except (OSError, RuntimeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    _print_result("update-symbols", result)


@app.command("collect-rss")
def collect_rss_command(
    db_path: DbPathOption = _default_db_path(),
    feed: Annotated[
        list[str] | None,
        typer.Option(
            "--feed",
            help="Repeatable publisher=URL override. Defaults to configured feeds.",
        ),
    ] = None,
) -> None:
    """RSS 항목을 수집해 DuckDB에 멱등하게 저장한다."""

    try:
        sources = (
            tuple(parse_feed_source(value) for value in feed)
            if feed
            else DEFAULT_FEED_SOURCES
        )
        source_results: list[tuple[FeedSource, OperationResult]] = []
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task(
                _progress_description(sources, 0),
                total=len(sources),
            )

            def record_source_result(
                source: FeedSource,
                result: OperationResult,
            ) -> None:
                source_results.append((source, result))
                progress.update(
                    task,
                    advance=1,
                    description=_progress_description(sources, len(source_results)),
                )

            result = _execute(
                db_path=db_path,
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
        return f"수집 중 · {_article_label(pending[next_index])}"
    return "수집 완료"


@app.command("collect-articles")
def collect_articles_command(
    db_path: DbPathOption = _default_db_path(),
    limit: Annotated[int, typer.Option(min=1)] = 100,
) -> None:
    """본문이 없거나 parser 버전이 지난 기사를 수집한다."""

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("수집 대상 조회 중…", total=None)
        pending_items: list[object] = []
        finished = 0

        def on_pending(items: Sequence[object]) -> None:
            pending_items.extend(items)
            progress.update(
                task,
                total=len(pending_items),
                description=_article_progress_description(pending_items, 0),
            )

        def on_item_result(item: object, item_result: OperationResult) -> None:
            nonlocal finished
            finished += 1
            progress.update(
                task,
                advance=1,
                description=_article_progress_description(pending_items, finished),
            )

        result = _execute(
            db_path=db_path,
            command="collect-articles",
            parameters={"limit": limit},
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
    db_path: DbPathOption = _default_db_path(),
    limit: Annotated[int, typer.Option(min=1)] = 100,
) -> None:
    """아직 분석되지 않은 기사에 결정적 기본 통계를 계산한다."""

    result = _execute(
        db_path=db_path,
        command="analyze",
        parameters={"limit": limit},
        operation_factory=lambda connection: analyze_articles(
            connection,
            limit=limit,
        ),
    )
    _print_result("analyze", result)


@app.command("extract-entities")
def extract_entities_command(
    db_path: DbPathOption = _default_db_path(),
    limit: Annotated[int, typer.Option(min=1)] = 100,
) -> None:
    """종목 마스터 어휘집으로 기사별 종목 entity를 추출한다."""

    try:
        result = _execute(
            db_path=db_path,
            command="extract-entities",
            parameters={"limit": limit},
            operation_factory=lambda connection: extract_entities(
                connection,
                limit=limit,
            ),
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    _print_result("extract-entities", result)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
