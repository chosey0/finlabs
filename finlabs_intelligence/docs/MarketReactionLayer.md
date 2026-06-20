# FinLabs News Intelligence — Market Reaction Layer

> 구조화된 뉴스 신호와 관측 시점 이전의 시장 상태를 결합해 후보 종목의 단기 반응 가능성을 순위화하는 계층

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 설계 상태 | Target contract — feature builder·모델·ranking 미구현 |
| Feature 계약 | [Feature Dictionary](./FeatureDictionary.md) |
| 선행 계층 | [News Trigger Layer](./NewsTriggerLayer.md) |
| 평가 계약 | [Backtest](./Backtest.md) |
| 입력 단위 | `(news_id, market, ticker, t0)` |
| MVP 목표 | `t0` 이후 30분 내 `strong_reaction` 확률 |
| 출력 | 뉴스별 후보 종목 Top-K, 확률, 근거, 모델 버전 |
| 기본 모델 | LightGBM binary classifier + 뉴스별 점수 정렬 |

## 1. 목적과 핵심 가설

Market Reaction Layer는 뉴스가 강한지만 보지 않는다. **뉴스 강도 × 종목 관련성 × 직전 수급 × 시장·섹터 국면 × 유동성 × 시간대**가 결합될 때 단기 반응 가능성이 높아진다는 가설을 검증한다.

이 계층의 책임은 다음과 같다.

- 후보별 `t0` 이전 시장 상태를 동일한 기준으로 생성한다.
- 30분 내 강한 반응 확률을 추정한다.
- 같은 뉴스의 후보를 비교 가능한 점수로 정렬한다.
- 모델 성능과 실전 유효성을 baseline 대비 평가한다.

자동 주문, 포지션 크기 결정, 손익 보장은 범위 밖이다.

## 2. 입력 계약

### 2.1 News Trigger Features

| Feature | 타입 | 설명 |
|---|---|---|
| `trigger_probability` | float | 사전 시점 Trigger 확률 |
| `event_type` | category | taxonomy v1 이벤트 |
| `polarity` | category | 후보 종목에 대한 영향 방향 |
| `certainty` | ordinal | `C0`~`C3` |
| `immediacy` | ordinal | `I0`~`I3` |
| `scope` | category | 종목·섹터·테마·시장 |
| `novelty_score` | float | 새 사건일 가능성 |
| `is_posthoc_article` | bool | 사후 설명 기사 flag |

### 2.2 Candidate Relation Features

| Feature | 타입 | 설명 |
|---|---|---|
| `candidate_score` | float | 후보 생성 규칙 점수 |
| `relation_type` | category | 직접 언급·테마·섹터 등 |
| `direct_mention` | bool | 제목·요약 직접 언급 여부 |
| `title_mention` | bool | 제목 직접 언급 여부 |
| `theme_match_score` | float | 테마 매핑 강도 |
| `sector_match_score` | float | 섹터 매핑 강도 |
| `relation_strength` | float | 버전된 관계 강도 |

### 2.3 Market State Features

모든 lookback window는 `t0` 이하에서 끝나야 한다. `return_5m`은 `[t0-5m, t0]` 구간이며 `t0` 이후 5분이 아니다.

| 그룹 | MVP Feature | 후속 Feature |
|---|---|---|
| 가격 | `return_1m`, `return_5m`, `return_15m`, `pre_return_5m` | gap, relative strength |
| 거래 | `volume_z_1m`, `volume_z_5m`, `turnover_z_5m` | trade count, buy/sell imbalance |
| 변동성 | `volatility_5m`, `volatility_15m`, `range_ratio` | realized volatility regime |
| 유동성 | `avg_turnover_20d`, `market_cap`, `liquidity_pass` | spread, orderbook depth, free float |
| 시간 | `minutes_from_open`, `minutes_to_close`, `session_type` | auction/VI 상태 |
| 시장 | `market_return_5m`, `market_return_15m` | breadth, volatility index |
| 섹터·테마 | `sector_return_5m`, `sector_turnover_z_5m` | theme momentum |

Z-score의 기준 집합과 lookback 기간은 `feature_version`에 포함한다. 장 시작 직후처럼 충분한 당일 관측치가 없는 구간은 과거 동일 시간대 분포를 사용하거나 결측 flag를 명시한다.

## 3. 시간과 세션 처리

### 3.1 기준 시각

`t0 = first_seen_at`이다. 시스템이 뉴스를 처음 관측하기 전 시장 데이터만 특징에 사용할 수 있다.

