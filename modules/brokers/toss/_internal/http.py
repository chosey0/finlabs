from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import httpx

from modules.brokers.toss.exceptions import TossApiError, TossRateLimitError

Sleep = Callable[[float], Awaitable[None]]


class AsyncHttpTransport:
    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient,
        timeout_seconds: float,
        max_retries: int,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._sleep = sleep

    async def request(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers={
                        "accept": "application/json",
                        "authorization": f"Bearer {access_token}",
                    },
                    params=params,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                raise TossApiError(
                    f"Toss API request failed: {exc}", status_code=0
                ) from exc

            if response.status_code == 429 and attempt < self._max_retries:
                await self._sleep(_retry_delay(response, attempt))
                continue

            payload = _json_object(response)
            if response.status_code >= 400:
                raise _api_error(response, payload)
            return payload
        raise AssertionError("unreachable")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise TossApiError(
            "Toss API returned a non-JSON response",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
        ) from exc
    if not isinstance(payload, dict):
        raise TossApiError(
            "Toss API response must be a JSON object",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
        )
    return payload


def _api_error(response: httpx.Response, payload: dict[str, Any]) -> TossApiError:
    envelope = payload.get("error")
    error = envelope if isinstance(envelope, dict) else {}
    request_id = _text(error.get("requestId")) or response.headers.get("x-request-id")
    code = _text(error.get("code"))
    message = (
        _text(error.get("message"))
        or f"Toss API request failed ({response.status_code})"
    )
    data = error.get("data") if isinstance(error.get("data"), dict) else None
    retry_after = _retry_after(response)
    error_type = TossRateLimitError if response.status_code == 429 else TossApiError
    return error_type(
        message,
        status_code=response.status_code,
        code=code,
        request_id=request_id,
        data=data,
        retry_after=retry_after,
    )


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    return _retry_after(response) or float(2**attempt)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
