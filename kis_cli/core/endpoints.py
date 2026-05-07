from __future__ import annotations

BASE_URLS = {
    "real": "https://openapi.koreainvestment.com:9443",
    "mock": "https://openapivts.koreainvestment.com:29443",
}
TOKEN_PATH = "/oauth2/tokenP"


def base_url(environment: str) -> str:
    try:
        return BASE_URLS[environment]
    except KeyError as exc:
        allowed = ", ".join(sorted(BASE_URLS))
        raise ValueError(f"environment must be one of: {allowed}") from exc


def token_url(environment: str) -> str:
    return f"{base_url(environment)}{TOKEN_PATH}"
