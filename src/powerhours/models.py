"""Models. Every model has the same two methods: fit(X, y) and predict(X).

The naive models are not placeholders. They are the bar every other model has to
clear: if a fancy model cannot beat "tomorrow = same hour last week", it is not
worth its complexity.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from powerhours.features import FEATURES


class NaiveLag:
    """Predict the price observed at the same hour some days ago."""

    def __init__(self, column: str) -> None:
        self.column = column

    def fit(self, X: pd.DataFrame, y: pd.Series) -> NaiveLag:
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X[self.column].to_numpy()


class GradientBoosting:
    """Gradient-boosted trees on the lag and calendar features.

    A starting point, not a tuned model: the hyperparameters below are sensible
    defaults that nobody has optimised yet.
    """

    def __init__(self) -> None:
        self.model = HistGradientBoostingRegressor(
            loss="absolute_error",  # we report MAE, so we optimise for it
            max_iter=300,
            learning_rate=0.05,
            random_state=0,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> GradientBoosting:
        self.model.fit(X[FEATURES], y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X[FEATURES])


MODELS = {
    "naive_yesterday": lambda: NaiveLag("lag_1d"),
    "naive_last_week": lambda: NaiveLag("lag_7d"),
    "gbm": GradientBoosting,
}
