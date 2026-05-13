<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# realtime

## Purpose
KIS WebSocket 실시간 시세 세션을 제공합니다. `KisClient.realtime.session()`이 반환하는 `RealtimeSession`은 async context manager로 (1) approval key 획득, (2) WebSocket 연결, (3) 구독/구독취소 메시지 전송, (4) 수신 프레임을 `RealtimeTick`/`OrderBookSnapshot`으로 파싱해 비동기 iterator로 노출합니다. Stage 4에서 코덱스가 추가한 모듈입니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `_RealtimeNamespace` — `KisClient.realtime` 진입점, `session()` 팩토리 + `RealtimeSession` re-export |
| `session.py` | `RealtimeSession` (async context manager), `RealtimeSubscription` (frozen dataclass: channel/tr_id/tr_key/market/symbol), 연결·구독·해제·프레임 수신 로직 |

## For AI Agents

### Working In This Directory
- WebSocket URL은 `kis.config.websocket_url(environment)`에서 가져옵니다. real/mock 모두 KIS가 동일 도메인의 다른 포트로 제공합니다.
- approval key는 REST 토큰과 **별개 캐시 키** (`f"ws:{environment}:{app_key}"`)로 24시간 유효 가정으로 보관합니다 (`KisClient.ensure_approval_key()`).
- 구독은 `EndpointSpec` (e.g. `domestic.realtime.trades`, `overseas.realtime.orderbook`)을 사용해 `tr_id`/`path`를 가져오고, `build_websocket_subscribe_message(tr_type="1")`로 메시지를 만듭니다. 해제는 `tr_type="2"`.
- 수신 프레임은 `parse_realtime_frame(text)`로 헤더와 바디를 분리한 뒤, `tr_id`에 따라 `parse_trade_payload` / `parse_orderbook_payload`로 디스패치합니다.
- 새 실시간 채널을 추가하면 (1) `endpoints/domestic/realtime.py` 또는 `overseas/realtime.py`에 spec 등록 → (2) `RealtimeSession`에 `subscribe_*` 메서드 추가 → (3) `parsers/realtime.py`에 payload 파서 추가.
- 절대 raw WebSocket 메시지를 로그에 남기지 마세요 — 시세/계좌 정보가 섞일 수 있습니다.

### Testing Requirements
- 실제 WebSocket 연결을 띄우지 말고 `parse_realtime_frame()` 등 파서 단위로 검증합니다 (`tests/test_realtime.py`).
- 구독 메시지 생성은 `build_websocket_subscribe_message(...)` 호출 결과 dict를 직접 비교하는 방식이 안전합니다.
- 재연결/타임아웃 로직은 (현재 구현 범위 내에서) 명시적 예외를 던지는지만 확인합니다.

### Common Patterns
- async context manager: `async with client.realtime.session() as session: async for tick in session.iter_ticks(): ...`
- 구독은 멱등하게 — 동일한 `RealtimeSubscription`을 두 번 추가해도 set 기반이라 중복되지 않습니다.
- `received_seq`/`seq` 보존으로 큐 순서 무결성 유지.

## Dependencies

### Internal
- `kis._internal.headers` — `build_websocket_subscribe_message`
- `kis.config` — `websocket_url`
- `kis.endpoints.registry` — `lookup`
- `kis.exceptions` — `KisRealtimeError`
- `kis.models.orderbook`, `kis.models.tick`
- `kis.parsers.realtime` — `parse_realtime_frame`

### External
- `websockets>=13.0`

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
