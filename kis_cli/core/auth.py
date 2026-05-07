from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from kis_cli.core.endpoints import token_url


class KisAuthError(RuntimeError):
    """Raised when KIS authentication fails."""


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    token_type: str
    issued_at: datetime
    expires_at: datetime
    raw: dict[str, Any]


def issue_access_token(
    *,
    environment: str,
    app_key: str,
    app_secret: str,
) -> IssuedToken:
    issued_at = datetime.now(UTC)
    body = json.dumps(
        {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        token_url(environment),
        data=body,
        headers={
            "content-type": "application/json; charset=utf-8",
            "accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = _read_error_message(exc)
        raise KisAuthError(f"KIS token request failed: {message}") from exc
    except OSError as exc:
        raise KisAuthError(f"KIS token request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise KisAuthError("KIS token response was not valid JSON") from exc

    return parse_token_response(payload, issued_at=issued_at)


def parse_token_response(payload: dict[str, Any], *, issued_at: datetime) -> IssuedToken:
    token = str(payload.get("access_token") or "")
    if not token:
        message = payload.get("msg1") or payload.get("error_description") or payload
        raise KisAuthError(f"KIS token response did not include access_token: {message}")

    token_type = str(payload.get("token_type") or "Bearer")
    expires_at = _parse_expires_at(payload, issued_at=issued_at)
    return IssuedToken(
        access_token=token,
        token_type=token_type,
        issued_at=issued_at,
        expires_at=expires_at,
        raw=payload,
    )


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


def _read_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except OSError:
        return f"HTTP {exc.code}"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return f"HTTP {exc.code}"
    return str(payload.get("msg1") or payload.get("error_description") or f"HTTP {exc.code}")
