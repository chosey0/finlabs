<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# tests

## Purpose
`pytest` 기반 단위/통합 테스트 슈트입니다. 실제 KIS API에 의존하지 않고, mock 트랜스포트와 임시 DuckDB/SQLite 파일로 정상/실패 경로를 검증합니다. 새 기능을 추가하면 여기에 회귀 테스트를 추가합니다.

## Key Files

| File | Description |
|------|-------------|
| `test_auth.py` | `kis_cli.services.auth` — 프로필 → 토큰 발급/캐시 흐름 |
| `test_chart.py` | OHLCV 차트 수집 + DuckDB 적재 + 페이지네이션 |
| `test_config_init.py` | `kiscli config init`, 프로필 추가/수정/삭제 |
| `test_kis_package.py` | `kis` SDK surface 검증 — `KisClient`, 모델, 파서, EndpointSpec |
| `test_logs.py` | `kiscli logs runs/api` — SQLite `app.db` 조회 + 필터 |
| `test_price.py` | 현재가 조회 service 함수 (`get_current_price`) |
| `test_query.py` | `kiscli query ohlcv/minutes` — DuckDB 조회 + CSV/JSON 출력 |
| `test_realtime.py` | Stage 4 WebSocket 세션 — `RealtimeSession`, 구독 메시지, 프레임 파싱 |
| `test_stage5_facades.py` | Stage 5 고수준 메서드 — `domestic.rank`, `domestic.analysis`, `overseas.analysis`, `domestic.symbols` |
| `test_storage.py` | DuckDB/SQLite 스키마 생성, unique constraints, ingestion 순서 |
| `test_supabase_schema.py` | Supabase DDL SQL 생성 + `PRIMARY KEY` 보장 |
| `test_symbols.py` | 종목 마스터 파싱 (KOSPI/KOSDAQ 고정폭, 해외 TSV) + DuckDB upsert |

## For AI Agents

### Working In This Directory
- **실제 KIS API 호출 금지.** `httpx.MockTransport`, `unittest.mock.AsyncMock`, 또는 `monkeypatch`로 트랜스포트를 대체합니다.
- DB 테스트는 `tmp_path` fixture로 격리합니다 — 사용자 데이터 디렉토리(`~/.local/share/kis-cli/`)를 절대 건드리지 마세요.
- WebSocket 테스트는 실제 연결 대신 `parse_realtime_frame()` 등 파서 단위로 검증합니다.
- 새 엔드포인트가 추가되면 `test_kis_package.py`에 `lookup("...")` 검증을 추가하고, 고수준 메서드는 `test_stage5_facades.py` 패턴을 따릅니다.

### Testing Requirements
- 실행: `uv run pytest` (또는 `pytest`)
- 린트: `uv run ruff check .`
- 새 테스트는 `def test_<behavior>():` 또는 `async def test_<behavior>():` (이 경우 `@pytest.mark.asyncio` 필요) 패턴을 따릅니다.

### Common Patterns
- mock 트랜스포트: `httpx.MockTransport(handler)` → `httpx.AsyncClient(transport=mock_transport)` → `KisClient(..., http_client=client)`.
- DuckDB 단위 테스트: `init_warehouse(tmp_path/'wh.duckdb')` 후 repository 함수 직접 호출.
- frozen dataclass 결과 비교: `assert result == ExpectedResult(...)` — 모든 service 결과는 frozen이라 equality 비교가 가능합니다.
- 응답 fixture는 가능한 한 인라인 dict로 작성 — 별도 JSON 파일은 회피 (가독성 우선).

## Dependencies

### Internal
- `kis` — SDK 본체
- `kis_cli` — CLI + 저장소

### External
- `pytest>=9.0.3` (현재 runtime dep, 추후 `dev` extras로 이동 예정)

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
