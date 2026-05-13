"""Endpoint specs for domestic (KRX/NXT) APIs.

Each submodule registers EndpointSpec entries via
`kis.endpoints.registry.register` at import time.
"""

from __future__ import annotations

from kis.endpoints.domestic import (  # noqa: F401
    analysis,
    basic_quote,
    rank,
    realtime,
    sector,
    symbol_info,
)

__all__: tuple[str, ...] = ()
