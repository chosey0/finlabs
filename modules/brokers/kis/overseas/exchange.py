from __future__ import annotations

_EXCHANGE_ALIASES: dict[str, str] = {
    "NASDAQ": "NAS",
    "NASD": "NAS",
    "NYSE": "NYS",
    "NEWYORK": "NYS",
    "NEW_YORK": "NYS",
    "AMEX": "AMS",
    "AMERICAN": "AMS",
    "NYSEAMERICAN": "AMS",
    "NYSE_AMERICAN": "AMS",
    "ARCA": "AMS",
    "NYSEARCA": "AMS",
    "NYSE_ARCA": "AMS",
    "HONGKONG": "HKS",
    "HONG_KONG": "HKS",
    "TOKYO": "TSE",
    "SHANGHAI": "SHS",
    "SHENZHEN": "SZS",
    "HANOI": "HNX",
    "HOCHIMINH": "HSX",
    "HO_CHI_MINH": "HSX",
}

_SUPPORTED_EXCHANGES = {"NAS", "NYS", "AMS", "HKS", "TSE", "SHS", "SZS", "HNX", "HSX"}


def normalize_overseas_exchange(exchange: str) -> str:
    normalized = exchange.strip().upper().replace(" ", "_").replace("-", "_")
    if not normalized:
        raise ValueError("exchange must not be empty")
    normalized = _EXCHANGE_ALIASES.get(normalized, normalized)
    if normalized not in _SUPPORTED_EXCHANGES:
        supported = ", ".join(sorted(_SUPPORTED_EXCHANGES))
        raise ValueError(f"exchange must be one of: {supported}")
    return normalized
