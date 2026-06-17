from __future__ import annotations

from typing import TYPE_CHECKING

from modules.brokers.kiwoom.realtime.session import RealtimeSession
from modules.brokers.kiwoom.realtime.subscription import (
    RealtimeSubscription,
    subscription_for,
)

if TYPE_CHECKING:
    from modules.brokers.kiwoom.client import KiwoomClient


class _RealtimeNamespace:
    def __init__(self, client: "KiwoomClient") -> None:
        self._client = client

    def session(
        self,
        *,
        reconnect: bool = True,
        reconnect_delay_seconds: float = 1.0,
    ) -> RealtimeSession:
        return RealtimeSession(
            self._client,
            reconnect=reconnect,
            reconnect_delay_seconds=reconnect_delay_seconds,
        )


__all__ = [
    "RealtimeSession",
    "RealtimeSubscription",
    "_RealtimeNamespace",
    "subscription_for",
]
