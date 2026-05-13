from __future__ import annotations

from pathlib import Path

from kis import CurrentPrice, KisClient, OVERSEAS_MARKET_CODES

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
        return await client.domestic.price.current(
            symbol,
            market=normalized_market,  # type: ignore[arg-type]
        )
    return await client.overseas.price.current(
        symbol,
        exchange=OVERSEAS_MARKET_CODES[normalized_market].upper(),  # type: ignore[arg-type]
        market=normalized_market,
    )
