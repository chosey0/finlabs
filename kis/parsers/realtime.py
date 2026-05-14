from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from kis.exceptions import KisRealtimeError
from kis.models.orderbook import OrderBookLevel, OrderBookSnapshot
from kis.models.tick import RealtimeTick

OVERSEAS_TRADE_FIELDS = (
    "RSYM",
    "SYMB",
    "ZDIV",
    "TYMD",
    "XYMD",
    "XHMS",
    "KYMD",
    "KHMS",
    "OPEN",
    "HIGH",
    "LOW",
    "LAST",
    "SIGN",
    "DIFF",
    "RATE",
    "PBID",
    "PASK",
    "VBID",
    "VASK",
    "EVOL",
    "TVOL",
    "TAMT",
    "BIVL",
    "ASVL",
    "STRN",
    "MTYP",
)

OVERSEAS_ORDERBOOK_FIELDS = (
    "RSYM",
    "SYMB",
    "ZDIV",
    "XYMD",
    "XHMS",
    "KYMD",
    "KHMS",
    "BVOL",
    "AVOL",
    "BDVL",
    "ADVL",
    *(
        item
        for level in range(1, 11)
        for item in (
            f"PBID{level}",
            f"PASK{level}",
            f"VBID{level}",
            f"VASK{level}",
            f"DBID{level}",
            f"DASK{level}",
        )
    ),
)

TRADE_FIELDS_BY_TR_ID = {"HDFSCNT0": OVERSEAS_TRADE_FIELDS}
ORDERBOOK_FIELDS_BY_TR_ID = {"HDFSASP0": OVERSEAS_ORDERBOOK_FIELDS}


def parse_realtime_frame(
    frame: str,
    *,
    received_at: str | None = None,
    received_seq_start: int = 1,
) -> list[RealtimeTick | OrderBookSnapshot]:
    header = parse_realtime_frame_header(frame)
    tr_id = header["tr_id"]
    payload = header["payload"]
    data_count = int(header["data_count"] or "1")
    if tr_id in TRADE_FIELDS_BY_TR_ID:
        return parse_trade_payload(
            tr_id=tr_id,
            payload=payload,
            data_count=data_count,
            received_at=received_at,
            received_seq_start=received_seq_start,
        )
    if tr_id in ORDERBOOK_FIELDS_BY_TR_ID:
        return parse_orderbook_payload(
            tr_id=tr_id,
            payload=payload,
            data_count=data_count,
            received_at=received_at,
            received_seq_start=received_seq_start,
        )
    raise KisRealtimeError(f"unsupported realtime tr_id: {tr_id}")


def parse_realtime_frame_header(frame: str) -> dict[str, str]:
    parts = frame.split("|", 3)
    if len(parts) != 4:
        raise KisRealtimeError("realtime frame must have four pipe-delimited parts")
    encrypted, tr_id, data_count, payload = parts
    if encrypted not in {"0", "1"}:
        raise KisRealtimeError(f"unsupported realtime encryption flag: {encrypted}")
    if encrypted == "1":
        raise KisRealtimeError("encrypted realtime frames are not supported yet")
    return {
        "encrypted": encrypted,
        "tr_id": tr_id,
        "tr_key": "",
        "data_count": data_count,
        "payload": payload,
    }


def parse_trade_payload(
    *,
    tr_id: str,
    payload: str,
    data_count: int = 1,
    received_at: str | None = None,
    received_seq_start: int = 1,
) -> list[RealtimeTick]:
    fields = TRADE_FIELDS_BY_TR_ID[tr_id]
    return [
        _trade_from_raw(
            tr_id=tr_id,
            raw=raw,
            received_at=received_at or _now_iso(),
            received_seq=received_seq_start + index,
            seq=index + 1,
        )
        for index, raw in enumerate(_payload_records(payload, fields, data_count))
    ]


