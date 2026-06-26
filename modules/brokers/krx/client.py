from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from modules.brokers.krx._internal.http import AsyncHttpTransport
from modules.brokers.krx.config import Credentials, DEFAULT_BASE_URL
from modules.brokers.krx.indices import IndexAPI


@dataclass
class KrxClient:
    """Async client for KRX Data Marketplace Open API read-only market data."""

    credentials: Credentials
    http_client: httpx.AsyncClient | None = None
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0
    use_sample_api: bool = False

    indices: IndexAPI = field(init=False, repr=False)

    _owns_client: bool = field(default=False, init=False, repr=False)
    _transport: AsyncHttpTransport | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.indices = IndexAPI(self)

    @classmethod
    def from_env(cls, **kwargs: Any) -> "KrxClient":
        return cls(credentials=Credentials.from_env(), **kwargs)

    async def __aenter__(self) -> "KrxClient":
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=self.timeout_seconds)
            self._owns_client = True
        self._transport = AsyncHttpTransport(
            base_url=self.base_url,
            client=self.http_client,
            timeout_seconds=self.timeout_seconds,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._transport = None
        if self._owns_client and self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None
            self._owns_client = False

    async def request(self, api_id: str, *, params: dict[str, str]) -> dict[str, Any]:
        if self._transport is None:
            raise RuntimeError(
                "KrxClient must be used as an async context manager: "
                "`async with KrxClient(...) as client:`"
            )
        namespace = "sample/apis" if self.use_sample_api else "apis"
        path = f"/svc/{namespace}/idx/{api_id}.json"
        return await self._transport.request(
            path,
            auth_key=self.credentials.auth_key.strip(),
            params=params,
        )
