<div align="center">

# FinLabs News Pipeline

**RSS 수집부터 기사 본문 저장과 기초 분석까지 연결하는 로컬 뉴스 파이프라인**

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Typer](https://img.shields.io/badge/Typer-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://typer.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-19_Passing-00C853?style=for-the-badge&logo=pytest&logoColor=white)](./tests/test_rss_pipeline.py)

Investing.com, 이데일리, 이투데이, 한국경제, 서울경제, 뉴스핌 RSS를 하나의 표준 모델로 정규화하고 **멱등하게 수집·저장·분석**합니다.

[FinLabs](../../README.md) · [운영 계획](./PLAN.md) · [회귀 테스트](./tests/test_rss_pipeline.py)

</div>

---

## Overview

`modules/news`는 FinLabs의 독립 실행형 뉴스 수집 모듈입니다. 언론사마다 다른 RSS 필드를 표준 스키마로 변환하고, 기사 URL 기반의 결정적 ID와 DuckDB 제약 조건으로 중복 저장을 방지합니다.

파이프라인은 RSS 메타데이터 수집, 기사 본문 수집, 기초 분석의 세 단계로 분리됩니다. 각 단계는 다시 실행해도 이미 처리한 항목을 건너뛰며, 성공·실패 상태와 처리 건수를 `pipeline_runs`에 기록합니다.

---

## Features

| | 기능 | 설명 |
|---|------|------|
| **[RSS 수집]** | 언론사별 파서 | 6개 매체의 전체·카테고리 RSS를 공통 `CanonicalRssEntry`로 변환 |
| **[카테고리]** | 출처별 분리 저장 | 매체 도메인, 피드 카테고리, XML 원문 카테고리를 구분해 보존 |
| **[중복 방지]** | 결정적 기사 ID | 기사 URL의 SHA-256 해시와 데이터베이스 제약으로 중복 적재 방지 |
| **[본문 수집]** | HTML 텍스트 추출 | 스크립트·스타일·SVG를 제외하고 가시 텍스트를 정규화해 저장 |
| **[기초 분석]** | 본문 통계 | 분석기 버전과 본문 해시를 기준으로 문자 수·단어 수 계산 |
| **[멱등 실행]** | 단계별 재실행 | 이미 저장되거나 현재 버전으로 분석된 항목은 다시 처리하지 않음 |
| **[실행 이력]** | 성공·실패 기록 | 명령, 매개변수, 상태, 처리 건수, 제한된 오류 메시지를 저장 |
| **[동시성 보호]** | 단일 writer 잠금 | 파일 잠금으로 동일 DuckDB에 대한 중복 파이프라인 실행을 즉시 차단 |
| **[정기 실행]** | systemd timer | 세 단계를 30분마다 순차 실행하는 Linux 서비스 예시 제공 |

---

## Pipeline

```text
RSS feeds
    │
    ▼
collect-rss
    │  provider parser → CanonicalRssEntry
    ▼
rss_items
    │
    ▼
collect-articles
    │  HTML → visible normalized text → content hash
    ▼
articles
    │
    ▼
analyze
    │  basic-stats-v1
    ▼
article_analyses

각 명령의 실행 결과 ──────────────────────▶ pipeline_runs
```

---

## Tech Stack

### Runtime

![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![feedparser](https://img.shields.io/badge/feedparser-6.0.12+-4B8BBE?style=flat-square)
![HTTPX](https://img.shields.io/badge/HTTPX-0.27+-2F6F9F?style=flat-square)
![Typer](https://img.shields.io/badge/Typer-0.12+-009688?style=flat-square)

### Storage & Quality

![DuckDB](https://img.shields.io/badge/DuckDB-1.1+-FFF000?style=flat-square&logo=duckdb&logoColor=black)
![pytest](https://img.shields.io/badge/pytest-9.0+-0A9EDC?style=flat-square&logo=pytest&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.15+-D7FF64?style=flat-square&logo=ruff&logoColor=black)

---

## Data Sources

| 언론사 | 기본 RSS URL | 요약 필드 | API 키 |
|--------|--------------|:---------:|:------:|
| Investing.com Korea | `https://kr.investing.com/rss/news.rss` | 미사용 | 불필요 |
| 이데일리 | `http://rss.edaily.co.kr/edaily_news.xml` | 사용 | 불필요 |
| 이투데이 | `https://rss.etoday.co.kr/eto/etoday_news_all.xml` | 사용 | 불필요 |
| 한국경제 | `https://www.hankyung.com/feed/all-news` | 미사용 | 불필요 |
| 서울경제 | `https://www.sedaily.com/rss/newsall` | 미사용 | 불필요 |
| 뉴스핌 | `http://rss.newspim.com/news/category/1` | 사용 | 불필요 |

기본 소스는 총 63개이며 `collect-rss` 실행 시 전체 피드와 제공된 카테고리별 피드를 함께 수집합니다. 매체별 구성은 Investing.com 16개, 이데일리 1개, 이투데이 11개, 한국경제 12개, 서울경제 12개, 뉴스핌 11개입니다. URL과 카테고리 설정의 기준은 [`pipeline.py`](./pipeline.py)의 `DEFAULT_FEED_SOURCES`입니다.

`--feed publisher=URL` 옵션을 반복하면 지원 언론사의 RSS URL을 실행 단위로 교체할 수 있습니다.

### 카테고리 피드

| 언론사 | 기본 등록 카테고리 |
|--------|--------------------|
| Investing.com Korea | 내부자거래, 주식시장투자아이디어, SEC 공시, 어닝콜 스크립트, 실적보고서와 발표예정일, 애널리스트 투자의견, IPO, 암호화폐, 외환, 많이 본 기사, 주식 시장 뉴스, 상품과 선물 뉴스, 경제 지표 뉴스, 스포츠 및 일반 뉴스, 경제 뉴스 |
| 이투데이 | 금융, 마켓, 부동산, 산업, 경제, 국제, 정치, 사회, 오피니언, 문화/라이프 |
| 한국경제 | 증권, 경제, 부동산, IT, 정치, 국제, 사회, 생활, 오피니언, 스포츠, 연예 |
| 서울경제 | 증권, 부동산, 경제, 정치, 사회, 국제, IT, 오피니언, 생활, 스포츠, 연예 |
| 뉴스핌 | 정치, 경제, 사회, 글로벌, 산업, 증권/금융, 부동산, 라이프/여행, 문화/연예, 스포츠 |
| 이데일리 | 전체 피드만 등록. XML 원문 카테고리는 `source_categories`에 저장 |

카테고리는 용도를 분리해 저장합니다.

- `domain_category`: 매체의 도메인 분류. Investing.com은 `금융`입니다.
- `feed_categories`: 카테고리별 RSS URL에 지정된 분류 목록입니다.
- `source_categories`: RSS XML의 `category` 값을 표준화하지 않고 보존한 목록입니다.

`feed_categories`와 `source_categories`의 빈 배열 `[]`은 수집은 정상적으로 완료됐지만 해당 카테고리가 없다는 뜻입니다. `NULL`은 기존 데이터 마이그레이션 과정에서 빈 배열로 보정합니다.

같은 기사 URL이 여러 카테고리 피드에 포함되면 기사 행은 하나만 유지하고 카테고리 목록을 합칩니다.

Investing.com의 `news_462.rss`(뉴스 속보 헤드라인)와 `news_477.rss`(최신 금융 뉴스)는 현재 HTTP 404를 반환하므로 기본 수집 목록에서 제외합니다.

---

## Getting Started

### 사전 요구사항

- Python 3.12+
- `uv`
- Linux 또는 macOS처럼 `fcntl` 파일 잠금을 지원하는 환경

### 설치

저장소 루트에서 의존성을 동기화합니다.

```bash
git clone https://github.com/chosey0/finlabs.git
cd finlabs
uv sync --group news
```

### 파이프라인 실행

```bash
# 전체 기본 RSS 수집
uv run --group news python -m modules.news.main collect-rss

# 아직 저장되지 않은 기사 본문 수집
uv run --group news python -m modules.news.main collect-articles --limit 100

# 아직 현재 버전으로 분석되지 않은 기사 분석
uv run --group news python -m modules.news.main analyze --limit 100
```

명령은 필요한 스키마를 자동으로 생성합니다. 기본 데이터베이스는 `modules/news/db/news.db`이며 Git에서 제외됩니다.

### 데이터베이스 경로 지정

모든 명령은 `--db-path` 또는 `NEWS_DB_PATH`를 지원합니다.

```bash
export NEWS_DB_PATH="$HOME/.local/share/finlabs/news.duckdb"
uv run --group news python -m modules.news.main collect-rss

# 또는 명령별 경로 지정
uv run --group news python -m modules.news.main analyze \
  --db-path /var/lib/finlabs-news/news.duckdb \
  --limit 200
```

### RSS URL 교체

`publisher` 값은 `investing.com`, `edaily`, `etoday`, `hankyung`, `newspim`, `sedaily` 중 하나여야 합니다.

```bash
uv run --group news python -m modules.news.main collect-rss \
  --feed investing.com=https://kr.investing.com/rss/news.rss \
  --feed edaily=http://rss.edaily.co.kr/edaily_news.xml \
  --feed hankyung=https://www.hankyung.com/feed/all-news
```

`--feed`는 전체 기본 목록을 교체합니다. CLI 형식에는 카테고리 입력값이 없으므로 이 방식으로 추가한 피드는 `domain_category=NULL`, `feed_categories=[]`로 저장되고 XML이 제공하는 값만 `source_categories`에 남습니다.

---

## Storage

| 테이블 | 역할 | 중복 방지 기준 |
|--------|------|----------------|
| `rss_items` | 표준 RSS 메타데이터와 출처·피드 카테고리 | `id` 기본키, `url` 고유 제약 |
| `articles` | 정규화된 기사 본문과 본문 해시 | `rss_item_id` 기본키 |
| `article_analyses` | 분석기 버전별 현재 분석 결과 | `rss_item_id` 기본키 |
| `pipeline_runs` | 명령 실행 상태와 처리 결과 | 실행별 UUID |
| `schema_migrations` | 스키마·데이터 마이그레이션 이력 | 마이그레이션 ID |

발행 시각은 입력 형식을 검증한 뒤 `Asia/Seoul` 기준으로 정규화합니다. 기존 UTC-naive 데이터의 서울 시각 변환은 마이그레이션 이력으로 한 번만 수행됩니다.

`rss_items`의 주요 카테고리 컬럼은 다음과 같습니다.

| 컬럼 | 타입 | 의미 |
|------|------|------|
| `domain_category` | `VARCHAR` | 매체 전체에 부여한 상위 도메인. 현재 Investing.com의 `금융`만 사용 |
| `feed_categories` | `VARCHAR[]` | 카테고리별 피드 URL에서 결정된 분류. 중복 기사에서는 목록 병합 |
| `source_categories` | `VARCHAR[]` | RSS XML이 제공한 원문 분류. 표준화하지 않음 |

---

## Architecture

```text
modules/news/
├── main.py                    Typer CLI와 DB별 단일 writer 실행 경계
├── pipeline.py                RSS·본문·분석 단계와 실행 이력 조율
├── db/
│   ├── init.py                DuckDB 스키마 생성과 안전한 마이그레이션
│   └── sql.py                 RSS·본문·분석·실행 이력 저장 연산
├── schema/
│   ├── base.py                표준 RSS 모델과 공통 파싱·검증
│   ├── article.py             기사 및 분석 모델
│   ├── investingcom.py        Investing.com RSS 파서
│   ├── edaily.py              이데일리 RSS 파서
│   ├── etoday.py              이투데이 RSS 파서
│   ├── hankyung.py            한국경제 RSS 파서
│   ├── sedaily.py             서울경제 RSS 파서
│   └── newspim.py             뉴스핌 RSS 파서
├── systemd/
│   ├── finlabs-news.service   세 단계 순차 실행 서비스
│   └── finlabs-news.timer     30분 주기 타이머
├── tests/
│   └── test_rss_pipeline.py   파서·CRUD·멱등성·마이그레이션 회귀 테스트
└── PLAN.md                    Airflow 도입 판단 기준
```

---

## Operations

`systemd/` 예시는 `/opt/finlabs` 체크아웃과 `/var/lib/finlabs-news/news.duckdb`를 기준으로 작성되어 있습니다. 배포 환경에 맞게 `User`, `WorkingDirectory`, `NEWS_DB_PATH`를 조정해야 합니다.

```bash
sudo cp modules/news/systemd/finlabs-news.service /etc/systemd/system/
sudo cp modules/news/systemd/finlabs-news.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now finlabs-news.timer
sudo systemctl status finlabs-news.timer
```

DuckDB 쓰기는 파일 잠금으로 직렬화됩니다. `collect-rss`, `collect-articles`, `analyze` 실행 중에는 DuckDB CLI나 다른 프로세스가 같은 DB 파일을 쓰기 가능한 상태로 열고 있으면 안 됩니다. 여러 서버나 컨테이너가 동시에 동일 파일을 쓰는 구조도 지원하지 않습니다. 백필, 단계별 재시도, 다중 노드 실행 요구가 커질 때의 Airflow 도입 기준은 [PLAN.md](./PLAN.md)에 정리되어 있습니다.

---

## Testing

테스트는 실제 RSS 서버를 호출하지 않고 고정된 feedparser 형식 데이터와 인메모리 DuckDB를 사용합니다.

```bash
uv run --group news python -m pytest modules/news/tests/test_rss_pipeline.py -q
uv run ruff check modules/news
```

현재 회귀 범위는 다음 동작을 포함합니다.

- 언론사별 표준 모델 변환과 URL 검증
- 서울 시간대 정규화
- RSS CRUD와 중복 삽입 방지
- 카테고리 원문 보존과 중복 기사 카테고리 병합
- 기존 RSS 행을 유지하는 카테고리 컬럼 마이그레이션
- RSS → 본문 → 분석 단계의 멱등성
- 성공·실패 실행 이력
- 빈 구버전 스키마 교체와 시간대 마이그레이션
- 동일 DB에 대한 중복 writer 차단

---

## Current Scope

현재 `collect-articles`는 언론사별 본문 선택자가 아니라 HTML 전체에서 스크립트·스타일·SVG를 제외한 가시 텍스트를 추출합니다. 따라서 메뉴, 관련 기사, 광고 문구가 포함될 수 있습니다.

`analyze` 단계는 `basic-stats-v1` 분석기로 문자 수와 공백 기준 단어 수만 계산합니다. 카테고리 표준화, AI 요약, 종목 연결, 감성 분석, 검색 API, 웹 대시보드는 아직 구현되어 있지 않습니다.

---

## License

이 저장소에는 아직 별도 라이선스 파일이 없습니다.
