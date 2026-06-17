from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from modules.brokers.kiwoom.models.ohlcv import ChartBar

_CHART_ROW_KEYS: dict[str, str] = {
    "tick": "stk_tic_chart_qry",
    "minute": "stk_min_pole_chart_qry",
    "daily": "stk_dt_pole_chart_qry",
    "weekly": "stk_stk_pole_chart_qry",
    "monthly": "stk_mth_pole_chart_qry",
    "yearly": "stk_yr_pole_chart_qry",
}


def chart_rows(payload: dict[str, Any], chart_type: str) -> list[dict[str, Any]]:
    try:
        key = _CHART_ROW_KEYS[chart_type]
    except KeyError as exc:
        allowed = ", ".join(sorted(_CHART_ROW_KEYS))
        raise ValueError(f"chart_type must be one of: {allowed}") from exc
    rows = payload.get(key)
    if rows is None:
        return []
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    raise ValueError(f"Kiwoom response field {key} was not a list")


def parse_chart_bar(
    *,
    market: str,
    symbol: str,
    interval: str,
    row: dict[str, Any],
) -> ChartBar:
    return ChartBar(
        market=market,
        symbol=symbol,
        interval=interval,
        timestamp=timestamp_value(row),
        open=required_price(row, "open_pric"),
        high=required_price(row, "high_pric"),
        low=required_price(row, "low_pric"),
        close=required_price(row, "cur_prc"),
        volume=required_abs_int(row, "trde_qty"),
        amount=optional_decimal(row, "trde_prica"),
        change=optional_decimal(row, "pred_pre"),
        change_signal=str_or_none(row.get("pred_pre_sig")),
        turnover_rate=optional_decimal(row, "trde_tern_rt"),
        raw=row,
    )


def parse_date(value: str) -> date:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return date.fromisoformat(text)


def format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def timestamp_value(row: dict[str, Any]) -> str:
    datetime_text = str(row.get("cntr_tm") or "").strip()
    if datetime_text:
        return parse_chart_datetime(datetime_text)
    date_text = str(row.get("dt") or "").strip()
    if date_text:
        return parse_date(date_text).isoformat()
    raise ValueError("missing Kiwoom chart timestamp field")


def parse_chart_datetime(value: str) -> str:
    text = value.strip()
    formats = ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
    for datetime_format in formats:
        try:
            return datetime.strptime(text, datetime_format).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    raise ValueError(f"invalid Kiwoom chart datetime: {value}")


def required_price(row: dict[str, Any], *keys: str) -> Decimal:
    return abs(required_decimal(row, *keys))


def required_abs_int(row: dict[str, Any], *keys: str) -> int:
    return abs(int(required_decimal(row, *keys)))


def required_decimal(row: dict[str, Any], *keys: str) -> Decimal:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip().replace(",", "")
        if not text:
            continue
        try:
            return Decimal(text)
        except InvalidOperation:
            continue
    raise ValueError(f"missing numeric field; expected one of: {', '.join(keys)}")


def optional_decimal(row: dict[str, Any], *keys: str) -> Decimal | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip().replace(",", "")
        if not text:
            continue
        try:
            return Decimal(text)
        except InvalidOperation:
            continue
    return None


def str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
