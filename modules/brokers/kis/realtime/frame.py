from __future__ import annotations

import json
import logging

from modules.brokers.kis.models.orderbook import OrderBookSnapshot
from modules.brokers.kis.models.tick import RealtimeTick
from modules.brokers.kis.parsers.realtime import parse_realtime_frame
from modules.brokers.kis.realtime.subscription import SubscriptionRegistry

logger = logging.getLogger(__name__)


def is_pingpong_frame(frame: str) -> bool:
    """Return True for KIS application-level PINGPONG keepalive frames.

    The server expects these JSON frames to be echoed back verbatim;
    otherwise it eventually drops the connection.
    """
    if not frame.lstrip().startswith("{"):
        return False
    try:
        payload = json.loads(frame)
    except json.JSONDecodeError:
        return False
    header = payload.get("header")
    return isinstance(header, dict) and header.get("tr_id") == "PINGPONG"


class RealtimeFrameProcessor:
    """Handle realtime control/data frames and preserve received_seq ordering."""

    def __init__(self, registry: SubscriptionRegistry) -> None:
        self._registry = registry
        self._received_seq = 0

    def process(self, frame: str) -> tuple[RealtimeTick | OrderBookSnapshot, ...]:
        if frame.lstrip().startswith("{"):
            self._handle_ack(frame)
            return ()
        return self._parse_events(frame)

    def _parse_events(self, frame: str) -> tuple[RealtimeTick | OrderBookSnapshot, ...]:
        received_seq_start = self._received_seq + 1
        events = parse_realtime_frame(
            frame,
            received_seq_start=received_seq_start,
        )
        self._received_seq += len(events)
        for event in events:
            self._registry.validate_event(event)
        return tuple(events)

    def _handle_ack(self, frame: str) -> None:
        try:
            payload = json.loads(frame)
        except json.JSONDecodeError:
            logger.warning("ignored malformed realtime JSON frame")
            return
        msg = str(payload.get("body", {}).get("msg1", ""))
        if msg and "SUCCESS" not in msg:
            logger.warning("realtime websocket control message: %s", msg)
