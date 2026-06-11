import duckdb

from research.fractal.data import load_fractal_candles_from_warehouse


def test_load_fractal_candles_from_warehouse_loads_daily_rows_in_time_order(tmp_path):
    db_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE ohlcv_bars (
                market VARCHAR,
                symbol VARCHAR,
                interval VARCHAR,
                timestamp VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            )
            """
        )
        connection.executemany(
            "INSERT INTO ohlcv_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("NASDAQ", "AAPL", "1d", "2026-01-02", 2, 3, 1, 2.5, 20),
                ("NASDAQ", "AAPL", "1d", "2026-01-01", 1, 2, 0.5, 1.5, 10),
            ],
        )

    candles = load_fractal_candles_from_warehouse(
        db_path,
        market="NASDAQ",
        symbol="AAPL",
        interval="1d",
    )

    assert [candle.timestamp for candle in candles] == ["2026-01-01", "2026-01-02"]
    assert [candle.close for candle in candles] == [1.5, 2.5]
    assert [candle.volume for candle in candles] == [10.0, 20.0]


def test_load_fractal_candles_from_warehouse_loads_minute_rows(tmp_path):
    db_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE overseas_minute_bars (
                market VARCHAR,
                symbol VARCHAR,
                interval_minutes BIGINT,
                local_business_date VARCHAR,
                local_date VARCHAR,
                local_time VARCHAR,
                korea_date VARCHAR,
                korea_time VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                amount DOUBLE
            )
            """
        )
        connection.executemany(
            "INSERT INTO overseas_minute_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "NASDAQ",
                    "AAPL",
                    1,
                    "2026-01-02",
                    "2026-01-02",
                    "09:31:00",
                    "2026-01-02",
                    "23:31:00",
                    2,
                    3,
                    1,
                    2.5,
                    20,
                    50,
                ),
                (
                    "NASDAQ",
                    "AAPL",
                    1,
                    "2026-01-02",
                    "2026-01-02",
                    "09:30:00",
                    "2026-01-02",
                    "23:30:00",
                    1,
                    2,
                    0.5,
                    1.5,
                    10,
                    15,
                ),
            ],
        )

    candles = load_fractal_candles_from_warehouse(
        db_path,
        market="NASDAQ",
        symbol="AAPL",
        interval="1m",
    )

    assert [candle.timestamp for candle in candles] == [
        "2026-01-02 09:30:00",
        "2026-01-02 09:31:00",
    ]
    assert [candle.high for candle in candles] == [2.0, 3.0]
