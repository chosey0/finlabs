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
    def get(self, key: str) -> TokenRecord | None: ...

    def set(self, key: str, record: TokenRecord) -> None: ...

    def delete(self, key: str) -> None: ...


class MemoryTokenCache:
    """Process-local token cache for tests and short scripts."""

    def __init__(self) -> None:
        self._store: dict[str, TokenRecord] = {}

    def get(self, key: str) -> TokenRecord | None:
        return self._store.get(key)

    def set(self, key: str, record: TokenRecord) -> None:
        self._store[key] = record

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
