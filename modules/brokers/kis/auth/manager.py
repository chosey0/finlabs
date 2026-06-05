from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

import httpx

from modules.brokers.kis.auth.cache import TokenCache, TokenRecord
from modules.brokers.kis.auth.oauth import issue_access_token_async, issue_websocket_approval_key_async
from modules.brokers.kis.config import Credentials
from modules.brokers.kis.types import Environment


@dataclass(slots=True)
class TokenProvider:
    """Issue and cache KIS REST/WebSocket authentication tokens.

    `KisClient` owns HTTP transport lifecycle; this class owns only auth cache
    key derivation and token issuance. The HTTP client is supplied lazily so
    callers still get the same context-manager validation as before.
    """

    credentials: Credentials
    environment: Environment
    token_cache: TokenCache
    http_client_factory: Callable[[], httpx.AsyncClient]

    async def ensure_token(self) -> str:
        """Return a valid REST access token, issuing and caching on miss."""
        key = self._token_cache_key()
        cached = self.token_cache.get(key)
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
        cached = self.token_cache.get(key)
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

    def _token_cache_key(self) -> str:
        return f"{self.environment}:{self.credentials.app_key}"

    def _approval_cache_key(self) -> str:
        return f"ws:{self.environment}:{self.credentials.app_key}"
