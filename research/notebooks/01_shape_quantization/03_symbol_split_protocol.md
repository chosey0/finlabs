# Symbol Split Repeated Evaluation Protocol

이 문서는 Shape Quantization 연구에서 여러 symbol split에 대해 반복 실험을 수행하기 위한 평가 프로토콜입니다.

현재까지의 Phase 1A / 1B 결과는 다음을 보여줍니다.

```text
shape token은 비교적 안정적이다.
range bucket은 종목별 volatility profile에 따라 크게 달라진다.
shape-range pair distribution은 range bucket 변화의 영향을 받는다.
```

따라서 한두 개 held-out split만으로 일반화 결론을 내리면 안 됩니다. 이후 실험은 여러 symbol split을 반복 실행하고, 결과를 평균과 분산으로 평가해야 합니다.

---

## 1. Goal

반복 실험의 목표는 다음 질문에 답하는 것입니다.

> **single market × multiple symbols × single timeframe 조건에서 shape token vocabulary가 symbol split 변화에도 안정적인가?**

Phase 1B에서는 질문을 하나 더 추가합니다.

> **range bucket drift가 shape token drift와 분리되어 관측되는가?**

즉, 평가 대상은 세 가지입니다.

```text
1. shape token stability
2. range bucket drift
3. shape-range pair drift
```

---

## 2. Fixed Controls

반복 split 실험에서는 비교 가능성을 위해 다음 값들을 고정합니다.

| Item | Fixed Value |
|------|-------------|
| Market | 하나의 market, 예: `NASDAQ` |
| Timeframe | 하나의 interval, 예: `1m` |
| Feature set | Phase별 고정 feature |
| Codebook size | 기본 `K = 12` |
| Max candles per symbol | 예: `12,000` |
| Min candles per symbol | 예: `500` |
| Train / val / test symbol count rule | split plan에 따라 고정 |
| Random seed | split별 명시 |
| Range bucket thresholds | 각 run의 train split으로만 fit |

비교 중에 바꾸면 안 되는 것:

```text
같은 comparison group 안에서 market 변경 금지
같은 comparison group 안에서 timeframe 변경 금지
같은 comparison group 안에서 K 변경 금지
같은 comparison group 안에서 feature set 변경 금지
```

---

## 3. Symbol Universe

반복 실험은 먼저 symbol universe를 정의한 뒤 시작합니다.

예시:

```text
NASDAQ large/mega cap:
AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, AVGO, NFLX

NASDAQ high-vol / growth:
AMD, PLTR, RKLB, SMCI, MSTR, COIN, ARM
```

초기 권장 universe:

```text
AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL,
AVGO, NFLX, AMD, INTC, RKLB, PLTR
```

단, 실제 실험에서는 DuckDB warehouse에 충분한 candle이 있는 symbol만 사용합니다.

---

## 4. Split Families

하나의 split 방식만 쓰면 결론이 split 선택에 과도하게 의존합니다. 따라서 최소한 다음 split family를 구분합니다.

### 4.1 Random Symbol Split

symbol universe에서 무작위로 train / val / test를 나눕니다.

목적:

```text
일반적인 held-out symbol generalization 확인
```

권장 반복 수:

```text
N = 10 이상
```

예시:

```text
train: 70%
val:   10~15%
test:  나머지
```

---

### 4.2 Volatility-stratified Split

symbol별 range profile을 먼저 계산한 뒤, low / medium / high volatility group이 train / val / test에 모두 섞이도록 나눕니다.

목적:

```text
range bucket drift가 특정 volatility group holdout 때문인지 확인
```

권장 방식:

```text
1. 각 symbol의 median log_range_pct 계산
2. symbol을 low / medium / high volatility tertile로 나눔
3. 각 tertile에서 train / val / test를 샘플링
```

**주의 — 데이터 누수 방지:**

