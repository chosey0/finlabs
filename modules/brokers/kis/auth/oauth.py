from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from modules.brokers.kis.config import rest_base_url
from modules.brokers.kis.exceptions import KisAuthError
from modules.brokers.kis.types import Environment

TOKEN_PATH = "/oauth2/tokenP"
APPROVAL_PATH = "/oauth2/Approval"

SECRET_PATTERNS = (
    re.compile(r"(app(?:key|secret)[\"':=\s]+)([A-Za-z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(access_token[\"':=\s]+)([A-Za-z0-9._\-]{8,})", re.IGNORECASE),
    re.compile(r"(approval_key[\"':=\s]+)([A-Za-z0-9._\-]{8,})", re.IGNORECASE),
)


@dataclass(frozen=True)
class IssuedToken:
    """Result of a successful KIS REST token issuance.

    Pure SDK record: no profile_id / file path / environment metadata. Higher
    layers wrap this in their own cache record.
    """

    access_token: str
    token_type: str
    issued_at: datetime
    expires_at: datetime
    raw: dict[str, Any]


def token_url(environment: Environment) -> str:
    return f"{rest_base_url(environment)}{TOKEN_PATH}"


def approval_url(environment: Environment) -> str:
    return f"{rest_base_url(environment)}{APPROVAL_PATH}"


def issue_access_token(
    *,
    environment: Environment,
    app_key: str,
    app_secret: str,
    timeout_seconds: float = 30.0,
) -> IssuedToken:
    """Issue a KIS REST access token (sync).

    The KIS `/oauth2/tokenP` endpoint is a one-shot POST; a synchronous client
    is the natural fit for ad-hoc scripts, even though market-data endpoints
    are async-first. See `issue_access_token_async` for the async variant.
    """
    issued_at = datetime.now(UTC)
    body = _token_request_body(app_key, app_secret)
    try:
        response = httpx.post(
            token_url(environment),
            json=body,
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KisAuthError(f"KIS token request failed: {exc}") from exc

    return _interpret_token_response(response, issued_at=issued_at)


async def issue_access_token_async(
    *,
    environment: Environment,
    app_key: str,
    app_secret: str,
    timeout_seconds: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> IssuedToken:
    """Issue a KIS REST access token (async).

    When an external `client` is supplied (e.g. one shared by `KisClient`),
    its lifecycle is the caller's responsibility. Otherwise a short-lived
    AsyncClient is created and closed inside this function.
    """
    issued_at = datetime.now(UTC)
    body = _token_request_body(app_key, app_secret)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)
    try:
        response = await client.post(
            token_url(environment),
            json=body,
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KisAuthError(f"KIS token request failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    return _interpret_token_response(response, issued_at=issued_at)


def issue_websocket_approval_key(
    *,
    environment: Environment,
    app_key: str,
    app_secret: str,
    timeout_seconds: float = 30.0,
) -> str:
    try:
        response = httpx.post(
            approval_url(environment),
            json=_approval_request_body(app_key, app_secret),
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KisAuthError(f"KIS websocket approval request failed: {exc}") from exc
    return _interpret_approval_response(response)


async def issue_websocket_approval_key_async(
    *,
    environment: Environment,
    app_key: str,
    app_secret: str,
    timeout_seconds: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> str:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)
    try:
        response = await client.post(
            approval_url(environment),
            json=_approval_request_body(app_key, app_secret),
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KisAuthError(f"KIS websocket approval request failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()
    return _interpret_approval_response(response)


_TOKEN_REQUEST_HEADERS = {
    "content-type": "application/json; charset=utf-8",
    "accept": "application/json",
}


def _token_request_body(app_key: str, app_secret: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret,
    }


def _approval_request_body(app_key: str, app_secret: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "secretkey": app_secret,
    }


def _interpret_token_response(
    response: httpx.Response, *, issued_at: datetime
) -> IssuedToken:
    if response.status_code >= 400:
        raise KisAuthError(
            f"KIS token request failed: {_extract_error_message(response)}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise KisAuthError("KIS token response was not valid JSON") from exc
    return parse_token_response(payload, issued_at=issued_at)


def _interpret_approval_response(response: httpx.Response) -> str:
    if response.status_code >= 400:
        raise KisAuthError(
            f"KIS websocket approval request failed: {_extract_error_message(response)}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise KisAuthError(
            "KIS websocket approval response was not valid JSON"
        ) from exc
    approval_key = str(payload.get("approval_key") or "")
    if not approval_key:
        message = payload.get("msg1") or payload.get("error_description") or payload
        raise KisAuthError(
            f"KIS websocket approval response did not include approval_key: {message}"
        )
    return approval_key


def parse_token_response(
    payload: dict[str, Any], *, issued_at: datetime
) -> IssuedToken:
    token = str(payload.get("access_token") or "")
    if not token:
        message = payload.get("msg1") or payload.get("error_description") or payload
        raise KisAuthError(
            f"KIS token response did not include access_token: {message}"
        )

    token_type = str(payload.get("token_type") or "Bearer")
    expires_at = _parse_expires_at(payload, issued_at=issued_at)
    return IssuedToken(
        access_token=token,
        token_type=token_type,
        issued_at=issued_at,
        expires_at=expires_at,
        raw=payload,
    )


def mask_sensitive_message(message: str) -> str:
    masked = message
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub(r"\1********", masked)
    return masked


def _parse_expires_at(payload: dict[str, Any], *, issued_at: datetime) -> datetime:
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        try:
            return issued_at + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            pass

    expired_at = payload.get("access_token_token_expired")
    if isinstance(expired_at, str) and expired_at.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
            try:
                parsed = datetime.strptime(expired_at.strip(), fmt)
            except ValueError:
                continue
            local_tz = datetime.now().astimezone().tzinfo
            return parsed.replace(tzinfo=local_tz).astimezone(UTC)

    raise KisAuthError("KIS token response did not include a usable expiration")


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    message = (
        payload.get("msg1")
        or payload.get("error_description")
        or f"HTTP {response.status_code}"
    )
    return mask_sensitive_message(str(message))
