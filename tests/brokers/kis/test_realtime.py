from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx

import pytest

from modules.brokers.kis import (
    Credentials,
    KisClient,
    KisRealtimeError,
    OrderBookSnapshot,
    RealtimeTick,
    issue_websocket_approval_key,
    issue_websocket_approval_key_async,
    lookup,
    mask_sensitive_message,
)
from modules.brokers.kis.parsers.realtime import (
    parse_realtime_frame,
    parse_trade_payload,
)
from modules.brokers.kis.realtime.subscription import (
    SubscriptionRegistry,
    subscription_for,
)


def test_issue_websocket_approval_key_sync(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return httpx.Response(200, json={"approval_key": "approval-secret-key"})

    monkeypatch.setattr("modules.brokers.kis.auth.oauth.httpx.post", fake_post)

    key = issue_websocket_approval_key(
        environment="real",
        app_key="app-key",
        app_secret="app-secret",
    )

    assert key == "approval-secret-key"
    assert captured["url"] == "https://openapi.koreainvestment.com:9443/oauth2/Approval"
    assert captured["json"] == {
        "grant_type": "client_credentials",
        "appkey": "app-key",
        "secretkey": "app-secret",
    }
    assert "approval-secret-key" not in mask_sensitive_message(
        "approval_key=approval-secret-key"
    )


def test_issue_websocket_approval_key_async_with_shared_client() -> None:
    class FakeAsyncClient:
        async def post(self, url, *, json, headers, timeout):
            return httpx.Response(200, json={"approval_key": "async-approval-key"})

    async def run() -> str:
        return await issue_websocket_approval_key_async(
            environment="mock",
            app_key="app-key",
            app_secret="app-secret",
            client=FakeAsyncClient(),
        )

    assert asyncio.run(run()) == "async-approval-key"


def test_realtime_endpoint_specs_cover_overseas_and_domestic() -> None:
    assert lookup("overseas.realtime.trades").tr_id_for("real") == "HDFSCNT0"
    assert lookup("overseas.realtime.orderbook").tr_id_for("real") == "HDFSASP0"
    assert lookup("domestic.realtime.trades").tr_id_for("real") == "H0STCNT0"
    assert lookup("domestic.realtime.orderbook").tr_id_for("real") == "H0STASP0"
    # KIS supports domestic realtime on the mock environment with the same TR IDs
    assert lookup("domestic.realtime.trades").tr_id_for("mock") == "H0STCNT0"
    assert lookup("domestic.realtime.orderbook").tr_id_for("mock") == "H0STASP0"


def test_parse_overseas_trade_frame() -> None:
    overseas = parse_trade_payload(
        tr_id="HDFSCNT0",
        payload="^".join(_overseas_trade_values()),
        received_at="2026-05-13T00:00:00+00:00",
    )[0]

    assert isinstance(overseas, RealtimeTick)
    assert overseas.market == "NAS"
    assert overseas.symbol == "AAPL"
    assert overseas.price == Decimal("182.86")
    assert overseas.exchange_ts == "2024-05-06 20:22:23"


def test_parse_overseas_orderbook_frame() -> None:
    overseas = parse_realtime_frame(
        f"0|HDFSASP0|001|{'^'.join(_overseas_orderbook_values())}",
        received_at="2026-05-13T00:00:00+00:00",
    )[0]

    assert isinstance(overseas, OrderBookSnapshot)
    assert overseas.market == "NAS"
    assert overseas.symbol == "AAPL"
    assert overseas.asks[0].ask_price == Decimal("182.8700")
    assert overseas.asks[0].bid_volume == 350


def test_parse_domestic_trade_frame() -> None:
    domestic = parse_realtime_frame(
        f"0|H0STCNT0|001|{'^'.join(_domestic_trade_values())}",
        received_at="2026-06-12T00:30:15+00:00",
    )[0]

    assert isinstance(domestic, RealtimeTick)
    assert domestic.market == "KRX"
    assert domestic.symbol == "005930"
    assert domestic.tr_key == "005930"
    assert domestic.price == Decimal("72000")
    assert domestic.volume == 10
    assert domestic.total_volume == 1234567
    assert domestic.bid_price == Decimal("72000")
    assert domestic.ask_price == Decimal("72100")
    assert domestic.exchange_ts == "2026-06-12 09:30:15"


def test_parse_domestic_orderbook_frame() -> None:
    domestic = parse_realtime_frame(
        f"0|H0STASP0|001|{'^'.join(_domestic_orderbook_values())}",
        received_at="2026-06-12T00:30:15+00:00",
    )[0]

    assert isinstance(domestic, OrderBookSnapshot)
    assert domestic.market == "KRX"
    assert domestic.symbol == "005930"
    assert domestic.asks[0].ask_price == Decimal("72100")
    assert domestic.asks[0].bid_price == Decimal("72000")
    assert domestic.asks[9].ask_volume == 1009
    assert domestic.total_ask_volume == 50000
    assert domestic.total_bid_volume == 60000
    assert domestic.exchange_ts == "093015"


def test_realtime_domestic_subscription_uses_bare_symbol_tr_key(monkeypatch) -> None:
    websocket = FakeWebSocket([])

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> None:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("005930", market="KOSPI")
                await ws.subscribe_orderbook("035720", market="KOSDAQ")

    asyncio.run(run())

    sent = [json.loads(message) for message in websocket.sent]
    assert sent[0]["body"]["input"] == {"tr_id": "H0STCNT0", "tr_key": "005930"}
    assert sent[1]["body"]["input"] == {"tr_id": "H0STASP0", "tr_key": "035720"}


def test_realtime_domestic_subscription_rejects_delayed_feed(monkeypatch) -> None:
    websocket = FakeWebSocket([])

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> None:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("005930", market="KRX", feed="delayed")

    try:
        asyncio.run(run())
    except ValueError as exc:
        assert "delayed" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_realtime_overseas_feed_selects_tr_key_prefix(monkeypatch) -> None:
    websocket = FakeWebSocket([])

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> None:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("AAPL", market="NAS", feed="realtime")
                await ws.subscribe_trades("TSLA", market="NAS")
                await ws.subscribe_trades("SOXL", market="AMEX")

    asyncio.run(run())

    sent = [json.loads(message) for message in websocket.sent]
    assert sent[0]["body"]["input"] == {"tr_id": "HDFSCNT0", "tr_key": "RNASAAPL"}
    assert sent[1]["body"]["input"] == {"tr_id": "HDFSCNT0", "tr_key": "DNASTSLA"}
    assert sent[2]["body"]["input"] == {"tr_id": "HDFSCNT0", "tr_key": "DAMSSOXL"}


def test_realtime_subscribe_unsubscribe_state_machine(monkeypatch) -> None:
    websocket = FakeWebSocket([])

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> None:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                subscription = await ws.subscribe_trades("AAPL", market="NAS")
                assert subscription in ws.subscriptions
                await ws.unsubscribe(subscription)
                assert subscription not in ws.subscriptions

    asyncio.run(run())

    sent = [json.loads(message) for message in websocket.sent]
    assert sent[0]["header"]["tr_type"] == "1"
    assert sent[0]["body"]["input"] == {"tr_id": "HDFSCNT0", "tr_key": "DNASAAPL"}
    assert sent[1]["header"]["tr_type"] == "2"


def test_realtime_subscribe_error_does_not_register_subscription(monkeypatch) -> None:
    websocket = QueueWebSocket()

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> int:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                stream_task = asyncio.create_task(_drain_stream(ws))
                await asyncio.sleep(0)
                subscribe_task = asyncio.create_task(
                    ws.subscribe_trades("SPCX", market="NAS", feed="realtime")
                )
                await asyncio.sleep(0)
                websocket.push(
                    json.dumps(
                        {
                            "header": {
                                "tr_id": "HDFSCNT0",
                                "tr_key": "RNASSPCX",
                                "encrypt": "N",
                            },
                            "body": {
                                "rt_cd": "1",
                                "msg1": "SUBSCRIBE ERROR : mci send failed",
                            },
                        }
                    )
                )
                with pytest.raises(KisRealtimeError, match="SUBSCRIBE ERROR"):
                    await subscribe_task
                stream_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await stream_task
                return len(ws.subscriptions)

    assert asyncio.run(run()) == 0


def test_realtime_quick_start_with_mock_websocket(monkeypatch) -> None:
    websocket = FakeWebSocket(
        [
            json.dumps(
                {
                    "header": {
                        "tr_id": "HDFSCNT0",
                        "tr_key": "DNASAAPL",
                        "encrypt": "N",
                    },
                    "body": {"rt_cd": "0", "msg1": "SUBSCRIBE SUCCESS"},
                }
            ),
            f"0|HDFSCNT0|001|{'^'.join(_overseas_trade_values())}",
        ]
    )

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> RealtimeTick:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("AAPL", market="NAS")
                async for event in ws.stream():
                    if isinstance(event, RealtimeTick):
                        return event
        raise AssertionError("expected realtime tick")

    event = asyncio.run(run())

    assert event.symbol == "AAPL"
    assert event.price == Decimal("182.86")
    assert event.exchange_ts == "2024-05-06 20:22:23"


def test_realtime_stream_echoes_pingpong_frames(monkeypatch) -> None:
    pingpong = json.dumps(
        {"header": {"tr_id": "PINGPONG", "datetime": "20260612090000"}}
    )
    websocket = FakeWebSocket(
        [
            pingpong,
            f"0|HDFSCNT0|001|{'^'.join(_overseas_trade_values())}",
        ]
    )

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> RealtimeTick:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("AAPL", market="NAS")
                async for event in ws.stream():
                    if isinstance(event, RealtimeTick):
                        return event
        raise AssertionError("expected realtime tick")

    event = asyncio.run(run())

    assert event.symbol == "AAPL"
    # sent[0] is the subscribe message; the PINGPONG frame must be echoed verbatim
    assert websocket.sent[1] == pingpong


def test_realtime_received_seq_does_not_overlap_across_multi_record_frames(
    monkeypatch,
) -> None:
    first_payload = "^".join(_overseas_trade_values() + _overseas_trade_values())
    second_payload = "^".join(_overseas_trade_values())
    websocket = FakeWebSocket(
        [
            f"0|HDFSCNT0|002|{first_payload}",
            f"0|HDFSCNT0|001|{second_payload}",
        ]
    )

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> list[int]:
        received_seq: list[int] = []
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("AAPL", market="NAS")
                async for event in ws.stream():
                    if isinstance(event, RealtimeTick):
                        received_seq.append(event.received_seq)
                    if len(received_seq) == 3:
                        return received_seq
        raise AssertionError("expected three realtime ticks")

    assert asyncio.run(run()) == [1, 2, 3]


def test_realtime_stream_reconnects_and_resubscribes_after_disconnect(
    monkeypatch,
) -> None:
    first_socket = FakeWebSocket([])  # recv가 즉시 실패해 연결 끊김을 모사한다
    second_socket = FakeWebSocket(
        [f"0|HDFSCNT0|001|{'^'.join(_overseas_trade_values())}"]
    )
    sockets = [first_socket, second_socket]

    async def fake_connect(url):
        return sockets.pop(0)

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> RealtimeTick:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("AAPL", market="NAS")
                async for event in ws.stream():
                    if isinstance(event, RealtimeTick):
                        return event
        raise AssertionError("expected realtime tick after reconnect")

    event = asyncio.run(run())

    assert event.symbol == "AAPL"
    assert first_socket.closed
    # 재연결된 소켓에 등록 구독이 자동으로 다시 전송되어야 한다
    resubscribed = json.loads(second_socket.sent[0])
    assert resubscribed["header"]["tr_type"] == "1"
    assert resubscribed["body"]["input"] == {"tr_id": "HDFSCNT0", "tr_key": "DNASAAPL"}


def test_realtime_subscribe_requires_market_or_exchange(monkeypatch) -> None:
    websocket = FakeWebSocket([])

    async def fake_connect(url):
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> None:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("005930")

    with pytest.raises(ValueError, match="market or exchange"):
        asyncio.run(run())


def test_realtime_unsubscribe_by_symbol_sends_release_message(monkeypatch) -> None:
    websocket = FakeWebSocket([])

    async def fake_connect(url):
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr(
        "modules.brokers.kis.realtime.connection.websockets.connect", fake_connect
    )
    monkeypatch.setattr(
        "modules.brokers.kis.client.KisClient.ensure_approval_key", fake_approval
    )

    async def run() -> int:
        async with KisClient(
            credentials=Credentials("app-key", "app-secret")
        ) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("005930", market="KOSPI")
                await ws.unsubscribe("005930", channel="trades", market="KOSPI")
                return len(ws.subscriptions)

    assert asyncio.run(run()) == 0

    sent = [json.loads(message) for message in websocket.sent]
    assert sent[1]["header"]["tr_type"] == "2"
    assert sent[1]["body"]["input"] == {"tr_id": "H0STCNT0", "tr_key": "005930"}


def test_parse_realtime_frame_rejects_malformed_and_unsupported_frames() -> None:
    with pytest.raises(KisRealtimeError, match="four pipe-delimited parts"):
        parse_realtime_frame("0|HDFSCNT0|001")
    with pytest.raises(KisRealtimeError, match="encryption flag"):
        parse_realtime_frame("X|HDFSCNT0|001|payload")
    with pytest.raises(KisRealtimeError, match="encrypted"):
        parse_realtime_frame("1|HDFSCNT0|001|payload")
    with pytest.raises(KisRealtimeError, match="unsupported realtime tr_id"):
        parse_realtime_frame("0|H0UNKNOWN|001|payload")


def test_parse_trade_payload_returns_none_for_blank_numeric_fields() -> None:
    values = _overseas_trade_values()
    values[11] = ""  # LAST
    values[19] = " "  # EVOL
    values[21] = "1,234,567"  # TAMT — 쉼표 포함 숫자

    tick = parse_trade_payload(
        tr_id="HDFSCNT0",
        payload="^".join(values),
        received_at="2026-06-13T00:00:00+00:00",
    )[0]

    assert tick.price is None
    assert tick.volume is None
    assert tick.amount == Decimal("1234567")


def test_subscription_registry_validates_events_against_active_keys() -> None:
    registry = SubscriptionRegistry()
    subscription = subscription_for(
        channel="trades", symbol="AAPL", venue="NAS", environment="real"
    )
    registry.add(subscription)

    tick = parse_trade_payload(
        tr_id="HDFSCNT0",
        payload="^".join(_overseas_trade_values()),
        received_at="2026-06-13T00:00:00+00:00",
    )[0]
    registry.validate_event(tick)

    registry.discard(subscription)
    with pytest.raises(KisRealtimeError, match="unsubscribed"):
        registry.validate_event(tick)


class FakeWebSocket:
    def __init__(self, frames: list[str]) -> None:
        self.frames = list(frames)
        self.sent: list[str] = []
        self.url = ""
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        if not self.frames:
            raise RuntimeError("no more frames")
        return self.frames.pop(0)

    async def close(self) -> None:
        self.closed = True


class QueueWebSocket:
    def __init__(self) -> None:
        self.frames: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []
        self.url = ""
        self.closed = False

    def push(self, frame: str) -> None:
        self.frames.put_nowait(frame)

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        return await self.frames.get()

    async def close(self) -> None:
        self.closed = True


async def _drain_stream(ws) -> None:
    async for _event in ws.stream():
        pass


def _overseas_trade_values() -> list[str]:
    return [
        "DNASAAPL",
        "AAPL",
        "4",
        "20240506",
        "20240506",
        "202223",
        "20240507",
        "092223",
        "182.50",
        "183.00",
        "182.00",
        "182.86",
        "2",
        "1.23",
        "0.65",
        "182.85",
        "182.87",
        "350",
        "57",
        "10",
        "1000",
        "182860",
        "1",
        "2",
        "50.0",
        "1",
    ]


def _domestic_trade_values() -> list[str]:
    return [
        "005930",
        "093015",
        "72000",
        "2",
        "500",
        "0.70",
        "71900.50",
        "71500",
        "72100",
        "71400",
        "72100",
        "72000",
        "10",
        "1234567",
        "88888888888",
        "100",
        "200",
        "100",
        "120.50",
        "500000",
        "600000",
        "1",
        "54.30",
        "80.50",
        "090001",
        "2",
        "500",
        "092000",
        "5",
        "-100",
        "090500",
        "2",
        "600",
        "20260612",
        "20",
        "N",
        "1000",
        "2000",
        "50000",
        "60000",
        "0.50",
        "1000000",
        "123.40",
        "0",
        "N",
        "71000",
    ]


def _domestic_orderbook_values() -> list[str]:
    values = ["005930", "093015", "0"]
    values.extend(str(72100 + level * 100) for level in range(10))  # ASKP1-10
    values.extend(str(72000 - level * 100) for level in range(10))  # BIDP1-10
    values.extend(str(1000 + level) for level in range(10))  # ASKP_RSQN1-10
    values.extend(str(2000 + level) for level in range(10))  # BIDP_RSQN1-10
    values.extend(
        [
            "50000",
            "60000",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "3",
            "0.00",
            "1234567",
            "0",
            "0",
            "0",
            "0",
            "00",
        ]
    )
    return values


def _overseas_orderbook_values() -> list[str]:
    values = [
        "DNASAAPL",
        "AAPL",
        "4",
        "20240506",
        "202223",
        "20240507",
        "092223",
        "1482",
        "381",
        "0",
        "-10",
    ]
    for level in range(10):
        values.extend(
            [
                f"{Decimal('182.85') - Decimal(level) / 100:.4f}",
                f"{Decimal('182.87') + Decimal(level) / 100:.4f}",
                str(350 + level),
                str(57 + level),
                "0",
                "-10",
            ]
        )
    return values
