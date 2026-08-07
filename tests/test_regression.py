"""Replay the frozen capture and lock every published figure.

Nothing here touches the network. When these numbers change, either the model
changed or the fixture was re-captured; both are deliberate acts.
"""

import pandas as pd
import pytest

from clab.pipeline import SCORE_NAMES, run
from tests.fixtures import frozen

EXPECTED_COMMON_SAMPLE: set[str] = {"ADJ.DE", "ATO.PA", "EMEIS.PA", "INTRUM.ST", "SBB-B.ST"}

EXPECTED_FAILURE_KEYS: set[str] = {"altman:CO.PA"}

EXPECTED_FALSE_ALARM_MONTHS: dict[str, float] = {"altman": 0.0, "ohlson": 0.0, "merton": 0.0}

EXPECTED_LEADS: dict[tuple[str, str], float | None] = {
    ("ATO.PA", "altman"): None,
    ("ATO.PA", "ohlson"): None,
    ("ATO.PA", "merton"): 10.808147,
    ("CO.PA", "altman"): None,
    ("CO.PA", "ohlson"): None,
    ("CO.PA", "merton"): None,
    ("EMEIS.PA", "altman"): None,
    ("EMEIS.PA", "ohlson"): None,
    ("EMEIS.PA", "merton"): None,
    ("SBB-B.ST", "altman"): 2.135348,
    ("SBB-B.ST", "ohlson"): None,
    ("SBB-B.ST", "merton"): 13.042050,
    ("ADJ.DE", "altman"): None,
    ("ADJ.DE", "ohlson"): None,
    ("ADJ.DE", "merton"): None,
    ("INTRUM.ST", "altman"): 18.495401,
    ("INTRUM.ST", "ohlson"): 18.495401,
    ("INTRUM.ST", "merton"): None,
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
        assert result.false_alarms[name] == pytest.approx(months, rel=1e-9)
    for (ticker, name), expected in EXPECTED_LEADS.items():
        actual = result.leads.loc[ticker, name]
        if expected is None:
            assert actual is None or pd.isna(actual)
        else:
            assert actual == pytest.approx(expected, rel=1e-6)


def test_casino_is_absent_from_the_altman_scores(frozen_result):
    assert any("CO.PA" in key for key in frozen_result.failures if key.startswith("altman"))


def test_emeis_has_no_accounting_score_in_time_for_its_event(frozen_result):
    # Its proceeding opens 2022-04-20, weeks after FY2021 first becomes public.
    assert frozen_result.leads.loc["EMEIS.PA", "altman"] is None or pd.isna(
        frozen_result.leads.loc["EMEIS.PA", "altman"]
    )


def test_no_control_ever_enters_the_riskiest_three(frozen_result):
    assert set(frozen_result.false_alarms) == set(SCORE_NAMES)
    # Zero across all three, and that is the measured result rather than a placeholder:
    # over the window where the cross-section is rankable, no control name ever reaches
    # the riskiest three under any score. It reads as a clean separation, and it also
    # means the false-alarm counter cannot discriminate between the scores here -- both
    # halves of that belong in the README. The earlier non-zero figure was an artefact
    # of ranking a one-name cross-section, which `raw_flags` now refuses.
    assert all(months == 0.0 for months in frozen_result.false_alarms.values())
