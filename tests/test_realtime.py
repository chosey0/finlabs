from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx

from kis import (
    Credentials,
    KisClient,
    OrderBookSnapshot,
    RealtimeTick,
    issue_websocket_approval_key,
    issue_websocket_approval_key_async,
    lookup,
    mask_sensitive_message,
)
from kis.parsers.realtime import parse_orderbook_payload, parse_realtime_frame, parse_trade_payload


def test_issue_websocket_approval_key_sync(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return httpx.Response(200, json={"approval_key": "approval-secret-key"})

    monkeypatch.setattr("kis.auth.oauth.httpx.post", fake_post)

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


def test_realtime_endpoint_specs_are_registered() -> None:
    assert lookup("domestic.realtime.trades").tr_id_for("mock") == "H0STCNT0"
    assert lookup("domestic.realtime.orderbook").tr_id_for("real") == "H0STASP0"
    assert lookup("overseas.realtime.trades").tr_id_for("real") == "HDFSCNT0"
    assert lookup("overseas.realtime.orderbook").tr_id_for("real") == "HDFSASP0"


def test_parse_domestic_and_overseas_trade_frames() -> None:
    domestic = parse_realtime_frame(
        f"0|H0STCNT0|001|{'^'.join(_domestic_trade_values())}",
        received_at="2026-05-13T00:00:00+00:00",
    )[0]
    overseas = parse_trade_payload(
        tr_id="HDFSCNT0",
        payload="^".join(_overseas_trade_values()),
        received_at="2026-05-13T00:00:00+00:00",
    )[0]

    assert isinstance(domestic, RealtimeTick)
    assert domestic.market == "KRX"
    assert domestic.symbol == "005930"
    assert domestic.price == Decimal("71900")
    assert domestic.exchange_ts == "2023-06-12 09:33:54"
    assert isinstance(overseas, RealtimeTick)
    assert overseas.market == "NAS"
    assert overseas.symbol == "AAPL"
    assert overseas.price == Decimal("182.86")
    assert overseas.exchange_ts == "2024-05-06 20:22:23"


def test_parse_orderbook_frames() -> None:
    domestic = parse_orderbook_payload(
        tr_id="H0STASP0",
        payload="^".join(_domestic_orderbook_values()),
        received_at="2026-05-13T00:00:00+00:00",
    )[0]
    overseas = parse_realtime_frame(
        f"0|HDFSASP0|001|{'^'.join(_overseas_orderbook_values())}",
        received_at="2026-05-13T00:00:00+00:00",
    )[0]

    assert isinstance(domestic, OrderBookSnapshot)
    assert domestic.symbol == "005930"
    assert domestic.asks[0].ask_price == Decimal("71900")
    assert domestic.asks[0].bid_price == Decimal("71800")
    assert domestic.total_ask_volume == 1159362
    assert isinstance(overseas, OrderBookSnapshot)
    assert overseas.market == "NAS"
    assert overseas.symbol == "AAPL"
    assert overseas.asks[0].ask_price == Decimal("182.8700")
    assert overseas.asks[0].bid_volume == 350


def test_realtime_subscribe_unsubscribe_state_machine(monkeypatch) -> None:
    websocket = FakeWebSocket([])

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr("kis.realtime.session.websockets.connect", fake_connect)
    monkeypatch.setattr("kis.client.KisClient.ensure_approval_key", fake_approval)

    async def run() -> None:
        async with KisClient(credentials=Credentials("app-key", "app-secret")) as client:
            async with client.realtime.session() as ws:
                subscription = await ws.subscribe_trades("005930", market="KRX")
                assert subscription in ws.subscriptions
                await ws.unsubscribe(subscription)
                assert subscription not in ws.subscriptions

    asyncio.run(run())

    sent = [json.loads(message) for message in websocket.sent]
    assert sent[0]["header"]["tr_type"] == "1"
    assert sent[0]["body"]["input"] == {"tr_id": "H0STCNT0", "tr_key": "005930"}
    assert sent[1]["header"]["tr_type"] == "2"


def test_realtime_quick_start_with_mock_websocket(monkeypatch) -> None:
    websocket = FakeWebSocket(
        [
            json.dumps(
                {
                    "header": {"tr_id": "H0STCNT0", "tr_key": "005930", "encrypt": "N"},
                    "body": {"rt_cd": "0", "msg1": "SUBSCRIBE SUCCESS"},
                }
            ),
            f"0|H0STCNT0|001|{'^'.join(_domestic_trade_values())}",
        ]
    )

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr("kis.realtime.session.websockets.connect", fake_connect)
    monkeypatch.setattr("kis.client.KisClient.ensure_approval_key", fake_approval)

    async def run() -> RealtimeTick:
        async with KisClient(credentials=Credentials("app-key", "app-secret")) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("005930", market="KRX")
                async for event in ws.stream():
                    if isinstance(event, RealtimeTick):
                        return event
        raise AssertionError("expected realtime tick")

    event = asyncio.run(run())

    assert event.symbol == "005930"
    assert event.price == Decimal("71900")
    assert event.exchange_ts == "2023-06-12 09:33:54"


def test_realtime_received_seq_does_not_overlap_across_multi_record_frames(
    monkeypatch,
) -> None:
    first_payload = "^".join(_domestic_trade_values() + _domestic_trade_values())
    second_payload = "^".join(_domestic_trade_values())
    websocket = FakeWebSocket(
        [
            f"0|H0STCNT0|002|{first_payload}",
            f"0|H0STCNT0|001|{second_payload}",
        ]
    )

    async def fake_connect(url):
        websocket.url = url
        return websocket

    async def fake_approval(self):
        return "approval-key"

    monkeypatch.setattr("kis.realtime.session.websockets.connect", fake_connect)
    monkeypatch.setattr("kis.client.KisClient.ensure_approval_key", fake_approval)

    async def run() -> list[int]:
        received_seq: list[int] = []
        async with KisClient(credentials=Credentials("app-key", "app-secret")) as client:
            async with client.realtime.session() as ws:
                await ws.subscribe_trades("005930", market="KRX")
                async for event in ws.stream():
                    if isinstance(event, RealtimeTick):
                        received_seq.append(event.received_seq)
                    if len(received_seq) == 3:
                        return received_seq
        raise AssertionError("expected three realtime ticks")

    assert asyncio.run(run()) == [1, 2, 3]


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


def _domestic_trade_values() -> list[str]:
    return [
        "005930",
        "093354",
        "71900",
        "5",
        "-100",
        "-0.14",
        "72023.83",
        "72100",
        "72400",
        "71700",
        "71900",
        "71800",
        "1",
        "3052507",
        "219853241700",
        "5105",
        "6937",
        "1832",
        "84.90",
        "1366314",
        "1159996",
        "1",
        "0.39",
        "20.28",
        "090020",
        "5",
        "-200",
        "090820",
        "5",
        "-500",
        "092619",
        "2",
        "200",
        "20230612",
        "20",
        "N",
        "65945",
        "216924",
        "1118750",
        "2199206",
        "0.05",
        "2424142",
        "125.92",
        "0",
        "",
        "72100",
    ]


def _domestic_orderbook_values() -> list[str]:
    return [
        "005930",
        "093730",
        "0",
        *[str(71900 + index * 100) for index in range(10)],
        *[str(71800 - index * 100) for index in range(10)],
        *[str(90000 + index) for index in range(10)],
        *[str(150000 + index) for index in range(10)],
        "1159362",
        "2095167",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "5",
        "-100.00",
        "3159115",
        "0",
        "8",
        "0",
        "0",
        "0",
    ]


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
