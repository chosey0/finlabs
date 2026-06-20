# FinLabs News Intelligence Feature Dictionary

> 뉴스별 후보 종목의 30분 내 시장 반응을 예측하기 위한 feature·label 정의와 point-in-time 생성 계약

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 설계 상태 | Target contract — 현재 feature·label 생성기는 미구현 |
| 연계 문서 | [News Trigger Layer](./NewsTriggerLayer.md), [Market Reaction Layer](./MarketReactionLayer.md), [Training Data Model](./TrainDataTable.md), [Backtest](./Backtest.md), [Python Interface](./Interface.md) |
| 학습 단위 | `(news_id, market, ticker, t0)` |
| 기준 시각 | `t0 = first_seen_at` |
| 예측 대상 | `t0` 이후 30분 내 `strong_reaction` 여부 |
| MVP target | `is_strong_reaction` |
| 단위 원칙 | 수익률은 소수, 금액은 KRW, Z-score는 무차원 |

## 1. 목적

이 문서는 모델에 입력되는 각 feature와 label의 의미, 자료형, source, 관측 window, 산식, 결측 처리와 버전 책임을 고정한다. 같은 이름의 feature가 학습·백테스트·운영에서 다르게 계산되는 문제를 방지하는 것이 목적이다.

Feature 구현은 이 문서만으로 다음 질문에 답할 수 있어야 한다.

- 어떤 시점까지의 원천 데이터를 사용했는가?
- 산식과 단위는 무엇인가?
- 결측 또는 데이터 부족 시 어떻게 처리하는가?
- 학습 target과 운영 feature가 물리적으로 분리됐는가?
- 계산 규칙을 어떤 version으로 재현하는가?

## 2. 공통 생성 계약

### 2.1 시간 기준

- `t0`는 뉴스 제공자의 발행시각이 아니라 FinLabs가 처음 사용할 수 있었던 `first_seen_at`이다.
- `feature_cutoff_at`은 실제 feature 원천의 최대 시각이며 항상 `feature_cutoff_at <= t0`여야 한다.
- 분봉은 `t0` 이전에 완결된 마지막 bar까지만 사용한다. 진행 중 bar의 최종 OHLCV를 소급 사용하지 않는다.
- 재수집은 `first_seen_at`을 변경하지 않는다.
- 장외·휴장일 뉴스는 `session_type`으로 분리하고 다음 정규장 label 규칙을 적용한다.

### 2.2 Point-in-time 기준

- 이동평균, Z-score, scaler와 category encoder는 해당 sample 시점 이후 데이터를 사용하지 않는다.
- 종목명, 별칭, 섹터, 테마와 시가총액은 `t0`에 유효한 snapshot을 사용한다.
- corporate action이 반영된 가격 계열을 사용하고 조정 방식은 `feature_version`에 기록한다.
- label window의 데이터는 어떤 feature에도 포함하지 않는다.

### 2.3 값과 결측 표현

- 수익률: `0.01 = 1%`
- 확률·유사도: `[0, 1]`
- Boolean: `true`/`false`; 원천 부족은 `false`로 대체하지 않고 missing flag 사용
- Categorical 결측: 학습 artifact에서 `__MISSING__`으로 encoding하되 원천 domain enum에는 추가하지 않음
- 수치 결측: `NULL` 유지 + `missing_flags`; train split 통계로만 imputation
- 극단값 clipping: train split에서만 경계 산출, 변환 artifact와 version 보존

### 2.4 버전

| Version | 책임 |
|---|---|
| `taxonomy_version` | event type 목록과 의미 |
| `trigger_model_version` | Trigger rule/model과 calibration artifact |
| `extractor_version` | entity 정규화·추출 규칙 |
| `cluster_version` | duplicate/event cluster 산식 |
| `mapping_version` | entity·theme·sector 시점 매핑 snapshot |
| `candidate_version` | 후보 생성 규칙과 candidate score |
| `feature_version` | lookback, baseline, 결측, 조정주가, 산식 |
| `label_version` | horizon, benchmark, 임계값, scaler |
| `dataset_version` | source snapshot, split, 포함·제외 규칙 |

