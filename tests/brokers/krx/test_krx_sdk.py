from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import httpx
import pytest

from modules.brokers.krx import Credentials, KrxApiError, KrxClient


def test_index_daily_prices_use_auth_header_and_parse_nullable_numbers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/svc/sample/apis/idx/kospi_dd_trd.json"
        assert request.url.params["basDd"] == "20200414"
        assert request.headers["AUTH_KEY"] == "sample-key"
        return httpx.Response(
            200,
            json={
                "OutBlock_1": [
                    {
                        "BAS_DD": "20200414",
                        "IDX_CLSS": "KOSPI",
                        "IDX_NM": "코스피 100",
                        "CLSPRC_IDX": "1901.46",
                        "CMPPREVDD_IDX": "30.20",
                        "FLUC_RT": "1.61",
                        "OPNPRC_IDX": "1893.22",
                        "HGPRC_IDX": "1909.54",
                        "LWPRC_IDX": "1880.47",
                        "ACC_TRDVOL": "96496189",
                        "ACC_TRDVAL": "4172518137834",
                        "MKTCAP": "995035040295400",
                    },
                    {
                        "BAS_DD": "20200414",
                        "IDX_CLSS": "KOSPI",
                        "IDX_NM": "코스피200제외 코스피지수",
                        "CLSPRC_IDX": "2183.24",
                        "CMPPREVDD_IDX": "41.38",
                        "FLUC_RT": "1.93",
                        "OPNPRC_IDX": "",
                        "HGPRC_IDX": "",
                        "LWPRC_IDX": "",
                        "ACC_TRDVOL": "",
                        "ACC_TRDVAL": "",
                        "MKTCAP": "",
                    },
                ]
            },
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with KrxClient(
            credentials=Credentials("sample-key"),
            http_client=http_client,
            use_sample_api=True,
        ) as client:
            prices = await client.indices.kospi_daily_prices(base_date=date(2020, 4, 14))
        await http_client.aclose()
        assert prices[0].base_date == date(2020, 4, 14)
        assert prices[0].close_index == Decimal("1901.46")
        assert prices[0].accumulated_volume == Decimal("96496189")
        assert prices[1].open_index is None
        assert prices[1].market_cap is None

    asyncio.run(run())


def test_index_daily_prices_default_to_production_api_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/svc/apis/idx/krx_dd_trd.json"
        assert request.url.params["basDd"] == "20200414"
        return httpx.Response(200, json={"OutBlock_1": []})

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with KrxClient(
            credentials=Credentials("auth-key"),
            http_client=http_client,
        ) as client:
            prices = await client.indices.daily_prices("krx", base_date="2020-04-14")
        await http_client.aclose()
        assert prices == ()

    asyncio.run(run())


def test_krx_error_payload_raises_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"respCode": "401", "respMsg": "Unauthorized API Call"},
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with KrxClient(
            credentials=Credentials("bad-key"),
            http_client=http_client,
        ) as client:
            with pytest.raises(KrxApiError) as exc_info:
                await client.indices.kosdaq_daily_prices(base_date="20200414")
        await http_client.aclose()
        assert exc_info.value.code == "401"
        assert exc_info.value.status_code == 200

    asyncio.run(run())


def test_invalid_index_series_raises_value_error() -> None:
    async def run() -> None:
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        )
        async with KrxClient(
            credentials=Credentials("auth-key"),
            http_client=http_client,
        ) as client:
            with pytest.raises(ValueError, match="series must be"):
                await client.indices.daily_prices(  # type: ignore[arg-type]
                    "bad", base_date="20200414"
                )
        await http_client.aclose()

    asyncio.run(run())
