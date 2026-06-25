# scripts

저장소 운영·데이터 적재·학습·검증에 쓰는 일회성/도구성 스크립트 모음입니다. 테스트가 아니라 **사람이 직접 실행**하는 진입점이며, 대부분 실제 외부 서비스(Supabase PostgreSQL, KIS/Kiwoom/Naver)에 접근합니다.

---

## 공통 사항

- **실행 위치**: 모두 저장소 루트에서 실행합니다.
- **Python 스크립트**: `uv run python -m scripts.<이름>` 형태(모듈 경로, `.py` 없이)로 실행해야 `modules.*` 패키지 import가 해결됩니다. 일부는 `--group postgres` 또는 `--group news`가 필요합니다(아래 표 참고).
- **셸 스크립트**: 실행 비트가 있으므로 `scripts/<이름>.sh`로 바로 실행합니다.
- **DB 접속**: PostgreSQL을 쓰는 스크립트는 `INTELLIGENCE_DATABASE_URL`(libpq 연결 문자열)을 읽습니다. 저장소 루트 `.env`에 두면 진입점이 자동 로드하며, `--dsn`으로 직접 넘길 수도 있습니다.
- **자격증명**: `.env`의 `KIWOOM_APP_KEY`/`KIWOOM_SECRET_KEY`, `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`이 필요한 스크립트가 있습니다. **`.env`와 export 산출물은 커밋하지 않습니다.**

### 한눈에 보기

| 스크립트 | 분류 | 필요한 것 | 실행 그룹 |
|---|---|---|:---:|
| `collect_rss_loop.sh` | 운영 | `INTELLIGENCE_DATABASE_URL` | (셸) |
| `verify-news-intelligence.sh` | 검증 | `uv`, `bun 1.3.3`, (선택) 테스트용 Postgres | (셸) |
| `load_kis_symbols_to_supabase.py` | 카탈로그 적재 | `INTELLIGENCE_DATABASE_URL` (공개 파일, 자격증명 불필요) | `postgres` |
| `seed_intelligence_catalog.py` | 카탈로그 적재 | `INTELLIGENCE_DATABASE_URL` + 로컬 DuckDB 웨어하우스 | `postgres` |
| `build_surge_training_set.py` | 학습 데이터 | Kiwoom + Naver 자격증명 + `INTELLIGENCE_DATABASE_URL` | (기본) |
| `train_surge_model.py` | 모델 | 데이터셋 스냅샷 JSON 파일 | (기본) |
| `run_news_intelligence_e2e_api.py` | 개발/E2E | `INTELLIGENCE_DATABASE_URL` | (기본) |

---

## 운영

### `collect_rss_loop.sh`
`collect-rss`를 고정 간격(기본 60초)으로 반복 실행합니다. 멱등(`ON CONFLICT DO NOTHING`)이라 매번 새 항목만 적재하고 중복은 건너뜁니다. 자기 자신과 절대 중첩하지 않고(실행 → 다음 경계까지 sleep), 원자적 `mkdir` 잠금으로 단일 인스턴스를 보장하며, `SIGINT`/`SIGTERM`에 종료합니다. 한 피드가 429나 네트워크 오류로 실패해도 그 회차 전체가 중단되지 않고 해당 피드만 건너뛰고 다음 회차에 재시도하므로, 일시적 rate limit이 루프를 죽이지 않습니다. 추가 인자는 `collect-rss`로 전달됩니다.

```bash
# 60초마다 전체 피드
scripts/collect_rss_loop.sh

# 간격 변경 / 피드 좁히기 / 백그라운드 로깅
INTERVAL_SECONDS=120 scripts/collect_rss_loop.sh
scripts/collect_rss_loop.sh --feed donga=https://rss.donga.com/total.xml
scripts/collect_rss_loop.sh >> /var/log/finlabs-collect-rss.log 2>&1 &
```

전체 72개 피드 한 회는 보통 수 초 안에 끝나며, 네트워크가 느려 간격을 넘기면 다음 경계에서 다시 시작합니다. 자세한 파이프라인·systemd 대안은 [News Pipeline README](../modules/news/README.md)를 참고하세요.

헤드리스 자동화에는 이 스크립트를, 현황을 눈으로 보며 돌릴 땐 같은 수집을 Rich 라이브 대시보드로 보여주는 `monitor` 명령(`uv run --group news python -m modules.news.main monitor --interval 60`)을 쓰세요.

---

## 검증

