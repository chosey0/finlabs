# 01 — Shape Quantization

이 폴더는 FinLabs Research의 첫 번째 연구 단계인 **Shape Quantization** 실험을 정리합니다.

핵심 질문은 다음 하나입니다.

> **다양한 종목에서 반복적으로 나타나는 candle price-shape를 같은 learned token으로 묶을 수 있는가?**

이 단계의 산출물은 **market state**가 아니라 **shape token**입니다.  
미래 수익률, trading signal, backtest, market regime 해석은 이 폴더의 직접 목표가 아닙니다.

---

## Research Position

전체 연구 흐름은 다음과 같이 분리합니다.

```text
1. Shape Quantization
   비슷한 candle shape를 같은 token으로 묶을 수 있는가?

2. Sequential Dynamics
   shape token sequence의 transition이 구조를 가지는가?

3. Market State Modeling
   token 또는 token sequence가 미래 market dynamics를 설명하는가?
```

이 폴더는 **1. Shape Quantization**만 다룹니다.

---

## Phase 1A — Price-Shape Only Quantization

첫 실험은 가장 단순하고 이론적으로 깨끗한 설정에서 시작합니다.

```text
OHLC candle
→ price-shape only feature
→ VQ-VAE encoder
→ learned codebook
→ discrete shape token
```

### 목표

VQ-VAE가 price-shape only feature의 잠재표현을 학습하고, 이를 codebook을 통해 안정적인 discrete token으로 양자화할 수 있는지 확인합니다.

단, 목표는 특정 종목에 과적합된 local token이 아니라 여러 종목에서 공유 가능한 **common candle shape vocabulary**를 만드는 것입니다.

---

## Phase 1A Feature Set

Phase 1A에서는 candle의 가격 형태만 사용합니다. 기존의 `close_position`과 `direction`은 분리하지 않고, 몸통의 방향성과 위치를 더 직접적으로 표현하는 feature로 재구성합니다.

권장 feature set은 다음 4D입니다.

| Feature | 의미 |
|---------|------|
| `signed_body_ratio` | 전체 range 대비 candle body 비율에 bullish / bearish 방향을 결합한 값 |
| `upper_ratio` | 전체 range 대비 upper wick 비율 |
| `lower_ratio` | 전체 range 대비 lower wick 비율 |
| `body_center_location` | candle body 중심이 `[low, high]` 구간 안에서 어디에 위치하는지 나타낸 값 |

### Feature Intuition

```text
signed_body_ratio
  > 0: bullish body
  < 0: bearish body
  ≈ 0: doji / flat body

upper_ratio
  높을수록 긴 upper wick

lower_ratio
  높을수록 긴 lower wick

body_center_location
  몸통이 range 상단, 중앙, 하단 중 어디에 놓였는지 표현
```

이 4D feature는 다음 정보를 직접 표현합니다.

```text
큰 양봉
큰 음봉
doji
긴 upper wick
긴 lower wick
상단 body
하단 body
```

### 의도적으로 제외하는 정보

첫 실험에서는 다음 정보를 제외합니다.

| Excluded | 제외 이유 |
|----------|-----------|
| `volume_state` | volume은 candle shape가 아니라 context이므로 price-shape token을 흐릴 수 있음 |
| `range_return` | range 크기는 shape라기보다 volatility / scale 정보에 가까움 |
| raw `open`, `high`, `low`, `close` | 가격 수준과 종목별 scale 차이가 섞일 수 있음 |
| future return | Phase 3에서 검증할 대상이며 Phase 1에는 미래 정보를 넣지 않음 |
| trading label | Shape Quantization의 목표가 supervised prediction이 아니기 때문 |

즉 Phase 1A의 token은 다음과 같이 해석해야 합니다.

```text
price-shape token
```

아직 다음처럼 해석하면 안 됩니다.

```text
market state token
trading signal
future return predictor
```

---

## Why Price-Shape Only First?

처음부터 volume, volatility scale, session effect를 모두 넣으면 token의 의미가 섞입니다.

예를 들어 같은 모양의 candle이라도 거래량이 다르다는 이유로 다른 token에 배정될 수 있습니다. 반대로 모양은 다른데 volume 상태가 비슷해서 같은 token이 될 수도 있습니다.

따라서 첫 실험에서는 의도적으로 질문을 좁힙니다.

