# FinLabs Research

FinLabs Research는 시장 데이터를 단순한 price prediction target으로만 보지 않고, 학습 가능한 **market representation**으로 재구성하기 위한 연구 공간입니다.

현재 research track은 **Candlestick VQ-VAE Tokenizer**에서 시작하지만, 최종 주장을 한 번에 `market state modeling`으로 두지 않습니다. 연구 질문을 다음 3단계로 분리합니다.

```text
1. Shape Quantization
   비슷한 candle shape를 같은 token으로 묶을 수 있는가?

2. Sequential Dynamics
   shape token sequence의 transition이 구조를 가지는가?

3. Market State Modeling
   token 또는 token sequence가 미래 market dynamics를 설명하는가?
```

이 분리는 중요한 안전장치입니다. Phase 1에서 생성된 token은 우선 **shape token**입니다. Phase 2에서 transition structure가 확인되면 **state candidate**가 되고, Phase 3에서 미래 return/volatility/regime distribution과의 관계가 검증될 때에만 **market state representation**이라고 부를 수 있습니다.

## Research Frame

### Phase 1 — Shape Quantization

질문:

> 비슷한 OHLCV candle shape를 같은 learned token으로 묶을 수 있는가?

입력과 출력:

```text
OHLCV candle
→ 7D candle feature vector
→ VQ-VAE encoder
→ learned codebook
→ shape token
```

이 단계에서는 미래 예측을 평가하지 않습니다. 관심사는 tokenizer 자체가 candle morphology를 안정적으로 압축·양자화하는지입니다.

주요 평가:

- Reconstruction Loss
- Semantic Consistency
- Token Utilization
- Dead Code Ratio
- Compression vs Information Tradeoff
- deterministic inference: same checkpoint + same input → same token sequence

### Phase 2 — Sequential Dynamics

질문:

> shape token sequence가 시간축에서 non-random transition structure를 가지는가?

입력과 출력:

```text
shape token sequence
→ transition counts / probabilities
→ transition entropy
→ repeated sequence pattern candidates
```

이 단계는 token이 단순한 candle label을 넘어 sequence 안에서 구조를 가지는지 확인합니다. 하지만 아직 미래 시장 설명력까지 주장하지 않습니다.

주요 평가:

- 1-step transition counts
- transition probability
- transition entropy
- shuffled sequence baseline 대비 structure 차이
- symbol / market / timeframe별 transition stability

### Phase 3 — Market State Modeling

질문:

> token 또는 token sequence가 미래 market dynamics를 설명하는가?

입력과 출력:

```text
token_t 또는 token sequence_{t-n:t}
→ future return distribution
→ future volatility distribution
→ drawdown / rebound tendency
→ regime statistics
```

이 단계에서 처음으로 미래를 봅니다. 단, 목표는 trading signal 생성이 아니라 representation의 설명력 검증입니다.

주요 평가 후보:

- token별 forward return distribution
- token별 future volatility distribution
- token motif별 future drawdown / rebound tendency
- raw feature baseline 대비 설명력
- out-of-sample stability

Phase 3는 아직 구현하지 않습니다. 별도 spec이 생기기 전까지는 research planning scope에만 둡니다.

## Current Implementation Scope

현재 구현은 Phase 1 중심이며, Phase 2 metric primitive 일부만 제공합니다.

### In Scope

- `research/tokenizers/` package scaffold
- DuckDB `ohlcv_bars` 기반 OHLCV loading
- candle 1개 → 7D feature vector 변환
- VQ-VAE encoder + codebook 기반 shape tokenizer 학습
- time-based `train` / `val` / `test` split
- deterministic inference: 동일 input + 동일 checkpoint → 동일 token sequence
- Phase 1 metrics
  - Reconstruction Loss
  - Semantic Consistency
  - Token Utilization
  - Compression vs Information Tradeoff
- Phase 2 primitives
  - transition counts
  - transition probability
  - transition entropy

### Out of Scope

- Phase 3 Market State Modeling 구현
- downstream prediction model
- trading signal generation
- realtime tokenization service
- UI / dashboard / backtesting
- 신규 broker API endpoint 추가
- multi-market / multi-asset / multi-timeframe training

## Data Source

입력 데이터는 기존 `kis_cli/storage/`의 DuckDB warehouse를 재사용합니다.

