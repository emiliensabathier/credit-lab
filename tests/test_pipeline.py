"""Orchestration, and the isolation that keeps one bad name from killing twelve."""

from dataclasses import replace

import pandas as pd

from clab.events import hard_event
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
    from clab.universe import STRESSED

    result = run(**synthetic_inputs())
    # The columns are guaranteed by the reindex in `run`, so asserting on them alone
    # would pass even if `lead_rows` were built wrong. The index is the real check.
    assert set(result.leads.columns) >= set(SCORE_NAMES)
    assert set(result.leads.index) == {company.ticker for company in STRESSED}


def test_a_measure_refusal_costs_one_row_not_the_whole_run():
    inputs = synthetic_inputs()
    # ATO.PA is flagged (alarm 2023-04-27, target 2024-03-26) by both altman and
    # ohlson on this fixture: all six stressed names share identical drift-driven
    # fundamentals, so `raw_flags`' tie-break by column order only ever confirms the
    # first three stressed tickers (ATO.PA, CO.PA, EMEIS.PA); Merton fails to converge
    # for every stressed name here regardless of truncation. Cutting ATO.PA's raw
    # prices to 45 days past its target leaves far fewer than the 126-session forward
    # window `measure` requires, so it refuses -- without touching the fundamentals
    # that drive the alarm itself.
    victim = "ATO.PA"
    target = hard_event(victim).date
    prices = inputs["loaded"][victim].prices
    truncated = prices[prices.index <= target + pd.Timedelta(days=45)]
    inputs["loaded"][victim] = replace(inputs["loaded"][victim], prices=truncated)

    result = run(**inputs)

    assert any(key.startswith("impact:") and victim in key for key in result.failures)
    # CO.PA is flagged the same way, with its price history untouched, so the run as
    # a whole still produces impact rows -- one refusal costs a row, not the table.
    assert not result.impacts.empty
