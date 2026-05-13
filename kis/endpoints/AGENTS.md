<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# endpoints

## Purpose
KIS REST/WebSocket 엔드포인트 메타데이터를 **데이터 기반 레지스트리**로 관리합니다. `EndpointSpec`은 path, TR ID(real/mock), 필수 파라미터, 페이지네이션 지원 여부를 frozen dataclass로 보관하며, 도메인별 등록 모듈이 import 시점에 `register()`로 글로벌 레지스트리에 추가합니다. 비즈니스 로직은 없으며, 모든 사용처는 `lookup("name")`으로 spec을 가져옵니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `domestic`/`overseas` 서브모듈을 import하여 spec 등록 트리거 + `EndpointSpec`/`lookup`/`names`/`register` re-export |
| `registry.py` | `EndpointSpec` frozen dataclass (`tr_id_for(env)` with `MockNotSupportedError` 가드), `_EndpointRegistry` (중복 등록 차단), 모듈 레벨 헬퍼 `register`/`lookup`/`names` |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `domestic/` | 국내 KRX/NXT 엔드포인트 등록 — basic_quote, analysis, rank, sector, symbol_info, realtime (see `domestic/AGENTS.md`) |
| `overseas/` | 해외 거래소 엔드포인트 등록 — basic_quote, analysis, realtime (see `overseas/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- 새 엔드포인트는 `EndpointSpec(name=..., method=..., path=..., tr_id_real=..., tr_id_mock=...)`로 만들고 **`register()`로 글로벌 레지스트리에 등록**합니다.
- `name`은 `<domain>.<group>.<action>` 패턴 (e.g. `domestic.price.current`, `overseas.chart.minute`) — duplicate 시 `KisConfigError`가 발생합니다.
- 모의투자 미지원 엔드포인트는 `tr_id_mock=None`으로 두세요. `tr_id_for("mock")` 호출 시 자동으로 `MockNotSupportedError`가 발생합니다.
- 페이지네이션이 필요한 엔드포인트는 `supports_tr_cont=True`로 표시합니다 — 호출자는 응답 헤더의 `tr_cont`를 다음 요청 헤더로 전달해야 합니다.
- `required_params`/`required_headers`는 문서화 목적입니다 — 현재 트랜스포트가 강제 검증은 하지 않지만, 새 엔드포인트 작성 시 KIS 문서의 필수 필드를 정확히 옮겨 두세요.
- POST 엔드포인트(특히 WebSocket realtime)는 `method="POST"` + `required_headers=("approval_key", "custtype", "tr_type", "content-type")` 패턴을 따릅니다.

### Testing Requirements
- 새 엔드포인트 등록 후 `lookup("name")`이 성공하는지, `tr_id_for("real")`/`tr_id_for("mock")` 동작을 회귀 케이스로 추가합니다.
- 중복 등록 시 `KisConfigError`, 미지원 mock 시 `MockNotSupportedError` 발생도 회귀로 둡니다.

### Common Patterns
- 등록 패턴 1 (단일 spec): 모듈 상단에서 `CURRENT_PRICE = register(EndpointSpec(...))` 후 모듈 변수로 노출.
- 등록 패턴 2 (대량 spec): `_SPECS = (...,)` 튜플 정의 후 모듈 import 시 루프로 `register()` 호출 (analysis/rank/sector/symbol_info에서 사용).
- 마지막 필드에 원본 엑셀 워크북의 "API 명"을 한국어로 기록해 추적성을 유지합니다.

## Dependencies

### Internal
- `kis.exceptions` — `KisConfigError`, `MockNotSupportedError`
- `kis.types` — `Environment`, `HttpMethod`

### External
- 없음 (stdlib만 사용).

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
