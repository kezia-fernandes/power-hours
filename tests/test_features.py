import numpy as np
import pandas as pd

from powerhours.features import FEATURES, build_features, hourly_matrix

TZ = "Europe/Berlin"


def test_hourly_matrix_shape_and_dst(prices):
    matrix = hourly_matrix(prices, TZ)
    assert matrix.shape == (150, 24)
    assert not matrix.isna().any().any()  # includes the 23-hour day at the end of March


def test_partial_days_are_dropped(prices):
    matrix = hourly_matrix(prices.iloc[: -96 + 20], TZ)  # last day has only 5 hours
    assert len(matrix) == 149


def test_features_include_tomorrow_without_target(prices):
    matrix = hourly_matrix(prices, TZ)
    features = build_features(matrix)
    tomorrow = features[features["date"] == matrix.index.max() + pd.Timedelta(days=1)]
    assert len(tomorrow) == 24
    assert tomorrow["y"].isna().all()
    assert not tomorrow[FEATURES].isna().any().any()


def test_no_leakage_from_target_day(prices):
    """Changing the prices of a day must not change that day's own features."""
    matrix = hourly_matrix(prices, TZ)
    day = matrix.index[100]
    tampered = matrix.copy()
    tampered.loc[day] = 9999.0

    before = build_features(matrix).set_index(["date", "hour"])
    after = build_features(tampered).set_index(["date", "hour"])
    columns = [f for f in FEATURES if f != "hour"]  # hour is part of the index here
    np.testing.assert_array_equal(
        before.loc[day, columns].to_numpy(), after.loc[day, columns].to_numpy()
    )
    # ...but it must change the next day's features (lag_1d).
    next_day = day + pd.Timedelta(days=1)
    assert (after.loc[next_day, "lag_1d"] == 9999.0).all()


def test_lag_values_are_correct(prices):
    matrix = hourly_matrix(prices, TZ)
    features = build_features(matrix).set_index(["date", "hour"])
    day = matrix.index[50]
    assert features.loc[(day, 13), "lag_1d"] == matrix.loc[day - pd.Timedelta(days=1), 13]
    assert features.loc[(day, 13), "lag_7d"] == matrix.loc[day - pd.Timedelta(days=7), 13]
    assert features.loc[(day, 13), "y"] == matrix.loc[day, 13]
