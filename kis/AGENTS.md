<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# kis

## Purpose
`kis`는 한국투자증권 Open API를 감싸는 순수 Python SDK 패키지입니다. 트랜스포트 (REST `httpx` / WebSocket `websockets`)와 페이로드 정규화 (frozen dataclass 모델 + 파서)만 책임지며, 파일 시스템·DB·CLI 코드는 포함하지 않습니다. 영속 계층과 사용자 워크플로는 자매 패키지 `kis_cli/`가 담당합니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | 공개 surface 일괄 export (`KisClient`, `Credentials`, 모델, 파서, 심볼, 예외) |
| `client.py` | `KisClient` 파사드 — async context manager, `request(spec, ...)`, `ensure_token()`, `ensure_approval_key()` |
| `config.py` | `Credentials` (`from_env()` 헬퍼), `rest_base_url()`, `websocket_url()` 환경별 URL 매핑 |
| `symbols.py` | 종목 마스터 다운로드/파싱 (`download_symbol_master`, `KOSPI/KOSDAQ` 고정폭, 해외 TSV) |
| `types.py` | 공용 Literal 타입 (`Environment`, `Market`, `Interval`, `HttpMethod`, `CustType`) |
| `exceptions.py` | `KisError` 계층 (`KisAuthError`, `KisApiError`, `KisConfigError`, `KisRealtimeError`, `MockNotSupportedError`) |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `_internal/` | 비공개 트랜스포트 — `AsyncHttpTransport`, 헤더 빌더 (see `_internal/AGENTS.md`) |
| `auth/` | OAuth 토큰 발급/캐시 + WebSocket approval key (see `auth/AGENTS.md`) |
| `endpoints/` | `EndpointSpec` 레지스트리와 도메인별 등록 모듈 (see `endpoints/AGENTS.md`) |
| `models/` | 정규화된 응답 dataclass 모델 (see `models/AGENTS.md`) |
| `parsers/` | KIS 페이로드 → 모델 변환 (REST + realtime, see `parsers/AGENTS.md`) |
| `domestic/` | 국내(KRX/NXT) 고수준 API 클라이언트 (see `domestic/AGENTS.md`) |
| `overseas/` | 해외 거래소 고수준 API 클라이언트 (see `overseas/AGENTS.md`) |
| `realtime/` | WebSocket 실시간 세션 (`RealtimeSession`) (see `realtime/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- 이 패키지는 **순수 SDK**입니다. 파일 시스템 접근, KST timestamp 스탬핑, DuckDB/SQLite 로직을 절대 추가하지 마세요 — 그런 책임은 `kis_cli/`에 있습니다.
- `KisClient`는 반드시 `async with` 컨텍스트로 사용해야 합니다. 컨텍스트 밖에서 `request()`를 호출하면 `RuntimeError`가 발생합니다.
- 새 엔드포인트는 (1) `endpoints/`에 `EndpointSpec` 등록 → (2) `parsers/rest.py`에 파서 추가 → (3) `models/`에 모델 추가 → (4) `domestic/` 또는 `overseas/`에 고수준 메서드 노출 순서로 추가합니다.
- 모든 모델은 `@dataclass(frozen=True)`이며 `raw: dict[str, Any]` 필드를 포함해 원본 페이로드를 보존합니다.
- 모의투자 미지원 엔드포인트는 `tr_id_mock=None`으로 등록 → `tr_id_for("mock")` 호출 시 `MockNotSupportedError`가 자동 발생합니다.

### Testing Requirements
- 실제 KIS API를 호출하지 마세요. `httpx.MockTransport` 또는 mock 객체로 트랜스포트를 대체합니다.
- 파서 테스트는 `tests/test_kis_package.py`, 고수준 메서드는 `tests/test_stage5_facades.py`, realtime은 `tests/test_realtime.py`에서 다룹니다.
- 새 endpoint를 등록하면 `lookup("name")`이 성공하는지, `tr_id_for("real")` / `tr_id_for("mock")` 동작이 의도대로인지 확인합니다.

### Common Patterns
- async-first 설계, 동기 wrapper는 Stage 6에서 별도 모듈로 제공 예정.
- 토큰 캐싱: `KisClient._token_cache_key()` = `f"{environment}:{app_key}"`, approval key는 `f"ws:{environment}:{app_key}"`.
- `EndpointSpec`은 frozen dataclass로 메타데이터만 보유 — 비즈니스 로직 금지.
- Decimal/int 변환은 항상 파서에서 수행하고 모델은 이미 변환된 값을 받습니다.

## Dependencies

### Internal
- 패키지 내부 import만 사용 — `kis_cli`에 대한 의존은 없어야 합니다 (역방향 의존은 OK).

### External
- `httpx>=0.27.0` — REST async 트랜스포트
- `websockets>=13.0` — realtime 세션

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
