from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from modules.brokers.kiwoom.config import rest_base_url
from modules.brokers.kiwoom.exceptions import KiwoomAuthError
from modules.brokers.kiwoom.types import Environment

TOKEN_PATH = "/oauth2/token"
REVOKE_PATH = "/oauth2/revoke"
KST = ZoneInfo("Asia/Seoul")

SECRET_PATTERNS = (
    re.compile(r"(app(?:key|_key)[\"':=\s]+)([A-Za-z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(secret(?:key|_key)[\"':=\s]+)([A-Za-z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(token[\"':=\s]+)([A-Za-z0-9._\-]{8,})", re.IGNORECASE),
)


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    token_type: str
    issued_at: datetime
    expires_at: datetime
    raw: dict[str, Any]


def token_url(environment: Environment) -> str:
    return f"{rest_base_url(environment)}{TOKEN_PATH}"


def revoke_url(environment: Environment) -> str:
    return f"{rest_base_url(environment)}{REVOKE_PATH}"


def issue_access_token(
    *,
    environment: Environment,
    app_key: str,
    secret_key: str,
    timeout_seconds: float = 30.0,
) -> IssuedToken:
    issued_at = datetime.now(UTC)
    try:
        response = httpx.post(
            token_url(environment),
            json=_token_request_body(app_key, secret_key),
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KiwoomAuthError(f"Kiwoom token request failed: {exc}") from exc
    return _interpret_token_response(response, issued_at=issued_at)


async def issue_access_token_async(
    *,
    environment: Environment,
    app_key: str,
    secret_key: str,
    timeout_seconds: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> IssuedToken:
    issued_at = datetime.now(UTC)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)
    try:
        response = await client.post(
            token_url(environment),
            json=_token_request_body(app_key, secret_key),
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KiwoomAuthError(f"Kiwoom token request failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()
    return _interpret_token_response(response, issued_at=issued_at)


def revoke_access_token(
    *,
    environment: Environment,
    app_key: str,
    secret_key: str,
    token: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    try:
        response = httpx.post(
            revoke_url(environment),
            json=_revoke_request_body(app_key, secret_key, token),
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KiwoomAuthError(f"Kiwoom token revoke request failed: {exc}") from exc
    return _interpret_revoke_response(response)


async def revoke_access_token_async(
    *,
    environment: Environment,
    app_key: str,
    secret_key: str,
    token: str,
    timeout_seconds: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_seconds)
    try:
        response = await client.post(
            revoke_url(environment),
            json=_revoke_request_body(app_key, secret_key, token),
            headers=_TOKEN_REQUEST_HEADERS,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KiwoomAuthError(f"Kiwoom token revoke request failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()
    return _interpret_revoke_response(response)


def parse_token_response(
    payload: dict[str, Any], *, issued_at: datetime
) -> IssuedToken:
    token = str(payload.get("token") or "")
    if not token:
        message = payload.get("return_msg") or payload
        raise KiwoomAuthError(
            f"Kiwoom token response did not include token: {message}"
        )
    return_code = payload.get("return_code")
    if return_code is not None and str(return_code) != "0":
        raise KiwoomAuthError(str(payload.get("return_msg") or payload))

    return IssuedToken(
        access_token=token,
        token_type=str(payload.get("token_type") or "bearer"),
        issued_at=issued_at,
        expires_at=_parse_expires_dt(payload.get("expires_dt")),
        raw=payload,
    )


def mask_sensitive_message(message: str) -> str:
    masked = message
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub(r"\1***", masked)
    return masked


_TOKEN_REQUEST_HEADERS = {
    "content-type": "application/json;charset=UTF-8",
    "accept": "application/json",
}


def _token_request_body(app_key: str, secret_key: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "secretkey": secret_key,
    }


def _revoke_request_body(
    app_key: str, secret_key: str, token: str
) -> dict[str, str]:
    return {"appkey": app_key, "secretkey": secret_key, "token": token}


def _interpret_token_response(
    response: httpx.Response, *, issued_at: datetime
) -> IssuedToken:
    payload = _json_response(response, action="token request")
    if response.status_code >= 400:
        raise KiwoomAuthError(
            f"Kiwoom token request failed: {_extract_error_message(payload)}"
        )
    return parse_token_response(payload, issued_at=issued_at)


def _interpret_revoke_response(response: httpx.Response) -> dict[str, Any]:
    payload = _json_response(response, action="token revoke")
    if response.status_code >= 400 or str(payload.get("return_code", "0")) != "0":
        raise KiwoomAuthError(
            f"Kiwoom token revoke failed: {_extract_error_message(payload)}"
        )
    return payload


def _json_response(response: httpx.Response, *, action: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise KiwoomAuthError(f"Kiwoom {action} response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise KiwoomAuthError(f"Kiwoom {action} response was not a JSON object")
    return payload


def _extract_error_message(payload: dict[str, Any]) -> str:
    return str(payload.get("return_msg") or payload)


def _parse_expires_dt(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise KiwoomAuthError("Kiwoom token response did not include expires_dt")
    try:
        expires_kst = datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except ValueError as exc:
        raise KiwoomAuthError(f"invalid Kiwoom token expires_dt: {text}") from exc
    return expires_kst.astimezone(UTC)
