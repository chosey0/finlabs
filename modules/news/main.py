"""뉴스 RSS 수집, 본문 수집, 분석을 독립 실행하는 CLI를 제공한다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Callable

import duckdb
import typer

from .db.init import DEFAULT_DB_PATH, connect_database, create_schema
from .pipeline import (
    DEFAULT_FEED_SOURCES,
    OperationResult,
    analyze_articles,
    collect_articles,
    collect_rss,
    parse_feed_source,
    run_recorded_operation,
    single_writer_lock,
)


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
        result = _execute(
            db_path=db_path,
            command="collect-rss",
            parameters={"feeds": [source.url for source in sources]},
            operation_factory=lambda connection: collect_rss(
                connection,
                sources=sources,
            ),
        )
    except (RuntimeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    _print_result("collect-rss", result)


@app.command("collect-articles")
def collect_articles_command(
    db_path: DbPathOption = _default_db_path(),
    limit: Annotated[int, typer.Option(min=1)] = 100,
) -> None:
    """아직 저장되지 않은 기사 본문을 수집한다."""

    result = _execute(
        db_path=db_path,
        command="collect-articles",
        parameters={"limit": limit},
        operation_factory=lambda connection: collect_articles(
            connection,
            limit=limit,
        ),
    )
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
