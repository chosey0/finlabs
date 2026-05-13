<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# overseas

## Purpose
해외 거래소(NAS/NYS/AMS/HKS/TSE/SHS/SZS/HNX/HSX) REST API의 **고수준 클라이언트**입니다. 국내와 달리 KIS는 해외 엔드포인트 대부분에 모의투자 TR ID를 제공하지 않으므로, 등록된 spec의 `tr_id_mock`이 `None`인 경우 `environment="mock"`로 사용 시 자동 `MockNotSupportedError`가 발생합니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `_OverseasNamespace` — `KisClient.overseas` 진입점, 하위 API 인스턴스(`price`, `chart`, `analysis`) 조립 |
| `price.py` | `OverseasPriceAPI.current(symbol, *, exchange, market=None)` → `CurrentPrice`. `exchange`는 3자 KIS 코드 (`NAS`/`NYS`/...) |
| `chart.py` | `OverseasChartAPI.daily(period="D"|"W"|"M")` (HHDFS76240000, KEYB 페이지네이션), `minute(interval_minutes=N)` (HHDFS76950200, `output1.next` 플래그 페이지네이션) |
| `analysis.py` | `OverseasAnalysisAPI.volume_surge(exchange, count, *, minutes=0, volume_range="0")` → `list[OverseasVolumeSurgeItem]` — Stage 5 |

## For AI Agents

### Working In This Directory
- 거의 모든 엔드포인트가 mock-unsupported이므로 테스트는 `environment="real"`로 작성하고, mock 흐름은 `MockNotSupportedError` 회귀 케이스만 추가합니다.
- 해외 메서드는 `symbol` + **`exchange`** 양쪽이 필수입니다 — 국내처럼 `market`만으로는 KIS endpoint를 분기할 수 없습니다.
- 해외 분봉(`minute`)은 양방향 페이지네이션을 위해 `KEYB`를 마지막 파싱 bar의 `local_date+local_time`에서 도출합니다 — `_derive_minute_keyb()` 패턴 유지.
- 해외 일봉(`daily`)은 backward 페이지네이션 (`BYMD` 감소) + `KEYB` 토큰 결합으로 `start`에 도달할 때까지 반복합니다.
- 새 해외 endpoint 추가 시 mock TR ID가 진짜로 없는지 KIS 문서를 확인하고 `tr_id_mock=None`을 유지합니다.

### Testing Requirements
- `tests/test_chart.py` (minute/daily 페이지네이션), `tests/test_stage5_facades.py` (analysis.volume_surge), `tests/test_price.py` (current price)에서 mock 트랜스포트로 검증합니다.
- 거래소 코드 대소문자 정규화(`exchange.strip().upper()`)가 의도대로 작동하는지 회귀로 확인합니다.

### Common Patterns
- 모듈 상단에서 `_SPEC = lookup("overseas.<...>")` 패턴.
- `OverseasExchangeCode = Literal["NAS", "NYS", "AMS", "HKS", "TSE", "SHS", "SZS", "HNX", "HSX"]` — 타입 안정성 확보.
- `market` 인자가 `None`이면 `exchange`를 라벨로 사용하는 fallback 패턴.

## Dependencies

### Internal
- `kis.endpoints.registry.lookup`
- `kis.models.*`, `kis.parsers.rest`

### External
- 없음.

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
