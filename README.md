<div align="center">

# FinLabs

**증권사 Open API SDK부터 시장 데이터·뉴스 수집과 분석까지 연결하는 로컬 우선 금융 데이터 도구**

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Typer](https://img.shields.io/badge/Typer-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://typer.tiangolo.com/)
[![pytest](https://img.shields.io/badge/Tested_with-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](https://pytest.org/)

한국투자증권 해외주식 데이터와 RSS 뉴스를 **수집·정규화·저장·조회·분석**하는 Python 프로젝트입니다.

[통합 계획서](./PLAN.md) · [KIS SDK](./modules/brokers/kis/README.md) · [Toss SDK](./modules/brokers/toss/README.md) · [KIS CLI](./kis_cli/README.md) · [News Pipeline](./modules/news/README.md) · [Research](./research/README.md)

</div>

---

## Overview

FinLabs는 증권사 Open API를 독립적인 Python SDK로 구현하고, 그 위에 시장 데이터 수집 CLI, 저장소, 대시보드, 뉴스 파이프라인과 연구 도구를 확장하는 오픈소스 개발자 도구 프로젝트입니다.

현재 중심은 한국투자증권(KIS) Open API의 해외주식 데이터 조회 SDK와 CLI입니다. 동시에 Investing.com·이투데이·뉴스핌 RSS를 표준 모델로 정규화하는 뉴스 파이프라인과 Candlestick VQ-VAE Tokenizer 연구를 별도 트랙으로 개발하고 있습니다.

코드베이스는 broker-agnostic 계층형 코어인 `modules/`로 이전 중입니다. SDK는 증권사별 차이를 캡슐화하고, 상위 애플리케이션은 canonical 모델과 orchestration 계층을 통해 데이터를 다루는 구조를 목표로 합니다.

전체 방향, 구현 순서와 모듈 간 계약은 [통합 계획서(PLAN.md)](./PLAN.md)가 관리합니다. 뉴스, KIS 실시간 수집, Toss 장 운영 정보, 저장소와 orchestration의 상세 정책은 각 모듈의 PLAN이 단일 원본입니다.

---

## Components

| | 영역 | 상태 | 설명 |
|---|------|:----:|------|
| **[Broker SDK]** | [KIS SDK](./modules/brokers/kis/README.md) | 구현 중 | 한국투자증권 해외주식 REST·WebSocket 조회, 인증, 엔드포인트, 파서, 모델 |
| **[Broker SDK]** | [Toss SDK](./modules/brokers/toss/README.md) | 구현됨 | 토스증권 현재가·캔들·종목정보와 국내·해외 장 운영 정보 조회, calendar adapter |
| **[Market CLI]** | [KIS CLI](./kis_cli/README.md) | 구현 중 | 해외 심볼 다운로드, OHLCV·분봉 수집, DuckDB 저장, 조회와 내보내기 |
| **[Core]** | `modules/` 계층형 코어 | 이전 중 | broker adapter, canonical domain, orchestration, warehouse read repository |
| **[News]** | [News Pipeline](./modules/news/README.md) | 초기 구현 | RSS 정규화, 기사 본문 수집, 멱등 저장, 기초 통계 분석, systemd 실행 |
| **[Dashboard]** | `dashboard/` | 구현 중 | `modules.orchestration`을 통해 저장된 시장 데이터를 읽는 Streamlit UI |
| **[Research]** | [Market Representation](./research/README.md) | 초기 연구 | Candlestick VQ-VAE Tokenizer 중심의 시장 표현 학습 |
| **[Platform]** | PostgreSQL·TimescaleDB·Redis·Parquet | 계획 확정 | [통합 PLAN](./PLAN.md) 단계 1~6의 신규 데이터 플랫폼, 구현 전 |
| **[Next Broker]** | Kiwoom SDK·adapter | 예정 | 추가 국내주식 데이터 조회용 Kiwoom REST API 통합 |

---

## Features

| | 기능 | 설명 |
|---|------|------|
| **[인증]** | KIS API 인증 | 접근 토큰 발급·캐시와 모의·실전 환경 설정 |
| **[심볼]** | 해외주식 마스터 | 거래소별 심볼 마스터 다운로드, 정규화, 검색 |
| **[시세]** | OHLCV 수집 | 일·주·월·년봉과 해외주식 분봉 조회·저장 |
| **[저장소]** | 로컬 우선 데이터 | 시장 데이터는 DuckDB, 운영 로그는 SQLite에 저장 |
| **[중복 방지]** | 멱등 적재 | 데이터베이스 고유 제약과 conflict 처리로 재실행 안전성 확보 |
| **[조회]** | 공통 warehouse query | CLI·대시보드·연구가 `modules.orchestration.query`를 통해 동일 SQL 사용 |
| **[뉴스]** | 3단계 뉴스 파이프라인 | RSS 수집 → 기사 본문 저장 → 버전 기반 기초 분석 |
| **[운영]** | 실행 이력과 직렬화 | 뉴스 단계별 성공·실패 기록과 DuckDB 단일 writer 잠금 |

---

## Tech Stack

### Runtime & CLI

![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![Typer](https://img.shields.io/badge/Typer-0.12+-009688?style=flat-square)
![HTTPX](https://img.shields.io/badge/HTTPX-0.27+-2F6F9F?style=flat-square)
![WebSockets](https://img.shields.io/badge/WebSockets-13+-010101?style=flat-square)

### Storage & Data

![DuckDB](https://img.shields.io/badge/DuckDB-1.1+-FFF000?style=flat-square&logo=duckdb&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_TimescaleDB-Planned-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis_Streams-Planned-DC382D?style=flat-square&logo=redis&logoColor=white)
![feedparser](https://img.shields.io/badge/feedparser-6.0.12+-4B8BBE?style=flat-square)

### Analysis & Quality

![PyTorch](https://img.shields.io/badge/PyTorch-Optional-EE4C2C?style=flat-square&logo=pytorch&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.58+-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-9.0+-0A9EDC?style=flat-square&logo=pytest&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.15+-D7FF64?style=flat-square&logo=ruff&logoColor=black)

---

## Architecture

FinLabs의 시장 데이터 코어는 의존성이 위에서 아래로만 흐르는 계층형 구조로 이전 중입니다.

```text
kis_cli / dashboard / research        thin transports
        │
        ▼
modules.orchestration                 use cases and warehouse queries
        │
        ├──────────────▶ modules.storage
        ▼
modules.adapters.brokers.{broker}     SDK → canonical model
        │
        ▼
modules.brokers.{broker}              standalone broker SDK

modules.domain                        pure shared contracts
```

| 계층 | 위치 | 책임 |
|------|------|------|
| Broker SDK | `modules/brokers/{broker}/` | 인증, API 요청, 응답 파싱과 broker-native 모델 |
| Broker adapter | `modules/adapters/brokers/{broker}/` | SDK 모델을 canonical domain 모델로 변환 |
| Orchestration | `modules/orchestration/` | adapter·storage·로깅을 하나의 use case로 조율 |
| Domain | `modules/domain/` | I/O가 없는 canonical dataclass와 Protocol |
| Storage | `modules/storage/` | warehouse read SQL의 단일 출처 |

`modules/news`는 이 broker 계층과 별도로 실행되는 독립 뉴스 파이프라인입니다. 자체 표준 뉴스 모델과 전용 DuckDB를 사용하며, 현재 시장 데이터용 `modules.domain` 또는 `modules.storage`에는 의존하지 않습니다.

### 목표 데이터 플랫폼

[통합 계획서](./PLAN.md)가 확정한 전체 데이터 흐름입니다. Redis는 전달 계층이고 PostgreSQL과 검증된 Parquet가 영구 원본입니다.

```text
KIS WebSocket
  -> Redis Streams
     -> TimescaleDB writer
     -> 1-minute candle aggregator
     -> Parquet archive writer
     -> Redis Pub/Sub live broadcast

RSS / Article Fetcher
  -> PostgreSQL news schema

Toss Market Calendar
  -> Toss SDK -> Toss Adapter -> PostgreSQL market schema

Monitoring Core
  -> Rich CLI
  -> Discord
  -> Future FastAPI/WebSocket and PyQt
```

영역별 상세 정책의 단일 원본은 다음 모듈 PLAN입니다.

| 영역 | 단일 원본 |
|---|---|
| 뉴스 수집·파싱·분석 | [modules/news/PLAN.md](./modules/news/PLAN.md) |
| KIS WebSocket 실시간 수집 | [modules/brokers/kis/PLAN.md](./modules/brokers/kis/PLAN.md) |
| Toss 장 운영 정보 | [modules/brokers/toss/PLAN.md](./modules/brokers/toss/PLAN.md) |
| PostgreSQL·TimescaleDB·Parquet·백업 | [modules/storage/PLAN.md](./modules/storage/PLAN.md) |
| Redis Streams·워커·구독·관측성 | [modules/orchestration/PLAN.md](./modules/orchestration/PLAN.md) |

---

## Repository

```text
finlabs/
├── modules/
│   ├── brokers/kis/            한국투자증권 해외주식 SDK
│   ├── brokers/toss/           토스증권 국내·미국주식 시세 SDK
│   ├── adapters/brokers/kis/   KIS SDK → canonical 모델 adapter
│   ├── adapters/brokers/toss/  Toss 장 운영 정보 → canonical calendar adapter
│   ├── orchestration/          use case와 warehouse query
│   ├── domain/                 canonical 데이터 계약
│   ├── storage/                warehouse read repository
│   └── news/                   RSS·본문·분석 뉴스 파이프라인
├── kis_cli/                    KIS 시장 데이터 수집 CLI
├── dashboard/                  Streamlit 시장 데이터 대시보드
├── research/                   시장 표현 학습 연구
├── tests/                      공통 단위·통합·아키텍처 테스트
├── exports/                    CSV 샘플 출력물
├── PLAN.md                     통합 계획서 — 전체 방향과 구현 순서
├── pyproject.toml              프로젝트 의존성
└── README.md                   프로젝트 개요
```

---

## Getting Started

### 사전 요구사항

- Python 3.12+
- `uv`
- KIS 기능 사용 시 한국투자증권 Open API 자격 증명

### 설치

```bash
git clone https://github.com/chosey0/finlabs.git
cd finlabs
uv sync
```

기본 동기화에는 KIS CLI 런타임과 개발 도구만 포함됩니다. 기능별 의존성은 필요할 때 그룹으로 추가합니다.

| 용도 | 동기화 명령 |
|------|-------------|
| FastAPI job server | `uv sync --group server` |
| Streamlit dashboard | `uv sync --group dashboard` |
| Research / modeling | `uv sync --group research` |
| RSS news pipeline | `uv sync --group news` |
| Scrapy crawler | `uv sync --group crawler` |
| Toss SDK | `uv sync --group toss` |
| PostgreSQL mirror | `uv sync --group postgres` |

### KIS CLI

로컬 개발에서는 console script 대신 Python 모듈로 실행합니다.

```bash
uv run python -m kis_cli --help
uv run python -m kis_cli config init
uv run python -m kis_cli db init
uv run python -m kis_cli symbols download --market NASDAQ
uv run python -m kis_cli chart daily \
  --symbol AAPL \
  --start 2025-01-01 \
  --end 2025-12-31 \
  --save
uv run python -m kis_cli query ohlcv --symbol AAPL --limit 10
```

자세한 설정, 인증과 명령 목록은 [KIS CLI README](./kis_cli/README.md)를 참고하세요.

### News Pipeline

뉴스 파이프라인은 API 키 없이 기본 RSS 소스를 수집할 수 있습니다.

```bash
uv run --group news python -m modules.news.main collect-rss
uv run --group news python -m modules.news.main collect-articles --limit 100
uv run --group news python -m modules.news.main analyze --limit 100
```

지원 언론사, DuckDB 스키마와 systemd 운영 방법은 [News Pipeline README](./modules/news/README.md)를 참고하세요.

---

## Storage

| 저장소 | 용도 | 상태 |
|--------|------|------|
| DuckDB | 시장 데이터와 뉴스 파이프라인 데이터 | 운영 중, 읽기 전용 레거시 전환 예정 |
| SQLite | KIS CLI 운영 로그 | 운영 중, 읽기 전용 레거시 전환 예정 |
| PostgreSQL (TimescaleDB) | `control`·`market`·`news` 스키마, 틱·호가·1분봉·기사 영구 원본 | 계획 확정, 구현 전 |
| Redis (Streams·Pub/Sub) | 실시간 이벤트 전달 계층 | 계획 확정, 구현 전 |
| Parquet | 검증된 틱·호가 장기 아카이브 | 계획 확정, 구현 전 |

### 전환 정책

[통합 계획서](./PLAN.md) 기준으로 신규 쓰기 경로는 PostgreSQL/TimescaleDB, Redis Streams와 검증된 Parquet를 사용합니다.

- 기존 `warehouse.duckdb`, `news.db`, SQLite는 이동·마이그레이션 없이 읽기 전용 레거시 보관소로 유지합니다.
- 신규 인프라는 빈 상태로 시작하며 이중 쓰기를 하지 않습니다.
- MongoDB는 도입하지 않습니다.
- 원문 HTML은 영구 보관하지 않고 정제 기사 본문만 저장합니다.

로컬 DB, 로그, 토큰, 계좌번호, API 키와 개인 설정 파일은 Git에 포함하지 않습니다.

---

## Development

```bash
# 전체 테스트와 정적 검사
uv run python -m pytest
uv run ruff check .

# 뉴스 파이프라인 회귀 테스트
uv run --group news python -m pytest modules/news/tests/test_rss_pipeline.py -q

# 주요 CLI 확인
uv run python -m kis_cli --help
uv run --group news python -m modules.news.main --help
```

새 core 코드는 `modules/`의 계층 규칙을 따라야 하며, broker SDK가 adapter·orchestration·storage를 역으로 import하지 않도록 아키텍처 테스트가 강제합니다. 실제 KIS API는 단위 테스트에서 호출하지 않습니다.

---

## Roadmap

구현 순서와 단계별 완료 기준은 [통합 계획서](./PLAN.md)가 관리합니다. 요약:

| 단계 | 범위 | 상태 |
|:---:|------|:----:|
| 1 | 기반 인프라 — TimescaleDB·Redis Docker Compose, 공통 환경설정, Alembic 3-스키마 | 구현 전 |
| 2 | 이벤트 전송과 구독 제어 — Redis Streams·DLQ·멱등성, KIS WebSocket 수집기, 동적 구독 CLI | 구현 전 |
| 3 | 시장 데이터 영구화 — 틱·호가·canonical 1분봉, Parquet 아카이브, Toss 장 운영 정보 저장 | 구현 전 |
| 4 | 뉴스 저장 개편 — RSS 상태·중복 관리 PostgreSQL 이전, parser registry 재처리 | 구현 전 |
| 5 | 관측성과 알림 — 공통 상태 DTO, Rich 실시간 모니터, Discord | 구현 전 |
| 6 | 백업과 복구 — 암호화 백업, 체크섬 검증, 격리 복구 훈련 | 구현 전 |

단계에 선행하는 기반은 구현되어 있습니다: KIS 해외주식 REST·실시간 SDK, Toss 시세·장 운영 정보 SDK와 calendar adapter, 뉴스 RSS 파이프라인(현 DuckDB), 국내·해외 종목 마스터 갱신 CLI. Kiwoom SDK와 Candlestick VQ-VAE 연구는 별도 트랙으로 진행합니다.

---

## Current Scope

FinLabs는 아직 초기 개발 단계이며 PyPI 배포보다 로컬 개발과 기능 검증을 우선합니다. 주문 실행, 투자 전략, 백테스트, ML 기반 예측은 현재 기본 SDK·CLI 범위에 포함되지 않습니다.

뉴스 분석은 현재 문자 수와 공백 기준 단어 수를 계산하는 `basic-stats-v1`까지만 구현되어 있습니다. AI 요약, 종목 연결, 감성 분석과 뉴스 검색 API는 아직 제공하지 않습니다.

---

## License

이 저장소에는 아직 별도 라이선스 파일이 없습니다.
