from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class IndexDailyPrice:
    base_date: date
    index_class: str
    index_name: str
    close_index: Decimal | None
    change: Decimal | None
    change_rate: Decimal | None
    open_index: Decimal | None
    high_index: Decimal | None
    low_index: Decimal | None
    accumulated_volume: Decimal | None
    accumulated_trading_value: Decimal | None
    market_cap: Decimal | None
    raw: dict[str, Any]
