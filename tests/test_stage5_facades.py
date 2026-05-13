from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx

from kis import (
    Credentials,
    KisClient,
    lookup,
    names,
    parse_domestic_volume_rank_item,
    parse_financial_summary,
    parse_investor_flow,
    parse_overseas_volume_surge_item,
    parse_product_info,
)


def test_stage5_endpoint_specs_are_registered() -> None:
    assert len(names()) >= 12
    assert lookup("domestic.symbol_info.product_info").tr_id_real == "CTPF1604R"
    assert lookup("domestic.rank.volume").tr_id_real == "FHPST01710000"
    assert lookup("domestic.analysis.investor_trade_by_stock_daily").tr_id_mock is None
    assert lookup("domestic.sector.inquire_daily_indexchartprice").tr_id_for("mock")
    assert lookup("overseas.analysis.volume_surge").tr_id_mock is None


def test_parse_product_info_from_document_shape() -> None:
    result = parse_product_info(
        market="KRX",
        symbol="005930",
        product_type="300",
        output={
            "pdno": "005930",
            "prdt_type_cd": "300",
            "prdt_name": "삼성전자",
            "prdt_eng_name": "Samsung Electronics",
            "std_pdno": "KR7005930003",
            "shtn_pdno": "005930",
        },
    )

    assert result.symbol == "005930"
    assert result.name == "삼성전자"
    assert result.english_name == "Samsung Electronics"
    assert result.standard_code == "KR7005930003"


def test_parse_financial_summary_from_document_shape() -> None:
    result = parse_financial_summary(
        market="KRX",
        symbol="005930",
        row={
            "stac_yymm": "202312",
            "sale_account": "258935494",
            "bsop_prfi": "6566976",
            "thtr_ntin": "15487100",
            "roe_val": "4.14",
            "lblt_rate": "25.36",
        },
    )

    assert result.fiscal_period == "202312"
    assert result.revenue == Decimal("258935494")
    assert result.operating_profit == Decimal("6566976")
    assert result.net_income == Decimal("15487100")
    assert result.roe == Decimal("4.14")
    assert result.debt_ratio == Decimal("25.36")


def test_parse_domestic_volume_rank_from_document_shape() -> None:
    result = parse_domestic_volume_rank_item(
        market="J",
        row={
            "data_rank": "1",
            "mksc_shrn_iscd": "005930",
            "hts_kor_isnm": "삼성전자",
            "stck_prpr": "70000",
            "prdy_vrss": "100",
            "prdy_ctrt": "0.14",
            "acml_vol": "1234567",
        },
    )

    assert result.rank == 1
    assert result.symbol == "005930"
    assert result.name == "삼성전자"
    assert result.volume == 1234567


def test_parse_investor_flow_from_document_shape() -> None:
    result = parse_investor_flow(
        market="KRX",
        symbol="005930",
        row={
            "stck_bsop_date": "20260507",
            "stck_clpr": "70000",
            "frgn_ntby_qty": "1000",
            "prsn_ntby_qty": "-500",
            "orgn_ntby_qty": "-500",
        },
    )

    assert result.date == "2026-05-07"
    assert result.close == Decimal("70000")
    assert result.foreign_net_buy_quantity == 1000
    assert result.individual_net_buy_quantity == -500
    assert result.institution_net_buy_quantity == -500


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


def test_client_domestic_product_info_uses_mock_transport() -> None:
    requests: list[httpx.Request] = []

    async def run():
        async with _client(_handler_for(requests)) as client:
            return await client.domestic.symbols.product_info("005930")

    result = asyncio.run(run())

    assert result.name == "삼성전자"
    assert requests[-1].url.path == "/uapi/domestic-stock/v1/quotations/search-info"
    assert requests[-1].url.params["PDNO"] == "005930"


def test_client_domestic_financial_summary_uses_mock_transport() -> None:
    requests: list[httpx.Request] = []

    async def run():
        async with _client(_handler_for(requests)) as client:
            return await client.domestic.symbols.financial_summary("005930")

    rows = asyncio.run(run())

    assert rows[0].fiscal_period == "202312"
    assert rows[0].roe == Decimal("4.14")
    assert requests[-1].url.path == "/uapi/domestic-stock/v1/finance/financial-ratio"


def test_client_domestic_rank_volume_uses_mock_transport() -> None:
    requests: list[httpx.Request] = []

    async def run():
        async with _client(_handler_for(requests)) as client:
            return await client.domestic.rank.volume("J", 1)

    rows = asyncio.run(run())

    assert len(rows) == 1
    assert rows[0].symbol == "005930"
    assert requests[-1].url.path == "/uapi/domestic-stock/v1/quotations/volume-rank"


def test_client_domestic_investor_flow_uses_mock_transport() -> None:
    requests: list[httpx.Request] = []

    async def run():
        async with _client(_handler_for(requests)) as client:
            return await client.domestic.analysis.investor_flow(
                "005930",
                start="2026-05-07",
                end="2026-05-07",
            )

    rows = asyncio.run(run())

    assert rows[0].date == "2026-05-07"
    assert rows[0].foreign_net_buy_quantity == 1000
    assert requests[-1].url.path.endswith("/investor-trade-by-stock-daily")


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
        if request.url.path.endswith("/search-info"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output": {
                        "pdno": "005930",
                        "prdt_type_cd": "300",
                        "prdt_name": "삼성전자",
                        "prdt_eng_name": "Samsung Electronics",
                        "std_pdno": "KR7005930003",
                        "shtn_pdno": "005930",
                    },
                },
            )
        if request.url.path.endswith("/financial-ratio"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output": [
                        {
                            "stac_yymm": "202312",
                            "sale_account": "258935494",
                            "bsop_prfi": "6566976",
                            "thtr_ntin": "15487100",
                            "roe_val": "4.14",
                            "lblt_rate": "25.36",
                        }
                    ],
                },
            )
        if request.url.path.endswith("/volume-rank"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output": [
                        {
                            "data_rank": "1",
                            "mksc_shrn_iscd": "005930",
                            "hts_kor_isnm": "삼성전자",
                            "stck_prpr": "70000",
                            "acml_vol": "1234567",
                        },
                        {
                            "data_rank": "2",
                            "mksc_shrn_iscd": "000660",
                            "hts_kor_isnm": "SK하이닉스",
                            "stck_prpr": "180000",
                            "acml_vol": "765432",
                        },
                    ],
                },
            )
        if request.url.path.endswith("/investor-trade-by-stock-daily"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output2": [
                        {
                            "stck_bsop_date": "20260507",
                            "stck_clpr": "70000",
                            "frgn_ntby_qty": "1000",
                            "prsn_ntby_qty": "-500",
                            "orgn_ntby_qty": "-500",
                        }
                    ],
                },
            )
        if request.url.path.endswith("/volume-surge"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output2": [
                        {
                            "excd": "NAS",
                            "symb": "AAPL",
                            "knam": "애플",
                            "last": "190.25",
                            "diff": "1.23",
                            "rate": "0.65",
                            "tvol": "987654",
                        },
                        {
                            "excd": "NAS",
                            "symb": "MSFT",
                            "knam": "마이크로소프트",
                            "last": "420.00",
                            "tvol": "1234",
                        },
                    ],
                },
            )
        return httpx.Response(404, json={"rt_cd": "1", "msg1": "not found"})

    return handler
