"""Shared test helpers. Tests never touch the network: they use synthetic prices."""

import numpy as np
import pandas as pd
import pytest


def synthetic_prices(days: int = 150, seed: int = 0, start: str = "2025-01-01") -> pd.DataFrame:
    """Fake 15-minute prices with a daily shape, a weekend effect and noise."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=days * 96, freq="15min", tz="Europe/Berlin")
    hour = ts.hour + ts.minute / 60
    daily_shape = 20 * np.sin((hour - 14) / 24 * 2 * np.pi) + 15 * np.exp(-((hour - 19) ** 2) / 4)
    weekend = np.where(ts.dayofweek >= 5, -15, 0)
    drift = np.repeat(rng.normal(0, 4, days).cumsum(), 96)
    value = 80 + daily_shape + weekend + drift + rng.normal(0, 5, len(ts))
    return pd.DataFrame(
        {"ts_utc": ts.tz_convert("UTC"), "series": "day_ahead_price", "value": value}
    )


@pytest.fixture
def prices() -> pd.DataFrame:
    return synthetic_prices()
