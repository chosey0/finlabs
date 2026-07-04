from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from modules.brokers.kiwoom._internal.http import HttpResponse
from modules.brokers.kiwoom.domestic.industry import DomesticIndustryAPI


def test_all_industry_index_uses_ka20003_contract_and_parses_rows() -> None:
    parent = _IndustryParent(
        [
            _response(
                [
                    {
                        "stk_cd": "001",
                        "stk_nm": "KOSPI",
                        "cur_prc": "+278912",
                        "pre_sig": "2",
                        "pred_pre": "+1234",
                        "flu_rt": "+0.44",
                        "trde_qty": "123,456",
                        "wght": "+100.00",
                        "trde_prica": "987,654",
                        "upl": "1",
                        "rising": "500",
                        "stdns": "20",
                        "fall": "400",
                        "lst": "0",
                        "flo_stk_num": "921",
                    }
                ]
            )
        ]
    )

    rows = asyncio.run(DomesticIndustryAPI(parent).all_index("001"))

    assert parent.api_id == "ka20003"
    assert parent.path == "/api/dostk/sect"
    assert parent.json_bodies == [{"inds_cd": "001"}]
    assert len(rows) == 1
    row = rows[0]
    assert row.request_industry_code == "001"
    assert row.industry_code == "001"
    assert row.name == "KOSPI"
    assert row.current_price == Decimal("+278912")
    assert row.change_signal == "2"
    assert row.change == Decimal("+1234")
    assert row.change_rate == Decimal("+0.44")
    assert row.volume_thousands == 123456
    assert row.weight == Decimal("+100.00")
    assert row.amount_million == 987654
    assert row.limit_up_count == 1
    assert row.rising_count == 500
    assert row.unchanged_count == 20
    assert row.falling_count == 400
    assert row.limit_down_count == 0
    assert row.listed_count == 921
    assert row.raw["stk_nm"] == "KOSPI"


def test_all_industry_index_follows_continuation_headers() -> None:
    parent = _IndustryParent(
        [
            _response(
                [{"stk_cd": "001", "stk_nm": "KOSPI"}],
                headers={"cont-yn": "Y", "next-key": "page-2"},
            ),
            _response([{"stk_cd": "002", "stk_nm": "Large Cap"}]),
        ]
    )

    rows = asyncio.run(DomesticIndustryAPI(parent).all_index("001"))

    assert [row.industry_code for row in rows] == ["001", "002"]
    assert parent.continuations == [("N", ""), ("Y", "page-2")]


def test_all_industry_index_rejects_empty_industry_code() -> None:
    with pytest.raises(ValueError, match="industry_code must not be empty"):
        asyncio.run(DomesticIndustryAPI(_IndustryParent([])).all_index(" "))


def test_all_industry_index_rejects_invalid_max_pages() -> None:
    with pytest.raises(ValueError, match="max_pages must be at least 1"):
        asyncio.run(DomesticIndustryAPI(_IndustryParent([])).all_index("001", max_pages=0))


def test_industry_code_list_uses_ka10101_contract_and_parses_rows() -> None:
    parent = _IndustryParent(
        [
            _response(
                [{"marketCode": "0", "code": "001", "name": "KOSPI", "group": "1"}],
                key="list",
            )
        ]
    )

    rows = asyncio.run(DomesticIndustryAPI(parent).code_list("0"))

    assert parent.api_id == "ka10101"
    assert parent.path == "/api/dostk/stkinfo"
    assert parent.json_bodies == [{"mrkt_tp": "0"}]
    assert len(rows) == 1
    row = rows[0]
    assert row.request_market_type == "0"
    assert row.market_code == "0"
    assert row.code == "001"
    assert row.name == "KOSPI"
    assert row.group == "1"
    assert row.raw["name"] == "KOSPI"


def test_industry_code_list_follows_continuation_headers() -> None:
    parent = _IndustryParent(
        [
            _response(
                [{"marketCode": "0", "code": "001", "name": "KOSPI"}],
                key="list",
                headers={"cont-yn": "Y", "next-key": "page-2"},
            ),
            _response(
                [{"marketCode": "0", "code": "002", "name": "Large Cap"}],
                key="list",
            ),
        ]
    )

    rows = asyncio.run(DomesticIndustryAPI(parent).code_list("0"))

    assert [row.code for row in rows] == ["001", "002"]
    assert parent.continuations == [("N", ""), ("Y", "page-2")]


def test_industry_code_list_rejects_unknown_market_type() -> None:
    with pytest.raises(ValueError, match="market_type must be one of: 0, 1, 2, 4, 7"):
        asyncio.run(DomesticIndustryAPI(_IndustryParent([])).code_list("9"))


def test_industry_code_list_rejects_invalid_max_pages() -> None:
    with pytest.raises(ValueError, match="max_pages must be at least 1"):
        asyncio.run(DomesticIndustryAPI(_IndustryParent([])).code_list("0", max_pages=0))


class _IndustryParent:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls = 0
        self.api_id = ""
        self.path = ""
        self.json_bodies: list[dict[str, str]] = []
        self.continuations: list[tuple[str, str]] = []

    async def request_raw(self, spec, *args, **kwargs) -> HttpResponse:
        self.api_id = spec.api_id
        self.path = spec.path
        self.json_bodies.append(kwargs["json_body"])
        self.continuations.append((kwargs["cont_yn"], kwargs["next_key"]))
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _response(
    rows: list[dict[str, str]],
    *,
    key: str = "all_inds_idex",
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    return HttpResponse(
        payload={
            "return_code": "0",
            key: rows,
        },
        headers=headers or {},
        status_code=200,
    )
