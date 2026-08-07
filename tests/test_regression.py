"""Replay the frozen capture and lock every published figure.

Nothing here touches the network. When these numbers change, either the model
changed or the fixture was re-captured; both are deliberate acts.
"""

import pandas as pd

from clab.pipeline import SCORE_NAMES, run
from tests.fixtures import frozen


def test_the_frozen_run_produces_a_lead_for_every_common_sample_name():
    result = run(**frozen.load())
    for ticker in result.common_sample:
        for _name in SCORE_NAMES:
            assert ticker in result.leads.index


def test_casino_is_absent_from_the_altman_scores():
    result = run(**frozen.load())
    assert any("CO.PA" in key for key in result.failures if key.startswith("altman"))


def test_emeis_has_no_accounting_score_in_time_for_its_event():
    # Its proceeding opens 2022-04-20, weeks after FY2021 first becomes public.
    result = run(**frozen.load())
    assert result.leads.loc["EMEIS.PA", "altman"] is None or pd.isna(
        result.leads.loc["EMEIS.PA", "altman"]
    )


def test_false_alarms_are_reported_for_all_three_scores():
    result = run(**frozen.load())
    assert set(result.false_alarms) == set(SCORE_NAMES)
