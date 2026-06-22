# FinLabs News Intelligence 백테스트 설계서

> 뉴스별 후보 종목 랭킹의 예측 품질과 거래 가능성을 시간 순서 test 구간에서 분리해 검증하는 평가 계약

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 설계 상태 | Target evaluation contract — runner·model 미구현 |
| 연계 문서 | [Market Reaction Layer](./MarketReactionLayer.md), [Feature Dictionary](./FeatureDictionary.md), [Training Data Model](./TrainDataTable.md) |
| 평가 단위 | 뉴스 1건과 해당 뉴스의 후보 종목 목록 |
| 기준 시각 | `t0 = first_seen_at` |
| 기본 horizon | 30 거래분 |
| 기본 Top-K | 1, 3, 5 |
| 핵심 원칙 | 랭킹 품질과 체결 기반 수익성을 별도 시나리오로 평가 |

## 1. 목적과 검증 질문

백테스트는 모델이 생성한 Top-K가 사후 라벨을 잘 맞히는지뿐 아니라, 실제로 관측 가능한 시점과 가격을 사용했을 때 경제적 가치가 남는지를 검증한다.

핵심 질문은 다음과 같다.

1. 모델이 시간 순서 test 구간에서 단순 baseline보다 높은 Hit@K와 NDCG@K를 보이는가?
2. 실행 지연과 거래비용을 반영한 Top-K 수익률이 양수이며 신뢰구간도 안정적인가?
3. 성능이 일부 날짜·이벤트·저유동성 종목에만 집중되지 않는가?
4. 모든 결과를 데이터셋·모델·특징·라벨·백테스트 버전으로 재현할 수 있는가?

백테스트는 투자수익을 보장하는 절차가 아니다. 모델 선택을 위한 오프라인 검증이며 자동 주문과 포트폴리오 운용은 범위 밖이다.

## 2. 평가 단위와 입력

### 2.1 랭킹 단위

모델 입력 행은 `(news_id, market, ticker, t0)`이지만 랭킹 평가는 같은 `news_id`의 후보 목록 전체를 하나의 query group으로 본다.

```text
news_id
├─ candidate A: reaction_probability, label, tradable return
├─ candidate B: reaction_probability, label, tradable return
└─ candidate C: reaction_probability, label, tradable return
```

### 2.2 필수 입력 snapshot

- `dataset_version`으로 고정된 test split과 exclusion 규칙
- 후보 생성 시점의 `candidate_version`
- `feature_version`, `label_version`, `model_version`
- 후보별 원본 모델 점수와 보정 확률
- point-in-time 1분봉, 시장 benchmark, 거래일 캘린더
- 수수료·세금·슬리피지·체결 지연이 포함된 `backtest_config`

평가 시 특징을 다시 계산해 학습 당시 snapshot과 달라지게 만들지 않는다. 재계산이 필요하면 새 dataset 또는 feature version을 발행한다.

## 3. 시간·세션 계약

### 3.1 기준 시각

```text
t0 = first_seen_at
```

`published_at`은 출처 표시와 수집 지연 분석에만 사용한다. 같은 기사의 재수집 시각인 `collected_at`을 `t0`로 사용하면 최초 관측보다 늦은 시점으로 이동하므로 금지한다.

### 3.2 신호와 체결 시각

```text
signal_time = inference_completed_at
eligible_entry_at = max(t0, signal_time) + execution_delay
entry_time = eligible_entry_at 이후 첫 번째 체결 가능한 완결 1분봉의 종료 시각
```

MVP의 `execution_delay` 초기값은 1분이다. 추론 완료 시각을 재현할 수 없는 과거 데이터는 보수적으로 `t0 + 1분`을 사용하고 해당 가정을 config에 기록한다.

### 3.3 보유 구간

기본 보유 기간은 진입 후 30 **거래분**이다. 점심 휴장, 장 마감, 거래정지 구간을 단순한 벽시계 30분으로 채우지 않는다.

