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


def synthetic_exog(prices: pd.DataFrame, extra_days: int = 1, seed: int = 1) -> pd.DataFrame:
    """Fake hourly solar, wind and load forecasts covering the price period plus `extra_days`."""
    rng = np.random.default_rng(seed)
    start = prices["ts_utc"].min().floor("h")
    end = prices["ts_utc"].max().floor("h") + pd.Timedelta(days=extra_days)
    ts = pd.date_range(start, end, freq="1h")
    hour = ts.tz_convert("Europe/Berlin").hour
    solar = np.clip(30000 * np.sin((hour - 6) / 12 * np.pi), 0, None)
    wind = 15000 + 8000 * np.sin(np.arange(len(ts)) / 40) + rng.normal(0, 1000, len(ts))
    load = 50000 + 8000 * np.sin((hour - 8) / 24 * 2 * np.pi)
    parts = [
        pd.DataFrame({"ts_utc": ts, "series": f"{name}_forecast", "value": values})
        for name, values in [
            ("solar", solar),
            ("wind_onshore", wind * 0.8),
            ("wind_offshore", wind * 0.2),
            ("load", load),
        ]
    ]
    return pd.concat(parts, ignore_index=True)
