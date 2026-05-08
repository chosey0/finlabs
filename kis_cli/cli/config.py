from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich_inquirer import ConfirmPrompt, SelectPrompt, TextPrompt

from kis_cli.cli.common import CANCEL_EXIT_CODE, console, result_table
from kis_cli.config.init import ConfigInitResult, init_config
from kis_cli.config.paths import default_config_file
from kis_cli.config.profiles import (
    ProfileAddResult,
    ProfileCredentials,
    ProfileDeleteResult,
    add_profile,
    delete_profile,
    update_profile,
)
from kis_cli.config.resolver import ResolvedProfile, mask_account, mask_secret, read_config
from kis_cli.config.resolver import resolve_profile

config_app = typer.Typer(help="Manage kis-cli configuration.", no_args_is_help=True)


@config_app.command("init")
def config_init(
    profile: Annotated[
        str,
        typer.Option("--profile", help="Profile name to create and activate."),
    ] = "real",
    environment: Annotated[
        str | None,
        typer.Option("--environment", help="KIS API environment. Defaults to profile when profile is real or mock."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing config file."),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Write config to a custom path instead of the platform config directory."),
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
    except (FileExistsError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_config_init_result(result)


@config_app.command("add")
def config_add(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Write config to a custom path instead of the platform config directory."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing profile with the same name."),
    ] = False,
) -> None:
    """Add a profile using interactive prompts."""
    credentials = _prompt_profile_credentials()
    try:
        result = add_profile(credentials, config_path=path, force=force)
    except (FileExistsError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_profile_add_result(result)


@config_app.command("validate")
def config_validate(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name to validate. Defaults to active_profile."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path instead of the platform config directory."),
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
        typer.Option("--profile", help="Profile name to update. Prompts when omitted."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path instead of the platform config directory."),
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
        typer.Option("--profile", help="Profile name to delete. Prompts when omitted."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path instead of the platform config directory."),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Delete without confirmation."),
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
    description = _prompt_value_or_exit(TextPrompt("Description (optional, blank clears)").ask())

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
    table = result_table()
    table.add_row("Config", str(result.path))
    table.add_row("Action", action)
    table.add_row("Active profile", result.profile)
    table.add_row("Environment", result.environment)
    table.add_row("Secrets", "environment variable references only")
    console.print(Panel(table, title="Config initialized", border_style="green", box=box.ROUNDED))


def _print_profile_add_result(result: ProfileAddResult, *, title: str = "Profile saved") -> None:
    action = "updated" if result.updated_existing_config else "created"
    table = result_table()
    table.add_row("Profile", result.profile_name)
    table.add_row("Action", action)
    table.add_row("Profile id", result.profile_id)
    table.add_row("Environment", result.environment)
    table.add_row("Config", str(result.config_path))
    table.add_row("Environment file", str(result.env_path))
    table.add_row("Secrets", "stored outside config.yaml")
    console.print(Panel(table, title=title, border_style="green", box=box.ROUNDED))


def _print_profile_delete_result(result: ProfileDeleteResult) -> None:
    table = result_table()
    table.add_row("Profile", result.profile_name)
    table.add_row("Profile id", result.profile_id or "-")
    table.add_row("Config", str(result.config_path))
    table.add_row("Environment file", str(result.env_path))
    table.add_row("Active profile", result.active_profile or "-")
    table.add_row("Secrets", "removed for deleted profile")
    console.print(Panel(table, title="Profile deleted", border_style="yellow", box=box.ROUNDED))


def _print_validate_result(profile: ResolvedProfile) -> None:
    table = result_table()
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
    console.print(Panel(table, title="Config validation", border_style="green", box=box.ROUNDED))
