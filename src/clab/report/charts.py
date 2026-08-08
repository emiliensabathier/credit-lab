"""Charts, rendered to inline SVG so the report is a single self-contained file."""

from __future__ import annotations

import io

import matplotlib

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


def score_paths_chart(scores: pd.DataFrame, ticker: str, target: pd.Timestamp) -> str:
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


def lead_chart(leads: pd.DataFrame) -> str:
    figure, axis = plt.subplots(figsize=(8, 3.5))
    leads.plot(kind="bar", ax=axis, width=0.8)
    axis.set_ylabel("months of lead")
    axis.axhline(0, color="#16181d", linewidth=0.8)
    axis.legend(fontsize=8, frameon=False)
    return _svg(figure)
