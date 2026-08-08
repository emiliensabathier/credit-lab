"""Assembly of the final HTML report.

Computes nothing: every number here is produced by the scoring and horse-race
modules. Refusals are printed, not hidden — a table with a company quietly missing
is worse than a table that says why.
"""

from __future__ import annotations

import html as html_escape

import numpy as np
import pandas as pd

from clab.events import hard_event
from clab.horserace import N_RISKIEST, PERSISTENCE_DAYS
from clab.pipeline import Result
from clab.pointintime import PUBLICATION_LAG_DAYS
from clab.report.charts import lead_chart, score_paths_chart
from clab.universe import STRESSED

STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0 auto;
       max-width: 980px; padding: 2rem 1.25rem; color: #16181d; line-height: 1.5; }
h1 { font-size: 1.9rem; margin-bottom: 0.25rem; }
h2 { font-size: 1.25rem; margin-top: 2.5rem; border-bottom: 1px solid #e3e5ea;
     padding-bottom: 0.35rem; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 0.45rem 0.6rem; border-bottom: 1px solid #eceef2; }
th:first-child, td:first-child { text-align: left; }
thead th { border-bottom: 2px solid #c9ccd4; }
.note { color: #5b6070; font-size: 0.9rem; }
.caveat { background: #f6f7f9; border-left: 3px solid #c9ccd4; padding: 0.75rem 1rem;
          margin: 1rem 0; }
svg { max-width: 100%; height: auto; }
"""

CAVEAT = (
    "Six events are not a statistic, and only the common sub-sample carries all three "
    "scores. This page measures a handful of histories; it does not test a hypothesis."
)


def _table(frame: pd.DataFrame) -> str:
    # `Result.leads` and `Result.secondary` build each ticker's row as a plain Python
    # dict that may hold a mix of floats and explicit `None` (see pipeline.py). When
    # every value in one of those per-ticker columns is `None` -- Casino, Emeis and
    # Adler here, flagged by no score -- pandas keeps that column as `object` dtype
    # rather than upcasting to `float64`, and `to_html`'s `na_rep` silently skips
    # `None` cells on an object column: they render as the literal string "None"
    # instead of the same "not in time" a `NaN` cell gets. `fillna(np.nan)` forces
    # every missing cell to the same NaN representation before formatting, regardless
    # of the column's dtype, so the two constructions of "no measurable lead" don't
    # read as two different things on the page.
    #
    # `Result.impacts` carries genuine timestamp columns (`alarm`, `target`,
    # `fallen_angel`), and `to_html`'s `na_rep` does not reach a missing entry in a
    # datetime64 column either: it renders as the literal "NaT", a third spelling of
    # the same "not applicable" that `fillna` alone cannot fix, since NaT is its own
    # sentinel rather than a NaN. Formatting those columns to plain date strings first
    # turns a missing entry into an ordinary NaN, so the same `na_rep` catches it.
    frame = frame.copy()
    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            frame[column] = frame[column].dt.strftime("%Y-%m-%d")
    return frame.fillna(np.nan).to_html(
        border=0, float_format=lambda value: f"{value:,.2f}", na_rep="not in time"
    )


def render(result: Result, robustness: pd.DataFrame | None = None) -> str:
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<title>credit-lab: which default score flags first</title>",
        f"<style>{STYLE}</style></head><body>",
        "<h1>Which default score flags first</h1>",
        f"<p class='note'>Alarm rule: among the {N_RISKIEST} riskiest of thirteen, held "
        f"{PERSISTENCE_DAYS} sessions, dated to the twentieth. Statements treated as public "
        f"{PUBLICATION_LAG_DAYS} days after fiscal year end.</p>",
        f"<div class='caveat'>{html_escape.escape(CAVEAT)}</div>",
        "<h2>Lead time, in months</h2>",
        _table(result.leads),
        f"<p class='note'>Common sub-sample: {', '.join(result.common_sample)}.</p>",
        lead_chart(result.leads),
        "<h2>False alarms, in control-name months</h2>",
        _table(pd.DataFrame(result.false_alarms, index=["months"]).T),
        "<p class='note'>A lead time only means something next to this number. Aroundtown "
        "sits in this group deliberately: it suffered the same property crunch as SBB and "
        "Adler, never fell below BBB-, and never entered a proceeding.</p>",
        "<h2>What the lead was worth</h2>",
        _table(result.impacts),
        "<p class='note'>Read <em>avoided</em> next to <em>already_suffered</em>: a score "
        "that only fires once the shares have halved shows a long lead and no value.</p>",
        "<h2>Cross-check against the fallen-angel target</h2>",
        _table(result.secondary),
        "<p class='note'>Only Atos and SBB ever fell below BBB-. Casino and Adler were "
        "already speculative grade before the window, Emeis has no public S&amp;P rating, "
        "and Intrum was already rated below BBB-. Two observations are a cross-check, not "
        "a statistic, and they are never averaged into the table above.</p>",
        "<h2>Robustness</h2>",
        _table(robustness) if robustness is not None else "<p class='note'>not computed</p>",
        "<p class='note'>Median lead per score under each convention: publication lag at "
        "60, 90 and 120 days; persistence at 10, 20 and 40 sessions; the riskiest three "
        "against the riskiest four. A ranking that flips between variants is a null "
        "result and reads as one.</p>",
    ]

    parts.append("<h2>Per company</h2>")
    for company in STRESSED:
        parts.append(f"<h3>{html_escape.escape(company.name)}</h3>")
        event = hard_event(company.ticker)
        parts.append(
            f"<p class='note'>{html_escape.escape(event.description)} "
            f"Source: {html_escape.escape(event.source)}.</p>"
        )
        parts.append(score_paths_chart(result.scores, company.ticker, event.date))

    refusals = {**result.failures, **result.insufficient}
    if refusals:
        parts.append("<h2>Refusals</h2>")
        parts.append(
            "<p class='note'>Printed rather than hidden. A table with a company quietly "
            "missing is worse than a table that says why it is missing.</p><ul>"
        )
        for key, message in sorted(refusals.items()):
            parts.append(f"<li>{html_escape.escape(key)}: {html_escape.escape(message)}</li>")
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts)
