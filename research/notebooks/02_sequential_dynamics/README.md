# Phase 2 Plan — Sequential Dynamics

이 문서는 Phase 1B에서 만든 discrete representation이 **시간 순서상 구조적인 전이 패턴을 가지는지** 검증하기 위한 Phase 2 계획입니다.

Phase 2의 이름은 다음으로 둡니다.

```text
Sequential Dynamics
```

Phase 2의 핵심 질문은 다음입니다.

> **Phase 1에서 만든 `shape_token`, `range_bucket`, `(shape_token, range_bucket)` sequence가 무작위 나열이 아니라 반복 가능한 transition structure를 가지는가?**

중요한 제한:

```text
Phase 2는 아직 market state modeling이 아니다.
Phase 2는 아직 future return prediction이 아니다.
Phase 2는 아직 trading signal 연구가 아니다.
```

Phase 2에서 확인할 것은 오직 다음입니다.

```text
token sequence에 통계적으로 반복되는 전이 구조가 있는가?
그 전이 구조가 train/val/test 및 symbol split을 바꿔도 유지되는가?
```

---

## 1. Background

Phase 1의 연구 단계는 다음 질문으로 시작했습니다.

```text
비슷한 candle shape를 같은 token으로 묶을 수 있는가?
```

Phase 1A에서는 price-shape only feature로 VQ-VAE shape token을 학습했습니다.

Phase 1B에서는 range / volatility context를 encoder input에 직접 섞는 대신 다음처럼 분리했습니다.

```text
shape_token  = price-shape only VQ-VAE token
range_bucket = train quantile 기반 log_range_pct bucket
final rep    = (shape_token, range_bucket)
```

Phase 1B 반복 split 결과 요약:

Source:

```text
research/notebooks/01_shape_quantization/summaries/SUMMARY.md
research/notebooks/01_shape_quantization/summaries/summary.csv
```

주요 결과:

| Split family | Runs | shape test-train L1 mean | range test-train L1 mean | pair test-train L1 mean |
|---|---:|---:|---:|---:|
| `random` | 20 | 0.091 | 0.249 | 0.292 |
| `vol_strat` | 10 | 0.096 | 0.105 | 0.164 |
| `vol_holdout` | 5 | 0.078 | 0.918 | 0.937 |

해석:

```text
shape_token은 symbol split과 volatility holdout에서도 안정적이다.
range_bucket은 volatility context를 별도로 포착한다.
pair drift는 range drift를 강하게 반영한다.
```

따라서 Phase 2로 넘어갈 최소 근거는 확보되었습니다.

---

## 2. Phase 2 Research Questions

Phase 2는 세 단계 질문으로 나눕니다.

### Q1. Transition structure exists?

```text
shape_token_t → shape_token_{t+1}
range_bucket_t → range_bucket_{t+1}
pair_token_t → pair_token_{t+1}
```

이 전이가 uniform random에 가까운지, 아니면 특정 token 다음에 특정 token이 반복적으로 나타나는지 확인합니다.

예시 질문:

```text
token 3 다음에는 token 7이 자주 오는가?
긴 upper wick 계열 token 다음에는 doji 계열 token이 자주 오는가?
extreme range bucket 이후 range bucket이 평균적으로 낮아지는가?
```

### Q2. Transition structure is stable?

전이 구조가 특정 symbol 또는 특정 split에만 의존하지 않는지 확인합니다.

```text
train transition matrix와 val/test transition matrix가 비슷한가?
random split, vol_strat split, vol_holdout split에서 같은 구조가 반복되는가?
symbol별 transition matrix가 전체 matrix와 크게 다르지 않은가?
```

### Q3. Sequential representation is richer than marginal distribution?

단순 token 빈도만으로 설명되는 구조인지, 실제 순서 정보가 추가 정보를 가지는지 확인합니다.

```text
marginal token distribution만 알면 충분한가?
아니면 token_t가 token_{t+1}에 대한 정보를 추가로 제공하는가?
```

---

## 3. Inputs and Representations

Phase 2는 Phase 1B run artifact를 입력으로 사용합니다.

