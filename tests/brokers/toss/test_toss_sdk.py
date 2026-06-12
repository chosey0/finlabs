from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from modules.brokers.toss import (
    Credentials,
    TossApiError,
    TossAuthError,
    TossClient,
    mask_sensitive_message,
)


def test_prices_reuse_cached_token_and_parse_decimals() -> None:
    token_calls = 0
    price_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, price_calls
        if request.url.path == "/oauth2/token":
            token_calls += 1
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(
                200,
                json={
                    "access_token": "token-value",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        assert request.url.path == "/api/v1/prices"
        assert request.headers["authorization"] == "Bearer token-value"
        assert request.url.params["symbols"] == "005930,AAPL"
        price_calls += 1
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "symbol": "005930",
                        "timestamp": "2026-03-25T09:30:00.123+09:00",
                        "lastPrice": "72000",
                        "currency": "KRW",
                    },
                    {
                        "symbol": "AAPL",
                        "timestamp": None,
                        "lastPrice": "185.70",
                        "currency": "USD",
                    },
                ]
            },
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with TossClient(
            credentials=Credentials("client-id", "client-secret"),
            http_client=http_client,
        ) as client:
            first = await client.market.prices(["005930", "aapl"])
            second = await client.market.prices("005930,AAPL")
        await http_client.aclose()
        assert first == second
        assert first[0].last_price == Decimal("72000")
        assert first[1].timestamp is None

    asyncio.run(run())
    assert token_calls == 1
    assert price_calls == 2


def test_candles_parse_page_and_send_pagination_parameters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600},
            )
        assert request.url.params["symbol"] == "AAPL"
        assert request.url.params["interval"] == "1d"
        assert request.url.params["count"] == "2"
        assert request.url.params["adjusted"] == "true"
        assert request.url.params["before"] == "2026-03-25T09:00:00+09:00"
        return httpx.Response(
            200,
            json={
                "result": {
                    "candles": [
                        {
                            "timestamp": "2026-03-24T09:00:00+09:00",
                            "openPrice": "180",
                            "highPrice": "190",
                            "lowPrice": "179",
                            "closePrice": "188",
                            "volume": "1000",
                            "currency": "USD",
                        }
                    ],
                    "nextBefore": "2026-03-24T09:00:00+09:00",
                }
            },
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with TossClient(
            credentials=Credentials("client-id", "client-secret"),
            http_client=http_client,
        ) as client:
            page = await client.market.candles(
                "aapl",
                interval="1d",
                count=2,
                before=datetime(2026, 3, 25, 9, tzinfo=timezone(timedelta(hours=9))),
            )
        await http_client.aclose()
        assert page.candles[0].symbol == "AAPL"
        assert page.candles[0].close_price == Decimal("188")
        assert page.next_before is not None

    asyncio.run(run())


def test_stocks_parse_domestic_market_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600},
            )
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "symbol": "005930",
                        "name": "Samsung Electronics",
                        "englishName": "SamsungElec",
                        "isinCode": "KR7005930003",
                        "market": "KOSPI",
                        "securityType": "STOCK",
                        "isCommonShare": True,
                        "status": "ACTIVE",
                        "currency": "KRW",
                        "listDate": "1975-06-11",
                        "delistDate": None,
                        "sharesOutstanding": "5919637922",
                        "leverageFactor": None,
                        "koreanMarketDetail": {
                            "liquidationTrading": False,
                            "nxtSupported": True,
                            "krxTradingSuspended": False,
                            "nxtTradingSuspended": None,
                        },
                    }
                ]
            },
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with TossClient(
            credentials=Credentials("client-id", "client-secret"),
            http_client=http_client,
        ) as client:
            stocks = await client.stocks.get("005930")
        await http_client.aclose()
        assert stocks[0].shares_outstanding == Decimal("5919637922")
        assert stocks[0].korean_market_detail is not None
        assert stocks[0].korean_market_detail.nxt_supported is True

    asyncio.run(run())


def test_error_envelope_is_exposed_without_losing_request_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600},
            )
        return httpx.Response(
            404,
            headers={"X-Request-Id": "request-123"},
            json={
                "error": {
                    "requestId": "request-123",
                    "code": "stock-not-found",
                    "message": "not found",
                    "data": {"field": "symbols"},
                }
            },
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with TossClient(
            credentials=Credentials("client-id", "client-secret"),
            http_client=http_client,
        ) as client:
            with pytest.raises(TossApiError) as captured:
                await client.market.prices("MISSING")
        await http_client.aclose()
        assert captured.value.status_code == 404
        assert captured.value.code == "stock-not-found"
        assert captured.value.request_id == "request-123"

    asyncio.run(run())


def test_client_requires_async_context() -> None:
    client = TossClient(credentials=Credentials("client-id", "client-secret"))
    with pytest.raises(RuntimeError, match="async context manager"):
        asyncio.run(client.market.prices("AAPL"))


@pytest.mark.parametrize("count", [0, 201])
def test_candle_count_validation(count: int) -> None:
    client = TossClient(credentials=Credentials("client-id", "client-secret"))
    with pytest.raises(ValueError, match="between 1 and 200"):
        asyncio.run(client.market.candles("AAPL", interval="1d", count=count))


def test_auth_error_message_masks_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth2/token"
        return httpx.Response(
            400,
            json={
                "error": "invalid_client",
                "error_description": "bad client_secret: super-secret-value",
            },
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with TossClient(
            credentials=Credentials("client-id", "super-secret-value"),
            http_client=http_client,
        ) as client:
            with pytest.raises(TossAuthError) as captured:
                await client.market.prices("AAPL")
        await http_client.aclose()
        assert "super-secret-value" not in str(captured.value)
        assert "client_secret: ********" in str(captured.value)

    asyncio.run(run())


def test_mask_sensitive_message_covers_token_and_secret() -> None:
    message = "client_secret=abcd1234efgh access_token: tok.en-value_123 other=x"
    masked = mask_sensitive_message(message)
    assert "abcd1234efgh" not in masked
    assert "tok.en-value_123" not in masked
    assert "other=x" in masked
