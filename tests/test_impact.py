"""What the lead time was worth, and what it was not.

`already_suffered` is the guard rail: a score that only fires after the stock has
halved shows a long lead and no value, and the two numbers sit on the same row.
"""

import pandas as pd
import pytest

from clab.errors import InsufficientHistoryError
from clab.impact import measure


def _prices() -> pd.Series:
    """A price that peaks at 100 and falls by 0.4 a session for 200 sessions, then flattens."""
    index = pd.date_range("2023-01-02", periods=400, freq="B")
    falling = [100.0 - 0.4 * step for step in range(200)]
    return pd.Series(falling + [falling[-1]] * 200, index=index)


def test_avoided_is_the_fall_between_alarm_and_target():
    prices = pd.Series(
        [100.0, 80.0, 50.0, 50.0],
        index=[pd.Timestamp("2023-01-02"), pd.Timestamp("2023-06-01"),
               pd.Timestamp("2023-12-01"), pd.Timestamp("2023-12-04")],
    )
    result = measure(prices, pd.Timestamp("2023-06-01"), pd.Timestamp("2023-12-01"),
                     lookback_days=1, forward_days=1)
    assert result.avoided == pytest.approx(-0.375)


def test_already_suffered_is_pinned_to_the_peak_of_the_lookback_window():
    prices = _prices()
    alarm, target = prices.index[150], prices.index[250]
    # The lookback is 252 sessions but only 151 exist before the alarm, so the peak is
    # the series maximum, 100.0, and the alarm price is 100 - 0.4*150 = 40.0.
    assert measure(prices, alarm, target).already_suffered == pytest.approx(40.0 / 100.0 - 1.0)


def test_a_short_lookback_window_raises_the_peak_it_can_see():
    prices = _prices()
    alarm, target = prices.index[150], prices.index[250]
    # Only the ten sessions before the alarm: the peak is 100 - 0.4*141 = 43.6, so the
    # measured fall is far smaller than against the all-time high. This is the test the
    # default-window version cannot perform, because 252 never truncates on this fixture.
    short = measure(prices, alarm, target, lookback_days=10)
    assert short.already_suffered == pytest.approx(40.0 / 43.6 - 1.0)
    assert short.already_suffered > measure(prices, alarm, target).already_suffered


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
        [100.0, 50.0, 50.0, 50.0],
        index=[pd.Timestamp("2023-01-02"), pd.Timestamp("2023-02-01"),
               pd.Timestamp("2023-02-20"), pd.Timestamp("2023-02-21")],
    )
    result = measure(prices, pd.Timestamp("2023-01-15"), pd.Timestamp("2023-02-15"),
                     lookback_days=1, forward_days=1)
    assert result.avoided == pytest.approx(-0.5)


def test_measure_refuses_a_truncated_forward_window():
    prices = _prices()
    with pytest.raises(InsufficientHistoryError) as excinfo:
        measure(prices, prices.index[0], prices.index[-3], forward_days=126)
    assert "127 required" in str(excinfo.value)


def test_measure_refuses_a_zero_price():
    index = pd.date_range("2023-01-02", periods=200, freq="B")
    prices = pd.Series([0.0] * 200, index=index)
    with pytest.raises(InsufficientHistoryError):
        measure(prices, index[10], index[20], forward_days=10)
