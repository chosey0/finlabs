"""Domestic current-price API.

Accessed via `client.domestic.price`. Wraps `domestic.price.current`
EndpointSpec + `parse_domestic_current_price` for a one-line call:

    async with KisClient(credentials=...) as client:
        price = await client.domestic.price.current("005930")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from kis.endpoints.registry import lookup
from kis.models.quote import CurrentPrice
from kis.parsers.rest import output_dict, parse_domestic_current_price

if TYPE_CHECKING:
    from kis.client import KisClient

_SPEC = lookup("domestic.price.current")

DomesticMarketLabel = Literal["KOSPI", "KOSDAQ"]


class DomesticPriceAPI:
    """High-level domestic current-price client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def current(
        self,
        symbol: str,
        *,
        market: DomesticMarketLabel = "KOSPI",
        market_div: Literal["J", "NX", "UN"] = "J",
    ) -> CurrentPrice:
        """Fetch the current price for a domestic symbol.

        `market` is used only to label the returned `CurrentPrice`; the KIS
        endpoint itself uses `market_div` to switch between KRX (`J`),
        NXT (`NX`), and the integrated market (`UN`).
        """
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        payload = await self._parent.request(
            _SPEC,
            params={
                "FID_COND_MRKT_DIV_CODE": market_div,
                "FID_INPUT_ISCD": normalized,
            },
        )
        return parse_domestic_current_price(
            market=market,
            symbol=normalized,
            output=output_dict(payload),
        )