- 장중: `exit_time = entry_time` 이후 30번째 체결 가능 분봉
- 장 마감 전 30분을 확보할 수 없음: 기본 제외하고 `insufficient_horizon` 기록
- 장외·휴장일 뉴스: 다음 정규장 cohort로 분리
- 거래정지·bar 누락: 임의 보간 없이 제외 사유 기록

장외 신호의 진입 규칙은 별도 config로 관리하며 장중 결과와 합산하기 전에 cohort별 결과를 먼저 보고한다.

## 4. 평가 시나리오

| 시나리오 | 목적 | 가격·비용 가정 | 주요 지표 |
|---|---|---|---|
| A. Ranking | 후보 순서 품질 | 거래 체결을 가정하지 않음 | Hit@K, Precision@K, NDCG@K, MRR |
| B. Tradable | 기본 거래 가능성 | 다음 체결 가능 1분봉, 기본 비용 | net return, excess return, win rate, drawdown |
| C. Conservative | 체결 낙관 편향 점검 | 불리한 bar 가격과 높은 슬리피지 | B와 동일 |
| D. Sensitivity | 가정 의존성 점검 | 지연·비용·horizon grid | 지표 변화와 손익분기점 |

Scenario A의 `future_max_excess_return_30m`은 라벨·랭킹 평가에만 사용한다. 미래 고가를 실제 청산 가격으로 사용하지 않는다.

## 5. 진입·청산 가격

### 5.1 기본 체결 모델

MVP는 틱·호가 데이터가 없다는 전제에서 1분봉 기반의 단순 체결 모델을 사용한다.

```text
entry_price = entry bar close
exit_price  = exit bar close
gross_return = exit_price / entry_price - 1
```

동일 bar의 최종 가격을 신호 시점에 이미 알았다고 가정하지 않는다. `entry_time`은 신호 이후 완결된 bar만 가리켜야 한다.

### 5.2 보수적 체결 모델

```text
long entry_price = entry bar high
long exit_price  = exit bar close
```

보수적 모델은 실제 체결을 정확히 모사하는 것이 아니라 결과가 유리한 bar 선택에 의존하는지 점검하는 스트레스 시나리오다. 호가 데이터가 확보되면 spread·시장충격 기반 모델로 교체한다.

## 6. 수익률과 benchmark

```text
gross_return = exit_price / entry_price - 1
benchmark_return = benchmark_exit / benchmark_entry - 1
gross_excess_return = gross_return - benchmark_return
net_return = gross_return - round_trip_cost
net_excess_return = gross_excess_return - round_trip_cost
```

- KOSPI 종목은 KOSPI, KOSDAQ 종목은 KOSDAQ을 기본 benchmark로 사용한다.
- 섹터 지수의 시점 품질이 확보되면 `sector_excess_return`을 보조 지표로 추가한다.
- 종목과 benchmark는 같은 entry·exit 시각을 사용한다.
- split·배당 등 corporate action을 반영한 가격 계열을 사용한다.

## 7. 거래비용과 체결 가능성

비용은 숫자 하나로 코드에 고정하지 않고 구성 요소와 유효기간을 보존한다.

| 구성 요소 | 설명 |
|---|---|
| `commission_bps` | 왕복 위탁수수료 |
| `tax_bps` | 매도 시 적용되는 시장·시점별 세금 |
| `slippage_bps` | 진입·청산 방향별 가격 불리분 |
| `impact_bps` | 주문 크기에 따른 시장충격; MVP에서는 0 또는 보수적 상수 |

초기 민감도 분석은 총 왕복 비용 10bp, 20bp, 30bp를 비교한다. 실제 기본값은 평가 실행일의 비용 근거와 함께 `backtest_config`에 고정한다.

체결 가능성 필터는 다음을 포함한다.

- `liquidity_pass = true`
- 거래정지·관리종목·상장폐지 상태가 아님
- 상·하한가 또는 VI로 체결이 비현실적인 경우 제외 또는 별도 cohort
- 진입 bar와 청산 bar가 모두 존재함
- 주문금액이 해당 bar 거래대금의 설정 비율을 넘지 않음

