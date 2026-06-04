from __future__ import annotations

import duckdb
import pytest

from dashboard import reader
from dashboard.reader import WarehouseBusyError, read_candles_with_retry


def _no_sleep(_seconds: float) -> None:
    return None


def test_retries_then_succeeds_on_lock(monkeypatch) -> None:
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise duckdb.Error("IO Error: Could not set lock ... Conflicting lock")
        return ("candle",)

    monkeypatch.setattr(reader, "load_candles", flaky)
    result = read_candles_with_retry(
        "wh.duckdb", market="NASDAQ", symbol="NVDA", interval="1d", sleep=_no_sleep
    )
    assert result == ("candle",)
    assert calls["n"] == 3


def test_raises_warehouse_busy_after_all_retries(monkeypatch) -> None:
    def always_locked(*args, **kwargs):
        raise duckdb.Error("Conflicting lock held by another process")

    monkeypatch.setattr(reader, "load_candles", always_locked)
    with pytest.raises(WarehouseBusyError):
        read_candles_with_retry(
            "wh.duckdb", market="NASDAQ", symbol="NVDA", interval="1d", sleep=_no_sleep
        )


def test_non_lock_error_propagates(monkeypatch) -> None:
    def other_error(*args, **kwargs):
        raise duckdb.Error("Catalog Error: table not found")

    monkeypatch.setattr(reader, "load_candles", other_error)
    with pytest.raises(duckdb.Error, match="Catalog Error"):
        read_candles_with_retry(
            "wh.duckdb", market="NASDAQ", symbol="NVDA", interval="1d", sleep=_no_sleep
        )


def test_list_available_series_missing_warehouse_returns_empty(tmp_path) -> None:
    assert reader.list_available_series(tmp_path / "nope.duckdb") == []


def test_weekly_and_monthly_series_are_readable(tmp_path) -> None:
    # Regression: Collect offers 1w/1mo, so reads of those intervals must work
    # (previously load_candles only matched 1d and crashed the Chart page).
    from kis_cli.storage import connect, init_database
    from kis_cli.storage.repositories import insert_ohlcv_bar

    db_path = tmp_path / "wh.duckdb"
    init_database(db_path)
    with connect(db_path) as connection:
        for interval, ts in (("1w", "2024-01-01"), ("1mo", "2024-01-31"), ("1d", "2024-02-01")):
            insert_ohlcv_bar(
                connection,
                market="NASDAQ",
                symbol="NVDA",
                interval=interval,
                timestamp=ts,
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=100,
            )

    series = reader.list_available_series(db_path)
    intervals = {s["interval"] for s in series}
    assert {"1w", "1mo", "1d"} <= intervals

    weekly = reader.read_candles_with_retry(
        db_path, market="NASDAQ", symbol="NVDA", interval="1w", sleep=_no_sleep
    )
    monthly = reader.read_candles_with_retry(
        db_path, market="NASDAQ", symbol="NVDA", interval="1mo", sleep=_no_sleep
    )
    assert len(weekly) == 1 and weekly[0].interval == "1w"
    assert len(monthly) == 1 and monthly[0].interval == "1mo"


def test_with_lock_retry_is_public() -> None:
    # The fractal page routes its loads through this public choke point.
    assert callable(reader.with_lock_retry)
