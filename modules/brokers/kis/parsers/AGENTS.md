<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# parsers

## Purpose
Converts KIS REST responses (JSON dicts) or WebSocket frames (pipe-delimited strings) into frozen dataclass instances from `modules.brokers.kis.models`. All type coercion — Decimal/int conversion, date/time parsing, and sign normalization — is concentrated here, keeping model code clean and data-only.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Shared helpers (`output_dict`, `output_rows`, `decimal_or_none`, `int_or_none`, `required_decimal`, `format_date`, `parse_date`, `parse_minute_datetime`) + bulk export of all `parse_*` functions |
| `rest.py` | REST payload parsers — `parse_overseas_current_price`, `parse_overseas_ohlcv_bar`, `parse_overseas_minute_bar`, `parse_overseas_volume_surge_item` |
| `realtime.py` | WebSocket frame parsers — `parse_realtime_frame` (header + body split), `parse_realtime_frame_header`, `parse_trade_payload` (trade tick → `RealtimeTick`), `parse_orderbook_payload` (order book → `OrderBookSnapshot`) — added in Stage 4. Field layouts per `tr_id`: overseas `HDFSCNT0`/`HDFSASP0`, domestic `H0STCNT0`/`H0STASP0` (KRX) |

## For AI Agents

### Working In This Directory
- All parser functions are **pure functions** — no external I/O, class state, or logging.
- Express input validation as explicit exceptions (`ValueError`); the `output_dict`/`output_rows` helpers handle missing `output` keys consistently.
- To add a new endpoint: (1) add a `parse_<...>` function to `rest.py` → (2) add to `__init__.py`'s `__all__` → (3) export from the package surface `modules/brokers/kis/__init__.py`.
- KIS negative number representation uses a sign field (e.g. `PRDY_VRSS_SIGN`) combined with an absolute value — follow the `_apply_sign()` helper pattern.
- Use `decimal_or_none` (nullable) or `required_decimal` (required) for all Decimal conversions to maintain consistency.

### Testing Requirements
- Write response fixtures as inline dicts (avoid external JSON files).
- Test realtime parsers by injecting string payloads directly — do not start a real WebSocket (`tests/brokers/kis/test_realtime.py` pattern).
- Regression cases must cover Decimal precision, sign handling, and date format.

### Common Patterns
- REST parser signature: `parse_<...>(*, market: str, symbol: str, output: dict) -> Model`, or for row-based parsers: `(*, market, row) -> Model`.
- WebSocket parser: `parse_realtime_frame(text)` → `(header, body)` tuple → dispatch to `parse_trade_payload` / `parse_orderbook_payload`.
- `format_date(date)` ↔ `parse_date(str)` handle both `YYYY-MM-DD` and `YYYYMMDD`.
- `parse_minute_datetime("20260513", "143000")` → `datetime(2026, 5, 13, 14, 30, 0)`.

## Dependencies

### Internal (within `modules.brokers.kis` only — no other `modules.*` sibling)
- `modules.brokers.kis.models.*` — target dataclasses
- `modules.brokers.kis.exceptions` — `KisRealtimeError` (on realtime parse failure)

### External
- stdlib: `decimal`, `datetime` only.

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
