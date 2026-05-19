# FinLabs Research

FinLabs Research는 시장 데이터를 단순한 price prediction target으로만 보지 않고, 학습 가능한 **market representation**으로 재구성하기 위한 연구 공간입니다.

현재 research track은 candlestick을 discrete token으로 양자화하는 실험에서 시작합니다. 다만 최종 주장을 처음부터 `market state modeling`으로 두지 않고, 다음 3단계로 분리합니다.

```text
1. Shape Quantization
   비슷한 candle shape를 같은 token으로 묶을 수 있는가?

2. Sequential Dynamics
   token sequence의 transition이 구조를 가지는가?

3. Market State Modeling
   token 또는 token sequence가 미래 market dynamics를 설명하는가?
```

이 분리는 중요한 안전장치입니다.

- Phase 1의 산출물은 **shape token**입니다.
- Phase 2에서 전이 구조가 확인되면 **state candidate**로 볼 수 있습니다.
- Phase 3에서 미래 return / volatility / regime distribution과의 관계가 검증될 때에만 **market state representation**이라고 부를 수 있습니다.

따라서 현재 연구 결과를 trading signal, 매수/매도 조건, 확정적 market regime으로 해석하지 않습니다.

---

## Current Status

현재 상태는 다음과 같습니다.

```text
Phase 1A — Price-shape only quantization       완료
Phase 1B — Shape token + range bucket          반복 split 검증 완료
Phase 2  — Sequential Dynamics                 계획 수립 완료, 구현 전
Phase 3  — Market State Modeling               미구현 / future scope
```

Phase 1B 반복 실험 결과는 다음 위치에 정리되어 있습니다.

```text
research/notebooks/01_shape_quantization/summaries/SUMMARY.md
research/notebooks/01_shape_quantization/summaries/summary.csv
```

Phase 1B 결과 요약:

| Split family | Runs | shape test-train L1 mean | range test-train L1 mean | pair test-train L1 mean |
|---|---:|---:|---:|---:|
| `random` | 20 | 0.091 | 0.249 | 0.292 |
| `vol_strat` | 10 | 0.096 | 0.105 | 0.164 |
| `vol_holdout` | 5 | 0.078 | 0.918 | 0.937 |

해석:

```text
shape_token은 symbol split과 volatility holdout에서도 안정적입니다.
range_bucket은 volatility context를 별도로 포착합니다.
pair drift는 range drift를 강하게 반영합니다.
```

현재 판단:

> **Phase 1B는 반복 split 기준에서 통과로 판단합니다.**
>
> 다음 단계는 `02_sequential_dynamics`에서 token transition structure를 검증하는 것입니다.

---

## Research Frame

## Phase 1 — Shape Quantization

질문:

> 비슷한 candle shape를 같은 learned token으로 묶을 수 있는가?

Phase 1은 두 단계로 진행했습니다.

### Phase 1A — Price-shape only

입력:

```text
OHLC candle
→ 4D price-shape feature
→ VQ-VAE encoder
→ learned codebook
→ shape_token
```

Phase 1A의 권장 feature set은 다음입니다.

| Feature | 의미 |
|---|---|
| `signed_body_ratio` | 전체 range 대비 body 비율에 bullish / bearish 방향을 결합한 값 |
| `upper_ratio` | 전체 range 대비 upper wick 비율 |
| `lower_ratio` | 전체 range 대비 lower wick 비율 |
| `body_center_location` | candle body 중심이 `[low, high]` 구간 안에서 어디에 위치하는지 나타낸 값 |

의도적으로 제외한 정보:

```text
volume
absolute price level
range scale / volatility scale
future return
trading label
```

목표는 순수하게 candle의 상대적 price-shape vocabulary를 학습하는 것입니다.

### Phase 1B — Shape token + range bucket

초기 ablation에서는 Phase 1A의 4D feature에 `range_scale_z`를 encoder input으로 직접 넣었습니다.

```text
price-shape feature + range_scale_z
→ VQ-VAE
→ shape-scale token
```

하지만 이 방식은 range scale이 token assignment를 강하게 지배하여 shape vocabulary의 의미가 흐려졌습니다.

따라서 Phase 1B의 채택 설계는 다음입니다.

```text
shape_token  = 4D price-shape only VQ-VAE token
range_bucket = train quantile 기반 log_range_pct bucket
final rep    = (shape_token, range_bucket)
```

이 설계의 의도는 다음입니다.

```text
shape는 shape_token으로 표현
volatility context는 range_bucket으로 분리
pair representation은 (shape_token, range_bucket)으로 관찰
```

Phase 1B 반복 split 검증은 다음 세 family로 수행했습니다.

