from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from kis.endpoints.registry import lookup
from kis.models.reference import InvestorFlow
from kis.parsers.rest import (
    format_date,
    output_rows,
    parse_date,
    parse_investor_flow,
)

if TYPE_CHECKING:
    from kis.client import KisClient

_INVESTOR_FLOW_SPEC = lookup("domestic.analysis.investor_trade_by_stock_daily")


class DomesticAnalysisAPI:
    """High-level domestic analysis client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def investor_flow(
        self,
        symbol: str,
        start: str | date,
        end: str | date,
        *,
        market: str = "KRX",
        market_div: str = "J",
        adjusted: bool = True,
    ) -> list[InvestorFlow]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        start_date = _coerce_date(start)
        end_date = _coerce_date(end)
        if start_date > end_date:
            raise ValueError("start must be on or before end")
        payload = await self._parent.request(
            _INVESTOR_FLOW_SPEC,
            params={
                "FID_COND_MRKT_DIV_CODE": market_div,
                "FID_INPUT_ISCD": normalized,
                "FID_INPUT_DATE_1": format_date(start_date),
                "FID_ORG_ADJ_PRC": "0" if adjusted else "1",
                "FID_ETC_CLS_CODE": "",
            },
        )
        flows = [
            parse_investor_flow(market=market, symbol=normalized, row=row)
            for row in output_rows(payload)
        ]
        return [
            flow for flow in flows if start_date <= parse_date(flow.date) <= end_date
        ]


def _coerce_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return parse_date(value)
