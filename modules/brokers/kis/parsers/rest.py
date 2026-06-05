from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from modules.brokers.kis.models.ohlcv import OhlcvBar, OverseasMinuteBar
from modules.brokers.kis.models.quote import CurrentPrice
from modules.brokers.kis.models.reference import OverseasVolumeSurgeItem


def output_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the `output` object from a KIS REST response."""
    output = payload.get("output")
    if not isinstance(output, dict):
        raise ValueError("KIS response did not include output object")
    return output


def output_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return list-shaped output rows for endpoints like daily chart/OHLCV.

    KIS uses `output2` for paginated rows on some endpoints and `output`
    on others. Both shapes (single dict or list) are flattened to a list.
    """
    if "output2" in payload:
        output = payload["output2"]
    else:
        output = payload.get("output")
    if output is None:
        return []
    if isinstance(output, dict):
        return [output]
    if isinstance(output, list):
        return [row for row in output if isinstance(row, dict)]
    raise ValueError("KIS response output rows had an unsupported shape")


def parse_overseas_current_price(
    *,
    market: str,
    symbol: str,
    output: dict[str, Any],
) -> CurrentPrice:
    return CurrentPrice(
        market=market,
        symbol=symbol,
        name=str(
            output.get("name") or output.get("ename") or output.get("e_name") or ""
        ),
        price=decimal_or_none(output.get("last")),
        currency=str(output.get("curr") or output.get("currency") or ""),
        change=decimal_or_none(output.get("diff") or output.get("t_xdif")),
        change_rate=decimal_or_none(output.get("rate") or output.get("t_rate")),
        open=decimal_or_none(output.get("open")),
        high=decimal_or_none(output.get("high")),
        low=decimal_or_none(output.get("low")),
        volume=int_or_none(output.get("tvol") or output.get("volume")),
        raw=output,
    )


def parse_overseas_ohlcv_bar(
    *,
    market: str,
    symbol: str,
    interval: str,
    row: dict[str, Any],
) -> OhlcvBar:
    return OhlcvBar(
        market=market,
        symbol=symbol,
        interval=interval,
        timestamp=date_value(row, "xymd", "date", "stck_bsop_date"),
        open=required_decimal(row, "open", "ovrs_nmix_oprc"),
        high=required_decimal(row, "high", "ovrs_nmix_hgpr"),
        low=required_decimal(row, "low", "ovrs_nmix_lwpr"),
        close=required_decimal(row, "clos", "close", "ovrs_nmix_prpr"),
        volume=required_int(row, "tvol", "volume", "acml_vol"),
        change=optional_decimal(row, "diff", "ovrs_nmix_prdy_vrss"),
        change_rate=optional_decimal(row, "rate", "prdy_ctrt"),
        amount=optional_decimal(row, "tamt"),
        raw=row,
    )


def parse_overseas_minute_bar(
    *,
    market: str,
    symbol: str,
    interval_minutes: int,
    row: dict[str, Any],
) -> OverseasMinuteBar:
    return OverseasMinuteBar(
        market=market,
        symbol=symbol,
        interval_minutes=interval_minutes,
        local_business_date=date_value(row, "tymd"),
        local_date=date_value(row, "xymd"),
        local_time=time_value(row, "xhms"),
        korea_date=date_value(row, "kymd"),
        korea_time=time_value(row, "khms"),
        open=required_decimal(row, "open"),
        high=required_decimal(row, "high"),
        low=required_decimal(row, "low"),
        close=required_decimal(row, "last"),
        volume=required_int(row, "evol"),
        amount=required_decimal(row, "eamt"),
        raw=row,
    )


def parse_overseas_volume_surge_item(
    *,
    exchange: str,
    row: dict[str, Any],
) -> OverseasVolumeSurgeItem:
    return OverseasVolumeSurgeItem(
        exchange=str(row.get("excd") or exchange),
        symbol=str(row.get("symb") or ""),
        name=str(row.get("knam") or row.get("enam") or ""),
        price=decimal_or_none(row.get("last")),
        change=decimal_or_none(row.get("diff")),
        change_rate=decimal_or_none(row.get("rate")),
        volume=int_or_none(row.get("tvol")),
        raw=row,
    )


def parse_minute_datetime(value: str) -> datetime:
    text = value.strip().replace("T", " ")
    if not text:
        raise ValueError("start must not be empty")
    formats = (
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    )
    for datetime_format in formats:
        try:
            return datetime.strptime(text, datetime_format)
        except ValueError:
            continue
    raise ValueError(
        "start must be a datetime like YYYY-MM-DD HH:MM[:SS] or YYYYMMDDHHMMSS"
    )


def parse_date(value: str) -> date:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return date.fromisoformat(text)


def format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def date_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return parse_date(value).isoformat()
    raise ValueError(f"missing date field; expected one of: {', '.join(keys)}")


def time_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        digits = value.zfill(6)
        if len(digits) == 6 and digits.isdigit():
            return f"{digits[0:2]}:{digits[2:4]}:{digits[4:6]}"
    raise ValueError(f"missing time field; expected one of: {', '.join(keys)}")


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


def required_int(row: dict[str, Any], *keys: str) -> int:
    return int(required_decimal(row, *keys))


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None