### `verify-news-intelligence.sh`
News Intelligence 변경의 전체 검증 게이트입니다. `uv sync --all-groups` 후 `pytest`, `ruff`, `compileall`, OpenAPI export를 돌리고, 웹(`bun ci`, `generate:api`, `typecheck`, `bun test`, `build`, Playwright `test:e2e`)을 실행한 뒤 생성물(openapi.json·TS 클라이언트)이 드리프트하지 않았는지 `git diff --exit-code`로 확인합니다.

```bash
scripts/verify-news-intelligence.sh
```

`uv`와 `bun 1.3.3`이 필요합니다. PostgreSQL 의존 테스트는 `INTELLIGENCE_TEST_DATABASE_URL`이 설정돼 있어야 실행되며(미설정 시 자동 skip), E2E는 로컬 Chrome을 headless로 씁니다.

---

## 카탈로그 적재 (`domestic_symbols`)

두 스크립트 모두 News Intelligence 카탈로그가 읽는 `domestic_symbols`를 채웁니다. 출처가 다릅니다.

### `load_kis_symbols_to_supabase.py` (권장)
KIS가 공개하는 종목 마스터 파일을 직접 내려받아 PostgreSQL에 원자적으로 교체합니다. 공개 다운로드라 **Kiwoom/KIS 자격증명이 필요 없고 DSN만** 있으면 됩니다. DuckDB 웨어하우스를 거치지 않습니다.

```bash
INTELLIGENCE_DATABASE_URL=postgresql://... \
  uv run --group postgres python -m scripts.load_kis_symbols_to_supabase \
  [--markets KOSPI KOSDAQ NASDAQ AMEX NYSE] [--dsn postgresql://...] [--timeout 30]
```

### `seed_intelligence_catalog.py`
기존 로컬 DuckDB 웨어하우스의 현재 스냅샷을 PostgreSQL로 복사합니다. 멱등(테이블 재생성 + 전 행 교체)이며 이미 DuckDB 웨어하우스가 있을 때 빠르게 시드하는 용도입니다.

```bash
INTELLIGENCE_DATABASE_URL=postgresql://... \
  uv run --group postgres python -m scripts.seed_intelligence_catalog \
  [--source /path/to/warehouse.duckdb] [--dsn postgresql://...]
```

---

## 학습 데이터·모델

### `build_surge_training_set.py`
급등 데이터셋의 **음성(negative) 표본**을 만듭니다. 평일 캘린더에서 시드 기반 무작위 `(종목, 분)` 앵커를 뽑아 UI와 동일한 뉴스 검색을 `random_control` 태그로 실행하고(가격 움직임에 조건화되지 않음), 발견된 표본을 반응 라벨링(베타 보정·표준화 초과수익)합니다. 관련성 라벨링과 데이터셋 고정은 라벨링 툴의 human-in-the-loop에 남습니다 — 이 스크립트는 후보 풀 생성·라벨링까지만 합니다.

**Kiwoom + Naver 자격증명**과 `INTELLIGENCE_DATABASE_URL`이 필요합니다(운영용).

```bash
uv run python -m scripts.build_surge_training_set \
  --start 2026-05-01 --end 2026-05-31 \
  --securities-limit 50 --per-session 1 --seed 2026-05 --label-reactions
```

### `train_surge_model.py`
고정된 데이터셋 스냅샷(`{"manifest", "members", ...}` JSON)으로 급등 랭킹 모델을 학습·평가합니다. out-of-time 랭킹 품질·베이스라인·슬라이스를 담은 평가 리포트를 JSON으로 출력하므로 캡처·diff하기 좋습니다.

```bash
uv run python -m scripts.train_surge_model <dataset.json> \
  [--k 10] [--out-of-time-fraction 0.2] [--model ridge|lightgbm] [--text-dim 64]
```

---

## 개발 / E2E

### `run_news_intelligence_e2e_api.py`
실제 FastAPI 앱을 결정적인 로컬 E2E 포트(`127.0.0.1:42818`)와 임시 저장소로 띄웁니다. Playwright E2E의 `webServer`가 자동으로 기동하지만, 수동 디버깅에도 쓸 수 있습니다. `INTELLIGENCE_DATABASE_URL`을 사용합니다.

```bash
# 저장소 루트에서 수동 실행
uv run python -m scripts.run_news_intelligence_e2e_api

# (참고) Playwright가 web 디렉터리에서 기동하는 형태
PYTHONPATH=../.. uv run python ../../scripts/run_news_intelligence_e2e_api.py
```
