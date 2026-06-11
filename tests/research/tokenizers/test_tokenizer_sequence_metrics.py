from research.tokenizers.sequence_metrics import transition_counts, transition_report


def test_transition_counts():
    assert transition_counts([1, 2, 1, 2, 2]) == {(1, 2): 2, (2, 1): 1, (2, 2): 1}


def test_transition_report_has_source_probabilities_and_entropy():
    report = transition_report([1, 2, 1, 2, 2])

    assert report.counts == {(1, 2): 2, (2, 1): 1, (2, 2): 1}
    assert report.probabilities == {(1, 2): 1.0, (2, 1): 0.5, (2, 2): 0.5}
    assert report.entropy_by_source == {1: 0.0, 2: 1.0}
