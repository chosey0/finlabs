from __future__ import annotations

from modules.domain.broker import BrokerCapabilities

KIS_CAPABILITIES = BrokerCapabilities(
    broker="kis",
    supports_daily_ohlcv=True,
    supports_minute_ohlcv=True,
    supports_symbol_master=True,
    supports_current_price=True,
    supports_realtime=True,
)

