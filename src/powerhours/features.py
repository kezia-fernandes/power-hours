"""Feature engineering for day-ahead forecasting.

The forecasting situation
    In the morning of day D we predict all 24 hourly prices of day D+1.
    At that moment we know every price up to the end of day D (they were
    published yesterday afternoon). We do NOT know any price of D+1.

So every price-based feature for a target day may only use days *before* it. This
rule ("no leakage") is the most important thing in this file, and there are tests
for it in tests/test_features.py.

Two groups of features
    BASE_FEATURES   calendar and past prices. Always available.
    EXOG_FEATURES   the grid operators' day-ahead forecasts of solar, wind and demand
                    for the target day itself. These are forecasts, so using them is
                    not leakage IF they are published before we have to forecast.
                    Whether that is true every morning is an open question that the
                    `exog_seen` dataset is collecting evidence for.

Simplification: the market trades in 15-minute steps, we model hourly averages.
"""

from __future__ import annotations

import pandas as pd

from powerhours import store
from powerhours.config import ZONES

PRICE_SERIES = "day_ahead_price"

BASE_FEATURES = [
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

EXOG_FEATURES = [
    "solar_fc",  # forecast solar generation in that hour (MW)
    "wind_fc",  # forecast wind generation, onshore + offshore (MW)
    "load_fc",  # forecast demand (MW)
    "residual_fc",  # demand minus wind minus solar: what other power plants must cover
    "residual_fc_day_mean",  # average of residual_fc over the target day
    "residual_fc_vs_day",  # residual_fc minus that average: is this hour tight or relaxed?
    "ws_share_fc",  # wind + solar as a percentage of demand
]

FEATURES = BASE_FEATURES  # kept for backwards compatibility


def to_matrix(frame: pd.DataFrame, series: str, timezone: str, min_hours: int = 23) -> pd.DataFrame:
    """Reshape one series into a table with one row per local day and 24 hour columns.

    Working in "day x hour" form sidesteps daylight-saving headaches: a 23-hour day
    gets its missing hour filled from the neighbour, a 25-hour day averages the
    repeated hour. Days with fewer than `min_hours` observed hours are dropped
    (for example a day that is only partly downloaded).
    """
    values = frame.loc[frame["series"] == series].set_index("ts_utc")["value"]
    local = values.tz_convert(timezone)
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


def hourly_matrix(prices: pd.DataFrame, timezone: str, min_hours: int = 23) -> pd.DataFrame:
    """Day x hour table of day-ahead prices."""
    return to_matrix(prices, PRICE_SERIES, timezone, min_hours)


def exog_matrices(exog: pd.DataFrame, timezone: str) -> dict[str, pd.DataFrame]:
    """Day x hour tables for the solar, wind and load forecasts (whichever exist)."""
    if exog.empty:
        return {}
    tables = {
        kind: to_matrix(exog, f"{kind}_forecast", timezone)
        for kind in ("solar", "wind_onshore", "wind_offshore", "load")
        if (exog["series"] == f"{kind}_forecast").any()
    }
    # Total wind = onshore + offshore, on days where both forecasts exist.
    if "wind_onshore" in tables and "wind_offshore" in tables:
        tables["wind"] = (tables.pop("wind_onshore") + tables.pop("wind_offshore")).dropna()
    return {kind: tables[kind] for kind in ("solar", "wind", "load") if kind in tables}


def _long(table: pd.DataFrame, name: str) -> pd.DataFrame:
    table = table.copy()
    table.index.name = "date"
    return table.reset_index().melt(id_vars="date", var_name="hour", value_name=name)


def build_features(
    matrix: pd.DataFrame, exog: dict[str, pd.DataFrame] | None = None
) -> pd.DataFrame:
    """One row per (date, hour) with the target `y`, BASE_FEATURES and EXOG_FEATURES.

    The output also contains the day *after* the last day in `matrix`: its `y`
    is missing (that is what we want to predict) but its features are complete.
    EXOG_FEATURES are missing (NaN) wherever no forecast was available.
    """
    days = pd.date_range(matrix.index.min(), matrix.index.max() + pd.Timedelta(days=1), freq="D")
    m = matrix.reindex(days)

    frame = _long(m, "y")
    for name, shift in [("lag_1d", 1), ("lag_2d", 2), ("lag_7d", 7)]:
        frame = frame.merge(_long(m.shift(shift), name), on=["date", "hour"])

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

    # Forecasts FOR the target day (not shifted): solar, wind, demand.
    exog = exog or {}
    for kind in ("solar", "wind", "load"):
        column = f"{kind}_fc"
        if kind in exog:
            table = _long(exog[kind].reindex(days), column)
            table["hour"] = table["hour"].astype(int)
            frame = frame.merge(table, on=["date", "hour"], how="left")
        else:
            frame[column] = float("nan")
    frame["residual_fc"] = frame["load_fc"] - frame["wind_fc"] - frame["solar_fc"]
    frame["residual_fc_day_mean"] = frame.groupby("date")["residual_fc"].transform("mean")
    frame["residual_fc_vs_day"] = frame["residual_fc"] - frame["residual_fc_day_mean"]
    frame["ws_share_fc"] = 100 * (frame["wind_fc"] + frame["solar_fc"]) / frame["load_fc"]

    frame = frame.dropna(subset=BASE_FEATURES).sort_values(["date", "hour"]).reset_index(drop=True)
    return frame[["date", "y", *BASE_FEATURES, *EXOG_FEATURES]]


def load_features(zone: str, root=None) -> pd.DataFrame:
    """Read prices and forecasts for a zone from the store and build the feature table."""
    info = ZONES[zone]
    prices = store.read("price", zone, root=root)
    if prices.empty:
        raise ValueError(f"No prices stored for {zone}. Run the ingestion first.")
    exog = store.read("exog", info.country, root=root)
    return build_features(hourly_matrix(prices, info.timezone), exog_matrices(exog, info.timezone))
