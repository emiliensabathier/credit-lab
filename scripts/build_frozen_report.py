"""Render the committed report and the README chart from the frozen fixture.

Both come out of one pipeline run, because that run costs about five minutes against the
frozen capture and doing it twice to produce two artefacts from the same numbers would be
five minutes spent proving they agree instead of guaranteeing it.

The chart exists because GitHub shows a committed HTML file as source, not as a page: every
figure in reports/horserace.html is invisible to anyone browsing the repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# tests/ is importable as "tests.fixtures.frozen" only when the repo root sits on sys.path,
# which pytest arranges for the suite but `python scripts/build_frozen_report.py` does not:
# running a script puts scripts/ on the path, not the directory above it.
sys.path.insert(0, str(ROOT))

from tests.fixtures import frozen  # noqa: E402

from clab.pipeline import robustness, run  # noqa: E402
from clab.report.build import render  # noqa: E402
from clab.report.charts import lead_figure  # noqa: E402

OUTPUT = ROOT / "reports" / "horserace.html"
CHART = ROOT / "docs" / "lead-times.png"
CHART_DPI = 130


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    inputs = frozen.load()
    result = run(**inputs)
    page = render(result, robustness(**inputs))
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUTPUT} from the {frozen.CAPTURED} capture")

    CHART.parent.mkdir(parents=True, exist_ok=True)
    lead_figure(result.leads, result.status).savefig(
        CHART, format="png", dpi=CHART_DPI, bbox_inches="tight"
    )
    print(f"wrote {CHART} ({CHART.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
