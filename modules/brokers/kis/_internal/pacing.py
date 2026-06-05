from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Awaitable, Callable, TypeVar

from modules.brokers.kis.exceptions import KisApiError

KIS_CONTINUATION_REQUESTS_PER_SECOND = 20
KIS_CONTINUATION_SAFETY_BUFFER_SECONDS = 0.01
KIS_CONTINUATION_MIN_INTERVAL_SECONDS = (
    1 / KIS_CONTINUATION_REQUESTS_PER_SECOND
) + KIS_CONTINUATION_SAFETY_BUFFER_SECONDS
KIS_RATE_LIMIT_BACKOFF_SECONDS = 1.0
T = TypeVar("T")


@dataclass
class ContinuationPacer:
    """Pace sequential continuation requests to respect KIS API limits.

    KIS documents a 20 requests/second limit for continuation queries.
    This helper spaces request starts by at least 50 ms while avoiding an
    unnecessary delay before the first page.
    """

    min_interval_seconds: float = KIS_CONTINUATION_MIN_INTERVAL_SECONDS
    _last_request_started_at: float | None = None

    async def wait_before_request(self) -> None:
        if self._last_request_started_at is not None:
            elapsed = monotonic() - self._last_request_started_at
            delay = self.min_interval_seconds - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
        self._last_request_started_at = monotonic()


async def call_with_continuation_pacing(
    pacer: ContinuationPacer,
    call: Callable[[], Awaitable[T]],
    *,
    max_rate_limit_retries: int = 3,
) -> T:
    """Run one continuation request with pacing and rate-limit backoff."""
    for attempt in range(max_rate_limit_retries + 1):
        await pacer.wait_before_request()
        try:
            return await call()
        except KisApiError as exc:
            if attempt >= max_rate_limit_retries or not _is_rate_limit_error(exc):
                raise
            await asyncio.sleep(KIS_RATE_LIMIT_BACKOFF_SECONDS)
    raise RuntimeError("unreachable")


def _is_rate_limit_error(exc: KisApiError) -> bool:
    message = " ".join(
        value
        for value in (str(exc), exc.msg1, exc.msg_cd)
        if value is not None
    )
    normalized = message.lower()
    return (
        "초당 거래건수" in message
        or "rate limit" in normalized
        or "too many requests" in normalized
    )