volatility profile 계산은 symbol이 가진 **전체 candle 데이터**로 수행합니다.
`RangeBucketizer` (quantile threshold fit)와는 달리 stratification step은 split을 결정하는 단계이므로,
어떤 split의 candle만 사용할지 아직 정해지지 않았습니다.
따라서 stratification용 volatility 측정값은 **symbol 단위 요약 통계** (예: 전체 candle의 median log_range_pct)를 사용하는 것이 맞습니다.

금지 패턴:

```text
✗ train split이 확정된 후 train candle만으로 volatility를 재계산하고 stratification 재적용
  → train에 저변동 종목이 몰리도록 사후적으로 조작하는 것과 같음
✗ 미래 candle (백테스트 기간 등)을 포함해 volatility 계산
  → 실제 운영 환경에서 재현 불가능한 split 기준이 됨
```

올바른 패턴:

```text
✓ 가용 candle 전체 (cap 적용 후)의 median log_range_pct를 symbol별로 계산
✓ 이 값으로 tertile 경계를 결정한 후 symbol을 그룹화
✓ 각 그룹에서 random으로 train/val/test 심볼을 선택
✓ 그룹화 기준(tertile boundaries)과 사용된 candle 범위를 experiment_config.json에 저장
```

---

### 4.3 Volatility-held-out Split

특정 volatility group 자체를 held-out으로 둡니다.

목적:

```text
high-volatility symbol에 대한 worst-case generalization 확인
```

예시:

```text
train: low + medium volatility symbols
val:   일부 high volatility symbols
test:  나머지 high volatility symbols
```

이 split은 range bucket drift가 크게 나오는 것이 정상입니다. 여기서 중요한 것은 shape token이 같이 무너지는지 여부입니다.

---

### 4.4 Sector / Theme-held-out Split

가능하면 sector 또는 theme 단위로 held-out합니다.

예시:

```text
train: mega-cap tech + consumer
val:   semiconductor
test:  high-growth / speculative
```

목적:

```text
특정 theme 또는 sector에 대한 shape vocabulary 일반화 확인
```

---

### 4.5 Manual Stress Split

연구자가 의도적으로 어려운 split을 구성합니다.

예시:

```text
train: AAPL, MSFT, AMZN, META, GOOGL
val:   AMD
test:  RKLB, PLTR
```

목적:

```text
known high-volatility symbols에서 representation이 어떻게 변하는지 확인
```

Manual split은 결론을 대표하지 않습니다. stress test로만 해석합니다.

---

## 5. Required Metrics

각 run은 최소한 다음 metric을 저장해야 합니다.

### 5.1 Shape Token Metrics

```text
shape_train_entropy
shape_val_entropy
shape_test_entropy
shape_train_utilized_count
shape_val_utilized_count
shape_test_utilized_count
shape_val_train_l1
shape_test_train_l1
shape_val_train_max_diff
shape_test_train_max_diff
shape_mean_semantic_consistency_train
shape_mean_semantic_consistency_val
shape_mean_semantic_consistency_test
```

### 5.2 Range Bucket Metrics

Phase 1B 이상에서 기록합니다.

```text
range_train_entropy
range_val_entropy
range_test_entropy
range_val_train_l1
range_test_train_l1
range_val_train_max_diff
range_test_train_max_diff
```

### 5.3 Shape-Range Pair Metrics

Phase 1B revised representation에서 기록합니다.

```text
pair_train_entropy
pair_val_entropy
pair_test_entropy
pair_train_utilized_count
pair_val_utilized_count
pair_test_utilized_count
pair_val_train_l1
pair_test_train_l1
pair_val_train_max_diff
pair_test_train_max_diff
```

### 5.4 Baseline Metrics

KMeans baseline은 필수입니다.

```text
kmeans_shape_val_train_l1
kmeans_shape_test_train_l1
kmeans_pair_val_train_l1
kmeans_pair_test_train_l1
kmeans_inertia_per_sample
```

---

## 6. Aggregated Metrics

반복 실험의 최종 보고는 개별 run이 아니라 split family별 집계로 작성합니다.

