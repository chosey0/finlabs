# FinLabs News Intelligence — News Trigger Layer

> 뉴스 제목·요약을 시장 관점의 이벤트 신호와 관련 종목 후보로 변환하는 계층

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 설계 상태 | Target contract — taxonomy DTO·Entity 추출·네이버 client만 현재 구현 |
| 입력 | 뉴스 제목, 요약, 링크, `published_at`, `first_seen_at` |
| 출력 | 이벤트 태그, Trigger 신호, 종목 후보와 관계 근거 |
| 처리 단위 | 뉴스 1건 |
| 현재 구현 | `ArticleEvent` taxonomy v1 DTO, 저장 기사 대상 종목 Entity 매칭, 네이버 검색 client |
| 미구현 | 제목+요약 분류 실행기, certainty·immediacy·polarity 출력, novelty cluster, 후보 확장, `trigger_probability` |

## 1. 목적과 책임

News Trigger Layer는 뉴스의 긍정·부정을 단순 분류하지 않는다. 다음 질문에 답하는 구조화 계층이다.

1. 시장 가격에 영향을 줄 수 있는 **새 이벤트**인가?
2. 이벤트의 방향, 확실성, 즉시성, 영향 범위는 무엇인가?
3. 직접 또는 간접적으로 관련된 종목은 무엇이며 연결 근거는 무엇인가?
4. 후속 Market Reaction Layer가 사용할 수 있는 버전된 특징을 제공할 수 있는가?

시장 반응을 관측한 뒤 만드는 라벨은 이 계층의 실시간 출력과 분리한다. 실시간 `trigger_probability`는 뉴스 내용과 `t0` 이전 정보로만 생성하고, `t0` 이후 가격·거래대금은 학습 라벨에만 사용한다.

## 2. 입출력 계약

### 2.1 입력

```json
{
  "news_id": "N20260619_001",
  "title": "반도체 장비 공급계약 체결",
  "description": "회사는 신규 고객과 공급계약을 체결했다고 밝혔다.",
  "published_at": "2026-06-19T10:03:00+09:00",
  "first_seen_at": "2026-06-19T10:05:00+09:00",
  "canonical_url": "https://example.com/article/1"
}
```

네이버 뉴스 검색 API는 기사 전문을 제공하지 않으므로 MVP의 텍스트 입력은 `title + description`으로 고정한다. 언론사 원문 HTML은 요청하거나 저장하지 않는다.

### 2.2 출력

```json
{
  "news_id": "N20260619_001",
  "event_type": "contract_supply",
  "polarity": "positive",
  "certainty": "C3",
  "immediacy": "I3",
  "scope": "single_stock",
  "novelty_score": 0.91,
  "trigger_probability": 0.87,
  "taxonomy_version": "v1",
  "model_version": "trigger-lgbm-v1",
  "candidates": [
    {
      "market": "KOSDAQ",
      "ticker": "042700",
      "relation_type": "direct_mention",
      "candidate_score": 0.94,
      "relation_reason": "제목에서 회사명 직접 언급"
    }
  ]
}
```

`trigger_probability`는 운영 시점의 예측값이며, 사후 시장 반응으로 계산하는 `reaction_class`와 혼용하지 않는다.

## 3. Event Taxonomy

현재 코드의 `modules/news/schema/event.py`에 정의된 닫힌 taxonomy v1을 기준으로 한다. 자유 문자열을 허용하지 않으며 변경 시 `taxonomy_version`을 올리고 영향 구간을 재분류한다.

| Event type | 정의 | 대표 사례 |
|---|---|---|
| `contract_supply` | 공급·납품 계약 체결 또는 확대 | 장기 공급계약, 고객사 납품 |
| `order_win` | 건설·방산·플랜트 등의 수주 | 대형 프로젝트 수주 |
| `regulatory_approval` | 국내외 인허가·승인 | FDA·식약처 승인 |
| `clinical_result` | 임상시험 결과 | 임상 성공·중단 |
| `earnings` | 실적 발표와 전망 | 어닝 서프라이즈, 가이던스 변경 |
| `product_launch` | 신제품·신서비스 출시 | 상용 출시, 양산 개시 |
| `tech_patent` | 기술 개발·특허 | 핵심 특허 취득 |
| `partnership` | 제휴·협력·MOU | 공동개발, 전략적 협력 |
| `ma_investment` | M&A·지분 투자·투자 유치 | 인수, 지분 취득 |
| `capital_change` | 자본 구조 변화 | 유상증자, 감자, CB 발행 |
| `policy_theme` | 정부 정책과 테마 편입 | 지원 정책, 규제 변화 |
| `litigation_risk` | 소송·제재·운영 위험 | 회계 이슈, 생산 중단 |
| `management` | 경영진·지배구조 변화 | 대표 교체, 최대주주 변경 |
| `market_commentary` | 시황·업종 일반 기사 | 장 마감 요약 |
| `simple_mention` | 타 기업 중심 기사 속 단순 언급 | 목록형 관련주 언급 |
| `other` | 위 분류로 설명되지 않는 사건 | 신규 유형 검토 대상 |

