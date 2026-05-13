from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from kis.endpoints.registry import EndpointSpec
from kis.exceptions import KisApiError


@dataclass(frozen=True)
class HttpResponse:
    payload: dict[str, Any]
    headers: dict[str, str]
    status_code: int


class AsyncHttpTransport:
    """Thin async HTTP transport over httpx for KIS REST calls.

    Concrete request building (URL, headers, params) is delegated to callers
    so this layer stays generic and easy to mock in tests.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "AsyncHttpTransport":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        spec: EndpointSpec,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> HttpResponse:
        if self._client is None:
            raise RuntimeError(
                "AsyncHttpTransport must be used as `async with` context manager"
            )
        url = f"{self._base_url}{spec.path}"
        response = await self._client.request(
            spec.method,
            url,
            headers=headers,
            params=params,
            json=json_body,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise KisApiError(
                f"non-JSON response from {spec.name}",
                status_code=response.status_code,
            ) from exc

        if response.status_code >= 400 or _is_kis_error(payload):
            raise KisApiError(
                _error_message(payload, fallback=f"{spec.name} failed"),
                status_code=response.status_code,
                rt_cd=_str_or_none(payload.get("rt_cd")),
                msg_cd=_str_or_none(payload.get("msg_cd")),
                msg1=_str_or_none(payload.get("msg1")),
            )

        return HttpResponse(
            payload=payload,
            headers=dict(response.headers),
            status_code=response.status_code,
        )


def _is_kis_error(payload: dict[str, Any]) -> bool:
    rt_cd = payload.get("rt_cd")
    return rt_cd is not None and str(rt_cd) != "0"


def _error_message(payload: dict[str, Any], *, fallback: str) -> str:
    msg = (
        payload.get("msg1") or payload.get("error_description") or payload.get("error")
    )
    return str(msg) if msg else fallback


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
