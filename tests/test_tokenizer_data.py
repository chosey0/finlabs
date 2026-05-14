import duckdb

from research.tokenizers.data import CandleBar, load_candles, split_by_date


def test_load_candles_filters_and_orders(tmp_path):
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
                ("NASDAQ", "AAPL", "1d", "2026-01-03", 1, 2, 0.5, 1.5, 30),
                ("NASDAQ", "AAPL", "1d", "2026-01-01", 1, 2, 0.5, 1.5, 10),
                ("NYSE", "AAPL", "1d", "2026-01-02", 1, 2, 0.5, 1.5, 20),
            ],
        )

    candles = load_candles(db_path, market="NASDAQ", symbol="AAPL", interval="1d")

    assert [candle.timestamp for candle in candles] == ["2026-01-01", "2026-01-03"]
    assert all(candle.market == "NASDAQ" for candle in candles)


def test_split_by_date_uses_inclusive_boundaries():
    candles = tuple(
        CandleBar("NASDAQ", "AAPL", "1d", timestamp, 1.0, 2.0, 0.5, 1.5, 10)
        for timestamp in ("2026-01-03", "2026-01-01", "2026-01-02", "2026-01-04")
    )

    split = split_by_date(candles, train_end="2026-01-01", val_end="2026-01-03")

    assert [candle.timestamp for candle in split.train] == ["2026-01-01"]
    assert [candle.timestamp for candle in split.val] == ["2026-01-02", "2026-01-03"]
    assert [candle.timestamp for candle in split.test] == ["2026-01-04"]
