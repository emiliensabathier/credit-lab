"""Robustness, the secondary target, and the textbook thresholds kept as a control."""

import pandas as pd
import pytest

from clab.pipeline import SCORE_NAMES, VARIANTS, build_scores, robustness, run
from clab.scores.thresholds import ALTMAN_DISTRESS, academic_flags
from tests.conftest import synthetic_inputs


def test_robustness_reports_one_row_per_variant():
    table = robustness(**synthetic_inputs())
    # Shape alone would pass on six rows of garbage; the labels are what tie each row
    # to the convention it is supposed to represent.
    assert list(table.index) == [variant["label"] for variant in VARIANTS]
    assert set(SCORE_NAMES).issubset(table.columns)


def test_robustness_rows_are_the_medians_of_their_variant():
    table = robustness(**synthetic_inputs())
    headline = VARIANTS[0]
    direct = run(
        **synthetic_inputs(),
        lag_days=headline["lag_days"],
        n_riskiest=headline["n_riskiest"],
        persistence=headline["persistence"],
    )
    for name in SCORE_NAMES:
        expected, actual = direct.leads[name].median(), table.loc[headline["label"], name]
        assert (pd.isna(expected) and pd.isna(actual)) or expected == pytest.approx(actual)


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


def test_the_guard_blanks_a_lead_it_has_declared_unmeasurable():
    result = run(**synthetic_inputs())
    # Emeis alone does not prove the guard works: its event predates every publication
    # date, so `lead_months` already returns None by the ordinary path, and the Emeis
    # assertion above would pass even with the blanking line deleted. Casino and Adler
    # are the real test -- they DO produce a computed lead of roughly a month from only
    # ~38 sessions of history, and the guard must blank it. Recording a refusal while
    # still publishing the lead time is the failure mode this pins down.
    assert any(key.endswith(":CO.PA") for key in result.insufficient)
    assert any(key.endswith(":ADJ.DE") for key in result.insufficient)
    for key in result.insufficient:
        name, ticker = key.split(":")
        assert pd.isna(result.leads.loc[ticker, name]), f"{key} recorded but still published"


def test_prebuilt_scores_give_the_same_result_as_building_them():
    inputs = synthetic_inputs()
    plain = run(**inputs)
    prebuilt = run(**inputs, prebuilt=build_scores(**inputs))
    pd.testing.assert_frame_equal(plain.leads, prebuilt.leads)
    assert plain.false_alarms == prebuilt.false_alarms
    assert plain.common_sample == prebuilt.common_sample
