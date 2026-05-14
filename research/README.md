# FinLabs Research

FinLabs Research는 시장 데이터를 단순한 price prediction target으로만 보지 않고, 학습 가능한 **market representation**으로 재구성하기 위한 연구 공간입니다.

현재 research track의 첫 번째 목표는 **Candlestick VQ-VAE Tokenizer**입니다. OHLCV candlestick sequence를 7-dimensional feature vector로 변환한 뒤, VQ-VAE의 learned codebook을 통해 각 candle을 discrete token으로 매핑합니다.

```text
OHLCV candle
→ 7D candle feature vector
→ VQ-VAE encoder
→ learned codebook
→ discrete market state token
```

이 tokenizer는 시장을 continuous signal이 아니라 reusable discrete latent states의 sequence로 다루기 위한 foundation layer입니다.

## Research Goal

Candlestick VQ-VAE Tokenizer의 목표는 다음과 같습니다.

> 캔들스틱(OHLCV) 시계열을 학습 가능한 discrete state space로 압축·추상화한다.

구체적으로는 다음 과정을 구현합니다.

```text
1 candle
→ FeatureVector(7D)
→ encoder
→ vector quantization
→ codebook index
→ token sequence
```

여기서 하나의 token은 rule-based label이 아니라, VQ-VAE가 학습한 codebook의 index입니다. 즉, token은 특정 candlestick feature pattern을 대표하는 learned discrete latent state입니다.

## Scope

### In Scope

- `research/tokenizers/` 패키지 설계 및 구현
- DuckDB `ohlcv_bars` 기반 OHLCV loading
- candle 1개 → 7D feature vector 변환
- VQ-VAE encoder + codebook 기반 tokenizer 학습
- time-based `train` / `val` / `test` split
- deterministic inference: 동일 input + 동일 checkpoint → 동일 token sequence
- tokenizer quality metrics
  - Reconstruction loss
  - Semantic Consistency
  - Token Utilization
  - Transition Structure
  - Cross-market Stability
  - Compression vs Information Tradeoff

### Out of Scope

- Analysis component 전체 설계
- multi-market / multi-asset / multi-timeframe training
- downstream prediction model
- trading signal generation
- realtime tokenization service
- UI / dashboard / backtesting
- 신규 broker API endpoint 추가

Analysis는 이번 단계에서는 deferred 상태입니다. Tokenizer를 먼저 독립적으로 설계하고, token sequence 기반 analysis는 후속 design phase에서 다룹니다.

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

1단계 학습 범위는 단순하게 제한합니다.

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

## VQ-VAE Tokenizer

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
- `Tokenizer`: 학습된 encoder + codebook을 사용해 candle sequence를 token sequence로 변환

Codebook size `K`는 configurable해야 합니다. `K`가 작으면 compression은 강해지지만 information loss가 커질 수 있고, `K`가 크면 reconstruction은 좋아질 수 있으나 dead code가 늘어날 수 있습니다.

## Evaluation Metrics

Tokenizer의 성공 여부는 단일 metric으로 판단하지 않습니다. 다음 관점들을 함께 봅니다.

### Reconstruction Loss

입력 feature vector와 decoder reconstruction 사이의 MSE를 측정합니다.

```text
lower reconstruction loss
= better information preservation
```

### Semantic Consistency

같은 token에 배정된 candle들이 feature space에서 얼마나 일관된 분포를 가지는지 측정합니다.

예시 metric:

```text
intra-cluster variance
inter-cluster variance
intra/inter ratio
```

### Token Utilization

Codebook이 얼마나 고르게 사용되는지 확인합니다.

주요 지표:

- utilized code count
- dead code count
- dead code ratio
- token histogram
- token entropy

### Transition Structure

Token sequence의 1-step transition matrix를 계산합니다.

```text
token_t → token_t+1
```

이를 통해 학습된 state들이 의미 있는 transition dynamics를 가지는지 확인합니다.

### Cross-market Stability

학습에 사용하지 않은 market/asset에 tokenizer를 적용했을 때 token distribution이 얼마나 안정적으로 유지되는지 측정합니다.

기본 divergence metric은 JS divergence를 사용합니다.

```text
reference token distribution
vs
out-of-sample token distribution
```

### Compression vs Information Tradeoff

여러 codebook size `K`에 대해 다음 값을 비교합니다.

- reconstruction loss
- dead code ratio
- token entropy
- utilized code ratio

목표는 하나의 최적값을 고정하는 것이 아니라, compression과 information preservation 사이의 tradeoff curve를 관찰하는 것입니다.

## Determinism

이 프로젝트는 deterministic inference를 중요하게 봅니다.

Acceptance target:

```text
same checkpoint + same input
→ same token sequence
```

학습 과정의 완전한 determinism은 hardware/backend에 따라 달라질 수 있으므로 best-effort로 다룹니다. 하지만 저장된 checkpoint를 load한 뒤 CPU inference에서 동일한 token sequence가 나오는 것은 반드시 보장해야 합니다.

## Planned Package Structure

```text
research/
├── README.md
├── AGENTS.md
└── tokenizers/
    ├── __init__.py
    ├── AGENTS.md
    ├── data.py        # CandleBar loading, DuckDB integration, time split
    ├── features.py    # CandleBar -> FeatureVector(7D)
    ├── model.py       # VectorQuantizer, VQVAE, model config
    ├── train.py       # training loop, checkpoint, history
    ├── encode.py      # Tokenizer facade, checkpoint loading, encode()
    └── metrics.py     # utilization, semantic consistency, transition metrics
```

## Planned Public API

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

candles = load_candles(
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
- `test_tokenizer_metrics.py`
  - codebook utilization
  - transition matrix
  - semantic consistency
  - JS divergence
- `test_tokenizer_determinism.py`
  - same checkpoint + same input → same tokens

`torch`가 설치되지 않은 환경에서는 tokenizer test를 skip할 수 있도록 구성합니다.

## Research Phases

### Phase 1 — Tokenizer Foundation

- `research/tokenizers/` package scaffold
- CandleBar data loading
- 7D feature extraction
- time-based split
- baseline VQ-VAE model
- tokenizer training / checkpoint / encode

### Phase 2 — Tokenizer Evaluation

- reconstruction history
- token utilization report
- semantic consistency metric
- transition matrix
- cross-market stability report
- compression vs information tradeoff curve

### Phase 3 — Analysis Design

- token sequence analysis component
- motif discovery
- regime structure analysis
- downstream evaluation tasks

Analysis component는 아직 명확히 정의하지 않습니다. Tokenizer가 안정화된 뒤 별도 spec으로 설계합니다.

## Non-Assumptions

이 연구는 financial markets가 natural language와 동일한 구조를 가진다고 가정하지 않습니다.

다만 candlestick sequence가 learned discrete representation과 symbolic sequence modeling 방식에서 도움을 받을 수 있는지 실험합니다.

## Status

Planning / early research prototype.