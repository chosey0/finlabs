from __future__ import annotations

from contextlib import suppress
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    RichLog,
    Select,
    Static,
    TabPane,
    TabbedContent,
)
from textual.worker import Worker

from brokers.kis import KisRealtimeError
from brokers.kiwoom import KiwoomRealtimeError

from finlabs_cli.app.realtime_manager import RealtimeManager
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.models.account import Account
from finlabs_cli.models.realtime import ActiveSubscription


class RealtimeMonitorApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #FFF8E7;
        color: #2D5A27;
    }

    #session-bar {
        dock: top;
        height: 3;
        padding: 0 1;
        layout: horizontal;
        background: #2D5A27;
        color: #FFF8E7;
        border-bottom: solid #D2B48C;
    }

    .metric {
        width: 1fr;
        content-align: center middle;
        text-style: bold;
    }

    #body {
        height: 1fr;
        layout: horizontal;
    }

    #market-pane {
        width: 3fr;
        height: 1fr;
        background: #FFF8E7;
    }

    #action-pane {
        width: 1fr;
        min-width: 34;
        height: 1fr;
        background: #FFF8E7;
        border-left: solid #D2B48C;
    }

    #subscriptions {
        height: 2fr;
        background: #FFF8E7;
        color: #2D5A27;
        border-bottom: solid #D2B48C;
    }

    #activity-log {
        height: 1fr;
        background: #FFF8E7;
        color: #2D5A27;
    }

    #actions {
        height: 1fr;
    }

    TabPane {
        padding: 1;
        background: #FFF8E7;
        color: #2D5A27;
    }

    .field {
        margin-bottom: 1;
        width: 1fr;
    }

    .section-title {
        text-style: bold;
        padding: 0 1;
        background: #96AD90;
        color: #FFF8E7;
    }

    Button {
        margin-top: 1;
        width: 1fr;
    }

    #subscribe {
        background: #2D5A27;
        color: #FFF8E7;
    }

    #unsubscribe {
        background: #D2B48C;
        color: #2D5A27;
    }

    #disconnect {
        background: #2D5A27;
        color: #FFF8E7;
        border: tall #D2B48C;
    }

    Input, Select {
        background: #FFF8E7;
        color: #2D5A27;
        border: tall #96AD90;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        accounts: list[Account],
        token_store: JsonTokenStore,
        *,
        selected_alias: str | None = None,
    ) -> None:
        super().__init__()
        if not accounts:
            raise ValueError("accounts must not be empty")
        self.accounts = tuple(accounts)
        self.token_store = token_store
        self.account = self._account_by_alias(selected_alias) or self.accounts[0]
        self.managers: dict[str, RealtimeManager] = {}
        self._stream_workers: dict[str, Worker[Any]] = {}
        self._rendered_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="session-bar"):
            yield Static("Connecting...", id="connection-status", classes="metric")
            yield Static("Account -", id="account-status", classes="metric")
            yield Static("Active 0", id="active-count", classes="metric")
            yield Static("Received 0", id="received-count", classes="metric")
        with Horizontal(id="body"):
            with Vertical(id="market-pane"):
                yield Static("Subscriptions", classes="section-title")
                yield DataTable(id="subscriptions")
                yield Static("Activity", classes="section-title")
                yield RichLog(
                    id="activity-log",
                    max_lines=200,
                    wrap=True,
                    markup=False,
                    highlight=False,
                )
            with Container(id="action-pane"):
                with TabbedContent(id="actions"):
                    with TabPane("Subscribe", id="subscribe-tab"):
                        yield Select(
                            self._account_options(),
                            value=self.account.alias,
                            allow_blank=False,
                            id="account-select",
                            classes="field",
                        )
                        yield Select(
                            [("Trades", "trades"), ("Orderbook", "orderbook")],
                            value="trades",
                            allow_blank=False,
                            id="channel",
                            classes="field",
                        )
                        yield Input(placeholder="Ticker", id="symbol", classes="field")
                        yield Input(
                            value="NAS" if self.account.broker == "kis" else "KRX",
                            placeholder="Market/Exchange",
                            id="market",
                            classes="field",
                        )
                        yield Select(
                            [("Delayed", "delayed"), ("Realtime", "realtime")],
                            value="delayed",
                            allow_blank=False,
                            id="feed",
                            classes="field",
                            disabled=self.account.broker != "kis",
                        )
                        yield Button("Subscribe", id="subscribe", variant="primary")
                    with TabPane("Unsubscribe", id="unsubscribe-tab"):
                        yield Select(
                            [],
                            prompt="Subscription",
                            allow_blank=True,
                            id="unsubscribe-target",
                            classes="field",
                        )
                        yield Button("Unsubscribe", id="unsubscribe", variant="warning")
                    with TabPane("Session", id="session-tab"):
                        yield Static("", id="session-details")
                        yield Button("Disconnect", id="disconnect", variant="error")
                        yield Button("Exit", id="exit", variant="default")
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#subscriptions", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("Account", key="account")
        table.add_column("Symbol", key="symbol")
        table.add_column("Market", key="market")
        table.add_column("TR ID", key="tr_id")
        table.add_column("Received Timestamp(exchange_ts)", key="exchange_ts")
        table.add_column("Received", key="received")
        self._refresh_session_details()
        self._refresh_summary(connection="Disconnected")
        self._log("select an account and subscribe to connect")
        self._refresh(update_options=True)

    async def on_unmount(self) -> None:
        await self._disconnect_all(refresh=False)

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "account-select":
            return
        if not isinstance(event.value, str):
            return
        await self._select_account(event.value)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "subscribe":
            await self._subscribe(event.button)
            return
        if event.button.id == "unsubscribe":
            await self._unsubscribe(event.button)
            return
        if event.button.id == "disconnect":
            await self.action_disconnect()
            return
        if event.button.id == "exit":
            await self.action_quit()

    async def action_disconnect(self) -> None:
        self._set_status(f"Disconnecting {self.account.alias}...")
        self._log(f"disconnecting {self.account.alias}")
        await self._disconnect_current()

    async def action_quit(self) -> None:
        await self._disconnect_all(refresh=False)
        self.exit()

    async def _select_account(self, alias: str) -> None:
        account = self._account_by_alias(alias)
        if account is None or account == self.account:
            return
        self.account = account
        self._sync_account_defaults()
        self._refresh_session_details()
        self._refresh_summary()
        self._log(f"selected {self.account.alias} ({self.account.broker})")

    async def _disconnect_current(self, *, refresh: bool = True) -> None:
        await self._disconnect_account(self.account.alias, refresh=refresh)

    async def _disconnect_all(self, *, refresh: bool = True) -> None:
        for alias in list(self.managers):
            await self._disconnect_account(alias, refresh=False)
        if refresh:
            self._refresh(update_options=True)
            self._refresh_summary(connection="Disconnected")

    async def _disconnect_account(self, alias: str, *, refresh: bool = True) -> None:
        worker = self._stream_workers.pop(alias, None)
        if worker is not None:
            worker.cancel()
        manager = self.managers.pop(alias, None)
        if manager is None:
            if refresh:
                self._refresh(update_options=True)
                self._refresh_summary(connection=self._connection_label())
            return
        with suppress(Exception):
            await manager.unsubscribe_all()
        with suppress(Exception):
            await manager.__aexit__(None, None, None)
        if refresh:
            self._refresh(update_options=True)
            self._refresh_summary(connection=self._connection_label())
            self._log(f"disconnected {alias}")

    async def _ensure_connected(self) -> bool:
        alias = self.account.alias
        if alias in self.managers:
            return True
        self._set_status(f"Connecting {alias}...")
        self._log(f"connecting {alias} ({self.account.broker})")
        manager = RealtimeManager(self.account, self.token_store)
        try:
            await manager.__aenter__()
        except Exception as exc:
            self._set_status(f"Connect failed: {exc}")
            self._log(f"connect failed: {exc}")
            self.notify(str(exc), title="Connect failed", severity="error")
            return False
        self.managers[alias] = manager
        self._set_status(self._connection_label())
        self._log(f"connected {alias} ({self.account.broker})")
        self._stream_workers[alias] = self.run_worker(
            self._stream_events(alias, manager),
            name=f"realtime-stream-{alias}",
            exit_on_error=False,
        )
        self._refresh(update_options=True)
        return True

    async def _subscribe(self, button: Button) -> None:
        symbol = self.query_one("#symbol", Input).value.strip()
        venue = self.query_one("#market", Input).value.strip()
        channel = str(self.query_one("#channel", Select).value)
        feed = self._selected_feed(venue)
        if not symbol:
            self.notify("Ticker is required", severity="warning")
            self._log("subscribe blocked: ticker is required")
            return
        if not await self._ensure_connected():
            return
        button.disabled = True
        self._set_status(f"Subscribing {symbol.upper()}...")
        self._log(f"subscribe requested {channel} {venue} {symbol.upper()}")
        manager = self.managers[self.account.alias]
        try:
            await manager.subscribe(
                channel=channel,
                symbol=symbol,
                venue=venue,
                feed=feed,
            )
        except (KisRealtimeError, KiwoomRealtimeError, ValueError) as exc:
            self._set_status(f"Subscribe failed: {exc}")
            self._log(f"subscribe failed: {exc}")
            self.notify(str(exc), title="Subscribe failed", severity="error")
        else:
            self.query_one("#symbol", Input).value = ""
            self._set_status(f"Subscribed {symbol.upper()}")
            self._log(f"subscribed {symbol.upper()}")
            self._refresh(update_options=True)
        finally:
            button.disabled = False

    async def _unsubscribe(self, button: Button) -> None:
        selected = self.query_one("#unsubscribe-target", Select).value
        subscription = self._subscription_by_key(str(selected))
        if subscription is None:
            self.notify("Select a subscription", severity="warning")
            self._log("unsubscribe blocked: no subscription selected")
            return
        button.disabled = True
        self._set_status(f"Unsubscribing {subscription.symbol}...")
        manager = self.managers.get(subscription.account_alias)
        if manager is None:
            self.notify("Subscription session is not connected", severity="warning")
            self._log(f"unsubscribe blocked: {subscription.account_alias} disconnected")
            button.disabled = False
            return
        self._log(
            f"unsubscribe requested {subscription.account_alias} "
            f"{subscription.market} {subscription.symbol}"
        )
        try:
            await manager.unsubscribe(subscription)
        except (KisRealtimeError, KiwoomRealtimeError) as exc:
            self._set_status(f"Unsubscribe failed: {exc}")
            self._log(f"unsubscribe failed: {exc}")
            self.notify(str(exc), title="Unsubscribe failed", severity="error")
        else:
            self._set_status(f"Unsubscribed {subscription.symbol}")
            self._log(f"unsubscribed {subscription.symbol}")
            self._refresh(update_options=True)
        finally:
            button.disabled = False

    async def _stream_events(self, alias: str, manager: RealtimeManager) -> None:
        try:
            async for event in manager.stream():
                if self.managers.get(alias) is not manager:
                    return
                manager.record_event(event)
                self._refresh(update_options=False)
        except Exception as exc:
            self._set_status(f"Stream stopped: {exc}")
            self._log(f"stream stopped: {exc}")
            self.notify(str(exc), title="Realtime stream stopped", severity="error")

    def _refresh(self, *, update_options: bool) -> None:
        table = self.query_one("#subscriptions", DataTable)
        statuses = self._subscription_statuses()
        keys = {self._subscription_key(status.subscription) for status in statuses}
        if keys != self._rendered_keys:
            table.clear()
            self._rendered_keys = set()
            for status in statuses:
                subscription = status.subscription
                key = self._subscription_key(subscription)
                table.add_row(
                    subscription.account_alias,
                    subscription.symbol,
                    subscription.market,
                    subscription.tr_id,
                    status.exchange_ts,
                    str(status.received),
                    key=key,
                )
                self._rendered_keys.add(key)
        else:
            for status in statuses:
                subscription = status.subscription
                key = self._subscription_key(subscription)
                table.update_cell(key, "exchange_ts", status.exchange_ts)
                table.update_cell(key, "received", str(status.received))
        self._refresh_summary()
        if update_options:
            self._refresh_unsubscribe_options()

    def _refresh_unsubscribe_options(self) -> None:
        subscriptions = self._subscriptions()
        target = self.query_one("#unsubscribe-target", Select)
        target.set_options(
            [
                (
                    f"{item.account_alias} {item.channel} {item.market} {item.symbol}",
                    self._subscription_key(item),
                )
                for item in subscriptions
            ]
        )

    def _selected_feed(self, venue: str) -> str | None:
        if self.account.broker != "kis":
            return None
        if venue.strip().upper() in {"KRX", "KOSPI", "KOSDAQ"}:
            return None
        return str(self.query_one("#feed", Select).value)

    def _subscription_by_key(self, key: str) -> ActiveSubscription | None:
        for subscription in self._subscriptions():
            if self._subscription_key(subscription) == key:
                return subscription
        return None

    def _subscription_key(self, subscription: ActiveSubscription) -> str:
        return (
            f"{subscription.account_alias}:"
            f"{subscription.channel}:{subscription.tr_id}:{subscription.tr_key}"
        )

    def _set_status(self, message: str) -> None:
        self.query_one("#connection-status", Static).update(message)

    def _refresh_summary(self, connection: str | None = None) -> None:
        statuses = self._subscription_statuses()
        received = sum(status.received for status in statuses)
        if connection is not None:
            self.query_one("#connection-status", Static).update(connection)
        self.query_one("#account-status", Static).update(
            f"{self.account.alias} | {self.account.broker}"
        )
        self.query_one("#active-count", Static).update(f"Active {len(statuses)}")
        self.query_one("#received-count", Static).update(f"Received {received}")

    def _log(self, message: str) -> None:
        self.query_one("#activity-log", RichLog).write(message)

    def _clear_subscription_table(self) -> None:
        self.query_one("#subscriptions", DataTable).clear()
        self._rendered_keys = set()

    def _sync_account_defaults(self) -> None:
        self.query_one("#account-select", Select).value = self.account.alias
        self.query_one("#market", Input).value = (
            "NAS" if self.account.broker == "kis" else "KRX"
        )
        self.query_one("#feed", Select).disabled = self.account.broker != "kis"

    def _refresh_session_details(self) -> None:
        self.query_one("#session-details", Static).update(
            "\n".join(
                [
                    f"Alias: {self.account.alias}",
                    f"Broker: {self.account.broker}",
                    f"Environment: {self.account.environment}",
                ]
            )
        )

    def _account_options(self) -> list[tuple[str, str]]:
        return [
            (f"{account.alias} ({account.broker})", account.alias)
            for account in self.accounts
        ]

    def _account_by_alias(self, alias: str | None) -> Account | None:
        if alias is None:
            return None
        for account in self.accounts:
            if account.alias == alias:
                return account
        return None

    def _subscriptions(self) -> list[ActiveSubscription]:
        items: list[ActiveSubscription] = []
        for manager in self.managers.values():
            items.extend(manager.subscriptions())
        return items

    def _subscription_statuses(self):
        items = []
        for manager in self.managers.values():
            items.extend(manager.subscription_statuses())
        return items

    def _connection_label(self) -> str:
        if not self.managers:
            return "Disconnected"
        return f"Connected {len(self.managers)}"