> **가격 형태만 보고도 비슷한 candle을 같은 token으로 묶을 수 있는가?**

이 질문에 답한 뒤에야 다음 확장 실험으로 넘어갑니다.

```text
Phase 1A: price-shape only
Phase 1B: price-shape + range / volatility scale
Phase 1C: price-shape + volume context
Phase 1D: price-shape + market session context
```

---

## Phase 1B — Shape + Range Scale Quantization

Phase 1B는 Phase 1A의 price-shape only token에 candle의 range / volatility scale 정보를 추가로 연결합니다.

핵심 질문은 다음과 같습니다.

> **price-shape token에 range scale 정보를 추가하면 더 풍부하고 안정적인 shape-scale token vocabulary를 만들 수 있는가?**

Phase 1A가 candle의 상대적 모양만 본다면, Phase 1B는 같은 모양이라도 작은 range에서 발생했는지, 큰 range에서 발생했는지를 함께 구분합니다.

초기 ablation에서는 `range_scale_z`를 VQ-VAE encoder 입력 feature에 직접 추가했습니다.

```text
OHLC candle
→ price-shape feature
→ range scale feature
→ VQ-VAE encoder
→ learned codebook
→ discrete shape-scale token
```

하지만 `runs/phase_1b_shape_range_NASDAQ_1m_k12` 결과에서는 range scale이 token assignment를 강하게 지배했고, held-out symbol token distribution이 Phase 1A보다 크게 불안정해졌습니다.

따라서 Phase 1B의 기본 방향은 다음 revised design으로 변경합니다.

```text
shape_token  = 4D price-shape only feature에서 학습
range_bucket = train range distribution 기준 별도 bucketizer로 계산

final representation = (shape_token, range_bucket)
```

이 방식은 shape vocabulary의 안정성을 유지하면서 range / volatility context를 잃지 않기 위한 설계입니다.

### Phase 1B Feature Set

초기 ablation의 5D encoder-input feature set은 다음과 같습니다.

| Feature | 의미 |
|---------|------|
| `signed_body_ratio` | 전체 range 대비 candle body 비율에 bullish / bearish 방향을 결합한 값 |
| `upper_ratio` | 전체 range 대비 upper wick 비율 |
| `lower_ratio` | 전체 range 대비 lower wick 비율 |
| `body_center_location` | candle body 중심이 `[low, high]` 구간 안에서 어디에 위치하는지 나타낸 값 |
| `range_scale_z` | candle range가 train distribution 대비 얼마나 큰지 나타내는 z-score |

`range_scale_z`는 raw 가격 차이를 그대로 쓰지 않습니다. 종목별 가격 수준 차이가 token을 지배하지 않도록 range를 가격 대비 비율로 바꾼 뒤, train split 기준 통계로 정규화합니다.

```text
range_pct = (high - low) / reference_price
log_range_pct = log1p(range_pct)
range_scale_z = train log_range_pct 기준 z-score
```

revised design에서는 `range_scale_z`를 encoder 입력으로 쓰지 않고, train quantile 기준 `range_bucket`으로 분리합니다.

예시 bucket:

```text
very_low
low
normal
high
very_high
extreme
```

### Leakage Control

Phase 1B에서 중요한 점은 range scale normalization이 미래 정보를 사용하지 않아야 한다는 것입니다.

따라서 notebook은 다음 원칙을 따릅니다.

```text
train candles로만 range scaler fit
val/test candles는 train scaler로 transform
held-out symbol의 test 분포를 scaler fit에 사용하지 않음
```

range bucket 방식에서도 동일합니다.

```text
train candles로만 bucket threshold fit
val/test candles는 train thresholds로 bucket assignment
```

### Phase 1A와 비교할 질문

Phase 1B 결과는 단독으로 해석하지 않고 Phase 1A와 비교해야 합니다.

- range scale을 추가했을 때 token utilization이 개선되는가?
- held-out symbol에서 token distribution이 더 안정적인가, 아니면 더 symbol-specific해지는가?
- `range_bucket`이 실제로 low-range / high-range candle을 구분하는가?
- KMeans baseline과 비교했을 때 VQ-VAE를 쓸 이유가 있는가?
- price-shape vocabulary의 해석 가능성을 유지하면서 더 많은 정보를 담는가?

Phase 1B의 token은 다음처럼 부를 수 있습니다.

```text
shape token + range bucket
```

