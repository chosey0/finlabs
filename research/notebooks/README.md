# Research Notebooks

이 디렉터리는 FinLabs research track의 exploratory notebook을 보관합니다.

## Notebooks

| Notebook | Phase | Purpose |
|----------|-------|---------|
| `01_shape_quantization/00_smoke.ipynb` | Phase 1 — Shape Quantization | 단일 market/symbol/timeframe의 OHLCV candle을 7D feature로 변환하고, VQ-VAE shape tokenizer를 학습한 뒤 token utilization, semantic consistency, prototype candle, transition heatmap을 시각적으로 확인합니다. |
| `01_shape_quantization/01_phase_1a_price_shape_only.ipynb` | Phase 1A — Price-Shape Only Quantization | single market × multiple symbols × single timeframe 데이터셋에서 4D price-shape feature를 VQ-VAE로 token화하고, per-symbol metric과 KMeans baseline을 비교합니다. |
| `01_shape_quantization/02_phase_1b_shape_plus_range_scale.ipynb` | Phase 1B — Shape + Range Scale Ablation | Phase 1A의 4D price-shape feature에 `range_scale_z`를 encoder input으로 직접 추가했을 때의 영향을 확인합니다. |
| `01_shape_quantization/02_phase_1b_shape_token_plus_range_bucket.ipynb` | Phase 1B — Shape Token + Range Bucket | 4D price-shape token은 유지하고 range context는 train quantile 기반 bucket으로 별도 분리해 `(shape_token, range_bucket)` representation을 실험합니다. |
| `01_shape_quantization/03_symbol_split_protocol.md` | Phase 1 — Repeated Split Evaluation | 여러 held-out symbol split에 대해 shape token stability, range bucket drift, shape-range pair drift를 반복 평가하기 위한 프로토콜입니다. |

## 실행 전 준비

```bash
uv sync --extra tokenizers
```

Jupyter kernel이 필요하면 다음 명령을 사용합니다.

```bash
uv run --extra tokenizers --with ipykernel python -m ipykernel install --user --name finlabs-tokenizers --display-name "FinLabs Tokenizers"
```

노트북은 실제 broker API를 호출하지 않습니다. 이미 수집되어 DuckDB warehouse에 저장된 `ohlcv_bars` 데이터를 읽습니다.


## Figure Outputs

`01_shape_quantization/00_smoke.ipynb`의 시각화 셀은 모든 figure를 화면에 표시하는 동시에 아래 디렉터리에 PNG로 저장합니다.

```text
RUN_DIR / "figures"
```

저장 파일 예시:

```text
01_token_histogram.png
02_mean_feature_heatmap.png
03_prototype_candles.png
04_feature_scatter_body_close_position.png
05_transition_matrix_heatmap.png
06_token_sequence_over_time.png
```


## Minute Data

`load_candles()`는 DuckDB `overseas_minute_bars`도 읽을 수 있습니다. notebook의 `INTERVAL`을 다음처럼 변경하면 됩니다.

```python
INTERVAL = "1m"   # or "5m", "1min", "5minutes"
```


분봉 데이터는 날짜 범위를 미리 모르면 train split이 비어 있을 수 있습니다. 이 경우 notebook 기본값처럼 ratio split을 사용합니다.

```python
SPLIT_MODE = "ratio"
TRAIN_RATIO = 0.7
VAL_RATIO = 0.15
```
