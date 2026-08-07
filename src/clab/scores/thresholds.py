"""The textbook distress levels, kept as a control and never as the headline.

Altman's Z'' distress line sits at 1.1, so on this package's negated orientation the
line is -1.1. Ohlson's model calls a probability above one half distressed, which is
O above zero.

Merton has no equivalent: no distance-to-default level commands consensus. That
absence is itself an argument for ranking rather than thresholding, and this table
leaves the column out rather than inventing a number to fill it.

Both surviving thresholds were calibrated on American industrials of the 1960s and
1970s. Applied to Swedish landlords and a French IT services group, the gap in alarm
frequency they produce measures their unsuitability more than the scores' content.
"""

from __future__ import annotations

import pandas as pd

ALTMAN_DISTRESS = -1.1  # Z'' < 1.1, negated
OHLSON_DISTRESS = 0.0  # probability > 0.5


def academic_flags(scores: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """True on each date where at least one name sits in the textbook distress zone."""
    return pd.DataFrame(
        {
            "altman": (scores["altman"] > ALTMAN_DISTRESS).any(axis=1),
            "ohlson": (scores["ohlson"] > OHLSON_DISTRESS).any(axis=1),
        }
    )