## 3. Feature 그룹

| 그룹 | 목적 |
|---|---|
| A. News Trigger | 뉴스 이벤트 자체의 사전 신호 |
| B. Candidate Relation | 뉴스와 후보 종목의 관계 |
| C. Market State | `t0` 직전 종목 가격·거래 상태 |
| D. Market Context | 시장·섹터의 동시 국면 |
| E. Time | 거래 세션과 장중 위치 |
| F. Liquidity·Risk | 거래 가능성과 오염 위험 |
| G. Labels | `t0` 이후 실제 반응; 모델 입력 금지 |

## 4. A. News Trigger Features

### 4.1 `trigger_probability`

| 속성 | 정의 |
|---|---|
| 타입 | `float` |
| 범위 | 0~1 |
| Source | `news_events` |
| MVP | 포함 |

뉴스가 유의미한 시장 반응을 만들 가능성에 대한 사전 확률이다. 사후 가격 반응으로 직접 계산한 점수가 아니며 Trigger 모델의 calibration을 거친 출력이어야 한다.

기존 초안의 `trigger_score`는 이 필드로 통일한다. 확률로 해석할 수 없는 규칙 점수라면 별도 `trigger_rule_score`로 저장하고 혼용하지 않는다.

### 4.2 `event_type`

| 속성 | 정의 |
|---|---|
| 타입 | `categorical` |
| Source | `news_events` |
| Version | `taxonomy_version` |
| MVP | 포함 |

현재 `modules/news/schema/event.py` taxonomy v1 값을 사용한다.

```text
contract_supply, order_win, regulatory_approval, clinical_result,
earnings, product_launch, tech_patent, partnership,
ma_investment, capital_change, policy_theme, litigation_risk,
management, market_commentary, simple_mention, other
```

기존 초안의 `event_type_lvl1` 8종은 현재 코드 계약과 다르므로 사용하지 않는다. 계층형 taxonomy가 필요하면 v2에서 `event_type_group`을 별도 추가한다.

### 4.3 `polarity`

| 속성 | 정의 |
|---|---|
| 타입 | `categorical` |
| 값 | `positive`, `negative`, `neutral` |
| Source | `news_events` |
| MVP | 포함 |

기사 문장의 감정이 아니라 후보 종목에 대한 예상 영향 방향이다. 미분류는 domain 값 `unknown`을 추가하지 않고 결측으로 관리한다.

### 4.4 `certainty`

| 속성 | 정의 |
|---|---|
| 타입 | `ordinal categorical` |
| 값 | `C0`, `C1`, `C2`, `C3` |
| Source | `news_events` |
| MVP | 포함 |

- `C3`: 발생 사실 확정
- `C2`: 공식 계획·발표
- `C1`: 검토·협의
- `C0`: 미확인·추정

원천 값은 문자열로 보존한다. 정수 encoding이 필요하면 `certainty_level = 0..3`을 dataset artifact에서 생성하고 encoder version을 기록한다.

### 4.5 `immediacy`

| 속성 | 정의 |
|---|---|
| 타입 | `ordinal categorical` |
| 값 | `I0`, `I1`, `I2`, `I3` |
| Source | `news_events` |
| MVP | 포함 |

- `I3`: 수분~30분 즉시형
- `I2`: 당일형
- `I1`: 수일 지연형
- `I0`: 비단기형

정수 encoding은 `immediacy_level = 0..3`으로 별도 생성한다.

### 4.6 `scope`

| 속성 | 정의 |
|---|---|
| 타입 | `categorical` |
| 값 | `single_stock`, `sector`, `theme`, `market` |
| Source | `news_events` |
| MVP | 포함 |

### 4.7 `novelty_score`

| 속성 | 정의 |
|---|---|
| 타입 | `float` |
| 범위 | 0~1 |
| Source | `news_clusters` |
| MVP | 후속 |