## 8. 표본 포함·제외 규칙

| 조건 | 기본 처리 | 기록 필드 예시 |
|---|---|---|
| 사후 설명 기사 | 제외 | `is_posthoc_article`, `posthoc_reason` |
| 큰 pre-move | 주 결과 제외, 별도 cohort 보고 | `pre_move_flag` |
| duplicate article | cluster 대표 기사만 포함 | `duplicate_cluster_id` |
| 동일 사건 반복 신호 | 첫 실행 가능 신호만 포함 | `event_cluster_id` |
| 30 거래분 부족 | 제외 | `insufficient_horizon` |
| 저유동성 | 제외 또는 유동성 cohort | `liquidity_pass` |
| 시장 데이터 결측 | 제외 | `missing_market_data` |

Pre-move의 초기 가설은 `pre_return_5m >= 2%` 또는 `pre_return_15m >= 4%`다. 확정 임계값은 [Feature Dictionary](./FeatureDictionary.md)의 `feature_version`으로 관리한다.

동일 cluster가 train·valid·test를 가로지르지 않아야 하며, test 내부에서도 반복 신호를 여러 번 독립 성공으로 계산하지 않는다.

## 9. 포트폴리오 집계 규칙

뉴스별 Top-K 평균만으로는 동시 신호와 자본 중복을 설명할 수 없다. 따라서 두 수준을 분리해 보고한다.

1. **Query-level 평가**: 각 뉴스의 Top-K를 동일 가중으로 평가
2. **Chronological portfolio 평가**: 시각 순서대로 신호를 처리하고 자본·동시 포지션 한도를 적용

MVP portfolio 기본 가정은 다음과 같다.

- Top-K 동일 가중
- 종목별·뉴스별 최대 비중 제한
- 동일 종목의 겹치는 신호는 추가 진입하지 않음
- 최대 동시 포지션 수를 config로 제한
- 자본 부족 시 모델 점수 순으로 체결
- 미체결과 제외 사유를 결과에 보존

이 규칙 없이 서로 겹치는 모든 뉴스에 독립 자본을 배정한 결과를 포트폴리오 수익률로 표현하지 않는다.

## 10. 지표

### 10.1 랭킹·후보 품질

- Candidate Recall@10/20
- Hit@1/3/5
- Precision@1/3/5
- NDCG@5/10
- MRR
- 뉴스당 평균 후보 수와 noise ratio

`hit`은 해당 `label_version`의 `is_strong_reaction`과 동일하게 정의한다. 백테스트에서 별도 임계값을 만들지 않는다.

### 10.2 경제적 성과

- Top-1·Top-3·Top-5 평균/중앙값 `net_return`
- 평균 `net_excess_return`
- win rate와 payoff ratio
- 누적 수익률, 최대 낙폭, 변동성, Sharpe-like ratio
- turnover, 거래 수, 미체결률

### 10.3 확률·안정성

- PR-AUC, Brier score, calibration error
- event type·relation type·시장·섹터·유동성·시간대별 성능
- 월별 성능과 최악 월
- bootstrap 신뢰구간
- 비용·지연·horizon 민감도

모든 지표는 표본 수와 함께 보고한다. 후보 행을 독립 표본으로 bootstrap하지 않고 뉴스 또는 event cluster 단위로 재표집한다.

## 11. Baseline과 비교 원칙

최소 baseline은 다음과 같다.

1. 무작위 후보 정렬
2. 직접 언급 우선 정렬
3. `candidate_score` 단독 정렬
4. `turnover_z_5m` 단독 정렬

Rule hybrid를 추가할 수 있지만 서로 다른 단위의 원시 값을 임의 가중합하지 않는다. 정규화 방식과 가중치를 valid split에서만 정하고 test에서는 고정한다.

모델과 baseline은 동일한 후보 집합, 포함·제외 규칙, 비용, 시각과 test 기간을 사용해야 한다.

## 12. 백테스트 실행 절차

