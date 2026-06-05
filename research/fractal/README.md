# Fractal Research

이 패키지는 기존 `Fractal` 프로토타입에서 fractal 라벨 실험 부분만 떼어내 정리한 것입니다.

핵심 아이디어는 다음과 같습니다.

1. 중앙 정렬 rolling window로 lagging 지도학습 라벨을 만든다.
2. 라벨링된 이벤트 시점까지의 candle만으로 샘플 하나를 구성한다.
3. 작은 `CNN1D`로 그 샘플을 분류한다.

## Labels

Fractal 이벤트 처리는 단계별로 명시적으로 나뉘어 있습니다.

```text
detect_fractal_events
→ filter_fractal_events
→ fractal_event_segments
→ segment-level filters
```

`detect_fractal_events`는 중앙 정렬 window의 close 기준 극값만 그대로 반환합니다.

- raw high: 홀수 window 안에서 중앙 candle의 close가 유일한 최댓값
- raw low: 홀수 window 안에서 중앙 candle의 close가 유일한 최솟값

이어서 `filter_fractal_events`가 거의 평평한 window 제거나 MA 기반 필터링 같은 이벤트 단위 조건을 적용합니다. 호환용 wrapper인 `compute_fractal_events`는 위 두 단계를 모두 실행한 뒤 다음과 같이 표시합니다.

- `0`: `short_ma >= long_ma` 상태에서의 fractal low
- `1`: `short_ma >= long_ma` 상태에서의 fractal high
- `2`: 필터링된 이벤트 (대개 `short_ma < long_ma`인 경우)

라벨 window는 홀수의 중앙 정렬 window이므로, 라벨을 만들 때 미래 candle이 쓰입니다. 지도학습용 라벨로는 유효하지만 실시간 매매 신호로는 쓸 수 없습니다.

현재의 라벨링 규칙은 모호한 극값을 의도적으로 배제합니다.

- `window`는 홀수여야 하며 기본값은 `21`입니다.
- fractal high/low는 close 기준으로 window 안의 **유일한** 최댓값/최솟값이어야 합니다.
- 거의 평평한 window는 `min_window_range_pct`로 건너뜁니다.

## Samples

`build_fractal_samples`는 이벤트 candle을 포함한 그 시점까지의 candle만 유지합니다. 기본적으로 모델은 다음 6개 feature를 입력으로 받습니다.

- open
- high
- low
- close
- short moving average
- long moving average

각 샘플은 원래 프로토타입과 동일하게 독립적으로 표준화됩니다.

## Plotting

`plot_fractal_events`는 Plotly로 candle과 fractal high/low 마커를 함께 그립니다. Plotly를 쓰는 이유는 native candlestick trace를 지원하고, 노트북/브라우저에서 인터랙티브하며, polling이나 streaming workflow에서 같은 figure 객체를 재사용할 수 있기 때문입니다. 함수는 `plotly.graph_objects.Figure`를 반환하므로, 화면에 띄울지, HTML로 저장할지, 같은 figure를 반복 업데이트할지는 호출자가 결정합니다.

```python
from research.fractal import FractalLabelConfig, plot_fractal_events

fig = plot_fractal_events(
    candles,
    label_config=FractalLabelConfig(window=21, short_ma=20, long_ma=120),
    max_candles=300,
    show_filtered=False,
)
fig.show()
```

실시간 또는 준실시간으로 사용할 때는 이전 `figure`와 rolling `max_candles` 값을 함께 넘깁니다. 가장 최근의 `window // 2`개 candle은 아직 중앙 정렬 window 라벨을 가질 수 없으므로, 확정된 lagging fractal 이벤트만 표시할 수 있습니다.

### DuckDB에서 plot 데이터 불러오기

FinLabs warehouse 데이터에는 `plot_fractal_events_from_warehouse`를 사용합니다. DuckDB 읽기는 `modules.orchestration.query.load_candles`에 위임하므로 이 모듈은 warehouse SQL을 중복 정의하지 않습니다. 일봉은 `ohlcv_bars`에서, 분봉은 `overseas_minute_bars`에서 읽어 옵니다.

warehouse 파일 경로 해석은 아직 transitional 계층인 `kis_cli.storage.warehouse.default_warehouse_file()`을 사용합니다(추후 `modules` 쪽으로 이전 예정). 읽기 SQL 자체는 이미 `modules` 계층을 통합니다.

```python
from kis_cli.storage.warehouse import default_warehouse_file
from research.fractal import plot_fractal_events_from_warehouse

fig = plot_fractal_events_from_warehouse(
    default_warehouse_file(),
    market="NASDAQ",
    symbol="AAPL",
    interval="1m",
    max_candles=300,
)
fig.show()
```

## Model

`CNN1D`는 입력 형상으로 `batch x steps x features`를 기대합니다. 내부에서 `batch x features x steps`로 transpose한 뒤 `Conv1d(kernel_size=1)` 층과 adaptive average pooling을 적용합니다.

```python
from research.fractal import FractalLabelConfig, build_fractal_samples
from research.fractal.data import Candle
from research.fractal.train import train_cnn1d

candles = [
    Candle(timestamp="2024-01-01", open=1, high=2, low=0.5, close=1.5),
    # ...
]

samples = build_fractal_samples(
    candles,
    max_len=20,
    label_config=FractalLabelConfig(window=21, short_ma=20, long_ma=120),
)
model, history = train_cnn1d(samples)
```

## CLI Plot Command

plotting 헬퍼는 모듈 형태로도 실행할 수 있습니다. 로컬 DuckDB warehouse에서 candle을 읽어 와, 확정된 인접 `high_to_low`·`low_to_high` fractal segment마다 plot을 한 장씩 저장합니다. SVG 파일은 기본적으로 `research/fractal/event_plots/` 아래에 저장되며, SVG/PNG/PDF 정적 export에는 Plotly Kaleido가 쓰입니다.

Candlestick 색상은 한국식 상승/하락 색상에 맞춰 고정되어 있습니다.

- 양봉: `#FD7979`
- 음봉: `#8CA9FF`

분봉 interval에서는 큰 timestamp gap을 가로지르는 segment를 건너뜁니다. 그래야 금요일 장외 시간 candle과 그다음 월요일 장전 시간 candle이 인위적인 low→high 또는 high→low segment 하나로 묶이는 일을 막을 수 있습니다. 인접 candle gap의 기본 허용 상한은 `interval_minutes * 5`이며 `--max-gap-minutes`로 덮어 쓸 수 있습니다. 일봉 interval에서는 명시적으로 값이 주어지지 않는 한 이 필터가 비활성화됩니다.

`high_to_low` 또는 `low_to_high` segment는, 해당 segment의 끝 이벤트 뒤에 충분한 가격 움직임을 동반한 다음 fractal 이벤트가 이어질 때만 저장됩니다. 예를 들어 `high_to_low` segment는 그 low에서 다음 high 또는 low 이벤트까지 이어지는 가격 이동으로 확인(confirm)됩니다. `--min-followthrough-change-pct`의 기본값은 `5`입니다.

기존의 시작/끝 segment 변화량 필터는 `--min-segment-change-pct`로 여전히 사용할 수 있지만 기본값이 `0`이므로, 명시적으로 지정하지 않는 한 비활성 상태입니다.

기본적으로 저장되는 plot은 segment 종료 이벤트에서 바로 다음 fractal 이벤트까지 확장됩니다. 이때 원래 segment 구간과 follow-through 구간은 서로 다른 배경색으로 표시됩니다. 이 확장을 끄려면 `--no-followthrough`를 지정합니다.

Segment plot은 MA로 필터링된 지도학습 라벨이 아니라 event-level 필터링만 거친 raw high/low 이벤트를 사용합니다. 이렇게 이벤트 탐지와 segment 선택을 분리해 둡니다.

```bash
uv run python -m research.fractal INTC NVDA TSLA
```

터미널에서 실행하면 입력한 ticker 수를 기준으로 진행률이 표시됩니다.

필요한 옵션만 덮어 씁니다.

```bash
uv run python -m research.fractal RKLB --interval 1d --type html
uv run python -m research.fractal INTC NVDA --min-followthrough-change-pct 3
uv run python -m research.fractal TSLA --no-followthrough
```

분봉이면 `--interval 1m`, 일봉이면 `--interval 1d`를 사용합니다. `--window`는 `21`처럼 홀수 값이어야 합니다. fractal 라벨이 중앙 정렬 window를 쓰기 때문에 짝수 window는 거부됩니다.

지원하는 `--type` 값은 `svg`, `png`, `html`, `pdf`입니다. `--out`의 확장자가 다르면 `--type`이 우선하고 확장자는 그에 맞춰 정규화됩니다. 명령은 출력 base 이름 뒤에 `_{transition}_{ordinal:03d}`를 덧붙이며, ordinal은 transition 타입별로 따로 셉니다. 같은 base 이름에 `_manifest.json`을 붙인 manifest 파일도 함께 기록되는데, 여기에는 CLI 설정, 선택 요약, skip 카운트, 저장된 segment metadata가 담깁니다.

출력 예시:

```text
research/fractal/event_plots/fractal_AAPL_1m_high_to_low_001.svg
research/fractal/event_plots/fractal_AAPL_1m_high_to_low_002.svg
research/fractal/event_plots/fractal_AAPL_1m_low_to_high_001.svg
research/fractal/event_plots/fractal_AAPL_1m_manifest.json
```

콘솔 요약:

```text
summary raw_events=120 filtered_events=108 candidate_segments=77 saved_segments=12 skipped_by_gap=4 skipped_by_change_pct=61
```