### 3.2 정규장 기사

- 분봉 경계 중간에 도착한 뉴스는 다음 완결 분봉을 라벨 구간의 시작으로 사용할 수 있다.
- 이 경우 원래 `t0`와 `label_window_start`를 모두 저장한다.
- 특징은 `t0` 이후 체결을 포함하지 않는다.

### 3.3 장외·휴장일 기사

장외 기사는 장중 기사와 별도 cohort로 관리한다.

- `session_type`: `pre_market`, `regular`, `after_market`, `closed_day`
- 다음 정규장 개시 전까지 도착한 중복 기사는 하나의 event cluster로 묶는다.
- 라벨 window는 다음 정규장 개시 시점부터 계산한다.
- 장외 cohort가 충분하지 않으면 MVP 학습에서 제외하고 별도 리포트한다.

## 4. Target과 Label

### 4.1 기본 연속형 지표

```text
future_max_excess_return_30m =
    max(stock_return(label_window_start, t)
        - benchmark_return(label_window_start, t)),
    t ∈ (label_window_start, label_window_end]
```

benchmark는 시장 지수를 기본으로 하고 섹터 지수가 안정적으로 제공되면 병행 비교한다. 가격은 split·배당 등 corporate action을 보정해야 한다.

`future_turnover_z_30m`은 label window의 누적 거래대금을 과거 동일 종목·동일 시간대 분포로 표준화한다. 정규장 기사에서는 window가 `t0` 이후 첫 체결 가능한 완결 분봉에서 시작할 수 있고, 장외 기사는 다음 정규장 cohort 규칙을 따른다.

### 4.2 MVP 분류 라벨

| Class | 초기 가설 |
|---|---|
| `strong` | 최대 초과수익률 ≥ 3% 그리고 거래대금 Z-score ≥ 2 |
| `medium` | 최대 초과수익률 ≥ 1.5% |
| `weak` | 최대 초과수익률 ≥ 0.5% |
| `none` | 그 외 |

MVP binary target은 `is_strong_reaction = reaction_class == "strong"`이다. 임계값은 데이터 분포 확인 후 `label_version`으로 고정한다.

### 4.3 Reaction score 사용 원칙

수익률과 Z-score를 원시 단위로 단순 가중합하지 않는다. 연속형 `reaction_score`가 필요하면 학습 구간 통계로 각각 정규화한 뒤 결합한다.

```text
reaction_score =
    0.7 × scaled_future_max_excess_return_30m
  + 0.3 × scaled_future_turnover_z_30m
```

scaler는 train split에서만 적합하고 `label_version`과 함께 보존한다.

## 5. 데이터셋 구성

### 5.1 Positive와 Negative

- Positive: 라벨 기준을 충족한 후보
- Hard negative: 동일 뉴스 후보 중 유동성은 충분하지만 반응하지 않은 종목
- Background negative: Trigger가 아닌 뉴스 또는 무관 후보

같은 뉴스의 모든 후보를 그대로 쓰면 negative가 과도하게 늘 수 있다. 뉴스별 sample weight 또는 계층적 sampling으로 특정 대형 후보군이 손실을 지배하지 않게 한다.

### 5.2 Split

- 랜덤 split 금지
- train → valid → test 시간 순서 유지
- 동일 duplicate/event cluster는 하나의 split에만 포함
- 동일 날짜·뉴스의 후보가 여러 split으로 나뉘지 않음
- 최종 test는 모델·임계값·특징 선택에 사용하지 않음

### 5.3 결측과 이상치

- 결측 자체가 정보일 수 있으므로 `*_missing` flag를 제공한다.
- 거래정지, VI, 상·하한가, corporate action은 별도 flag 또는 제외 사유로 남긴다.
- 극단값 clipping 기준은 train split에서만 산출한다.

## 6. 모델 전략

### 6.1 Baseline

최소 네 가지 baseline을 유지한다.

1. 무작위 후보 정렬
2. 직접 언급 우선 정렬
3. `candidate_score` 단독 정렬
4. `turnover_z_5m` 단독 정렬

복합 모델은 시간 순서 test에서 baseline을 유의미하게 개선해야 한다.

### 6.2 MVP

- LightGBM binary classifier
- target: `is_strong_reaction`
- output: calibrated `reaction_probability`
- ranking: 같은 `news_id` 내 확률 내림차순

