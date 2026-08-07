"""What the lead time was worth, and what it was not.

`already_suffered` is the guard rail: a score that only fires after the stock has
halved shows a long lead and no value, and the two numbers sit on the same row.
"""

import pandas as pd
import pytest

from clab.impact import measure


def _prices() -> pd.Series:
    """A price that peaks at 100, falls steadily to 20, then flattens."""
    index = pd.date_range("2023-01-02", periods=400, freq="B")
    falling = [100.0 - 0.4 * step for step in range(200)]
    return pd.Series(falling + [20.0] * 200, index=index)


def test_avoided_is_the_fall_between_alarm_and_target():
    prices = pd.Series(
        [100.0, 80.0, 50.0],
        index=[pd.Timestamp("2023-01-02"), pd.Timestamp("2023-06-01"),
               pd.Timestamp("2023-12-01")],
    )
    result = measure(prices, pd.Timestamp("2023-06-01"), pd.Timestamp("2023-12-01"),
                     lookback_days=1, forward_days=1)
    assert result.avoided == pytest.approx(-0.375)


def test_already_suffered_measures_the_fall_from_the_prior_peak():
    prices = _prices()
    alarm = prices.index[150]
    target = prices.index[250]
    result = measure(prices, alarm, target)
    assert result.already_suffered < 0


def test_after_target_covers_the_forward_window():
    prices = pd.Series(
        [100.0] * 10 + [40.0] * 10,
        index=pd.date_range("2023-01-02", periods=20, freq="B"),
    )
    result = measure(prices, prices.index[0], prices.index[5],
                     lookback_days=2, forward_days=10)
    assert result.after_target == pytest.approx(-0.6)


def test_measure_uses_the_last_price_at_or_before_each_date():
    prices = pd.Series(
        [100.0, 50.0],
        index=[pd.Timestamp("2023-01-02"), pd.Timestamp("2023-02-01")],
    )
    result = measure(prices, pd.Timestamp("2023-01-15"), pd.Timestamp("2023-02-15"),
                     lookback_days=1, forward_days=1)
    assert result.avoided == pytest.approx(-0.5)
