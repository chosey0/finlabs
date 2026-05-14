<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# realtime

## Purpose
Provides a KIS WebSocket realtime quote session. `RealtimeSession`, returned by `KisClient.realtime.session()`, is an async context manager that: (1) obtains an approval key, (2) establishes a WebSocket connection, (3) sends subscribe/unsubscribe messages, and (4) parses incoming frames into `RealtimeTick`/`OrderBookSnapshot` and exposes them as an async iterator. This module was added in Stage 4.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `_RealtimeNamespace` — `KisClient.realtime` entry point, `session()` factory + `RealtimeSession` re-export |
| `session.py` | `RealtimeSession` (async context manager), `RealtimeSubscription` (frozen dataclass: channel/tr_id/tr_key/market/symbol), connection/subscribe/unsubscribe/frame-receive logic |

## For AI Agents

### Working In This Directory
- Retrieve the WebSocket URL from `kis.config.websocket_url(environment)`. KIS provides both real and paper-trading on the same domain with different ports.
- The approval key uses a **separate cache key** (`f"ws:{environment}:{app_key}"`) from the REST token, assumed valid for 24 hours (`KisClient.ensure_approval_key()`).
- Subscriptions use `EndpointSpec` (e.g. `overseas.realtime.orderbook`) to retrieve `tr_id`/`path`, then build messages via `build_websocket_subscribe_message(tr_type="1")`. Unsubscription uses `tr_type="2"`.
- Incoming frames are split by `parse_realtime_frame(text)`, then dispatched to `parse_trade_payload` / `parse_orderbook_payload` based on `tr_id`.
- To add a new realtime channel: (1) register spec in `endpoints/overseas/realtime.py` → (2) add `subscribe_*` method to `RealtimeSession` → (3) add payload parser in `parsers/realtime.py`.
- Never log raw WebSocket messages — they may contain quote or account information.

### Testing Requirements
- Do not start a real WebSocket connection. Validate at the parser unit level via `parse_realtime_frame()` (`tests/test_realtime.py`).
- Testing subscription message construction by comparing the result of `build_websocket_subscribe_message(...)` directly against an expected dict is the safest approach.
- For reconnect/timeout logic, verify only that an explicit exception is raised (within the current implementation scope).

### Common Patterns
- Async context manager usage: `async with client.realtime.session() as session: async for tick in session.iter_ticks(): ...`
- Subscriptions are idempotent — adding the same `RealtimeSubscription` twice is a no-op due to set-based deduplication.
- Preserve `received_seq`/`seq` to maintain queue ordering integrity.

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

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
