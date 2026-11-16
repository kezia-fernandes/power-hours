"""The washing machine question: which block of hours is cheapest?"""

from __future__ import annotations

import numpy as np


def window_costs(prices, duration: int) -> np.ndarray:
    """Average price of every block of `duration` consecutive hours.

    Element i is the average over hours i .. i+duration-1.
    """
    prices = np.asarray(prices, dtype=float)
    if not 1 <= duration <= len(prices):
        raise ValueError("duration must be between 1 and the number of hours")
    sums = np.convolve(prices, np.ones(duration), mode="valid")
    return sums / duration


def best_window(prices, duration: int = 2) -> int:
    """Start hour of the cheapest block of `duration` hours."""
    return int(np.argmin(window_costs(prices, duration)))


def window_regret(actual, predicted, duration: int = 2) -> float:
    """How much more you pay by trusting the forecast instead of knowing the future.

    We pick the cheapest window according to `predicted`, then look at what that
    window really cost and compare it with the truly cheapest window.
    0 means the forecast found the best window. Unit: same as the prices (EUR/MWh).
    """
    actual_costs = window_costs(actual, duration)
    return float(actual_costs[best_window(predicted, duration)] - actual_costs.min())