아직 다음처럼 해석하면 안 됩니다.

```text
market state token
future return predictor
trading signal
```

---

## Dataset Direction

기존 smoke test는 단일 market, 단일 symbol, 단일 timeframe으로 시작했습니다.

```text
single market × single symbol × single timeframe
```

이 설정은 코드가 정상 동작하는지 확인하는 smoke test로는 충분하지만, 연구 결론을 내리기에는 약합니다. 종목마다 candle 분포가 다르기 때문에 단일 종목 tokenizer는 특정 종목의 local distribution에 과적합될 수 있습니다.

Shape Quantization의 본 실험 데이터셋은 다음 방향으로 설계합니다.

```text
single market × multiple symbols × single timeframe
```

예시:

```text
NASDAQ × [AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, AMD, INTC, RKLB] × 1m
```

목표는 다음과 같습니다.

> 여러 종목에서 공통적으로 나타나는 price-shape pattern을 공유 token vocabulary로 학습한다.

### Dataset Rules

- **market은 섞지 않습니다.**
  - NASDAQ, NYSE, KRX 등은 시장 구조와 microstructure가 다르므로 하나의 실험에서는 하나의 market만 사용합니다.
- **timeframe은 섞지 않습니다.**
  - `1m`, `5m`, `1d` candle은 의미가 다르므로 하나의 실험에서는 하나의 timeframe만 사용합니다.
- **symbol은 여러 개 사용합니다.**
  - 단일 종목 전용 token이 아니라 공통 candle shape vocabulary를 학습하기 위함입니다.
- **symbol-balanced sampling을 우선합니다.**
  - 데이터 수가 많은 종목이 전체 학습을 지배하지 않도록 종목별 sample 수를 제한하거나 batch sampling을 균형 있게 구성합니다.

초기 notebook에서는 구현 복잡도를 낮추기 위해 다음 방식부터 시작합니다.

```text
MAX_CANDLES_PER_SYMBOL = N
각 symbol에서 최대 N개 candle만 사용
```

---

## Split Strategy

multi-symbol dataset에서는 time split과 symbol split을 구분해야 합니다.

### 1. Time Split

각 종목 내부에서 시간 순서를 유지한 채 나눕니다.

```text
AAPL: train 70% → val 15% → test 15%
MSFT: train 70% → val 15% → test 15%
...
```

이 split은 같은 종목의 미래 구간에서도 tokenization이 안정적인지 확인합니다.

### 2. Held-out Symbol Split

종목 자체를 train / val / test로 나눕니다.

```text
train symbols: AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL
val symbols:   AMD
test symbols:  INTC, RKLB
```

(Phase 1A k12 run 실제 split 기준. `auto_symbol_split`으로 70/15/15 비율 적용.)

이 split은 학습에 사용하지 않은 종목에서도 token vocabulary가 작동하는지 확인합니다.

Shape Quantization에서는 최종적으로 두 관점을 모두 확인해야 합니다.

```text
primary: held-out symbol generalization
secondary: within-symbol time generalization
```

---

## Notebook Plan

이 폴더에는 Phase별 notebook을 추가합니다.

권장 파일명은 다음과 같습니다.

```text
01_phase_1a_price_shape_only.ipynb
02_phase_1b_shape_plus_range_scale.ipynb              # range를 encoder input에 직접 추가한 ablation
02_phase_1b_shape_token_plus_range_bucket.ipynb       # revised design: shape token + separate range bucket
03_phase_1c_shape_plus_volume_context.ipynb
04_phase_1d_shape_plus_session_context.ipynb
```

현재 작성된 notebook:

```text
01_phase_1a_price_shape_only.ipynb
02_phase_1b_shape_plus_range_scale.ipynb
02_phase_1b_shape_token_plus_range_bucket.ipynb
```

---

## Phase 1A Evaluation

Phase 1A에서 확인할 것은 예측력이 아니라 tokenizer의 안정성과 일반화 가능성입니다.

### Global Checks

- `token_utilization`
  - codebook 중 실제 사용된 token 수
  - dead token 비율
  - token histogram
  - token entropy
- `semantic_consistency`
  - 같은 token에 속한 candle feature가 서로 가까운지
- `prototype candle`
  - token별 평균 shape가 사람이 보기에도 구분되는지
- `deterministic inference`
  - 같은 checkpoint와 같은 input이 항상 같은 token sequence를 만드는지

