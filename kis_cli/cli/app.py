from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich_inquirer import ConfirmPrompt, SelectPrompt, TextPrompt

from kis_cli.config.paths import default_config_file
from kis_cli.config.init import ConfigInitResult, init_config
from kis_cli.config.profiles import (
    ProfileAddResult,
    ProfileCredentials,
    ProfileDeleteResult,
    add_profile,
    delete_profile,
    update_profile,
)
from kis_cli.config.resolver import ResolvedProfile, mask_account, mask_secret, resolve_profile
from kis_cli.config.resolver import read_config
from kis_cli.core.auth import KisAuthError
from kis_cli.core.client import KisApiError
from kis_cli.core.price import CurrentPrice
from kis_cli.core.symbol_master import ALL_SYMBOL_MARKETS
from kis_cli.services.auth import (
    AuthClearResult,
    AuthStatusResult,
    AuthTestResult,
    clear_auth_tokens,
    get_auth_statuses,
    test_auth,
)
from kis_cli.services.chart import ChartHistoryResult, collect_ohlcv_history
from kis_cli.services.price import get_current_price
from kis_cli.services.query import OhlcvQueryResult, query_stored_daily_ohlcv
from kis_cli.services.symbols import download_and_store_symbols, search_stored_symbols
from kis_cli.storage import (
    DatabaseCountsResult,
    DatabaseInitResult,
    DatabaseSchemaResult,
    init_database,
    inspect_database_counts,
    inspect_database_schema,
)
from kis_cli.storage.app_db import init_app_database
from kis_cli.storage.app_repositories import list_api_logs, list_ingest_runs

app = typer.Typer(
    help="Collect domestic and overseas stock data with the KIS Open API.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage kis-cli configuration.", no_args_is_help=True)
auth_app = typer.Typer(help="Authenticate with the KIS Open API.", no_args_is_help=True)
db_app = typer.Typer(help="Manage kis-cli local storage.", no_args_is_help=True)
symbols_app = typer.Typer(help="Download and query symbol masters.", no_args_is_help=True)
price_app = typer.Typer(help="Query REST price data.", no_args_is_help=True)
chart_app = typer.Typer(help="Collect REST OHLCV history.", no_args_is_help=True)
query_app = typer.Typer(help="Query and export locally stored data.", no_args_is_help=True)
logs_app = typer.Typer(help="Inspect local app logs.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(auth_app, name="auth")
app.add_typer(db_app, name="db")
app.add_typer(symbols_app, name="symbols")
app.add_typer(price_app, name="price")
app.add_typer(chart_app, name="chart")
app.add_typer(query_app, name="query")
app.add_typer(logs_app, name="logs")
console = Console()
CANCEL_EXIT_CODE = 130


@config_app.command("init")
def config_init(
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="Profile name to create and activate.",
        ),
    ] = "real",
    environment: Annotated[
        str | None,
        typer.Option(
            "--environment",
            help="KIS API environment. Defaults to profile when profile is real or mock.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite an existing config file.",
        ),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Write config to a custom path instead of the platform config directory.",
        ),
    ] = None,
) -> None:
    """Create a profile-based config template."""
    try:
        result = init_config(
            profile=profile,
            environment=environment,
            force=force,
            config_path=path,
        )
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_config_init_result(result)


@config_app.command("add")
def config_add(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Write config to a custom path instead of the platform config directory.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite an existing profile with the same name.",
        ),
    ] = False,
) -> None:
    """Add a profile using interactive prompts."""
    credentials = _prompt_profile_credentials()
    try:
        result = add_profile(credentials, config_path=path, force=force)
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_profile_add_result(result)


@config_app.command("validate")
def config_validate(
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Profile name to validate. Defaults to active_profile.",
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Read config from a custom path instead of the platform config directory.",
        ),
    ] = None,
) -> None:
    """Validate and resolve a profile without printing secrets."""
    try:
        resolved = resolve_profile(profile=profile, config_path=path)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_validate_result(resolved)


