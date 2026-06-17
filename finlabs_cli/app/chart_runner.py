from __future__ import annotations

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
):
    async with build_client(account, token_store) as client:
        if interval == "tick":
            return await client.domestic.chart.tick(symbol)
        if interval == "minute":
            return await client.domestic.chart.minute(symbol, base_date=base_date)
        if interval == "daily":
            return await client.domestic.chart.daily(symbol, base_date=base_date or "")
        if interval == "weekly":
            return await client.domestic.chart.weekly(symbol, base_date=base_date or "")
        if interval == "monthly":
            return await client.domestic.chart.monthly(symbol, base_date=base_date or "")
        if interval == "yearly":
            return await client.domestic.chart.yearly(symbol, base_date=base_date or "")
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
):
    async with build_client(account, token_store) as client:
        if interval == "minute":
            return await client.overseas.chart.minute(
                symbol,
                exchange=exchange,
                start=start,
            )
        period = {"daily": "D", "weekly": "W", "monthly": "M"}[interval]
        return await client.overseas.chart.daily(
            symbol,
            exchange=exchange,
            start=start,
            end=end,
            period=period,
        )