기본 입력 위치:

```text
research/notebooks/01_shape_quantization/runs/phase_1b/
research/notebooks/01_shape_quantization/summaries/summary.csv
```

Phase 2에서 비교할 representation은 세 가지입니다.

### 3.1 Shape token only

```text
x_t = shape_token_t
vocabulary size = 12
```

목적:

```text
순수 candle shape sequence에 전이 구조가 있는지 확인
```

### 3.2 Range bucket only

```text
x_t = range_bucket_t
vocabulary size = 6
```

목적:

```text
volatility context 자체가 persistence / mean reversion 구조를 가지는지 확인
```

### 3.3 Shape-range pair token

```text
x_t = pair_token_t = shape_token_t * num_range_buckets + range_bucket_t
vocabulary size = 12 × 6 = 72
```

목적:

```text
shape와 volatility context를 결합했을 때 더 명확한 sequential structure가 생기는지 확인
```

주의:

```text
pair vocabulary는 sparse할 수 있다.
transition matrix는 72 × 72라서 표본 수 부족 문제가 생길 수 있다.
따라서 pair token은 smoothing과 minimum count filtering이 필요하다.
```

---

## 4. Data Split Policy

Phase 2는 Phase 1B의 split family를 그대로 이어받습니다.

```text
random
vol_strat
vol_holdout
```

Phase 2의 핵심 원칙:

```text
Phase 1B tokenizer / bucketizer fit은 train candles로만 수행한다.
Phase 2 transition metric 계산도 train/val/test를 분리해서 계산한다.
val/test transition을 train transition에 맞춰 평가한다.
```

### 4.1 Within-symbol chronology

Transition은 반드시 같은 symbol 내부에서만 계산합니다.

올바른 예:

```text
AAPL token_0 → AAPL token_1 → AAPL token_2
MSFT token_0 → MSFT token_1 → MSFT token_2
```

금지:

```text
AAPL 마지막 token → MSFT 첫 token
```

즉 symbol 경계를 넘어 transition을 만들면 안 됩니다.

### 4.2 Time order

각 symbol의 candle은 timestamp 기준 오름차순이어야 합니다.

```text
ORDER BY timestamp ASC
```

minute data에서는 local date/time ordering을 보존해야 합니다.

### 4.3 No leakage

Phase 2에서 금지되는 leakage:

```text
val/test token을 보고 transition smoothing parameter를 선택
val/test transition을 이용해 tokenizer 재학습
future token을 현재 token feature에 포함
symbol 경계를 이어붙여 가짜 transition 생성
```

---

## 5. Core Metrics

## 5.1 Transition counts

Token sequence가 다음과 같을 때:

```text
x_0, x_1, x_2, ..., x_T
```

one-step transition count는 다음입니다.

```text
C[i, j] = count(x_t = i and x_{t+1} = j)
```

symbol별 count를 먼저 계산한 뒤, split 단위로 합산합니다.

```text
C_split = sum_symbol C_symbol
```

---

## 5.2 Transition probability matrix

각 source token `i`에 대해 row-normalize합니다.

```text
P[j | i] = C[i, j] / sum_k C[i, k]
```

smoothing이 필요한 경우 train에서만 smoothing policy를 정합니다.

초기 smoothing:

```text
alpha = 1e-6
```

pair token처럼 sparse한 경우:

```text
source_count(i) < min_source_count이면 해당 row를 stability 평가에서 제외
```

초기값:

```text
min_source_count = 100
```

---

## 5.3 Transition entropy

각 source token에서 다음 token이 얼마나 예측 불가능한지 봅니다.

```text
H(i) = - sum_j P[j | i] * log2(P[j | i])
```

전체 weighted transition entropy:

```text
H_weighted = sum_i source_ratio(i) * H(i)
```

해석:

```text
entropy가 낮다  → 특정 next token으로 전이가 집중됨
entropy가 높다  → next token이 다양하고 불확실함
```

단, entropy가 낮다고 좋은 것은 아닙니다. token collapse나 low-count artifact일 수 있으므로 utilization과 함께 해석합니다.

---

## 5.4 Transition matrix stability

