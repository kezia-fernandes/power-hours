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
from powerhours.features import PRICE_SERIES, load_features
from powerhours.models import MODELS, NEEDS_EXOG, PREFERRED
from powerhours.window import best_window

AUCTION_HOUR_LOCAL = 12  # bids close at noon; results for tomorrow appear shortly after
EXOG_INPUTS = ["solar_fc", "wind_fc", "load_fc"]


def make_forecast(zone: str, root=None, now: datetime | None = None) -> pd.DataFrame:
    """Forecast the first day without prices in the store, with every model that can run.

    Models in NEEDS_EXOG are skipped when tomorrow's solar/wind/load forecasts have
    not been published yet. They get another chance at the next scheduled run.
    """
    tz = ZONES[zone].timezone
    now = now or datetime.now(timezone.utc)

    features = load_features(zone, root=root)
    train = features.dropna(subset=["y"])
    target_date = train["date"].max() + pd.Timedelta(days=1)
    target = features[features["date"] == target_date]
    if len(target) != 24:
        raise ValueError(f"Cannot build features for {target_date.date()} (gap in recent data?).")
    has_exog = bool(target[EXOG_INPUTS].notna().all().all())

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
        if name in NEEDS_EXOG and not has_exog:
            continue
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
    """Store a forecast, but never replace an earlier forecast for the same hour and model."""
    return store.insert_new(forecast, "forecast", zone, public=True, root=root)


def latest_forecast(zone: str, root=None) -> pd.DataFrame:
    """The saved forecast for the most recent target day, from the best available model.

    Returns columns ts_utc, model, yhat (24 rows), or an empty frame.
    """
    forecasts = store.read("forecast", zone, root=root)
    if forecasts.empty:
        return forecasts
    tz = ZONES[zone].timezone
    local_date = forecasts["ts_utc"].dt.tz_convert(tz).dt.date
    day = forecasts[local_date == local_date.max()]
    for name in PREFERRED:
        chosen = day[day["model"] == name]
        if not chosen.empty:
            return chosen.sort_values("ts_utc").reset_index(drop=True)
    return day.iloc[0:0]


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
    models = sorted(forecast["model"].unique())
    print(f"Saved {saved} new forecast rows for {args.zone}. Models that ran: {models}")
    missing = NEEDS_EXOG - set(models)
    if missing:
        print(f"Skipped {sorted(missing)}: tomorrow's solar/wind/load forecasts are not out yet.")
    if not forecast["before_auction"].all():
        print("Note: made after the auction deadline, so it will not count as a real forecast.")

    best = latest_forecast(args.zone)
    tz = ZONES[args.zone].timezone
    start = best["ts_utc"].dt.tz_convert(tz).iloc[best_window(best["yhat"], args.duration)]
    print(
        f"Cheapest {args.duration}-hour window on {start:%A %d %b}: starts {start:%H:%M} "
        f"(model: {best['model'].iloc[0]})."
    )


if __name__ == "__main__":
    main()