`market_commentary`와 `simple_mention`은 기본적으로 Trigger 후보와 유사 사례 검색에서 제외하되, 분류 성능 평가를 위한 negative로 보존한다.

## 4. 보조 태그 체계

### 4.1 Polarity

| 값 | 의미 |
|---|---|
| `positive` | 해당 후보 종목에 긍정적 영향이 예상됨 |
| `negative` | 해당 후보 종목에 부정적 영향이 예상됨 |
| `neutral` | 방향을 확정하기 어려움 |

Polarity는 기사 문장의 감정이 아니라 **후보 종목에 대한 예상 영향 방향**이다. 동일 뉴스라도 경쟁사에는 반대 방향일 수 있으므로 중기 단계에서는 `(news_id, ticker)` 단위 polarity를 허용한다.

### 4.2 Certainty

| 값 | 의미 | 예시 |
|---|---|---|
| `C3` | 발생 사실 확정 | 계약 체결, 승인 완료 |
| `C2` | 공식 계획·발표 | 이사회 결의, 공식 가이던스 |
| `C1` | 검토·협의 중 | 인수 검토, 협상 진행 |
| `C0` | 미확인·루머 | 익명 관계자 보도 |

### 4.3 Immediacy

| 값 | 의미 | 기대 반응 구간 |
|---|---|---|
| `I3` | 즉시형 | 수분~30분 |
| `I2` | 당일형 | 정규장 내 |
| `I1` | 지연형 | 수일 |
| `I0` | 비단기형 | 중장기 또는 불명 |

30분 모델은 주로 `I2`와 `I3`를 대상으로 한다. 이 값은 학습 전에 확정된 규칙 또는 모델 출력이어야 하며 실제 미래 반응으로 다시 쓰지 않는다.

### 4.4 Scope와 Novelty

- `scope`: `single_stock`, `sector`, `theme`, `market`
- `novelty_score`: 동일 사건 클러스터에서 처음 관측된 정보일 가능성, 0~1
- `is_posthoc_article`: 이미 발생한 가격 움직임을 사후 설명하는 기사 여부

Novelty는 URL 중복만으로 판정하지 않는다. 정규화 제목, 핵심 entity, event type, 시간 근접도와 추후 임베딩 유사도를 조합한다.

## 5. Candidate Generation

### 5.1 목표와 KPI

목표는 뉴스별로 작은 후보 집합을 만들되 실제 반응 종목을 놓치지 않는 것이다. 1차 KPI는 `Candidate Recall@K`, 2차 KPI는 뉴스당 평균 후보 수와 후보 생성 지연이다.

### 5.2 생성 단계

1. **Entity extraction**: 기업, 종목, 브랜드, 제품, 산업, 테마, 기관 추출
2. **Point-in-time ticker mapping**: 기사 시점에 유효한 회사명·별칭을 종목 코드에 연결
3. **Direct candidates**: 제목·요약에 직접 언급된 종목 생성
4. **MVP expansion**: 버전된 테마·섹터 매핑으로 후보 확장
5. **Eligibility filter**: 거래정지, 상장폐지, 최소 유동성 미달 종목 제외
6. **Deduplication and ranking**: `(news_id, market, ticker)`별 하나의 후보와 근거 목록 유지

### 5.3 관계 유형

| 관계 | MVP | 설명 |
|---|:---:|---|
| `direct_mention` | 포함 | 회사·종목이 직접 언급됨 |
| `theme_related` | 포함 | 버전된 테마 사전에 연결됨 |
| `sector_peer` | 포함 | 동일 섹터의 유동성 조건 충족 종목 |
| `supplier` | 제외 | 공급망 그래프 필요 |
| `customer` | 제외 | 고객사 관계 그래프 필요 |
| `competitor` | 제외 | 방향성과 관계 유효기간 관리 필요 |
| `policy_beneficiary` | 후속 | 정책-산업-기업 매핑 필요 |

