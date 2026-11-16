"""Backtesting: pretend to be in the past and forecast day by day.

Why not a normal random train/test split?
    With time series, a random split lets the model "see the future" (it trains
    on Wednesday and Friday, then is tested on Thursday). Results look far better
    than they will ever be in real use. Instead we walk forward: for each test day
    the model is trained only on days before it.

Usage
    python -m powerhours.backtest --zone DE-LU --days 90
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from powerhours import store
from powerhours.config import DEFAULT_ZONE, ZONES
from powerhours.features import build_features, hourly_matrix
from powerhours.models import MODELS
from powerhours.window import window_regret


def backtest(
    features: pd.DataFrame,
    test_days: int = 60,
    refit_every: int = 7,
    min_train_days: int = 60,
    models: dict | None = None,
) -> pd.DataFrame:
    """Walk-forward evaluation over the last `test_days` days.

    Models are refitted every `refit_every` days (refitting daily is more faithful
    but slower). Returns one row per (date, hour, model) with `y` and `yhat`.
    """
    models = models or MODELS
    known = features.dropna(subset=["y"])
    days = np.sort(known["date"].unique())
    if len(days) < min_train_days + test_days:
        raise ValueError(
            f"Need at least {min_train_days + test_days} days of data, have {len(days)}."
        )
    test = days[-test_days:]

    results = []
    for block_start in range(0, len(test), refit_every):
        block = test[block_start : block_start + refit_every]
        train = known[known["date"] < block[0]]  # strictly before the test block
        target = known[known["date"].isin(block)]
        for name, make in models.items():
            model = make().fit(train, train["y"])
            out = target[["date", "hour", "y"]].copy()
            out["model"] = name
            out["yhat"] = model.predict(target)
            results.append(out)
    return pd.concat(results, ignore_index=True)


def summarize(predictions: pd.DataFrame, duration: int = 2) -> pd.DataFrame:
    """Score each model. Lower is better everywhere except `window_hit_rate`.

    mae, rmse        classic error metrics in EUR/MWh
    window_regret    average extra cost (EUR/MWh) of running a `duration`-hour load in
                     the window the forecast recommends instead of the truly cheapest one
    window_hit_rate  share of days on which the forecast picked the truly cheapest window
    """
    rows = []
    for model, group in predictions.groupby("model"):
        error = group["yhat"] - group["y"]
        regrets = [
            window_regret(day["y"].to_numpy(), day["yhat"].to_numpy(), duration)
            for _, day in group.sort_values("hour").groupby("date")
            if len(day) == 24
        ]
        rows.append(
            {
                "model": model,
                "mae": error.abs().mean(),
                "rmse": float(np.sqrt((error**2).mean())),
                "window_regret": float(np.mean(regrets)),
                "window_hit_rate": float(np.mean(np.isclose(regrets, 0))),
                "days": len(regrets),
            }
        )
    return pd.DataFrame(rows).set_index("model").sort_values("mae")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest of all models.")
    parser.add_argument("--zone", default=DEFAULT_ZONE, choices=list(ZONES))
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--duration", type=int, default=2, help="length of the load in hours")
    args = parser.parse_args(argv)

    prices = store.read("price", args.zone)
    if prices.empty:
        raise SystemExit(f"No prices stored for {args.zone}. Run the backfill first.")
    features = build_features(hourly_matrix(prices, ZONES[args.zone].timezone))
    summary = summarize(backtest(features, test_days=args.days), duration=args.duration)
    print(f"\nBacktest {args.zone}, last {args.days} days, {args.duration}-hour window\n")
    print(summary.round(3).to_string())


if __name__ == "__main__":
    main()
