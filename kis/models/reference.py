from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class OverseasVolumeSurgeItem:
    exchange: str
    symbol: str
    name: str
    price: Decimal | None
    change: Decimal | None
    change_rate: Decimal | None
    volume: int | None
    raw: dict[str, Any] | None = None
