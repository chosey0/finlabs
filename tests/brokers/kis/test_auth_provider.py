from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from modules.brokers.kis import Credentials, KisApiError, MemoryTokenCache
from modules.brokers.kis._internal.http import AsyncHttpTransport
from modules.brokers.kis.auth.cache import TokenRecord
from modules.brokers.kis.auth.manager import TokenProvider
from modules.brokers.kis.auth.oauth import IssuedToken
from modules.brokers.kis.endpoints.registry import EndpointSpec

TOKEN_CACHE_KEY = "real:app-key"


def _provider(cache: MemoryTokenCache) -> TokenProvider:
    return TokenProvider(
        credentials=Credentials(app_key="app-key", app_secret="app-secret"),
        environment="real",
        token_cache=cache,
        http_client_factory=lambda: None,  # type: ignore[arg-type, return-value]
    )


def _issued(token: str, *, expires_in: timedelta = timedelta(hours=6)) -> IssuedToken:
    now = datetime.now(UTC)
    return IssuedToken(
        access_token=token,
        token_type="Bearer",
        issued_at=now,
        expires_at=now + expires_in,
        raw={},
    )


def test_concurrent_token_requests_issue_only_once(monkeypatch) -> None:
    issue_calls = 0

    async def fake_issue(**kwargs) -> IssuedToken:
        nonlocal issue_calls
        issue_calls += 1
        await asyncio.sleep(0.01)
        return _issued(f"token-{issue_calls}")

    monkeypatch.setattr(
        "modules.brokers.kis.auth.manager.issue_access_token_async", fake_issue
    )
    provider = _provider(MemoryTokenCache())

    async def run() -> list[str]:
        return await asyncio.gather(*(provider.ensure_token() for _ in range(5)))

    tokens = asyncio.run(run())
    assert issue_calls == 1
    assert set(tokens) == {"token-1"}


def test_concurrent_approval_requests_issue_only_once(monkeypatch) -> None:
    issue_calls = 0

    async def fake_issue(**kwargs) -> str:
        nonlocal issue_calls
        issue_calls += 1
        await asyncio.sleep(0.01)
        return f"approval-{issue_calls}"

    monkeypatch.setattr(
        "modules.brokers.kis.auth.manager.issue_websocket_approval_key_async",
        fake_issue,
    )
    provider = _provider(MemoryTokenCache())

    async def run() -> list[str]:
        return await asyncio.gather(
            *(provider.ensure_approval_key() for _ in range(5))
        )

    keys = asyncio.run(run())
    assert issue_calls == 1
    assert set(keys) == {"approval-1"}


def test_token_expiring_within_skew_is_reissued(monkeypatch) -> None:
    async def fake_issue(**kwargs) -> IssuedToken:
        return _issued("fresh-token")

    monkeypatch.setattr(
        "modules.brokers.kis.auth.manager.issue_access_token_async", fake_issue
    )
    cache = MemoryTokenCache()
    cache.set(
        TOKEN_CACHE_KEY,
        TokenRecord(
            access_token="stale-token",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(seconds=10),
        ),
    )
    provider = _provider(cache)

    assert asyncio.run(provider.ensure_token()) == "fresh-token"


def test_token_valid_beyond_skew_is_reused(monkeypatch) -> None:
    async def fail_issue(**kwargs) -> IssuedToken:
        raise AssertionError("token must not be reissued while still valid")

    monkeypatch.setattr(
        "modules.brokers.kis.auth.manager.issue_access_token_async", fail_issue
    )
    cache = MemoryTokenCache()
    cache.set(
        TOKEN_CACHE_KEY,
        TokenRecord(
            access_token="cached-token",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
    )
    provider = _provider(cache)

    assert asyncio.run(provider.ensure_token()) == "cached-token"


def test_memory_cache_is_a_plain_store() -> None:
    cache = MemoryTokenCache()
    expired = TokenRecord(
        access_token="expired-token",
        token_type="Bearer",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    cache.set("key", expired)
    assert cache.get("key") == expired


def test_transport_wraps_network_errors_as_kis_api_error() -> None:
    spec = EndpointSpec(
        name="test-endpoint",
        method="GET",
        path="/test",
        tr_id_real="TTTT0000R",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async def run() -> KisApiError:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            async with AsyncHttpTransport(
                base_url="https://example.invalid", client=client
            ) as transport:
                with pytest.raises(KisApiError) as exc_info:
                    await transport.request(spec, headers={})
        finally:
            await client.aclose()
        return exc_info.value

    error = asyncio.run(run())
    assert error.status_code is None
    assert "test-endpoint" in str(error)
