from __future__ import annotations

import csv
import json

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.services.query import query_stored_daily_ohlcv, query_stored_overseas_minutes
from kis_cli.storage import connect, init_database
from kis_cli.storage.repositories import insert_ohlcv_bar, insert_overseas_minute_bars

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
    assert [row["timestamp"] for row in result.rows] == ["2026-05-09", "2026-05-08"]
    assert [row["close"] for row in result.rows] == [109.0, 108.0]


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
            change=500.0,
            change_rate=0.71,
            amount=87000000.0,
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
            "change": 500.0,
            "change_rate": 0.71,
            "amount": 87000000.0,
        }
    ]


def test_query_ohlcv_command_table_includes_change_metrics(tmp_path) -> None:
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
            change=500.0,
            change_rate=0.71,
            amount=87000000.0,
        )

    result = runner.invoke(
        app,
        ["query", "ohlcv", "--symbol", "005930", "--db-path", str(db_path)],
        env={"COLUMNS": "200"},
    )

    assert result.exit_code == 0
    assert "Change" in result.output
    assert "Change Rate" in result.output
    assert "Amount" in result.output
    assert "500.0" in result.output
    assert "0.71" in result.output
    assert "87000000.0" in result.output


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
    assert all_rows[0]["timestamp"] == "2026-05-23"
    assert all_rows[-1]["timestamp"] == "2026-05-01"


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
            change=5.0,
            change_rate=5.0,
            amount=105000.0,
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
            "change": "5.0",
            "change_rate": "5.0",
            "amount": "105000.0",
        }
    ]


def _minute_bar(
    *,
    local_date: str,
    local_time: str,
    close: float,
    volume: int = 100,
    interval_minutes: int = 1,
) -> dict[str, object]:
    return {
        "market": "NASDAQ",
        "symbol": "AAPL",
        "interval_minutes": interval_minutes,
        "local_business_date": local_date,
        "local_date": local_date,
        "local_time": local_time,
        "korea_date": local_date,
        "korea_time": local_time,
        "open": 100.0,
        "high": 110.0,
        "low": 99.0,
        "close": close,
        "volume": volume,
        "amount": 10000.0,
    }


def test_query_stored_overseas_minutes_orders_newest_first(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_overseas_minute_bars(
            connection,
            [
                _minute_bar(local_date="2026-05-07", local_time="09:35:00", close=101.0),
                _minute_bar(local_date="2026-05-07", local_time="09:40:00", close=102.0),
                _minute_bar(local_date="2026-05-08", local_time="09:30:00", close=103.0),
            ],
        )

    result = query_stored_overseas_minutes(symbol="aapl", limit=10, db_path=db_path)

    assert result.symbol == "AAPL"
    assert [row["close"] for row in result.rows] == [103.0, 102.0, 101.0]


def test_query_minutes_command_outputs_json(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_overseas_minute_bars(
            connection,
            [_minute_bar(local_date="2026-05-07", local_time="15:30:00", close=105.5)],
        )

    result = runner.invoke(
        app,
        ["query", "minutes", "--symbol", "AAPL", "--format", "json", "--db-path", str(db_path)],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert len(rows) == 1
    assert rows[0]["market"] == "NASDAQ"
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["interval_minutes"] == 1
    assert rows[0]["local_date"] == "2026-05-07"
    assert rows[0]["local_time"] == "15:30:00"
    assert rows[0]["close"] == 105.5


def test_query_minutes_command_exports_csv(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    export_path = tmp_path / "exports" / "aapl-min.csv"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_overseas_minute_bars(
            connection,
            [_minute_bar(local_date="2026-05-07", local_time="15:30:00", close=105.5)],
        )

    result = runner.invoke(
        app,
        [
            "query",
            "minutes",
            "--symbol",
            "AAPL",
            "--export",
            str(export_path),
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Overseas minute bars exported" in result.output
    with export_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert rows == [
        {
            "market": "NASDAQ",
            "symbol": "AAPL",
            "interval_minutes": "1",
            "local_business_date": "2026-05-07",
            "local_date": "2026-05-07",
            "local_time": "15:30:00",
            "korea_date": "2026-05-07",
            "korea_time": "15:30:00",
            "open": "100.0",
            "high": "110.0",
            "low": "99.0",
            "close": "105.5",
            "volume": "100",
            "amount": "10000.0",
        }
    ]
