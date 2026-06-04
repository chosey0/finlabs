from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from kis_cli.cli import job as job_cli
from kis_cli.cli.job import job_app
from kis_cli.server.app import create_app
from kis_cli.server.jobs import JobQueue

runner = CliRunner()


class _Shim:
    """Context-manager shim so the CLI's ``with _client() as c`` reuses one client.

    A sync httpx.Client cannot drive an ASGI app, so we use Starlette's TestClient
    (which bridges async internally). The shim avoids re-running lifespan (which
    would stop the manually-started worker between CLI calls).
    """

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def __enter__(self) -> TestClient:
        return self._client

    def __exit__(self, *exc) -> bool:
        return False


@pytest.fixture
def wired_app(monkeypatch):
    queue = JobQueue(runner=lambda job: {"fetched": 1, "stored": 1, "market": "NASDAQ"})
    queue.start()
    client = TestClient(create_app(queue=queue))  # not entered -> no lifespan stop
    monkeypatch.setattr(job_cli, "_client", lambda: _Shim(client))
    try:
        yield queue
    finally:
        queue.stop()


def test_cli_submit_calls_server(wired_app) -> None:
    result = runner.invoke(job_app, ["submit", "--symbol", "NVDA", "--start", "2024-01-01"])
    assert result.exit_code == 0, result.output
    assert "NVDA" in result.output


def test_cli_status_reports_job(wired_app) -> None:
    submit = runner.invoke(job_app, ["submit", "--symbol", "TSLA", "--start", "2024-01-01"])
    assert submit.exit_code == 0, submit.output
    job_id = next(
        line.split()[-1] for line in submit.output.splitlines() if line.strip().startswith("id")
    )
    wired_app.join()

    status = runner.invoke(job_app, ["status", job_id])
    assert status.exit_code == 0, status.output
    assert "succeeded" in status.output


def test_cli_list_shows_jobs(wired_app) -> None:
    runner.invoke(job_app, ["submit", "--symbol", "AAA", "--start", "2024-01-01"])
    wired_app.join()
    result = runner.invoke(job_app, ["list"])
    assert result.exit_code == 0, result.output
    assert "AAA" in result.output


def test_cli_status_missing_job_exits_nonzero(wired_app) -> None:
    result = runner.invoke(job_app, ["status", "nope"])
    assert result.exit_code == 1
    assert "not found" in result.output
