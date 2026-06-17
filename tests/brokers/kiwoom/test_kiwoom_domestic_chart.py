from __future__ import annotations

import asyncio

import pytest

from modules.brokers.kiwoom._internal.http import HttpResponse
from modules.brokers.kiwoom.domestic.chart import DomesticChartAPI
from modules.brokers.kiwoom.exceptions import KiwoomApiError


def test_domestic_chart_retries_rate_limit_error(monkeypatch) -> None:
    sleeps: list[float] = []
    parent = _RetryOnceParent()

    async def fake_sleep(delay_seconds: float) -> None:
        sleeps.append(delay_seconds)

    monkeypatch.setattr(
        "modules.brokers.kiwoom.domestic.chart.asyncio.sleep", fake_sleep
    )

    bars = asyncio.run(DomesticChartAPI(parent).minute("005930", max_pages=1))

    assert parent.calls == 2
    assert sleeps == [1.0]
    assert len(bars) == 1
    assert bars[0].timestamp == "2026-06-17 09:30:00"


def test_domestic_chart_does_not_retry_non_rate_limit_error(monkeypatch) -> None:
    sleeps: list[float] = []
    parent = _AlwaysFailsParent()

    async def fake_sleep(delay_seconds: float) -> None:
        sleeps.append(delay_seconds)

    monkeypatch.setattr(
        "modules.brokers.kiwoom.domestic.chart.asyncio.sleep", fake_sleep
    )

    with pytest.raises(KiwoomApiError, match="bad request"):
        asyncio.run(DomesticChartAPI(parent).minute("005930", max_pages=1))

    assert parent.calls == 1
    assert sleeps == []


def test_domestic_minute_chart_stops_when_start_datetime_is_reached() -> None:
    parent = _PagedMinuteParent()

    bars = asyncio.run(
        DomesticChartAPI(parent).minute(
            "005930",
            base_date="2026-06-17",
            start_date="2026-06-17 093000",
        )
    )

    assert parent.calls == 2
    assert [bar.timestamp for bar in bars] == [
        "2026-06-17 09:30:00",
        "2026-06-17 09:31:00",
        "2026-06-17 09:32:00",
    ]


def test_domestic_monthly_chart_accepts_year_month_start_and_base_date() -> None:
    parent = _MonthlyParent()

    bars = asyncio.run(
        DomesticChartAPI(parent).monthly(
            "005930",
            base_date="2026-06",
            start_date="2026-04",
        )
    )

    assert parent.json_body["base_dt"] == "20260630"
    assert [bar.timestamp for bar in bars] == [
        "2026-04-01",
        "2026-05-01",
        "2026-06-01",
    ]


def test_domestic_yearly_chart_accepts_year_start_and_base_date() -> None:
    parent = _YearlyParent()

    bars = asyncio.run(
        DomesticChartAPI(parent).yearly(
            "005930",
            base_date="2026",
            start_date="2024",
        )
    )

    assert parent.json_body["base_dt"] == "20261231"
    assert [bar.timestamp for bar in bars] == [
        "2024-01-01",
        "2025-01-01",
        "2026-01-01",
    ]


class _RetryOnceParent:
    def __init__(self) -> None:
        self.calls = 0

    async def request_raw(self, *args, **kwargs) -> HttpResponse:
        self.calls += 1
        if self.calls == 1:
            raise KiwoomApiError(
                "허용된 요청 개수를 초과하였습니다",
                return_code="1700",
                return_msg="허용된 요청 개수를 초과하였습니다. API ID=ka10080",
            )
        return _minute_response()


class _AlwaysFailsParent:
    def __init__(self) -> None:
        self.calls = 0

    async def request_raw(self, *args, **kwargs) -> HttpResponse:
        self.calls += 1
        raise KiwoomApiError("bad request", return_code="9999")


class _PagedMinuteParent:
    def __init__(self) -> None:
        self.calls = 0

    async def request_raw(self, *args, **kwargs) -> HttpResponse:
        self.calls += 1
        if self.calls == 1:
            return _minute_response(
                rows=[
                    _row("20260617093200"),
                    _row("20260617093100"),
                ],
                headers={"cont-yn": "Y", "next-key": "page-2"},
            )
        return _minute_response(
            rows=[
                _row("20260617093000"),
                _row("20260617092900"),
            ],
            headers={"cont-yn": "Y", "next-key": "page-3"},
        )


class _MonthlyParent:
    def __init__(self) -> None:
        self.json_body = {}

    async def request_raw(self, *args, **kwargs) -> HttpResponse:
        self.json_body = kwargs["json_body"]
        return _chart_response(
            key="stk_mth_pole_chart_qry",
            rows=[
                _row("20260601", key="dt"),
                _row("20260501", key="dt"),
                _row("20260401", key="dt"),
                _row("20260301", key="dt"),
            ],
        )


class _YearlyParent:
    def __init__(self) -> None:
        self.json_body = {}

    async def request_raw(self, *args, **kwargs) -> HttpResponse:
        self.json_body = kwargs["json_body"]
        return _chart_response(
            key="stk_yr_pole_chart_qry",
            rows=[
                _row("20260101", key="dt"),
                _row("20250101", key="dt"),
                _row("20240101", key="dt"),
                _row("20230101", key="dt"),
            ],
        )


def _minute_response(
    *,
    rows: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    return _chart_response(
        key="stk_min_pole_chart_qry",
        rows=rows or [_row("20260617093000")],
        headers=headers,
    )


def _chart_response(
    *,
    key: str,
    rows: list[dict[str, str]],
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


def _row(value: str, *, key: str = "cntr_tm") -> dict[str, str]:
    return {
        key: value,
        "open_pric": "100",
        "high_pric": "110",
        "low_pric": "90",
        "cur_prc": "105",
        "trde_qty": "1000",
    }