대상 테이블:

```text
ohlcv_bars
```

주요 key:

```text
UNIQUE (market, symbol, interval, timestamp)
```

초기 학습 범위는 단순하게 제한합니다.

```text
single market × single asset × single timeframe
```

예상 초기 대상은 KIS 해외주식 일봉 데이터입니다. 국내주식 데이터는 향후 Kiwoom SDK에서 별도 수집될 예정입니다.

## Candle Feature Vector

하나의 candle은 7-dimensional feature vector로 변환됩니다.

| Feature | Description |
|---------|-------------|
| `body_ratio` | candle body length / total range |
| `upper_ratio` | upper wick length / total range |
| `lower_ratio` | lower wick length / total range |
| `close_position` | close price position within `[low, high]` |
| `range_return` | range-based return |
| `direction` | bullish / bearish / flat direction |
| `volume_state` | normalized volume state |

Feature extraction은 deterministic해야 합니다. 동일한 `CandleBar`와 동일한 volume context가 주어지면 항상 동일한 `FeatureVector`가 생성되어야 합니다.

경계 조건도 명시적으로 처리합니다.

- `high == low`인 candle
- `open == 0`인 candle
- volume standard deviation이 0인 경우

## VQ-VAE Shape Tokenizer

Tokenizer는 VQ-VAE 구조를 사용합니다.

```text
feature vector
→ encoder
→ z_e
→ vector quantizer
→ codebook index
→ z_q
→ decoder
→ reconstruction
```

핵심 구성요소:

- `Encoder`: 7D feature vector를 latent vector로 변환
- `Codebook`: `K`개의 learned embedding vector
- `VectorQuantizer`: encoder output과 가장 가까운 codebook entry 선택
- `Decoder`: quantized vector로부터 feature vector 복원
- `Tokenizer`: 학습된 encoder + codebook을 사용해 candle sequence를 shape token sequence로 변환

Codebook size `K`는 configurable해야 합니다. `K`가 작으면 compression은 강해지지만 information loss가 커질 수 있고, `K`가 크면 reconstruction은 좋아질 수 있으나 dead code가 늘어날 수 있습니다.

## Metrics by Research Phase

### Phase 1 Metrics — Shape Quantization

Phase 1 metric은 `research/tokenizers/shape_metrics.py`에 둡니다.

- `token_utilization(tokens, codebook_size=K)`
  - utilized code count
  - dead code count
  - dead code ratio
  - token histogram
  - token entropy
- `semantic_consistency(tokens, features)`
  - 같은 token에 배정된 candle들이 feature space에서 얼마나 일관적인지 측정

추가 후보:

- reconstruction loss
- compression vs information tradeoff curve
- token별 representative candle shape summary

### Phase 2 Metrics — Sequential Dynamics

Phase 2 metric은 `research/tokenizers/sequence_metrics.py`에 둡니다.

- `transition_counts(tokens)`
- `transition_report(tokens)`
  - transition probabilities
  - entropy by source token

추가 후보:

- shuffled baseline comparison
- n-step transition pattern
- transition matrix normalization
- market/symbol/timeframe별 transition stability

### Phase 3 Metrics — Market State Modeling

Phase 3 metric은 아직 구현하지 않습니다. 후보는 별도 spec에서 정의합니다.

- token별 forward return distribution
- token별 future volatility distribution
- motif별 future drawdown / rebound tendency
- raw feature baseline 대비 설명력
- out-of-sample stability

## Determinism

이 프로젝트는 deterministic inference를 중요하게 봅니다.

Acceptance target:

```text
same checkpoint + same input
→ same token sequence
```

학습 과정의 완전한 determinism은 hardware/backend에 따라 달라질 수 있으므로 best-effort로 다룹니다. 하지만 저장된 checkpoint를 load한 뒤 CPU inference에서 동일한 token sequence가 나오는 것은 반드시 보장해야 합니다.

## Initial Package Structure

```text
research/
├── README.md
├── AGENTS.md
└── tokenizers/
    ├── __init__.py
    ├── AGENTS.md
    ├── data.py              # CandleBar loading, DuckDB integration, time split
    ├── features.py          # CandleBar -> FeatureVector(7D)
    ├── model.py             # VectorQuantizer, VQVAE, model config
    ├── train.py             # training loop, checkpoint, history
    ├── encode.py            # Tokenizer facade, checkpoint loading, encode()
    ├── shape_metrics.py     # Phase 1 shape quantization metrics
    ├── sequence_metrics.py  # Phase 2 sequential dynamics metrics
    └── metrics.py           # backward-compatible metric exports
```

