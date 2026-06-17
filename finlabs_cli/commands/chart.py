from __future__ import annotations

import asyncio
from datetime import date

import typer

from finlabs_cli.app.account_store import AccountStore
from finlabs_cli.app.chart_runner import fetch_domestic_chart, fetch_overseas_chart
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.ui.console import console
from finlabs_cli.ui.prompts import choose, text
from finlabs_cli.ui.tables import chart_table

chart_app = typer.Typer(help="Fetch chart data through broker SDKs.")


@chart_app.command("domestic")
def domestic(
    alias: str | None = typer.Option(None, "--alias"),
    symbol: str | None = typer.Option(None, "--symbol"),
    interval: str | None = typer.Option(None, "--interval"),
    base_date: str | None = typer.Option(None, "--base-date"),
) -> None:
    account = _account(alias, broker="kiwoom")
    selected_symbol = symbol or text("Ticker / company", default="005930")
    selected_interval = interval or choose(
        "Interval",
        choices=[
            ("Tick ka10079", "tick"),
            ("Minute ka10080", "minute"),
            ("Daily ka10081", "daily"),
            ("Weekly ka10082", "weekly"),
            ("Monthly ka10083", "monthly"),
            ("Yearly ka10094", "yearly"),
        ],
    )
    selected_base_date = base_date
    if selected_interval != "tick" and not selected_base_date:
        selected_base_date = text("Base date", default=date.today().isoformat())
    bars = asyncio.run(
        fetch_domestic_chart(
            account,
            JsonTokenStore.default(),
            symbol=selected_symbol,
            interval=selected_interval,
            base_date=selected_base_date,
        )
    )
    console.print(chart_table(bars))


@chart_app.command("overseas")
def overseas(
    alias: str | None = typer.Option(None, "--alias"),
    symbol: str | None = typer.Option(None, "--symbol"),
    exchange: str | None = typer.Option(None, "--exchange"),
    interval: str | None = typer.Option(None, "--interval"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
) -> None:
    account = _account(alias, broker="kis")
    selected_symbol = symbol or text("Ticker / company", default="AAPL")
    selected_exchange = exchange or text("Exchange", default="NAS")
    selected_interval = interval or choose(
        "Interval",
        choices=[
            ("Minute HHDFS76950200", "minute"),
            ("Daily HHDFS76240000", "daily"),
            ("Weekly HHDFS76240000", "weekly"),
            ("Monthly HHDFS76240000", "monthly"),
        ],
    )
    selected_start = start or text("Start", default=date.today().isoformat())
    selected_end = end or text("End", default=date.today().isoformat())
    bars = asyncio.run(
        fetch_overseas_chart(
            account,
            JsonTokenStore.default(),
            symbol=selected_symbol,
            exchange=selected_exchange,
            interval=selected_interval,
            start=selected_start,
            end=selected_end,
        )
    )
    console.print(chart_table(bars))


def _account(alias: str | None, *, broker: str):
    store = AccountStore.default()
    candidates = [account for account in store.list() if account.broker == broker]
    if not candidates:
        raise typer.BadParameter(f"no {broker} accounts registered")
    selected = alias or choose(
        "Account",
        choices=[(account.alias, account.alias) for account in candidates],
    )
    account = store.require(selected)
    if account.broker != broker:
        raise typer.BadParameter(f"account '{selected}' is not a {broker} account")
    return account
