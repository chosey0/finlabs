from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from modules.brokers.kiwoom.exceptions import KiwoomRealtimeError
from modules.brokers.kiwoom.models.orderbook import OrderBookLevel, OrderBookSnapshot
from modules.brokers.kiwoom.models.tick import RealtimeTick

RealtimeEvent = RealtimeTick | OrderBookSnapshot


def parse_realtime_message(
    message: str | dict[str, Any],
    *,
    market: str = "KRX",
    received_at: str | None = None,
    received_seq_start: int = 1,
) -> tuple[RealtimeEvent, ...]:
    payload = _payload(message)
    if payload.get("trnm") != "REAL":
        return ()

    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise KiwoomRealtimeError("Kiwoom REAL frame field `data` must be a list")

    timestamp = received_at or datetime.now(UTC).isoformat()
    events: list[RealtimeEvent] = []
    for offset, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        tr_id = _text(row.get("type"))
        values = _values(row.get("values"))
        seq = received_seq_start + offset
        if tr_id == "0B":
            events.append(
                _parse_trade(
                    row=row,
                    values=values,
                    market=market,
                    received_at=timestamp,
                    received_seq=seq,
                )
            )
        elif tr_id == "0D":
            events.append(
                _parse_orderbook(
                    row=row,
                    values=values,
                    market=market,
                    received_at=timestamp,
                    received_seq=seq,
                )
            )
    return tuple(events)


def _parse_trade(
    *,
    row: dict[str, Any],
    values: dict[str, str],
    market: str,
    received_at: str,
    received_seq: int,
) -> RealtimeTick:
    volume_text = values.get("15")
    return RealtimeTick(
        market=market,
        symbol=_text(row.get("item")),
        tr_id="0B",
        tr_key=_text(row.get("item")),
        exchange_ts=_time_value(values.get("20")),
        received_at=received_at,
        received_seq=received_seq,
        seq=received_seq,
        price=_price(values.get("10")),
        volume=_abs_int(volume_text),
        side=_execution_side(volume_text),
        change=_decimal(values.get("11")),
        change_rate=_decimal(values.get("12")),
        total_volume=_abs_int(values.get("13")),
        amount=_decimal(values.get("14")),
        ask_price=_price(values.get("27")),
        bid_price=_price(values.get("28")),
        open=_price(values.get("16")),
        high=_price(values.get("17")),
        low=_price(values.get("18")),
        raw=values,
    )


def _parse_orderbook(
    *,
    row: dict[str, Any],
    values: dict[str, str],
    market: str,
    received_at: str,
    received_seq: int,
) -> OrderBookSnapshot:
    levels = tuple(
        OrderBookLevel(
            level=level,
            ask_price=_price(values.get(str(40 + level))),
            bid_price=_price(values.get(str(50 + level))),
            ask_volume=_abs_int(values.get(str(60 + level))),
            bid_volume=_abs_int(values.get(str(70 + level))),
            ask_change=_int(values.get(str(80 + level))),
            bid_change=_int(values.get(str(90 + level))),
        )
        for level in range(1, 11)
    )
    symbol = _text(row.get("item"))
    return OrderBookSnapshot(
        market=market,
        symbol=symbol,
        tr_id="0D",
        tr_key=symbol,
        exchange_ts=_time_value(values.get("21")),
        received_at=received_at,
        received_seq=received_seq,
        seq=received_seq,
        asks=levels,
        bids=levels,
        total_ask_volume=_abs_int(values.get("121")),
        total_bid_volume=_abs_int(values.get("125")),
        total_ask_change=_int(values.get("122")),
        total_bid_change=_int(values.get("126")),
        expected_price=_price(values.get("23")),
        expected_volume=_abs_int(values.get("24")),
        raw=values,
    )


def _payload(message: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError as exc:
        raise KiwoomRealtimeError("Kiwoom realtime frame was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise KiwoomRealtimeError("Kiwoom realtime frame must be a JSON object")
    return parsed


def _values(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise KiwoomRealtimeError("Kiwoom REAL row field `values` must be an object")
    return {str(key): str(item).strip() for key, item in value.items()}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _time_value(value: str | None) -> str:
    text = _text(value)
    if len(text) == 6 and text.isdigit():
        return f"{text[0:2]}:{text[2:4]}:{text[4:6]}"
    return text


def _price(value: str | None) -> Decimal | None:
    decimal = _decimal(value)
    if decimal is None:
        return None
    return abs(decimal)


def _decimal(value: str | None) -> Decimal | None:
    text = _text(value).replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _int(value: str | None) -> int | None:
    decimal = _decimal(value)
    if decimal is None:
        return None
    return int(decimal)


def _abs_int(value: str | None) -> int | None:
    integer = _int(value)
    if integer is None:
        return None
    return abs(integer)


def _execution_side(volume_text: str | None) -> str | None:
    text = _text(volume_text)
    if text.startswith("+"):
        return "buy"
    if text.startswith("-"):
        return "sell"
    return None
