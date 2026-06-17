from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import finlabs_cli.app.chart_runner as chart_runner
import finlabs_cli.commands.chart as chart_command
from finlabs_cli.app.account_store import AccountStore
from finlabs_cli.app.broker_registry import build_client
from finlabs_cli.app.realtime_manager import RealtimeManager
from finlabs_cli.app.token_store import JsonTokenStore, StoredToken
from finlabs_cli.main import app
from finlabs_cli.models.account import Account
from finlabs_cli.models.realtime import ActiveSubscription, RealtimeSubscriptionStatus
from finlabs_cli.ui import prompts
import finlabs_cli.ui.realtime_tui as realtime_tui
from finlabs_cli.ui.tables import realtime_status_table


def test_app_exposes_command_groups() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "accounts" in result.output
    assert "auth" in result.output
    assert "chart" in result.output
    assert "realtime" in result.output


def test_account_store_round_trips_accounts(tmp_path: Path) -> None:
    store = AccountStore(tmp_path / "accounts.json")
    account = Account(
        id="account-1",
        alias="kiwoom-main",
        broker="kiwoom",
        owner_name="owner",
        environment="mock",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "secret_key": "secret"},
    )

    store.add(account)

    assert store.require("kiwoom-main") == account
    assert store.list() == [account]


def test_token_store_round_trips_namespaced_records(tmp_path: Path) -> None:
    store = JsonTokenStore(tmp_path / "tokens.json", namespace="kiwoom-main")
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    store.set(
        "mock:app",
        StoredToken(
            access_token="token",
            token_type="bearer",
            expires_at=expires_at,
        ),
    )

    record = store.get("mock:app")
    assert record is not None
    assert record.access_token == "token"
    assert not record.is_expired(now=datetime.now(UTC))
    assert list(store.records()) == ["mock:app"]


def test_broker_registry_builds_kiwoom_client(tmp_path: Path) -> None:
    account = Account(
        id="account-1",
        alias="kiwoom-main",
        broker="kiwoom",
        owner_name="owner",
        environment="mock",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "secret_key": "secret"},
    )

    client = build_client(account, JsonTokenStore(tmp_path / "tokens.json"))

    assert client.credentials.app_key == "app"
    assert client.environment == "mock"


def test_text_prompt_applies_default_without_passing_prompt_default(monkeypatch) -> None:
    captured = {}

    class FakeTextPrompt:
        def __init__(self, message: str) -> None:
            captured["message"] = message

        def ask(self) -> str:
            return ""

    monkeypatch.setattr(prompts, "TextPrompt", FakeTextPrompt)

    assert prompts.text("Expired At", default="2026-06-17") == "2026-06-17"
    assert captured["message"] == "Expired At (2026-06-17)"


def test_overseas_chart_runner_uses_kis_adapter_pagination(monkeypatch) -> None:
    account = Account(
        id="account-1",
        alias="kis-main",
        broker="kis",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "app_secret": "secret"},
    )
    captured = {}

    async def fake_fetch_ohlcv_history(client, **kwargs):
        captured["client"] = client
        captured.update(kwargs)
        return ["bar"]

    monkeypatch.setattr(chart_runner, "build_client", lambda *_: _FakeClient())
    monkeypatch.setattr(chart_runner, "fetch_ohlcv_history", fake_fetch_ohlcv_history)

    rows = asyncio.run(
        chart_runner.fetch_overseas_chart(
            account,
            JsonTokenStore(Path("/tmp/unused-tokens.json")),
            symbol="SOXL",
            exchange="AMEX",
            interval="daily",
            start="2026-01-01",
            end="2026-06-17",
            max_pages=250,
        )
    )

    assert rows == ["bar"]
    assert isinstance(captured["client"], _FakeClient)
    assert captured["market"] == "AMEX"
    assert captured["symbol"] == "SOXL"
    assert captured["period"] == "D"
    assert captured["max_pages"] == 250


