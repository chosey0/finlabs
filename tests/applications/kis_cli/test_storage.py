from __future__ import annotations

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.storage import connect, init_database, inspect_database_counts, inspect_database_schema
from kis_cli.storage.repositories import (
    insert_ohlcv_bar,
    insert_realtime_tick,
    insert_symbol,
    list_ohlcv_bars,
    search_symbols,
    upsert_symbols,
)
from kis_cli.storage.schema import TABLE_NAMES

runner = CliRunner()


def test_init_database_creates_required_tables(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"

    result = init_database(db_path)

    assert result.path == db_path
    assert result.tables == TABLE_NAMES
    with connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                """
            ).fetchall()
        }
    assert set(TABLE_NAMES).issubset(table_names)


def test_db_init_command_creates_schema(tmp_path) -> None:
    db_path = tmp_path / "custom.db"

    result = runner.invoke(app, ["db", "init", "--path", str(db_path)])

    assert result.exit_code == 0
    assert "Database initialized" in result.output
    assert db_path.exists()
    with connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    assert count == 0


def test_inspect_database_schema_returns_tables_columns_and_indexes(tmp_path) -> None:
    db_path = tmp_path / "custom.db"
    init_database(db_path)

    result = inspect_database_schema(db_path)

    symbols = next(table for table in result.tables if table.name == "symbols")
    assert {column.name for column in symbols.columns}.issuperset({"market", "symbol"})
    assert any(index.unique and index.columns == ("market", "symbol") for index in symbols.indexes)


def test_db_schema_command_prints_database_structure(tmp_path) -> None:
    db_path = tmp_path / "custom.db"
    init_database(db_path)

    result = runner.invoke(app, ["db", "schema", "--path", str(db_path)])

    assert result.exit_code == 0
    assert "Database schema" in result.output
    assert "Table: symbols" in result.output
    assert "market" in result.output
    assert "symbol" in result.output


def test_inspect_database_counts_returns_table_row_counts(tmp_path) -> None:
    db_path = tmp_path / "custom.db"
    init_database(db_path)

    with connect(db_path) as connection:
        insert_symbol(connection, market="NASDAQ", symbol="AAPL", name="Apple Inc.")
        insert_symbol(connection, market="NASDAQ", symbol="MSFT", name="Microsoft")
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

    result = inspect_database_counts(db_path)

    counts = {table.name: table.rows for table in result.tables}
    assert counts["symbols"] == 2
    assert counts["ohlcv_bars"] == 1
    assert result.total_rows == 3


def test_db_counts_command_prints_table_row_counts(tmp_path) -> None:
    db_path = tmp_path / "custom.db"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_symbol(connection, market="NASDAQ", symbol="AAPL", name="Apple Inc.")

    result = runner.invoke(app, ["db", "counts", "--path", str(db_path)])

    assert result.exit_code == 0
    assert "Database counts" in result.output
    assert "symbols" in result.output
    assert "1" in result.output
    assert "Total" in result.output


def test_symbol_unique_constraint_prevents_duplicate_inserts(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)

    with connect(db_path) as connection:
        first_inserted = insert_symbol(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            name="Apple Inc.",
        )
        duplicate_inserted = insert_symbol(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            name="Duplicate Apple",
        )
        count = connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]

    assert first_inserted is True
    assert duplicate_inserted is False
    assert count == 1
    with connect(db_path) as connection:
        downloaded_at, created_at, updated_at = connection.execute(
            """
            SELECT downloaded_at, created_at, updated_at
            FROM symbols
            WHERE market = 'NASDAQ' AND symbol = 'AAPL'
            """
        ).fetchone()
    assert str(downloaded_at).endswith("+09:00")
    assert str(created_at).endswith("+09:00")
    assert str(updated_at).endswith("+09:00")


def test_symbol_upsert_replaces_existing_market_snapshot(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)

    with connect(db_path) as connection:
        upsert_symbols(
            connection,
            [
                _symbol_values(market="NASDAQ", symbol="AAPL", english_name="Apple"),
                _symbol_values(market="NASDAQ", symbol="MSFT", english_name="Microsoft"),
                _symbol_values(market="NYSE", symbol="IBM", english_name="IBM"),
            ],
        )
        stored = upsert_symbols(
            connection,
            [
                _symbol_values(market="NASDAQ", symbol="AAPL", english_name="Apple Inc."),
            ],
        )
        rows = connection.execute(
            """
            SELECT market, symbol, english_name
            FROM symbols
            ORDER BY market, symbol
            """
        ).fetchall()

    assert stored == 1
    assert rows == [
        ("NASDAQ", "AAPL", "Apple Inc."),
        ("NYSE", "IBM", "IBM"),
    ]


def test_symbol_search_orders_by_query_similarity(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)

    with connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO symbols (
                market, symbol, korean_name, english_name, raw_source, raw, downloaded_at
            )
            VALUES (?, ?, ?, ?, '', '{}', CURRENT_TIMESTAMP)
            """,
            [
                ("NASDAQ", "PINE", "파인애플", "Pineapple Holdings",),
                ("NASDAQ", "AAPL", "애플", "Apple",),
                ("NASDAQ", "APPLEW", "애플 워런트", "Apple Warrant",),
                ("NASDAQ", "MSFT", "마이크로소프트", "Microsoft",),
                ("NASDAQ", "APPLE", "애플", "Apple Inc.",),
            ],
        )

        rows = search_symbols(connection, query="apple")

    assert [row["symbol"] for row in rows] == ["APPLE", "AAPL", "APPLEW", "PINE"]


