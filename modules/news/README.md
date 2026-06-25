<div align="center">

# FinLabs News Intelligence

**과거 급등 직전 뉴스 패턴과의 유사도로 급등 후보 종목을 조기 탐지하는 시스템 — 현재는 그 기반인 뉴스 수집 파이프라인 단계**

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/Supabase_PostgreSQL-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)
[![Typer](https://img.shields.io/badge/Typer-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://typer.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-Passing-00C853?style=for-the-badge&logo=pytest&logoColor=white)](./tests/)

Investing.com, 이데일리, 이투데이, 한국경제, 서울경제, 뉴스핌, 동아일보 RSS를 하나의 표준 모델로 정규화하고 **멱등하게 수집·저장·분석**합니다.

[FinLabs](../../README.md) · [뉴스 모듈 계획서](./PLAN.md) · [통합 계획서](../../PLAN.md) · [회귀 테스트](./tests/test_rss_pipeline.py)

</div>

---

## Overview

`modules/news`는 **FinLabs News Intelligence**의 뉴스 수집 모듈입니다. 프로젝트의 최종 목표는 국내 주식 시장(코스피·코스닥)의 뉴스를 실시간 수집·분석해 익일 또는 3거래일 이내 +10% 이상 상승 가능성이 있는 종목을 조기에 탐지하는 것입니다.

핵심 아이디어는 단순 감성 분석이 아니라 **과거 급등 직전 뉴스 패턴과의 유사도(Contrastive Vector Similarity)**입니다. "좋은 뉴스인가?"가 아니라 "과거 급등 직전 뉴스와 얼마나 비슷한가? 급등하지 않은 유사 뉴스와는 얼마나 다른가?"를 판단하고, 여기에 거래대금·변동성·테마 확산·시장 국면 등 **Market Context features**를 결합해 학습 모델(LightGBM)로 점수화합니다. 뉴스 설계는 [뉴스 모듈 PLAN](./PLAN.md), 전체 데이터 플랫폼과 구현 순서는 [통합 PLAN](../../PLAN.md)에 정리되어 있습니다.

현재 구현된 범위는 그 기반이 되는 데이터 수집 파이프라인과 재사용 가능한 네이버 뉴스 검색 클라이언트입니다. 언론사마다 다른 RSS 필드를 표준 스키마로 변환하고, 기사 URL 기반의 결정적 ID와 PostgreSQL 제약 조건으로 중복 저장을 방지합니다. 저장소는 finlabs_intelligence와 동일한 Supabase PostgreSQL 인스턴스를 공유합니다. **본문 직접 수집은 언론사 이용약관에 따라 비활성화**되어 있습니다. 네이버 연동은 현재 키워드와 날짜로 제목·요약·링크·발행시각을 조회하는 독립 모듈까지 구현됐으며, 파이프라인 저장과 과거 백필 실행기는 아직 연결되지 않았습니다.

---

## Features

| | 기능 | 설명 |
|---|------|------|
| **[RSS 수집]** | 언론사별 파서 | 7개 매체의 전체·카테고리 RSS를 공통 `CanonicalRssEntry`로 변환 |
| **[네이버 검색]** | 키워드·날짜 검색 API | 지정 날짜의 제목·요약·링크·발행시각을 완전성 검증과 함께 반환하는 재사용 모듈 |
| **[카테고리]** | 출처별 분리 저장 | 매체 도메인, 피드 카테고리, XML 원문 카테고리를 구분해 보존 |
| **[중복 방지]** | 결정적 기사 ID | 기사 URL의 SHA-256 해시와 데이터베이스 제약으로 중복 적재 방지 |
| **[진행 표시]** | 수집 진행바·집계 | `collect-rss` 실행 중 소스별 진행바를 표시하고 완료 후 언론사·카테고리별 수집 결과를 표로 출력 |
| **[라이브 모니터]** | Rich TUI 대시보드 | `monitor` 명령이 수집 중 언론사별 수집·적재·중복·실패 현황과 세션 누적을 실시간 표시. 단발 또는 `--interval` 주기 반복 |
| **[본문 수집]** | 비활성화 (이용약관) | 언론사 페이지 직접 수집은 약관 위배로 중단. 네이버 API는 기사 전문이 아닌 제목·요약만 제공 |
| **[오류 격리]** | 기사 단위 실패 격리 | 차단·삭제된 기사 한 건의 실패가 배치를 중단시키지 않고 다음 실행에서 재시도 |
| **[본문 재처리]** | Parser 버전 추적 | 언론사 parser 버전이 바뀌면 기존 기사 본문을 자동으로 다시 수집 |
| **[기초 분석]** | 본문 통계 | 분석기 버전과 본문 해시를 기준으로 문자 수·단어 수 계산 |
| **[Entity 추출]** | 종목 마스터 기반 매칭 | 종목 마스터·별칭 사전 어휘집으로 기사별 종목을 결정적으로 추출, 긴 이름 우선 매칭으로 오탐 방지 |
| **[이벤트 체계]** | 닫힌 taxonomy DTO | LLM 이벤트 분류용 16종 event_type enum과 `taxonomy_version` 추적 DTO |
| **[급등 이벤트 연계]** | 공통 시장 이벤트 활용 | 공통 orchestration이 생성한 `(종목, 급등일)` 데이터셋을 과거 뉴스 검색·사례 구축에 사용 |
| **[멱등 실행]** | 단계별 재실행 | 이미 저장되거나 현재 버전으로 분석된 항목은 다시 처리하지 않음 |
| **[실행 이력]** | 성공·실패 기록 | 명령, 매개변수, 상태, 처리 건수, 제한된 오류 메시지를 저장 |
| **[동시성 보호]** | DB 서버 동시성 | PostgreSQL 서버가 트랜잭션으로 동시 쓰기를 직렬화 (별도 파일 잠금 불필요) |
| **[정기 실행]** | systemd timer | RSS 수집·분석을 30분마다 순차 실행하는 Linux 서비스 예시 제공 |
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
collect-articles (비활성화 — 이용약관)
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

![PostgreSQL](https://img.shields.io/badge/Supabase_PostgreSQL-3FCF8E?style=flat-square&logo=supabase&logoColor=white)
![psycopg](https://img.shields.io/badge/psycopg-3.2+-336791?style=flat-square&logo=postgresql&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-9.0+-0A9EDC?style=flat-square&logo=pytest&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.15+-D7FF64?style=flat-square&logo=ruff&logoColor=black)

---

## Data Sources

| 언론사 | 기본 RSS URL | 요약 필드 |
|--------|--------------|:---------:|
| Investing.com Korea | `https://kr.investing.com/rss/news.rss` | 미사용 |
| 이데일리 | `http://rss.edaily.co.kr/edaily_news.xml` | 사용 |
| 이투데이 | `https://rss.etoday.co.kr/eto/etoday_news_all.xml` | 사용 |
| 한국경제 | `https://www.hankyung.com/feed/all-news` | 미사용 |
| 서울경제 | `https://www.sedaily.com/rss/newsall` | 미사용 |
| 뉴스핌 | `http://rss.newspim.com/news/category/1` | 사용 |
| 동아일보 | `https://rss.donga.com/total.xml` | 미사용 |

모든 RSS 소스는 API 키 없이 수집합니다.

> **본문 수집 정책**: 언론사 웹페이지에서 자동화 수단으로 본문을 수집하는
> 행위는 언론사 이용약관(데이터 크롤링 금지 조항)에 위배되어 모든 매체의
> 본문 직접 수집(`collect-articles`)을 비활성화했습니다. 본문·요약 확보는
> [네이버 뉴스 검색 API](https://developers.naver.com/docs/serviceapi/search/news/news.md)만
> 사용합니다 (빅카인즈는 유료 전환으로 제외). 현재 구현은 검색 결과
> 메타데이터 조회 모듈이며 파이프라인 저장·백필 연결은 후속 범위입니다. 상세 정책은
> [PLAN.md 4.4절](./PLAN.md)을 참고하세요.

기본 소스는 총 72개이며 `collect-rss` 실행 시 전체 피드와 제공된 카테고리별 피드를 함께 수집합니다. 매체별 구성은 Investing.com 16개, 이데일리 1개, 이투데이 11개, 한국경제 12개, 서울경제 12개, 뉴스핌 11개, 동아일보 9개입니다. URL과 카테고리 설정의 기준은 [`pipeline.py`](./pipeline.py)의 `DEFAULT_FEED_SOURCES`입니다.

`--feed publisher=URL` 옵션을 반복하면 지원 언론사의 RSS URL을 실행 단위로 교체할 수 있습니다.

### 카테고리 피드

| 언론사 | 기본 등록 카테고리 |
|--------|--------------------|
| Investing.com Korea | 내부자거래, 주식시장투자아이디어, SEC 공시, 어닝콜 스크립트, 실적보고서와 발표예정일, 애널리스트 투자의견, IPO, 암호화폐, 외환, 많이 본 기사, 주식 시장 뉴스, 상품과 선물 뉴스, 경제 지표 뉴스, 스포츠 및 일반 뉴스, 경제 뉴스 |
| 이투데이 | 금융, 마켓, 부동산, 산업, 경제, 국제, 정치, 사회, 오피니언, 문화/라이프 |
| 한국경제 | 증권, 경제, 부동산, IT, 정치, 국제, 사회, 생활, 오피니언, 스포츠, 연예 |
| 서울경제 | 증권, 부동산, 경제, 정치, 사회, 국제, IT, 오피니언, 생활, 스포츠, 연예 |
| 뉴스핌 | 정치, 경제, 사회, 글로벌, 산업, 증권/금융, 부동산, 라이프/여행, 문화/연예, 스포츠 |
| 동아일보 | 정치, 사회, 경제, 국제, 과학, 연예, 스포츠, 건강 (전체 피드 포함) |
| 이데일리 | 전체 피드만 등록. XML 원문 카테고리는 `source_categories`에 저장 |

카테고리는 용도를 분리해 저장합니다.

- `domain_category`: 매체의 도메인 분류. Investing.com은 `금융`입니다.
- `feed_categories`: 카테고리별 RSS URL에 지정된 분류 목록입니다.
- `source_categories`: RSS XML의 `category` 값을 표준화하지 않고 보존한 목록입니다.

`feed_categories`와 `source_categories`의 빈 배열 `{}`은 수집은 정상적으로 완료됐지만 해당 카테고리가 없다는 뜻입니다. 두 컬럼은 기본값이 빈 배열(`'{}'`)이라 새 행에서 `NULL`이 발생하지 않습니다.

같은 기사 URL이 여러 카테고리 피드에 포함되면 기사 행은 하나만 유지하고 카테고리 목록을 합칩니다.

Investing.com의 `news_462.rss`(뉴스 속보 헤드라인)와 `news_477.rss`(최신 금융 뉴스)는 현재 HTTP 404를 반환하므로 기본 수집 목록에서 제외합니다.

---

## Getting Started

### 사전 요구사항

- Python 3.12+
- `uv`
- finlabs_intelligence와 공유하는 Supabase PostgreSQL 접속 문자열 (`INTELLIGENCE_DATABASE_URL`)

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

# 라이브 모니터 — 수집·적재·실패 현황을 Rich 대시보드로 표시 (1회 또는 주기 반복)
uv run --group news python -m modules.news.main monitor
uv run --group news python -m modules.news.main monitor --interval 60

# (비활성화) 본문 직접 수집 — 언론사 이용약관 위배로 실행이 차단됨
# 제목·요약 검색은 아래의 독립 Naver API 모듈을 사용 (PLAN.md 4.4절)
# uv run --group news python -m modules.news.main collect-articles --limit 100

# 아직 현재 버전으로 분석되지 않은 기사 분석
uv run --group news python -m modules.news.main analyze --limit 100

# 종목 마스터 어휘집으로 기사별 종목 entity 추출 (update-symbols 선행 필요)
uv run --group news python -m modules.news.main extract-entities --limit 100
```

명령은 `INTELLIGENCE_DATABASE_URL`(finlabs_intelligence와 공유하는 Supabase PostgreSQL)에 연결하고 필요한 스키마를 자동으로 생성합니다. DSN은 저장소 루트의 `.env`에 두거나 환경 변수로 export 하면 됩니다.

### 네이버 뉴스 검색 API

네이버 개발자 센터에서 애플리케이션을 등록하고 검색 API 사용 권한을 활성화해야 합니다. 클라이언트는 환경 변수를 직접 읽지 않으므로 자격증명을 호출 측에서 주입합니다.

```python
import os
from datetime import date

from modules.news.naver import NaverNewsClient


with NaverNewsClient(
    client_id=os.environ["NAVER_CLIENT_ID"],
    client_secret=os.environ["NAVER_CLIENT_SECRET"],
) as client:
    articles = client.search("삼성전자", date(2026, 6, 18))

for article in articles:
    print(article.published_at, article.title, article.canonical_url)
```

`search()`는 불변 `NaverNewsArticle` 튜플을 최신 발행순으로 반환합니다. 제목과 요약의 HTML entity 및 `<b>` 강조 태그는 제거되며, 동일 canonical URL은 결정적으로 하나만 유지됩니다. 날짜 비교는 네이버가 반환한 `pubDate`의 원래 UTC offset을 보존한 상태에서 수행합니다.

네이버 API는 검색 결과를 최대 `start=1000`까지만 제공합니다. 지정 날짜의 전체 결과를 확인할 수 없거나 응답의 `total`과 페이지 길이가 모순되면 부분 결과를 반환하지 않고 각각 `NaverNewsIncompleteSearchError` 또는 `NaverNewsMalformedResponseError`를 발생시킵니다. 429와 5xx 및 네트워크 오류는 기본 3회까지 제한적으로 재시도합니다.

공개 오류는 모두 `NaverNewsError`를 상속합니다.

| 오류 | 의미 |
|------|------|
| `NaverNewsValidationError` | 빈 키워드, 잘못된 날짜 또는 잘못된 클라이언트 설정 |
| `NaverNewsAuthenticationError` | 자격증명 누락 또는 인증 실패 |
| `NaverNewsPermissionError` | 애플리케이션의 검색 API 권한 부족 |
| `NaverNewsRateLimitError` | 재시도 후에도 호출 한도 초과 |
| `NaverNewsUpstreamError` | 네트워크 또는 네이버 서버 오류 |
| `NaverNewsMalformedResponseError` | 응답 구조·페이지 메타데이터 불일치 |
| `NaverNewsIncompleteSearchError` | API 페이지 한계로 완전한 날짜 결과를 보장할 수 없음 |

테스트에서는 `HttpTransport` Protocol을 구현한 가짜 transport를 주입할 수 있습니다. 주입한 transport의 생명주기는 호출자가 관리합니다.

### 데이터베이스 연결 지정

모든 명령은 `--dsn` 또는 `INTELLIGENCE_DATABASE_URL`로 Supabase PostgreSQL 접속 문자열을 받습니다. finlabs_intelligence와 같은 인스턴스를 공유하므로 동일한 DSN을 사용합니다.

```bash
export INTELLIGENCE_DATABASE_URL="postgresql://...@aws-...pooler.supabase.com:5432/postgres"
uv run --group news python -m modules.news.main collect-rss

# 또는 명령별 DSN 지정
uv run --group news python -m modules.news.main analyze \
  --dsn "postgresql://...@.../postgres" \
  --limit 200
```

### RSS URL 교체

`publisher` 값은 `investing.com`, `edaily`, `etoday`, `hankyung`, `newspim`, `sedaily`, `donga` 중 하나여야 합니다.

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
| `article_entities` | 기사별 종목 entity와 티커·신뢰도 | `(rss_item_id, entity_type, entity_name)` 기본키 |
| `article_entity_extractions` | 추출기 버전·본문 해시 기준 추출 이력 | `rss_item_id` 기본키 |
| `pipeline_runs` | 명령 실행 상태와 처리 결과 | 실행별 UUID |
| `domestic_symbols` | KIS KOSPI·KOSDAQ 종목 마스터 현재 스냅샷 (finlabs_intelligence 카탈로그와 공유) | `(market, symbol)` 고유 제약 |
| `overseas_symbols` | KIS NASDAQ·NYSE·AMEX 종목 마스터 현재 스냅샷 | `(market, symbol)` 고유 제약 |

발행 시각은 입력 형식을 검증한 뒤 `Asia/Seoul` 기준으로 저장하고, 조회 시 같은 시각대로 복원합니다.

저장소는 finlabs_intelligence와 동일한 Supabase PostgreSQL 인스턴스입니다. 뉴스 테이블은 `intelligence_*` 테이블과 같은 데이터베이스에 공존하며, `domestic_symbols`는 두 도구가 공유합니다(`update-symbols`가 채우고 finlabs_intelligence 카탈로그가 읽습니다). 스키마는 명령 실행 시 `CREATE TABLE IF NOT EXISTS`로 멱등하게 생성됩니다.

`rss_items`의 주요 카테고리 컬럼은 다음과 같습니다.

| 컬럼 | 타입 | 의미 |
|------|------|------|
| `domain_category` | `text` | 매체 전체에 부여한 상위 도메인. 현재 Investing.com의 `금융`만 사용 |
| `feed_categories` | `text[]` | 카테고리별 피드 URL에서 결정된 분류. 중복 기사에서는 목록 병합 |
| `source_categories` | `text[]` | RSS XML이 제공한 원문 분류. 표준화하지 않음 |

---

## Architecture

```text
modules/news/
├── main.py                    Typer CLI와 Supabase PostgreSQL 실행 경계 (--dsn)
├── naver/
│   ├── client.py              키워드·날짜 검색, 페이지네이션, 재시도와 HTTP 경계
│   ├── errors.py              공개 타입 오류 계층
│   └── models.py              불변 검색 결과 모델
├── pipeline.py                RSS·본문·분석 단계와 실행 이력 조율
├── monitor.py                 collect-rss 현황 집계와 Rich 라이브 대시보드
├── articles/
│   └── parsers.py             언론사별 본문 선택자와 parser 버전 registry
├── db/
│   ├── init.py                PostgreSQL 스키마 생성과 연결 팩토리 (resolve_dsn)
│   └── sql.py                 RSS·본문·분석·entity·실행 이력 저장 연산 (psycopg)
├── entities.py                종목 마스터·별칭 사전 기반 entity 추출기
├── schema/
│   ├── article.py             기사 및 분석 모델
│   ├── entity.py              기사 entity 모델
│   ├── event.py               이벤트 taxonomy와 LLM 분류 결과 DTO
│   └── symbol.py              뉴스 DB용 종목 마스터 모델
├── rss/
│   ├── models.py              표준 RSS 모델과 검증
│   └── parsers.py             공통 파서 계약, 설정 기반 파서, 언론사 레지스트리
├── systemd/
│   ├── finlabs-news.service   RSS 수집·분석 순차 실행 서비스
│   ├── finlabs-news.timer     30분 주기 타이머
│   ├── finlabs-news-symbols.service  종목 마스터 갱신 서비스
│   └── finlabs-news-symbols.timer    매일 09:00 KST 갱신 타이머
├── tests/
│   ├── conftest.py            격리 PostgreSQL 스키마 픽스처 (news_connection)
│   ├── test_article_parsers.py  언론사별 본문 선택자 회귀 테스트
│   ├── test_entity_extraction.py  entity 추출·이벤트 taxonomy 회귀 테스트
│   ├── test_monitor.py        라이브 모니터 집계 상태 회귀 테스트
│   ├── test_naver_news.py     네이버 검색·완전성·재시도 회귀 테스트
│   ├── test_rss_pipeline.py   파서·CRUD·멱등성·소스 회귀 테스트
│   └── test_symbols.py        종목 마스터 스냅샷 갱신 회귀 테스트
├── symbols.py                 KIS 다운로드와 뉴스 DB 동기화
└── PLAN.md                    뉴스 모듈 계획서 (v3.0)
```

---

## Operations

`systemd/` 예시는 `/opt/finlabs` 체크아웃을 기준으로 작성되어 있습니다. 배포 환경에 맞게 `User`, `WorkingDirectory`, 그리고 Supabase 접속 문자열(`INTELLIGENCE_DATABASE_URL`)을 조정해야 합니다.

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

각 service는 `EnvironmentFile=-/etc/finlabs-news.env`에서 환경 변수를 읽으므로 그 파일에 `INTELLIGENCE_DATABASE_URL`(과 종목 갱신용 KIS 자격증명)을 둡니다.

`finlabs-news-symbols.timer`는 매일 오전 9시(Asia/Seoul)에 KOSPI·KOSDAQ·NASDAQ·NYSE·AMEX 마스터를 갱신합니다. 다운로드가 비어 있거나 한 시장이라도 실패하면 두 테이블의 기존 스냅샷을 모두 유지합니다.

systemd 없이 더 잦은 주기로 RSS만 수집하려면 `scripts/collect_rss_loop.sh`를 쓸 수 있습니다. 기본 60초 간격으로 `collect-rss`를 멱등 재실행하며(중첩 방지·단일 인스턴스 잠금), `INTERVAL_SECONDS`로 간격을, 추가 인자로 피드를 좁힐 수 있습니다. 전체 72개 피드 한 회는 보통 수 초 안에 끝나지만(피드 fetch가 대부분), 네트워크가 느려 간격을 넘기면 루프가 다음 경계에서 다시 시작합니다.

현황을 눈으로 보며 돌리려면 `monitor` 명령이 같은 수집을 Rich 라이브 대시보드(언론사별 수집·적재·중복·실패 + 세션 누적)로 보여줍니다. `--interval N`을 주면 N초마다 반복하며 다음 실행까지 카운트다운을 표시하고, `Ctrl-C`(SIGINT) 또는 `SIGTERM`에 "모니터를 종료합니다" 메시지와 함께 깨끗이 종료합니다. 헤드리스 자동화에는 루프 스크립트를, 사람이 지켜볼 땐 `monitor`를 쓰세요.

쓰기 동시성은 Supabase PostgreSQL 서버가 트랜잭션으로 직렬화하므로, 여러 서버나 컨테이너가 동시에 같은 데이터베이스를 안전하게 사용할 수 있습니다. 연결은 `update-symbols`/`replace_article_entities`처럼 원자성이 필요한 연산만 명시적 트랜잭션으로 감싸고, 나머지는 statement 단위로 자동 커밋합니다.

---

## Testing

테스트는 실제 RSS 서버를 호출하지 않고 고정된 feedparser 데이터를 사용하며, DB 의존 테스트는 `INTELLIGENCE_TEST_DATABASE_URL`이 가리키는 PostgreSQL에 매 테스트마다 격리된 스키마를 만들어 실행합니다(미설정 시 자동 skip).

```bash
export INTELLIGENCE_TEST_DATABASE_URL="postgresql://...@localhost:5432/test"
uv run --group news python -m pytest modules/news/tests/test_rss_pipeline.py -q
uv run --group news python -m pytest modules/news/tests/test_symbols.py -q
uv run ruff check modules/news
```

현재 회귀 범위는 다음 동작을 포함합니다.

- 언론사별 표준 모델 변환과 URL 검증
- 서울 시간대 정규화
- RSS CRUD와 중복 삽입 방지
- 카테고리 원문 보존과 중복 기사 카테고리 병합
- RSS → 본문 → 분석 단계의 멱등성
- 성공·실패 실행 이력
- 국내·해외 종목 마스터 분리 저장과 5개 시장의 원자적 스냅샷 교체
- 빈 다운로드 결과에서 기존 종목 마스터 보존

---

## Current Scope

`collect-articles`(언론사 페이지 본문 직접 수집)는 언론사 이용약관 위배로 **비활성화**되어 실행 시 안내 메시지와 함께 종료됩니다. 네이버 검색 클라이언트는 독립 공개 API로 구현됐지만 CLI, PostgreSQL 저장, 백필 체크포인트에는 아직 연결되지 않았습니다. 네이버 API는 기사 전문을 제공하지 않으므로 이후 분석 입력은 제목과 요약을 기준으로 구성합니다.

`analyze` 단계는 `basic-stats-v1` 분석기로 문자 수와 공백 기준 단어 수만 계산합니다. `extract-entities` 단계는 종목 마스터와 소규모 별칭 시드(삼전, 하이닉스, 네이버)로 종목 entity만 추출하며, 기업·산업·키워드 entity는 아직 추출하지 않습니다. 급등 이벤트의 계약·KIS/Toss 정규화·판정·저장은 각각 `modules.domain`, `modules.adapters`, `modules.orchestration`, `modules.storage`가 소유하며, 이 모듈은 해당 `(종목, 급등일)`을 뉴스 검색과 사례 라이브러리에 연결합니다. 이벤트 분류는 16종 taxonomy와 `ArticleEvent` DTO까지 구현되어 있고 LLM 호출 파이프라인은 미구현입니다. 전면적인 별칭 사전 구축, 과거 뉴스 백필, 임베딩·Vector Store, 점수화, 백테스트, 대시보드는 아래 로드맵의 대상입니다.

---

## Roadmap

[PLAN.md](./PLAN.md)의 개발 로드맵 요약입니다. 데이터 축적(백필, 급등 사례 라벨링)에 시간이 걸리므로 Cold Start 해소 작업을 가장 앞에 배치합니다.

| 단계 | 범위 | 상태 |
|------|------|:----:|
| **초기** (2~4주) | RSS 수집·본문 수집·Supabase PostgreSQL 저장 | ✅ 구현됨 |
| | KIS 종목 마스터 자동 갱신 | ✅ 구현됨 |
| | 종목 마스터 기반 entity 추출, 이벤트 taxonomy·분류 DTO | ✅ 구현됨 |
| | 공통 시장 계층의 KIS/Toss 일봉 기반 과거 급등 이벤트 추출 | ✅ 구현됨 |
| | 네이버 뉴스 검색 클라이언트 | ✅ 구현됨 |
| | 네이버 검색 결과 저장·과거 뉴스 백필, 별칭 사전 확장, Streamlit 기본 조회 | 예정 |
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
