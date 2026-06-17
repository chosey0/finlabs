from __future__ import annotations

import typer

from finlabs_cli.app.account_store import AccountStore
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.ui.console import console
from finlabs_cli.ui.realtime_tui import RealtimeMonitorApp

realtime_app = typer.Typer(help="Run interactive realtime WebSocket sessions.")


@realtime_app.command("run")
def run(alias: str | None = typer.Option(None, "--alias")) -> None:
    accounts = _realtime_accounts()
    if alias is not None and alias not in {account.alias for account in accounts}:
        raise typer.BadParameter(f"unknown realtime-capable account: {alias}")
    RealtimeMonitorApp(
        accounts,
        JsonTokenStore.default(),
        selected_alias=alias,
    ).run()


@realtime_app.command("monitor")
def monitor() -> None:
    console.print(
        "[yellow]Realtime monitor requires the interactive run process in this MVP.[/yellow]"
    )
    console.print("Run [bold]python -m finlabs_cli realtime run[/bold].")


def _realtime_accounts():
    store = AccountStore.default()
    accounts = [
        account for account in store.list() if account.broker in {"kis", "kiwoom"}
    ]
    if not accounts:
        raise typer.BadParameter("no realtime-capable accounts registered")
    return accounts
