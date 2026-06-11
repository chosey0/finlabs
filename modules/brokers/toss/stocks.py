from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from modules.brokers.toss.market import normalize_symbols
from modules.brokers.toss.models import StockInfo
from modules.brokers.toss.parsers import parse_stock_info, result_list

if TYPE_CHECKING:
    from modules.brokers.toss.client import TossClient


class StocksAPI:
    def __init__(self, parent: "TossClient") -> None:
        self._parent = parent

    async def get(self, symbols: str | Iterable[str]) -> tuple[StockInfo, ...]:
        normalized = normalize_symbols(symbols)
        payload = await self._parent.request(
            "GET", "/api/v1/stocks", params={"symbols": ",".join(normalized)}
        )
        return tuple(parse_stock_info(row) for row in result_list(payload))