train과 val/test의 transition matrix 차이를 봅니다.

기본 metric:

```text
transition_l1(P_train, P_eval)
```

row-weighted L1:

```text
sum_i w_i * sum_j |P_train[j|i] - P_eval[j|i]|
```

초기 weight:

```text
w_i = train source_ratio(i)
```

이렇게 하면 train에서 거의 나오지 않는 source token의 noisy row가 전체 metric을 지배하지 않습니다.

---

## 5.5 Persistence and self-transition

각 token이 다음 step에서도 유지되는지 봅니다.

```text
self_transition_rate = sum_i C[i, i] / sum_{i,j} C[i, j]
```

특히 range bucket은 persistence가 강할 가능성이 있습니다.

예상:

```text
range_bucket self-transition > shape_token self-transition
```

---

## 5.6 Mutual information proxy

순서 정보가 marginal distribution보다 추가 정보를 가지는지 보기 위해 다음을 계산합니다.

```text
I(x_t; x_{t+1}) = sum_{i,j} P(i,j) * log2(P(i,j) / (P(i)P(j)))
```

해석:

```text
I ≈ 0     → 다음 token이 현재 token과 거의 독립
I > 0     → 현재 token이 다음 token에 대한 정보를 일부 제공
```

초기에는 full statistical test보다 descriptive metric으로 사용합니다.

---

## 5.7 Baseline comparison

Phase 2는 반드시 baseline과 비교합니다.

### Baseline A — Marginal shuffle

각 symbol의 token multiset은 유지하되 순서를 shuffle합니다.

```text
same token histogram
no temporal order
```

목적:

```text
관측된 transition structure가 단순 token 빈도 때문인지 분리
```

### Baseline B — First-order Markov train model

train transition matrix로 val/test sequence의 next token likelihood를 평가합니다.

```text
NLL = - mean_t log P_train[x_{t+1} | x_t]
```

비교 대상:

```text
marginal model: P[x_{t+1}]
first-order model: P[x_{t+1} | x_t]
```

판단:

```text
first-order NLL < marginal NLL이면 sequence 정보가 추가 설명력을 가짐
```

### Baseline C — KMeans token

Phase 1B에서 KMeans가 VQ-VAE와 비슷한 성능을 보였으므로 Phase 2에서도 비교합니다.

```text
VQ-VAE shape token sequence
KMeans shape token sequence
```

질문:

```text
VQ-VAE token sequence가 KMeans token sequence보다 더 안정적인 transition structure를 가지는가?
```

---

## 6. Experiment Plan

## 6.1 Phase 2A — Single-run smoke test

목적:

```text
Phase 2 metric 계산 pipeline이 정상 동작하는지 확인
```

대상 run:

```text
shape_token_range_bucket_NASDAQ_1m_k12_random_00
```

산출물:

```text
transition matrices
transition entropy table
self-transition rates
marginal vs first-order NLL
shuffle baseline comparison
```

추천 notebook:

```text
research/notebooks/02_sequential_dynamics/01_phase_2a_transition_smoke.ipynb
```

---

## 6.2 Phase 2B — Repeated split aggregation

목적:

```text
random / vol_strat / vol_holdout 전체 run에서 transition metric을 집계
```

대상:

```text
random:      20 runs
vol_strat:   10 runs
vol_holdout:  5 runs
```

산출물:

```text
summary_transition.csv
summary_transition_random.csv
summary_transition_vol_strat.csv
summary_transition_vol_holdout.csv
```

분석 단위:

```text
shape_token only
range_bucket only
pair token
VQ-VAE vs KMeans shape token
```

---

## 6.3 Phase 2C — Symbol-level transition stability

목적:

```text
전체 transition structure가 일부 symbol에만 의해 만들어진 것인지 확인
```

방법:

```text
symbol별 transition matrix 계산
symbol matrix와 split-level matrix의 distance 계산
symbol별 self-transition / entropy 비교
```

산출물:

```text
per_symbol_transition_summary.csv
per_symbol_transition_heatmap.png
```

해석:

```text
소수 symbol만 강한 구조를 보이면 common sequence vocabulary라고 보기 어렵다.
여러 symbol에서 유사한 transition 구조가 반복되면 Phase 2 근거가 강해진다.
```

---

## 6.4 Phase 2D — Lag and horizon extension

one-step transition이 확인되면 lag를 확장합니다.

```text
x_t → x_{t+1}
x_t → x_{t+2}
x_t → x_{t+5}
x_t → x_{t+10}
```

목적:

```text
transition structure가 아주 짧은 micro persistence인지,
몇 step 이후에도 남는 structure인지 확인
```

주의:

```text
horizon이 커질수록 sample count가 줄어든다.
minute data에서는 session boundary 처리가 필요할 수 있다.
```

---

## 7. Figures

Phase 2에서 자동 저장할 figure는 다음입니다.

```text
figures/
  01_shape_transition_matrix.png
  02_range_transition_matrix.png
  03_pair_transition_matrix.png
  04_transition_entropy_by_token.png
  05_self_transition_rate_by_representation.png
  06_train_val_test_transition_distance.png
  07_markov_vs_marginal_nll.png
  08_vqvae_vs_kmeans_transition_stability.png
  09_per_symbol_transition_distance_heatmap.png
```

Figure 해석 원칙:

```text
transition matrix의 diagonal이 강하면 persistence 가능성
특정 off-diagonal pattern이 반복되면 shape rotation 가능성
range matrix의 high/high, extreme/extreme이 강하면 volatility clustering 가능성
```

단, 다음 표현은 금지합니다.

```text
매수/매도 신호
상승/하락 예측
definitive market regime
```

---

## 8. Proposed File Structure

Phase 2는 Shape Quantization 폴더와 분리합니다.

```text
research/notebooks/02_sequential_dynamics/
  README.md
  Phase2.md
  01_phase_2a_transition_smoke.ipynb
  02_phase_2b_repeated_transition_summary.ipynb
  scripts/
    collect_transition_metrics.py
  results/
    01_phase_2a_result.md
    02_phase_2b_result.md
  summaries/
    summary_transition.csv
    summary_transition_random.csv
    summary_transition_vol_strat.csv
    summary_transition_vol_holdout.csv
  runs/
    phase_2a/
    phase_2b/
```

공통 helper는 notebook에만 두지 말고 `research/tokenizers/sequence_metrics.py`를 확장합니다.

현재 존재하는 helper:

```text
transition_counts(tokens)
transition_report(tokens)
```

확장 후보:

```text
transition_matrix(tokens, vocab_size)
transition_entropy(matrix)
transition_l1(train_matrix, eval_matrix, row_weights)
self_transition_rate(matrix)
mutual_information(tokens)
markov_nll(tokens, train_matrix)
shuffle_baseline(tokens, seed)
```

---

## 9. Implementation Steps

### Step 1 — Phase 2 folder scaffold

```text
research/notebooks/02_sequential_dynamics/
  README.md
  Phase2.md
  scripts/
  results/
  summaries/
  runs/
```

### Step 2 — sequence_metrics.py 확장

추가할 함수:

```text
transition_matrix
row_normalize
weighted_transition_l1
transition_entropy_by_source
weighted_transition_entropy
self_transition_rate
mutual_information_lag1
markov_nll
marginal_nll
```

테스트:

```text
tests for synthetic token sequences
empty sequence
single-token sequence
missing token rows
zero-count rows
```

### Step 3 — Phase 2A smoke notebook

입력:

```text
runs/phase_1b/shape_token_range_bucket_NASDAQ_1m_k12_random_00
```

출력:

```text
runs/phase_2a/transition_smoke_random_00/
  metrics.json
  experiment_config.json
  figures/
```

### Step 4 — repeated transition runner

Phase 1B의 35개 run을 순회해서 transition metrics를 계산합니다.

```text
for each phase_1b run:
  load experiment_config.json
  reconstruct or load token sequences by symbol
  compute train/val/test transition metrics
  compare val/test to train
  save metrics.json
```

주의:

```text
Phase 1B metrics.json에는 histogram은 있지만 full token sequence가 없을 수 있다.
필요하면 tokenizer.pt와 original candles로 token sequence를 재생성해야 한다.
```

### Step 5 — aggregation and report

```text
summaries/summary_transition.csv
results/02_phase_2b_result.md
```

---

## 10. Decision Criteria

Phase 2의 초기 통과 기준은 다음처럼 둡니다.

### 10.1 Transition structure exists

다음 중 하나 이상을 만족해야 합니다.

```text
first-order Markov NLL < marginal NLL
observed transition entropy < shuffle baseline transition entropy
mutual information I(x_t; x_{t+1}) > shuffle baseline
```

### 10.2 Transition structure is stable

```text
random split transition_l1 mean이 낮고 max가 과도하지 않음
vol_strat split에서 transition_l1이 random과 비슷하거나 더 낮음
vol_holdout에서 shape transition_l1은 낮고 range transition_l1은 높아도 허용
```

초기 임시 기준:

```text
shape transition_l1 random mean < 0.20
shape transition_l1 random max  < 0.35
shape transition_l1 vol_strat mean < 0.20
```

이 threshold는 첫 결과를 본 뒤 조정합니다.

### 10.3 Pair token caution

Pair token은 vocabulary가 72로 크기 때문에 더 엄격한 count filter가 필요합니다.

```text
pair transition result는 source_count >= 100인 row만 primary metric에 포함
low-count pair rows는 appendix 또는 diagnostic으로만 해석
```

---

## 11. Expected Outcomes

가능한 결과 해석은 다음과 같습니다.

### Outcome A — Strong sequential structure

```text
Markov NLL이 marginal NLL보다 명확히 낮다.
transition matrix가 split 간 안정적이다.
shuffle baseline보다 mutual information이 높다.
```

해석:

```text
Phase 3 Market State Modeling으로 진행할 근거가 강하다.
```

### Outcome B — Weak but stable structure

```text
Markov NLL 개선은 작지만 transition_l1은 안정적이다.
```

해석:

```text
shape token은 sequential modeling에 사용할 수 있지만,
더 긴 context 또는 range/pair representation이 필요할 수 있다.
```

### Outcome C — Range only structure

```text
shape token transition은 약하지만 range bucket transition은 강하다.
```

해석:

```text
현재 representation은 volatility clustering은 잘 포착하지만
shape dynamics는 약할 수 있다.
```

### Outcome D — No stable structure

```text
Markov model이 marginal baseline을 이기지 못한다.
transition matrix가 split별로 크게 흔들린다.
```

해석:

```text
Phase 3으로 바로 넘어가지 않고 Phase 1 token design을 재검토한다.
```

---

## 12. What Phase 2 Must Not Claim

Phase 2 결과가 좋아도 다음을 말하면 안 됩니다.

```text
이 token은 매수 신호다.
이 sequence는 상승장을 의미한다.
이 transition은 future return을 예측한다.
이 token은 market state다.
```

Phase 2에서 허용되는 표현은 다음입니다.

```text
token transition structure가 있다.
transition entropy가 baseline보다 낮다.
first-order Markov model이 marginal baseline보다 sequence를 더 잘 설명한다.
shape transition은 range holdout에서도 비교적 안정적이다.
```

Market state 또는 future dynamics 설명은 Phase 3에서 별도로 검증합니다.

---

## 13. Immediate Next Task

가장 먼저 할 일은 다음입니다.

```text
Phase 2A smoke notebook 작성
```

권장 순서:

1. `research/tokenizers/sequence_metrics.py` 확장
2. synthetic sequence unit test 추가
3. `02_sequential_dynamics/01_phase_2a_transition_smoke.ipynb` 작성
4. `random_00` run 하나로 transition matrix / entropy / baseline figure 생성
5. 결과를 `results/01_phase_2a_result.md`로 정리

첫 smoke test의 성공 기준:

```text
symbol boundary를 넘지 않고 transition count가 계산된다.
shape/range/pair transition matrix가 저장된다.
Markov vs marginal NLL이 계산된다.
shuffle baseline이 재현 가능하게 생성된다.
figures가 자동 저장된다.
```
