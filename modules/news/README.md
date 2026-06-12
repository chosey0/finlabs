<div align="center">

# FinLabs News Intelligence

**과거 급등 직전 뉴스 패턴과의 유사도로 급등 후보 종목을 조기 탐지하는 시스템 — 현재는 그 기반인 뉴스 수집 파이프라인 단계**

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Typer](https://img.shields.io/badge/Typer-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://typer.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-25_Passing-00C853?style=for-the-badge&logo=pytest&logoColor=white)](./tests/)

Investing.com, 이데일리, 이투데이, 한국경제, 서울경제, 뉴스핌 RSS를 하나의 표준 모델로 정규화하고 **멱등하게 수집·저장·분석**합니다.

[FinLabs](../../README.md) · [뉴스 모듈 계획서](./PLAN.md) · [통합 계획서](../../PLAN.md) · [회귀 테스트](./tests/test_rss_pipeline.py)

</div>

---

## Overview

`modules/news`는 **FinLabs News Intelligence**의 뉴스 수집 모듈입니다. 프로젝트의 최종 목표는 국내 주식 시장(코스피·코스닥)의 뉴스를 실시간 수집·분석해 익일 또는 3거래일 이내 +10% 이상 상승 가능성이 있는 종목을 조기에 탐지하는 것입니다.

핵심 아이디어는 단순 감성 분석이 아니라 **과거 급등 직전 뉴스 패턴과의 유사도(Contrastive Vector Similarity)**입니다. "좋은 뉴스인가?"가 아니라 "과거 급등 직전 뉴스와 얼마나 비슷한가? 급등하지 않은 유사 뉴스와는 얼마나 다른가?"를 판단하고, 여기에 거래대금·변동성·테마 확산·시장 국면 등 **Market Context features**를 결합해 학습 모델(LightGBM)로 점수화합니다. 뉴스 설계는 [뉴스 모듈 PLAN](./PLAN.md), 전체 데이터 플랫폼과 구현 순서는 [통합 PLAN](../../PLAN.md)에 정리되어 있습니다.

현재 구현된 범위는 그 기반이 되는 데이터 수집 파이프라인입니다. 언론사마다 다른 RSS 필드를 표준 스키마로 변환하고, 기사 URL 기반의 결정적 ID와 DuckDB 제약 조건으로 중복 저장을 방지합니다. 파이프라인은 RSS 메타데이터 수집, 기사 본문 수집, 기초 분석의 세 단계로 분리됩니다. 각 단계는 다시 실행해도 이미 처리한 항목을 건너뛰며, 성공·실패 상태와 처리 건수를 `pipeline_runs`에 기록합니다.

---

## Features

| | 기능 | 설명 |
|---|------|------|
| **[RSS 수집]** | 언론사별 파서 | 6개 매체의 전체·카테고리 RSS를 공통 `CanonicalRssEntry`로 변환 |
| **[카테고리]** | 출처별 분리 저장 | 매체 도메인, 피드 카테고리, XML 원문 카테고리를 구분해 보존 |
| **[중복 방지]** | 결정적 기사 ID | 기사 URL의 SHA-256 해시와 데이터베이스 제약으로 중복 적재 방지 |
| **[진행 표시]** | 수집 진행바·집계 | `collect-rss` 실행 중 소스별 진행바를 표시하고 완료 후 언론사·카테고리별 수집 결과를 표로 출력 |
| **[본문 수집]** | 언론사별 본문 선택자 | 6개 매체의 지정 본문 요소만 정규화해 저장하고 원문 HTML은 폐기 |
| **[본문 재처리]** | Parser 버전 추적 | 언론사 parser 버전이 바뀌면 기존 기사 본문을 자동으로 다시 수집 |
| **[기초 분석]** | 본문 통계 | 분석기 버전과 본문 해시를 기준으로 문자 수·단어 수 계산 |
| **[멱등 실행]** | 단계별 재실행 | 이미 저장되거나 현재 버전으로 분석된 항목은 다시 처리하지 않음 |
| **[실행 이력]** | 성공·실패 기록 | 명령, 매개변수, 상태, 처리 건수, 제한된 오류 메시지를 저장 |
| **[동시성 보호]** | 단일 writer 잠금 | 파일 잠금으로 동일 DuckDB에 대한 중복 파이프라인 실행을 즉시 차단 |
| **[정기 실행]** | systemd timer | 세 단계를 30분마다 순차 실행하는 Linux 서비스 예시 제공 |
| **[종목 마스터]** | KIS 국내·해외 마스터 동기화 | 국내 2개·미국 3개 시장을 분리 테이블에 원자적으로 교체 |

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
    │  publisher parser → cleaned text → content hash + parser version
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
# KOSPI·KOSDAQ·NASDAQ·NYSE·AMEX 종목 마스터 갱신
uv run --group news python -m modules.news.main update-symbols

# 전체 기본 RSS 수집
uv run --group news python -m modules.news.main collect-rss

# 본문이 없거나 parser 버전이 지난 기사 수집
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
| `articles` | 정제 기사 본문, 본문 해시와 parser 버전 | `rss_item_id` 기본키 |
| `article_analyses` | 분석기 버전별 현재 분석 결과 | `rss_item_id` 기본키 |
| `pipeline_runs` | 명령 실행 상태와 처리 결과 | 실행별 UUID |
| `domestic_symbols` | KIS KOSPI·KOSDAQ 종목 마스터 현재 스냅샷 | `(market, symbol)` 고유 제약 |
| `overseas_symbols` | KIS NASDAQ·NYSE·AMEX 종목 마스터 현재 스냅샷 | `(market, symbol)` 고유 제약 |
| `schema_migrations` | 스키마·데이터 마이그레이션 이력 | 마이그레이션 ID |

발행 시각은 입력 형식을 검증한 뒤 `Asia/Seoul` 기준으로 정규화합니다. 기존 UTC-naive 데이터의 서울 시각 변환은 마이그레이션 이력으로 한 번만 수행됩니다.

[통합 PLAN](../../PLAN.md) 단계 4에 따라 RSS 상태·중복 관리와 정제 본문 저장은 PostgreSQL `news` 스키마로 이전할 예정입니다. 기존 DuckDB는 마이그레이션 없이 읽기 전용 레거시 보관소로 유지되며, 신규 인프라는 빈 상태에서 시작해 이중 쓰기를 하지 않습니다.

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
├── articles/
│   └── parsers.py             언론사별 본문 선택자와 parser 버전 registry
├── db/
│   ├── init.py                DuckDB 스키마 생성과 안전한 마이그레이션
│   ├── locking.py             DB 파일 단일 writer 잠금
│   └── sql.py                 RSS·본문·분석·실행 이력 저장 연산
├── schema/
│   ├── article.py             기사 및 분석 모델
│   └── symbol.py              뉴스 DB용 종목 마스터 모델
├── rss/
│   ├── models.py              표준 RSS 모델과 검증
│   └── parsers.py             공통 파서 계약, 설정 기반 파서, 언론사 레지스트리
├── systemd/
│   ├── finlabs-news.service   세 단계 순차 실행 서비스
│   ├── finlabs-news.timer     30분 주기 타이머
│   ├── finlabs-news-symbols.service  종목 마스터 갱신 서비스
│   └── finlabs-news-symbols.timer    매일 09:00 KST 갱신 타이머
├── tests/
│   ├── test_article_parsers.py  언론사별 본문 선택자 회귀 테스트
│   ├── test_rss_pipeline.py   파서·CRUD·멱등성·마이그레이션 회귀 테스트
│   └── test_symbols.py        종목 마스터 스냅샷 갱신 회귀 테스트
├── symbols.py                 KIS 다운로드와 뉴스 DB 동기화
└── PLAN.md                    뉴스 모듈 계획서 (v3.0)
```

---

## Operations

`systemd/` 예시는 `/opt/finlabs` 체크아웃과 `/var/lib/finlabs-news/news.duckdb`를 기준으로 작성되어 있습니다. 배포 환경에 맞게 `User`, `WorkingDirectory`, `NEWS_DB_PATH`를 조정해야 합니다.

```bash
sudo cp modules/news/systemd/finlabs-news.service /etc/systemd/system/
sudo cp modules/news/systemd/finlabs-news.timer /etc/systemd/system/
sudo cp modules/news/systemd/finlabs-news-symbols.service /etc/systemd/system/
sudo cp modules/news/systemd/finlabs-news-symbols.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now finlabs-news.timer
sudo systemctl enable --now finlabs-news-symbols.timer
sudo systemctl status finlabs-news.timer
sudo systemctl status finlabs-news-symbols.timer
```

`finlabs-news-symbols.timer`는 매일 오전 9시(Asia/Seoul)에 KOSPI·KOSDAQ·NASDAQ·NYSE·AMEX 마스터를 갱신합니다. 다운로드가 비어 있거나 한 시장이라도 실패하면 두 테이블의 기존 스냅샷을 모두 유지합니다.

DuckDB 쓰기는 파일 잠금으로 직렬화됩니다. `update-symbols`, `collect-rss`, `collect-articles`, `analyze` 실행 중에는 DuckDB CLI나 다른 프로세스가 같은 DB 파일을 쓰기 가능한 상태로 열고 있으면 안 됩니다. 여러 서버나 컨테이너가 동시에 동일 파일을 쓰는 구조도 지원하지 않습니다.

---

## Testing

테스트는 실제 RSS 서버를 호출하지 않고 고정된 feedparser 형식 데이터와 인메모리 DuckDB를 사용합니다.

```bash
uv run --group news python -m pytest modules/news/tests/test_rss_pipeline.py -q
uv run --group news python -m pytest modules/news/tests/test_symbols.py -q
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
- 국내·해외 종목 마스터 분리 저장과 5개 시장의 원자적 스냅샷 교체
- 빈 다운로드 결과에서 기존 종목 마스터 보존

---

## Current Scope

현재 `collect-articles`는 Investing.com, 이데일리, 뉴스핌, 이투데이, 한국경제, 서울경제의 언론사별 본문 선택자를 사용합니다. 선택자가 바뀌면 해당 parser의 버전을 올려 기존 기사를 재처리하며, 원문 HTML은 저장하지 않습니다.

`analyze` 단계는 `basic-stats-v1` 분석기로 문자 수와 공백 기준 단어 수만 계산합니다. 종목 별칭 사전, 과거 뉴스 백필, 임베딩·Vector Store, LLM 이벤트 분류, 점수화, 백테스트, 대시보드는 아직 구현되어 있지 않으며 아래 로드맵의 대상입니다.

---

## Roadmap

[PLAN.md](./PLAN.md)의 개발 로드맵 요약입니다. 데이터 축적(백필, 급등 사례 라벨링)에 시간이 걸리므로 Cold Start 해소 작업을 가장 앞에 배치합니다.

| 단계 | 범위 | 상태 |
|------|------|:----:|
| **초기** (2~4주) | RSS 수집·본문 수집·DuckDB 저장 | ✅ 구현됨 |
| | KIS 종목 마스터 자동 갱신 | ✅ 구현됨 |
| | 별칭 사전, 과거 뉴스 백필(네이버 API·빅카인즈), 시세 기반 급등 이벤트 추출, Streamlit 기본 조회 | 예정 |
| **중기** (1~2개월) | 임베딩 모델 비교·선정, Vector Store(DuckDB VSS, point-in-time 필터), 급등/비급등 사례 라이브러리, LLM 이벤트 분류(taxonomy 기반), Market Context features, Entity 추출, Contrastive Similarity, 콘텐츠 기반 중복 제거 | 예정 |
| **후기** (2~3개월) | 학습 기반 점수화(LightGBM), "뉴스 단독 vs 뉴스+시장" 비교 실험, 백테스트 엔진(체결 가능성·비용·베이스라인), 감성 분석(KR-FinBERT), RAG 설명 + 인용 강제, Dashboard 고도화 | 예정 |
| **확장** (장기) | Qdrant 이전 검토, 뉴스 토큰 + 캔들 토큰 멀티모달 예측 연구 | 예정 |

시스템 전반에 강제되는 설계 원칙은 다음 다섯 가지입니다.

1. **Point-in-Time 무결성** — 모든 검색·점수 계산은 평가 시점 이전 데이터만 사용하며, 백테스트 엔진이 미래 데이터를 참조할 수 없도록 구조적으로 차단
2. **Contrastive 비교** — 급등 사례뿐 아니라 비급등 유사 사례와 함께 비교해 흔한 호재 기사의 고득점(Precision 붕괴)을 방지
3. **데이터 우선** — 과거 뉴스 백필과 급등 사례 라벨링을 로드맵 초·중기로 전진 배치
4. **베이스라인 대비 검증** — 랜덤 선택, 키워드 점수, 거래대금 모멘텀 대비 상대 성능으로 보고
5. **뉴스 + 시장의 결합** — 뉴스 팩터와 Market Context features를 하나의 학습 모델에 함께 입력해 상호작용을 학습

---

## License

이 저장소에는 아직 별도 라이선스 파일이 없습니다.