### 5.4 Candidate score

MVP 규칙 점수는 다음 요소를 0~1로 정규화해 계산한다.

```text
candidate_score =
    w_direct × directness
  + w_relation × relation_strength
  + w_title × title_mention
  + w_theme × theme_match_score
  + w_sector × sector_match_score
```

가중치는 `candidate_version`과 함께 보존한다. 시장의 미래 반응을 candidate score에 직접 넣지 않는다.

## 6. Trigger supervision용 사후 라벨

Trigger 신호의 유효성을 학습·평가하기 위한 supervision은 사후 시장 반응으로 만들 수 있지만, 운영 `TriggerSignal`과 물리적으로 분리해 `reaction_labels`에 저장한다. 이는 실시간 Trigger 출력 필드가 아니다.

| 필드 | 정의 |
|---|---|
| `is_trigger` | 사전 정의한 최소 초과수익·거래대금 반응 충족 여부 |
| `trigger_strength` | `strong`, `medium`, `weak`, `none` |
| `reaction_direction` | `positive`, `negative`, `neutral` |

초기 가설 기준은 다음과 같다.

- `strong`: 30분 최대 초과수익률 ≥ 3% 그리고 30분 거래대금 Z-score ≥ 2
- `medium`: 30분 최대 초과수익률 ≥ 1.5%
- `weak`: 30분 최대 초과수익률 ≥ 0.5%
- `none`: 그 외

임계값은 확정 규칙이 아니다. 종목·시장별 분포와 거래비용을 분석한 뒤 `label_version`으로 관리한다. 음의 반응 모델이 필요하면 상승과 하락 라벨을 분리해 대칭 기준을 검토한다.

## 7. 노이즈와 인과 오염 방지

| 검사 | 처리 원칙 |
|---|---|
| Pre-move | `t0` 직전 수익률이 임계값을 넘으면 별도 flag 또는 학습 제외 |
| Post-hoc 기사 | “급등 이유”, “상한가 배경” 등 사후 설명 문구와 가격 선행 여부로 판정 |
| Market neutralization | 종목 수익률에서 시장·섹터 benchmark 수익률 제거 |
| Low liquidity | 최근 평균 거래대금, 스프레드, 체결 수 기준 필터 |
| Duplicate event | 동일 사건 클러스터는 대표 기사만 학습하거나 가중치 축소 |
| Delayed collection | `published_at`이 아니라 `first_seen_at`을 `t0`로 사용 |
| After-hours news | 다음 정규장 cohort로 분리하고 장중 기사와 혼합하지 않음 |

## 8. 품질 평가

- 이벤트 분류: macro/micro F1, class별 precision·recall, confusion matrix
- 보조 태그: certainty/immediacy/scope별 macro F1
- 후보 생성: Recall@5/10/20, 평균 후보 수, 직접·확장 후보별 recall
- 확률 출력: PR-AUC, Brier score, calibration curve
- 데이터 품질: 미매핑 entity 비율, taxonomy `other` 비율, 중복 cluster 크기

평가 데이터는 최소 2인의 독립 라벨과 불일치 조정 기록을 포함해야 한다. 특정 모델이 만든 라벨만으로 같은 모델을 평가하지 않는다.

## 9. MVP 구현 범위

### 포함

- taxonomy v1과 보조 태그 스키마
- 제목+요약 기반 이벤트 분류
- 직접 언급, 테마, 섹터 후보
- 규칙 기반 candidate score
- pre-move, post-hoc, 중복 flag
- 모든 출력의 모델·프롬프트·taxonomy·후보 생성 버전

### 제외

- 공급망·고객사·경쟁사 지식 그래프
- 해외-국내 자동 전이
- 사건별 자동 인과 설명
- 기사 전문 기반 분류

## 10. 완료 기준

1. JSON schema 또는 DTO가 위 입출력 계약을 강제한다.
2. taxonomy 외 값과 잘못된 점수 범위를 거부한다.
3. 후보마다 관계 유형, 근거, 매핑 버전을 추적한다.
4. `first_seen_at` 이후 정보가 Trigger 특징에 포함되지 않는다.
5. 이벤트 분류와 후보 생성의 baseline 대비 성능을 보고한다.
6. 출력이 [Feature Dictionary](./FeatureDictionary.md), [Market Reaction Layer](./MarketReactionLayer.md), [Training Data Model](./TrainDataTable.md)의 필드 계약에 일치한다.
