from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from modules.brokers.krx.models import IndexDailyPrice
from modules.brokers.krx.parsers import parse_index_daily_prices
from modules.brokers.krx.types import IndexSeries

if TYPE_CHECKING:
    from modules.brokers.krx.client import KrxClient

_INDEX_API_IDS: dict[IndexSeries, str] = {
    "kospi": "kospi_dd_trd",
    "kosdaq": "kosdaq_dd_trd",
    "krx": "krx_dd_trd",
}


class IndexAPI:
    def __init__(self, parent: "KrxClient") -> None:
        self._parent = parent

    async def daily_prices(
        self,
        series: IndexSeries,
        *,
        base_date: date | str,
    ) -> tuple[IndexDailyPrice, ...]:
        try:
            api_id = _INDEX_API_IDS[series]
        except KeyError as exc:
            raise ValueError("series must be 'kospi', 'kosdaq', or 'krx'") from exc
        payload = await self._parent.request(
            api_id,
            params={"basDd": _format_base_date(base_date)},
        )
        return parse_index_daily_prices(payload)

    async def kospi_daily_prices(
        self, *, base_date: date | str
    ) -> tuple[IndexDailyPrice, ...]:
        return await self.daily_prices("kospi", base_date=base_date)

    async def kosdaq_daily_prices(
        self, *, base_date: date | str
    ) -> tuple[IndexDailyPrice, ...]:
        return await self.daily_prices("kosdaq", base_date=base_date)

    async def krx_daily_prices(
        self, *, base_date: date | str
    ) -> tuple[IndexDailyPrice, ...]:
        return await self.daily_prices("krx", base_date=base_date)


def _format_base_date(value: date | str) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    compact = value.replace("-", "").strip()
    if len(compact) != 8 or not compact.isdigit():
        raise ValueError("base_date must be a date or YYYYMMDD string")
    return compact