1. `dataset_version`과 test member를 불변 snapshot으로 로드한다.
2. 학습이 끝난 `model_version`과 calibration artifact를 로드한다.
3. 저장된 feature row에서 후보별 점수를 생성한다.
4. 같은 뉴스 내에서 결정적 tie-breaker로 정렬한다.
5. Scenario A의 랭킹 지표를 계산한다.
6. 체결 가능성, 중복, pre-move 규칙을 적용한다.
7. entry·exit bar와 비용을 계산한다.
8. query-level 및 chronological portfolio 결과를 각각 집계한다.
9. 동일 조건에서 baseline을 실행한다.
10. slice·민감도·신뢰구간을 계산하고 manifest를 저장한다.

점수 동률은 `reaction_probability DESC, candidate_score DESC, market ASC, ticker ASC` 순으로 결정한다.

## 13. 결과 데이터 계약

### 13.1 `backtest_runs`

| 필드 | 설명 |
|---|---|
| `run_id` | 실행 식별자 |
| `dataset_version` | test snapshot |
| `model_version` | 모델 artifact |
| `feature_version`, `label_version` | 입력·정답 계약 |
| `backtest_version` | 평가 코드·규칙 버전 |
| `config_json` | 지연·비용·K·필터·자본 가정 |
| `source_revision` | 코드 revision |
| `started_at`, `completed_at`, `status` | 실행 감사 정보 |

### 13.2 `backtest_predictions`

후보별 원본 점수, 보정 점수, rank, label, entry·exit 시각과 가격, 비용, 수익률, 포함 여부와 제외 사유를 저장한다. 키에는 최소 `(run_id, news_id, market, ticker)`가 포함되어야 한다.

### 13.3 `backtest_summary`

`run_id`, scenario, K, slice dimension/value별 지표와 표본 수, 신뢰구간을 저장한다. 전체 평균만 저장하면 후속 분석을 재현할 수 없다.

물리 SQL은 [Training Data Model](./TrainDataTable.md)의 논리 schema와 [Migration](./Migration.md)의 PostgreSQL-primary 전환 규칙에 맞춰 별도 확정한다.

## 14. 누수·재현성 검증

다음 검사는 실행 전 실패 처리한다.

- test 기간이 train·valid 이후인가?
- 동일 duplicate/event cluster가 여러 split에 존재하지 않는가?
- `feature_cutoff_at <= t0`인가?
- 모델·encoder·imputer·calibrator가 test에서 적합되지 않았는가?
- entry bar가 `eligible_entry_at` 이전 정보를 사용하지 않는가?
- benchmark와 종목의 window가 일치하는가?
- 동일 manifest로 재실행한 핵심 지표 checksum이 일치하는가?

## 15. 의사결정 기준

MVP는 단일 절대 수익률 수치가 아니라 baseline 대비 개선과 안정성으로 판단한다.

필수 조건은 다음과 같다.

1. Candidate Recall@K가 운영 Top-K의 상한을 설명할 만큼 충분하다.
2. Hit@5 또는 NDCG@5가 주요 baseline보다 개선된다.
3. 기본·보수적 비용 시나리오의 Top-K `net_excess_return`과 신뢰구간을 보고한다.
4. 월별·이벤트별 결과에서 성능 집중과 최악 구간을 설명한다.
5. 지연·비용 증가에 따른 성능 저하가 허용 범위 내인지 확인한다.

임계값은 test 결과를 본 뒤 조정하지 않는다. 승인 기준 변경은 새 valid/test 기간과 새 평가 version으로 검증한다.

## 16. 완료 기준

1. 동일 manifest로 모델과 baseline 결과를 재현할 수 있다.
2. Ranking·Tradable·Conservative 시나리오가 분리되어 있다.
3. 미래 고가를 체결 수익률로 사용하지 않는다.
4. 실행 지연, 비용, 체결 불가, 장외·장마감 규칙이 config와 결과에 남는다.
5. query-level과 chronological portfolio 지표를 구분한다.
6. cluster 단위 누수 검사와 point-in-time 검사가 자동화되어 있다.
7. 전체·slice·민감도 결과에 표본 수와 신뢰구간이 포함된다.