| Split family | 목적 |
|---|---|
| `random` | 일반적인 held-out symbol generalization 확인 |
| `vol_strat` | volatility 구성을 train/val/test에 균형 있게 배치 |
| `vol_holdout` | high-volatility symbols를 train에서 제외한 stress test |

결론:

```text
shape_token + separate range_bucket 설계는 유지합니다.
```

단, VQ-VAE가 KMeans보다 명확히 우월하다는 결론은 아직 없습니다. Phase 2에서도 KMeans baseline은 유지합니다.

---

## Phase 2 — Sequential Dynamics

질문:

> token sequence가 시간축에서 non-random transition structure를 가지는가?

Phase 2의 입력은 Phase 1B의 representation입니다.

```text
shape_token sequence
range_bucket sequence
(shape_token, range_bucket) pair sequence
```

Phase 2에서 확인할 것은 다음입니다.

```text
shape_token_t → shape_token_{t+1}
range_bucket_t → range_bucket_{t+1}
pair_token_t → pair_token_{t+1}
```

주요 평가 후보:

- transition counts
- transition probability matrix
- transition entropy
- self-transition rate
- mutual information proxy
- marginal baseline vs first-order Markov baseline
- shuffled sequence baseline
- split family별 transition stability
- VQ-VAE token vs KMeans token transition 비교

Phase 2 계획 문서:

```text
research/notebooks/02_sequential_dynamics/README.md
```

Phase 2에서 아직 주장하지 않는 것:

```text
이 token은 market state다.
이 sequence는 future return을 예측한다.
이 transition은 trading signal이다.
```

Phase 2의 목표는 더 제한적입니다.

```text
token sequence에 반복 가능한 전이 구조가 있는지 검증한다.
```

---

## Phase 3 — Market State Modeling

질문:

> token 또는 token sequence가 미래 market dynamics를 설명하는가?

Phase 3에서 처음으로 미래 정보를 평가합니다.

입력과 출력 후보:

```text
token_t 또는 token sequence_{t-n:t}
→ future return distribution
→ future volatility distribution
→ drawdown / rebound tendency
→ regime statistics
```

주요 평가 후보:

- token별 forward return distribution
- token별 future volatility distribution
- token motif별 future drawdown / rebound tendency
- raw feature baseline 대비 설명력
- out-of-sample stability

Phase 3는 아직 구현하지 않습니다. Shape Quantization과 Sequential Dynamics가 안정화된 뒤 별도 spec으로 설계합니다.

---

## Current Repository Structure

```text
research/
├── README.md
├── AGENTS.md
├── notebooks/
│   ├── README.md
│   ├── 01_shape_quantization/
│   │   ├── 00_smoke.ipynb
│   │   ├── 01_phase_1a_price_shape_only.ipynb
│   │   ├── 02_phase_1b_shape_plus_range_scale.ipynb
│   │   ├── 03_phase_1b_shape_token_plus_range_bucket.ipynb
│   │   ├── 04_symbol_split_protocol.md
│   │   ├── README.md
│   │   ├── results/
│   │   ├── runs/
│   │   ├── scripts/
│   │   └── summaries/
│   └── 02_sequential_dynamics/
│       └── README.md
└── tokenizers/
    ├── __init__.py
    ├── AGENTS.md
    ├── data.py
    ├── features.py
    ├── model.py
    ├── train.py
    ├── encode.py
    ├── shape_metrics.py
    ├── sequence_metrics.py
    └── metrics.py
```

---

## Notebook Workflow

현재 주요 notebook은 다음입니다.

| Notebook / Document | Phase | Purpose |
|---|---|---|
| `01_shape_quantization/00_smoke.ipynb` | Smoke | 초기 단일 symbol tokenizer smoke test |
| `01_shape_quantization/01_phase_1a_price_shape_only.ipynb` | Phase 1A | 4D price-shape only VQ-VAE / KMeans 비교 |
| `01_shape_quantization/02_phase_1b_shape_plus_range_scale.ipynb` | Phase 1B ablation | `range_scale_z`를 encoder input에 직접 넣는 방식 검증 |
| `01_shape_quantization/03_phase_1b_shape_token_plus_range_bucket.ipynb` | Phase 1B | `shape_token + range_bucket` revised design |
| `01_shape_quantization/04_symbol_split_protocol.md` | Phase 1B protocol | repeated split 검증 프로토콜 |
| `02_sequential_dynamics/README.md` | Phase 2 plan | Sequential Dynamics 계획 |

실행 전 optional dependency를 설치합니다.

```bash
uv sync --extra tokenizers
```

Jupyter kernel이 필요하면 다음 명령을 사용합니다.

```bash
uv run --extra tokenizers --with ipykernel python -m ipykernel install --user --name finlabs-tokenizers --display-name "FinLabs Tokenizers"
```

