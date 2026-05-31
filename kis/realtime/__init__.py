"""WebSocket realtime session and subscriptions.

`_RealtimeNamespace` is accessed as `KisClient.realtime`. Stage 4 returns
a `RealtimeSession` async context manager from `session()`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kis.realtime.session import RealtimeSession
from kis.realtime.subscription import RealtimeSubscription

if TYPE_CHECKING:
    from kis.client import KisClient


class _RealtimeNamespace:
    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    def session(self) -> RealtimeSession:
        return RealtimeSession(self._parent)


__all__ = ["RealtimeSession", "RealtimeSubscription"]