동일 event cluster 내에서 새로운 정보를 포함할 가능성이다. `1`은 신규 사건에 가깝고 `0`은 중복·재탕에 가깝다. MVP에서 안정적인 cluster가 없으면 feature를 임의의 기본값으로 채우지 않고 제외한다.

## 5. B. Candidate Relation Features

### 5.1 `candidate_score`

| 속성 | 정의 |
|---|---|
| 타입 | `float` |
| 범위 | 0~1 |
| Source | `news_candidates` |
| Version | `candidate_version` |
| MVP | 포함 |

뉴스와 후보 종목의 **관계 강도만** 나타낸다.

```text
candidate_score =
    w_direct × directness
  + w_title × title_mention
  + w_relation × relation_strength
  + w_theme × theme_match_score
  + w_sector × sector_match_score
```

각 구성값과 가중치는 0~1 범위이고 가중치 합은 1이다. 유동성과 시장 반응은 별도 feature이므로 candidate score에 넣지 않는다.

### 5.2 `relation_type`

| 속성 | 정의 |
|---|---|
| 타입 | `categorical` |
| Source | `news_candidates` |
| MVP 값 | `direct_mention`, `theme_related`, `sector_peer` |
| 후속 값 | `supplier`, `customer`, `competitor`, `policy_beneficiary` |

미분류 후보는 생성하지 않는 것을 원칙으로 한다. 진단 목적으로 보존해야 하면 결측과 exclusion reason을 사용한다.

### 5.3 직접 언급 특징

| Feature | 타입 | 정의 | MVP |
|---|---|---|:---:|
| `direct_mention` | bool | 제목 또는 요약에서 기업·종목이 직접 언급됨 | 포함 |
| `title_mention` | bool | 제목에서 직접 언급됨 | 포함 |
| `entity_mention_count` | int | 제목+요약 내 해당 entity 언급 횟수 | 후속 |

네이버 API는 기사 전문을 제공하지 않으므로 “본문 등장”으로 정의하지 않는다. 텍스트 정규화 후 exact span을 기준으로 세고 중복 alias가 같은 위치를 이중 계상하지 않는다.

### 5.4 관계 일치도

| Feature | 타입 | 범위 | Source | MVP |
|---|---|---:|---|:---:|
| `theme_match_score` | float | 0~1 | 시점 유효 `theme_ticker_map` | 포함 |
| `sector_match_score` | float | 0~1 | 시점 유효 종목·섹터 매핑 | 포함 |
| `relation_strength` | float | 0~1 | 관계 mapping | 후속 |

현재 시점의 테마·섹터를 과거 기사에 소급 적용하지 않는다.

## 6. C. Market State Features

### 6.1 가격 수익률

| Feature | Window | 산식 | MVP |
|---|---|---|:---:|
| `return_1m` | 마지막 1분 | `P(cutoff) / P(cutoff-1m) - 1` | 포함 |
| `return_5m` | 마지막 5분 | `P(cutoff) / P(cutoff-5m) - 1` | 포함 |
| `return_15m` | 마지막 15분 | `P(cutoff) / P(cutoff-15m) - 1` | 포함 |
| `pre_return_5m` | 뉴스 직전 5분 | `return_5m`과 동일 원천, risk rule용 별칭 | 저장 |

`P(cutoff)`은 `t0` 이전 마지막 완결 1분봉의 조정 종가다. 거래 중단이나 bar 누락으로 정확한 window를 만들 수 없으면 NULL과 missing flag를 남긴다.

### 6.2 거래 활성도

| Feature | 산식 | MVP |
|---|---|:---:|
| `volume_z_5m` | `(최근 5분 거래량 - baseline 평균) / baseline 표준편차` | 포함 |
| `turnover_z_5m` | `(최근 5분 거래대금 - baseline 평균) / baseline 표준편차` | 포함 |
| `turnover_ratio_5m` | `최근 5분 거래대금 / baseline 평균` | 포함 |

Baseline 기본안:

