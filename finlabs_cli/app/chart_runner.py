from __future__ import annotations

from modules.adapters.brokers.kis.market_data import (
    fetch_ohlcv_history,
    fetch_overseas_minutes,
)
from modules.brokers.kis.overseas.exchange import normalize_overseas_exchange

from finlabs_cli.app.broker_registry import build_client
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.models.account import Account


async def fetch_domestic_chart(
    account: Account,
    token_store: JsonTokenStore,
    *,
    symbol: str,
    interval: str,
    base_date: str | None,
    start_date: str | None = None,
    tic_scope: int | None = None,
):
    async with build_client(account, token_store) as client:
        if interval == "tick":
            return await client.domestic.chart.tick(symbol, start_date=start_date)
        if interval == "minute":
            return await client.domestic.chart.minute(
                symbol,
                interval_minutes=tic_scope or 1,
                base_date=base_date,
                start_date=start_date,
            )
        if interval == "daily":
            return await client.domestic.chart.daily(
                symbol,
                base_date=base_date or "",
                start_date=start_date,
            )
        if interval == "weekly":
            return await client.domestic.chart.weekly(
                symbol,
                base_date=base_date or "",
                start_date=start_date,
            )
        if interval == "monthly":
            return await client.domestic.chart.monthly(
                symbol,
                base_date=base_date or "",
                start_date=start_date,
            )
        if interval == "yearly":
            return await client.domestic.chart.yearly(
                symbol,
                base_date=base_date or "",
                start_date=start_date,
            )
    raise ValueError(f"unsupported domestic interval: {interval}")


async def fetch_overseas_chart(
    account: Account,
    token_store: JsonTokenStore,
    *,
    symbol: str,
    exchange: str,
    interval: str,
    start: str,
    end: str,
    max_pages: int = 100,
):
    market = _market_from_exchange(exchange)
    async with build_client(account, token_store) as client:
        if interval == "minute":
            return await fetch_overseas_minutes(
                client,
                market=market,
                symbol=symbol,
                start=start,
                interval_minutes=1,
                count=120,
                include_previous=True,
            )
        period = {"daily": "D", "weekly": "W", "monthly": "M"}[interval]
        return await fetch_ohlcv_history(
            client,
            market=market,
            symbol=symbol,
            start=start,
            end=end,
            period=period,
            adjusted=True,
            max_pages=max_pages,
        )


def _market_from_exchange(exchange: str) -> str:
    kis_exchange = normalize_overseas_exchange(exchange)
    return {
        "NAS": "NASDAQ",
        "NYS": "NYSE",
        "AMS": "AMEX",
        "HKS": "HONGKONG",
        "TSE": "TOKYO",
        "SHS": "SHANGHAI",
        "SZS": "SHENZHEN",
        "HNX": "HANOI",
        "HSX": "HOCHIMINH",
    }[kis_exchange]
