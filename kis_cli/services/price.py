from __future__ import annotations

from pathlib import Path

from modules.brokers.kis import CurrentPrice, KisClient, OVERSEAS_MARKET_CODES

from kis_cli.services.auth import call_with_sdk_client


def get_current_price(
    *,
    symbol: str,
    market: str,
    profile: str | None = None,
    config_path: Path | None = None,
) -> CurrentPrice:
    return call_with_sdk_client(
        lambda client: _get_current_price_async(client, market=market, symbol=symbol),
        profile=profile,
        config_path=config_path,
    )


async def _get_current_price_async(
    client: KisClient,
    *,
    symbol: str,
    market: str,
) -> CurrentPrice:
    normalized_market = market.strip().upper().replace("-", "_")
    if normalized_market in {"KOSPI", "KOSDAQ"}:
        raise ValueError("KIS data queries support overseas stocks only; use Kiwoom for domestic stocks")
    if normalized_market not in OVERSEAS_MARKET_CODES:
        raise ValueError("KIS data queries support overseas stock markets only")
    return await client.overseas.price.current(
        symbol,
        exchange=OVERSEAS_MARKET_CODES[normalized_market].upper(),  # type: ignore[arg-type]
        market=normalized_market,
    )
