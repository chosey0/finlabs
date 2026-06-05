from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from modules.brokers.kis._internal.headers import build_rest_headers
from modules.brokers.kis._internal.http import AsyncHttpTransport
from modules.brokers.kis.auth.cache import MemoryTokenCache, TokenCache
from modules.brokers.kis.auth.manager import TokenProvider
from modules.brokers.kis.config import Credentials, rest_base_url
from modules.brokers.kis.endpoints.registry import EndpointSpec
from modules.brokers.kis.types import Environment

if TYPE_CHECKING:
    from modules.brokers.kis.overseas import _OverseasNamespace
    from modules.brokers.kis.realtime import _RealtimeNamespace


@dataclass
class KisClient:
    """Facade for the KIS Open API.

    Use as an async context manager so the underlying `httpx.AsyncClient`
    and token cache are scoped to a single block:

        async with KisClient(credentials=...) as client:
            price = await client.overseas.price.current("AAPL", exchange="NAS")

    The client lazily issues and caches access tokens. Construct it without
    a context manager only when you need to inspect non-network attributes
    such as `base_url`.
    """

    credentials: Credentials
    environment: Environment = "real"
    token_cache: TokenCache = field(default_factory=MemoryTokenCache)
    http_client: httpx.AsyncClient | None = None
    timeout_seconds: float = 30.0

    overseas: "_OverseasNamespace" = field(init=False, repr=False)
    realtime: "_RealtimeNamespace" = field(init=False, repr=False)

    _owns_client: bool = field(default=False, init=False, repr=False)
    _entered: bool = field(default=False, init=False, repr=False)
    _transport: AsyncHttpTransport | None = field(default=None, init=False, repr=False)
    _token_provider: TokenProvider = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from modules.brokers.kis.overseas import _OverseasNamespace
        from modules.brokers.kis.realtime import _RealtimeNamespace

        self._token_provider = TokenProvider(
            credentials=self.credentials,
            environment=self.environment,
            token_cache=self.token_cache,
            http_client_factory=self._require_http_client,
        )
        self.overseas = _OverseasNamespace(self)
        self.realtime = _RealtimeNamespace(self)

    @property
    def base_url(self) -> str:
        return rest_base_url(self.environment)

    async def __aenter__(self) -> "KisClient":
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=self.timeout_seconds)
            self._owns_client = True
        self._transport = AsyncHttpTransport(
            base_url=self.base_url,
            timeout_seconds=self.timeout_seconds,
            client=self.http_client,
        )
        await self._transport.__aenter__()
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._entered = False
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
    ) -> "KisClient":
        return cls(
            credentials=Credentials.from_env(),
            environment=environment,
            token_cache=token_cache or MemoryTokenCache(),
        )

    def _require_http_client(self) -> httpx.AsyncClient:
        """Return the open AsyncClient, or raise if used outside `async with`."""
        if self.http_client is None:
            raise RuntimeError(
                "KisClient must be used as an async context manager: "
                "`async with KisClient(...) as client:`"
            )
        return self.http_client

    async def request(
        self,
        spec: EndpointSpec,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        tr_cont: str = "",
        custtype: str = "P",
    ) -> dict[str, Any]:
        """Execute one REST call against a registered EndpointSpec.

        Pulls a valid access token from `ensure_token()`, assembles the KIS
        headers, and dispatches via the cached AsyncHttpTransport. Returns
        the parsed JSON payload; callers feed it into the appropriate parser
        in `kis.parsers.rest`.
        """
        if self._transport is None:
            raise RuntimeError(
                "KisClient must be used as an async context manager: "
                "`async with KisClient(...) as client:`"
            )
        token = await self.ensure_token()
        headers = build_rest_headers(
            credentials=self.credentials,
            access_token=token,
            tr_id=spec.tr_id_for(self.environment),
            tr_cont=tr_cont,
            custtype=custtype,  # type: ignore[arg-type]
        )
        response = await self._transport.request(
            spec,
            headers=headers,
            params=params,
            json_body=json_body,
        )
        return response.payload

    async def ensure_token(self) -> str:
        """Return a valid REST access token, fetching one if needed."""
        return await self._token_provider.ensure_token()

    async def ensure_approval_key(self) -> str:
        """Return a valid WebSocket approval key, fetching one if needed."""
        return await self._token_provider.ensure_approval_key()
