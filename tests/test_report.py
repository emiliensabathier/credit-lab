"""The committed page is the artefact the suite verifies, not a separate live pull.

`run()` costs about 300 seconds against the frozen fixture and `robustness()` about
810, since it rebuilds scores once per distinct publication lag. A module-scoped
fixture computes both exactly once and shares them across every test below --
without it, three tests calling `run()` and `robustness()` independently would cost
several multiples of that, which is the difference between a suite that finishes and
one that times out.
"""

import re
from pathlib import Path

import pytest

from clab.pipeline import robustness, run
from clab.report.build import render
from tests.fixtures import frozen

COMMITTED = Path(__file__).resolve().parents[1] / "reports" / "horserace.html"

SVG_BLOCK = re.compile(r"<svg\b.*?</svg>", re.DOTALL)


def _without_charts(page: str) -> tuple[str, int]:
    """The page with each inline SVG replaced by a marker, plus the chart count.

    A byte-for-byte comparison of the whole page cannot survive CI: matplotlib's SVG
    output drifts between versions and platforms, and the committed page is generated
    on one machine while CI renders on another. What the comparison is for -- proving
    the published page is the artefact this suite verifies, not a stale or hand-edited
    file -- rests entirely on the numbers and the prose, which are compared exactly.
    The chart count is asserted separately so a silently dropped chart still fails.
    """
    return SVG_BLOCK.sub("[CHART]", page), len(SVG_BLOCK.findall(page))


@pytest.fixture(scope="module")
def pipeline_outputs():
    inputs = frozen.load()
    return run(**inputs), robustness(**inputs)


def test_the_committed_report_matches_the_frozen_fixture(pipeline_outputs):
    result, robustness_table = pipeline_outputs
    committed = COMMITTED.read_text(encoding="utf-8")
    rendered = render(result, robustness_table)
    assert _without_charts(committed) == _without_charts(rendered)


def test_the_report_names_every_refusal(pipeline_outputs):
    result, _robustness_table = pipeline_outputs
    page = render(result)
    for key in result.failures:
        assert key in page


def test_the_report_names_every_untestable_event(pipeline_outputs):
    result, _robustness_table = pipeline_outputs
    page = render(result)
    for key in result.untestable:
        assert key in page