@config_app.command("update")
def config_update(
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Profile name to update. Prompts when omitted.",
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Read config from a custom path instead of the platform config directory.",
        ),
    ] = None,
) -> None:
    """Update an existing profile using interactive prompts."""
    profile_name = profile or _prompt_existing_profile(path)
    try:
        current = resolve_profile(profile=profile_name, config_path=path)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    credentials = _prompt_profile_update(current)
    try:
        result = update_profile(credentials, config_path=path)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_profile_add_result(result, title="Profile updated")


@config_app.command("delete")
def config_delete(
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Profile name to delete. Prompts when omitted.",
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Read config from a custom path instead of the platform config directory.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Delete without confirmation.",
        ),
    ] = False,
) -> None:
    """Delete a profile and its stored environment values."""
    profile_name = profile or _prompt_existing_profile(path)
    if not yes:
        confirmed = _prompt_value_or_exit(
            ConfirmPrompt(f"Delete profile '{profile_name}'?", default=False).ask()
        )
        if not confirmed:
            typer.echo("Delete cancelled")
            return

    try:
        result = delete_profile(profile_name, config_path=path)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_profile_delete_result(result)


@auth_app.command("test")
def auth_test(
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Profile name to authenticate. Defaults to active_profile.",
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Read config from a custom path instead of the platform config directory.",
        ),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Ignore a valid cached token and request a new one.",
        ),
    ] = False,
) -> None:
    """Issue or reuse a REST access token without printing secrets."""
    try:
        result = test_auth(profile=profile, config_path=path, refresh=refresh)
    except (FileNotFoundError, ValueError, KisAuthError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_auth_test_result(result)


@auth_app.command("status")
def auth_status(
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Profile name to inspect. Defaults to active_profile.",
        ),
    ] = None,
    all_profiles: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Inspect token status for every configured profile.",
        ),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Read config from a custom path instead of the platform config directory.",
        ),
    ] = None,
) -> None:
    """Show cached REST token status without contacting KIS."""
    try:
        results = get_auth_statuses(
            profile=profile,
            all_profiles=all_profiles,
            config_path=path,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_auth_status_result(results)


@auth_app.command("clear")
def auth_clear(
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Profile name to clear. Defaults to active_profile.",
        ),
    ] = None,
    all_profiles: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Clear cached tokens for every configured profile.",
        ),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Read config from a custom path instead of the platform config directory.",
        ),
    ] = None,
) -> None:
    """Remove cached REST tokens without contacting KIS."""
    try:
        results = clear_auth_tokens(
            profile=profile,
            all_profiles=all_profiles,
            config_path=path,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_auth_clear_result(results)


@db_app.command("init")
def db_init(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Create or update a DuckDB warehouse at a custom path.",
        ),
    ] = None,
) -> None:
    """Create the local app database and DuckDB warehouse schemas."""
    result = init_database(path)
    _print_database_init_result(result)


@db_app.command("schema")
def db_schema(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Inspect a DuckDB warehouse at a custom path.",
        ),
    ] = None,
) -> None:
    """Inspect local warehouse tables, columns, and indexes."""
    try:
        result = inspect_database_schema(path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_database_schema_result(result)


@db_app.command("counts")
def db_counts(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Inspect row counts in a DuckDB warehouse at a custom path.",
        ),
    ] = None,
) -> None:
    """Show row counts for each local warehouse table."""
    try:
        result = inspect_database_counts(path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_database_counts_result(result)


@logs_app.command("runs")
def logs_runs(
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=500, help="Maximum number of runs to show."),
    ] = 20,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Inspect a custom app SQLite database path."),
    ] = None,
) -> None:
    """Show recent ingest run records from the app database."""
    app_db_path = init_app_database(path)
    _print_ingest_runs(list_ingest_runs(app_db_path, limit=limit), app_db_path)


@logs_app.command("api")
def logs_api(
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=500, help="Maximum number of API log rows to show."),
    ] = 20,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Inspect a custom app SQLite database path."),
    ] = None,
) -> None:
    """Show recent API log records from the app database."""
    app_db_path = init_app_database(path)
    _print_api_logs(list_api_logs(app_db_path, limit=limit), app_db_path)


