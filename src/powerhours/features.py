"""Feature engineering for day-ahead forecasting.

The forecasting situation
    In the morning of day D we predict all 24 hourly prices of day D+1.
    At that moment we know every price up to the end of day D (they were
    published yesterday afternoon). We do NOT know anything about D+1.

So every feature for a target day may only use days *before* it. This rule
("no leakage") is the most important thing in this file, and there is a test
for it in tests/test_features.py.

Simplification: the market trades in 15-minute steps, we model hourly averages.
"""

from __future__ import annotations

import pandas as pd

PRICE_SERIES = "day_ahead_price"

FEATURES = [
    "hour",
    "dow",
    "is_weekend",
    "month",
    "lag_1d",
    "lag_2d",
    "lag_7d",
    "prev_day_mean",
    "prev_day_min",
    "prev_day_max",
    "prev_day_std",
    "prev_week_mean",
]


def hourly_matrix(prices: pd.DataFrame, timezone: str, min_hours: int = 23) -> pd.DataFrame:
    """Reshape raw prices into a table with one row per local day and 24 hour columns.

    Working in "day x hour" form sidesteps daylight-saving headaches: a 23-hour day
    gets its missing hour filled from the neighbour, a 25-hour day averages the
    repeated hour. Days with fewer than `min_hours` observed hours are dropped
    (for example a day that is only partly downloaded).
    """
    series = prices.loc[prices["series"] == PRICE_SERIES].set_index("ts_utc")["value"]
    local = series.tz_convert(timezone)
    long = pd.DataFrame(
        {
            "date": pd.to_datetime(local.index.date),
            "hour": local.index.hour,
            "value": local.to_numpy(),
        }
    )
    matrix = long.pivot_table(index="date", columns="hour", values="value", aggfunc="mean")
    matrix = matrix.reindex(columns=range(24))
    complete = matrix.notna().sum(axis=1) >= min_hours
    matrix = matrix.loc[complete].ffill(axis=1).bfill(axis=1)
    matrix.columns.name = "hour"
    return matrix


def build_features(matrix: pd.DataFrame) -> pd.DataFrame:
    """One row per (date, hour) with the target `y` and the features in FEATURES.

    The output also contains the day *after* the last day in `matrix`: its `y`
    is missing (that is what we want to predict) but its features are complete.
    """
    days = pd.date_range(matrix.index.min(), matrix.index.max() + pd.Timedelta(days=1), freq="D")
    m = matrix.reindex(days)
    m.index.name = "date"

    def long(table: pd.DataFrame, name: str) -> pd.DataFrame:
        return table.reset_index().melt(id_vars="date", var_name="hour", value_name=name)

    frame = long(m, "y")
    for name, shift in [("lag_1d", 1), ("lag_2d", 2), ("lag_7d", 7)]:
        frame = frame.merge(long(m.shift(shift), name), on=["date", "hour"])

    previous = m.shift(1)  # the day before the target day
    daily = pd.DataFrame(
        {
            "prev_day_mean": previous.mean(axis=1),
            "prev_day_min": previous.min(axis=1),
            "prev_day_max": previous.max(axis=1),
            "prev_day_std": previous.std(axis=1),
            "prev_week_mean": m.mean(axis=1).shift(1).rolling(7, min_periods=4).mean(),
        }
    )
    frame = frame.merge(daily, left_on="date", right_index=True)

    frame["hour"] = frame["hour"].astype(int)
    frame["dow"] = frame["date"].dt.dayofweek
    frame["is_weekend"] = (frame["dow"] >= 5).astype(int)
    frame["month"] = frame["date"].dt.month

    frame = frame.dropna(subset=FEATURES).sort_values(["date", "hour"]).reset_index(drop=True)
    return frame[["date", "y", *FEATURES]]
