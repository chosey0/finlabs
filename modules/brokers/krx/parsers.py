from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from modules.brokers.krx.models import IndexDailyPrice


def parse_index_daily_prices(payload: dict[str, Any]) -> tuple[IndexDailyPrice, ...]:
    rows = payload.get("OutBlock_1")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("response OutBlock_1 must be a list of objects")
    return tuple(parse_index_daily_price(row) for row in rows)


def parse_index_daily_price(row: dict[str, Any]) -> IndexDailyPrice:
    return IndexDailyPrice(
        base_date=_required_yyyymmdd(row, "BAS_DD"),
        index_class=_required_text(row, "IDX_CLSS"),
        index_name=_required_text(row, "IDX_NM"),
        close_index=_optional_decimal(row.get("CLSPRC_IDX")),
        change=_optional_decimal(row.get("CMPPREVDD_IDX")),
        change_rate=_optional_decimal(row.get("FLUC_RT")),
        open_index=_optional_decimal(row.get("OPNPRC_IDX")),
        high_index=_optional_decimal(row.get("HGPRC_IDX")),
        low_index=_optional_decimal(row.get("LWPRC_IDX")),
        accumulated_volume=_optional_decimal(row.get("ACC_TRDVOL")),
        accumulated_trading_value=_optional_decimal(row.get("ACC_TRDVAL")),
        market_cap=_optional_decimal(row.get("MKTCAP")),
        raw=dict(row),
    )


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid {key}")
    return value.strip()


def _required_yyyymmdd(row: dict[str, Any], key: str) -> date:
    value = _required_text(row, key)
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"missing or invalid {key}")
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in {"", "-"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc
