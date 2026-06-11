from research.tokenizers.data import CandleBar
from research.tokenizers.features import VolumeContext, build_volume_context, extract_features, extract_features_batch


def _bar(**overrides):
    values = {
        "market": "NASDAQ",
        "symbol": "AAPL",
        "interval": "1d",
        "timestamp": "2026-01-02",
        "open": 100.0,
        "high": 110.0,
        "low": 95.0,
        "close": 105.0,
        "volume": 1_000,
    }
    values.update(overrides)
    return CandleBar(**values)


def test_extract_features_is_deterministic():
    candle = _bar()
    context = VolumeContext(mean=900.0, std=100.0)

    first = extract_features(candle, context)
    second = extract_features(candle, context)

    assert first == second
    assert first.as_tuple() == (
        5.0 / 15.0,
        5.0 / 15.0,
        5.0 / 15.0,
        10.0 / 15.0,
        15.0 / 100.0,
        1.0,
        1.0,
    )


def test_extract_features_handles_zero_range_and_zero_open():
    feature = extract_features(_bar(open=0.0, high=10.0, low=10.0, close=10.0), VolumeContext(mean=1_000, std=0))

    assert feature.body_ratio == 0.0
    assert feature.upper_ratio == 0.0
    assert feature.lower_ratio == 0.0
    assert feature.close_position == 0.5
    assert feature.range_return == 0.0
    assert feature.volume_state == 0.0


def test_extract_features_batch_builds_volume_context():
    candles = (_bar(volume=100), _bar(timestamp="2026-01-03", volume=300))

    context = build_volume_context(candles)
    features = extract_features_batch(candles)

    assert context.mean == 200.0
    assert context.std == 100.0
    assert [feature.volume_state for feature in features] == [-1.0, 1.0]