클래스 불균형은 class weight와 뉴스별 sample weight를 비교한다. 확률은 isotonic 또는 Platt scaling을 valid 구간에서 적합하고 test에서 평가한다.

### 6.3 후속 단계

1. 연속형 reaction score 회귀
2. Pairwise ranking: 같은 뉴스 내 positive > negative
3. LambdaRank 또는 listwise objective
4. 국면·이벤트 유형별 mixture 또는 calibration

## 7. 최종 점수와 필터

MVP의 기본 순위 점수는 보정된 `reaction_probability`다. 운영 규칙을 더할 경우 모델 점수와 혼합하지 말고 사유가 추적 가능한 별도 필터 또는 보정 필드로 유지한다.

```text
final_score = calibrated_model_score + bounded_adjustments
```

`reaction_probability`는 calibration된 확률로 그대로 보존한다. adjustment가 적용된 `final_score`는 정렬용 비확률 점수이며 0~1 확률로 해석하거나 calibration 지표 계산에 사용하지 않는다.

허용 가능한 보정 예:

- `pre_move_penalty`
- `low_liquidity_penalty`
- `duplicate_news_penalty`
- `sector_momentum_adjustment`

각 보정은 범위가 제한되어야 하며 `scoring_version`과 근거를 출력한다. 학습 특징으로 이미 반영된 값을 운영 단계에서 다시 크게 보정해 이중 계산하지 않는다.

## 8. 출력 계약

```json
{
  "news_id": "N20260619_001",
  "t0": "2026-06-19T10:05:00+09:00",
  "model_version": "reaction-lgbm-v1",
  "feature_version": "market-features-v1",
  "label_version": "reaction-30m-v1",
  "ranked_candidates": [
    {
      "rank": 1,
      "market": "KOSDAQ",
      "ticker": "042700",
      "name": "한미반도체",
      "reaction_probability": 0.74,
      "final_score": 0.74,
      "expected_horizon": "0-30m",
      "main_factors": [
        "direct_mention",
        "high_trigger_probability",
        "turnover_spike_5m",
        "sector_momentum_positive"
      ],
      "warnings": []
    }
  ]
}
```

`main_factors`는 SHAP 등 설명 방법의 안정성을 검토한 뒤 제공한다. 인과 설명이 아니라 모델 기여 요약임을 UI에 명시한다.

## 9. 평가 체계

### 9.1 핵심 랭킹 지표

- Hit@1, Hit@3, Hit@5
- NDCG@5, NDCG@10
- Precision@K
- Mean Top-K excess return

### 9.2 분류·확률 지표

- PR-AUC와 ROC-AUC
- Recall at fixed precision
- False Positive Rate
- Brier score, calibration error

### 9.3 실전성 지표

- Top-1·Top-3 평균 30분 초과수익률
- 거래비용·슬리피지 적용 후 평균 수익률
- 뉴스당 평균 후보 수
- 장중·장외·이벤트 유형·유동성 구간별 성능
- 특징 생성과 추론 p50/p95 지연

평균만 보고하지 않고 표본 수, 신뢰구간, 월별 안정성과 최악 구간을 함께 제시한다.

## 10. MVP Feature Set

```text
trigger_probability, event_type, certainty, immediacy, polarity,
candidate_score, relation_type, direct_mention, title_mention,
theme_match_score, sector_match_score,
return_1m, return_5m, return_15m,
turnover_z_5m, turnover_ratio_5m, volume_z_5m, volatility_5m,
market_return_5m, sector_return_5m, sector_turnover_z_5m,
avg_turnover_20d, market_cap,
minutes_from_open, session_type, session_bucket,
pre_move_flag, liquidity_pass
```

## 11. 완료 기준

1. 특징 생성 시점과 lookback window가 자동 검증된다.
2. 미래 데이터, 재수집 시각 덮어쓰기, split cluster 누수를 탐지하는 테스트가 있다.
3. baseline과 LightGBM 결과를 동일한 시간 순서 test에서 비교한다.
4. 뉴스별 랭킹 지표와 calibration 지표를 함께 보고한다.
5. 장외·결측·거래정지·저유동성 처리 사유가 데이터에 남는다.
6. 모든 출력은 [Training Data Model](./TrainDataTable.md)의 버전 필드로 재현 가능하다.

## 12. 구조 요약

```text
News Trigger Features + Candidate Relation Features
                         +
             t0 이전 Market State Features
                         ↓
             Reaction Probability Model
                         ↓
                 뉴스별 Top-K Ranking
```
