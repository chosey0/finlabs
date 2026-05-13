<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# kis_cli

## Purpose
`kis_cli`는 `kiscli` 커맨드라인 인터페이스와 영속 계층을 담당하는 애플리케이션 패키지입니다. 순수 SDK 인 `kis/`를 소비하여 (1) 프로필/시크릿 관리, (2) DuckDB 웨어하우스 + SQLite `app.db` 저장, (3) Supabase/PostgreSQL 미러 (옵션), (4) Typer 기반 CLI를 제공합니다. KST 시간 스탬핑·파일 경로 결정·인제스트 로그 같은 운영성 책임은 모두 여기에 위치합니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | 패키지 메타데이터 (`__version__`) |
| `__main__.py` | `python -m kis_cli` 진입점 — `cli.app:main` 위임 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `cli/` | Typer 서브앱(`config`/`auth`/`db`/`symbols`/`chart`/`query`/`logs`)과 공용 console |
| `config/` | 프로필 기반 설정 로딩 + `~/.config/kis-cli/` 경로 결정 |
| `core/` | 레거시 동기 REST 클라이언트와 파일 기반 토큰 캐시 (`CachedToken`) |
| `services/` | CLI ↔ 저장소를 잇는 유스케이스 (인제스트, 인증, 차트 수집, 쿼리) |
| `storage/` | DuckDB 웨어하우스, SQLite `app.db`, Supabase 어댑터 + repositories |
| `utils/` | 공용 헬퍼 — 현재는 KST 타임스탬프 (`now_kst_iso`) |

세부 가이드라인은 상위 [AGENTS.md](../AGENTS.md)의 **Repository Layout** 및 **Common Tasks** 섹션을 참고하세요.

## For AI Agents

### Working In This Directory
- CLI 명령은 항상 `cli/<group>.py`에 둡니다. `app.py`는 root Typer 조립만 담당하고, 비즈니스 로직은 `services/`에 위임해야 합니다.
- 마켓 데이터(`symbols`, `ohlcv_bars`, `overseas_minute_bars`, `realtime_ticks`)는 **반드시** DuckDB 웨어하우스로 라우팅합니다. SQLite `app.db`는 `api_logs`/`ingest_runs` 같은 운영 로그 전용입니다.
- `kis_cli.core.*` 일부 모듈은 SDK로 이전 후 얇은 shim으로 남아있습니다. 새 코드는 `from kis import ...`를 직접 사용하세요.
- `kis_cli`에서만 KST 타임스탬프(`now_kst_iso`)와 파일 경로(`config/paths.py`)를 알아야 합니다. SDK 쪽으로 새지 않도록 유의합니다.
- 시크릿·토큰·DB 파일은 절대 패키지 소스 안에 두지 마세요. 모두 `platformdirs` 기반 OS 표준 경로로 가야 합니다.

### Testing Requirements
- `tests/` 디렉토리에서 `pytest`로 검증. 실제 KIS API 호출 없이 mock 트랜스포트와 임시 SQLite/DuckDB 파일을 활용합니다.
- 새 CLI 명령은 최소 success-path + failure-path 두 가지를 수동 검증하고, 가능한 한 `tests/test_<group>.py`에 단위 테스트를 추가합니다.
- DuckDB unique 제약, `ON CONFLICT DO NOTHING`, KST 정렬을 회귀로 확인합니다.

### Common Patterns
- 모든 service 함수는 frozen `@dataclass`로 결과를 반환 (e.g. `ChartHistoryResult`, `AuthTestResult`).
- 인제스트 흐름: `start_ingest_run` → 본문 → `record_api_log` → `finish_ingest_run(status="success|failed")`.
- Supabase 의존은 옵션 — `KISCLI_SUPABASE_DB_DSN` 환경 변수가 있을 때만 활성화됩니다.
- `cli/common.py`의 `result_table`, `cli_console()`, `console`을 통해 Rich 출력을 통일합니다.

## Dependencies

### Internal
- `kis/` — SDK (`KisClient`, `Credentials`, 모델, 파서, 심볼 다운로더)

### External
- `typer>=0.12.0` — CLI 프레임워크
- `rich>=13.0.0` + `rich-inquirer>=0.1.8` — 콘솔 출력/프롬프트
- `duckdb>=1.1.0` — 로컬 웨어하우스
- `platformdirs>=4.0.0` — OS별 표준 경로
- `psycopg>=3.3.4` (옵션, `[postgres]` extras) — Supabase 미러

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