@symbols_app.command("download")
def symbols_download(
    market: Annotated[
        str | None,
        typer.Option(
            "--market",
            help="Market to download, for example KOSPI, KOSDAQ, NASDAQ, NYSE, or AMEX.",
        ),
    ] = None,
    all_markets: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Download every supported domestic and overseas symbol master.",
        ),
    ] = False,
    db_path: Annotated[
        Path | None,
        typer.Option(
            "--db-path",
            help="Use a custom DuckDB warehouse path.",
        ),
    ] = None,
) -> None:
    """Download KIS symbol master files and upsert them into the warehouse."""
    if all_markets and market:
        raise typer.BadParameter("pass either --market or --all, not both")
    if not all_markets and not market:
        raise typer.BadParameter("pass --market or --all")

    markets = ALL_SYMBOL_MARKETS if all_markets else (market or "",)
    results = []
    try:
        if all_markets:
            with typer.progressbar(markets, label="Downloading symbol masters") as progress:
                for item in progress:
                    results.append(download_and_store_symbols(market=item, db_path=db_path))
        else:
            for item in markets:
                results.append(download_and_store_symbols(market=item, db_path=db_path))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except OSError as exc:
        raise typer.BadParameter(f"failed to download symbol master: {exc}") from exc

    _print_symbols_download_result(results)


