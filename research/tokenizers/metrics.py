"""Backward-compatible metric exports.

Prefer importing Phase 1 metrics from `shape_metrics` and Phase 2 metrics from
`sequence_metrics` in new code.
"""

from research.tokenizers.sequence_metrics import TransitionReport, transition_counts, transition_report
from research.tokenizers.shape_metrics import TokenUtilization, semantic_consistency, token_utilization

__all__ = [
    "TokenUtilization",
    "TransitionReport",
    "semantic_consistency",
    "token_utilization",
    "transition_counts",
    "transition_report",
]
