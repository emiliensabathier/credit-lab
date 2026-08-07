"""Command line entry point: pull, run, render.

A live run writes to reports/horserace.local.html by default. The committed
reports/horserace.html is rendered from the frozen fixture by
scripts/build_frozen_report.py, and a test checks the two stay identical — a live
run overwriting it would silently break that guarantee.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from clab.data.loader import load_company, load_deflator, load_fx, load_rates
from clab.pipeline import robustness, run
from clab.report.build import render
from clab.universe import UNIVERSE

DEFAULT_OUTPUT = Path("reports/horserace.local.html")


def main() -> None:
    parser = argparse.ArgumentParser(prog="clab")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh", action="store_true", help="ignore the on-disk cache")
    args = parser.parse_args()

    loaded = {
        company.ticker: load_company(company, refresh=args.refresh) for company in UNIVERSE
    }
    inputs = {
        "loaded": loaded,
        "rates": load_rates(),
        "deflator": load_deflator(),
        "fx": load_fx(),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(run(**inputs), robustness(**inputs)), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
