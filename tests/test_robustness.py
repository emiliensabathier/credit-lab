"""Robustness, the secondary target, and the textbook thresholds kept as a control."""

import pandas as pd

from clab.pipeline import SCORE_NAMES, VARIANTS, robustness, run
from clab.scores.thresholds import ALTMAN_DISTRESS, academic_flags
from tests.conftest import synthetic_inputs


def test_robustness_reports_one_row_per_variant():
    table = robustness(**synthetic_inputs())
    assert len(table) == len(VARIANTS)
    assert set(SCORE_NAMES).issubset(table.columns)


def test_variants_cover_the_two_conventions_named_in_the_spec():
    lags = {variant["lag_days"] for variant in VARIANTS}
    persistences = {variant["persistence"] for variant in VARIANTS}
    widths = {variant["n_riskiest"] for variant in VARIANTS}
    assert {60, 90, 120}.issubset(lags)
    assert {10, 20, 40}.issubset(persistences)
    assert {3, 4}.issubset(widths)


def test_secondary_leads_cover_only_the_two_fallen_angels():
    result = run(**synthetic_inputs())
    assert sorted(result.secondary.index) == ["ATO.PA", "SBB-B.ST"]


def test_academic_flags_use_the_published_distress_levels():
    scores = {
        "altman": pd.DataFrame({"X.PA": [-2.0, -0.5]}),
        "ohlson": pd.DataFrame({"X.PA": [1.0, -1.0]}),
        "merton": pd.DataFrame({"X.PA": [1.0, -1.0]}),
    }
    flags = academic_flags(scores)
    # -Z'' of -2.0 means Z'' = 2.0, above the 1.1 distress line: not flagged.
    assert not bool(flags.loc[0, "altman"])
    assert bool(flags.loc[1, "altman"])
    assert ALTMAN_DISTRESS == -1.1
    # Merton has no consensus threshold and must be absent from this control table.
    assert "merton" not in flags.columns


def test_a_name_without_enough_history_before_its_event_is_recorded():
    result = run(**synthetic_inputs())
    # Emeis' proceeding opens 2022-04-20, before any statement in the fixture has been
    # published, so no accounting score can have MIN_OBSERVATIONS_BEFORE_EVENT points
    # in front of it. This is the real finding the spec predicts, not a formality: the
    # accounting scores are not computable in time for the fastest collapse.
    assert any(key.endswith(":EMEIS.PA") for key in result.insufficient)
    assert result.leads.loc["EMEIS.PA", "altman"] is None or pd.isna(
        result.leads.loc["EMEIS.PA", "altman"]
    )
