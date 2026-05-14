from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx

from kis import (
    Credentials,
    KisClient,
    lookup,
    names,
    parse_overseas_volume_surge_item,
)


def test_stage5_overseas_endpoint_specs_are_registered() -> None:
    assert len(names()) >= 20
    assert not any(name.startswith("domestic.") for name in names())
    assert lookup("overseas.analysis.volume_surge").tr_id_mock is None


def test_parse_overseas_volume_surge_from_document_shape() -> None:
    result = parse_overseas_volume_surge_item(
        exchange="NAS",
        row={
            "excd": "NAS",
            "symb": "AAPL",
            "knam": "애플",
            "last": "190.25",
            "diff": "1.23",
            "rate": "0.65",
            "tvol": "987654",
        },
    )

    assert result.exchange == "NAS"
    assert result.symbol == "AAPL"
    assert result.name == "애플"
    assert result.price == Decimal("190.25")
    assert result.volume == 987654


def test_client_overseas_volume_surge_uses_mock_transport() -> None:
    requests: list[httpx.Request] = []

    async def run():
        async with _client(_handler_for(requests)) as client:
            return await client.overseas.analysis.volume_surge("NAS", 1)

    rows = asyncio.run(run())

    assert len(rows) == 1
    assert rows[0].symbol == "AAPL"
    assert rows[0].price == Decimal("190.25")
    assert requests[-1].url.path == "/uapi/overseas-stock/v1/ranking/volume-surge"


def _client(handler) -> KisClient:
    return KisClient(
        credentials=Credentials("app-key", "app-secret"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _handler_for(requests: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "token_type": "Bearer",
                    "expires_in": 86400,
                },
            )
        if request.url.path.endswith("/volume-surge"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output": [
                        {
                            "excd": "NAS",
                            "symb": "AAPL",
                            "knam": "애플",
                            "last": "190.25",
                            "diff": "1.23",
                            "rate": "0.65",
                            "tvol": "987654",
                        }
                    ],
                },
            )
        return httpx.Response(404, json={"rt_cd": "1", "msg1": "unexpected"})

    return handler