- `t0` 이전 완료된 최근 20거래일
- 동일 종목·동일 세션 시간 bucket의 5분 window
- 현재 거래일의 `t0` 이후 데이터 제외
- 유효 관측치 최소 10개
- 표준편차가 0이면 Z-score는 NULL, ratio 분모가 0이면 NULL

실제 lookback·최소 관측치·시간 bucket은 탐색 분석 후 `feature_version`에 고정한다.

### 6.3 변동성

| Feature | 산식 | MVP |
|---|---|:---:|
| `volatility_5m` | 최근 5개 완결 1분 로그수익률의 population std | 포함 |
| `volatility_15m` | 최근 15개 완결 1분 로그수익률의 population std | 후속 |

bar 수가 부족하면 짧은 window로 대체하지 않고 NULL을 반환한다.

## 7. D. Market Context Features

| Feature | 정의 | Source | MVP |
|---|---|---|:---:|
| `market_return_5m` | 해당 시장 benchmark의 직전 5분 수익률 | 지수 1분봉 | 포함 |
| `market_return_15m` | 해당 시장 benchmark의 직전 15분 수익률 | 지수 1분봉 | 후속 |
| `sector_return_5m` | point-in-time 섹터 benchmark의 직전 5분 수익률 | 섹터 지수·basket | 포함 |
| `sector_turnover_z_5m` | 섹터 구성 종목 거래대금의 동시간대 Z-score | 섹터 basket | 포함 |
| `theme_momentum_score` | 테마 구성 종목의 동조 상승·거래 활성도 | 테마 basket | 후속 |

시장 benchmark는 KOSPI/KOSDAQ 등 `market`에 따라 결정한다. 섹터 index가 없으면 시점 유효 구성 종목 basket을 사용하고 구성·가중 방식은 version으로 보존한다. 안정적인 source가 없으면 0으로 대체하지 않는다.

## 8. E. Time Features

### 8.1 `minutes_from_open`, `minutes_to_close`

| Feature | 타입 | 정의 | MVP |
|---|---|---|:---:|
| `minutes_from_open` | int | 해당 거래 세션 시작 후 경과 분 | 포함 |
| `minutes_to_close` | int | 해당 거래 세션 종료까지 남은 분 | 후속 |

거래소 calendar와 세션 정보를 기준으로 계산한다. 날짜·시간을 고정 문자열로 판정하지 않는다.

### 8.2 `session_type`, `session_bucket`

`session_type`은 원천 세션 계약이다.

```text
pre_market, regular, after_market, closed_day
```

`session_bucket`은 정규장 내부 모델 feature다.

```text
early, mid, late
```

bucket 경계는 거래소 calendar 기반 설정이며 `feature_version`에 포함한다. 장외 sample에 임의의 `minutes_from_open=0`을 넣지 않는다.

## 9. F. Liquidity·Risk Features

### 9.1 유동성

| Feature | 타입 | 정의 | MVP |
|---|---|---|:---:|
| `avg_turnover_20d` | numeric | `t0` 이전 완료된 20거래일 평균 거래대금, KRW | 포함 |
| `market_cap` | numeric | `t0` 이전 최신 point-in-time 시가총액, KRW | 포함 |
| `liquidity_pass` | bool | 버전된 최소 유동성 기준 충족 | 포함 |
| `low_liquidity_flag` | bool | `NOT liquidity_pass`; 저장 편의용 | 제외 |

`avg_turnover_20d`는 현재 종목 마스터의 mutable 값이 아니라 as-of 계산값이어야 한다. 초기 “10억 원 이상” 기준은 가설이며 학습 표본의 분위수와 거래비용을 분석한 뒤 결정한다.

### 9.2 Pre-move

| Feature | 타입 | 정의 | MVP |
|---|---|---|:---:|
| `pre_move_flag` | bool | 뉴스 방향과 같은 방향으로 이미 2% 이상 움직였는지 | 포함 |

초기 규칙:

```text
positive → pre_return_5m >=  0.02
negative → pre_return_5m <= -0.02
neutral  → abs(pre_return_5m) >= 0.02
```

