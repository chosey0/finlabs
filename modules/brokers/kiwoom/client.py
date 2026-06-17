from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from modules.brokers.kiwoom._internal.headers import build_rest_headers
from modules.brokers.kiwoom._internal.http import AsyncHttpTransport, HttpResponse
from modules.brokers.kiwoom.auth.cache import MemoryTokenCache, TokenCache
from modules.brokers.kiwoom.auth.manager import TokenProvider
from modules.brokers.kiwoom.config import Credentials, rest_base_url
from modules.brokers.kiwoom.endpoints.registry import EndpointSpec
from modules.brokers.kiwoom.types import Environment

if TYPE_CHECKING:
    from modules.brokers.kiwoom.domestic import _DomesticNamespace
    from modules.brokers.kiwoom.realtime import _RealtimeNamespace


@dataclass
class KiwoomClient:
    """Facade for the Kiwoom REST and realtime APIs.

    Use as an async context manager so the underlying ``httpx.AsyncClient`` and
    token cache are scoped to a single block:

        async with KiwoomClient(credentials=...) as client:
            bars = await client.domestic.chart.daily("005930", base_date="20260617")
    """

    credentials: Credentials
    environment: Environment = "real"
    token_cache: TokenCache = field(default_factory=MemoryTokenCache)
    http_client: httpx.AsyncClient | None = None
    timeout_seconds: float = 30.0

    domestic: "_DomesticNamespace" = field(init=False, repr=False)
    realtime: "_RealtimeNamespace" = field(init=False, repr=False)

    _owns_client: bool = field(default=False, init=False, repr=False)
    _transport: AsyncHttpTransport | None = field(default=None, init=False, repr=False)
    _token_provider: TokenProvider = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from modules.brokers.kiwoom.domestic import _DomesticNamespace
        from modules.brokers.kiwoom.realtime import _RealtimeNamespace

        self._token_provider = TokenProvider(
            credentials=self.credentials,
            environment=self.environment,
            token_cache=self.token_cache,
            http_client_factory=self._require_http_client,
        )
        self.domestic = _DomesticNamespace(self)
        self.realtime = _RealtimeNamespace(self)

    @property
    def base_url(self) -> str:
        return rest_base_url(self.environment)

    async def __aenter__(self) -> "KiwoomClient":
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=self.timeout_seconds)
            self._owns_client = True
        self._transport = AsyncHttpTransport(
            base_url=self.base_url,
            timeout_seconds=self.timeout_seconds,
            client=self.http_client,
        )
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._transport is not None:
            await self._transport.__aexit__(exc_type, exc, tb)
            self._transport = None
        if self._owns_client and self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None
            self._owns_client = False

    @classmethod
    def from_env(
        cls,
        *,
        environment: Environment = "real",
        token_cache: TokenCache | None = None,
    ) -> "KiwoomClient":
        return cls(
            credentials=Credentials.from_env(),
            environment=environment,
            token_cache=token_cache or MemoryTokenCache(),
        )

    async def request(
        self,
        spec: EndpointSpec,
        *,
        json_body: dict[str, Any] | None = None,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> dict[str, Any]:
        """Execute one REST call and return the parsed JSON payload."""
        response = await self.request_raw(
            spec,
            json_body=json_body,
            cont_yn=cont_yn,
            next_key=next_key,
        )
        return response.payload

    async def request_raw(
        self,
        spec: EndpointSpec,
        *,
        json_body: dict[str, Any] | None = None,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> HttpResponse:
        """Execute one REST call and preserve response headers for pagination."""
        if self._transport is None:
            raise RuntimeError(
                "KiwoomClient must be used as an async context manager: "
                "`async with KiwoomClient(...) as client:`"
            )
        token = await self.ensure_token()
        headers = build_rest_headers(
            access_token=token,
            spec=spec,
            cont_yn=cont_yn,
            next_key=next_key,
        )
        return await self._transport.request(
            spec,
            headers=headers,
            json_body=json_body,
        )

    async def ensure_token(self) -> str:
        """Return a valid REST access token, fetching one if needed."""
        return await self._token_provider.ensure_token()

    def _require_http_client(self) -> httpx.AsyncClient:
        if self.http_client is None:
            raise RuntimeError(
                "KiwoomClient must be used as an async context manager: "
                "`async with KiwoomClient(...) as client:`"
            )
        return self.http_client
