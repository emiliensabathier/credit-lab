"""Render the committed report from the frozen fixture, byte for byte."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures import frozen

from clab.pipeline import robustness, run
from clab.report.build import render

OUTPUT = Path(__file__).resolve().parents[1] / "reports" / "horserace.html"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    inputs = frozen.load()
    page = render(run(**inputs), robustness(**inputs))
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUTPUT} from the {frozen.CAPTURED} capture")


if __name__ == "__main__":
    main()
