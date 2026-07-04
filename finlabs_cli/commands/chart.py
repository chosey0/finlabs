from __future__ import annotations

import asyncio
from datetime import date
from time import perf_counter
from typing import Iterable

import typer
from rich.progress import BarColumn, Progress, ProgressColumn, SpinnerColumn, Task
from rich.table import Table
from rich.text import Text

from brokers.kis import KisApiError
from brokers.kiwoom import KiwoomApiError

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
    start_date: str | None = typer.Option(None, "--start-date"),
    tic_scope: int | None = typer.Option(
        None,
        "--tic-scope",
        min=1,
        help="Kiwoom minute chart tic_scope. Numbers only.",
    ),
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
    selected_tic_scope = tic_scope
    if selected_interval == "minute" and selected_tic_scope is None:
        selected_tic_scope = _number_prompt("tic_scope", default=1)
    selected_base_date = base_date
    if selected_interval != "tick" and not selected_base_date:
        selected_base_date = text("Base date", default=date.today().isoformat())
    selected_start_date = start_date or text(
        "Start date",
        default=_domestic_start_default(selected_interval),
    )
    try:
        bars, elapsed_seconds = _run_with_progress(
            ticker=selected_symbol,
            market="KRX",
            service=f"domestic.{selected_interval}",
            coroutine=fetch_domestic_chart(
                account,
                JsonTokenStore.default(),
                symbol=selected_symbol,
                interval=selected_interval,
                base_date=selected_base_date,
                start_date=selected_start_date,
                tic_scope=selected_tic_scope,
            ),
        )
    except (KiwoomApiError, KisApiError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_chart(bars, elapsed_seconds=elapsed_seconds)


@chart_app.command("overseas")
def overseas(
    alias: str | None = typer.Option(None, "--alias"),
    symbol: str | None = typer.Option(None, "--symbol"),
    exchange: str | None = typer.Option(None, "--exchange"),
    interval: str | None = typer.Option(None, "--interval"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    max_pages: int = typer.Option(
        100,
        "--max-pages",
        min=1,
        max=1000,
        help="Maximum continuation requests for daily/weekly/monthly charts.",
    ),
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
    try:
        bars, elapsed_seconds = _run_with_progress(
            ticker=selected_symbol,
            market=selected_exchange,
            service=f"overseas.{selected_interval}",
            coroutine=fetch_overseas_chart(
                account,
                JsonTokenStore.default(),
                symbol=selected_symbol,
                exchange=selected_exchange,
                interval=selected_interval,
                start=selected_start,
                end=selected_end,
                max_pages=max_pages,
            ),
        )
    except (KiwoomApiError, KisApiError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_chart(bars, elapsed_seconds=elapsed_seconds)


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


def _domestic_start_default(interval: str) -> str:
    today = date.today()
    if interval in {"tick", "minute"}:
        return f"{today.isoformat()} 090000"
    if interval in {"daily", "weekly"}:
        return today.isoformat()
    if interval == "monthly":
        return today.strftime("%Y-%m")
    if interval == "yearly":
        return today.strftime("%Y")
    return today.isoformat()


def _number_prompt(prompt: str, *, default: int) -> int:
    while True:
        value = text(prompt, default=str(default)).strip()
        if value.isdigit():
            return int(value)
        console.print("[red]숫자만 입력하세요.[/red]")


def _run_with_progress(*, ticker: str, market: str, service: str, coroutine):
    started_at = perf_counter()
    progress = Progress(
        SpinnerColumn(),
        "[bold cyan]ticker[/bold cyan]",
        "{task.fields[ticker]}",
        "[bold magenta]market[/bold magenta]",
        "{task.fields[market]}",
        "[bold green]{task.fields[service]}[/bold green]",
        "|",
        _ElapsedSecondsColumn(),
        BarColumn(),
        console=console,
    )
    with progress:
        task_id = progress.add_task(
            "Fetching chart",
            total=None,
            ticker=ticker.strip().upper(),
            market=market.strip().upper(),
            service=service.strip().lower(),
        )
        bars = asyncio.run(coroutine)
        progress.update(task_id, total=1, completed=1)
    return bars, perf_counter() - started_at


class _ElapsedSecondsColumn(ProgressColumn):
    def render(self, task: Task) -> Text:
        elapsed = task.elapsed or 0.0
        return Text(f"{elapsed:.2f}s")


def _print_chart(bars: Iterable, *, elapsed_seconds: float) -> None:
    bars = list(bars)
    if not bars:
        console.print(
            "[yellow]No chart data returned. Check symbol, exchange, interval, and date range.[/yellow]"
        )
    console.print(_chart_result_table(bars, elapsed_seconds=elapsed_seconds))
    console.print(chart_table(bars))


def _chart_result_table(bars: list, *, elapsed_seconds: float) -> Table:
    table = Table(title="Chart Result")
    table.add_column("Range")
    table.add_column("Count", justify="right")
    table.add_column("Elapsed", justify="right")
    table.add_row(*_chart_result_row(bars, elapsed_seconds=elapsed_seconds))
    return table


def _chart_result_row(bars: list, *, elapsed_seconds: float) -> tuple[str, str, str]:
    return _chart_range(bars), str(len(bars)), f"{elapsed_seconds:.2f}s"


def _chart_range(bars: list) -> str:
    timestamps = [_chart_timestamp(bar) for bar in bars]
    timestamps = [value for value in timestamps if value]
    if not timestamps:
        return "-"
    timestamps = sorted(timestamps)
    return f"{timestamps[0]} - {timestamps[-1]}"


def _chart_timestamp(bar) -> str:
    timestamp = getattr(bar, "timestamp", None)
    if timestamp:
        return str(timestamp)
    local_date = str(getattr(bar, "local_date", "") or "")
    local_time = str(getattr(bar, "local_time", "") or "")
    return f"{local_date} {local_time}".strip()
