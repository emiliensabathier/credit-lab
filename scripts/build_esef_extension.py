"""Re-run the horse race with the accounts extended back to FY2020 from ESEF filings.

The headline stays on the frozen Yahoo capture it was registered on. This is a second,
labelled run on the same capture plus the issuers' own filings (see clab.data.esef), and
it writes its numbers to docs/esef-extension.json.

    python scripts/build_esef_extension.py            # from the committed ESEF fixture
    python scripts/build_esef_extension.py --capture  # fetch filings.xbrl.org, refreeze
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # see build_frozen_report.py

from tests.fixtures import frozen  # noqa: E402

from clab.data import esef  # noqa: E402
from clab.pipeline import run  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "esef"
OUTPUT = ROOT / "docs" / "esef-extension.json"


def _slug(ticker: str) -> str:
    return ticker.replace(".", "_").replace("-", "_")


def filings_for(ticker: str, lei: str | None, capture: bool) -> dict:
    path = FIXTURES / f"{_slug(ticker)}.json"
    if capture and lei:
        filings = esef.load_filings(lei)
        FIXTURES.mkdir(parents=True, exist_ok=True)
        path.write_text(esef.dump(filings), encoding="utf-8")
        return filings
    return esef.undump(path.read_text(encoding="utf-8")) if path.exists() else {}


def _table(frame) -> dict:
    return {
        ticker: {name: (None if value != value else value) for name, value in row.items()}
        for ticker, row in frame.astype(object).iterrows()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--capture", action="store_true", help="refetch and refreeze filings")
    args = parser.parse_args()

    inputs = frozen.load()
    extended, coverage = {}, {}
    restated = compared = 0
    for ticker, data in inputs["loaded"].items():
        filings = filings_for(ticker, data.company.lei, args.capture)
        result = esef.extend(data, esef.merge(filings))
        extended[ticker] = result.data
        moved, seen = esef.restatements(filings)
        restated, compared = restated + moved, compared + seen
        coverage[ticker] = {
            "filings": [p.date().isoformat() for p in sorted(filings)],
            "lines": {
                line: {"candidate": label, "added": [y.date().isoformat() for y in years]}
                for line, label in result.chosen.items()
                for years in [result.added_years.get(line, [])]
            },
        }

    result = run(**{**inputs, "loaded": extended})
    payload = {
        "captured": frozen.CAPTURED,
        "tolerance": esef.TOLERANCE,
        "restated_comparatives": {"restated": restated, "compared": compared},
        "coverage": coverage,
        "leads": _table(result.leads),
        "status": _table(result.status),
        "false_alarms": result.false_alarms,
        "forced_false_alarms": result.forced_false_alarms,
        "failures": result.failures,
        "untestable": result.untestable,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("leads", "status", "false_alarms")}, indent=2,
                     default=str))
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
