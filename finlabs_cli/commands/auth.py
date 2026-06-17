from __future__ import annotations

import asyncio

import typer

from finlabs_cli.app.account_store import AccountStore
from finlabs_cli.app.broker_registry import build_client, revoke_token
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.ui.console import console
from finlabs_cli.ui.prompts import choose
from finlabs_cli.ui.tables import auth_status_table, account_summary

auth_app = typer.Typer(help="Refresh, revoke, and inspect broker tokens.")


@auth_app.command("status")
def status() -> None:
    store = AccountStore.default()
    token_store = JsonTokenStore.default()
    console.print(auth_status_table(store.list(), token_store))


@auth_app.command("refresh")
def refresh(alias: str | None = typer.Option(None, "--alias")) -> None:
    account = _selected_account(alias)
    token_store = JsonTokenStore.default()
    asyncio.run(_refresh(account.alias, token_store))


@auth_app.command("revoke")
def revoke(alias: str | None = typer.Option(None, "--alias")) -> None:
    account = _selected_account(alias)
    token_store = JsonTokenStore.default()
    result = asyncio.run(revoke_token(account, token_store))
    console.print(result)
    console.print(account_summary(account, title="Account"))


def _selected_account(alias: str | None):
    store = AccountStore.default()
    accounts = store.list()
    if not accounts:
        raise typer.BadParameter("no accounts registered")
    selected = alias or choose(
        "Account",
        choices=[(account.alias, account.alias) for account in accounts],
    )
    return store.require(selected)


async def _refresh(alias: str, token_store: JsonTokenStore) -> None:
    account = AccountStore.default().require(alias)
    async with build_client(account, token_store) as client:
        token = await client.ensure_token()
    console.print(f"[green]Token refreshed[/green] {account.alias}: {token[:6]}...")
    console.print(account_summary(account, title="Account"))
