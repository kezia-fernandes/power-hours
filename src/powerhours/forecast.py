"""The daily job: forecast tomorrow, save the forecast, and later score it.

Usage
    python -m powerhours.forecast --zone DE-LU

Saved forecasts are never overwritten by better hindsight: every row records when
it was made (`made_at_utc`) and whether that was before the auction results came
out (`before_auction`). Only those rows count as real forecasts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

from powerhours import store
from powerhours.config import DEFAULT_ZONE, ZONES
from powerhours.features import PRICE_SERIES, build_features, hourly_matrix
from powerhours.models import MODELS
from powerhours.window import best_window

AUCTION_HOUR_LOCAL = 12  # results for tomorrow appear shortly after noon


def make_forecast(zone: str, root=None, now: datetime | None = None) -> pd.DataFrame:
    """Forecast the first day without prices in the store, with every model."""
    tz = ZONES[zone].timezone
    now = now or datetime.now(timezone.utc)
    prices = store.read("price", zone, root=root)
    if prices.empty:
        raise ValueError(f"No prices stored for {zone}. Run the ingestion first.")

    features = build_features(hourly_matrix(prices, tz))
    train = features.dropna(subset=["y"])
    target_date = train["date"].max() + pd.Timedelta(days=1)
    target = features[features["date"] == target_date]
    if len(target) != 24:
        raise ValueError(f"Cannot build features for {target_date.date()} (gap in recent data?).")

    # A real forecast for day D+1 must be made before noon of day D.
    deadline = (target_date - pd.Timedelta(days=1)).tz_localize(tz) + pd.Timedelta(
        hours=AUCTION_HOUR_LOCAL
    )
    before_auction = pd.Timestamp(now) < deadline

    local_ts = (target["date"] + pd.to_timedelta(target["hour"], unit="h")).dt.tz_localize(
        tz, nonexistent="NaT", ambiguous="NaT"
    )
    parts = []
    for name, make in MODELS.items():
        model = make().fit(train, train["y"])
        parts.append(
            pd.DataFrame(
                {
                    "ts_utc": local_ts.dt.tz_convert("UTC").to_numpy(),
                    "model": name,
                    "yhat": model.predict(target),
                    "made_at_utc": pd.Timestamp(now),
                    "before_auction": before_auction,
                }
            )
        )
    forecast = pd.concat(parts, ignore_index=True).dropna(subset=["ts_utc"])
    forecast["ts_utc"] = pd.to_datetime(forecast["ts_utc"], utc=True)
    return forecast


def save_forecast(forecast: pd.DataFrame, zone: str, root=None) -> int:
    """Store a forecast, but never replace an earlier forecast for the same hour."""
    return store.insert_new(forecast, "forecast", zone, public=True, root=root)


def score_forecasts(zone: str, root=None) -> pd.DataFrame:
    """Join saved forecasts with what really happened. One row per (hour, model)."""
    forecasts = store.read("forecast", zone, root=root)
    prices = store.read("price", zone, root=root)
    if forecasts.empty or prices.empty:
        return pd.DataFrame()
    actual = (
        prices.loc[prices["series"] == PRICE_SERIES]
        .set_index("ts_utc")["value"]
        .resample("1h")
        .mean()
        .rename("y")
    )
    scored = forecasts.merge(actual, left_on="ts_utc", right_index=True, how="inner")
    scored["abs_error"] = (scored["yhat"] - scored["y"]).abs()
    return scored.dropna(subset=["y"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Forecast the next day and save it.")
    parser.add_argument("--zone", default=DEFAULT_ZONE, choices=list(ZONES))
    parser.add_argument("--duration", type=int, default=2)
    args = parser.parse_args(argv)

    forecast = make_forecast(args.zone)
    saved = save_forecast(forecast, args.zone)

    tz = ZONES[args.zone].timezone
    gbm = forecast[forecast["model"] == "gbm"].sort_values("ts_utc")
    start = gbm["ts_utc"].dt.tz_convert(tz).iloc[best_window(gbm["yhat"], args.duration)]
    print(f"Saved {saved} new forecast rows for {args.zone}.")
    if not forecast["before_auction"].all():
        print("Note: made after the auction deadline, so it will not count as a real forecast.")
    print(f"Cheapest {args.duration}-hour window on {start:%A %d %b}: starts {start:%H:%M}.")


if __name__ == "__main__":
    main()
