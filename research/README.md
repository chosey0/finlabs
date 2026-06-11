<div align="center">

# FinLabs Research

**시장 데이터를 검증 가능한 표현으로 재구성하는 실험 연구 공간**

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-Optional-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)](https://pytorch.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Tests](https://img.shields.io/badge/Focused_Tests-55-00C853?style=for-the-badge&logo=pytest&logoColor=white)](../tests/research)

Candlestick shape tokenization과 fractal event labeling을 **데이터 누수 없이 분리·검증**합니다.

[FinLabs](../README.md) · [Shape Quantization](./notebooks/01_shape_quantization/README.md) · [Sequential Dynamics](./notebooks/02_sequential_dynamics/README.md) · [Fractal](./fractal/README.md)

</div>

---

## Overview

`research/`는 FinLabs의 실험적 시장 표현 연구 영역입니다. 실제 broker API를 호출하지 않고, 이미 수집된 DuckDB 시장 데이터를 공통 query 계층으로 읽어 재현 가능한 feature, label과 metric을 만듭니다.

현재 연구는 두 트랙으로 나뉩니다. Tokenizer 트랙은 candle의 상대적 price shape를 discrete token으로 양자화하고 sequence transition을 검증합니다. Fractal 트랙은 중앙 정렬 window로 lagging event label을 만들고 segment 시각화와 CNN1D 분류 실험을 제공합니다.

Phase 1 산출물은 **shape token**, Phase 2 산출물은 **sequential structure candidate**입니다. 미래 시장 dynamics에 대한 out-of-sample 검증 전에는 **market state**나 trading signal이라고 부르지 않습니다.

---

## Research Tracks

| | 트랙 | 상태 | 핵심 질문 |
|---|------|:----:|-----------|
| **[Tokenizer 1A]** | Price-shape quantization | 완료 | 비슷한 4D candle shape를 같은 learned token으로 묶을 수 있는가? |
| **[Tokenizer 1B]** | Shape token + range bucket | 반복 검증 완료 | Shape와 volatility context를 분리하면서 split 안정성을 유지하는가? |
| **[Tokenizer 2]** | Sequential dynamics | Primitive 구현 | Token sequence가 반복 가능한 전이 구조를 가지는가? |
| **[Tokenizer 3]** | Market state modeling | 예정 | Token이나 motif가 미래 return·volatility distribution을 설명하는가? |
| **[Fractal]** | Lagging event research | 초기 구현 | 중앙 정렬 극값 label과 segment가 재현 가능한 학습 샘플을 만드는가? |

---

## Phase 1 Results

Phase 1B는 shape와 volatility scale을 하나의 encoder input에 섞지 않습니다.

```text
OHLC candle
    ├── 4D relative price shape ──▶ VQ-VAE ──▶ shape_token
    └── log range percentage ─────▶ train quantiles ──▶ range_bucket

final representation = (shape_token, range_bucket)
```

`volume >= 2` 조건으로 35개 repeated split을 실행한 결과입니다.

| Split family | Runs | Shape L1 mean | Range L1 mean | Pair L1 mean |
|--------------|-----:|--------------:|--------------:|-------------:|
| `random` | 20 | 0.085 | 0.251 | 0.289 |
| `vol_strat` | 10 | 0.081 | 0.102 | 0.156 |
| `vol_holdout` | 5 | 0.074 | 0.920 | 0.940 |

- `shape_token` drift는 symbol split과 high-volatility holdout에서도 낮게 유지됩니다.
- `range_bucket`은 volatility context를 별도로 포착합니다.
- Pair drift는 range composition 변화의 영향을 강하게 받습니다.
- VQ-VAE가 KMeans보다 명확히 우월하다는 결론은 없어 KMeans baseline을 유지합니다.

상세 결과는 [Phase 1B Summary](./notebooks/01_shape_quantization/summaries/SUMMARY.md)에 기록되어 있습니다.

---

## Research Frame

### Phase 1: Shape Quantization

| Feature | 의미 |
|---------|------|
| `signed_body_ratio` | 전체 range 대비 body 크기와 상승·하락 방향 |
| `upper_ratio` | 전체 range 대비 upper wick 비율 |
| `lower_ratio` | 전체 range 대비 lower wick 비율 |
| `body_center_location` | Body 중심의 `[low, high]` 내 상대 위치 |

Absolute price, range scale, future return과 trading label은 shape encoder input에서 제외합니다. Volume은 데이터 품질 필터와 별도 context 실험에만 사용합니다.

### Phase 2: Sequential Dynamics

```text
shape_token_t  → shape_token_t+1
range_bucket_t → range_bucket_t+1
pair_token_t   → pair_token_t+1
```

현재 `transition_counts`와 source probability·entropy를 계산하는 `transition_report` primitive가 구현되어 있습니다. Split 안정성, shuffled baseline, marginal baseline과 first-order Markov 비교는 [Phase 2 계획](./notebooks/02_sequential_dynamics/README.md)에 따라 확장합니다.

### Phase 3: Market State Modeling

Phase 3에서 처음으로 token 또는 motif와 미래 return·volatility·drawdown distribution의 관계를 평가합니다. 아직 구현하지 않았으며 Phase 1·2가 안정화되기 전에는 token을 market state로 해석하지 않습니다.

### Fractal Event Research

```text
detect raw fractal events
    ▼
apply event-level filters
    ▼
build high-to-low / low-to-high segments
    ▼
plot segments or build CNN1D samples
```

Fractal label은 중앙 정렬 홀수 window에서 close의 유일한 극값을 사용합니다. Label 생성 시 미래 candle이 필요하므로 지도학습 실험에는 사용할 수 있지만 실시간 매매 신호로 사용할 수 없습니다. 세부 규칙은 [Fractal README](./fractal/README.md)를 참고하세요.

---

## Tech Stack

### Data & Runtime

![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-1.1+-FFF000?style=flat-square&logo=duckdb&logoColor=black)
![NumPy](https://img.shields.io/badge/NumPy-Optional-013243?style=flat-square&logo=numpy&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-Optional-F7931E?style=flat-square&logo=scikitlearn&logoColor=white)

### Modeling & Visualization

![PyTorch](https://img.shields.io/badge/PyTorch-2.2+-EE4C2C?style=flat-square&logo=pytorch&logoColor=white)
![Matplotlib](https://img.shields.io/badge/Matplotlib-3.10+-11557C?style=flat-square)
![Plotly](https://img.shields.io/badge/Plotly-5.24+-3F4F75?style=flat-square&logo=plotly&logoColor=white)
![Kaleido](https://img.shields.io/badge/Kaleido-Static_Export-5A5A5A?style=flat-square)

---

## Data Flow

```text
local DuckDB warehouse
    ▼
modules.orchestration.query
    ▼
ordered canonical CandleBar records
    ├──▶ research.tokenizers
    └──▶ research.fractal
```

| 테이블 | 데이터 | 사용 예 |
|--------|--------|---------|
| `ohlcv_bars` | 일·주·월·년 OHLCV | Daily tokenizer·fractal experiment |
| `overseas_minute_bars` | 해외주식 분봉 OHLCV | Repeated split과 minute fractal segment |

Transition은 같은 symbol 내부에서 timestamp 오름차순으로만 계산합니다. Research code는 broker transport를 호출하거나 warehouse SQL을 중복 정의하지 않습니다.

---

## Getting Started

### 사전 요구사항

- Python 3.12+
- `uv`
- FinLabs가 수집한 로컬 DuckDB warehouse
- VQ-VAE·CNN 학습 시 optional tokenizer dependencies

### 설치

```bash
git clone https://github.com/chosey0/finlabs.git
cd finlabs
uv sync
uv sync --extra tokenizers
```

### Jupyter Kernel

```bash
uv run --extra tokenizers --with ipykernel python -m ipykernel install \
  --user --name finlabs-tokenizers --display-name "FinLabs Tokenizers"
```

### Phase 1 Repeated Splits

```bash
uv run --extra tokenizers python \
  research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py \
  --split-family random \
  --n-runs 20 \
  --seed-start 0
```

Runner는 기존 run directory를 덮어쓰지 않으며 완료 후 summary CSV를 갱신합니다.

### Fractal Segment Plots

```bash
uv run python -m research.fractal INTC NVDA TSLA
uv run python -m research.fractal RKLB --interval 1d --type html
uv run python -m research.fractal TSLA --no-followthrough
```

기본 출력은 `research/fractal/event_plots/`에 생성되며 Git에서 제외됩니다.

---

## Repository

```text
research/
├── tokenizers/
│   ├── data.py                 ordered warehouse loading and split helpers
│   ├── features.py             deterministic candle feature extraction
│   ├── model.py                optional VQ-VAE model
│   ├── train.py                safe checkpoint training
│   ├── encode.py               checkpoint-backed inference
│   ├── shape_metrics.py        Phase 1 metrics
│   └── sequence_metrics.py     Phase 2 transition primitives
├── fractal/
│   ├── labels.py               centered-window event detection
│   ├── data.py                 CNN sample construction
│   ├── model.py                optional CNN1D model
│   ├── train.py                supervised training helper
│   ├── infer.py                latest-window inference
│   ├── plot.py                 event and segment visualization
│   └── plot_command.py         multi-symbol export CLI
├── notebooks/
│   ├── 01_shape_quantization/  notebooks, runners and summaries
│   └── 02_sequential_dynamics/ Phase 2 plan
└── README.md
```

---

## Metrics

| 단계 | 구현된 지표 | 다음 검증 |
|------|-------------|-----------|
| Phase 1 | Utilization, dead-token ratio, entropy, semantic consistency, reconstruction MSE, split L1 drift | KMeans 대비 반복 안정성 |
| Phase 2 | Transition counts, source probabilities, weighted entropy | Split stability, shuffled·marginal·Markov baseline |
| Phase 3 | 미구현 | Future return·volatility distribution 설명력 |
| Fractal | Raw·filtered event 수, segment selection과 skip reason | Label stability와 CNN baseline 품질 |

---

## Determinism & Leakage

- 같은 checkpoint와 input의 CPU inference는 같은 token sequence를 반환해야 합니다.
- VQ-VAE와 range bucket threshold는 train candle로만 fit합니다.
- Validation·test는 train-derived statistics로만 transform합니다.
- Symbol 경계를 넘는 transition을 만들지 않습니다.
- Phase 1·2 feature에 future token, return 또는 trading label을 넣지 않습니다.
- Fractal centered-window label이 미래 candle을 사용한다는 점을 항상 명시합니다.
- 실제 broker API는 research test와 notebook에서 호출하지 않습니다.

---

## Testing

Focused tests는 synthetic candle과 `tmp_path` 기반 DuckDB를 사용합니다.

```bash
# Tokenizer: 17 tests
uv run python -m pytest tests/research/tokenizers -q

# Fractal: 38 tests
uv run python -m pytest tests/research/fractal -q

uv run ruff check research tests/research
```

PyTorch가 없는 환경에서는 optional model·training test가 skip될 수 있습니다.

---

## Current Scope

이 연구는 price prediction 제품, 자동매매 전략, 주문 실행 또는 backtest engine을 제공하지 않습니다. Shape token은 candle morphology vocabulary이며, fractal label은 미래 candle을 사용하는 lagging supervised label입니다.

Phase 2는 transition primitive까지만 구현되어 있고 전체 repeated split 검증은 진행 전입니다. Phase 3 future dynamics modeling은 아직 구현하지 않았습니다.

---

## License

이 저장소에는 아직 별도 라이선스 파일이 없습니다.
