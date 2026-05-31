# Phase 1B Volume-filtered Rerun Result

이 문서는 Phase 1 실험 데이터에서 **거래량이 1 이하인 candle을 제외**한 뒤 Phase 1B 반복 split 실험을 다시 실행한 결과입니다.

## 1. 변경된 데이터 조건

기존 조건에 다음 filter를 추가했습니다.

```text
volume >= 2
```

즉, `volume <= 1` candle은 VQ-VAE 학습, RangeBucketizer fit, val/test 평가 모두에서 제외했습니다.

중요한 처리 순서는 다음과 같습니다.

```text
DuckDB load
→ volume filter 적용
→ symbol별 최근 max_candles_per_symbol cap 적용
→ train/val/test symbol split
```

이 순서를 사용한 이유는 cap을 먼저 적용하면 최근 12,000개 안에서 저거래량 candle이 빠진 만큼 sample 수가 줄어들고, 더 과거의 유효 candle을 사용할 기회를 잃기 때문입니다.

## 2. Source Artifacts

새 rerun은 기존 unfiltered run을 덮어쓰지 않도록 run id에 `vge2`를 포함합니다.

```text
runs/phase_1b/shape_token_range_bucket_NASDAQ_1m_k12_vge2_random_00..19
runs/phase_1b/shape_token_range_bucket_NASDAQ_1m_k12_vge2_vol_strat_00..09
runs/phase_1b/shape_token_range_bucket_NASDAQ_1m_k12_vge2_vol_holdout_00..04
```

전용 집계 CSV는 다음 파일입니다.

```text
summaries/summary_vge2.csv
summaries/summary_random_vge2.csv
summaries/summary_vol_strat_vge2.csv
summaries/summary_vol_holdout_vge2.csv
```

## 3. Filtered Candle Counts

`volume <= 1`로 제외된 candle 수는 symbol별로 다음과 같습니다.

| Symbol | Excluded candles |
|---|---:|
| SOXX | 381 |
| AVGO | 147 |
| NFLX | 131 |
| MRVL | 93 |
| QCOM | 77 |
| META | 51 |
| AAPL | 48 |
| AMZN | 38 |
| RKLB | 36 |
| GOOGL | 19 |
| QQQ | 18 |
| PLTR | 5 |
| TSLA | 5 |
| AMD | 4 |
| MSFT | 2 |
| MU | 1 |
| NVDA | 1 |
| INTC | 0 |

해석:

- 제외량은 전체 symbol당 최대 12,000개 기준으로 대부분 작습니다.
- SOXX, AVGO, NFLX는 상대적으로 저거래량 candle이 많아 가장 큰 영향을 받았습니다.
- 그래도 모든 symbol은 `min_candles_per_symbol=500` 기준을 충분히 통과했습니다.

## 4. Aggregate Metrics

### 4.1 `random` split — 20 runs

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape test-train L1 | 0.085 | 0.039 | 0.019 | 0.157 |
| range test-train L1 | 0.251 | 0.159 | 0.058 | 0.662 |
| pair test-train L1 | 0.289 | 0.156 | 0.141 | 0.739 |

### 4.2 `vol_strat` split — 10 runs

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape test-train L1 | 0.081 | 0.032 | 0.038 | 0.141 |
| range test-train L1 | 0.102 | 0.062 | 0.033 | 0.255 |
| pair test-train L1 | 0.156 | 0.050 | 0.108 | 0.287 |

### 4.3 `vol_holdout` split — 5 runs

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape test-train L1 | 0.074 | 0.034 | 0.035 | 0.122 |
| range test-train L1 | 0.920 | 0.038 | 0.880 | 0.966 |
| pair test-train L1 | 0.940 | 0.040 | 0.897 | 0.995 |

## 5. Comparison with Previous Unfiltered Runs

| Split family | Metric | Unfiltered mean | Volume-filtered mean | Change |
|---|---|---:|---:|---:|
| random | shape test-train L1 | 0.091 | 0.085 | -0.006 |
| random | range test-train L1 | 0.249 | 0.251 | +0.002 |
| random | pair test-train L1 | 0.292 | 0.289 | -0.004 |
| vol_strat | shape test-train L1 | 0.096 | 0.081 | -0.015 |
| vol_strat | range test-train L1 | 0.105 | 0.102 | -0.002 |
| vol_strat | pair test-train L1 | 0.164 | 0.156 | -0.007 |
| vol_holdout | shape test-train L1 | 0.078 | 0.074 | -0.004 |
| vol_holdout | range test-train L1 | 0.918 | 0.920 | +0.001 |
| vol_holdout | pair test-train L1 | 0.937 | 0.940 | +0.003 |

해석:

- `volume <= 1` candle 제거 후에도 Phase 1B의 주요 결론은 바뀌지 않았습니다.
- `shape_token` drift는 전반적으로 소폭 낮아졌습니다.
- `range_bucket`과 `shape_range_pair` drift는 거의 동일합니다.
- 따라서 기존 결과가 저거래량 candle artifact에 의해 만들어진 것은 아니라고 볼 수 있습니다.

## 6. Phase 2 Entry Criteria Check

기존 Phase 2 진입 기준은 `random` split 기준입니다.

```text
shape_test_train_l1 mean < 0.15
shape_test_train_l1 std  < 0.05
shape_test_train_l1 max  < 0.30
```

Volume-filtered random 20회 결과는 다음입니다.

| Criterion | Result | Pass |
|---|---:|---:|
| mean < 0.15 | 0.085 | ✅ |
| std < 0.05 | 0.039 | ✅ |
| max < 0.30 | 0.157 | ✅ |

판단:

> `volume <= 1` candle을 제거해도 Phase 1B는 Phase 2 진입 기준을 통과합니다.

## 7. Conclusion

Volume filter를 적용한 재실험에서도 핵심 구조는 유지됩니다.

```text
shape_token drift는 낮다.
volatility-balanced split에서는 range/pair drift도 낮다.
high-volatility holdout에서는 range/pair drift만 의도대로 크게 증가한다.
```

따라서 Phase 1B의 기본 표현은 계속 다음으로 유지할 수 있습니다.

```text
final rep = (shape_token, range_bucket)
```

다음 단계에서는 이 표현을 Phase 2 Sequential Dynamics로 넘기되, `volume >= 2` filter를 Phase 1/2 공통 데이터 전처리 규칙으로 유지하는 것이 적절합니다.