def parse_orderbook_payload(
    *,
    tr_id: str,
    payload: str,
    data_count: int = 1,
    received_at: str | None = None,
    received_seq_start: int = 1,
) -> list[OrderBookSnapshot]:
    fields = ORDERBOOK_FIELDS_BY_TR_ID[tr_id]
    return [
        _orderbook_from_raw(
            tr_id=tr_id,
            raw=raw,
            received_at=received_at or _now_iso(),
            received_seq=received_seq_start + index,
            seq=index + 1,
        )
        for index, raw in enumerate(_payload_records(payload, fields, data_count))
    ]


def _trade_from_raw(
    *,
    tr_id: str,
    raw: dict[str, str],
    received_at: str,
    received_seq: int,
    seq: int,
) -> RealtimeTick:
    return RealtimeTick(
        market=_overseas_market(raw.get("RSYM", "")),
        symbol=raw.get("SYMB", ""),
        tr_id=tr_id,
        tr_key=raw.get("RSYM", ""),
        exchange_ts=_combine_date_time(raw.get("XYMD", ""), raw.get("XHMS", "")),
        received_at=received_at,
        received_seq=received_seq,
        seq=seq,
        price=_decimal(raw.get("LAST")),
        volume=_int(raw.get("EVOL")),
        total_volume=_int(raw.get("TVOL")),
        amount=_decimal(raw.get("TAMT")),
        bid_price=_decimal(raw.get("PBID")),
        ask_price=_decimal(raw.get("PASK")),
        raw=raw,
    )


def _orderbook_from_raw(
    *,
    tr_id: str,
    raw: dict[str, str],
    received_at: str,
    received_seq: int,
    seq: int,
) -> OrderBookSnapshot:
    levels = tuple(
        OrderBookLevel(
            level=level,
            ask_price=_decimal(raw.get(f"PASK{level}")),
            bid_price=_decimal(raw.get(f"PBID{level}")),
            ask_volume=_int(raw.get(f"VASK{level}")),
            bid_volume=_int(raw.get(f"VBID{level}")),
        )
        for level in range(1, 11)
    )
    return OrderBookSnapshot(
        market=_overseas_market(raw.get("RSYM", "")),
        symbol=raw.get("SYMB", ""),
        tr_id=tr_id,
        tr_key=raw.get("RSYM", ""),
        exchange_ts=_combine_date_time(raw.get("XYMD", ""), raw.get("XHMS", "")),
        received_at=received_at,
        received_seq=received_seq,
        seq=seq,
        asks=levels,
        bids=levels,
        total_ask_volume=_int(raw.get("AVOL")),
        total_bid_volume=_int(raw.get("BVOL")),
        raw=raw,
    )


def _payload_records(
    payload: str,
    fields: tuple[str, ...],
    data_count: int,
) -> Iterable[dict[str, str]]:
    values = payload.split("^")
    width = len(fields)
    if data_count < 1:
        raise KisRealtimeError("realtime data_count must be at least 1")
    for index in range(data_count):
        start = index * width
        chunk = values[start : start + width]
        if not chunk:
            break
        yield _values_to_raw(fields, chunk)


def _values_to_raw(fields: tuple[str, ...], values: list[str]) -> dict[str, str]:
    raw = {
        field: values[index] if index < len(values) else ""
        for index, field in enumerate(fields)
    }
    if len(values) > len(fields):
        for index, value in enumerate(values[len(fields) :], start=1):
            raw[f"_extra_{index}"] = value
    return raw


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _int(value: str | None) -> int | None:
    number = _decimal(value)
    return int(number) if number is not None else None


def _combine_date_time(date_value: str, time_value: str) -> str:
    date_text = date_value.strip()
    time_text = time_value.strip().zfill(6)
    if len(date_text) == 8 and len(time_text) == 6:
        return (
            f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]} "
            f"{time_text[0:2]}:{time_text[2:4]}:{time_text[4:6]}"
        )
    return f"{date_text} {time_text}".strip()


def _overseas_market(realtime_symbol: str) -> str:
    text = realtime_symbol.strip()
    if len(text) >= 4 and text[0] in {"D", "R"}:
        return text[1:4]
    return ""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