임계값과 제외·penalty 정책은 별도 설정으로 version 관리한다. 모델 입력과 학습 제외 정책을 동시에 적용해 효과를 이중 계산하지 않는다.

### 9.3 가격 제한 근접

| Feature | 타입 | 정의 | MVP |
|---|---|---|:---:|
| `price_limit_near_flag` | bool | 해당 시장의 당일 가격 제한에 근접 | 후속 |

시장별 가격 제한 규칙과 기준가격을 point-in-time으로 계산해야 하므로 MVP에서는 제외한다.

## 10. G. Label Columns

Label은 feature가 아니며 모델 입력과 운영 요청 payload에 포함하면 안 된다.

### 10.1 `future_max_return_30m`

```text
max(P(t) / P(label_window_start) - 1),
t ∈ (label_window_start, label_window_end]
```

`label_window_start`와 `label_window_end`를 명시적으로 저장한다. 분봉 경계·장 마감·장외 뉴스 규칙은 `label_version`으로 고정한다.

### 10.2 `future_max_excess_return_30m`

각 시점의 종목과 benchmark 수익률 차이 중 최대값이다.

```text
max(
  stock_return(label_window_start, t)
  - benchmark_return(label_window_start, t)
),
t ∈ (label_window_start, label_window_end]
```

종목 최대수익률에서 benchmark 최대수익률을 별도로 빼면 서로 다른 시점이 결합될 수 있으므로 사용하지 않는다.

### 10.3 `future_turnover_z_30m`

`label_window`의 누적 거래대금을 과거 동일 종목·동일 시간대 30분 분포로 표준화한다. baseline은 sample 시점 이전 데이터만 사용한다.

### 10.4 `reaction_score`

원시 수익률과 Z-score를 바로 합하지 않는다. train split에서 적합한 scaler로 두 값을 변환한 뒤 결합한다.

```text
reaction_score =
    0.7 × scaled_future_max_excess_return_30m
  + 0.3 × scaled_future_turnover_z_30m
```

scaler artifact는 `label_version`과 함께 보존한다.

### 10.5 `reaction_class`, `is_strong_reaction`

| Class | 초기 기준 |
|---|---|
| `strong` | 초과수익률 ≥ 0.03 그리고 거래대금 Z-score ≥ 2.0 |
| `medium` | 초과수익률 ≥ 0.015 |
| `weak` | 초과수익률 ≥ 0.005 |
| `none` | 그 외 |

`is_strong_reaction = reaction_class == "strong"`을 MVP binary target으로 사용한다. 수치는 데이터 분포 검토 전 가설이며 `label_version` 없이 변경하지 않는다.

`label_exclusion_reason`이 있는 sample은 `reaction_class`와 `is_strong_reaction`을 NULL로 유지한다. 이를 `none` 또는 `false`로 채우면 관측 불가 표본이 negative로 오염된다.

## 11. MVP Feature Set

### News Trigger

```text
trigger_probability, event_type, polarity, certainty, immediacy, scope
```

### Candidate Relation

```text
candidate_score, relation_type, direct_mention, title_mention,
theme_match_score, sector_match_score
```

### Market State·Context

```text
return_1m, return_5m, return_15m,
volume_z_5m, turnover_z_5m, turnover_ratio_5m,
volatility_5m, market_return_5m,
sector_return_5m, sector_turnover_z_5m
```

### Time·Risk

```text
avg_turnover_20d, market_cap,
minutes_from_open, session_type, session_bucket,
pre_move_flag, liquidity_pass
```

### Target

```text
is_strong_reaction
```

`novelty_score`, `entity_mention_count`, `volatility_15m`, `market_return_15m`, `theme_momentum_score`, `minutes_to_close`, `price_limit_near_flag`는 source 품질과 표본량을 확인한 뒤 추가한다.

## 12. 모델 입력 금지 필드

다음 필드는 label 또는 미래 결과이므로 입력 feature에 포함하지 않는다.

