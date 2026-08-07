"""Turning a date into money.

Three numbers per score and per name, published on the same row:

- avoided: the fall from the alarm to the target, which is what the lead was worth;
- already_suffered: the fall from the prior peak down to the alarm, which is what the
  lead had already cost by the time it arrived;
- after_target: the fall in the months following the target, which is what the event
  still cost once everyone knew.

An eight-month lead that avoids four percent is worthless. Six months that avoid sixty
change the conclusion. Without these columns the project answers "which flags first"
and never answers "was it worth anything".
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from clab.errors import InsufficientHistoryError


@dataclass(frozen=True)
class Impact:
    avoided: float
    already_suffered: float
    after_target: float


def _at(prices: pd.Series, date: pd.Timestamp) -> float:
    return float(prices.asof(date))


def _nonzero(value: float, label: str) -> float:
    if value == 0:
        raise InsufficientHistoryError(f"{label} price is zero; a relative change is undefined")
    return value


def measure(
    prices: pd.Series,
    alarm: pd.Timestamp,
    target: pd.Timestamp,
    lookback_days: int = 252,
    forward_days: int = 126,
) -> Impact:
    """Three signed relative changes around one alarm and one event.

    Short windows refuse rather than truncate. Reporting a partial forward window as a
    full one would turn "we do not have six months of prices after this event" into
    "the event cost nothing" -- the exact silent failure this package refuses, at the
    one place where it would corrupt the number the project publishes.
    """
    prices = prices.sort_index()
    at_alarm = _nonzero(_at(prices, alarm), "alarm")
    at_target = _nonzero(_at(prices, target), "target")

    window = prices.loc[: pd.Timestamp(alarm)]
    if window.empty:
        raise InsufficientHistoryError(f"no price at or before the alarm date {alarm.date()}")
    peak = _nonzero(float(window.tail(lookback_days).max()), "lookback peak")

    forward = prices.loc[pd.Timestamp(target) :].head(forward_days + 1)
    if len(forward) < forward_days + 1:
        raise InsufficientHistoryError(
            f"only {len(forward)} observations after the target date {target.date()}, "
            f"{forward_days + 1} required; a truncated window would read as a smaller loss"
        )

    return Impact(
        avoided=at_target / at_alarm - 1.0,
        already_suffered=at_alarm / peak - 1.0,
        after_target=float(forward.iloc[-1]) / at_target - 1.0,
    )
