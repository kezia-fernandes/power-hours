"""The green question: are the cheapest hours also the greenest?

"Green" here means the renewable share of load: how much of the electricity being
consumed in an hour is covered by renewable generation, in percent. It can exceed
100 when Germany produces more renewable power than it uses and exports the rest.
"""

from __future__ import annotations

import pandas as pd

from powerhours.features import to_matrix
from powerhours.window import best_window, window_means

SHARE_SERIES = "renewable_share_of_load"


def share_matrix(power: pd.DataFrame, timezone: str) -> pd.DataFrame:
    """Day x hour table of the actual renewable share of load (percent)."""
    return to_matrix(power, SHARE_SERIES, timezone)


def cheap_vs_green(prices: pd.DataFrame, shares: pd.DataFrame, duration: int = 2) -> pd.DataFrame:
    """For each day, compare the cheapest window with the greenest window.

    Both inputs are day x hour tables. One output row per day:
        cheap_start, green_start      start hours of the two windows
        overlap_hours                 how many hours the two windows share
        price_cheapest, price_green   average price in each window (EUR/MWh)
        share_cheapest, share_green   average renewable share in each window (%)
    """
    days = prices.index.intersection(shares.index)
    rows = []
    for day in days:
        price, share = prices.loc[day].to_numpy(), shares.loc[day].to_numpy()
        cheap = best_window(price, duration)
        green = best_window(share, duration, largest=True)
        price_means, share_means = window_means(price, duration), window_means(share, duration)
        rows.append(
            {
                "date": day,
                "cheap_start": cheap,
                "green_start": green,
                "overlap_hours": max(0, duration - abs(cheap - green)),
                "price_cheapest": price_means[cheap],
                "price_green": price_means[green],
                "share_cheapest": share_means[cheap],
                "share_green": share_means[green],
            }
        )
    return pd.DataFrame(rows)


def summarize_cheap_vs_green(comparison: pd.DataFrame) -> dict:
    """Headline numbers for the comparison."""
    if comparison.empty:
        return {}
    return {
        "days": int(len(comparison)),
        "share_of_days_overlapping": float((comparison["overlap_hours"] > 0).mean()),
        "share_of_days_identical": float(
            (comparison["cheap_start"] == comparison["green_start"]).mean()
        ),
        "avg_extra_price_for_green": float(
            (comparison["price_green"] - comparison["price_cheapest"]).mean()
        ),
        "avg_share_lost_by_cheap": float(
            (comparison["share_green"] - comparison["share_cheapest"]).mean()
        ),
    }


def price_by_share_bucket(
    prices: pd.DataFrame, shares: pd.DataFrame, edges=(0, 20, 40, 60, 80, 100, 1000)
) -> pd.DataFrame:
    """Average price per band of renewable share, over all hours.

    Answers "how much cheaper is electricity when the grid is green?".
    """
    days = prices.index.intersection(shares.index)
    hours = pd.DataFrame(
        {
            "price": prices.loc[days].to_numpy().ravel(),
            "share": shares.loc[days].to_numpy().ravel(),
        }
    ).dropna()
    labels = [
        f"{low}-{high}%" if high <= 100 else f"over {low}%"
        for low, high in zip(edges[:-1], edges[1:], strict=True)
    ]
    hours["bucket"] = pd.cut(hours["share"], bins=list(edges), labels=labels, right=False)
    table = hours.groupby("bucket", observed=True)["price"].agg(avg_price="mean", hours="count")
    table = table.reset_index()
    table.attrs["correlation"] = float(hours["price"].corr(hours["share"]))
    return table
