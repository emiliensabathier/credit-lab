"""Turning annual statements into series that only know what was public at the time.

An annual report closed on 31 December is not available on 31 December. Using it to
"predict" an event in the following March is look-ahead, and it leaves no trace in
the output: it simply makes every score look better than it was.

The lag is uniform rather than per-company. A hand-collected set of real publication
dates would be more accurate, but a uniform lag has a property that matters more
here: applied identically to every name and every year, it cannot favour one score
over another. Robustness at 60 and 120 days is published alongside the headline.
"""

from __future__ import annotations

import pandas as pd

PUBLICATION_LAG_DAYS = 90


def known_at(fiscal_end: pd.Timestamp, lag_days: int = PUBLICATION_LAG_DAYS) -> pd.Timestamp:
    """The date a statement closed on `fiscal_end` is treated as public."""
    return pd.Timestamp(fiscal_end) + pd.Timedelta(days=lag_days)


def step_series(
    annual: pd.Series,
    index: pd.DatetimeIndex,
    lag_days: int = PUBLICATION_LAG_DAYS,
) -> pd.Series:
    """Expand annual figures onto `index`, each value starting at its publication date.

    Dates before the first publication are NaN, not back-filled: nothing was known
    then, and inventing a value would be the whole error this module exists to stop.
    """
    published = pd.Series(
        annual.to_numpy(),
        index=[known_at(end, lag_days) for end in annual.index],
    ).sort_index()
    published = published[~published.index.duplicated(keep="last")]
    return published.reindex(published.index.union(index)).ffill().reindex(index)
