from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from kis_cli.cli.common import console, result_table
from kis_cli.core.auth import KisAuthError
from kis_cli.services.auth import (
    AuthClearResult,
    AuthStatusResult,
    AuthTestResult,
    clear_auth_tokens,
    get_auth_statuses,
    test_auth,
)

auth_app = typer.Typer(help="Authenticate with the KIS Open API.", no_args_is_help=True)


@auth_app.command("test")
def auth_test(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name to authenticate. Defaults to active_profile."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path instead of the platform config directory."),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Ignore a valid cached token and request a new one."),
    ] = False,
) -> None:
    """Issue or reuse a REST access token without printing secrets."""
    try:
        with console.status("Checking KIS authentication..."):
            result = test_auth(profile=profile, config_path=path, refresh=refresh)
    except (FileNotFoundError, ValueError, KisAuthError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_auth_test_result(result)


@auth_app.command("status")
def auth_status(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name to inspect. Defaults to active_profile."),
    ] = None,
    all_profiles: Annotated[
        bool,
        typer.Option("--all", help="Inspect token status for every configured profile."),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path instead of the platform config directory."),
    ] = None,
) -> None:
    """Show cached REST token status without contacting KIS."""
    try:
        with console.status("Reading auth token cache..."):
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
        typer.Option("--profile", help="Profile name to clear. Defaults to active_profile."),
    ] = None,
    all_profiles: Annotated[
        bool,
        typer.Option("--all", help="Clear cached tokens for every configured profile."),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path instead of the platform config directory."),
    ] = None,
) -> None:
    """Remove cached REST tokens without contacting KIS."""
    try:
        with console.status("Clearing auth token cache..."):
            results = clear_auth_tokens(
                profile=profile,
                all_profiles=all_profiles,
                config_path=path,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_auth_clear_result(results)


def _print_auth_test_result(result: AuthTestResult) -> None:
    table = result_table()
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
    console.print(Panel(table, title="Auth status", border_style="green", box=box.ROUNDED))


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
    console.print(Panel(table, title="Auth cache cleared", border_style="yellow", box=box.ROUNDED))
