# Phase 1B Repeated Split Summary

이 문서는 `summary.csv`에 집계된 Phase 1B 반복 실험 결과를 해석합니다.

Source:

```text
research/notebooks/01_shape_quantization/summaries/summary.csv
```

작성 기준:

```text
market: NASDAQ
interval: 1m
codebook size: 12
representation: (shape_token, range_bucket)
```

---

## 1. Executive Summary

현재 `summary.csv`에는 총 **35개 run**이 포함되어 있습니다.

| Split family | Runs | 목적 |
|---|---:|---|
| `random` | 20 | 일반적인 held-out symbol generalization 확인 |
| `vol_strat` | 10 | volatility 구성을 균형 있게 맞춘 조건에서 확인 |
| `vol_holdout` | 5 | high-volatility symbols를 train에서 제외한 어려운 일반화 조건 확인 |

핵심 결론은 다음과 같습니다.

> **Phase 1B의 `shape_token + range_bucket` 분리 설계는 반복 실험 기준으로 유지할 만합니다.**
>
> `shape_token` drift는 모든 split family에서 낮게 유지되었고, `vol_holdout`에서는 `range_bucket` drift만 크게 증가했습니다. 이는 shape와 volatility context가 의도대로 분리되고 있음을 보여줍니다.

가장 중요한 수치는 다음입니다.

| Metric | random | vol_strat | vol_holdout |
|---|---:|---:|---:|
| shape test-train L1 mean | 0.091 | 0.096 | 0.078 |
| shape test-train L1 std | 0.040 | 0.038 | 0.037 |
| shape test-train L1 max | 0.167 | 0.145 | 0.131 |
| range test-train L1 mean | 0.249 | 0.105 | 0.918 |
| pair test-train L1 mean | 0.292 | 0.164 | 0.937 |

해석:

```text
shape drift는 낮다.
volatility-balanced split에서는 range/pair drift도 낮다.
high-volatility holdout에서는 range/pair drift가 의도대로 크게 증가한다.
```

---

## 2. Phase 2 Entry Criteria Check

`03_symbol_split_protocol.md`의 임시 기준은 다음입니다.

```text
random split shape_test_train_l1 mean < 0.15
random split shape_test_train_l1 std  < 0.05
random split shape_test_train_l1 max  < 0.30
```

현재 `random` 20회 결과는 다음입니다.

| Criterion | Result | Pass |
|---|---:|---:|
| mean < 0.15 | 0.091 | ✅ |
| std < 0.05 | 0.040 | ✅ |
| max < 0.30 | 0.167 | ✅ |

따라서 **random split 기준은 통과**했습니다.

추가로 `vol_holdout`에서도 다음 조건이 관찰됩니다.

```text
shape_test_train_l1 mean = 0.078
range_test_train_l1 mean = 0.918
pair_test_train_l1  mean = 0.937
```

즉, 고변동성 종목을 train에서 제외해도 shape drift는 낮고, range drift만 크게 증가합니다. 이는 Phase 1B 설계 의도와 일치합니다.

현재 판단:

> **Phase 2로 진입할 수 있는 수준의 Phase 1B 반복 실험 근거는 확보되었습니다.**
>
> 단, VQ-VAE가 KMeans보다 수치적으로 명확히 우월하다는 근거는 아직 없습니다. Phase 2에서는 KMeans를 baseline으로 계속 유지해야 합니다.

---

## 3. Split Family별 상세 해석

## 3.1 `random` split

Run count:

```text
20 runs: random_00 ~ random_19
```

Aggregate metrics:

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape val-train L1 | 0.129 | 0.076 | 0.049 | 0.300 |
| shape test-train L1 | 0.091 | 0.040 | 0.024 | 0.167 |
| range val-train L1 | 0.440 | 0.233 | 0.135 | 0.936 |
| range test-train L1 | 0.249 | 0.158 | 0.053 | 0.651 |
| pair val-train L1 | 0.489 | 0.218 | 0.162 | 0.944 |
| pair test-train L1 | 0.292 | 0.154 | 0.151 | 0.742 |

해석:

- `shape_test_train_l1` 평균이 0.091로 낮습니다.
- 최대값도 0.167로 protocol 기준인 0.30보다 충분히 낮습니다.
- `range`와 `pair` drift는 run에 따라 더 크게 흔들립니다.
- 이는 random split에서 symbol별 volatility profile이 우연히 다르게 배치될 수 있기 때문입니다.

가장 큰 outlier:

| Metric | Run | Value |
|---|---|---:|
| max shape_test_train_l1 | `random_11` | 0.167 |
| max range_test_train_l1 | `random_11` | 0.651 |
| max pair_test_train_l1 | `random_11` | 0.742 |

`random_11`은 shape drift도 가장 크지만, range/pair drift가 훨씬 큽니다. 따라서 이 outlier는 shape vocabulary 붕괴보다는 train/test volatility profile 차이가 큰 split으로 해석하는 편이 적절합니다.

---

## 3.2 `vol_strat` split

Run count:

```text
10 runs: vol_strat_00 ~ vol_strat_09
```

Aggregate metrics:

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape val-train L1 | 0.101 | 0.059 | 0.036 | 0.187 |
| shape test-train L1 | 0.096 | 0.038 | 0.031 | 0.145 |
| range val-train L1 | 0.109 | 0.084 | 0.029 | 0.317 |
| range test-train L1 | 0.105 | 0.060 | 0.045 | 0.252 |
| pair val-train L1 | 0.174 | 0.076 | 0.100 | 0.347 |
| pair test-train L1 | 0.164 | 0.049 | 0.114 | 0.292 |

해석:

- `shape_test_train_l1` 평균은 0.096으로 random과 비슷하게 낮습니다.
- `range_test_train_l1` 평균이 0.105로 random의 0.249보다 훨씬 낮습니다.
- `pair_test_train_l1` 평균도 0.164로 random의 0.292보다 낮습니다.

즉, volatility tertile을 train/val/test에 균형 있게 배치하면 range/pair drift가 크게 줄어듭니다.

이 결과는 다음 해석을 지지합니다.

```text
random split의 range/pair drift 상당 부분은
shape token 문제라기보다 symbol volatility composition 차이에서 발생한다.
```

가장 큰 outlier:

| Metric | Run | Value |
|---|---|---:|
| max shape_test_train_l1 | `vol_strat_09` | 0.145 |
| max range_test_train_l1 | `vol_strat_02` | 0.252 |
| max pair_test_train_l1 | `vol_strat_02` | 0.292 |

`vol_strat`에서도 모든 shape drift가 0.15 미만입니다. 이는 shape vocabulary가 volatility-balanced 조건에서 안정적임을 보여줍니다.

---

## 3.3 `vol_holdout` split

Run count:

```text
5 runs: vol_holdout_00 ~ vol_holdout_04
```

Aggregate metrics:

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape val-train L1 | 0.103 | 0.066 | 0.046 | 0.199 |
| shape test-train L1 | 0.078 | 0.037 | 0.037 | 0.131 |
| range val-train L1 | 0.951 | 0.038 | 0.908 | 0.992 |
| range test-train L1 | 0.918 | 0.038 | 0.877 | 0.961 |
| pair val-train L1 | 0.961 | 0.030 | 0.934 | 0.997 |
| pair test-train L1 | 0.937 | 0.039 | 0.896 | 0.988 |

해석:

`vol_holdout`은 가장 중요한 stress test입니다. high-volatility symbols를 train에서 제외하고 val/test로 보내기 때문에, range drift가 커지는 것이 정상입니다.

현재 결과는 이상적인 방향에 가깝습니다.

```text
shape_test_train_l1 mean = 0.078   낮음
range_test_train_l1 mean = 0.918   매우 높음
pair_test_train_l1  mean = 0.937   매우 높음
```

이는 다음을 의미합니다.

```text
고변동성 종목을 holdout해도 shape token distribution은 크게 흔들리지 않는다.
반면 range bucket은 고변동성 regime 차이를 강하게 포착한다.
pair drift는 shape 문제가 아니라 range bucket drift의 영향으로 커진다.
```

따라서 `vol_holdout` 결과는 Phase 1B의 핵심 가설을 가장 강하게 지지합니다.

가장 큰 outlier:

| Metric | Run | Value |
|---|---|---:|
| max shape_test_train_l1 | `vol_holdout_00` | 0.131 |
| max range_test_train_l1 | `vol_holdout_03` | 0.961 |
| max pair_test_train_l1 | `vol_holdout_03` | 0.988 |

`vol_holdout`의 모든 run에서 `shape_test_train_l1 < range_test_train_l1`입니다.

---

## 4. Cross-family Interpretation

전체 35개 run의 평균은 다음입니다.

| Metric | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| shape test-train L1 | 0.090 | 0.039 | 0.024 | 0.167 |
| range test-train L1 | 0.303 | 0.290 | 0.045 | 0.961 |
| pair test-train L1 | 0.348 | 0.277 | 0.114 | 0.988 |

가장 중요한 패턴은 다음입니다.

```text
shape drift는 split family가 바뀌어도 낮고 안정적이다.
range drift는 split family에 따라 의도적으로 달라진다.
pair drift는 range drift를 강하게 따라간다.
```

Split family별 기대와 실제 결과를 비교하면 다음과 같습니다.

| Split family | Expected | Observed | Interpretation |
|---|---|---|---|
| `random` | shape drift 낮음, range drift는 split마다 변동 | shape 낮음, range/pair 변동 큼 | 통과 |
| `vol_strat` | shape/range/pair 모두 비교적 안정 | 모두 낮음 | 통과 |
| `vol_holdout` | shape 낮음, range 높음 | shape 낮고 range/pair 매우 높음 | 통과 |

---

## 5. VQ-VAE vs KMeans

`summary.csv` 기준으로 VQ-VAE와 KMeans의 `shape_test_train_l1`은 거의 비슷합니다.

| Split family | VQ-VAE mean | KMeans mean | VQ-VAE - KMeans | VQ-VAE worse count |
|---|---:|---:|---:|---:|
| `random` | 0.091 | 0.089 | +0.002 | 13 / 20 |
| `vol_strat` | 0.096 | 0.097 | -0.001 | 5 / 10 |
| `vol_holdout` | 0.078 | 0.079 | -0.001 | 2 / 5 |
| all | 0.090 | 0.090 | +0.001 | 20 / 35 |

해석:

- VQ-VAE가 KMeans보다 명확히 우월하다고 말할 수 없습니다.
- 반대로 KMeans로 즉시 교체해야 할 만큼 큰 차이도 아닙니다.
- 전체 평균 차이는 약 0.001 수준으로 실질적으로 매우 작습니다.

따라서 현재 결정은 다음이 적절합니다.

```text
Phase 2에서는 VQ-VAE를 primary tokenizer로 유지한다.
KMeans는 반드시 baseline으로 함께 유지한다.
```

---

## 6. Decision

현재 반복 실험 결과는 Phase 1B의 기본 설계를 지지합니다.

채택할 표현:

```text
shape_token  = price-shape only VQ-VAE token
range_bucket = train-quantile log_range_pct bucket
final rep    = (shape_token, range_bucket)
```

판단:

| Decision Item | Status |
|---|---|
| random split 기준 | ✅ 통과 |
| vol_strat robustness | ✅ 통과 |
| vol_holdout stress behavior | ✅ 기대와 일치 |
| shape/range separation | ✅ 지지됨 |
| VQ-VAE superiority over KMeans | ⚠️ 미확정 |
| Phase 2 진입 | ✅ 가능 |

최종 결론:

> **Phase 1B는 반복 split 기준에서 통과로 판단합니다.**
>
> `shape_token`은 symbol split과 volatility holdout 조건에서도 안정적이며, `range_bucket`은 volatility context를 분리해서 포착합니다.
>
> 다음 단계는 Phase 2 Sequential Dynamics로 넘어가되, KMeans baseline을 유지한 비교 실험을 함께 설계하는 것입니다.

---

## 7. Recommended Next Steps

1. Phase 2 notebook 생성
   - token transition matrix
   - Markov baseline
   - transition entropy
   - split별 transition stability

2. VQ-VAE token과 KMeans token을 모두 Phase 2 baseline으로 비교

3. Phase 2에서도 다음 표현을 분리해 평가

```text
shape_token only
range_bucket only
(shape_token, range_bucket) pair
```

4. Phase 3 Market State Modeling으로 넘어가기 전까지는 token을 trading signal이나 market state로 해석하지 않기

