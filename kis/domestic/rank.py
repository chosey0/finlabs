from __future__ import annotations

from typing import TYPE_CHECKING

from kis.endpoints.registry import lookup
from kis.models.reference import DomesticVolumeRankItem
from kis.parsers.rest import output_rows, parse_domestic_volume_rank_item

if TYPE_CHECKING:
    from kis.client import KisClient

_VOLUME_SPEC = lookup("domestic.rank.volume")


class DomesticRankAPI:
    """High-level domestic ranking client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def volume(
        self,
        market_code: str,
        count: int,
        *,
        market: str | None = None,
    ) -> list[DomesticVolumeRankItem]:
        if count < 1:
            raise ValueError("count must be at least 1")
        normalized_market = market_code.strip().upper()
        if not normalized_market:
            raise ValueError("market_code must not be empty")
        payload = await self._parent.request(
            _VOLUME_SPEC,
            params={
                "FID_COND_SCR_DIV_CODE": "20171",
                "FID_INPUT_ISCD": normalized_market,
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",
                "FID_TRGT_CLS_CODE": "111111111",
                "FID_TRGT_EXLS_CLS_CODE": "000000",
                "FID_INPUT_PRICE_1": "",
                "FID_INPUT_PRICE_2": "",
                "FID_VOL_CNT": "",
            },
        )
        market_label = market or normalized_market
        return [
            parse_domestic_volume_rank_item(market=market_label, row=row)
            for row in output_rows(payload)
        ][:count]
