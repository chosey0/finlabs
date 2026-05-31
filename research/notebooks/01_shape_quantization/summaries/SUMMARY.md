# Phase 1B Repeated Split Summary

이 문서는 Phase 1B 반복 실험 결과를 요약합니다.

Primary source는 volume-filtered rerun입니다.

```text
summaries/summary_vge2.csv
```

전체 집계 파일은 기존 unfiltered run과 volume-filtered rerun을 모두 포함합니다.

```text
summaries/summary.csv
```

작성 기준:

```text
market: NASDAQ
interval: 1m
codebook size: 12
representation: (shape_token, range_bucket)
primary candle filter: volume >= 2
```

---

## 1. Executive Summary

Volume-filtered 기준으로 총 **35개 run**을 다시 실행했습니다.

| Split family | Runs | 목적 |
|---|---:|---|
| `random` | 20 | 일반적인 held-out symbol generalization 확인 |
| `vol_strat` | 10 | volatility 구성을 균형 있게 맞춘 조건에서 확인 |
| `vol_holdout` | 5 | high-volatility symbols를 train에서 제외한 어려운 일반화 조건 확인 |

핵심 결론은 다음과 같습니다.

> **`volume <= 1` candle을 제외해도 Phase 1B의 결론은 유지됩니다.**
>
> `shape_token` drift는 모든 split family에서 낮게 유지되고, `vol_holdout`에서는 `range_bucket` drift만 크게 증가합니다. 이는 shape와 volatility context가 분리되고 있다는 기존 해석을 강화합니다.

주요 수치:

| Metric | random | vol_strat | vol_holdout |
|---|---:|---:|---:|
| shape test-train L1 mean | 0.085 | 0.081 | 0.074 |
| shape test-train L1 std | 0.039 | 0.032 | 0.034 |
| shape test-train L1 max | 0.157 | 0.141 | 0.122 |
| range test-train L1 mean | 0.251 | 0.102 | 0.920 |
| pair test-train L1 mean | 0.289 | 0.156 | 0.940 |

---

## 2. Data Filter

Phase 1 실험 데이터에 다음 조건을 적용했습니다.

```text
volume >= 2
```

처리 순서:

```text
DuckDB load
→ volume filter
→ symbol별 최근 max_candles_per_symbol cap
→ train/val/test split
```

Symbol별 제외 candle 수는 `results/03_phase_1b_volume_filter_result.md`에 기록했습니다.

---

## 3. Phase 2 Entry Criteria Check

기준:

```text
random split shape_test_train_l1 mean < 0.15
random split shape_test_train_l1 std  < 0.05
random split shape_test_train_l1 max  < 0.30
```

Volume-filtered random 20회 결과:

| Criterion | Result | Pass |
|---|---:|---:|
| mean < 0.15 | 0.085 | ✅ |
| std < 0.05 | 0.039 | ✅ |
| max < 0.30 | 0.157 | ✅ |

판단:

> **Phase 1B는 volume-filtered 기준에서도 Phase 2 진입 조건을 통과합니다.**

---

## 4. Split Family별 해석

### 4.1 `random`

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape test-train L1 | 0.085 | 0.039 | 0.019 | 0.157 |
| range test-train L1 | 0.251 | 0.159 | 0.058 | 0.662 |
| pair test-train L1 | 0.289 | 0.156 | 0.141 | 0.739 |

해석:

- shape drift는 낮습니다.
- range/pair drift는 split마다 더 크게 흔들립니다.
- 이는 symbol별 volatility profile이 random split에서 우연히 다르게 배치되기 때문입니다.

### 4.2 `vol_strat`

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape test-train L1 | 0.081 | 0.032 | 0.038 | 0.141 |
| range test-train L1 | 0.102 | 0.062 | 0.033 | 0.255 |
| pair test-train L1 | 0.156 | 0.050 | 0.108 | 0.287 |

해석:

- volatility tertile을 균형 있게 배치하면 range/pair drift가 낮아집니다.
- random split의 range/pair drift 상당 부분은 shape vocabulary 문제가 아니라 symbol volatility composition 차이입니다.

### 4.3 `vol_holdout`

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape test-train L1 | 0.074 | 0.034 | 0.035 | 0.122 |
| range test-train L1 | 0.920 | 0.038 | 0.880 | 0.966 |
| pair test-train L1 | 0.940 | 0.040 | 0.897 | 0.995 |

해석:

- high-volatility symbols를 train에서 제외해도 shape drift는 낮습니다.
- range drift는 의도대로 매우 큽니다.
- pair drift는 대부분 range bucket drift에서 발생합니다.

---

## 5. Unfiltered 결과와 비교

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

결론:

```text
저거래량 candle 제거는 shape drift를 소폭 낮췄지만,
Phase 1B의 정성적 결론은 바꾸지 않았다.
```

---

## 6. Next Step

Phase 2 Sequential Dynamics에서는 다음을 기본 전처리로 사용합니다.

```text
volume >= 2
representation = (shape_token, range_bucket)
```

KMeans는 Phase 2에서도 baseline으로 유지합니다.
