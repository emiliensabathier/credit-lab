"""The rank rule, tested on synthetic series with known crossings.

horserace never learns which model produced a column. That is the point: a rule
that cannot tell Altman from Merton cannot favour one of them.
"""

import pandas as pd
import pytest

from clab.horserace import (
    PERSISTENCE_DAYS,
    TRADING_SESSIONS_PER_MONTH,
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


def test_false_alarm_months_counts_only_the_named_controls():
    scores = _scores()
    flags = raw_flags(scores)
    # Pinned rather than asserted positive: `months > 0` would still pass if the
    # function summed every column, used the wrong persistence window, or divided by
    # the wrong constant.
    expected_sessions = sum(
        int((flags[t].astype(float).rolling(PERSISTENCE_DAYS).sum() >= PERSISTENCE_DAYS).sum())
        for t in ("SAFE2", "SAFE3", "SAFE4")
    )
    months = false_alarm_months(flags, controls=["SAFE2", "SAFE3", "SAFE4"])
    assert months == pytest.approx(expected_sessions / TRADING_SESSIONS_PER_MONTH)


def test_false_alarm_months_excludes_names_not_listed_as_controls():
    scores = _scores()
    flags = raw_flags(scores)
    two = false_alarm_months(flags, controls=["SAFE3", "SAFE4"])
    three = false_alarm_months(flags, controls=["SAFE2", "SAFE3", "SAFE4"])
    assert three > two


def test_false_alarm_months_refuses_a_control_with_no_column():
    flags = raw_flags(_scores())
    with pytest.raises(KeyError) as excinfo:
        false_alarm_months(flags, controls=["SAFE2", "NOPE.XX"])
    assert "NOPE.XX" in str(excinfo.value)
