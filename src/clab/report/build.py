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
from clab.horserace import (
    CENSORED,
    MEASURED,
    MIN_OBSERVATIONS_BEFORE_EVENT,
    MISSED,
    N_RISKIEST,
    PERSISTENCE_DAYS,
    UNTESTABLE,
)
from clab.pipeline import NO_SCORE, Result
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
    "Six events are not a statistic, and only part of them can be tested at all: the "
    "data source carries about four years of annual accounts, so an event that arrives "
    "before the cross-section has enough ranked history is untestable, not missed. "
    "This page measures a handful of histories; it does not test a hypothesis."
)

STATUS_LABELS = {
    MISSED: "not in time",
    UNTESTABLE: "untestable",
    NO_SCORE: "no score",
}


def _table(frame: pd.DataFrame, na_rep: str = "n/a", index: bool = True) -> str:
    # `Result.impacts` carries genuine timestamp columns (`alarm`, `target`), and
    # `to_html`'s `na_rep` does not reach a missing entry in a datetime64 column: it
    # renders as the literal "NaT". Formatting those columns to plain date strings first
    # turns a missing entry into an ordinary NaN, so the same `na_rep` catches it.
    # `fillna(np.nan)` likewise folds a stray `None` in an object column into NaN, which
    # `to_html` would otherwise print as the string "None".
    frame = frame.copy()
    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            frame[column] = frame[column].dt.strftime("%Y-%m-%d")
    return frame.fillna(np.nan).to_html(
        border=0, float_format=lambda value: f"{value:,.2f}", na_rep=na_rep, index=index
    )


def lead_cell(months: float | None, status: str) -> str:
    """One lead-table cell, spelling out which of the four outcomes it is.

    A censored lead is printed as a lower bound, because that is all it is: the
    alarm fired on the first date the data allowed any alarm at all.
    """
    if status == MEASURED:
        return f"{months:.2f}"
    if status == CENSORED:
        return f"\u2265 {months:.2f}"
    return STATUS_LABELS[status]


def lead_display(leads: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            name: [lead_cell(leads.loc[t, name], status.loc[t, name]) for t in leads.index]
            for name in leads.columns
        },
        index=leads.index,
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
        _table(lead_display(result.leads, result.status)),
        "<p class='note'><em>untestable</em>: fewer than "
        f"{MIN_OBSERVATIONS_BEFORE_EVENT} sessions before the event on which the name was "
        "scored inside a rankable cross-section, so the score never had a fair chance. "
        "<em>not in time</em>: testable, and no alarm before the event. "
        "<em>&ge;</em>: the alarm fired on the first date any alarm was possible, so the "
        "lead is a lower bound, not a measurement. <em>no score</em>: the score refused "
        "the name (see Refusals).</p>",
        "<p class='note'>Common sub-sample, testable under all three scores: "
        f"{', '.join(result.common_sample) or 'none'}.</p>",
        lead_chart(result.leads, result.status),
        "<h2>False alarms, in control-name months</h2>",
        _table(
            pd.DataFrame(
                {"months": result.false_alarms, "forced by the rule": result.forced_false_alarms}
            )
        ),
        "<p class='note'>Counted from the first rankable date to the last credit event. "
        "Defaulted names leave the ranking, so once fewer than "
        f"{N_RISKIEST} stressed names are alive the remaining slots go to controls whatever "
        "the score says: <em>forced by the rule</em> is that arithmetic floor, before the "
        "persistence filter (a forced slot that rotates between controls never persists, so "
        "a count can sit below it). Only a count above the floor says something about the "
        "score. A lead time only means something next to this number. Aroundtown "
        "sits in this group deliberately: it suffered the same property crunch as SBB and "
        "Adler, never fell below BBB-, and never entered a proceeding.</p>",
        "<h2>What the lead was worth</h2>",
        _table(result.impacts, index=False),
        "<p class='note'>Read <em>avoided</em> next to <em>already_suffered</em>: a score "
        "that only fires once the shares have halved shows a long lead and no value. On a "
        "<em>censored</em> row the alarm date is the first date any alarm was possible, so "
        "<em>already_suffered</em> measures the fall before the test could start, not the "
        "cost of a late warning.</p>",
        "<h2>Cross-check against the fallen-angel target</h2>",
        _table(lead_display(result.secondary, result.secondary_status)),
        "<p class='note'>Only Atos and SBB ever fell below BBB-. Casino and Adler were "
        "already speculative grade before the window, Emeis has no public S&amp;P rating, "
        "and Intrum was already rated below BBB-. Both downgrades (2022-07-13 and "
        "2023-05-08) come before the cross-section has enough ranked history, so the "
        "cross-check is untestable on this data rather than failed. Kept on the page so "
        "the gap stays visible.</p>",
        "<h2>Robustness</h2>",
        _table(robustness) if robustness is not None else "<p class='note'>not computed</p>",
        "<p class='note'>Per score and convention: events testable, alarms in time, "
        "of which censored, and the median of the measured (uncensored) leads only. "
        "Publication lag at 60, 90 and 120 days; persistence at 10, 20 and 40 sessions; "
        "the riskiest three against the riskiest four. A median over one or two leads is "
        "a description, not an estimate.</p>",
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

    refusals = {**result.failures, **result.untestable}
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
