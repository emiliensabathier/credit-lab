"""The comparison engine, deliberately blind to which model it is ranking.

Every score arrives as a column of numbers where higher means riskier. A name is
flagged when it sits among the three riskiest of the thirteen and stays there for
twenty sessions.

The alarm is dated to the twentieth session, not the first. An observer only knows
on the twentieth that the condition held; dating it to the first would credit the
score with information that did not exist yet — the same look-ahead this package
spends its point-in-time layer eliminating. The choice costs all three scores one
month, equally.
"""

from __future__ import annotations

import pandas as pd

N_RISKIEST = 3
PERSISTENCE_DAYS = 20
MIN_OBSERVATIONS_BEFORE_EVENT = 60
DAYS_PER_MONTH = 30.44
TRADING_SESSIONS_PER_MONTH = 252 / 12


def raw_flags(scores: pd.DataFrame, n_riskiest: int = N_RISKIEST) -> pd.DataFrame:
    """True where a name is among the `n_riskiest` on that date."""
    ranks = scores.rank(axis=1, ascending=False, method="first")
    return ranks.le(n_riskiest) & scores.notna()


def alarm_date(flags: pd.Series, persistence: int = PERSISTENCE_DAYS) -> pd.Timestamp | None:
    """The first date on which the flag has held for `persistence` sessions."""
    held = flags.fillna(False).astype(float).rolling(persistence).sum()
    confirmed = held[held >= persistence]
    return None if confirmed.empty else confirmed.index[0]


def lead_months(alarm: pd.Timestamp | None, target: pd.Timestamp) -> float | None:
    """Months between an alarm and the target, or None if it never came in time."""
    if alarm is None or alarm >= target:
        return None
    return (target - alarm).days / DAYS_PER_MONTH


def false_alarm_months(
    flags: pd.DataFrame,
    controls: list[str],
    persistence: int = PERSISTENCE_DAYS,
) -> float:
    """Cumulative months the control names spend in a confirmed alarm state.

    A lead time only means something next to this number: a score that flags
    everyone all the time will always look fast.

    Refuses rather than skipping when a requested control has no column. A control
    legitimately has no column when the score refused to compute it for that name;
    callers in that situation are expected to filter their control list themselves
    and publish the refusal, so the omission stays visible instead of quietly
    shrinking the denominator and flattering the score.
    """
    missing = [ticker for ticker in controls if ticker not in flags.columns]
    if missing:
        raise KeyError(f"control names absent from the score frame: {', '.join(missing)}")
    total_sessions = 0
    for ticker in controls:
        column = flags[ticker].fillna(False).astype(float)
        held = column.rolling(persistence).sum() >= persistence
        total_sessions += int(held.sum())
    return total_sessions / TRADING_SESSIONS_PER_MONTH
