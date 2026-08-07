"""Orchestration, and the isolation that keeps one bad name from killing twelve."""

from clab.pipeline import SCORE_NAMES, build_scores, run
from tests.conftest import synthetic_inputs


def test_a_failing_company_is_recorded_not_propagated():
    inputs = synthetic_inputs(break_ticker="CO.PA")
    frames, failures = build_scores(**inputs)
    assert "CO.PA" in " ".join(failures.values())
    assert set(frames) == set(SCORE_NAMES)
    for frame in frames.values():
        assert not frame.empty


def test_common_sample_excludes_names_missing_from_any_score():
    inputs = synthetic_inputs(break_ticker="CO.PA")
    result = run(**inputs)
    assert "CO.PA" not in result.common_sample


def test_leads_carry_one_row_per_stressed_name_and_score():
    result = run(**synthetic_inputs())
    assert set(result.leads.columns) >= set(SCORE_NAMES)
