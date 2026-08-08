"""The committed page is the artefact the suite verifies, not a separate live pull.

`run()` costs about 300 seconds against the frozen fixture and `robustness()` about
810, since it rebuilds scores once per distinct publication lag. A module-scoped
fixture computes both exactly once and shares them across every test below --
without it, three tests calling `run()` and `robustness()` independently would cost
several multiples of that, which is the difference between a suite that finishes and
one that times out.
"""

from pathlib import Path

import pytest

from clab.pipeline import robustness, run
from clab.report.build import render
from tests.fixtures import frozen

COMMITTED = Path(__file__).resolve().parents[1] / "reports" / "horserace.html"


@pytest.fixture(scope="module")
def pipeline_outputs():
    inputs = frozen.load()
    return run(**inputs), robustness(**inputs)


def test_the_committed_report_matches_the_frozen_fixture(pipeline_outputs):
    result, robustness_table = pipeline_outputs
    assert COMMITTED.read_text(encoding="utf-8") == render(result, robustness_table)


def test_the_report_names_every_refusal(pipeline_outputs):
    result, _robustness_table = pipeline_outputs
    page = render(result)
    for key in result.failures:
        assert key in page


def test_the_report_names_every_insufficient_history_refusal(pipeline_outputs):
    result, _robustness_table = pipeline_outputs
    page = render(result)
    for key in result.insufficient:
        assert key in page