필수 집계:

```text
mean
std
min
max
median
```

예시 table:

| Split Family | N | Metric | Mean | Std | Min | Max |
|--------------|---|--------|------|-----|-----|-----|
| random | 10 | shape_test_train_l1 | ... | ... | ... | ... |
| random | 10 | range_test_train_l1 | ... | ... | ... | ... |
| random | 10 | pair_test_train_l1 | ... | ... | ... | ... |
| volatility-held-out | 5 | shape_test_train_l1 | ... | ... | ... | ... |
| volatility-held-out | 5 | range_test_train_l1 | ... | ... | ... | ... |

---

## 7. Recommended Run Naming

각 run은 split family와 index를 이름에 포함합니다.

```text
phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_random_00
phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_random_01
phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_vol_strat_00
phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_vol_holdout_00
phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_stress_00
```

수동 비교용 suffix는 사용 가능하지만, 최종 집계에서는 split metadata를 반드시 저장해야 합니다.

```text
phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_a
```

위와 같은 이름만으로는 split family를 알기 어렵기 때문에 `experiment_config.json`에 다음 필드를 포함해야 합니다.

```json
{
  "split_family": "manual_stress",
  "split_index": 0,
  "split_seed": 42,
  "train_symbols": ["..."],
  "val_symbols": ["..."],
  "test_symbols": ["..."]
}
```

---

## 8. Suggested Summary CSV Schema

반복 실험 결과는 `summary.csv` 또는 `summary.jsonl`로 모읍니다.

집계는 `collect_metrics.py`로 자동화할 수 있습니다.

```bash
python research/notebooks/01_shape_quantization/collect_metrics.py \
    --runs-dir research/notebooks/01_shape_quantization/runs \
    --out research/notebooks/01_shape_quantization/summary.csv
```

Phase 1A run 및 ablation run (`phase_1b_shape_range_*`)은 `range_bucket` 키가 없어 자동 스킵됩니다.

권장 CSV columns:

```text
run_id
run_dir
phase
market
interval
codebook_size
split_family
split_index
split_seed
train_symbols
val_symbols
test_symbols
train_candles
val_candles
test_candles
shape_val_train_l1
shape_test_train_l1
shape_val_train_max_diff
shape_test_train_max_diff
shape_train_entropy
shape_val_entropy
shape_test_entropy
range_val_train_l1
range_test_train_l1
range_val_train_max_diff
range_test_train_max_diff
range_train_entropy
range_val_entropy
range_test_entropy
pair_val_train_l1
pair_test_train_l1
pair_val_train_max_diff
pair_test_train_max_diff
pair_train_entropy
pair_val_entropy
pair_test_entropy
kmeans_shape_val_train_l1
kmeans_shape_test_train_l1
kmeans_pair_val_train_l1
kmeans_pair_test_train_l1
notes
```

---

## 9. Interpretation Rules

### 9.1 Success Criteria — Shape Token

Shape token은 다음 조건을 만족하면 안정적이라고 봅니다.

```text
shape_test_train_l1이 대부분의 random split에서 낮다.
volatility-held-out split에서도 shape drift가 range drift보다 훨씬 작다.
dead token이 반복적으로 발생하지 않는다.
semantic consistency가 split별로 크게 악화되지 않는다.
```

초기 기준값은 임시로 다음처럼 둡니다.

```text
random split shape_test_train_l1 mean  < 0.15
random split shape_test_train_l1 std   < 0.05
random split shape_test_train_l1 max   < 0.30
```

**N이 충분하지 않으면 mean/std 보고가 무의미합니다.**
N < 5이면 std를 보고하지 않거나, "N이 부족하여 std 신뢰 불가" 주석을 붙여야 합니다.
현재 k12 revised run은 3개(k12/k12_a/k12_b)로, 이 기준을 충족하지 못합니다.
반복 실험을 최소 5 runs 이상 수행한 뒤 mean/std를 보고하세요.

