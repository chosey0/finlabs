from __future__ import annotations

import os
from dataclasses import dataclass

from modules.brokers.kiwoom.exceptions import KiwoomConfigError
from modules.brokers.kiwoom.types import Environment


@dataclass(frozen=True)
class Credentials:
    app_key: str
    secret_key: str

    @classmethod
    def from_env(
        cls,
        *,
        app_key_var: str = "KIWOOM_APP_KEY",
        secret_key_var: str = "KIWOOM_SECRET_KEY",
    ) -> "Credentials":
        app_key = os.environ.get(app_key_var)
        secret_key = os.environ.get(secret_key_var)
        if not app_key or not secret_key:
            raise KiwoomConfigError(
                f"{app_key_var} and {secret_key_var} must be set in environment"
            )
        return cls(app_key=app_key, secret_key=secret_key)


_BASE_URLS: dict[Environment, str] = {
    "real": "https://api.kiwoom.com",
    "mock": "https://mockapi.kiwoom.com",
    "dev": "https://apidev.kiwoom.com",
}

_WS_URLS: dict[Environment, str] = {
    "real": "wss://api.kiwoom.com:10000",
    "mock": "wss://mockapi.kiwoom.com:10000",
    "dev": "wss://apidev.kiwoom.com:10000",
}


def rest_base_url(environment: Environment) -> str:
    try:
        return _BASE_URLS[environment]
    except KeyError as exc:
        allowed = ", ".join(sorted(_BASE_URLS))
        raise KiwoomConfigError(f"environment must be one of: {allowed}") from exc


def websocket_url(environment: Environment) -> str:
    try:
        return _WS_URLS[environment]
    except KeyError as exc:
        allowed = ", ".join(sorted(_WS_URLS))
        raise KiwoomConfigError(f"environment must be one of: {allowed}") from exc