def test_domestic_minute_chart_runner_passes_tic_scope(monkeypatch) -> None:
    account = Account(
        id="account-1",
        alias="kiwoom-main",
        broker="kiwoom",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "secret_key": "secret"},
    )
    client = _FakeDomesticClient()

    monkeypatch.setattr(chart_runner, "build_client", lambda *_: client)

    rows = asyncio.run(
        chart_runner.fetch_domestic_chart(
            account,
            JsonTokenStore(Path("/tmp/unused-tokens.json")),
            symbol="005930",
            interval="minute",
            base_date="2026-06-17",
            start_date="2026-06-17 090000",
            tic_scope=5,
        )
    )

    assert rows == ["minute"]
    assert client.minute_kwargs == {
        "interval_minutes": 5,
        "base_date": "2026-06-17",
        "start_date": "2026-06-17 090000",
    }


def test_overseas_chart_runner_uses_kis_minute_adapter(monkeypatch) -> None:
    account = Account(
        id="account-1",
        alias="kis-main",
        broker="kis",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "app_secret": "secret"},
    )
    captured = {}

    async def fake_fetch_overseas_minutes(client, **kwargs):
        captured["client"] = client
        captured.update(kwargs)
        return ["minute"]

    monkeypatch.setattr(chart_runner, "build_client", lambda *_: _FakeClient())
    monkeypatch.setattr(
        chart_runner, "fetch_overseas_minutes", fake_fetch_overseas_minutes
    )

    rows = asyncio.run(
        chart_runner.fetch_overseas_chart(
            account,
            JsonTokenStore(Path("/tmp/unused-tokens.json")),
            symbol="AAPL",
            exchange="NASDAQ",
            interval="minute",
            start="2026-06-17 09:30:00",
            end="2026-06-17",
        )
    )

    assert rows == ["minute"]
    assert isinstance(captured["client"], _FakeClient)
    assert captured["market"] == "NASDAQ"
    assert captured["interval_minutes"] == 1
    assert captured["count"] == 120
    assert captured["include_previous"] is True


def test_overseas_chart_runner_rejects_unknown_exchange() -> None:
    account = Account(
        id="account-1",
        alias="kis-main",
        broker="kis",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "app_secret": "secret"},
    )

    with pytest.raises(ValueError, match="exchange must be one of"):
        asyncio.run(
            chart_runner.fetch_overseas_chart(
                account,
                JsonTokenStore(Path("/tmp/unused-tokens.json")),
                symbol="AAPL",
                exchange="LSE",
                interval="daily",
                start="2026-01-01",
                end="2026-06-17",
            )
        )


def test_chart_result_summary_includes_range_count_and_elapsed() -> None:
    row = chart_command._chart_result_row(
        [
            SimpleNamespace(timestamp="2026-01-02"),
            SimpleNamespace(timestamp="2026-06-17"),
        ],
        elapsed_seconds=1.234,
    )

    assert row == ("2026-01-02 - 2026-06-17", "2", "1.23s")


def test_chart_result_summary_uses_minute_bar_local_timestamp() -> None:
    row = chart_command._chart_result_row(
        [
            SimpleNamespace(local_date="2026-06-17", local_time="09:30:00"),
            SimpleNamespace(local_date="2026-06-17", local_time="09:31:00"),
        ],
        elapsed_seconds=60.0,
    )

    assert row == (
        "2026-06-17 09:30:00 - 2026-06-17 09:31:00",
        "2",
        "60.00s",
    )


def test_number_prompt_retries_until_digits(monkeypatch) -> None:
    values = iter(["abc", "5"])
    messages: list[str] = []

    monkeypatch.setattr(chart_command, "text", lambda *_args, **_kwargs: next(values))
    monkeypatch.setattr(
        chart_command.console,
        "print",
        lambda message: messages.append(str(message)),
    )

    assert chart_command._number_prompt("tic_scope", default=1) == 5
    assert messages == ["[red]숫자만 입력하세요.[/red]"]


def test_realtime_manager_records_subscription_status(tmp_path: Path) -> None:
    account = Account(
        id="account-1",
        alias="kis-main",
        broker="kis",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "app_secret": "secret"},
    )
    manager = RealtimeManager(account, JsonTokenStore(tmp_path / "tokens.json"))
    subscription = ActiveSubscription(
        account_alias="kis-main",
        broker="kis",
        channel="trades",
        market="NAS",
        symbol="AAPL",
        tr_id="HDFSCNT0",
        tr_key="DNASAAPL",
    )
    manager._subscriptions.append((subscription, object()))
    manager._statuses[subscription] = RealtimeSubscriptionStatus(subscription)

    manager.record_event(
        SimpleNamespace(
            tr_id="HDFSCNT0",
            tr_key="DNASAAPL",
            exchange_ts="2026-06-17T09:30:00",
        )
    )

    status = manager.subscription_statuses()[0]
    assert status.exchange_ts == "2026-06-17T09:30:00"
    assert status.received == 1


