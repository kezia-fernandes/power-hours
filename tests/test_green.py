import pandas as pd

from powerhours.green import cheap_vs_green, price_by_share_bucket, summarize_cheap_vs_green


def _tables():
    days = pd.date_range("2025-06-01", periods=2)
    # Day 1: cheap and green coincide at hours 12-13. Day 2: cheap at 2-3, green at 12-13.
    price = pd.DataFrame(100.0, index=days, columns=range(24))
    share = pd.DataFrame(30.0, index=days, columns=range(24))
    price.loc[days[0], [12, 13]] = 10
    share.loc[days[0], [12, 13]] = 95
    price.loc[days[1], [2, 3]] = 20
    share.loc[days[1], [12, 13]] = 90
    return price, share


def test_cheap_vs_green_per_day():
    result = cheap_vs_green(*_tables(), duration=2).set_index("date")
    first, second = result.iloc[0], result.iloc[1]
    assert (first["cheap_start"], first["green_start"], first["overlap_hours"]) == (12, 12, 2)
    assert (second["cheap_start"], second["green_start"], second["overlap_hours"]) == (2, 12, 0)
    assert second["price_green"] - second["price_cheapest"] == 80
    assert second["share_green"] - second["share_cheapest"] == 60


def test_summary():
    summary = summarize_cheap_vs_green(cheap_vs_green(*_tables(), duration=2))
    assert summary["days"] == 2
    assert summary["share_of_days_identical"] == 0.5
    assert summary["avg_extra_price_for_green"] == 40
    assert summarize_cheap_vs_green(pd.DataFrame()) == {}


def test_price_by_share_bucket():
    table = price_by_share_bucket(*_tables())
    assert table["hours"].sum() == 48
    by_bucket = table.set_index("bucket")["avg_price"]
    assert by_bucket["80-100%"] < by_bucket["20-40%"]
    assert table.attrs["correlation"] < 0
