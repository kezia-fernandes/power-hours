import numpy as np
import pytest

from powerhours.window import best_window, window_costs, window_regret


def test_best_window_finds_cheapest_block():
    prices = [50, 40, 10, 12, 60, 5]
    assert best_window(prices, 2) == 2  # hours 2-3 cost 11 on average
    assert best_window(prices, 1) == 5


def test_window_costs_length():
    assert len(window_costs(np.arange(24), 3)) == 22


def test_invalid_duration():
    with pytest.raises(ValueError):
        window_costs([1, 2, 3], 0)


def test_regret_is_zero_for_perfect_forecast_and_positive_for_wrong_one():
    actual = np.array([50, 40, 10, 12, 60, 5.0])
    assert window_regret(actual, actual, 2) == 0
    wrong = np.array([1, 1, 9, 9, 9, 9.0])  # recommends hours 0-1, which really cost 45
    assert window_regret(actual, wrong, 2) == pytest.approx(45 - 11)
