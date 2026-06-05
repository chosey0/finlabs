"""Overseas current-price API.

Accessed via `client.overseas.price`. The KIS overseas quote endpoint
keys on the `EXCD` (exchange) + `SYMB` pair, so callers must supply
`exchange`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from modules.brokers.kis.endpoints.registry import lookup
from modules.brokers.kis.models.quote import CurrentPrice
from modules.brokers.kis.parsers.rest import output_dict, parse_overseas_current_price

if TYPE_CHECKING:
    from modules.brokers.kis.client import KisClient

_SPEC = lookup("overseas.price.current")

OverseasExchangeCode = Literal[
    "NAS", "NYS", "AMS", "HKS", "TSE", "SHS", "SZS", "HNX", "HSX"
]


class OverseasPriceAPI:
    """High-level overseas current-price client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def current(
        self,
        symbol: str,
        *,
        exchange: OverseasExchangeCode,
        market: str | None = None,
    ) -> CurrentPrice:
        """Fetch the current price for an overseas symbol.

        `exchange` is the 3-letter KIS exchange code (e.g. `NAS`). `market`
        labels the result; when omitted the exchange code is used.
        """
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        normalized_exchange = exchange.strip().upper()
        payload = await self._parent.request(
            _SPEC,
            params={
                "AUTH": "",
                "EXCD": normalized_exchange,
                "SYMB": normalized_symbol,
            },
        )
        return parse_overseas_current_price(
            market=market or normalized_exchange,
            symbol=normalized_symbol,
            output=output_dict(payload),
        )
