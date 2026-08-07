"""Point-in-time discipline: a statement is unknown until it is published.

The look-ahead test below is the one that matters. It fails the moment someone
indexes a balance sheet by its fiscal year end instead of its publication date,
which is the easiest mistake to make here and the only one that would invalidate
every published figure without leaving a visible trace.
"""

import pandas as pd

from clab.pointintime import PUBLICATION_LAG_DAYS, known_at, step_series


def _annual() -> pd.Series:
    return pd.Series(
        {
            pd.Timestamp("2022-12-31"): 10.0,
            pd.Timestamp("2023-12-31"): 20.0,
            pd.Timestamp("2024-12-31"): 30.0,
        }
    )


def test_known_at_adds_the_publication_lag():
    assert known_at(pd.Timestamp("2023-12-31")) == pd.Timestamp("2023-12-31") + pd.Timedelta(
        days=PUBLICATION_LAG_DAYS
    )


def test_step_series_holds_the_last_published_value():
    index = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    series = step_series(_annual(), index)
    # FY2023 closes 2023-12-31 and is known from 2024-03-30 onward.
    assert series.loc[pd.Timestamp("2024-03-29")] == 10.0
    assert series.loc[pd.Timestamp("2024-03-30")] == 20.0
    assert series.loc[pd.Timestamp("2024-12-31")] == 20.0


def test_step_series_is_empty_before_the_first_publication():
    index = pd.date_range("2023-01-01", "2023-02-01", freq="D")
    series = step_series(_annual(), index)
    assert series.isna().all()


def test_no_value_changes_when_a_future_statement_is_injected():
    """The look-ahead padlock.

    Adding FY2025 to the inputs must not move a single value dated before that
    statement could have been published.
    """
    index = pd.date_range("2024-01-01", "2025-06-30", freq="D")
    baseline = step_series(_annual(), index)

    with_future = _annual().copy()
    with_future[pd.Timestamp("2025-12-31")] = 999.0
    perturbed = step_series(with_future, index)

    pd.testing.assert_series_equal(baseline, perturbed)


def test_a_longer_lag_delays_every_step():
    index = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    late = step_series(_annual(), index, lag_days=120)
    assert late.loc[pd.Timestamp("2024-03-30")] == 10.0
    assert late.loc[pd.Timestamp("2024-04-29")] == 20.0
