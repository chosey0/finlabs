from __future__ import annotations

import typer

from kis_cli.cli.auth import auth_app
from kis_cli.cli.chart import chart_app
from kis_cli.cli.common import CANCEL_EXIT_CODE
from kis_cli.cli.config import _prompt_value_or_exit, config_app
from kis_cli.cli.db import db_app
from kis_cli.cli.logs import logs_app
from kis_cli.cli.price import price_app
from kis_cli.cli.query import query_app
from kis_cli.cli.symbols import symbols_app

app = typer.Typer(
    help="Collect domestic and overseas stock data with the KIS Open API.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")
app.add_typer(auth_app, name="auth")
app.add_typer(db_app, name="db")
app.add_typer(symbols_app, name="symbols")
app.add_typer(price_app, name="price")
app.add_typer(chart_app, name="chart")
app.add_typer(query_app, name="query")
app.add_typer(logs_app, name="logs")

__all__ = ["CANCEL_EXIT_CODE", "_prompt_value_or_exit", "app", "main"]


def main() -> None:
    app()
