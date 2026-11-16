"""End-to-end test on synthetic data: store -> features -> backtest -> forecast -> score."""

from datetime import datetime, timezone

import pytest

from powerhours import store
from powerhours.backtest import backtest, summarize
from powerhours.features import build_features, hourly_matrix
from powerhours.forecast import make_forecast, save_forecast, score_forecasts

from .conftest import synthetic_prices


def test_backtest_trains_only_on_the_past_and_scores_all_models(prices):
    features = build_features(hourly_matrix(prices, "Europe/Berlin"))
    predictions = backtest(features, test_days=28, refit_every=7)
    summary = summarize(predictions)

    assert set(summary.index) == {"naive_yesterday", "naive_last_week", "gbm"}
    assert (summary["days"] == 28).all()
    assert (summary["mae"] > 0).all()
    assert summary["window_hit_rate"].between(0, 1).all()
    # The synthetic data has a learnable pattern, so the model should beat "yesterday".
    assert summary.loc["gbm", "mae"] < summary.loc["naive_yesterday", "mae"]


def test_backtest_needs_enough_data(prices):
    features = build_features(hourly_matrix(prices, "Europe/Berlin"))
    with pytest.raises(ValueError):
        backtest(features, test_days=500)


def test_forecast_save_and_score(tmp_path):
    all_prices = synthetic_prices(days=122)
    local_date = all_prices["ts_utc"].dt.tz_convert("Europe/Berlin").dt.strftime("%Y-%m-%d")
    known, next_day = all_prices[local_date < "2025-05-01"], all_prices[local_date == "2025-05-01"]
    store.upsert(known, "price", "DE-LU", public=True, root=tmp_path)

    # The first unknown day is 2025-05-01. Forecast made at 08:00 UTC on the day before = on time.
    on_time = datetime(2025, 4, 30, 8, 0, tzinfo=timezone.utc)
    forecast = make_forecast("DE-LU", root=tmp_path, now=on_time)
    assert len(forecast) == 24 * 3
    assert forecast["before_auction"].all()
    assert forecast["ts_utc"].min() == next_day["ts_utc"].min()

    assert save_forecast(forecast, "DE-LU", root=tmp_path) == 72
    # Running again later must not overwrite the original forecast.
    late = make_forecast("DE-LU", root=tmp_path, now=datetime(2025, 5, 2, tzinfo=timezone.utc))
    assert not late["before_auction"].any()
    assert save_forecast(late, "DE-LU", root=tmp_path) == 0

    assert score_forecasts("DE-LU", root=tmp_path).empty  # no actuals yet
    store.upsert(next_day, "price", "DE-LU", public=True, root=tmp_path)
    scored = score_forecasts("DE-LU", root=tmp_path)
    assert len(scored) == 72
    assert scored["before_auction"].all()
    assert scored["abs_error"].mean() < 30
