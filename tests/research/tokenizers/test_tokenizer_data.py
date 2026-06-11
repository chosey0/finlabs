import duckdb

from research.tokenizers.data import (
    CandleBar,
    filter_by_min_volume,
    load_candles,
    split_by_date,
)


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


def test_load_candles_loads_overseas_minute_bars(tmp_path):
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
                ("NASDAQ", "AAPL", 1, "2026-01-02", "2026-01-02", "09:31:00", "2026-01-02", "23:31:00", 2, 3, 1, 2.5, 20, 50),
                ("NASDAQ", "AAPL", 1, "2026-01-02", "2026-01-02", "09:30:00", "2026-01-02", "23:30:00", 1, 2, 0.5, 1.5, 10, 15),
                ("NASDAQ", "AAPL", 5, "2026-01-02", "2026-01-02", "09:30:00", "2026-01-02", "23:30:00", 5, 6, 4, 5.5, 50, 275),
                ("NYSE", "AAPL", 1, "2026-01-02", "2026-01-02", "09:32:00", "2026-01-02", "23:32:00", 3, 4, 2, 3.5, 30, 105),
            ],
        )

    candles = load_candles(db_path, market="NASDAQ", symbol="aapl", interval="1m")

    assert [candle.timestamp for candle in candles] == ["2026-01-02 09:30:00", "2026-01-02 09:31:00"]
    assert [candle.interval for candle in candles] == ["1m", "1m"]
    assert [candle.close for candle in candles] == [1.5, 2.5]
    assert all(candle.market == "NASDAQ" for candle in candles)


def test_load_candles_accepts_minute_interval_aliases(tmp_path):
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
        connection.execute(
            "INSERT INTO overseas_minute_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("NASDAQ", "AAPL", 5, "2026-01-02", "2026-01-02", "09:30:00", "2026-01-02", "23:30:00", 1, 2, 0.5, 1.5, 10, 15),
        )

    candles = load_candles(db_path, market="NASDAQ", symbol="AAPL", interval="5minutes")

    assert len(candles) == 1
    assert candles[0].interval == "5m"


def test_filter_by_min_volume_excludes_low_volume_candles():
    candles = tuple(
        CandleBar("NASDAQ", "AAPL", "1m", f"2026-01-01 09:3{i}:00", 1.0, 2.0, 0.5, 1.5, volume)
        for i, volume in enumerate((0, 1, 2, 100))
    )

    filtered = filter_by_min_volume(candles, min_volume=2)

    assert [candle.volume for candle in filtered] == [2, 100]


def test_filter_by_min_volume_rejects_negative_threshold():
    candles = (CandleBar("NASDAQ", "AAPL", "1m", "2026-01-01 09:30:00", 1.0, 2.0, 0.5, 1.5, 1),)

    try:
        filter_by_min_volume(candles, min_volume=-1)
    except ValueError as exc:
        assert "min_volume" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("negative min_volume should fail")


def test_split_by_ratio_preserves_time_order_without_shuffle():
    candles = tuple(
        CandleBar("NASDAQ", "AAPL", "1m", timestamp, 1.0, 2.0, 0.5, 1.5, 10)
        for timestamp in (
            "2026-01-01 09:34:00",
            "2026-01-01 09:30:00",
            "2026-01-01 09:31:00",
            "2026-01-01 09:32:00",
            "2026-01-01 09:33:00",
        )
    )

    from research.tokenizers.data import split_by_ratio

    split = split_by_ratio(candles, train_ratio=0.6, val_ratio=0.2)

    assert [candle.timestamp for candle in split.train] == [
        "2026-01-01 09:30:00",
        "2026-01-01 09:31:00",
        "2026-01-01 09:32:00",
    ]
    assert [candle.timestamp for candle in split.val] == ["2026-01-01 09:33:00"]
    assert [candle.timestamp for candle in split.test] == ["2026-01-01 09:34:00"]
