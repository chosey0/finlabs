from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel

from kis_cli.cli.common import console, format_decimal, result_table
from kis_cli.core.auth import KisAuthError
from kis_cli.core.client import KisApiError
from kis_cli.core.price import CurrentPrice
from kis_cli.services.price import get_current_price

price_app = typer.Typer(help="Query REST price data.", no_args_is_help=True)


@price_app.command("current")
def price_current(
    symbol: Annotated[str, typer.Option("--symbol", help="Symbol code, for example AAPL.")],
    market: Annotated[str, typer.Option("--market", help="Market, for example NASDAQ or KOSPI.")],
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name. Defaults to active_profile."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Config file path. Defaults to the platform config path."),
    ] = None,
) -> None:
    """Query the current REST quote for one stock."""
    try:
        with console.status("Querying current price..."):
            result = get_current_price(
                symbol=symbol,
                market=market,
                profile=profile,
                config_path=path,
            )
    except (FileNotFoundError, ValueError, KisAuthError, KisApiError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_current_price_result(result)


def _print_current_price_result(result: CurrentPrice) -> None:
    table = result_table()
    table.add_row("Market", result.market)
    table.add_row("Symbol", result.symbol)
    table.add_row("Name", result.name or "-")
    table.add_row("Price", format_decimal(result.price))
    table.add_row("Currency", result.currency or "-")
    table.add_row("Change", format_decimal(result.change))
    table.add_row("Change rate", format_decimal(result.change_rate))
    table.add_row("Open", format_decimal(result.open))
    table.add_row("High", format_decimal(result.high))
    table.add_row("Low", format_decimal(result.low))
    table.add_row("Volume", str(result.volume) if result.volume is not None else "-")
    console.print(
        Panel(
            table,
            title="Current price",
            border_style="green",
            box=box.ROUNDED,
        )
    )