노트북은 실제 broker API를 호출하지 않습니다. 이미 수집되어 DuckDB warehouse에 저장된 market data를 읽습니다.

---

## Scripts and Summaries

Phase 1B 반복 실험 runner:

```text
research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py
```

예시:

```bash
uv run python research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py \
  --split-family random \
  --n-runs 20 \
  --seed-start 0
```

집계 스크립트:

```text
research/notebooks/01_shape_quantization/scripts/collect_metrics.py
```

집계 결과:

```text
research/notebooks/01_shape_quantization/summaries/summary.csv
research/notebooks/01_shape_quantization/summaries/summary_random.csv
research/notebooks/01_shape_quantization/summaries/summary_vol_strat.csv
research/notebooks/01_shape_quantization/summaries/summary_vol_holdout.csv
research/notebooks/01_shape_quantization/summaries/SUMMARY.md
```

---

## Data Source

입력 데이터는 기존 `kis_cli/storage/`의 DuckDB warehouse를 재사용합니다.

대상 테이블:

```text
ohlcv_bars             # daily / weekly / monthly / yearly OHLCV
overseas_minute_bars   # overseas minute OHLCV
```

현재 Shape Quantization 반복 실험은 해외주식 minute data를 중심으로 진행했습니다.

```text
market: NASDAQ
interval: 1m
max candles per symbol: 12,000
```

research code는 broker API를 직접 호출하지 않습니다.

---

## Metrics by Research Phase

### Phase 1 Metrics — Shape Quantization

Phase 1 metric은 `research/tokenizers/shape_metrics.py` 또는 notebook-local metric helper에서 계산합니다.

주요 지표:

- token utilization
- dead token ratio
- token entropy
- semantic consistency
- reconstruction MSE
- split distribution drift
  - `shape_val_train_l1`
  - `shape_test_train_l1`
- KMeans baseline comparison

Phase 1B 추가 지표:

- `range_val_train_l1`
- `range_test_train_l1`
- `pair_val_train_l1`
- `pair_test_train_l1`

### Phase 2 Metrics — Sequential Dynamics

Phase 2 metric은 `research/tokenizers/sequence_metrics.py`를 확장해서 관리합니다.

현재 primitive:

- `transition_counts(tokens)`
- `transition_report(tokens)`

확장 후보:

- transition matrix
- row-normalized transition probability
- transition entropy
- weighted transition L1
- self-transition rate
- mutual information proxy
- marginal baseline NLL
- first-order Markov NLL
- shuffled baseline comparison

### Phase 3 Metrics — Market State Modeling

Phase 3 metric은 아직 구현하지 않습니다. 후보는 별도 spec에서 정의합니다.

---

## Determinism and Leakage Control

Deterministic inference target:

```text
same checkpoint + same input → same token sequence
```

학습 과정의 완전한 determinism은 hardware/backend에 따라 달라질 수 있으므로 best-effort로 다룹니다. 하지만 저장된 checkpoint를 load한 뒤 CPU inference에서 동일한 token sequence가 나오는 것은 보장해야 합니다.

Leakage control:

```text
VQ-VAE는 train candles로만 학습
RangeBucketizer threshold도 train candles로만 fit
val/test는 train-derived statistics로만 transform
symbol boundary를 넘는 transition 생성 금지
future token/return을 Phase 1/2 feature로 사용 금지
```

---

## Dependency Policy

ML dependency는 기본 dependency에 포함하지 않습니다.

```bash
uv sync --extra tokenizers
```

예상 dependency:

- `torch`
- `numpy`
- `matplotlib`
- `scikit-learn`

기본 FinLabs CLI/SDK 사용자는 무거운 ML dependency를 설치하지 않아도 됩니다.

---

## Testing Strategy

모든 테스트는 synthetic data와 `tmp_path` 기반 local warehouse를 사용합니다. 실제 broker API는 호출하지 않습니다.

예상 테스트 범위:

- feature extraction boundary case
- DuckDB loading order and filtering
- VQ-VAE smoke training
- checkpoint loading / deterministic inference
- shape metric calculation
- sequence metric calculation
- repeated split runner dry-run behavior

`torch`가 설치되지 않은 환경에서는 tokenizer model/train/determinism test를 skip할 수 있도록 구성합니다.

---

## Non-Assumptions

이 연구는 financial markets가 natural language와 동일한 구조를 가진다고 가정하지 않습니다.

또한 Phase 1의 shape token이 곧바로 market state라고 가정하지 않습니다. 먼저 shape quantization을 검증하고, 그 다음 sequential dynamics와 future market dynamics 설명력을 단계적으로 검증합니다.
