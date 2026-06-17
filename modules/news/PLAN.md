# FinLabs News Intelligence — 뉴스 모듈 계획서 (v3.0)

> 이 문서는 `modules/news`가 소유하는 RSS 수집, 기사 파싱, 뉴스 분석,
> 사례 라이브러리와 점수화 계획만 다룬다. 전체 로드맵과 데이터 플랫폼은
> [루트 PLAN](../../PLAN.md)을 기준으로 하며 저장·전송 정책은 해당 모듈
> PLAN을 단일 원본으로 사용한다.

## 1. 프로젝트 개요

**프로젝트명**: FinLabs News Intelligence

**목표**: 국내 주식 시장(코스피·코스닥)의 뉴스를 실시간 수집·분석하여, 익일 또는 3거래일 이내 +10% 이상 상승 가능성이 있는 종목을 조기에 탐지하는 시스템 구축.

**핵심 차별점**: 단순 감성 분석이 아니라 **"과거 급등 직전 뉴스 패턴과의 유사도(Vector Similarity Factor)"**를 핵심 신호로 사용. "좋은 뉴스인가?"가 아니라 "과거 급등 직전 뉴스와 얼마나 비슷한가? 그리고 **급등하지 않은 유사 뉴스와는 얼마나 다른가?**"를 판단한다. 여기에 **Market Context Features(거래대금·변동성·테마 확산·시장 국면)**를 결합해 "재료의 질"과 "재료를 받아들일 시장 환경"을 함께 평가한다.

---

## 2. 핵심 설계 원칙 (v2에서 추가)

본 개정판은 다음 5가지 원칙을 시스템 전반에 강제한다.

1. **Point-in-Time 무결성**: 모든 검색·점수 계산은 평가 시점 이전 데이터만 사용한다. 백테스트 엔진이 미래 데이터를 참조할 수 없도록 구조적으로 차단한다.
2. **Contrastive 비교**: 급등 사례(positive)뿐 아니라 비급등 유사 사례(negative)와 함께 비교한다. 급등 사례하고만 비교하면 "공급 계약" 류의 흔한 기사가 모두 고득점을 받아 Precision이 붕괴한다.
3. **데이터 우선**: 과거 뉴스 백필과 급등 사례 라벨링이 프로젝트의 본체이므로 로드맵 초·중기로 앞당긴다. RSS만으로는 라이브러리 축적에 6개월~1년이 걸린다(Cold Start).
4. **베이스라인 대비 검증**: 모든 성능 지표는 랜덤 선택, 단순 키워드 점수, 거래대금 모멘텀 등 베이스라인과 비교해 보고한다.
5. **뉴스 + 시장의 결합** (v2.2): 급등은 뉴스 단독이 아니라 거래량·변동성·테마·시장 국면과의 결합으로 발생한다. 뉴스 팩터와 Market Context features를 하나의 학습 모델에 함께 입력해 상호작용을 학습시킨다.

---

## 3. 뉴스 모듈 아키텍처

```
RSS Sources / Historical Backfill
                ↓
         News Collector
                ↓
      Article Fetcher / Parser
                ↓
    PostgreSQL news schema
                ↓
 Entity / Event / Dedup Pipeline
                ↓
 Surge / Negative Case Library
                ↓
 News Features + Market Context
                ↓
 Scoring / Backtest / Explanation
```

PostgreSQL, Redis, Parquet, 실시간 시장 데이터와 장 운영 정보의 상세 설계는
[루트 PLAN](../../PLAN.md)의 모듈별 링크를 따른다.

---

## 4. 데이터 수집

### 4.1 실시간 수집 (RSS)

- **대상**: 연합뉴스, 한국경제, 매일경제, 이데일리, 서울경제, Investing.com
- **주기**: 5분
- **테이블**: `rss_sources`, `rss_items`

`rss_items` 스키마:

```
id, source_id, rss_guid, rss_url, canonical_url,
title, summary, published_at, collected_at,
unique_key, article_status
```

### 4.2 과거 뉴스 백필 (v2 신규, 초기 단계 필수)

