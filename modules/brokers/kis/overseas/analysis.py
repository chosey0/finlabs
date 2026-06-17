from __future__ import annotations

from typing import TYPE_CHECKING

from modules.brokers.kis.endpoints.registry import lookup
from modules.brokers.kis.models.reference import OverseasVolumeSurgeItem
from modules.brokers.kis.overseas.exchange import normalize_overseas_exchange
from modules.brokers.kis.parsers.rest import output_rows, parse_overseas_volume_surge_item

if TYPE_CHECKING:
    from modules.brokers.kis.client import KisClient

_VOLUME_SURGE_SPEC = lookup("overseas.analysis.volume_surge")


class OverseasAnalysisAPI:
    """High-level overseas analysis client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def volume_surge(
        self,
        exchange: str,
        count: int,
        *,
        minutes: int = 0,
        volume_range: str = "0",
    ) -> list[OverseasVolumeSurgeItem]:
        if count < 1:
            raise ValueError("count must be at least 1")
        normalized_exchange = normalize_overseas_exchange(exchange)
        payload = await self._parent.request(
            _VOLUME_SURGE_SPEC,
            params={
                "AUTH": "",
                "EXCD": normalized_exchange,
                "MINX": str(minutes),
                "VOL_RANG": volume_range,
            },
        )
        return [
            parse_overseas_volume_surge_item(exchange=normalized_exchange, row=row)
            for row in output_rows(payload)
        ][:count]
