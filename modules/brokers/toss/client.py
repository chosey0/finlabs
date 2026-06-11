from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from modules.brokers.toss._internal.http import AsyncHttpTransport
from modules.brokers.toss.auth import MemoryTokenCache, TokenCache, TokenProvider
from modules.brokers.toss.config import Credentials, DEFAULT_BASE_URL
from modules.brokers.toss.market import MarketDataAPI
from modules.brokers.toss.stocks import StocksAPI


@dataclass
class TossClient:
    """Async client for the Toss Securities Open API read-only market surface."""

    credentials: Credentials
    token_cache: TokenCache = field(default_factory=MemoryTokenCache)
    http_client: httpx.AsyncClient | None = None
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0
    max_retries: int = 2

    market: MarketDataAPI = field(init=False, repr=False)
    stocks: StocksAPI = field(init=False, repr=False)

    _owns_client: bool = field(default=False, init=False, repr=False)
    _transport: AsyncHttpTransport | None = field(default=None, init=False, repr=False)
    _token_provider: TokenProvider = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.market = MarketDataAPI(self)
        self.stocks = StocksAPI(self)
        self._token_provider = TokenProvider(
            credentials=self.credentials,
            token_cache=self.token_cache,
            client_factory=self._require_http_client,
            base_url=self.base_url,
        )

    @classmethod
    def from_env(cls, **kwargs) -> "TossClient":
        return cls(credentials=Credentials.from_env(), **kwargs)

    async def __aenter__(self) -> "TossClient":
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=self.timeout_seconds)
            self._owns_client = True
        self._transport = AsyncHttpTransport(
            base_url=self.base_url,
            client=self.http_client,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._transport = None
        if self._owns_client and self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None
            self._owns_client = False

    async def ensure_token(self) -> str:
        return await self._token_provider.ensure_token()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self._transport is None:
            raise RuntimeError(
                "TossClient must be used as an async context manager: "
                "`async with TossClient(...) as client:`"
            )
        return await self._transport.request(
            method,
            path,
            access_token=await self.ensure_token(),
            params=params,
        )

    def _require_http_client(self) -> httpx.AsyncClient:
        if self.http_client is None:
            raise RuntimeError(
                "TossClient must be used as an async context manager: "
                "`async with TossClient(...) as client:`"
            )
        return self.http_client
