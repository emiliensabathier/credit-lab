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


@dataclass(frozen=True)
class Impact:
    avoided: float
    already_suffered: float
    after_target: float


def _at(prices: pd.Series, date: pd.Timestamp) -> float:
    return float(prices.asof(date))


def measure(
    prices: pd.Series,
    alarm: pd.Timestamp,
    target: pd.Timestamp,
    lookback_days: int = 252,
    forward_days: int = 126,
) -> Impact:
    prices = prices.sort_index()
    at_alarm = _at(prices, alarm)
    at_target = _at(prices, target)

    window = prices.loc[: pd.Timestamp(alarm)].tail(lookback_days)
    peak = float(window.max()) if not window.empty else at_alarm

    forward = prices.loc[pd.Timestamp(target) :].head(forward_days + 1)
    at_forward = float(forward.iloc[-1]) if not forward.empty else at_target

    return Impact(
        avoided=at_target / at_alarm - 1.0,
        already_suffered=at_alarm / peak - 1.0,
        after_target=at_forward / at_target - 1.0,
    )
