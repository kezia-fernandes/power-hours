"""Models. Every model has the same two methods: fit(X, y) and predict(X).

The naive models are not placeholders. They are the bar every other model has to
clear: if a fancy model cannot beat "tomorrow = same hour as today", it is not
worth its complexity.

To try a new idea, add an entry to MODELS at the bottom. The backtest, the
experiment log and the daily forecast pick it up automatically.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from powerhours.features import BASE_FEATURES, EXOG_FEATURES


class NaiveLag:
    """Predict the price observed at the same hour some days ago."""

    features: list[str] = []

    def __init__(self, column: str) -> None:
        self.column = column
        self.features = [column]

    def fit(self, X: pd.DataFrame, y: pd.Series) -> NaiveLag:
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X[self.column].to_numpy()


class GradientBoosting:
    """Gradient-boosted trees on a chosen list of features.

    A starting point, not a tuned model: the hyperparameters below are sensible
    defaults that nobody has optimised yet. Missing values are allowed (this model
    type handles them itself), which matters for the forecast features.
    """

    def __init__(self, features: list[str], **params) -> None:
        self.features = list(features)
        defaults = {
            "loss": "absolute_error",  # we report MAE, so we optimise for it
            "max_iter": 300,
            "learning_rate": 0.05,
            "random_state": 0,
        }
        self.params = {**defaults, **params}
        self.model = HistGradientBoostingRegressor(**self.params)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> GradientBoosting:
        # A feature with no values at all in the training data cannot be learned from.
        self.used_ = [f for f in self.features if X[f].notna().any()]
        self.model.fit(X[self.used_], y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X[self.used_])


MODELS = {
    "naive_yesterday": lambda: NaiveLag("lag_1d"),
    "naive_last_week": lambda: NaiveLag("lag_7d"),
    "gbm": lambda: GradientBoosting(BASE_FEATURES),
    "gbm_exog": lambda: GradientBoosting(BASE_FEATURES + EXOG_FEATURES),
}

# Models that cannot produce a forecast unless tomorrow's solar/wind/load forecasts exist.
NEEDS_EXOG = {"gbm_exog"}

# The model whose forecast the dashboard and the briefing show, in order of preference.
PREFERRED = ["gbm_exog", "gbm"]
