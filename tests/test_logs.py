from __future__ import annotations

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.storage.app_db import init_app_database
from kis_cli.storage.app_repositories import (
    finish_ingest_run,
    list_api_logs,
    list_ingest_runs,
    record_api_log,
    start_ingest_run,
)

runner = CliRunner()


def test_logs_runs_command_prints_recent_ingest_runs(tmp_path) -> None:
    app_db_path = tmp_path / "app.db"
    init_app_database(app_db_path)
    first_id = start_ingest_run(app_db_path, kind="symbols", market="KOSPI")
    finish_ingest_run(app_db_path, first_id, status="success", rows_written=10)
    second_id = start_ingest_run(
        app_db_path,
        kind="ohlcv:1d",
        market="NASDAQ",
        symbol="AAPL",
    )
    finish_ingest_run(app_db_path, second_id, status="failed", error="boom")

    result = runner.invoke(app, ["logs", "runs", "--path", str(app_db_path), "--limit", "1"])

    assert result.exit_code == 0
    assert "Ingest runs" in result.output
    assert "ohlcv:1d" in result.output
    assert "NASDAQ" in result.output
    assert "failed" in result.output
    assert "boom" in result.output
    assert "symbols" not in result.output
    assert runs_have_kst_offset(app_db_path)


def test_logs_api_command_prints_recent_api_logs(tmp_path) -> None:
    app_db_path = tmp_path / "app.db"
    init_app_database(app_db_path)
    record_api_log(app_db_path, endpoint="symbol_master:KOSPI", status_code=200)
    record_api_log(
        app_db_path,
        endpoint="ohlcv:NASDAQ:1d",
        tr_id="HHDFS76240000",
        error="timeout",
    )

    result = runner.invoke(app, ["logs", "api", "--path", str(app_db_path), "--limit", "1"])

    assert result.exit_code == 0
    assert "API logs" in result.output
    assert "ohlcv:NASDAQ:1d" in result.output
    assert "HHDFS76240000" in result.output
    assert "timeout" in result.output
    assert "symbol_master:KOSPI" not in result.output


def test_app_log_repositories_return_recent_rows_first(tmp_path) -> None:
    app_db_path = tmp_path / "app.db"
    init_app_database(app_db_path)
    first_id = start_ingest_run(app_db_path, kind="symbols", market="KOSPI")
    finish_ingest_run(app_db_path, first_id, status="success", rows_written=1)
    second_id = start_ingest_run(app_db_path, kind="symbols", market="NASDAQ")
    finish_ingest_run(app_db_path, second_id, status="success", rows_written=2)
    record_api_log(app_db_path, endpoint="first", status_code=200)
    record_api_log(app_db_path, endpoint="second", status_code=500)

    runs = list_ingest_runs(app_db_path, limit=1)
    api_logs = list_api_logs(app_db_path, limit=1)

    assert [run.market for run in runs] == ["NASDAQ"]
    assert [row["endpoint"] for row in api_logs] == ["second"]
    assert runs[0].started_at.endswith("+09:00")
    assert runs[0].finished_at.endswith("+09:00")
    assert str(api_logs[0]["requested_at"]).endswith("+09:00")


def runs_have_kst_offset(app_db_path) -> bool:
    runs = list_ingest_runs(app_db_path, limit=1)
    return runs[0].started_at.endswith("+09:00") and runs[0].finished_at.endswith("+09:00")
