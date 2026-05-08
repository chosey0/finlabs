from __future__ import annotations

import csv
import json
from io import StringIO

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.storage.app_db import connect_app, init_app_database
from kis_cli.storage.app_repositories import (
    find_api_logs,
    find_ingest_runs,
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


def test_logs_runs_command_filters_and_prints_json(tmp_path) -> None:
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

    result = runner.invoke(
        app,
        [
            "logs",
            "runs",
            "--path",
            str(app_db_path),
            "--status",
            "failed",
            "--kind",
            "ohlcv:1d",
            "--market",
            "nasdaq",
            "--symbol",
            "aapl",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert len(rows) == 1
    assert rows[0]["kind"] == "ohlcv:1d"
    assert rows[0]["market"] == "NASDAQ"
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["status"] == "failed"
    assert rows[0]["error"] == "boom"


def test_logs_runs_command_prints_csv(tmp_path) -> None:
    app_db_path = tmp_path / "app.db"
    init_app_database(app_db_path)
    run_id = start_ingest_run(app_db_path, kind="symbols", market="KOSDAQ")
    finish_ingest_run(app_db_path, run_id, status="success", rows_written=3)

    result = runner.invoke(
        app,
        ["logs", "runs", "--path", str(app_db_path), "--format", "csv"],
    )

    assert result.exit_code == 0
    rows = list(csv.DictReader(StringIO(result.output)))
    assert rows[0]["kind"] == "symbols"
    assert rows[0]["market"] == "KOSDAQ"
    assert rows[0]["status"] == "success"


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


def test_logs_api_command_filters_and_prints_json(tmp_path) -> None:
    app_db_path = tmp_path / "app.db"
    init_app_database(app_db_path)
    record_api_log(app_db_path, endpoint="symbol_master:KOSPI", status_code=200)
    record_api_log(
        app_db_path,
        endpoint="ohlcv:NASDAQ:1d",
        tr_id="HHDFS76240000",
        status_code=500,
        error="timeout",
    )

    result = runner.invoke(
        app,
        [
            "logs",
            "api",
            "--path",
            str(app_db_path),
            "--endpoint",
            "ohlcv",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert rows == [
        {
            "endpoint": "ohlcv:NASDAQ:1d",
            "tr_id": "HHDFS76240000",
            "status_code": 500,
            "requested_at": rows[0]["requested_at"],
            "elapsed_ms": None,
            "error": "timeout",
        }
    ]


def test_logs_api_command_prints_csv(tmp_path) -> None:
    app_db_path = tmp_path / "app.db"
    init_app_database(app_db_path)
    record_api_log(app_db_path, endpoint="ohlcv:KOSPI:1d", status_code=200)

    result = runner.invoke(app, ["logs", "api", "--path", str(app_db_path), "--format", "csv"])

    assert result.exit_code == 0
    rows = list(csv.DictReader(StringIO(result.output)))
    assert rows[0]["endpoint"] == "ohlcv:KOSPI:1d"
    assert rows[0]["status_code"] == "200"


def test_logs_commands_do_not_create_missing_app_database(tmp_path) -> None:
    app_db_path = tmp_path / "missing.db"

    result = runner.invoke(app, ["logs", "runs", "--path", str(app_db_path)])

    assert result.exit_code != 0
    assert "app database not found" in result.output
    assert not app_db_path.exists()


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


def test_app_log_repositories_filter_rows(tmp_path) -> None:
    app_db_path = tmp_path / "app.db"
    init_app_database(app_db_path)
    with connect_app(app_db_path) as connection:
        connection.execute(
            """
            INSERT INTO ingest_runs (
                kind, market, symbol, started_at, finished_at, status, rows_written, error
            )
            VALUES
                ('symbols', 'KOSPI', NULL, '2026-05-07T09:00:00+09:00', '2026-05-07T09:01:00+09:00', 'success', 10, NULL),
                ('ohlcv:1d', 'NASDAQ', 'AAPL', '2026-05-08T09:00:00+09:00', '2026-05-08T09:01:00+09:00', 'failed', 0, 'boom')
            """
        )
        connection.execute(
            """
            INSERT INTO api_logs (
                endpoint, tr_id, status_code, requested_at, elapsed_ms, error
            )
            VALUES
                ('symbol_master:KOSPI', NULL, 200, '2026-05-07T09:00:00+09:00', 10, NULL),
                ('ohlcv:NASDAQ:1d', 'HHDFS76240000', 500, '2026-05-08T09:00:00+09:00', 20, 'timeout')
            """
        )

    runs = find_ingest_runs(
        app_db_path,
        status="failed",
        kind="OHLCV:1D",
        market="nasdaq",
        symbol="aapl",
        since="2026-05-08",
    )
    api_logs = find_api_logs(app_db_path, endpoint="ohlcv", since="2026-05-08")

    assert [run.symbol for run in runs] == ["AAPL"]
    assert [row["endpoint"] for row in api_logs] == ["ohlcv:NASDAQ:1d"]


def runs_have_kst_offset(app_db_path) -> bool:
    runs = list_ingest_runs(app_db_path, limit=1)
    return runs[0].started_at.endswith("+09:00") and runs[0].finished_at.endswith("+09:00")
