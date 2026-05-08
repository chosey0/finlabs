from __future__ import annotations

import csv
import json

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.services.query import query_stored_daily_ohlcv
from kis_cli.storage import connect, init_database
from kis_cli.storage.repositories import insert_ohlcv_bar

runner = CliRunner()


def test_query_stored_daily_ohlcv_uses_symbol_only_and_daily_interval(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)

    with connect(db_path) as connection:
        insert_ohlcv_bar(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            interval="1w",
            timestamp="2026-05-01",
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10,
        )
        for market, timestamp, close in (
            ("NASDAQ", "2026-05-07", 107.0),
            ("NASDAQ", "2026-05-08", 108.0),
            ("NASDAQ", "2026-05-09", 109.0),
        ):
            insert_ohlcv_bar(
                connection,
                market=market,
                symbol="AAPL",
                interval="1d",
                timestamp=timestamp,
                open=100.0,
                high=110.0,
                low=99.0,
                close=close,
                volume=1000,
            )

    result = query_stored_daily_ohlcv(symbol="aapl", limit=2, db_path=db_path)

    assert result.symbol == "AAPL"
    assert result.interval == "1d"
    assert [row["timestamp"] for row in result.rows] == ["2026-05-08", "2026-05-09"]
    assert [row["close"] for row in result.rows] == [108.0, 109.0]


def test_query_ohlcv_command_outputs_json(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_ohlcv_bar(
            connection,
            market="KOSPI",
            symbol="005930",
            interval="1d",
            timestamp="2026-05-07",
            open=70000.0,
            high=71000.0,
            low=69000.0,
            close=70500.0,
            volume=1234,
        )

    result = runner.invoke(
        app,
        ["query", "ohlcv", "--symbol", "005930", "--format", "json", "--db-path", str(db_path)],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert rows == [
        {
            "market": "KOSPI",
            "symbol": "005930",
            "interval": "1d",
            "timestamp": "2026-05-07",
            "open": 70000.0,
            "high": 71000.0,
            "low": 69000.0,
            "close": 70500.0,
            "volume": 1234,
        }
    ]


def test_query_ohlcv_command_all_returns_every_matching_row(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)
    with connect(db_path) as connection:
        for day in range(1, 24):
            insert_ohlcv_bar(
                connection,
                market="KOSPI",
                symbol="005930",
                interval="1d",
                timestamp=f"2026-05-{day:02d}",
                open=70000.0,
                high=71000.0,
                low=69000.0,
                close=70000.0 + day,
                volume=1000 + day,
            )

    default_result = runner.invoke(
        app,
        ["query", "ohlcv", "--symbol", "005930", "--format", "json", "--db-path", str(db_path)],
    )
    all_result = runner.invoke(
        app,
        [
            "query",
            "ohlcv",
            "--symbol",
            "005930",
            "--all",
            "--format",
            "json",
            "--db-path",
            str(db_path),
        ],
    )

    assert default_result.exit_code == 0
    assert all_result.exit_code == 0
    assert len(json.loads(default_result.output)) == 20
    all_rows = json.loads(all_result.output)
    assert len(all_rows) == 23
    assert all_rows[0]["timestamp"] == "2026-05-01"
    assert all_rows[-1]["timestamp"] == "2026-05-23"


def test_query_ohlcv_command_exports_csv(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    export_path = tmp_path / "exports" / "aapl.csv"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_ohlcv_bar(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            interval="1d",
            timestamp="2026-05-07",
            open=100.0,
            high=110.0,
            low=99.0,
            close=105.0,
            volume=1000,
        )

    result = runner.invoke(
        app,
        [
            "query",
            "ohlcv",
            "--symbol",
            "AAPL",
            "--export",
            str(export_path),
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "OHLCV exported" in result.output
    with export_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert rows == [
        {
            "market": "NASDAQ",
            "symbol": "AAPL",
            "interval": "1d",
            "timestamp": "2026-05-07",
            "open": "100.0",
            "high": "110.0",
            "low": "99.0",
            "close": "105.0",
            "volume": "1000",
        }
    ]
