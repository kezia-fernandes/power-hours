"""The washing machine question: which block of hours is best?"""

from __future__ import annotations

import numpy as np


def window_means(values, duration: int) -> np.ndarray:
    """Average of every block of `duration` consecutive hours.

    Element i is the average over hours i .. i+duration-1.
    """
    values = np.asarray(values, dtype=float)
    if not 1 <= duration <= len(values):
        raise ValueError("duration must be between 1 and the number of hours")
    return np.convolve(values, np.ones(duration), mode="valid") / duration


window_costs = window_means  # the same thing when the values are prices


def best_window(values, duration: int = 2, largest: bool = False) -> int:
    """Start hour of the block of `duration` hours with the lowest average.

    With largest=True it returns the block with the highest average instead
    (used for "greenest hours", where more renewable share is better).
    """
    means = window_means(values, duration)
    return int(np.argmax(means) if largest else np.argmin(means))


def window_regret(actual, predicted, duration: int = 2) -> float:
    """How much more you pay by trusting the forecast instead of knowing the future.

    We pick the cheapest window according to `predicted`, then look at what that
    window really cost and compare it with the truly cheapest window.
    0 means the forecast found the best window. Unit: same as the prices (EUR/MWh).
    """
    actual_costs = window_means(actual, duration)
    return float(actual_costs[best_window(predicted, duration)] - actual_costs.min())
