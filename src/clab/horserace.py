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

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

N_RISKIEST = 3
PERSISTENCE_DAYS = 20
MIN_OBSERVATIONS_BEFORE_EVENT = 60
DAYS_PER_MONTH = 30.44
TRADING_SESSIONS_PER_MONTH = 252 / 12

# The four outcomes a (score, event) pair can have. Keeping "untestable" apart from
# "missed" is the whole point: a score cannot be blamed for missing an event that
# happened before it had enough ranked history to flag anything, and a lead that
# starts on the first date an alarm was even possible is a lower bound, not a
# measurement.
MEASURED = "measured"
CENSORED = "censored"
MISSED = "missed"
UNTESTABLE = "untestable"


@dataclass(frozen=True)
class Lead:
    months: float | None
    status: str


def raw_flags(scores: pd.DataFrame, n_riskiest: int = N_RISKIEST) -> pd.DataFrame:
    """True where a name is among the `n_riskiest` on that date.

    A date only counts once at least `2 * n_riskiest` names carry a score, so the
    flagged set is never more than half the ranked cross-section. Below that the rule
    stops selecting and starts describing whoever happens to have data: in the first
    quarter of 2023 exactly one company in the universe has a published score --
    Siemens, whose fiscal year ends in September and who therefore reports before
    anyone else -- and "the three riskiest of thirteen" would flag it for want of a
    rival. That is not a hypothetical: it produced 2.24 months of identical false
    alarms across all three scores, every one of them an artefact of coverage.
    """
    ranks = scores.rank(axis=1, ascending=False, method="first")
    return ranks.le(n_riskiest) & eligible(scores, n_riskiest)


def eligible(scores: pd.DataFrame, n_riskiest: int = N_RISKIEST) -> pd.DataFrame:
    """True where a name carries a score on a date whose cross-section is rankable.

    These are the only sessions on which `raw_flags` could flag the name at all, so
    they bound what any alarm can say: no alarm can predate the `persistence`-th of
    them.
    """
    rankable = scores.notna().sum(axis=1) >= 2 * n_riskiest
    return scores.notna() & rankable.to_numpy()[:, None]


def exclude_after(scores: pd.DataFrame, defaults: Mapping[str, pd.Timestamp]) -> pd.DataFrame:
    """A copy of `scores` with each name blanked from its default date onwards.

    A name already in default is not a forecast target any more. Left in the ranking
    it occupies one of the riskiest slots for the rest of the window and pushes a
    live name out, which would both delay real alarms and hide false ones.
    """
    masked = scores.copy()
    for ticker, date in defaults.items():
        if ticker in masked.columns:
            masked.loc[masked.index >= date, ticker] = float("nan")
    return masked


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


def classify_lead(
    flags: pd.Series,
    eligible_sessions: pd.Series,
    target: pd.Timestamp,
    persistence: int = PERSISTENCE_DAYS,
    min_observations: int = MIN_OBSERVATIONS_BEFORE_EVENT,
) -> Lead:
    """Lead time and status of one score against one event.

    - untestable: fewer than `min_observations` eligible sessions before the target,
      so the score never had a fair chance to flag the name;
    - missed: testable, and no alarm came before the target;
    - censored: the alarm fired on the first date an alarm was possible, so the true
      lead is at least the measured one and possibly much longer;
    - measured: the alarm fired later than that, so the lead is a real measurement.
    """
    observed = int(eligible_sessions[eligible_sessions.index < target].sum())
    if observed < min_observations:
        return Lead(None, UNTESTABLE)
    alarm = alarm_date(flags, persistence)
    months = lead_months(alarm, target)
    if months is None:
        return Lead(None, MISSED)
    first_possible = alarm_date(eligible_sessions, persistence)
    return Lead(months, CENSORED if alarm == first_possible else MEASURED)


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


def forced_control_months(
    eligible_sessions: pd.DataFrame,
    stressed: list[str],
    n_riskiest: int = N_RISKIEST,
) -> float:
    """Control-name months the rank rule flags by arithmetic alone.

    A rank rule flags `n_riskiest` names on every rankable date. When fewer stressed
    names than that are still alive and scored, the remaining slots go to controls
    whatever the score says. This is the floor under any false-alarm count from this
    rule (before the persistence filter), and publishing it beside the count is what
    keeps the count from being read as a property of the score.
    """
    rankable = eligible_sessions.any(axis=1)
    present = [ticker for ticker in stressed if ticker in eligible_sessions.columns]
    alive = eligible_sessions[present].sum(axis=1)
    forced = (n_riskiest - alive).clip(lower=0)[rankable]
    return float(forced.sum()) / TRADING_SESSIONS_PER_MONTH
