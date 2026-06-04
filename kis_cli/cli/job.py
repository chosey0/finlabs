"""``python -m kis_cli job`` — a thin HTTP client for the job server.

The CLI is just another client of the job API (the same one the dashboard uses).
It loads no KIS credentials; it only talks HTTP to the localhost server.
"""

from __future__ import annotations

from typing import Annotated

import httpx
import typer
from rich import box
from rich.table import Table

from kis_cli.cli.common import console
from kis_cli.server.config import base_url

job_app = typer.Typer(help="Submit and inspect collection jobs on the job server.", no_args_is_help=True)


def _client() -> httpx.Client:
    return httpx.Client(base_url=base_url(), timeout=10.0)


def _fail(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _render_job(job: dict) -> None:
    table = Table(box=box.SIMPLE)
    table.add_column("field", style="cyan")
    table.add_column("value")
    for key in ("id", "symbol", "interval", "status", "market", "result", "error"):
        value = job.get(key)
        if value is not None:
            table.add_row(key, str(value))
    console.print(table)


@job_app.command("submit")
def submit(
    symbol: Annotated[str, typer.Option("--symbol", help="Ticker symbol, e.g. NVDA.")],
    start: Annotated[str, typer.Option("--start", help="Start date YYYY-MM-DD or minute start.")],
    interval: Annotated[str, typer.Option("--interval", help="1d/1w/1mo or 1m/5m.")] = "1d",
    end: Annotated[str | None, typer.Option("--end", help="End date for daily history.")] = None,
    count: Annotated[int, typer.Option("--count", min=1, help="Bars for minute collection.")] = 120,
) -> None:
    payload = {"symbol": symbol, "start": start, "interval": interval, "end": end, "count": count}
    try:
        with _client() as client:
            response = client.post("/jobs", json=payload)
    except httpx.HTTPError as exc:
        _fail(f"could not reach job server at {base_url()}: {exc}")
    if response.status_code >= 400:
        _fail(f"server returned {response.status_code}: {response.text}")
    _render_job(response.json())


@job_app.command("status")
def status(job_id: Annotated[str, typer.Argument(help="Job id returned by submit.")]) -> None:
    try:
        with _client() as client:
            response = client.get(f"/jobs/{job_id}")
    except httpx.HTTPError as exc:
        _fail(f"could not reach job server at {base_url()}: {exc}")
    if response.status_code == 404:
        _fail(f"job '{job_id}' not found")
    if response.status_code >= 400:
        _fail(f"server returned {response.status_code}: {response.text}")
    _render_job(response.json())


@job_app.command("list")
def list_jobs() -> None:
    try:
        with _client() as client:
            response = client.get("/jobs")
    except httpx.HTTPError as exc:
        _fail(f"could not reach job server at {base_url()}: {exc}")
    if response.status_code >= 400:
        _fail(f"server returned {response.status_code}: {response.text}")
    jobs = response.json()
    if not jobs:
        console.print("[dim]no jobs[/dim]")
        return
    table = Table(box=box.SIMPLE)
    for column in ("id", "symbol", "interval", "status", "market"):
        table.add_column(column)
    for job in jobs:
        table.add_row(
            job.get("id", ""),
            job.get("symbol", ""),
            job.get("interval", ""),
            job.get("status", ""),
            str(job.get("market") or ""),
        )
    console.print(table)