@symbols_app.command("search")
def symbols_search(
    query: Annotated[
        str,
        typer.Option(
            "--query",
            "-q",
            help="Search by symbol, Korean name, or English name.",
        ),
    ],
    market: Annotated[
        str | None,
        typer.Option(
            "--market",
            help="Restrict search to one market.",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            min=1,
            max=100,
            help="Maximum number of rows to show.",
        ),
    ] = 20,
    db_path: Annotated[
        Path | None,
        typer.Option(
            "--db-path",
            help="Use a custom DuckDB warehouse path.",
        ),
    ] = None,
) -> None:
    """Search locally stored symbols."""
    if not query.strip():
        raise typer.BadParameter("query must not be empty")
    try:
        rows = search_stored_symbols(
            query=query.strip(),
            market=market,
            db_path=db_path,
            limit=limit,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_symbols_search_result(rows)


@price_app.command("current")
def price_current(
    symbol: Annotated[
        str,
        typer.Option(
            "--symbol",
            help="Stock symbol to query, for example 005930 or AAPL.",
        ),
    ],
    market: Annotated[
        str,
        typer.Option(
            "--market",
            help="Market, for example KOSPI, KOSDAQ, NASDAQ, NYSE, or AMEX.",
        ),
    ],
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Profile name to authenticate. Defaults to active_profile.",
        ),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Read config from a custom path instead of the platform config directory.",
        ),
    ] = None,
) -> None:
    """Query the current REST quote for one stock."""
    try:
        result = get_current_price(
            symbol=symbol,
            market=market,
            profile=profile,
            config_path=path,
        )
    except (FileNotFoundError, ValueError, KisAuthError, KisApiError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_current_price_result(result)


@chart_app.command("history")
def chart_history(
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Stock symbol to collect, for example 005930 or AAPL."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="Start date in YYYY-MM-DD or YYYYMMDD format."),
    ],
    end: Annotated[
        str | None,
        typer.Option("--end", help="End date in YYYY-MM-DD or YYYYMMDD format. Defaults to today."),
    ] = None,
    period: Annotated[
        str,
        typer.Option("--period", help="Period: D, W, M, or Y."),
    ] = "D",
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name to authenticate. Defaults to active_profile."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path."),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
    save: Annotated[
        bool,
        typer.Option("--save", help="Persist bars into the local warehouse ohlcv_bars table."),
    ] = False,
    adjusted: Annotated[
        bool,
        typer.Option("--adjusted/--raw-price", help="Use adjusted prices for domestic history."),
    ] = True,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", min=1, max=1000, help="Maximum continuation requests."),
    ] = 100,
) -> None:
    """Collect domestic or overseas OHLCV history with continuation support."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period=period,
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("daily")
def chart_daily(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect daily OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="D",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("weekly")
def chart_weekly(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect weekly OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="W",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("monthly")
def chart_monthly(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect monthly OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="M",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("yearly")
def chart_yearly(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect yearly OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="Y",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@query_app.command("ohlcv")
def query_ohlcv(
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Stock symbol to query, for example 005930 or AAPL."),
    ],
    start: Annotated[
        str | None,
        typer.Option("--start", help="Start date in YYYY-MM-DD or YYYYMMDD format."),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", help="End date in YYYY-MM-DD or YYYYMMDD format."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=10000, help="Maximum number of daily bars to show."),
    ] = 20,
    all_rows: Annotated[
        bool,
        typer.Option("--all", help="Show all matching daily bars instead of applying --limit."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table, json, or csv."),
    ] = "table",
    export_path: Annotated[
        Path | None,
        typer.Option("--export", help="Export rows to a .csv or .json file."),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
) -> None:
    """Query locally stored daily OHLCV bars."""
    normalized_format = _normalize_output_format(output_format)
    try:
        result = query_stored_daily_ohlcv(
            symbol=symbol,
            start=start,
            end=end,
            limit=None if all_rows else limit,
            db_path=db_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if export_path is not None:
        export_format = _export_format(export_path, fallback=normalized_format)
        _export_ohlcv_rows(result.rows, export_path, export_format)
        _print_export_result(export_path=export_path, row_count=len(result.rows), export_format=export_format)
        return

    _print_ohlcv_query_result(result, output_format=normalized_format)


def _run_chart_history(
    *,
    symbol: str,
    start: str,
    end: str | None,
    period: str,
    profile: str | None,
    path: Path | None,
    db_path: Path | None,
    save: bool,
    adjusted: bool,
    max_pages: int,
) -> None:
    try:
        result = collect_ohlcv_history(
            symbol=symbol,
            start=start,
            end=end,
            period=period,
            profile=profile,
            config_path=path,
            db_path=db_path,
            save=save,
            adjusted=adjusted,
            max_pages=max_pages,
        )
    except (FileNotFoundError, ValueError, KisAuthError, KisApiError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_chart_history_result(result)


def _prompt_profile_credentials() -> ProfileCredentials:
    profile_name = _prompt_value_or_exit(TextPrompt("Profile name").ask())
    environment = _prompt_value_or_exit(
        SelectPrompt(
            "Environment",
            choices=[("real", "real"), ("mock", "mock")],
        ).ask()
    )
    account_no = _prompt_value_or_exit(TextPrompt("Account number").ask())
    app_key = _prompt_value_or_exit(TextPrompt("APP key", password=True).ask())
    app_secret = _prompt_value_or_exit(TextPrompt("Secret Key", password=True).ask())
    owner = _prompt_value_or_exit(TextPrompt("Owner").ask())
    expires_at = _prompt_value_or_exit(TextPrompt("Expires at").ask())
    description = _prompt_value_or_exit(TextPrompt("Description (optional)").ask())

    return ProfileCredentials(
        profile_name=profile_name or "",
        environment=environment or "",
        account_no=account_no or "",
        app_key=app_key or "",
        app_secret=app_secret or "",
        owner=owner or "",
        expires_at=expires_at or "",
        description=description or "",
    )


def _prompt_profile_update(current: ResolvedProfile) -> ProfileCredentials:
    environment_choices = [current.environment]
    environment_choices.extend(
        environment for environment in ("real", "mock") if environment != current.environment
    )
    environment = _prompt_value_or_exit(
        SelectPrompt(
            "Environment",
            choices=[(value, value) for value in environment_choices],
        ).ask()
    )
    account_no = _prompt_value_or_exit(
        TextPrompt(f"Account number (blank keeps {mask_account(current.account_no)})").ask()
    )
    app_key = _prompt_value_or_exit(
        TextPrompt("APP key (blank keeps current)", password=True).ask()
    )
    app_secret = _prompt_value_or_exit(
        TextPrompt("Secret Key (blank keeps current)", password=True).ask()
    )
    owner = _prompt_value_or_exit(TextPrompt(f"Owner (blank keeps {current.owner})").ask())
    expires_at = _prompt_value_or_exit(
        TextPrompt(f"Expires at (blank keeps {current.expires_at})").ask()
    )
    description = _prompt_value_or_exit(
        TextPrompt("Description (optional, blank clears)").ask()
    )

    return ProfileCredentials(
        profile_name=current.name,
        environment=environment or current.environment,
        account_no=account_no or current.account_no,
        app_key=app_key or current.app_key,
        app_secret=app_secret or current.app_secret,
        owner=owner or current.owner,
        expires_at=expires_at or current.expires_at,
        description=description or "",
        profile_id=current.profile_id,
    )


def _prompt_existing_profile(path: Path | None) -> str:
    config_path = path.expanduser() if path is not None else default_config_file()
    try:
        _, profiles = read_config(config_path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not profiles:
        raise typer.BadParameter("no profiles found")
    return _prompt_value_or_exit(
        SelectPrompt(
            "Profile",
            choices=[(name, name) for name in profiles],
        ).ask()
    )


def _prompt_value_or_exit[T](value: T | None) -> T:
    if value is None:
        raise typer.Exit(CANCEL_EXIT_CODE)
    return value


def _print_config_init_result(result: ConfigInitResult) -> None:
    action = "updated" if result.overwritten else "created"
    table = _result_table()
    table.add_row("Config", str(result.path))
    table.add_row("Action", action)
    table.add_row("Active profile", result.profile)
    table.add_row("Environment", result.environment)
    table.add_row("Secrets", "environment variable references only")
    console.print(
        Panel(
            table,
            title="Config initialized",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_profile_add_result(result: ProfileAddResult, *, title: str = "Profile saved") -> None:
    action = "updated" if result.updated_existing_config else "created"
    table = _result_table()
    table.add_row("Profile", result.profile_name)
    table.add_row("Action", action)
    table.add_row("Profile id", result.profile_id)
    table.add_row("Environment", result.environment)
    table.add_row("Config", str(result.config_path))
    table.add_row("Environment file", str(result.env_path))
    table.add_row("Secrets", "stored outside config.yaml")
    console.print(
        Panel(
            table,
            title=title,
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_profile_delete_result(result: ProfileDeleteResult) -> None:
    table = _result_table()
    table.add_row("Profile", result.profile_name)
    table.add_row("Profile id", result.profile_id or "-")
    table.add_row("Config", str(result.config_path))
    table.add_row("Environment file", str(result.env_path))
    table.add_row("Active profile", result.active_profile or "-")
    table.add_row("Secrets", "removed for deleted profile")
    console.print(
        Panel(
            table,
            title="Profile deleted",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )


def _print_validate_result(profile: ResolvedProfile) -> None:
    table = _result_table()
    table.add_row("Status", "[green]valid[/green]")
    table.add_row("Config", str(profile.config_path))
    table.add_row("Profile", profile.name)
    table.add_row("Profile id", profile.profile_id)
    table.add_row("Environment", profile.environment)
    table.add_row("Expires at", profile.expires_at)
    table.add_row("Owner", profile.owner)
    table.add_row("Account", mask_account(profile.account_no))
    table.add_row("APP key", mask_secret(profile.app_key))
    table.add_row("Secret key", mask_secret(profile.app_secret, visible=0))
    console.print(
        Panel(
            table,
            title="Config validation",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_auth_test_result(result: AuthTestResult) -> None:
    table = _result_table()
    table.add_row("Status", "[green]passed[/green]")
    table.add_row("Profile", result.profile_name)
    table.add_row("Profile id", result.profile_id)
    table.add_row("Environment", result.environment)
    table.add_row("Token", result.token_status)
    table.add_row("Expires at", result.expires_at)
    table.add_row("Cache", str(result.cache_path))
    table.add_row("Secrets", "not printed")
    console.print(
        Panel(
            table,
            title="Auth test",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_auth_status_result(results: list[AuthStatusResult]) -> None:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Profile", style="bold cyan")
    table.add_column("Environment")
    table.add_column("Token")
    table.add_column("Expires at")
    table.add_column("Expires in")
    table.add_column("Cache")
    for result in results:
        table.add_row(
            result.profile_name,
            result.environment,
            result.token_status,
            result.expires_at,
            result.expires_in,
            str(result.cache_path),
        )
    console.print(
        Panel(
            table,
            title="Auth status",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_auth_clear_result(results: list[AuthClearResult]) -> None:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Profile", style="bold cyan")
    table.add_column("Environment")
    table.add_column("Removed")
    table.add_column("Cache")
    for result in results:
        table.add_row(
            result.profile_name,
            result.environment,
            "yes" if result.removed else "no",
            str(result.cache_path),
        )
    console.print(
        Panel(
            table,
            title="Auth cache cleared",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )


def _print_database_init_result(result: DatabaseInitResult) -> None:
    table = _result_table()
    table.add_row("App database", str(result.app_path))
    table.add_row("Warehouse", str(result.warehouse_path))
    table.add_row("Tables", ", ".join(result.tables))
    console.print(
        Panel(
            table,
            title="Database initialized",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_database_schema_result(result: DatabaseSchemaResult) -> None:
    summary = _result_table()
    summary.add_row("Database", str(result.path))
    summary.add_row("Tables", str(len(result.tables)))
    console.print(
        Panel(
            summary,
            title="Database schema",
            border_style="green",
            box=box.ROUNDED,
        )
    )

    for db_table in result.tables:
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("Column", style="bold cyan")
        table.add_column("Type")
        table.add_column("Required")
        table.add_column("Primary key")
        table.add_column("Default")
        for column in db_table.columns:
            table.add_row(
                column.name,
                column.type or "-",
                "yes" if column.not_null else "no",
                "yes" if column.primary_key else "no",
                column.default or "",
            )
        console.print(Panel(table, title=f"Table: {db_table.name}", box=box.ROUNDED))

        if db_table.indexes:
            index_table = Table(box=box.SIMPLE)
            index_table.add_column("Index", style="bold cyan")
            index_table.add_column("Unique")
            index_table.add_column("Origin")
            index_table.add_column("Columns")
            for index in db_table.indexes:
                index_table.add_row(
                    index.name,
                    "yes" if index.unique else "no",
                    index.origin,
                    ", ".join(index.columns),
                )
            console.print(index_table)


def _print_database_counts_result(result: DatabaseCountsResult) -> None:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Table", style="bold cyan")
    table.add_column("Rows", justify="right")
    for count in result.tables:
        table.add_row(count.name, str(count.rows))
    table.add_section()
    table.add_row("Total", str(result.total_rows))
    console.print(
        Panel(
            table,
            title=f"Database counts: {result.path}",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_ingest_runs(rows, app_db_path: Path) -> None:
    summary = _result_table()
    summary.add_row("App database", str(app_db_path))
    summary.add_row("Rows", str(len(rows)))
    console.print(Panel(summary, title="Ingest runs", border_style="green", box=box.ROUNDED))

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("ID", justify="right")
    table.add_column("Kind", style="bold cyan", no_wrap=True)
    table.add_column("Market")
    table.add_column("Symbol")
    table.add_column("Status")
    table.add_column("Rows", justify="right")
    table.add_column("Started at")
    table.add_column("Finished at")
    table.add_column("Error")
    for row in rows:
        table.add_row(
            str(row.id),
            row.kind,
            row.market or "",
            row.symbol or "",
            row.status,
            str(row.rows_written),
            row.started_at,
            row.finished_at or "",
            row.error or "",
        )
    console.print(table)


def _print_api_logs(rows, app_db_path: Path) -> None:
    summary = _result_table()
    summary.add_row("App database", str(app_db_path))
    summary.add_row("Rows", str(len(rows)))
    console.print(Panel(summary, title="API logs", border_style="green", box=box.ROUNDED))

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Endpoint", style="bold cyan", no_wrap=True)
    table.add_column("TR ID", no_wrap=True)
    table.add_column("Status", justify="right")
    table.add_column("Requested at")
    table.add_column("Elapsed ms", justify="right")
    table.add_column("Error")
    for row in rows:
        table.add_row(
            str(row["endpoint"]),
            str(row["tr_id"] or ""),
            "" if row["status_code"] is None else str(row["status_code"]),
            str(row["requested_at"]),
            "" if row["elapsed_ms"] is None else str(row["elapsed_ms"]),
            str(row["error"] or ""),
        )
    console.print(table)


def _print_symbols_download_result(results: list) -> None:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Market", style="bold cyan")
    table.add_column("Downloaded", justify="right")
    table.add_column("Stored", justify="right")
    table.add_column("Database")
    for result in results:
        table.add_row(
            result.market,
            str(result.downloaded),
            str(result.stored),
            str(result.db_path),
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


def _print_current_price_result(result: CurrentPrice) -> None:
    table = _result_table()
    table.add_row("Market", result.market)
    table.add_row("Symbol", result.symbol)
    table.add_row("Name", result.name or "-")
    table.add_row("Price", _format_decimal(result.price))
    table.add_row("Currency", result.currency or "-")
    table.add_row("Change", _format_decimal(result.change))
    table.add_row("Change rate", _format_decimal(result.change_rate))
    table.add_row("Open", _format_decimal(result.open))
    table.add_row("High", _format_decimal(result.high))
    table.add_row("Low", _format_decimal(result.low))
    table.add_row("Volume", str(result.volume) if result.volume is not None else "-")
    console.print(
        Panel(
            table,
            title="Current price",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_chart_history_result(result: ChartHistoryResult) -> None:
    table = _result_table()
    table.add_row("Market", result.market)
    table.add_row("Symbol", result.symbol)
    table.add_row("Interval", result.interval)
    table.add_row("Fetched", str(result.fetched))
    table.add_row("Stored", str(result.stored))
    table.add_row("Database", str(result.db_path) if result.db_path else "-")
    if result.bars:
        table.add_row("First", result.bars[0].timestamp)
        table.add_row("Last", result.bars[-1].timestamp)
    console.print(
        Panel(
            table,
            title="OHLCV history",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_ohlcv_query_result(result: OhlcvQueryResult, *, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(result.rows, ensure_ascii=False, indent=2))
        return
    if output_format == "csv":
        _write_ohlcv_csv(result.rows, sys.stdout)
        return

    if not result.rows:
        console.print("No OHLCV bars found")
        return

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Market", style="bold cyan")
    table.add_column("Symbol", style="bold")
    table.add_column("Date")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")
    for row in result.rows:
        table.add_row(
            str(row["market"]),
            str(row["symbol"]),
            str(row["timestamp"]),
            str(row["open"]),
            str(row["high"]),
            str(row["low"]),
            str(row["close"]),
            str(row["volume"]),
        )
    console.print(table)


def _print_export_result(*, export_path: Path, row_count: int, export_format: str) -> None:
    table = _result_table()
    table.add_row("Path", str(export_path.expanduser()))
    table.add_row("Format", export_format)
    table.add_row("Rows", str(row_count))
    console.print(
        Panel(
            table,
            title="OHLCV exported",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _normalize_output_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"table", "json", "csv"}:
        raise typer.BadParameter("format must be one of: table, json, csv")
    return normalized


def _export_format(path: Path, *, fallback: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if fallback in {"csv", "json"}:
        return fallback
    raise typer.BadParameter("export path must end with .csv or .json, or pass --format csv|json")


def _export_ohlcv_rows(rows: list[dict[str, object]], path: Path, export_format: str) -> None:
    export_path = path.expanduser()
    export_path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "json":
        export_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    with export_path.open("w", encoding="utf-8", newline="") as file:
        _write_ohlcv_csv(rows, file)


def _write_ohlcv_csv(rows, file) -> None:
    fieldnames = ["market", "symbol", "interval", "timestamp", "open", "high", "low", "close", "volume"]
    writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def _format_decimal(value) -> str:
    if value is None:
        return "-"
    return format(value, "f")


def _result_table() -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    return table


def main() -> None:
    app()
