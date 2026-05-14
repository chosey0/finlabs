from research.tokenizers.features import FeatureVector
from research.tokenizers.metrics import semantic_consistency, token_utilization, transition_counts


def test_token_utilization_reports_dead_codes_and_entropy():
    result = token_utilization([0, 0, 2, 2], codebook_size=4)

    assert result.utilized_count == 2
    assert result.dead_count == 2
    assert result.dead_ratio == 0.5
    assert result.entropy == 1.0
    assert result.histogram == {0: 2, 2: 2}


def test_transition_counts():
    assert transition_counts([1, 2, 1, 2, 2]) == {(1, 2): 2, (2, 1): 1, (2, 2): 1}


def test_semantic_consistency_groups_by_token():
    features = [
        FeatureVector(0, 0, 0, 0, 0, 0, 0),
        FeatureVector(2, 0, 0, 0, 0, 0, 0),
        FeatureVector(5, 0, 0, 0, 0, 0, 0),
    ]

    result = semantic_consistency([7, 7, 8], features)

    assert result[7] == 1.0
    assert result[8] == 0.0
