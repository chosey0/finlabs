<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# _internal

## Purpose
SDK 내부 트랜스포트와 헤더 빌더입니다. 언더스코어 prefix가 알려주듯 **공개 surface 아님** — `kis` 패키지 바깥에서 import하지 마세요. 외부 사용자는 `kis.KisClient.request()`를 통해서만 이 계층에 도달합니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | 비공개 표식 docstring |
| `headers.py` | `build_rest_headers()` (Bearer 토큰 + tr_id/custtype), `build_websocket_subscribe_message()` (approval_key + tr_type) |
| `http.py` | `AsyncHttpTransport` — `httpx.AsyncClient` 래퍼, `EndpointSpec` 기반 GET/POST 디스패치, `rt_cd != "0"`을 `KisApiError`로 매핑 |

## For AI Agents

### Working In This Directory
- 이 모듈은 **트랜스포트 전용**입니다. 비즈니스 로직, 파싱, 모델 변환은 절대 추가하지 마세요.
- `AsyncHttpTransport`는 외부에서 `httpx.AsyncClient`를 주입받거나 자체 생성합니다 (`_owns_client` 플래그로 lifecycle 추적).
- 헤더 빌더는 frozen `Credentials`만 받습니다. 토큰 발급 로직은 `kis.auth.oauth`에 위치합니다.
- 새 헤더 키가 KIS API 명세에 추가되면 `build_rest_headers`에 옵션으로 추가하되, 기본값은 KIS 표준 그대로 둡니다.

### Testing Requirements
- `httpx.MockTransport(handler)`로 응답을 주입한 뒤 `AsyncHttpTransport.request()`를 직접 호출해 검증합니다.
- `rt_cd` 에러 매핑 회귀: `{"rt_cd": "1", "msg_cd": "...", "msg1": "..."}` 응답이 `KisApiError(rt_cd=..., msg_cd=..., msg1=...)`로 변환되는지 확인.

### Common Patterns
- async context manager 표준 패턴: `async with AsyncHttpTransport(...) as transport:` — `__aexit__`에서 소유한 client만 닫습니다.
- `EndpointSpec.method`를 보고 GET이면 `params=`, POST이면 `json=`을 디스패치합니다.

## Dependencies

### Internal
- `kis.config` — `Credentials`, `rest_base_url`
- `kis.endpoints.registry` — `EndpointSpec`
- `kis.exceptions` — `KisApiError`
- `kis.types` — `CustType`

### External
- `httpx>=0.27.0`

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
