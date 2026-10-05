"""The rank rule, tested on synthetic series with known crossings.

horserace never learns which model produced a column. That is the point: a rule
that cannot tell Altman from Merton cannot favour one of them.
"""

import pandas as pd
import pytest

from clab.horserace import (
    CENSORED,
    MEASURED,
    MISSED,
    PERSISTENCE_DAYS,
    TRADING_SESSIONS_PER_MONTH,
    UNTESTABLE,
    alarm_date,
    classify_lead,
    eligible,
    exclude_after,
    false_alarm_months,
    forced_control_months,
    lead_months,
    raw_flags,
)


def _scores() -> pd.DataFrame:
    index = pd.date_range("2023-01-02", periods=100, freq="B")
    frame = pd.DataFrame(index=index)
    # Six always-populated names, one more than 2 * N_RISKIEST, so every date in this
    # fixture clears the rankability floor and the tests below exercise the ranking
    # rule itself rather than tripping the sparse-cross-section guard.
    frame["SAFE0"] = -0.1
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


def test_a_sparse_cross_section_flags_nobody():
    index = pd.date_range("2023-01-02", periods=40, freq="B")
    sparse = pd.DataFrame(index=index)
    sparse["ONLY"] = 5.0
    for filler in ("A", "B", "C", "D"):
        sparse[filler] = float("nan")
    # Five columns, one with data: ranking three of them would be a tautology, not a
    # selection, so nothing may be flagged.
    assert not raw_flags(sparse).to_numpy().any()


def test_the_cross_section_becomes_rankable_once_enough_names_have_scores():
    index = pd.date_range("2023-01-02", periods=40, freq="B")
    frame = pd.DataFrame(index=index)
    for position, name in enumerate(("A", "B", "C", "D", "E", "F")):
        frame[name] = float(position)
    frame.loc[frame.index[:20], ["E", "F"]] = float("nan")
    flags = raw_flags(frame)
    # First twenty sessions: four names with scores, below 2 * N_RISKIEST -> no flags.
    assert not flags.iloc[:20].to_numpy().any()
    # After that all six carry scores, so the three riskiest are flagged.
    assert flags.iloc[20:].sum(axis=1).unique().tolist() == [3]


def _eligible_from(index: pd.DatetimeIndex, start: int) -> pd.Series:
    return pd.Series([False] * start + [True] * (len(index) - start), index=index)


def test_an_event_with_too_little_rankable_history_is_untestable_not_missed():
    index = pd.date_range("2023-01-02", periods=100, freq="B")
    eligible = _eligible_from(index, 80)
    flags = eligible.copy()
    # Twenty eligible sessions before the target: fewer than the sixty required, so the
    # score never had a fair chance and must not be scored as having missed.
    lead = classify_lead(flags, eligible, index[99], persistence=PERSISTENCE_DAYS)
    assert lead.status == UNTESTABLE
    assert lead.months is None


def test_an_alarm_on_the_first_possible_date_is_censored():
    index = pd.date_range("2023-01-02", periods=200, freq="B")
    eligible = _eligible_from(index, 10)
    flags = eligible.copy()
    lead = classify_lead(flags, eligible, index[-1], persistence=PERSISTENCE_DAYS)
    # Flagged from the first rankable session, so the measured lead is a lower bound.
    assert lead.status == CENSORED
    assert lead.months == pytest.approx(lead_months(index[10 + PERSISTENCE_DAYS - 1], index[-1]))


def test_an_alarm_after_the_first_possible_date_is_measured():
    index = pd.date_range("2023-01-02", periods=200, freq="B")
    eligible = _eligible_from(index, 10)
    flags = _eligible_from(index, 100)
    lead = classify_lead(flags, eligible, index[-1], persistence=PERSISTENCE_DAYS)
    assert lead.status == MEASURED
    assert lead.months == pytest.approx(lead_months(index[100 + PERSISTENCE_DAYS - 1], index[-1]))


def test_a_testable_event_with_no_alarm_in_time_is_missed():
    index = pd.date_range("2023-01-02", periods=200, freq="B")
    eligible = _eligible_from(index, 10)
    flags = pd.Series(False, index=index)
    lead = classify_lead(flags, eligible, index[-1], persistence=PERSISTENCE_DAYS)
    assert lead.status == MISSED
    assert lead.months is None


def test_eligibility_requires_a_score_and_a_rankable_cross_section():
    index = pd.date_range("2023-01-02", periods=40, freq="B")
    frame = pd.DataFrame({name: float(i) for i, name in enumerate("ABCDEF")}, index=index)
    frame.loc[frame.index[:20], ["E", "F"]] = float("nan")
    mask = eligible(frame)
    assert not mask.iloc[:20].to_numpy().any()
    assert mask.iloc[20:].to_numpy().all()


def test_names_are_dropped_from_the_ranking_from_their_default_date():
    index = pd.date_range("2023-01-02", periods=10, freq="B")
    frame = pd.DataFrame({"X": 1.0, "Y": 2.0}, index=index)
    masked = exclude_after(frame, {"X": index[4], "NOT.IN.FRAME": index[0]})
    assert masked["X"].iloc[:4].notna().all()
    assert masked["X"].iloc[4:].isna().all()
    assert masked["Y"].notna().all()
    # Immutability: the input frame is left untouched.
    assert frame["X"].notna().all()


def test_forced_control_months_counts_the_slots_stressed_names_cannot_fill():
    index = pd.date_range("2023-01-02", periods=42, freq="B")
    eligible_sessions = pd.DataFrame(
        {"S1": True, "S2": [True] * 21 + [False] * 21, "C1": True, "C2": True}, index=index
    )
    # Three slots. Two stressed names alive for 21 sessions force one control in; one
    # alive for the next 21 forces two: 21 + 42 = 63 control-sessions, three months.
    months = forced_control_months(eligible_sessions, stressed=["S1", "S2"], n_riskiest=3)
    assert months == pytest.approx(63 / TRADING_SESSIONS_PER_MONTH)


def test_forced_control_months_ignores_dates_that_are_not_rankable():
    index = pd.date_range("2023-01-02", periods=10, freq="B")
    eligible_sessions = pd.DataFrame({"S1": False, "C1": False}, index=index)
    assert forced_control_months(eligible_sessions, stressed=["S1"], n_riskiest=3) == 0.0
