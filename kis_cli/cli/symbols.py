from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from kis import ALL_SYMBOL_MARKETS

from kis_cli.cli.common import console, prompt_supabase_dsn_if_missing
from kis_cli.services.symbols import download_and_store_symbols, search_stored_symbols

symbols_app = typer.Typer(help="Download and query symbol masters.", no_args_is_help=True)


@symbols_app.command("download")
def symbols_download(
    market: Annotated[
        str | None,
        typer.Option("--market", help="Market to download, for example KOSPI, KOSDAQ, NASDAQ, NYSE, or AMEX."),
    ] = None,
    all_markets: Annotated[
        bool,
        typer.Option("--all", help="Download every supported domestic and overseas symbol master."),
    ] = False,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend to write: duckdb or supabase."),
    ] = "duckdb",
) -> None:
    """Download KIS symbol master files and upsert them into the warehouse."""
    if all_markets and market:
        raise typer.BadParameter("pass either --market or --all, not both")
    if not all_markets and not market:
        raise typer.BadParameter("pass --market or --all")
    normalized_store = _normalize_store(store)
    if normalized_store == "supabase" and db_path is not None:
        raise typer.BadParameter("--db-path is only valid with --store duckdb")
    supabase_dsn = prompt_supabase_dsn_if_missing() if normalized_store == "supabase" else None

    markets = ALL_SYMBOL_MARKETS if all_markets else (market or "",)
    results = []
    try:
        if all_markets:
            with typer.progressbar(markets, label="Downloading symbol masters") as progress:
                for item in progress:
                    results.append(
                        download_and_store_symbols(
                            market=item,
                            db_path=db_path,
                            store=normalized_store,
                            supabase_dsn=supabase_dsn,
                        )
                    )
        else:
            for item in markets:
                with console.status(f"Downloading symbol master: {item}..."):
                    results.append(
                        download_and_store_symbols(
                            market=item,
                            db_path=db_path,
                            store=normalized_store,
                            supabase_dsn=supabase_dsn,
                        )
                    )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except OSError as exc:
        raise typer.BadParameter(f"failed to download symbol master: {exc}") from exc

    _print_symbols_download_result(results)


@symbols_app.command("search")
def symbols_search(
    query: Annotated[
        str,
        typer.Option("--query", "-q", help="Search by symbol, Korean name, or English name."),
    ],
    market: Annotated[
        str | None,
        typer.Option("--market", help="Restrict search to one market."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=100, help="Maximum number of rows to show."),
    ] = 20,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
) -> None:
    """Search locally stored symbols."""
    if not query.strip():
        raise typer.BadParameter("query must not be empty")
    try:
        with console.status("Searching symbols..."):
            rows = search_stored_symbols(
                query=query.strip(),
                market=market,
                db_path=db_path,
                limit=limit,
            )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_symbols_search_result(rows)


def _print_symbols_download_result(results: list) -> None:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Market", style="bold cyan")
    table.add_column("Downloaded", justify="right")
    table.add_column("Stored", justify="right")
    table.add_column("Store")
    table.add_column("Database")
    for result in results:
        table.add_row(
            result.market,
            str(result.downloaded),
            str(result.stored),
            result.store,
            str(result.db_path) if result.db_path else "-",
        )
    console.print(
        Panel(
            table,
            title="Symbols downloaded",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_symbols_search_result(rows) -> None:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Market", style="bold cyan")
    table.add_column("Symbol", style="bold")
    table.add_column("Realtime symbol")
    table.add_column("Korean name")
    table.add_column("English name")
    table.add_column("Currency")
    table.add_column("Type")
    for row in rows:
        table.add_row(
            row["market"],
            row["symbol"],
            row["realtime_symbol"] or "",
            row["korean_name"] or "",
            row["english_name"] or "",
            row["currency"] or "",
            row["security_type"] or "",
        )
    console.print(table)


def _normalize_store(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"duckdb", "supabase"}:
        raise typer.BadParameter("store must be one of: duckdb, supabase")
    return normalized
