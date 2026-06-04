# dashboard 패키지

`dashboard`는 Streamlit 기반 대시보드입니다. KIS 주가 데이터를 수집하고, 저장된 캔들을 조회하며, `research/fractal` 연구 기능을 노출합니다.

## 아키텍처: 두 개의 데이터 경로

대시보드는 **읽기**와 **쓰기** 경로를 의도적으로 분리합니다.

```text
쓰기:  Streamlit(Collect) ─HTTP→ FastAPI job 서버 ─→ services.chart ─→ kis SDK ─→ DuckDB
읽기:  Streamlit(Chart/Fractal) ───────────────────────────────────→ DuckDB (직접, read_only)
```

- **수집/쓰기**는 localhost FastAPI **job 서버**(`kis_cli/server/`)가 담당합니다. 이 서버만 KIS credentials를 로드하며, single worker가 수집 job을 하나씩 순차 실행해 DuckDB warehouse에 적재합니다. job 상태는 인메모리이며 서버 재시작 시 사라집니다(수집 결과는 warehouse에 영속).
- **조회/연구**는 warehouse를 **직접** 읽습니다(`dashboard/reader.py`). 수집 쓰기가 진행 중이면 DuckDB 파일 락이 잡히므로, 읽기는 bounded 재시도/backoff로 일시적 락을 흡수합니다.

읽기 페이지(`2_Chart`, `3_Fractal`)는 `dashboard/api_client.py`(FastAPI HTTP 클라이언트)를 import하지 않습니다 — 이 경로 분리는 정적 테스트(`tests/test_architecture_boundaries.py`)로 강제됩니다.

## 실행 (두 프로세스)

```bash
# 1) job 서버 기동 (KIS credentials 소유)
python -m kis_cli.server

# 2) 대시보드 기동 (repo 루트에서)
streamlit run dashboard/app.py
```

서버 호스트/포트는 `kis_cli/server/config.py`의 단일 상수(`KIS_SERVER_HOST`, `KIS_SERVER_PORT` 환경변수로 override, 기본 `127.0.0.1:8765`)를 서버·CLI 클라이언트·대시보드가 공유합니다.

## 페이지

| 페이지 | 역할 | 데이터 경로 |
|--------|------|-------------|
| `1_Collect` | 종목/시장/주기로 수집 job 등록, 상태 조회 | FastAPI(HTTP) |
| `2_Chart` | 저장된 OHLCV candlestick 렌더 | warehouse 직접 |
| `3_Fractal` | fractal 파라미터 조절 → 세그먼트 재계산 → 렌더 → `event_plots/` 저장 | warehouse 직접 |

## CLI 클라이언트

CLI도 같은 job API의 클라이언트입니다.

```bash
python -m kis_cli job submit --symbol NVDA --start 2024-01-01 --interval 1d
python -m kis_cli job status <job-id>
python -m kis_cli job list
```

## 연구 기능 확장

`3_Fractal`은 연구 기능의 기본 단위 — **파라미터 입력 → 실행 → 결과 렌더링 → 산출물 저장** — 을 따르는 첫 구현체입니다. 자동 탭 등록/플러그인 프레임워크는 의도적으로 보류했으며, 둘째 연구 모듈이 생기면 이 형태에서 공통 계약을 추출합니다(Rule of Three).
