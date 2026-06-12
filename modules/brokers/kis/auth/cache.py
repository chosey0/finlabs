from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class TokenRecord:
    access_token: str
    token_type: str
    expires_at: datetime

    def is_expired(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return current >= self.expires_at


class TokenCache(Protocol):
    """Storage-agnostic cache for KIS REST access tokens.

    Implementations may persist tokens to memory, files, or external stores.
    `key` is opaque from this layer's perspective; callers typically derive it
    from credentials + environment.

    Implementations are plain stores: `get` may return an expired record.
    `TokenProvider` is authoritative for validity (including expiry skew).
    """

    def get(self, key: str) -> TokenRecord | None: ...

    def set(self, key: str, record: TokenRecord) -> None: ...

    def delete(self, key: str) -> None: ...


class MemoryTokenCache:
    """Process-local TokenCache backed by a dict. Useful for tests and short scripts."""

    def __init__(self) -> None:
        self._store: dict[str, TokenRecord] = {}

    def get(self, key: str) -> TokenRecord | None:
        return self._store.get(key)

    def set(self, key: str, record: TokenRecord) -> None:
        self._store[key] = record

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
