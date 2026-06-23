"""Surge-score regressors behind a common protocol.

The default ``RidgeRegressor`` is pure Python (closed-form ridge with standardized
features) so the pipeline trains and is tested with no native dependencies. The
recommended production model is ``LightGbmRegressor``, which lazily imports
LightGBM and exposes the same protocol; install the ``modeling`` dependency group
to use it. Both predict the continuous standardized abnormal return, which is the
``surge_score`` used to rank candidates.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class SurgeModel(Protocol):
    def fit(
        self, features: Sequence[Sequence[float]], targets: Sequence[float]
    ) -> None: ...

    def predict(self, features: Sequence[Sequence[float]]) -> list[float]: ...


class RidgeRegressor:
    """Closed-form ridge regression on standardized features (pure Python)."""

    def __init__(self, alpha: float = 1.0) -> None:
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        self._alpha = alpha
        self._weights: list[float] = []
        self._means: list[float] = []
        self._scales: list[float] = []
        self._intercept = 0.0

    def fit(
        self, features: Sequence[Sequence[float]], targets: Sequence[float]
    ) -> None:
        if not features:
            raise ValueError("cannot fit on an empty feature matrix")
        if len(features) != len(targets):
            raise ValueError("features and targets must align")
        dimension = len(features[0])
        self._means = [
            sum(row[j] for row in features) / len(features) for j in range(dimension)
        ]
        self._scales = []
        for j in range(dimension):
            variance = sum((row[j] - self._means[j]) ** 2 for row in features) / len(
                features
            )
            self._scales.append(variance**0.5 or 1.0)
        standardized = [
            [(row[j] - self._means[j]) / self._scales[j] for j in range(dimension)]
            for row in features
        ]
        self._intercept = sum(targets) / len(targets)
        centered = [value - self._intercept for value in targets]

        gram = [[0.0] * dimension for _ in range(dimension)]
        moment = [0.0] * dimension
        for row, target in zip(standardized, centered):
            for a in range(dimension):
                moment[a] += row[a] * target
                gram_row = gram[a]
                value_a = row[a]
                for b in range(dimension):
                    gram_row[b] += value_a * row[b]
        for a in range(dimension):
            gram[a][a] += self._alpha
        self._weights = _solve(gram, moment)

    def predict(self, features: Sequence[Sequence[float]]) -> list[float]:
        if not self._weights:
            raise RuntimeError("model is not fitted")
        predictions: list[float] = []
        for row in features:
            standardized = (
                (row[j] - self._means[j]) / self._scales[j]
                for j in range(len(self._weights))
            )
            predictions.append(
                self._intercept
                + sum(weight * value for weight, value in zip(self._weights, standardized))
            )
        return predictions


class LightGbmRegressor:
    """LightGBM regressor adapter (optional; install the ``modeling`` group)."""

    def __init__(self, **params: object) -> None:
        self._params = {
            "objective": "regression",
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "verbose": -1,
            **params,
        }
        self._model: object | None = None

    def fit(
        self, features: Sequence[Sequence[float]], targets: Sequence[float]
    ) -> None:
        try:
            from lightgbm import LGBMRegressor
        except ImportError as error:  # pragma: no cover - exercised only with extra
            raise RuntimeError(
                "LightGbmRegressor requires the 'modeling' dependency group"
            ) from error
        model = LGBMRegressor(**self._params)
        model.fit([list(row) for row in features], list(targets))
        self._model = model

    def predict(self, features: Sequence[Sequence[float]]) -> list[float]:
        if self._model is None:
            raise RuntimeError("model is not fitted")
        return [float(value) for value in self._model.predict([list(r) for r in features])]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for a square system."""

    size = len(vector)
    augmented = [matrix[i][:] + [vector[i]] for i in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(augmented[r][column]))
        if augmented[pivot][column] == 0:
            continue
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column] / pivot_value
            if factor == 0:
                continue
            for col in range(column, size + 1):
                augmented[row][col] -= factor * augmented[column][col]
    return [
        augmented[i][size] / augmented[i][i] if augmented[i][i] != 0 else 0.0
        for i in range(size)
    ]
