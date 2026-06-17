from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

import httpx

from modules.brokers.kiwoom.auth.cache import TokenCache, TokenRecord
from modules.brokers.kiwoom.auth.oauth import issue_access_token_async
from modules.brokers.kiwoom.config import Credentials
from modules.brokers.kiwoom.types import Environment


@dataclass
class TokenProvider:
    credentials: Credentials
    environment: Environment
    token_cache: TokenCache
    http_client_factory: Callable[[], httpx.AsyncClient]
    expiry_skew: timedelta = timedelta(minutes=1)

    async def ensure_token(self) -> str:
        cache_key = f"{self.environment}:{self.credentials.app_key}"
        cached = self.token_cache.get(cache_key)
        if cached is not None and not self._is_effectively_expired(cached):
            return cached.access_token

        issued = await issue_access_token_async(
            environment=self.environment,
            app_key=self.credentials.app_key,
            secret_key=self.credentials.secret_key,
            client=self.http_client_factory(),
        )
        self.token_cache.set(
            cache_key,
            TokenRecord(
                access_token=issued.access_token,
                token_type=issued.token_type,
                expires_at=issued.expires_at,
            ),
        )
        return issued.access_token

    def _is_effectively_expired(self, record: TokenRecord) -> bool:
        return datetime.now(UTC) + self.expiry_skew >= record.expires_at