### Per-symbol Checks

multi-symbol dataset에서는 전체 metric만 보면 안 됩니다. 종목별 metric을 함께 봐야 합니다.

- per-symbol token utilization
- per-symbol token histogram
- per-symbol semantic consistency
- held-out symbol token distribution
- 특정 token이 특정 symbol에만 과도하게 의존하는지

중요한 질문:

```text
이 token은 공통 shape token인가,
아니면 특정 symbol 전용 token인가?
```

### Visual Diagnostics

각 notebook은 가능하면 figure를 다음 위치에 저장합니다.

```text
RUN_DIR / "figures"
```

권장 figure:

```text
01_global_token_ratio_histogram.png
02_per_symbol_token_heatmap.png
03_per_symbol_token_ratio_chart.png
04_split_token_ratio_difference.png
05_mean_feature_heatmap.png
06_prototype_candles.png
07_feature_scatter.png
08_vqvae_vs_kmeans_histogram.png
```

---

## Baseline Requirement

VQ-VAE만으로 결론을 내리면 안 됩니다. 입력이 저차원 handcrafted feature이기 때문에 단순 clustering baseline과 비교해야 합니다.

최소 baseline:

```text
KMeans on price-shape features
```

가능하면 추가 baseline:

```text
PCA + KMeans
Gaussian Mixture Model
MiniBatchKMeans
```

VQ-VAE가 baseline보다 뚜렷한 장점이 없다면, Phase 1A에서는 더 단순한 방법을 우선해야 합니다.

---

## Interpretation Rules

Phase 1A 결과는 다음 수준까지만 주장합니다.

가능한 주장:

```text
비슷한 price-shape candle을 discrete token으로 묶는 후보를 만들었다.
token별 평균 price-shape pattern이 구분된다.
여러 symbol에서 공유되는 candle shape vocabulary 후보를 만들었다.
held-out symbol에서도 token distribution이 크게 무너지지 않았다.
특정 K에서 token collapse가 덜하다.
```

아직 하면 안 되는 주장:

```text
market state를 발견했다.
미래 수익률을 예측한다.
매매 신호로 사용할 수 있다.
```

---

## Recommended Experiment Order

```text
1. single-symbol smoke test
   - 기존 notebook 수준
   - 코드와 데이터 파이프라인 확인용

2. multi-symbol shared vocabulary
   - single market × multiple symbols × single timeframe
   - symbol-balanced sampling

3. held-out symbol validation
   - train에 없는 symbol에서도 token vocabulary가 유지되는지 확인

4. K comparison
   - K = 4, 8, 16, 32 등 비교

5. baseline comparison
   - VQ-VAE vs KMeans
```

---

## Current Step

완료된 실험:

```text
Phase 1A (완료)
  runs/phase_1a_price_shape_NASDAQ_1m_k8
  runs/phase_1a_price_shape_NASDAQ_1m_k12   ← K=12 best (dead token 없음)
  runs/phase_1a_price_shape_NASDAQ_1m_k16
  결과: 01_phase_1a_result.md

Phase 1B ablation (완료 — held-out 불안정, deprecated)
  runs/deprecated/phase_1b_shape_range_NASDAQ_1m_k12
  runs/deprecated/phase_1b_shape_range_NASDAQ_1m_k16
  - range_scale_z를 encoder input에 직접 넣은 실험
  - 결과: val-train L1 = 0.8648 (shape token 안정성 크게 악화)

Phase 1B revised (완료)
  runs/phase_1b_shape_token_range_bucket_NASDAQ_1m_k12    (split_family: manual_stress)
  runs/phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_a  (split_family: manual_stress)
  runs/phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_b  (split_family: manual_stress)
  - shape token + separate range bucket
  - shape test-train L1: 0.060 ~ 0.113 (Phase 1A 수준 회복)
  결과: 02_phase_1b_result.md
```

다음 단계:

```text
03_symbol_split_protocol.md에 따라 반복 symbol split 실험 수행
  - random split:           최소 5 runs
  - volatility-stratified:  최소 3 runs
  - volatility-held-out:    최소 2 runs

집계:
  python research/notebooks/01_shape_quantization/collect_metrics.py
```

```text
Phase 1A: shape only
Phase 1B ablation: shape + range scale as encoder input (deprecated)
Phase 1B revised: shape token + separate range bucket  ← current
```