```text
future_max_return_30m
future_max_excess_return_30m
future_turnover_z_30m
reaction_score
reaction_class
is_strong_reaction
label_window_start
label_window_end
```

`is_posthoc_article`, `duplicate_cluster_id`, `event_cluster_id`, `exclusion_reason`은 기본적으로 필터·split·감사용이다. 모델 입력으로 사용할 경우 운영 시 동일 시점에 생성 가능함을 별도로 입증해야 한다.

## 13. 생성 순서

1. 뉴스 적재와 immutable `first_seen_at` 확정
2. event·entity·candidate 생성
3. `t0` 이전 마지막 완결 bar와 point-in-time mapping 확정
4. 시장·섹터·시간·유동성 feature 생성
5. `feature_cutoff_at <= t0` 검증
6. 완결된 미래 window에서 label 생성
7. duplicate/event cluster 단위 시간 split
8. train split에서 encoder·imputer·scaler 적합
9. `training_pairs` 생성과 누수 검사
10. dataset manifest·checksum·분포 보고서 저장

Split은 categorical encoding보다 먼저 논리적으로 확정한다. 전처리 artifact는 train 행으로만 적합한다.

## 14. Feature Registry 필수 메타데이터

Feature 구현체 또는 registry는 최소 다음 정보를 제공한다.

| 필드 | 설명 |
|---|---|
| `feature_name` | canonical 이름 |
| `dtype` | 논리 자료형 |
| `entity_key` | `(news_id, market, ticker, t0)` |
| `source_tables` | 원천 테이블·dataset |
| `lookback` | 관측 window |
| `availability_rule` | as-of cutoff 규칙 |
| `formula` | 결정적 산식 |
| `unit` | decimal return, KRW, score 등 |
| `missing_policy` | NULL·flag·imputation 정책 |
| `owner` | 생성 모듈 |
| `feature_version` | 변경 추적 version |

## 15. 검증 규칙

| 검사 | 기대 결과 |
|---|---|
| Point-in-time | 모든 원천 최대 시각이 `t0` 이하 |
| Window boundary | 정확한 bar 수가 없으면 NULL, 짧은 window 대체 금지 |
| Z-score | 미래 데이터 제외, 최소 관측치와 0 표준편차 처리 |
| Return unit | 모든 수익률이 소수 단위 |
| Score range | 확률·일치도·관계 점수가 0~1 |
| Category contract | taxonomy와 허용 enum 외 값 거부 |
| Label isolation | label 필드가 feature matrix에 없음 |
| Split isolation | encoder·scaler가 train에만 fit |
| Reproducibility | 동일 source snapshot+version의 checksum 일치 |
| Training-serving parity | 동일 fixture의 offline·online feature 값 일치 |

## 16. 변경 관리

다음 변경은 `feature_version` 증가가 필요하다.

- 산식, lookback, baseline 기간 또는 최소 관측치 변경
- 분봉 cutoff와 장외 세션 처리 변경
- 결측·imputation·clipping 정책 변경
- point-in-time mapping source 변경
- 조정주가 또는 benchmark 변경

Label horizon, class 임계값, benchmark 또는 scaler 변경은 `label_version`을 증가시킨다. 이름만 바꾸는 경우에도 dataset schema가 달라지므로 migration mapping을 남긴다.

## 17. 완료 기준

1. 모든 MVP feature가 registry metadata를 갖는다.
2. offline feature builder와 운영 feature builder의 parity test가 있다.
3. 시간 cutoff, Z-score baseline, 결측, category와 범위 테스트가 있다.
4. label column이 입력 matrix에 포함되지 않는 자동 검사에 통과한다.
5. 동일 dataset manifest에서 feature checksum을 재현한다.
6. Feature 중요도뿐 아니라 결측률, drift와 source 지연을 함께 모니터링한다.

한 줄로 요약하면 MVP 모델은 **뉴스 이벤트 신호 + 종목 관계 + `t0` 이전 가격·거래대금 + 시장·섹터 국면 + 시간·유동성 조건**으로 30분 내 강한 반응 여부를 예측한다.