- **목적**: Cold Start 해소. 급등 사례 라이브러리를 수집 시작일 이전 데이터로 채운다.
- **소스**: [네이버 뉴스 검색 API](https://developers.naver.com/docs/serviceapi/search/news/news.md)만 사용한다.
  빅카인즈(BIGKinds)는 유료로 전환되어 사용하지 않는다 (v3.1).
- **범위**: 최소 과거 2~3년
- **방법**: 급등 이벤트를 먼저 시세 데이터로 추출 → 해당 종목·기간 뉴스 역수집

### 4.3 중복 제거 (2단계)

**1단계 — URL/메타 기반** (수집 시):
1. guid
2. canonical_url
3. normalized_url
4. title + published_at

**2단계 — 콘텐츠 기반** (v2 신규, 임베딩 생성 후):
- 임베딩 유사도가 임계값(예: 0.97) 이상이면 동일 콘텐츠 클러스터로 묶는다.
- 통신사 기사 전재(연합뉴스 → 각 매체) 문제 해결. **뉴스 확산도 점수는 클러스터 단위로 계산**해 전재 기사로 인한 부풀림을 방지한다.

### 4.4 기사 본문 수집 (v3.1 — 직접 수집 비활성화)

> **이용약관 정책 (v3.1)**: 언론사 웹페이지에서 자동화 수단으로 본문을
> 수집·복제하는 행위는 언론사 이용약관(데이터 크롤링 금지 조항)에
> 위배되므로 **`collect-articles` 직접 수집을 비활성화한다**. 구현 코드와
> 선택자 registry, 저장·재처리 로직은 허용된 소스 연동 시 재사용을 위해
> 유지하되 CLI에서 실행을 차단한다.
>
> 본문·요약 확보는 **[네이버 뉴스 검색 API](https://developers.naver.com/docs/serviceapi/search/news/news.md)만 사용한다**.
> 빅카인즈는 유료로 전환되어 사용하지 않는다. 네이버 API는 전문이 아닌
> 제목·요약(description)·링크·발행시각을 제공하므로, 본문 의존 분석은
> 제목+요약 기준으로 재정의한다.

- 대상: `article_status = pending`
- 테이블: `articles`

```
id, rss_item_id, canonical_url, title, publisher,
author, cleaned_text, parser_version, published_at, fetched_at
```

> **저작권 정책 (v3)**: 정제 본문만 영구 보관한다. 원문 HTML은 파싱
> 과정에서만 사용하고 영구 저장하지 않는다.

- 언론사별 본문 선택자는 registry에서 관리한다 (비활성 상태로 유지).
- 선택자 변경 시 `parser_version`을 올리고 이전 버전의 기사만 재처리한다.

---

## 5. 종목 마스터 / Entity 추출

### 5.1 종목 마스터 (v2 신규, 독립 작업으로 분리)

종목명→티커 매핑은 공수가 큰 별도 작업이다.

- KRX 종목 마스터 테이블 (상장/폐지 이력 포함)
- **별칭 사전**: 약칭(삼전, 하이닉스), 옛 사명, 영문명
- 우선주/지주사/스팩 구분 규칙

### 5.2 Entity 추출

- 추출 대상: 종목, 기업, 산업, 키워드 (예: 삼성전자, SK하이닉스, HBM, AI반도체)
- 테이블: `article_entities`

```
article_id, entity_type, entity_name, ticker, confidence
```

---

## 6. Vector Store

### 6.1 저장 구조 (v2 수정)

```
article_id
title
tickers            ← 리스트형. 한 기사가 여러 종목을 다루므로 1:1 필드 불가
published_at       ← point-in-time 필터의 기준
embedding
embedding_model    ← 모델 교체 시 재임베딩 추적용 (필수)
model_version
dup_cluster_id     ← 콘텐츠 중복 클러스터 ID
```

### 6.2 임베딩 모델 (v2 신규)

한국어 금융 텍스트 기준 후보 비교 실험을 초기 단계에 수행:

- multilingual-e5-large
- KURE (한국어 특화)
- OpenAI text-embedding-3 계열

선정 기준: surge library 내 유사 사례 검색의 Precision@k.

### 6.3 DB 선택

| 단계 | 선택 | 이유 |
|---|---|---|
| 초기 후보 | **재선정 필요** | v2의 DuckDB VSS 결정은 데이터 플랫폼 v3 전환으로 보류. PostgreSQL 연계성과 point-in-time 필터를 기준으로 재평가 |
| 대안 | ChromaDB | 설치 쉬움, 로컬 실행 |
| 중기 | Qdrant | 고속 검색, 풍부한 필터링, 운영 안정성 |

### 6.4 Point-in-Time 검색 강제 (v2 핵심)

- 모든 유사도 검색은 `published_at < 평가 시점` AND `surge_date < 평가 시점` 필터를 **검색 레이어에서 강제**한다.
- 백테스트 엔진은 필터 없는 raw 검색 API에 접근할 수 없도록 인터페이스를 분리한다.
- 이를 어기면 백테스트 성능이 허위로 부풀려진다 (look-ahead bias).

---

## 7. 사례 라이브러리 (핵심 자산)

### 7.1 급등 사례 라이브러리 (Positive)

**급등 정의**: 거래대금 100억 이상 AND (익일 +10% OR 3거래일 내 +10%)

**테이블**: `surge_news_library`

```
article_id, ticker, surge_date,
return_1d, return_3d, return_5d
```

> 기사의 이벤트 정보(event_type, entities, industry)는 `article_events` 테이블(7.3절)에 저장하고 article_id로 조인한다. 급등의 "원인" 여부를 별도 라벨로 저장하지 않는다 — 어떤 이벤트 유형이 급등과 연결되는지는 학습 모델이 데이터에서 발견한다.

### 7.2 라이브러리 구축 파이프라인 — 전 과정 자동화 (v2.1 상세화)

사람이 기사를 직접 검색·수집·라벨링하는 단계는 없다. 전체가 다음 배치 파이프라인으로 자동 실행되며, 사람의 역할은 마지막 샘플 검증뿐이다.

```
① 시세 데이터
   → "거래대금 100억 + 익일/3거래일 내 +10%" 조건으로
     (종목, 급등일) 이벤트 목록 추출            [코드]
        ↓
② 후보 기사 자동 수집
   - 백필 구간: 네이버 뉴스 검색 API에
     "종목명+별칭 × 급등일 이전 7일" 쿼리       [코드]
   - 실시간 구간: RSS 수집분에서 entity 매칭     [코드]
        ↓
③ 규칙 기반 1차 필터
   종목 entity가 제목/리드 문단에 등장하는 기사만 통과
   → LLM 호출량을 이벤트당 5~20건으로 축소      [코드]
        ↓
④ LLM 이벤트 분류 (7.3절)                      [LLM]
        ↓
⑤ 샘플 검증 100~200건                          [사람]
```

운영 시 주의:
- **②의 품질은 별칭 사전에 좌우된다.** "삼전", 옛 사명, 영문명으로만 보도된 기사는 정식 종목명 쿼리로 잡히지 않는다. 종목 마스터 + 별칭 사전(5.1절)이 선행 작업인 이유.
- **API 호출 한도**: 네이버 뉴스 API는 일 25,000건 제한이 있으므로, 2~3년치 백필은 며칠에 걸쳐 분할 실행하도록 스케줄링한다.
- 급등일에 가까운 기사일수록 가중치를 부여해 저장한다.

### 7.3 LLM 이벤트 분류 (v2.3 전면 수정)

#### 7.3.1 설계 변경의 배경

v2.1까지의 과제였던 **"이 기사가 급등의 직접적 재료인가?"는 인과 판단이라 개념이 애매하다.** 같은 기사를 보고도 사람마다 yes/no가 갈리고, LLM 라벨의 일관성도 보장하기 어렵다.

v2.3에서는 과제를 **"이 기사는 어떤 이벤트를 다루고 있는가?"**라는 객관적 분류 문제로 바꾼다.

- LLM의 역할: 기사에서 **사실(이벤트 유형, 관련 기업, 산업)을 추출**하는 것까지만. 주관적 인과 판단을 하지 않는다.
- 인과 발견의 역할: **학습 모델(8.3절)로 이관**한다. event_type을 feature로 넣으면, 어떤 이벤트 유형이 어떤 시장 환경에서 급등과 자주 연결되는지를 모델이 데이터에서 스스로 발견한다. 예컨대 "regulatory_approval × biotech × 테마 강세"의 급등 확률이 높다는 패턴은 사람이 정의하는 게 아니라 학습된다.

부수 효과로 적용 범위가 넓어진다. "급등의 원인" 라벨은 급등이 일어난 뒤에만 붙일 수 있었지만, **이벤트 분류는 급등 여부와 무관하게 모든 기사에 적용**할 수 있다. 따라서 surge library뿐 아니라 negative library, 그리고 **실시간 유입 기사에도 동일한 분류기를 그대로 사용**한다 — 라벨링 파이프라인이 곧 실시간 feature 생성 파이프라인이 된다.

#### 7.3.2 이벤트 분류 체계 (Taxonomy)

자유 서술이 아니라 **닫힌 목록(enum)**으로 강제한다. 자유 서술을 허용하면 "공급계약", "납품 계약", "supply deal"처럼 같은 이벤트가 다른 라벨로 파편화되어 feature로 쓸 수 없다.

| event_type | 정의 | 예 |
|---|---|---|
| `contract_supply` | 공급·납품 계약 체결/확대 | 삼성전자, 엔비디아에 HBM 공급 확대 |
| `order_win` | 수주 (건설·방산·플랜트 등) | 두산에너빌리티, 원전 수주 |
| `regulatory_approval` | 인허가·승인 (FDA, 식약처 등) | 셀트리온, FDA 승인 획득 |
| `clinical_result` | 임상 결과 발표 | 임상 3상 1차 지표 달성 |
| `earnings` | 실적 발표·전망 (서프라이즈 포함) | 영업이익 컨센서스 상회 |
| `product_launch` | 신제품·신서비스 출시 | 카카오, AI 서비스 출시 |
| `tech_patent` | 신기술 개발·특허 | 고체전해질 특허 등록 |
| `partnership` | 제휴·협력·MOU | 글로벌 빅테크와 협력 |
| `ma_investment` | M&A·지분 투자·유치 | 경영권 인수, 대규모 투자 유치 |
| `capital_change` | 유상증자·감자·CB 발행 | 주주가치에 양/음 모두 가능 |
| `policy_theme` | 정부 정책·테마 편입 | 정책 수혜주 부각 |
| `litigation_risk` | 소송·제재·악재 | 공정위 제재 |
| `management` | 경영진·지배구조 변화 | 대표 교체, 승계 |
| `market_commentary` | 시황·업종 일반 기사 | 코스피 전망 |
| `simple_mention` | 타 기업이 주인공, 단순 언급 | 경쟁사 기사에 언급 |
| `other` | 위에 없는 유형 | — |

> 초기 16종으로 시작하고, 검증 과정에서 `other` 비중이 높으면 유형을 추가한다. taxonomy 변경 시 `taxonomy_version`을 올리고 영향 구간을 재분류한다.

**노이즈 처리도 이 체계 안에서 해결된다**: 기존의 "no(원인 아님)" 판정 대신, `market_commentary`·`simple_mention`으로 분류된 기사를 라이브러리의 유사도 검색 대상에서 제외하면 된다. "원인인가?"라는 주관 판단 없이 객관적 유형 기준으로 같은 효과를 얻는다.

#### 7.3.3 출력 스키마와 저장

**테이블**: `article_events` (모든 기사 대상, surge library 전용 아님)

```
article_id,
event_type,        ← taxonomy enum
entities,          ← 이벤트의 주체 기업 리스트 (JSON)
tickers,           ← entities를 종목 마스터로 매핑한 결과
industry,          ← semiconductor, biotech, software, ...
specificity,       ← high/low: 금액·수량·기간이 명시됐는가
confidence,        ← 0.0~1.0
reason,            ← 한 문장 근거 (검증용)
label_model, prompt_version, taxonomy_version
```

`specificity`는 선택 필드지만 권장한다 — "1조원 규모 공급 계약"과 "공급 논의 중"은 같은 contract_supply라도 시장 반응이 다르며, 이 구분도 학습 feature가 된다.

#### 7.3.4 프롬프트 설계

입력: 기사 제목 + 본문 앞부분(1,000~2,000자) + 발행일. (급등일 정보는 불필요해졌다 — 분류는 급등과 무관한 과제이므로)

```
당신은 금융 뉴스 분석가입니다. 아래 기사가 다루는
이벤트를 분류하세요.

event_type은 반드시 다음 중 하나:
contract_supply, order_win, regulatory_approval,
clinical_result, earnings, product_launch, tech_patent,
partnership, ma_investment, capital_change, policy_theme,
litigation_risk, management, market_commentary,
simple_mention, other

[각 유형의 정의 서술...]

예시:
"삼성전자, 엔비디아에 HBM 공급 확대"
→ {"event_type": "contract_supply",
   "entities": ["삼성전자", "엔비디아"],
   "industry": "semiconductor", "specificity": "low"}

"카카오, AI 서비스 출시"
→ {"event_type": "product_launch",
   "entities": ["카카오"],
   "industry": "software", "specificity": "low"}

"셀트리온, FDA 승인 획득"
→ {"event_type": "regulatory_approval",
   "entities": ["셀트리온"],
   "industry": "biotech", "specificity": "high"}

기사 발행일: 2025-03-10
제목: ...
본문: ...

JSON으로만 응답:
{"event_type": "...", "entities": [...],
 "industry": "...", "specificity": "high|low",
 "confidence": 0.0~1.0, "reason": "한 문장"}
```

설계 원칙:
- **taxonomy 전체와 각 유형의 정의를 프롬프트에 명시**한다. 정의 없이 유형명만 주면 경계 사례에서 흔들린다.
- **few-shot 예시에 경계 사례 포함**: contract_supply vs partnership(계약 체결 vs MOU), product_launch vs tech_patent(출시 vs 개발) 같은 혼동 쌍을 예시로 넣는다. 검증에서 발견한 혼동 사례를 재활용한다.
- **출력의 event_type을 코드에서 enum 검증**하고, 목록 밖 값이 나오면 재시도한다.
- entities는 LLM이 추출한 기업명 그대로 받고, **티커 매핑은 종목 마스터(5.1절)로 코드에서 처리**한다. LLM에게 티커를 직접 묻지 않는다 (환각 위험).

#### 7.3.5 배치 실행 코드 골격

```python
def classify_article(article):
    prompt = build_prompt(article)
    resp = call_llm(prompt, temperature=0)
    result = parse_json_with_retry(resp)   # 코드펜스 제거, 재시도
    assert result["event_type"] in EVENT_TAXONOMY  # enum 검증
    tickers = map_to_tickers(result["entities"])   # 종목 마스터 매핑
    db.execute("""
        INSERT INTO article_events
        (article_id, event_type, entities, tickers, industry,
         specificity, confidence, reason,
         label_model, prompt_version, taxonomy_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [article.id, result["event_type"],
          json.dumps(result["entities"]), json.dumps(tickers),
          result["industry"], result["specificity"],
          result["confidence"], result["reason"],
          MODEL_NAME, PROMPT_VERSION, TAXONOMY_VERSION])
```

구현 규칙:
- **temperature=0** 고정 (재현성 확보)
- JSON 파싱 실패·enum 위반 대비 **재시도 로직**
- `label_model`, `prompt_version`, `taxonomy_version`을 반드시 저장 — 모델·프롬프트·분류 체계를 바꿔 재분류할 때 어느 구간을 다시 돌려야 하는지 추적

#### 7.3.6 비용 전략

- 분류 과제이므로 고성능 모델은 불필요하다. **Haiku급 경량 모델**로 충분하다.
- 본문을 2,000자로 절단하면 수천 건도 수 달러 수준.
- 백필 구간은 **Batch API**(약 50% 할인)로 처리한다.
- 실시간 구간은 기사 유입 시점에 1회 분류 — 이후 모든 단계(라이브러리, 점수화)가 결과를 재사용하므로 기사당 LLM 호출은 1회로 끝난다.

#### 7.3.7 검증 루프 — 사람의 역할

사람이 개입하는 유일한 지점. 수천 건을 손으로 분류하지 않는다.

1. **샘플 검증 (필수)**: 무작위 100~200건을 직접 검토해 사람-LLM 분류 일치율을 측정한다.
   - 일치율 ≥ 90% → 나머지는 LLM에 위임
   - 일치율 < 90% → **혼동 행렬로 어떤 유형 쌍이 헷갈리는지 분석** (예: partnership↔contract_supply) → 해당 유형의 정의를 명확화하거나 few-shot에 경계 사례 추가 → 프롬프트 버전 올리고 해당 구간 재분류
2. **저신뢰 건 처리**: confidence가 낮거나 `other`로 분류된 건은 (a) 샘플링해 사람이 확인하거나 (b) 새 유형 추가의 신호로 활용한다.
3. **유형 분포 모니터링**: `other`·`simple_mention` 비중이 비정상적으로 높으면 taxonomy나 규칙 필터(③)에 문제가 있다는 신호다.

### 7.4 비급등 사례 라이브러리 (Negative, v2 신규)

- 급등 기사와 유사한 주제(계약, 수주, 특허 등)이지만 **급등으로 이어지지 않은** 기사를 별도 저장: `non_surge_news_library`
- 구성 방법: surge library 기사와 임베딩 유사도가 높지만 해당 종목이 이후 3거래일 내 +10%를 달성하지 못한 기사를 자동 수집
- **이벤트 분류 도입으로 구성이 더 정교해진다** (v2.3): "같은 event_type인데 급등하지 않은 기사"를 직접 쿼리할 수 있다. 예: contract_supply 기사 전체 중 급등 미달성 건 → contrastive 비교가 동일 유형 내에서 이루어져 변별력이 올라간다.

---

## 8. 점수화 — 뉴스 팩터 + Market Context (v2.2 확장)

> 같은 뉴스라도 시장 국면에 따라 결과가 다르다. 뉴스 팩터는 "재료의 질"을, Market Context는 "재료를 받아들일 시장 환경"을 측정한다. 급등은 둘의 결합으로 발생하므로 뉴스만으로 예측하는 것은 구조적으로 한계가 있다.

### 8.1 뉴스 팩터

| 팩터 | 내용 |
|---|---|
| **Event Type** | (v2.3 신규) LLM 이벤트 분류 결과(7.3절)를 범주형 feature로 사용. industry, specificity 포함. 어떤 이벤트 유형이 급등과 연결되는지는 학습 모델이 발견 |
| Sentiment | 긍정/중립/부정. **범용 모델 대신 KR-FinBERT 또는 LLM 분류 사용** (v2) |
| Novelty | 최근 30일 내 등장 빈도 기반 신규성 |
| Urgency | 수주, 계약, 특허, 실적, 승인 등 긴급 키워드 |
| News Spread | 같은 내용 기사 수. **콘텐츠 중복 제거 후 클러스터 단위 카운트** (v2) |
| **Contrastive Similarity** | (v2 수정) `sim(급등 사례 Top-k 평균) − sim(비급등 사례 Top-k 평균)`. 급등 패턴과 비슷하면서 흔한 패턴과는 다른 기사에 고득점. **동일 event_type 내에서 비교하면 변별력 상승** (v2.3) |
| Source Trust | (v2 신규) 발행처 신뢰도. 작전성 보도자료·홍보성 기사에 낚이는 것을 방지 |

### 8.2 Market Context Features (v2.2 신규)

#### 8.2.1 종목 레벨

| Feature | 내용 | 의미 |
|---|---|---|
| 거래대금 이상치 | 전일 거래대금 ÷ 20일 평균 거래대금 | 자금 유입의 선행 신호. 뉴스 + 거래대금 급증의 결합이 강력 |
| 변동성 | 20일 historical volatility, ATR | 변동성이 깨어 있는 종목이 재료에 민감하게 반응 |
| 가격 위치 | 52주 고가/저가 대비 현재가 위치 | 신고가 근접(돌파 대기) vs 바닥권(반등 재료)은 다른 패턴 |
| 단기 모멘텀 | 5일/20일 수익률 | 이미 움직이기 시작했는지 |
| 시가총액 | 로그 시총 | 소형주일수록 동일 재료에 대한 가격 탄력이 큼 |
| 유통 물량 | 유통주식비율 (가능 시) | 물량이 가벼울수록 급등 용이 |

#### 8.2.2 섹터/테마 레벨

| Feature | 내용 | 의미 |
|---|---|---|
| 섹터 모멘텀 | 동일 업종 지수의 5일/20일 수익률 | 주도 섹터의 재료가 더 잘 먹힘 |
| 테마 확산 | 동일 테마 내 최근 3거래일 급등 종목 수 | 테마 순환매 국면 포착. "두 번째, 세 번째 급등주" 탐지 |
| 섹터 거래대금 집중도 | 해당 섹터 거래대금 ÷ 시장 전체 거래대금 | 시장 자금이 어디에 몰려 있는지 |

#### 8.2.3 시장 레벨 (국면/Regime)

| Feature | 내용 | 의미 |
|---|---|---|
| 지수 수익률 | KOSPI/KOSDAQ 5일/20일 수익률 | 강세장 vs 약세장에서 재료 수용성이 다름 |
| 시장 변동성 | VKOSPI 또는 지수 realized volatility | 공포 국면에서는 호재도 묻힘 |
| 시장 폭 | 상승종목비율(ADR) | 시장 체력 |
| 투기 심리 | 일별 상한가 종목 수, 코스닥 거래대금 비중 | 급등이 잘 나오는 "판"인지에 대한 직접적 proxy |

#### 8.2.4 저장 및 Point-in-Time 규칙

**테이블**: `market_features`

```
ticker, as_of_date,
turnover_ratio_20d, volatility_20d, atr_14,
price_position_52w, return_5d, return_20d,
log_market_cap, sector_momentum, theme_spread_count,
market_return_5d, market_volatility, adr, limit_up_count
```

- **모든 feature는 전일 종가 기준(as_of_date = 평가일 전일)으로 계산한다.** 당일 거래량·종가는 장중에 알 수 없으므로 사용 시 look-ahead bias가 발생한다.
- 시세 원천: pykrx 등. 급등 이벤트 추출(7.2절 ①)에 이미 시세 수집이 필요하므로 동일 파이프라인에서 feature를 함께 생성한다 — 추가 수집 비용이 거의 없다.
- **생존 편향 주의**: 상장폐지 종목도 과거 시점 데이터에 포함해야 한다. 현재 상장 종목만으로 백테스트하면 성과가 부풀려진다.

#### 8.2.5 뉴스 팩터와의 결합 방식

별도의 "시장 점수"를 만들어 수동 가중치로 더하지 않는다. **뉴스 팩터 6개 + Market Context features를 하나의 feature 벡터로 묶어 학습 모델(8.3절)에 함께 입력**한다. 이렇게 하면:

- "강세 테마 + 유사도 높은 뉴스 + 거래대금 이상치" 같은 **상호작용을 모델(LightGBM)이 자동 학습**한다.
- 약세장에서는 뉴스 점수의 기여가 자동으로 할인되는 국면 적응이 별도 규칙 없이 달성된다.
- 이것이 수동 가중치를 폐기하고 학습 기반 점수화를 채택한 또 하나의 이유다 — 수동 가중치로는 feature가 늘어날수록 조합이 불가능해진다.

추가로, feature importance 분석을 통해 "뉴스 단독 vs 뉴스+시장 결합"의 성능 차이를 정량화한다. 이 비교 자체가 시스템의 가치를 증명하는 핵심 실험이다.

### 8.3 최종 점수 — 학습 기반 가중치 (v2 수정)

수동 가중치(0.20/0.15/0.15/0.15/0.35)는 근거가 없으므로 폐기하고, **뉴스 팩터 + Market Context features 전체를 feature로 하여 로지스틱 회귀 또는 LightGBM으로 학습**한다.

- 라벨: 익일/3거래일 내 +10% 달성 여부
- 학습/검증 분리: 시계열 기준 walk-forward (랜덤 분할 금지)
- 초기 데이터 부족 시: 수동 가중치 + 뉴스 팩터만으로 시작하되, 백테스트에서 grid search로 보정. "수동 vs 학습", "뉴스 단독 vs 뉴스+시장" 비교 자체가 검증 자료이자 논문 소재가 된다.

---

## 9. 백테스트 (v2 대폭 강화)

### 9.1 현실성 규칙

- **진입 시점 통일**: 뉴스 발행 시각 기준 익일 시가 진입 (장중 발행 기사도 동일 적용. 장 마감 후 기사는 익일 시가)
- **체결 가능성**: 시가가 이미 상한가이거나 갭이 임계값 이상이면 체결 불가 처리. 상한가 종목 매수 불가 모델링 없이는 Hit Rate가 환상이다.
- **비용 반영**: 수수료, 거래세, 슬리피지(보수적으로 설정)

### 9.2 베이스라인 비교

다음과의 상대 성능으로 보고:
1. 랜덤 5종목 선택
2. 단순 키워드 점수만 사용
3. 거래대금 모멘텀 전략

### 9.3 지표

- Top-5 평균 수익률, Hit Rate (+10% 달성 비율)
- Precision@5, Precision@10, Recall
- Sharpe Ratio, Max Drawdown
- **Lift**: 익일 +10%는 희귀 이벤트이므로 base rate 대비 배수로 보고 (v2)

---

## 10. RAG 기반 설명

사용자 질문: "왜 이 종목이 추천됐지?"

1. Vector Search로 관련 뉴스 Top-10 검색 (point-in-time 필터 적용)
2. LLM 입력: 관련 뉴스 + 팩터별 점수 + 과거 유사 급등/비급등 사례
3. 출력: 추천 이유, 위험 요소, 유사 사례
4. **인용 강제** (v2): 모든 주장에 근거 기사 ID를 인용하도록 프롬프트와 출력 검증을 설계해 환각을 차단

---

## 11. Dashboard (Streamlit)

- Top-5 추천 종목: 종목명, 최종 점수, 팩터별 기여도
- 유사 급등 사례 / 유사 비급등 사례 나란히 표시 (v2)
- 관련 뉴스 수(중복 제거 후), 최근 뉴스
- 백테스트 성능 vs 베이스라인 차트

---

## 12. 개발 로드맵 (v2 재구성)

> 변경 핵심: 데이터 축적(백필, 급등 라벨링)은 시간이 걸리므로 가장 먼저 시작한다. 감성 분석은 후순위로 미룬다.

### 초기 (2~4주)

- RSS 수집, PostgreSQL `news` 스키마 저장
- **네이버 뉴스 검색 API 연동 (본문·요약 확보의 단일 경로, 4.4절)**
- **종목 마스터 + 별칭 사전 구축**
- **과거 뉴스 백필 파이프라인 (네이버 뉴스 검색 API)**
- **시세 데이터로 과거 급등 이벤트 추출**
- Streamlit 기본 조회 화면

### 중기 (1~2개월)

- 임베딩 모델 비교 실험 → 선정
- Vector Store 선정 및 구축 (point-in-time 필터 레이어 필수)
- **급등 사례 라이브러리 + LLM 이벤트 분류 (taxonomy 기반)**
- **비급등(negative) 라이브러리 구축**
- **Market Context features 생성 파이프라인** — 시세 수집이 초기부터 있으므로 추가 비용이 작다. 종목 레벨 feature부터 구현, 섹터/시장 레벨은 순차 확장 (v2.2)
- Entity 추출, Contrastive Similarity 점수
- 콘텐츠 기반 중복 제거

### 후기 (2~3개월)

- 학습 기반 점수화 (LightGBM / 로지스틱 회귀) — **뉴스 팩터 + Market Context 결합 입력** (v2.2)
- "뉴스 단독 vs 뉴스+시장" 성능 비교 실험 (v2.2)
- 백테스트 엔진 (체결 가능성, 비용, 베이스라인)
- 감성 분석 (KR-FinBERT), Source Trust 팩터
- RAG 설명 + 인용 강제
- Dashboard 고도화

### 확장 (장기)

- Qdrant 이전 검토
- FinLabs 캔들 토큰화 연구와 결합 → **뉴스 토큰 + 캔들 토큰 멀티모달 예측** (논문 주제 후보)

### 12.1 현재 구현 상태 (2026-06-13)

최근 변경사항과 현재 코드를 기준으로 로드맵 진행 상태를 다음처럼 판정한다.

| PLAN 항목 | 상태 | 근거 |
|---|---|---|
| RSS 수집과 1단계 중복 방지 | **구현됨** | `pipeline.py:466`의 매체별 병렬 수집, `db/init.py:77`의 URL 고유 제약, `main.py:193`의 CLI |
| 종목 마스터 동기화 | **부분 구현** | `main.py:133`의 KIS 국내·미국 5개 시장 갱신. 상장·폐지 이력과 시점별 마스터는 아직 없음 |
| 종목 Entity 추출 | **부분 구현** | `pipeline.py:714`의 종목명·소규모 별칭 매칭. 기업·산업·키워드 추출과 전면 별칭 사전은 아직 없음 |
| 이벤트 taxonomy | **계약만 구현** | `schema/event.py:12`의 16종 taxonomy와 DTO는 있으나 `article_events` 테이블, LLM 호출, 재시도·버전별 재분류는 없음 |
| 기사 본문 직접 수집 금지 | **정책 회귀 발견** | PLAN 4.4절은 CLI 차단을 요구하지만 현재 `main.py:279`가 언론사 페이지 직접 수집 흐름을 다시 실행함 |
| PostgreSQL `news` 스키마 | **미구현** | 현재 영속 테이블은 `db/init.py:77` 이하 DuckDB 스키마이며 루트 PLAN 단계 4의 PostgreSQL 전환 전 상태 |
| 네이버 뉴스 검색 API와 과거 백필 | **미구현** | API client, 검색 쿼리, 호출량 제한, 체크포인트, 백필 실행 이력이 없음 |
| 급등 이벤트 추출과 사례 라이브러리 | **부분 구현** | 공통 `domain/adapters/orchestration/storage` 계층에 KIS/Toss 정규화, 거래대금 100억·1일/3거래일 +10% 판정, `surge_events` 저장 구현. 뉴스 연결과 positive/negative library는 미구현 |
| Streamlit 기본 조회 | **미구현** | 뉴스 수집 상태·기사·Entity를 조회하는 화면이 없음 |

### 12.2 다음 실행 순서

초기 단계의 완료를 우선한다. 아래 작업은 의존 순서이며, 앞 단계의 완료 기준을
충족하기 전에는 임베딩·Vector Store·점수화 구현으로 넘어가지 않는다.

#### P0. 직접 기사 수집 정책 회귀 복구

- `collect-articles` CLI와 정기 실행 경로에서 언론사 페이지 직접 HTTP 수집을 다시 차단한다.
- parser registry와 저장·재처리 코드는 허용된 API 소스의 입력을 처리하는 내부 경로로만 유지한다.
- 회귀 테스트는 CLI가 종료 코드 1과 정책 안내를 반환하고 HTTP 요청을 만들지 않는지 검증한다.

**완료 기준**:
- `python -m modules.news.main collect-articles`가 네트워크 호출 없이 차단된다.
- systemd 서비스에는 언론사 페이지 본문 수집 명령이 없다.
- 정책 차단 테스트가 최신 배치 처리·진행 표시 테스트와 함께 통과한다.

#### P1. PostgreSQL `news` 저장 경계 구축

- 루트 PLAN 단계 4에 맞춰 `rss_sources`, `rss_items`, `articles`, `pipeline_runs`의 PostgreSQL 스키마와 저장 repository를 만든다.
- 수집·분석 로직이 DuckDB 연결을 직접 요구하지 않도록 repository Protocol을 경계로 둔다.
- 기존 DuckDB는 읽기 전용 레거시 보관소로 유지하고 이중 쓰기나 자동 데이터 이관은 하지 않는다.

**완료 기준**:
- 동일 RSS 항목을 반복 저장해도 PostgreSQL에 중복 행이 생기지 않는다.
- 원문 HTML은 어떤 영구 컬럼에도 저장되지 않는다.
- 성공, 재시도 가능 실패, 영구 실패, parser/API 버전이 실행 이력에 남는다.
- PostgreSQL 통합 테스트가 중복·재시도·실패 복구를 검증한다.

#### P2. 네이버 뉴스 검색 API 수집 경로 구현

- 제목, `description`, 원문 링크, 발행시각을 canonical article 입력으로 변환한다.
- 전문이 제공되지 않는 계약에 맞춰 Entity·이벤트 분류 입력을 `제목 + 요약`으로 고정한다.
- API 인증값은 환경 또는 공통 config에서 주입하고 로그·실행 이력에는 남기지 않는다.
- 페이지네이션, 일 25,000건 한도, 오류 재시도, 중단 후 재개 체크포인트를 구현한다.

**완료 기준**:
- mocked API 응답으로 정상 수집, 빈 결과, 429/5xx 재시도, 잘못된 응답을 검증한다.
- 같은 검색 구간을 재실행해도 기사와 실행 체크포인트가 중복되지 않는다.
- API 수집 경로는 언론사 페이지 HTML을 요청하지 않는다.

#### P3. 시점 보존 종목 마스터와 별칭 사전 확장

- KOSPI·KOSDAQ의 상장·폐지 이력과 사명 변경 이력을 보존한다.
- 약칭, 옛 사명, 영문명, 우선주·지주사·스팩 구분 규칙을 버전 가능한 데이터로 관리한다.
- Entity 추출은 평가 시점에 유효했던 종목명·별칭만 사용하도록 point-in-time 조회를 적용한다.

**완료 기준**:
- 상장폐지·사명 변경 종목을 과거 기사 발행일 기준으로 올바른 티커에 매핑한다.
- 긴 이름 우선, 별칭 충돌, 우선주·보통주 구분의 회귀 테스트가 있다.
- `other`가 아닌 모든 종목 Entity 결과에 매핑 근거와 사전 버전이 남는다.

#### P4. 급등 이벤트 추출과 네이버 백필 실행기

- **완료**: 공통 시장 계층이 KIS/Toss 일봉에서 `거래대금 100억 이상 AND (1일 +10% OR 최근 3거래일 내 +10%)`인 `(종목, 급등일)`을 추출해 `surge_events`에 멱등 저장한다. `news`는 이 데이터셋을 소비만 한다.
- **남음**: 전체 종목·기간의 시세를 페이지네이션해 추출기에 공급하는 배치 실행기를 연결한다.
- 이벤트별로 `종목명 + 별칭 × 급등일 이전 7일` 검색 작업을 생성하고 호출 한도 안에서 분할 실행한다.
- 작업 상태, 마지막 페이지, 재시도 횟수를 저장해 며칠에 걸친 2~3년 백필을 재개 가능하게 한다.

**완료 기준**:
- 거래일 달력 기준 익일·3거래일 수익률이 미래 데이터 누수 없이 계산된다.
- 동일 이벤트·검색 구간을 다시 실행해도 작업과 기사 레코드가 중복되지 않는다.
- 중단된 백필이 마지막 성공 체크포인트부터 재개된다.

#### P5. 초기 운영 조회 화면

- Streamlit에서 수집 실행 상태, 소스별 성공·실패, 최신 기사, Entity 매핑, 백필 진행률을 조회한다.
- 화면은 repository 조회만 사용하고 수집·분류 비즈니스 로직을 포함하지 않는다.

**초기 단계 종료 조건**:
- PostgreSQL 기반 실시간 RSS와 네이버 API 수집이 멱등하게 동작한다.
- 시점 보존 종목 마스터로 급등 이벤트별 2~3년 백필을 시작·중단·재개할 수 있다.
- 운영 화면에서 수집 실패, 호출 한도, 백필 진행률과 Entity 결과를 확인할 수 있다.

### 12.3 초기 단계 이후 대기 항목

다음 항목은 P0~P5가 완료되고 백필 데이터 품질 표본 검증이 끝난 뒤 착수한다.

1. `article_events` 저장과 LLM 이벤트 분류 실행기
2. 임베딩 모델 비교와 Vector Store 선정
3. 급등·비급등 사례 라이브러리와 Contrastive Similarity
4. Market Context features, 학습 기반 점수화, 백테스트
5. RAG 설명과 Dashboard 고도화

---

## 13. 주요 리스크 요약

| 리스크 | 대응 |
|---|---|
| Look-ahead bias | Point-in-time 필터를 검색 레이어에서 강제. Market feature는 전일 종가 기준으로만 계산 |
| 흔한 호재 기사의 고득점 (Precision 붕괴) | Negative library + Contrastive 점수 |
| 뉴스 단독 신호의 한계 | Market Context features 결합 — 거래대금·변동성·테마 확산·시장 국면을 학습 모델에 함께 입력 (8.2절) |
| Cold Start (라이브러리 빈약) | 과거 2~3년 뉴스 백필을 초기 단계에 수행 |
| 라이브러리 노이즈 | LLM 이벤트 분류로 market_commentary·simple_mention 유형을 검색 대상에서 제외 (7.3절) |
| LLM 분류 오류 | 샘플 100~200건 사람 검증, 혼동 행렬 분석, few-shot 보강 루프, enum 검증, prompt_version·taxonomy_version 추적 |
| 백테스트 과대평가 | 익일 시가 진입, 체결 가능성, 비용, 베이스라인 비교 |
| 생존 편향 | 상장폐지 종목 포함한 시세 데이터로 백테스트 (8.2.4절) |
| 전재 기사로 인한 확산도 부풀림 | 콘텐츠 기반 중복 제거 후 클러스터 단위 카운트 |
| 작전성 보도자료 | Source Trust 팩터 |
| RAG 환각 | 근거 기사 인용 강제 |
| 저작권 | 원문 HTML 비영구화, cleaned_text만 영구 보관 |

---

## 14. 외부 계획 문서

- [전체 프로젝트 로드맵](../../PLAN.md)
- [KIS 실시간 수집 계획](../brokers/kis/PLAN.md)
- [Toss 장 운영 정보 계획](../brokers/toss/PLAN.md)
- [저장·백업 계획](../storage/PLAN.md)
- [이벤트 전송·워커·관측성 계획](../orchestration/PLAN.md)
