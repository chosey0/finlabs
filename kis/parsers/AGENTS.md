<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# parsers

## Purpose
KIS REST 응답(JSON dict) 또는 WebSocket 프레임(파이프 구분 문자열)을 `kis.models`의 frozen dataclass 인스턴스로 변환합니다. Decimal/int 변환, 날짜·시간 파싱, 마이너스 부호 정규화 같은 모든 타입 강제 변환이 여기에 집중되어 있어, 모델 코드가 깔끔하게 데이터-only로 유지됩니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | 공용 helper(`output_dict`, `output_rows`, `decimal_or_none`, `int_or_none`, `required_decimal`, `format_date`, `parse_date`, `parse_minute_datetime`) + 모든 `parse_*` 함수 일괄 export |
| `rest.py` | REST 페이로드 파서 — `parse_domestic_current_price`, `parse_overseas_current_price`, `parse_domestic_ohlcv_bar`, `parse_overseas_ohlcv_bar`, `parse_overseas_minute_bar`, `parse_domestic_volume_rank_item`, `parse_overseas_volume_surge_item`, `parse_financial_summary`, `parse_investor_flow`, `parse_product_info` |
| `realtime.py` | WebSocket 프레임 파서 — `parse_realtime_frame` (헤더+바디 split), `parse_realtime_frame_header`, `parse_trade_payload` (체결틱 → `RealtimeTick`), `parse_orderbook_payload` (호가 → `OrderBookSnapshot`) — Stage 4 추가 |

## For AI Agents

### Working In This Directory
- 모든 파서 함수는 **순수 함수**입니다 — 외부 I/O, 클래스 상태, 로깅 없음.
- 입력 유효성 검사는 명시적 예외(`ValueError`)로 표현하고 `output` 키 누락은 `output_dict`/`output_rows` 헬퍼가 일관되게 처리합니다.
- 새 endpoint를 추가하면 (1) `rest.py`에 `parse_<...>` 함수 → (2) `__init__.py` `__all__`에 추가 → (3) `kis/__init__.py` 패키지 surface에도 export.
- KIS 응답의 음수 표기는 `PRDY_VRSS_SIGN` 같은 sign 필드와 절대값을 조합해 결정합니다 — `_apply_sign()` 같은 헬퍼 패턴을 따르세요.
- Decimal 변환은 `decimal_or_none` (선택) / `required_decimal` (필수)를 사용해 일관성을 유지합니다.

### Testing Requirements
- 응답 fixture는 인라인 dict로 작성합니다 (외부 JSON 파일 회피).
- 실시간 파서는 실제 WebSocket을 띄우지 말고 **문자열 페이로드만 직접 주입**해 검증 (`tests/test_realtime.py` 패턴).
- Decimal 정밀도, sign 처리, 날짜 포맷 회귀 케이스를 반드시 포함합니다.

### Common Patterns
- REST 파서 시그니처: `parse_<...>(*, market: str, symbol: str, output: dict) -> Model` 또는 row 기반은 `(*, market, row) -> Model`.
- WebSocket 파서: `parse_realtime_frame(text)` → `(header, body)` tuple → `parse_trade_payload`/`parse_orderbook_payload`에 넘김.
- `format_date(date)` ↔ `parse_date(str)` 는 `YYYY-MM-DD` ↔ `YYYYMMDD` 둘 다 처리.
- `parse_minute_datetime("20260513", "143000")` → `datetime(2026, 5, 13, 14, 30, 0)` 패턴.

## Dependencies

### Internal
- `kis.models.*` — 변환 대상 dataclass들
- `kis.exceptions` — `KisRealtimeError` (realtime 파싱 실패 시)

### External
- stdlib: `decimal`, `datetime` only.

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
