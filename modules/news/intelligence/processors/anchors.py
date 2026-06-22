"""Pure temporal leakage guards."""

from __future__ import annotations

from datetime import datetime


def validate_feature_window(
    *,
    source_max_at: datetime,
    feature_cutoff_at: datetime,
    effective_label_anchor: datetime,
    label_window_start: datetime,
    label_window_end: datetime,
) -> None:
    values = (
        source_max_at,
        feature_cutoff_at,
        effective_label_anchor,
        label_window_start,
        label_window_end,
    )
    if any(value.tzinfo is None or value.utcoffset() is None for value in values):
        raise ValueError("processor timestamps must be timezone-aware")
    if not (
        source_max_at
        <= feature_cutoff_at
        <= effective_label_anchor
        < label_window_start
        < label_window_end
    ):
        raise ValueError("feature and label windows violate point-in-time ordering")
