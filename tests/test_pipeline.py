"""Orchestration, and the isolation that keeps one bad name from killing twelve."""

from dataclasses import replace

import pandas as pd
import pytest

from clab.events import hard_event
from clab.horserace import CENSORED, MISSED, UNTESTABLE
from clab.pipeline import NO_SCORE, SCORE_NAMES, build_scores, run
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
    # ATO.PA is flagged by both altman and ohlson on this fixture: all six stressed
    # names share identical drift-driven fundamentals, so `raw_flags`' tie-break by
    # column order confirms the first three stressed tickers still alive -- EMEIS.PA
    # and ADJ.DE are already in default when the cross-section becomes rankable, so
    # that is ATO.PA, CO.PA and SBB-B.ST. Cutting ATO.PA's raw
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
    # SBB-B.ST is flagged the same way, with its price history untouched, so the run
    # as a whole still produces impact rows -- one refusal costs a row, not the table.
    assert not result.impacts.empty


def test_events_before_any_rankable_history_are_untestable_not_missed():
    result = run(**synthetic_inputs())
    # Statements in this fixture first become public on 2023-03-31. Emeis (2022-04-20)
    # and Adler (2023-04-12) default before that, Casino (2023-05-26) a few weeks after:
    # none has the sixty ranked sessions a fair test needs.
    # Merton refuses every stressed name on this fixture (the solver does not converge
    # on its synthetic leverage), so it reports "no score" there instead.
    for ticker in ("EMEIS.PA", "ADJ.DE", "CO.PA"):
        for name in ("altman", "ohlson"):
            assert result.status.loc[ticker, name] == UNTESTABLE, (ticker, name)
        assert result.status.loc[ticker, "merton"] in (UNTESTABLE, NO_SCORE)
        assert result.leads.loc[ticker].isna().all()


def test_the_common_sample_holds_only_names_testable_under_every_score():
    result = run(**synthetic_inputs())
    for ticker in result.common_sample:
        assert not result.status.loc[ticker].isin([UNTESTABLE, NO_SCORE]).any()
    assert "EMEIS.PA" not in result.common_sample


def test_a_refused_score_is_reported_as_no_score():
    result = run(**synthetic_inputs(break_ticker="ATO.PA"))
    assert result.status.loc["ATO.PA", "altman"] == NO_SCORE


def test_an_alarm_on_the_first_rankable_session_is_marked_censored():
    result = run(**synthetic_inputs())
    # ATO.PA is among the three riskiest from the first rankable session onwards.
    assert result.status.loc["ATO.PA", "altman"] == CENSORED
    rows = result.impacts[result.impacts["ticker"] == "ATO.PA"]
    assert rows.loc[rows["score"] == "altman", "censored"].all()


def test_names_in_default_leave_the_ranking():
    result = run(**synthetic_inputs())
    # With EMEIS.PA and ADJ.DE out of the ranking, SBB-B.ST takes the third slot that
    # a defaulted name would otherwise have held for the rest of the window.
    assert result.status.loc["SBB-B.ST", "altman"] != MISSED
    assert not pd.isna(result.leads.loc["SBB-B.ST", "altman"])


def test_false_alarms_are_counted_only_until_the_last_credit_event():
    from clab.horserace import exclude_after, false_alarm_months, raw_flags
    from clab.pipeline import _defaults
    from clab.universe import CONTROLS

    inputs = synthetic_inputs()
    result = run(**inputs)
    defaults = _defaults()
    last = max(defaults.values())
    # After the last event every stressed name has left the ranking and the rule can
    # only rank controls against each other: three of them are flagged by construction.
    # Counting those sessions would measure the rule's arithmetic, not the score.
    controls = [company.ticker for company in CONTROLS]
    for name, frame in result.scores.items():
        flags = raw_flags(exclude_after(frame, defaults))
        expected = false_alarm_months(flags[flags.index < last], controls)
        assert result.false_alarms[name] == pytest.approx(expected)
        assert result.forced_false_alarms[name] >= 0.0