## Initial Public API

```python
from research.tokenizers import (
    CandleBar,
    FeatureVector,
    VQVAEConfig,
    TrainConfig,
    Tokenizer,
)
```

예상 사용 흐름:

```python
from research.tokenizers.data import load_candles, split_by_date
from research.tokenizers.features import build_volume_context, extract_features_batch
from research.tokenizers.train import TrainConfig, train
from research.tokenizers.encode import Tokenizer
from research.tokenizers.shape_metrics import token_utilization
from research.tokenizers.sequence_metrics import transition_report

candles = load_candles(
    warehouse_path="warehouse.duckdb",
    market="NASDAQ",
    symbol="AAPL",
    interval="1d",
)

split = split_by_date(
    candles,
    train_end="2025-12-31",
    val_end="2026-03-31",
)

volume_context = build_volume_context(split.train)
train_features = extract_features_batch(split.train, volume_context)

result = train(train_features, config=TrainConfig(...))
tokenizer = Tokenizer.load(result.checkpoint_path)
tokens = tokenizer.encode(split.test)

shape_report = token_utilization(tokens, codebook_size=32)
sequence_report = transition_report(tokens)
```

## Dependency Policy

ML dependency는 기본 dependency에 포함하지 않습니다.

예상 optional extras:

```bash
uv sync --extra tokenizers
```

또는:

```bash
pip install -e ".[tokenizers]"
```

예상 dependency:

- `torch`
- `numpy`

기본 FinLabs CLI/SDK 사용자는 무거운 ML dependency를 설치하지 않아도 됩니다.

## Testing Strategy

모든 테스트는 synthetic data와 `tmp_path` 기반 local warehouse를 사용합니다. 실제 broker API는 호출하지 않습니다.

예상 테스트 범위:

- `test_tokenizer_features.py`
  - 7D feature extraction
  - `high == low`, `open == 0` boundary case
  - deterministic feature output
- `test_tokenizer_data.py`
  - DuckDB `ohlcv_bars` loading
  - market filtering
  - timestamp ascending order
  - time-based split boundary
- `test_tokenizer_model.py`
  - VQ-VAE forward shape
  - gradient flow
- `test_tokenizer_train.py`
  - smoke training
  - checkpoint 생성
  - history JSONL 기록
- `test_tokenizer_shape_metrics.py`
  - codebook utilization
  - semantic consistency
- `test_tokenizer_sequence_metrics.py`
  - transition counts
  - transition report
- `test_tokenizer_determinism.py`
  - same checkpoint + same input → same tokens

`torch`가 설치되지 않은 환경에서는 tokenizer model/train/determinism test를 skip할 수 있도록 구성합니다.

## Research Phases

### Phase 1 — Shape Quantization

- `research/tokenizers/` package scaffold
- CandleBar data loading
- 7D feature extraction
- time-based split
- baseline VQ-VAE model
- tokenizer training / checkpoint / encode
- shape metrics

### Phase 2 — Sequential Dynamics

- transition counts
- transition probabilities
- transition entropy
- shuffled baseline comparison
- n-step transition structure

### Phase 3 — Market State Modeling

- token-level future return distribution
- token-level future volatility distribution
- motif-level future dynamics
- baseline comparison against raw features
- out-of-sample stability

Phase 3는 아직 명확히 정의하지 않습니다. Shape Quantization과 Sequential Dynamics가 안정화된 뒤 별도 spec으로 설계합니다.

## Non-Assumptions

이 연구는 financial markets가 natural language와 동일한 구조를 가진다고 가정하지 않습니다.

또한 Phase 1의 shape token이 곧바로 market state라고 가정하지 않습니다. 먼저 shape quantization을 검증하고, 그 다음 sequential dynamics와 future market dynamics 설명력을 단계적으로 검증합니다.

## Status

Foundation scaffold implemented. Current terminology is phase-aware: Phase 1 outputs are shape tokens; Market State Modeling remains a future research phase.
