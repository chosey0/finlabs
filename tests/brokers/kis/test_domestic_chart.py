from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx

from modules.brokers.kis import (
    Credentials,
    KisClient,
    MockNotSupportedError,
    lookup,
    parse_domestic_minute_bar,
)


def test_domestic_minute_endpoint_spec_is_registered() -> None:
    spec = lookup("domestic.chart.minute")

    assert spec.path == "/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
    assert spec.tr_id_real == "FHKST03010230"
    assert spec.tr_id_mock is None
    try:
        spec.tr_id_for("mock")
    except MockNotSupportedError:
        pass
    else:
        raise AssertionError("expected MockNotSupportedError")


def test_parse_domestic_minute_bar_preserves_cumulative_amount_semantics() -> None:
    bar = parse_domestic_minute_bar(
        market="KRX",
        symbol="005930",
        row={
            "stck_bsop_date": "20241108",
            "stck_cntg_hour": "140000",
            "stck_prpr": "57300",
            "stck_oprc": "57300",
            "stck_hgpr": "57400",
            "stck_lwpr": "57200",
            "cntg_vol": "59047",
            "acml_tr_pbmn": "538940180600",
        },
    )

    assert bar.business_date == "2024-11-08"
    assert bar.time == "14:00:00"
    assert bar.close == Decimal("57300")
    assert bar.volume == 59047
    assert bar.cumulative_amount == Decimal("538940180600")


def test_domestic_minute_chart_paginates_backward_and_deduplicates_boundary() -> None:
    requests: list[httpx.Request] = []

    async def run():
        async with _client(_domestic_minute_handler(requests)) as client:
            return await client.domestic.chart.minute(
                "005930",
                date="2024-11-08",
                end_time="14:00:00",
                start_time="11:59:00",
            )

    bars = asyncio.run(run())

    assert [bar.time for bar in bars] == ["11:59:00", "12:00:00", "12:01:00", "13:59:00", "14:00:00"]
    assert len(requests) == 3  # OAuth + two chart pages
    assert requests[1].url.params["FID_INPUT_HOUR_1"] == "140000"
    assert requests[2].url.params["FID_INPUT_HOUR_1"] == "120100"
    assert requests[1].url.params["FID_INPUT_DATE_1"] == "20241108"
    assert requests[1].url.params["FID_PW_DATA_INCU_YN"] == "Y"


def _client(handler) -> KisClient:
    return KisClient(
        credentials=Credentials("app-key", "app-secret"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _domestic_minute_handler(requests: list[httpx.Request]):
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

        hour = request.url.params["FID_INPUT_HOUR_1"]
        if hour == "140000":
            rows = [
                _row("140000", "57300", "59047", "538940180600"),
                _row("135900", "57300", "118619", "535556648100"),
                _row("120100", "57700", "3856", "357875441100"),
            ]
        elif hour == "120100":
            rows = [
                _row("120100", "57700", "3856", "357875441100"),
                _row("120000", "57600", "4200", "357652980000"),
                _row("115900", "57500", "6100", "357411060000"),
            ]
        else:
            return httpx.Response(400, json={"rt_cd": "1", "msg1": "unexpected cursor"})

        return httpx.Response(200, json={"rt_cd": "0", "output1": {}, "output2": rows})

    return handler


def _row(time: str, price: str, volume: str, cumulative_amount: str) -> dict[str, str]:
    return {
        "stck_bsop_date": "20241108",
        "stck_cntg_hour": time,
        "stck_prpr": price,
        "stck_oprc": price,
        "stck_hgpr": price,
        "stck_lwpr": price,
        "cntg_vol": volume,
        "acml_tr_pbmn": cumulative_amount,
    }
