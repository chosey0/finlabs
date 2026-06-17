from __future__ import annotations

import asyncio
from contextlib import suppress

import typer

from finlabs_cli.app.account_store import AccountStore
from finlabs_cli.app.realtime_manager import RealtimeManager
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.ui.console import console
from finlabs_cli.ui.prompts import choose, text
from finlabs_cli.ui.tables import subscriptions_table

realtime_app = typer.Typer(help="Run interactive realtime WebSocket sessions.")


@realtime_app.command("run")
def run(alias: str | None = typer.Option(None, "--alias")) -> None:
    account = _selected_account(alias)
    asyncio.run(_run_session(account.alias))


@realtime_app.command("monitor")
def monitor() -> None:
    console.print(
        "[yellow]Realtime monitor requires the interactive run process in this MVP.[/yellow]"
    )
    console.print("Run [bold]python -m finlabs_cli realtime run[/bold].")


async def _run_session(alias: str) -> None:
    account = AccountStore.default().require(alias)
    manager = RealtimeManager(account, JsonTokenStore.default())
    async with manager:
        stream_task = asyncio.create_task(_print_events(manager))
        try:
            while True:
                action = await asyncio.to_thread(
                    choose,
                    f"Realtime action ({account.alias})",
                    choices=[
                        ("Subscribe", "subscribe"),
                        ("Unsubscribe", "unsubscribe"),
                        ("Show subscriptions", "subscriptions"),
                        ("Disconnect", "disconnect"),
                    ],
                )
                if action == "disconnect":
                    await manager.unsubscribe_all()
                    break
                if action == "subscriptions":
                    console.print(subscriptions_table(manager.subscriptions()))
                    continue
                if action == "subscribe":
                    channel = await asyncio.to_thread(
                        choose,
                        "Channel",
                        choices=[("Trades", "trades"), ("Orderbook", "orderbook")],
                    )
                    symbol = await asyncio.to_thread(text, "Ticker", "")
                    venue = ""
                    if account.broker == "kis":
                        venue = await asyncio.to_thread(text, "Market/Exchange", "NAS")
                    await manager.subscribe(channel=channel, symbol=symbol, venue=venue)
                    console.print(subscriptions_table(manager.subscriptions()))
                if action == "unsubscribe":
                    subscriptions = manager.subscriptions()
                    if not subscriptions:
                        console.print("[yellow]No active subscriptions[/yellow]")
                        continue
                    selected = await asyncio.to_thread(
                        choose,
                        "Subscription",
                        choices=[
                            (
                                f"{item.channel} {item.market} {item.symbol}",
                                str(index),
                            )
                            for index, item in enumerate(subscriptions)
                        ],
                    )
                    await manager.unsubscribe(subscriptions[int(selected)])
                    console.print(subscriptions_table(manager.subscriptions()))
        finally:
            stream_task.cancel()
            with suppress(asyncio.CancelledError):
                await stream_task


async def _print_events(manager: RealtimeManager) -> None:
    async for event in manager.stream():
        console.print(event)


def _selected_account(alias: str | None):
    store = AccountStore.default()
    accounts = [
        account for account in store.list() if account.broker in {"kis", "kiwoom"}
    ]
    if not accounts:
        raise typer.BadParameter("no realtime-capable accounts registered")
    selected = alias or choose(
        "Account",
        choices=[(account.alias, account.alias) for account in accounts],
    )
    return store.require(selected)
