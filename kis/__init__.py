"""kis — Python SDK for the Korea Investment & Securities Open API.

Public surface:

- `KisClient`          : facade with `domestic`, `overseas`, `realtime` namespaces
- `Credentials`        : app key/secret container with `from_env()` helper
- `EndpointSpec`       : metadata for a single REST endpoint
- exception hierarchy  : `KisError` and its subclasses

This package is transport + parsing only. Persistence, CLI, and config
files live in the `kis_cli` application package.
"""

from __future__ import annotations

from kis.auth import (
    IssuedToken,
    MemoryTokenCache,
    TokenCache,
    TokenRecord,
    issue_access_token,
    issue_access_token_async,
    issue_websocket_approval_key,
    issue_websocket_approval_key_async,
    mask_sensitive_message,
    parse_token_response,
)
from kis.client import KisClient
from kis.config import Credentials, rest_base_url, websocket_url
from kis.endpoints import domestic as endpoints_domestic  # noqa: F401  (trigger registration)
from kis.endpoints import overseas as endpoints_overseas  # noqa: F401
from kis.endpoints.registry import EndpointSpec, lookup, names, register
from kis.models import (
    CurrentPrice,
    DomesticVolumeRankItem,
    FinancialSummary,
    InvestorFlow,
    OhlcvBar,
    OrderBookLevel,
    OrderBookSnapshot,
    OverseasMinuteBar,
    OverseasVolumeSurgeItem,
    ProductInfo,
    RealtimeTick,
    SymbolRecord,
)
from kis.parsers import (
    parse_orderbook_payload,
    parse_domestic_current_price,
    parse_domestic_ohlcv_bar,
    parse_minute_datetime,
    parse_overseas_current_price,
    parse_overseas_minute_bar,
    parse_overseas_ohlcv_bar,
    parse_realtime_frame,
    parse_trade_payload,
    parse_domestic_volume_rank_item,
    parse_financial_summary,
    parse_investor_flow,
    parse_overseas_volume_surge_item,
    parse_product_info,
)
from kis.realtime import RealtimeSession
from kis.symbols import (
    ALL_SYMBOL_MARKETS,
    DOMESTIC_MARKETS,
    OVERSEAS_MARKET_CODES,
    SUPPORTED_SYMBOL_MARKETS,
    download_symbol_master,
    normalize_market,
    parse_symbol_master,
)
from kis.exceptions import (
    KisApiError,
    KisAuthError,
    KisConfigError,
    KisError,
    KisRealtimeError,
    MockNotSupportedError,
)

__all__ = [
    "ALL_SYMBOL_MARKETS",
    "Credentials",
    "CurrentPrice",
    "DOMESTIC_MARKETS",
    "DomesticVolumeRankItem",
    "EndpointSpec",
    "FinancialSummary",
    "IssuedToken",
    "InvestorFlow",
    "KisApiError",
    "KisAuthError",
    "KisClient",
    "KisConfigError",
    "KisError",
    "KisRealtimeError",
    "MemoryTokenCache",
    "MockNotSupportedError",
    "OVERSEAS_MARKET_CODES",
    "OhlcvBar",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "OverseasMinuteBar",
    "OverseasVolumeSurgeItem",
    "ProductInfo",
    "RealtimeSession",
    "RealtimeTick",
    "SUPPORTED_SYMBOL_MARKETS",
    "SymbolRecord",
    "TokenCache",
    "TokenRecord",
    "download_symbol_master",
    "issue_access_token",
    "issue_access_token_async",
    "issue_websocket_approval_key",
    "issue_websocket_approval_key_async",
    "lookup",
    "mask_sensitive_message",
    "names",
    "normalize_market",
    "parse_orderbook_payload",
    "parse_domestic_current_price",
    "parse_domestic_ohlcv_bar",
    "parse_domestic_volume_rank_item",
    "parse_financial_summary",
    "parse_investor_flow",
    "parse_minute_datetime",
    "parse_overseas_current_price",
    "parse_overseas_minute_bar",
    "parse_overseas_ohlcv_bar",
    "parse_overseas_volume_surge_item",
    "parse_product_info",
    "parse_realtime_frame",
    "parse_symbol_master",
    "parse_token_response",
    "parse_trade_payload",
    "register",
    "rest_base_url",
    "websocket_url",
]

__version__ = "0.1.0"
