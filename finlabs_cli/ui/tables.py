from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, Sequence

from rich.panel import Panel
from rich.table import Table

from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.models.account import Account
from finlabs_cli.models.realtime import ActiveSubscription


def accounts_table(accounts: Sequence[Account]) -> Table:
    table = Table(title="Accounts")
    table.add_column("Alias")
    table.add_column("Broker")
    table.add_column("Owner")
    table.add_column("Account Number")
    table.add_column("Environment")
    table.add_column("Expires At")
    for account in accounts:
        table.add_row(
            account.alias,
            account.broker,
            account.owner_name,
            _mask(account.account_number),
            account.environment,
            account.expires_at,
        )
    return table


def auth_status_table(accounts: Sequence[Account], token_store: JsonTokenStore) -> Table:
    table = Table(title="Auth Status")
    table.add_column("Owner Name")
    table.add_column("Account Number")
    table.add_column("Alias")
    table.add_column("Broker")
    table.add_column("Token Status")
    for account in accounts:
        status = _token_status(token_store.namespaced(account.alias))
        table.add_row(
            account.owner_name,
            _mask(account.account_number),
            account.alias,
            account.broker,
            status,
        )
    return table


def account_summary(account: Account, *, title: str) -> Panel:
    lines = [
        f"Alias: {account.alias}",
        f"Broker: {account.broker}",
        f"Owner: {account.owner_name}",
        f"Account Number: {_mask(account.account_number)}",
        f"Environment: {account.environment}",
        f"Expires At: {account.expires_at}",
    ]
    return Panel("\n".join(lines), title=title)


def chart_table(bars: Iterable) -> Table:
    table = Table(title="Chart")
    table.add_column("Timestamp")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")
    for bar in list(bars)[-30:]:
        timestamp = getattr(bar, "timestamp", None) or (
            f"{getattr(bar, 'local_date', '')} {getattr(bar, 'local_time', '')}".strip()
        )
        table.add_row(
            str(timestamp),
            str(getattr(bar, "open", "")),
            str(getattr(bar, "high", "")),
            str(getattr(bar, "low", "")),
            str(getattr(bar, "close", "")),
            str(getattr(bar, "volume", "")),
        )
    return table


def subscriptions_table(subscriptions: Sequence[ActiveSubscription]) -> Table:
    table = Table(title="Realtime Subscriptions")
    table.add_column("Account")
    table.add_column("Broker")
    table.add_column("Channel")
    table.add_column("Market")
    table.add_column("Symbol")
    table.add_column("TR")
    table.add_column("Key")
    for item in subscriptions:
        table.add_row(
            item.account_alias,
            item.broker,
            item.channel,
            item.market,
            item.symbol,
            item.tr_id,
            item.tr_key,
        )
    return table


def _token_status(store: JsonTokenStore) -> str:
    records = store.records()
    if not records:
        return "missing"
    now = datetime.now(UTC)
    if any(not record.is_expired(now=now) for record in records.values()):
        return "valid"
    return "expired"


def _mask(value: str) -> str:
    if not value:
        return "-"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"
