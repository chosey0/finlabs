from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from kis_cli.config.resolver import ResolvedProfile
from modules.brokers.kis import KisAuthError
from kis_cli.core.endpoints import base_url
from kis_cli.core.token_cache import CachedToken


class KisApiError(RuntimeError):
    """Raised when a KIS REST API call fails."""


@dataclass(frozen=True)
class KisResponse:
    payload: dict[str, Any]
    headers: dict[str, str]


@dataclass(frozen=True)
class KisClient:
    profile: ResolvedProfile
    token: CachedToken

    def get(
        self,
        path: str,
        *,
        tr_id: str,
        params: dict[str, str],
        tr_cont: str = "",
    ) -> dict[str, Any]:
        return self.get_response(
            path,
            tr_id=tr_id,
            params=params,
            tr_cont=tr_cont,
        ).payload

    def get_response(
        self,
        path: str,
        *,
        tr_id: str,
        params: dict[str, str],
        tr_cont: str = "",
    ) -> KisResponse:
        query = urllib.parse.urlencode(params)
        url = f"{base_url(self.profile.environment)}{path}?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "content-type": "application/json; charset=utf-8",
                "accept": "application/json",
                "authorization": f"{self.token.token_type} {self.token.access_token}",
                "appKey": self.profile.app_key,
                "appSecret": self.profile.app_secret,
                "tr_id": tr_id,
                "tr_cont": tr_cont,
                "custtype": "P",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
                headers = {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            raise KisApiError(_read_error_message(exc)) from exc
        except OSError as exc:
            raise KisApiError(f"KIS API request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise KisApiError("KIS API response was not valid JSON") from exc

        _raise_for_kis_error(payload)
        return KisResponse(payload=payload, headers=headers)


def _raise_for_kis_error(payload: dict[str, Any]) -> None:
    rt_cd = payload.get("rt_cd")
    if rt_cd is None or str(rt_cd) == "0":
        return
    message = payload.get("msg1") or payload.get("msg_cd") or payload
    raise KisApiError(f"KIS API returned error: {message}")


def _read_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except OSError:
        return f"KIS API request failed: HTTP {exc.code}"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return f"KIS API request failed: HTTP {exc.code}"

    message = payload.get("msg1") or payload.get("error_description") or f"HTTP {exc.code}"
    if "token" in str(message).lower():
        raise KisAuthError(str(message)) from exc
    return f"KIS API request failed: {message}"
