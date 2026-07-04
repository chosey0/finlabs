"""KIS canonical adapter(mapper·capabilities·market-data 검증)의 단위 테스트."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from modules.adapters.brokers.kis import KIS_CAPABILITIES
from modules.adapters.brokers.kis.mapper import minute_to_candle, ohlcv_to_candle
from modules.adapters.brokers.kis.market_data import (
    fetch_ohlcv_history,
    fetch_overseas_minutes,
    normalize_period,
    period_to_interval,
)
from brokers.kis import OhlcvBar, OverseasMinuteBar
from modules.domain.market_data import CandleBar


def test_capabilities_declare_kis_feature_set() -> None:
    assert KIS_CAPABILITIES.broker == "kis"
    assert KIS_CAPABILITIES.supports_daily_ohlcv
    assert KIS_CAPABILITIES.supports_minute_ohlcv
    assert KIS_CAPABILITIES.supports_symbol_master
    assert KIS_CAPABILITIES.supports_current_price
    assert KIS_CAPABILITIES.supports_realtime


def test_ohlcv_bar_maps_to_canonical_candle() -> None:
    bar = OhlcvBar(
        market="NASDAQ",
        symbol="AAPL",
        interval="1d",
        timestamp="2026-01-02",
        open=Decimal("182.50"),
        high=Decimal("183.00"),
        low=Decimal("182.00"),
        close=Decimal("182.86"),
        volume=1000,
    )

    candle = ohlcv_to_candle(bar)

    assert candle == CandleBar(
        market="NASDAQ",
        symbol="AAPL",
        interval="1d",
        timestamp="2026-01-02",
        open=182.50,
        high=183.00,
        low=182.00,
        close=182.86,
        volume=1000,
    )


def test_minute_bar_maps_interval_label_and_local_timestamp() -> None:
    bar = OverseasMinuteBar(
        market="NASDAQ",
        symbol="AAPL",
        interval_minutes=5,
        local_business_date="20260102",
        local_date="20260102",
        local_time="093000",
        korea_date="20260102",
        korea_time="233000",
        open=Decimal("182.50"),
        high=Decimal("183.00"),
        low=Decimal("182.00"),
        close=Decimal("182.86"),
        volume=250,
        amount=Decimal("45715.00"),
    )

    candle = minute_to_candle(bar)

    assert candle.interval == "5m"
    assert candle.timestamp == "20260102 093000"
    assert candle.close == 182.86
    assert candle.volume == 250


def test_normalize_period_accepts_known_codes_case_insensitively() -> None:
    assert normalize_period(" d ") == "D"
    assert period_to_interval("w") == "1w"
    assert period_to_interval("M") == "1mo"
    with pytest.raises(ValueError, match="period must be one of"):
        normalize_period("H")


def test_fetch_ohlcv_history_rejects_invalid_requests_before_sdk_call() -> None:
    client = _UnusedClient()

    with pytest.raises(ValueError, match="start must be on or before end"):
        _run_fetch(client, market="NASDAQ", start="2026-02-01", end="2026-01-01")
    with pytest.raises(ValueError, match="Kiwoom"):
        _run_fetch(client, market="KOSPI")
    with pytest.raises(ValueError, match="overseas stock markets only"):
        _run_fetch(client, market="LSE")
    with pytest.raises(ValueError, match="supports only D, W, or M"):
        _run_fetch(client, market="NASDAQ", period="Y")


def test_fetch_ohlcv_history_dispatches_uppercase_exchange_code() -> None:
    captured: dict[str, object] = {}

    async def fake_daily(symbol: str, **kwargs: object) -> list[object]:
        captured["symbol"] = symbol
        captured.update(kwargs)
        return []

    client = SimpleNamespace(
        overseas=SimpleNamespace(chart=SimpleNamespace(daily=fake_daily))
    )

    result = _run_fetch(client, market="NASDAQ", period="w")

    assert result == []
    assert captured["symbol"] == "AAPL"
    assert captured["exchange"] == "NAS"
    assert captured["period"] == "W"
    assert captured["market"] == "NASDAQ"


def test_fetch_overseas_minutes_rejects_domestic_market() -> None:
    with pytest.raises(ValueError, match="overseas stock markets only"):
        asyncio.run(
            fetch_overseas_minutes(
                _UnusedClient(),
                market="KOSDAQ",
                symbol="035720",
                start="2026-01-02 09:00:00",
                interval_minutes=1,
                count=10,
                include_previous=False,
            )
        )


class _UnusedClient:
    """검증 실패가 SDK 호출 전에 일어나는지 보장하는 클라이언트 대역."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError("SDK must not be called for invalid requests")


def _run_fetch(
    client: object,
    *,
    market: str,
    start: str = "2026-01-01",
    end: str = "2026-01-31",
    period: str = "D",
) -> list[object]:
    return asyncio.run(
        fetch_ohlcv_history(
            client,  # type: ignore[arg-type]
            market=market,
            symbol="AAPL",
            start=start,
            end=end,
            period=period,
            adjusted=True,
            max_pages=1,
        )
    )