이 기준은 더 많은 run이 쌓이면 조정합니다.

### 9.2 Expected Behavior — Range Bucket

Range bucket은 종목별 volatility profile을 반영하므로 split에 따라 달라지는 것이 정상입니다.

허용 가능한 해석:

```text
range drift가 크다 → held-out symbols의 volatility profile이 train과 다르다.
```

실패 해석이 필요한 경우:

```text
range bucket이 항상 한 bucket에만 몰린다.
train split에서도 range bucket이 의도한 quantile 비율을 만들지 못한다.
range bucket drift를 해석할 metadata가 없다.
```

### 9.3 Pair Distribution

Pair drift는 shape drift와 range drift를 분해해서 해석합니다.

```text
pair drift가 크고 shape drift가 작다:
  range profile 차이가 pair drift의 주원인입니다.

pair drift가 크고 shape drift도 크다:
  shape vocabulary가 held-out symbols에서 불안정할 수 있습니다.
```

---

## 10. Minimum Next Experiment Set

다음 단계에서 최소한 아래 run set을 수행합니다.

```text
random split:              5 runs
volatility-stratified:     3 runs
volatility-held-out:       2 runs
```

총 최소 10 runs입니다.

**manual stress split은 최소 run set에 포함하지 않습니다.**
stress split은 특정 held-out 조합에 대한 worst-case 탐색 목적이므로, 집계 통계를 왜곡할 수 있습니다.
stress split 결과는 별도 섹션에서 해석하고, mean/std 집계에서는 제외합니다.

더 안정적인 결론을 위해서는 다음을 권장합니다.

```text
random split:              20 runs
volatility-stratified:     10 runs
volatility-held-out:       5 runs
```

stress split은 위 결론이 나온 후 추가로 수행할 수 있습니다 (선택 사항, 권장 5 runs).

---

## 11. Reporting Template

반복 실험 보고서는 다음 구조로 작성합니다.

```text
1. Symbol universe
2. Split family definitions
3. Fixed controls
4. Run table
5. Aggregate metric table
6. Shape token stability interpretation
7. Range bucket drift interpretation
8. Shape-range pair interpretation
9. KMeans baseline comparison
10. Final decision
```

Final decision은 다음 중 하나로 제한합니다.

```text
A. shape token vocabulary is stable enough for Phase 2
B. shape token vocabulary requires more symbols or different K
C. range bucket design should be revised
D. VQ-VAE should be replaced by KMeans for Phase 2 baseline
```

**Phase 2 진입 조건 (metric threshold → decision 매핑):**

| Condition | Decision |
|-----------|----------|
| random split `shape_test_train_l1` mean < 0.15 AND std < 0.05 AND max < 0.30 | **A** — Phase 2 진입 |
| random split mean ≥ 0.15 또는 max ≥ 0.30, BUT vol-held-out에서 shape drift < range drift | **B** — K 또는 symbol universe 재검토 |
| range_test_train_l1이 항상 높고 train range bucket이 특정 bucket에 집중 | **C** — quantile 수 또는 bucketizer 재설계 |
| VQ-VAE `shape_test_train_l1` > KMeans `shape_test_train_l1` across majority of runs | **D** — KMeans를 Phase 2 기본 모델로 채택 |

단, A/B/C/D는 상호 배타적이지 않습니다 (예: B + C 동시 가능).
최종 결정 전에 반드시 split family별 집계 결과를 기반으로 판단하세요.

---

## 12. Current Working Hypothesis

현재까지의 working hypothesis는 다음입니다.

```text
4D price-shape token은 symbol split 변화에도 비교적 안정적이다.
range bucket은 종목별 volatility profile을 반영하므로 split에 따라 달라진다.
(shape_token, range_bucket)은 정보량은 늘지만 pair distribution drift가 range drift에 민감하다.
KMeans는 여전히 강한 baseline이다.
```

이 hypothesis는 반복 split 실험으로 검증해야 하며, 아직 최종 결론이 아닙니다.
