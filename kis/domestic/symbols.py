from __future__ import annotations

from typing import TYPE_CHECKING

from kis.endpoints.registry import lookup
from kis.models.reference import FinancialSummary, ProductInfo
from kis.parsers.rest import (
    output_dict,
    output_rows,
    parse_financial_summary,
    parse_product_info,
)

if TYPE_CHECKING:
    from kis.client import KisClient

_PRODUCT_SPEC = lookup("domestic.symbol_info.product_info")
_FINANCIAL_RATIO_SPEC = lookup("domestic.symbol_info.financial_ratio")


class DomesticSymbolsAPI:
    """High-level domestic symbol and financial metadata client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def product_info(
        self,
        symbol: str,
        *,
        product_type: str = "300",
        market: str = "KRX",
    ) -> ProductInfo:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        payload = await self._parent.request(
            _PRODUCT_SPEC,
            params={"PDNO": normalized, "PRDT_TYPE_CD": product_type},
        )
        return parse_product_info(
            market=market,
            symbol=normalized,
            product_type=product_type,
            output=output_dict(payload),
        )

    async def financial_summary(
        self,
        symbol: str,
        *,
        market: str = "KRX",
        market_div: str = "J",
    ) -> list[FinancialSummary]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        payload = await self._parent.request(
            _FINANCIAL_RATIO_SPEC,
            params={
                "fid_cond_mrkt_div_code": market_div,
                "fid_input_iscd": normalized,
            },
        )
        return [
            parse_financial_summary(market=market, symbol=normalized, row=row)
            for row in output_rows(payload)
        ]
