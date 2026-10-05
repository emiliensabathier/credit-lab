"""Replay the frozen capture and lock every published figure.

Nothing here touches the network. When these numbers change, either the model
changed or the fixture was re-captured; both are deliberate acts.
"""

import pandas as pd
import pytest

from clab.horserace import CENSORED, MEASURED, UNTESTABLE
from clab.pipeline import NO_SCORE, SCORE_NAMES, run
from tests.fixtures import frozen

EXPECTED_COMMON_SAMPLE: set[str] = {"ATO.PA", "INTRUM.ST", "SBB-B.ST"}

EXPECTED_FAILURE_KEYS: set[str] = {"altman:CO.PA"}

# Counted up to the last credit event, next to the floor the rank rule forces on its own.
EXPECTED_FALSE_ALARM_MONTHS: dict[str, float] = {
    "altman": 10.666667,
    "ohlson": 10.523810,
    "merton": 21.047619,
}
EXPECTED_FORCED_MONTHS: dict[str, float] = {
    "altman": 12.476190,
    "ohlson": 12.476190,
    "merton": 12.476190,
}

U, C, M = UNTESTABLE, CENSORED, MEASURED

EXPECTED_LEADS: dict[tuple[str, str], tuple[float | None, str]] = {
    ("ATO.PA", "altman"): (10.545335, M),
    ("ATO.PA", "ohlson"): (10.808147, C),
    ("ATO.PA", "merton"): (10.808147, C),
    ("CO.PA", "altman"): (None, NO_SCORE),
    ("CO.PA", "ohlson"): (None, U),
    ("CO.PA", "merton"): (None, U),
    ("EMEIS.PA", "altman"): (None, U),
    ("EMEIS.PA", "ohlson"): (None, U),
    ("EMEIS.PA", "merton"): (None, U),
    ("SBB-B.ST", "altman"): (14.060447, C),
    ("SBB-B.ST", "ohlson"): (12.385020, M),
    ("SBB-B.ST", "merton"): (14.060447, C),
    ("ADJ.DE", "altman"): (None, U),
    ("ADJ.DE", "ohlson"): (None, U),
    ("ADJ.DE", "merton"): (None, U),
    ("INTRUM.ST", "altman"): (18.495401, C),
    ("INTRUM.ST", "ohlson"): (18.495401, C),
    ("INTRUM.ST", "merton"): (7.128778, M),
}


@pytest.fixture(scope="module")
def frozen_result():
    """One pipeline run, shared by every test here.

    All five tests interrogate the same frozen replay; rebuilding the scores per test
    turned a four-minute file into a twenty-minute one for no additional coverage.
    """
    return run(**frozen.load())


def test_the_fixture_round_trips_statement_column_types():
    loaded = frozen.load()["loaded"]["MC.PA"]
    assert isinstance(loaded.balance_sheet.columns, pd.DatetimeIndex)
    assert isinstance(loaded.income.columns, pd.DatetimeIndex)
    assert isinstance(loaded.cashflow.columns, pd.DatetimeIndex)
    assert isinstance(loaded.prices.index, pd.DatetimeIndex)


def test_the_frozen_run_pins_its_published_figures(frozen_result):
    """The point of this file: lock the numbers, not merely prove the code runs.

    `run()` puts every stressed ticker in `leads.index` unconditionally, and
    `false_alarms` always carries the three score names, so asserting on either shape
    tests nothing. These expectations are the figures the frozen capture actually
    produced; when they change, either the model changed or the fixture was
    re-captured, and both are deliberate acts that should have to be re-stated here.
    """
    result = frozen_result

    assert set(result.common_sample) == EXPECTED_COMMON_SAMPLE
    assert set(result.failures) == EXPECTED_FAILURE_KEYS
    for name, months in EXPECTED_FALSE_ALARM_MONTHS.items():
        assert result.false_alarms[name] == pytest.approx(months, rel=1e-6)
    for name, months in EXPECTED_FORCED_MONTHS.items():
        assert result.forced_false_alarms[name] == pytest.approx(months, rel=1e-6)
    for (ticker, name), (expected, status) in EXPECTED_LEADS.items():
        actual = result.leads.loc[ticker, name]
        assert result.status.loc[ticker, name] == status, (ticker, name)
        if expected is None:
            assert pd.isna(actual)
        else:
            assert actual == pytest.approx(expected, rel=1e-6)


def test_casino_is_absent_from_the_altman_scores(frozen_result):
    assert any("CO.PA" in key for key in frozen_result.failures if key.startswith("altman"))


def test_events_before_the_accounts_begin_are_untestable(frozen_result):
    # The data source carries annual accounts from FY2022 on (FY2021 is all but empty),
    # first public on 2023-03-31 under the ninety-day lag. Emeis (2022-04-20) and Adler
    # (2023-04-12) default before or days after that; Casino (2023-05-26) leaves only
    # 37 ranked sessions. None of the three can be tested, under any score.
    for ticker in ("EMEIS.PA", "ADJ.DE"):
        assert (frozen_result.status.loc[ticker] == UNTESTABLE).all()
    assert set(frozen_result.status.loc["CO.PA"]) == {UNTESTABLE, NO_SCORE}


def test_false_alarms_above_the_forced_floor_come_from_merton_only(frozen_result):
    assert set(frozen_result.false_alarms) == set(SCORE_NAMES)
    # Altman and Ohlson never flag a control beyond the slots the rule hands to
    # controls once fewer than three stressed names are alive; Merton does, by about
    # eight and a half control-months. That is the one place the false-alarm count
    # discriminates between the scores on this sample.
    for name in ("altman", "ohlson"):
        assert frozen_result.false_alarms[name] <= frozen_result.forced_false_alarms[name]
    assert frozen_result.false_alarms["merton"] > frozen_result.forced_false_alarms["merton"]