def test_realtime_status_table_uses_monitor_columns() -> None:
    subscription = ActiveSubscription(
        account_alias="kis-main",
        broker="kis",
        channel="trades",
        market="NAS",
        symbol="AAPL",
        tr_id="HDFSCNT0",
        tr_key="DNASAAPL",
    )

    table = realtime_status_table(
        [
            RealtimeSubscriptionStatus(
                subscription=subscription,
                exchange_ts="2026-06-17T09:30:00",
                received=3,
            )
        ]
    )

    assert [column.header for column in table.columns] == [
        "Account",
        "Symbol",
        "Market",
        "TR ID",
        "Received Timestamp(exchange_ts)",
        "Received",
    ]


def test_realtime_tui_mounts_with_status_table(monkeypatch) -> None:
    account = Account(
        id="account-1",
        alias="kis-main",
        broker="kis",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "app_secret": "secret"},
    )

    monkeypatch.setattr(realtime_tui, "RealtimeManager", _FakeRealtimeManager)

    async def run() -> list[str]:
        app = realtime_tui.RealtimeMonitorApp(
            [account],
            JsonTokenStore(Path("/tmp/unused-tokens.json")),
        )
        async with app.run_test():
            table = app.query_one("#subscriptions", realtime_tui.DataTable)
            app.query_one("#activity-log", realtime_tui.RichLog)
            app.query_one("#actions", realtime_tui.TabbedContent)
            app.query_one("#account-select", realtime_tui.Select)
            app.query_one("#account-status", realtime_tui.Static)
            return [column.label.plain for column in table.ordered_columns]

    columns = asyncio.run(run())
    assert columns == [
        "Account",
        "Symbol",
        "Market",
        "TR ID",
        "Received Timestamp(exchange_ts)",
        "Received",
    ]


def test_realtime_tui_keeps_sessions_when_account_changes(monkeypatch) -> None:
    kis_account = Account(
        id="account-1",
        alias="kis-main",
        broker="kis",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "app_secret": "secret"},
    )
    kiwoom_account = Account(
        id="account-2",
        alias="kiwoom-main",
        broker="kiwoom",
        owner_name="owner",
        environment="real",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "secret_key": "secret"},
    )

    monkeypatch.setattr(realtime_tui, "RealtimeManager", _FakeRealtimeManager)

    async def run() -> tuple[bool, int]:
        app = realtime_tui.RealtimeMonitorApp(
            [kis_account, kiwoom_account],
            JsonTokenStore(Path("/tmp/unused-tokens.json")),
        )
        async with app.run_test():
            await app._ensure_connected()
            first_manager = app.managers["kis-main"]
            await app._select_account("kiwoom-main")
            return app.managers["kis-main"] is first_manager, len(app.managers)

    kept, manager_count = asyncio.run(run())
    assert kept is True
    assert manager_count == 1


class _FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeDomesticClient:
    def __init__(self) -> None:
        self.minute_kwargs = {}
        self.domestic = SimpleNamespace(chart=self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def minute(self, _symbol: str, **kwargs):
        self.minute_kwargs = kwargs
        return ["minute"]


class _FakeRealtimeManager:
    def __init__(self, account, _token_store) -> None:
        self._subscription = ActiveSubscription(
            account_alias=account.alias,
            broker=account.broker,
            channel="trades",
            market="NAS",
            symbol="AAPL",
            tr_id="HDFSCNT0",
            tr_key="DNASAAPL",
        )
        self._status = RealtimeSubscriptionStatus(
            subscription=self._subscription,
            exchange_ts="-",
            received=0,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def subscriptions(self):
        return [self._subscription]

    def subscription_statuses(self):
        return [self._status]

    async def unsubscribe_all(self) -> None:
        return None

    async def stream(self):
        await asyncio.Event().wait()
        yield None

    def record_event(self, _event) -> None:
        return None
