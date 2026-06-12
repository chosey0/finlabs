from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from modules.brokers.toss.config import Credentials, DEFAULT_BASE_URL
from modules.brokers.toss.exceptions import TossAuthError

TOKEN_PATH = "/oauth2/token"

SECRET_PATTERNS = (
    re.compile(r"(client_secret[\"':=\s]+)([A-Za-z0-9._\-]{8,})", re.IGNORECASE),
    re.compile(r"(access_token[\"':=\s]+)([A-Za-z0-9._\-]{8,})", re.IGNORECASE),
)


def mask_sensitive_message(message: str) -> str:
    masked = message
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub(r"\1********", masked)
    return masked


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    token_type: str
    issued_at: datetime
    expires_at: datetime
    raw: dict[str, Any]


class TokenCache(Protocol):
    def get(self, key: str) -> IssuedToken | None: ...

    def set(self, key: str, token: IssuedToken) -> None: ...


class MemoryTokenCache:
    def __init__(self) -> None:
        self._tokens: dict[str, IssuedToken] = {}

    def get(self, key: str) -> IssuedToken | None:
        return self._tokens.get(key)

    def set(self, key: str, token: IssuedToken) -> None:
        self._tokens[key] = token


class TokenProvider:
    def __init__(
        self,
        *,
        credentials: Credentials,
        token_cache: TokenCache,
        client_factory,
        base_url: str,
    ) -> None:
        self._credentials = credentials
        self._cache = token_cache
        self._client_factory = client_factory
        self._base_url = base_url
        self._lock = asyncio.Lock()

    async def ensure_token(self) -> str:
        cached = self._valid_cached_token()
        if cached is not None:
            return cached.access_token
        async with self._lock:
            cached = self._valid_cached_token()
            if cached is not None:
                return cached.access_token
            token = await issue_access_token_async(
                credentials=self._credentials,
                client=self._client_factory(),
                base_url=self._base_url,
            )
            self._cache.set(self._credentials.client_id, token)
            return token.access_token

    def _valid_cached_token(self) -> IssuedToken | None:
        token = self._cache.get(self._credentials.client_id)
        if token is None:
            return None
        if token.expires_at <= datetime.now(UTC) + timedelta(seconds=30):
            return None
        return token


async def issue_access_token_async(
    *,
    credentials: Credentials,
    client: httpx.AsyncClient | None = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 30.0,
) -> IssuedToken:
    issued_at = datetime.now(UTC)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)
    try:
        response = await client.post(
            f"{base_url.rstrip('/')}{TOKEN_PATH}",
            data={
                "grant_type": "client_credentials",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
            },
            headers={"accept": "application/json"},
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise TossAuthError(
            mask_sensitive_message(f"Toss token request failed: {exc}")
        ) from exc
    finally:
        if owns_client:
            await client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise TossAuthError("Toss token response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TossAuthError("Toss token response must be a JSON object")
    if response.status_code >= 400:
        message = payload.get("error_description") or payload.get("error")
        raise TossAuthError(
            mask_sensitive_message(
                f"Toss token request failed: {message or response.status_code}"
            )
        )
    return parse_token_response(payload, issued_at=issued_at)


def parse_token_response(
    payload: dict[str, Any], *, issued_at: datetime
) -> IssuedToken:
    access_token = payload.get("access_token")
    token_type = payload.get("token_type")
    expires_in = payload.get("expires_in")
    if not isinstance(access_token, str) or not access_token:
        raise TossAuthError("Toss token response did not include access_token")
    if token_type != "Bearer":
        raise TossAuthError("Toss token response included an unsupported token_type")
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise TossAuthError("Toss token response included an invalid expires_in")
    return IssuedToken(
        access_token=access_token,
        token_type=token_type,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=expires_in),
        raw=dict(payload),
    )
