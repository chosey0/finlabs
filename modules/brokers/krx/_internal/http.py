from __future__ import annotations

from typing import Any

import httpx

from modules.brokers.krx.exceptions import KrxApiError


class AsyncHttpTransport:
    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient,
        timeout_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout_seconds

    async def request(
        self,
        path: str,
        *,
        auth_key: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(
                f"{self._base_url}{path}",
                headers={"accept": "application/json", "AUTH_KEY": auth_key},
                params=params,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise KrxApiError(
                f"KRX API request failed: {exc}",
                status_code=0,
            ) from exc

        payload = _json_object(response)
        if response.status_code >= 400:
            raise _api_error(response, payload)
        if _is_error_payload(payload):
            raise _api_error(response, payload)
        return payload


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise KrxApiError(
            "KRX API returned a non-JSON response",
            status_code=response.status_code,
        ) from exc
    if not isinstance(payload, dict):
        raise KrxApiError(
            "KRX API response must be a JSON object",
            status_code=response.status_code,
        )
    return payload


def _is_error_payload(payload: dict[str, Any]) -> bool:
    code = payload.get("respCode")
    if code is None:
        return False
    return str(code) not in {"000", "0", "OK"}


def _api_error(response: httpx.Response, payload: dict[str, Any]) -> KrxApiError:
    code = _text(payload.get("respCode"))
    message = _text(payload.get("respMsg")) or f"KRX API request failed ({response.status_code})"
    return KrxApiError(message, status_code=response.status_code, code=code, data=payload)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
