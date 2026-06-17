from __future__ import annotations

import typer

from finlabs_cli.commands.accounts import accounts_app
from finlabs_cli.commands.auth import auth_app
from finlabs_cli.commands.chart import chart_app
from finlabs_cli.commands.realtime import realtime_app
from finlabs_cli.ui.console import console
from finlabs_cli.ui.prompts import choose

app = typer.Typer(
    help="FinLabs broker SDK CLI.",
    invoke_without_command=True,
)
app.add_typer(accounts_app, name="accounts")
app.add_typer(auth_app, name="auth")
app.add_typer(chart_app, name="chart")
app.add_typer(realtime_app, name="realtime")


@app.callback()
def root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    action = choose(
        "Select feature",
        choices=[
            ("Accounts", "accounts"),
            ("Auth", "auth"),
            ("Chart", "chart"),
            ("Realtime", "realtime"),
        ],
    )
    console.print(f"Run [bold]python -m finlabs_cli {action} --help[/bold]")


def main() -> None:
    app()
