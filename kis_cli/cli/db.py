from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from kis_cli.cli.common import console, result_table
from kis_cli.storage import (
    DatabaseCountsResult,
    DatabaseInitResult,
    DatabaseSchemaResult,
    init_database,
    inspect_database_counts,
    inspect_database_schema,
)

db_app = typer.Typer(help="Manage kis-cli local storage.", no_args_is_help=True)


@db_app.command("init")
def db_init(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Create or update a DuckDB warehouse at a custom path."),
    ] = None,
) -> None:
    """Create the local app database and DuckDB warehouse schemas."""
    with console.status("Initializing local storage..."):
        result = init_database(path)
    _print_database_init_result(result)


@db_app.command("schema")
def db_schema(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Inspect a DuckDB warehouse at a custom path."),
    ] = None,
) -> None:
    """Inspect local warehouse tables, columns, and indexes."""
    try:
        with console.status("Inspecting warehouse schema..."):
            result = inspect_database_schema(path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_database_schema_result(result)


@db_app.command("counts")
def db_counts(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Inspect row counts in a DuckDB warehouse at a custom path."),
    ] = None,
) -> None:
    """Show row counts for each local warehouse table."""
    try:
        with console.status("Counting warehouse rows..."):
            result = inspect_database_counts(path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_database_counts_result(result)


def _print_database_init_result(result: DatabaseInitResult) -> None:
    table = result_table()
    table.add_row("App database", str(result.app_path))
    table.add_row("Warehouse", str(result.warehouse_path))
    table.add_row("Tables", ", ".join(result.tables))
    console.print(
        Panel(
            table,
            title="Database initialized",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _print_database_schema_result(result: DatabaseSchemaResult) -> None:
    summary = result_table()
    summary.add_row("Database", str(result.path))
    summary.add_row("Tables", str(len(result.tables)))
    console.print(Panel(summary, title="Database schema", border_style="green", box=box.ROUNDED))

    for table_schema in result.tables:
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("Column", style="bold cyan")
        table.add_column("Type")
        table.add_column("Required")
        table.add_column("Primary key")
        table.add_column("Default")
        for column in table_schema.columns:
            table.add_row(
                column.name,
                column.type or "-",
                "yes" if column.not_null else "no",
                "yes" if column.primary_key else "no",
                column.default or "",
            )
        console.print(Panel(table, title=f"Table: {table_schema.name}", box=box.ROUNDED))

        if table_schema.indexes:
            indexes = Table(box=box.SIMPLE_HEAVY)
            indexes.add_column("Index", style="bold cyan")
            indexes.add_column("Unique")
            indexes.add_column("Origin")
            indexes.add_column("Columns")
            for index in table_schema.indexes:
                indexes.add_row(
                    index.name,
                    "yes" if index.unique else "no",
                    index.origin,
                    ", ".join(index.columns),
                )
            console.print(indexes)


def _print_database_counts_result(result: DatabaseCountsResult) -> None:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Table", style="bold cyan")
    table.add_column("Rows", justify="right")
    for count in result.tables:
        table.add_row(count.name, str(count.rows))
    table.add_section()
    table.add_row("Total", str(result.total_rows))
    console.print(
        Panel(
            table,
            title=f"Database counts: {result.path}",
            border_style="green",
            box=box.ROUNDED,
        )
    )
