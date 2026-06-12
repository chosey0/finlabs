from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable

import httpx

from modules.brokers.kis.auth.cache import TokenCache, TokenRecord
from modules.brokers.kis.auth.oauth import issue_access_token_async, issue_websocket_approval_key_async
from modules.brokers.kis.config import Credentials
from modules.brokers.kis.types import Environment

TOKEN_EXPIRY_SKEW = timedelta(seconds=30)


@dataclass(slots=True)
class TokenProvider:
    """Issue and cache KIS REST/WebSocket authentication tokens.

    `KisClient` owns HTTP transport lifecycle; this class owns only auth cache
    key derivation and token issuance. The HTTP client is supplied lazily so
    callers still get the same context-manager validation as before.

    This layer is authoritative for token validity: cached records expiring
    within `TOKEN_EXPIRY_SKEW` are treated as misses, so `TokenCache`
    implementations can stay dumb stores. Issuance is serialized per artifact
    so concurrent first requests cannot trigger duplicate issuance — KIS
    rate-limits token issuance itself.
    """

    credentials: Credentials
    environment: Environment
    token_cache: TokenCache
    http_client_factory: Callable[[], httpx.AsyncClient]
    _token_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )
    _approval_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

    async def ensure_token(self) -> str:
        """Return a valid REST access token, issuing and caching on miss."""
        key = self._token_cache_key()
        cached = self._valid_record(key)
        if cached is not None:
            return cached.access_token

        async with self._token_lock:
            cached = self._valid_record(key)
            if cached is not None:
                return cached.access_token

            issued = await issue_access_token_async(
                environment=self.environment,
                app_key=self.credentials.app_key,
                app_secret=self.credentials.app_secret,
                client=self.http_client_factory(),
            )
            self.token_cache.set(
                key,
                TokenRecord(
                    access_token=issued.access_token,
                    token_type=issued.token_type,
                    expires_at=issued.expires_at,
                ),
            )
            return issued.access_token

    async def ensure_approval_key(self) -> str:
        """Return a cached WebSocket approval key, issuing on miss."""
        key = self._approval_cache_key()
        cached = self._valid_record(key)
        if cached is not None:
            return cached.access_token

        async with self._approval_lock:
            cached = self._valid_record(key)
            if cached is not None:
                return cached.access_token

            approval_key = await issue_websocket_approval_key_async(
                environment=self.environment,
                app_key=self.credentials.app_key,
                app_secret=self.credentials.app_secret,
                client=self.http_client_factory(),
            )
            self.token_cache.set(
                key,
                TokenRecord(
                    access_token=approval_key,
                    token_type="approval_key",
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                ),
            )
            return approval_key

    def _valid_record(self, key: str) -> TokenRecord | None:
        record = self.token_cache.get(key)
        if record is None:
            return None
        if record.is_expired(now=datetime.now(UTC) + TOKEN_EXPIRY_SKEW):
            return None
        return record

    def _token_cache_key(self) -> str:
        return f"{self.environment}:{self.credentials.app_key}"

    def _approval_cache_key(self) -> str:
        return f"ws:{self.environment}:{self.credentials.app_key}"
