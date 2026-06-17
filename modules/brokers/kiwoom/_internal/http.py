from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from modules.brokers.kiwoom.endpoints.registry import EndpointSpec
from modules.brokers.kiwoom.exceptions import KiwoomApiError


@dataclass(frozen=True)
class HttpResponse:
    payload: dict[str, Any]
    headers: dict[str, str]
    status_code: int


class AsyncHttpTransport:
    """Thin async HTTP transport over httpx for Kiwoom REST calls."""

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
        json_body: dict[str, Any] | None = None,
    ) -> HttpResponse:
        if self._client is None:
            raise RuntimeError(
                "AsyncHttpTransport must be used as `async with` context manager"
            )
        url = f"{self._base_url}{spec.path}"
        try:
            response = await self._client.request(
                spec.method,
                url,
                headers=headers,
                json=json_body,
            )
        except httpx.HTTPError as exc:
            raise KiwoomApiError(
                f"Kiwoom API request failed for {spec.name}: {exc}",
                status_code=None,
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise KiwoomApiError(
                f"non-JSON response from {spec.name}",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise KiwoomApiError(
                f"non-object JSON response from {spec.name}",
                status_code=response.status_code,
            )

        if response.status_code >= 400 or _is_kiwoom_error(payload):
            return_code = _str_or_none(payload.get("return_code"))
            return_msg = _str_or_none(payload.get("return_msg"))
            raise KiwoomApiError(
                return_msg or f"{spec.name} failed",
                status_code=response.status_code,
                return_code=return_code,
                return_msg=return_msg,
            )

        return HttpResponse(
            payload=payload,
            headers=dict(response.headers),
            status_code=response.status_code,
        )


def _is_kiwoom_error(payload: dict[str, Any]) -> bool:
    return_code = payload.get("return_code")
    return return_code is not None and str(return_code) != "0"


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
