"""Charts, rendered to inline SVG so the report is a single self-contained file."""

from __future__ import annotations

import io

import matplotlib
import numpy as np

matplotlib.use("Agg")
# Two renders of the same figure are not byte-identical by default: the SVG backend
# stamps a wall-clock <dc:date> into the metadata block, and it derives marker and
# clip-path element ids from Python's id() -- a memory address that differs between
# separate objects even within one process, let alone between the process that wrote
# the committed report and the process that later re-renders it to check the byte
# comparison. A fixed hash salt makes those ids a function of the path data alone,
# and metadata={"Date": None} drops the timestamp instead of freezing it to a
# plausible-looking but still-wrong constant.
matplotlib.rcParams["svg.hashsalt"] = "clab-report"
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def _svg(figure: plt.Figure) -> str:
    """Serialise to SVG and drop the XML preamble, so the markup can be inlined."""
    buffer = io.StringIO()
    figure.savefig(buffer, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)
    markup = buffer.getvalue()
    return markup[markup.index("<svg") :]


def score_paths_chart(scores: dict[str, pd.DataFrame], ticker: str, target: pd.Timestamp) -> str:
    figure, axis = plt.subplots(figsize=(8, 3))
    for name, frame in scores.items():
        if ticker in frame.columns:
            series = frame[ticker].dropna()
            if not series.empty:
                axis.plot(
                    series.index,
                    (series - series.mean()) / (series.std() or 1.0),
                    label=name,
                    linewidth=1.2,
                )
    axis.axvline(target, color="#b3262a", linestyle="--", linewidth=1.0, label="credit event")
    axis.set_title(f"{ticker}: standardised risk scores")
    axis.legend(fontsize=8, frameon=False)
    return _svg(figure)


def lead_figure(leads: pd.DataFrame) -> plt.Figure:
    """Grouped bars, one group per company, one bar per score.

    Returned as a figure rather than as markup, because the README needs the same chart as
    a raster: GitHub shows a committed HTML report as source, so the one picture that
    carries the result has to travel separately.

    `DataFrame.plot(kind="bar")` fills missing cells with 0 before drawing, which is
    wrong here: a company a score never flagged is not the same as one it flagged
    with zero months to spare, and drawing both as a bar of the same height flatters
    the "no lead" result into looking like a real, if small, one. Bars are placed by
    hand instead, straight from the (possibly `NaN`, possibly Python `None`) values,
    so a missing lead draws no bar at all rather than a zero-height one.
    """
    figure, axis = plt.subplots(figsize=(8, 3.5))
    companies = list(leads.index)
    scores = list(leads.columns)
    positions = np.arange(len(companies))
    width = 0.8 / max(len(scores), 1)
    for i, name in enumerate(scores):
        offset = (i - (len(scores) - 1) / 2) * width
        heights = leads[name].to_numpy(dtype=float)
        axis.bar(positions + offset, heights, width=width, label=name)
    axis.set_xticks(positions)
    axis.set_xticklabels(companies)
    axis.set_ylabel("months of lead")
    axis.axhline(0, color="#16181d", linewidth=0.8)
    axis.legend(fontsize=8, frameon=False)
    return figure


def lead_chart(leads: pd.DataFrame) -> str:
    """The lead chart as inline SVG, for the report."""
    return _svg(lead_figure(leads))
