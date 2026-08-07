"""The rank rule, tested on synthetic series with known crossings.

horserace never learns which model produced a column. That is the point: a rule
that cannot tell Altman from Merton cannot favour one of them.
"""

import pandas as pd
import pytest

from clab.horserace import (
    PERSISTENCE_DAYS,
    alarm_date,
    false_alarm_months,
    lead_months,
    raw_flags,
)


def _scores() -> pd.DataFrame:
    index = pd.date_range("2023-01-02", periods=100, freq="B")
    frame = pd.DataFrame(index=index)
    frame["SAFE1"] = 0.0
    frame["SAFE2"] = 0.1
    frame["SAFE3"] = 0.2
    frame["SAFE4"] = 0.3
    frame["RISKY"] = [0.05] * 30 + [9.0] * 70  # crosses into the top three at row 30
    return frame


def test_raw_flags_marks_exactly_the_three_riskiest_each_day():
    flags = raw_flags(_scores())
    assert flags.sum(axis=1).unique().tolist() == [3]


def test_alarm_date_is_the_twentieth_session_of_the_run_not_the_first():
    scores = _scores()
    flags = raw_flags(scores)
    alarm = alarm_date(flags["RISKY"])
    # The run starts at positional index 30; confirmation lands 19 sessions later.
    assert alarm == scores.index[30 + PERSISTENCE_DAYS - 1]


def test_alarm_date_is_none_when_the_flag_never_persists():
    index = pd.date_range("2023-01-02", periods=50, freq="B")
    flickering = pd.Series([True, False] * 25, index=index)
    assert alarm_date(flickering) is None


def test_lead_months_is_positive_when_the_alarm_precedes_the_target():
    alarm = pd.Timestamp("2023-01-01")
    target = pd.Timestamp("2023-07-02")
    assert lead_months(alarm, target) == pytest.approx(6.0, abs=0.1)


def test_lead_months_is_none_when_the_alarm_follows_the_target():
    assert lead_months(pd.Timestamp("2024-01-01"), pd.Timestamp("2023-01-01")) is None


def test_lead_months_is_none_when_there_was_no_alarm():
    assert lead_months(None, pd.Timestamp("2023-01-01")) is None


def test_false_alarm_months_counts_control_names_in_the_riskiest_bucket():
    scores = _scores()
    flags = raw_flags(scores)
    # SAFE2, SAFE3, SAFE4 sit in the top three for the first 30 rows.
    months = false_alarm_months(flags, controls=["SAFE2", "SAFE3", "SAFE4"])
    assert months > 0