def _symbol_values(*, market: str, symbol: str, english_name: str) -> dict[str, object]:
    return {
        "market": market,
        "symbol": symbol,
        "standard_code": "",
        "realtime_symbol": symbol,
        "korean_name": "",
        "english_name": english_name,
        "security_type": "",
        "currency": "USD",
        "exchange_id": "",
        "exchange_code": "",
        "exchange_name": market,
        "country_code": "US",
        "listed_date": "",
        "base_price": None,
        "lot_size": None,
        "raw_source": "test",
        "raw": "{}",
        "downloaded_at": "2026-05-07T00:00:00+00:00",
    }


def test_ohlcv_unique_constraint_prevents_duplicate_inserts(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)

    with connect(db_path) as connection:
        first_inserted = insert_ohlcv_bar(
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
        duplicate_inserted = insert_ohlcv_bar(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            interval="1d",
            timestamp="2026-05-07",
            open=200.0,
            high=210.0,
            low=199.0,
            close=205.0,
            volume=2000,
        )
        count = connection.execute("SELECT COUNT(*) FROM ohlcv_bars").fetchone()[0]

    assert first_inserted is True
    assert duplicate_inserted is False
    assert count == 1
    with connect(db_path) as connection:
        created_at = connection.execute(
            """
            SELECT created_at
            FROM ohlcv_bars
            WHERE market = 'NASDAQ' AND symbol = 'AAPL'
            """
        ).fetchone()[0]
    assert str(created_at).endswith("+09:00")


def test_realtime_tick_unique_constraint_prevents_duplicate_inserts(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)

    with connect(db_path) as connection:
        first_inserted = insert_realtime_tick(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            exchange_ts="2026-05-07T09:00:00Z",
            received_at="2026-05-07T09:00:01Z",
            received_seq=1,
            seq=42,
            price=105.0,
            volume=10,
        )
        duplicate_inserted = insert_realtime_tick(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            exchange_ts="2026-05-07T09:00:00Z",
            received_at="2026-05-07T09:00:02Z",
            received_seq=2,
            seq=42,
            price=106.0,
            volume=20,
        )
        count = connection.execute("SELECT COUNT(*) FROM realtime_ticks").fetchone()[0]

    assert first_inserted is True
    assert duplicate_inserted is False
    assert count == 1
    with connect(db_path) as connection:
        created_at = connection.execute(
            """
            SELECT created_at
            FROM realtime_ticks
            WHERE market = 'NASDAQ' AND symbol = 'AAPL'
            """
        ).fetchone()[0]
    assert str(created_at).endswith("+09:00")


def test_ohlcv_query_uses_latest_first_timestamp_order(tmp_path) -> None:
    db_path = tmp_path / "test-warehouse.duckdb"
    init_database(db_path)

    with connect(db_path) as connection:
        for timestamp, close in (
            ("2026-05-09", 109.0),
            ("2026-05-07", 107.0),
            ("2026-05-08", 108.0),
        ):
            insert_ohlcv_bar(
                connection,
                market="NASDAQ",
                symbol="AAPL",
                interval="1d",
                timestamp=timestamp,
                open=100.0,
                high=110.0,
                low=99.0,
                close=close,
                volume=1000,
            )

        rows = list_ohlcv_bars(
            connection,
            market="NASDAQ",
            symbol="AAPL",
            interval="1d",
        )

    assert [row["timestamp"] for row in rows] == [
        "2026-05-09",
        "2026-05-08",
        "2026-05-07",
    ]
    assert [row["close"] for row in rows] == [109.0, 108.0, 107.0]
