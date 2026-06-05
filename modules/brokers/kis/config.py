from __future__ import annotations

import os
from dataclasses import dataclass

from modules.brokers.kis.exceptions import KisConfigError
from modules.brokers.kis.types import Environment


@dataclass(frozen=True)
class Credentials:
    app_key: str
    app_secret: str
    account_number: str | None = None
    account_product_code: str | None = None

    @classmethod
    def from_env(
        cls,
        *,
        app_key_var: str = "KIS_APP_KEY",
        app_secret_var: str = "KIS_APP_SECRET",
        account_var: str = "KIS_ACCOUNT",
        account_product_var: str = "KIS_ACCOUNT_PRODUCT",
    ) -> "Credentials":
        app_key = os.environ.get(app_key_var)
        app_secret = os.environ.get(app_secret_var)
        if not app_key or not app_secret:
            raise KisConfigError(
                f"{app_key_var} and {app_secret_var} must be set in environment"
            )
        return cls(
            app_key=app_key,
            app_secret=app_secret,
            account_number=os.environ.get(account_var),
            account_product_code=os.environ.get(account_product_var),
        )


_BASE_URLS: dict[Environment, str] = {
    "real": "https://openapi.koreainvestment.com:9443",
    "mock": "https://openapivts.koreainvestment.com:29443",
}

_WS_URLS: dict[Environment, str] = {
    "real": "ws://ops.koreainvestment.com:21000",
    "mock": "ws://ops.koreainvestment.com:31000",
}


def rest_base_url(environment: Environment) -> str:
    try:
        return _BASE_URLS[environment]
    except KeyError as exc:
        allowed = ", ".join(sorted(_BASE_URLS))
        raise KisConfigError(f"environment must be one of: {allowed}") from exc


def websocket_url(environment: Environment) -> str:
    try:
        return _WS_URLS[environment]
    except KeyError as exc:
        allowed = ", ".join(sorted(_WS_URLS))
        raise KisConfigError(f"environment must be one of: {allowed}") from exc
