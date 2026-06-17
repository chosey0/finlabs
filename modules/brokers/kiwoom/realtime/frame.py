from __future__ import annotations

import json
from typing import Any

from modules.brokers.kiwoom.models.orderbook import OrderBookSnapshot
from modules.brokers.kiwoom.models.tick import RealtimeTick
from modules.brokers.kiwoom.parsers.realtime import parse_realtime_message
from modules.brokers.kiwoom.realtime.subscription import SubscriptionRegistry

RealtimeEvent = RealtimeTick | OrderBookSnapshot


def is_ping_frame(frame: str) -> bool:
    try:
        payload = json.loads(frame)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("trnm") == "PING"


class RealtimeFrameProcessor:
    def __init__(self, subscriptions: SubscriptionRegistry) -> None:
        self._subscriptions = subscriptions
        self._received_seq = 1

    def process(self, frame: str | dict[str, Any]) -> tuple[RealtimeEvent, ...]:
        events = parse_realtime_message(
            frame,
            received_seq_start=self._received_seq,
        )
        self._received_seq += len(events)
        for event in events:
            self._subscriptions.validate(tr_id=event.tr_id, tr_key=event.tr_key)
        return events
