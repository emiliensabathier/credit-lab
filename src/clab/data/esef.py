"""Older annual accounts from the issuers' own ESEF filings.

Yahoo serves annual statements from FY2022 on, which leaves the 2022 and early 2023
credit events with nothing to score. Every EU-listed issuer has filed its annual report
in machine-readable form (ESEF, inline XBRL tagged against the IFRS taxonomy) since
FY2021, and filings.xbrl.org republishes those filings as xBRL-JSON, free and keyless.
A FY2021 report carries FY2020 as its comparative year, so the history gains two years.

Two sources are only worth splicing if they mean the same thing by the same line. So no
mapping from IFRS concepts to statement lines is trusted on its name: each candidate is
checked against Yahoo on every fiscal year both sources cover, and a line is extended
only through the first candidate that agrees with Yahoo within `TOLERANCE` on all of
them. A line no candidate reproduces is left alone, and the scores that need it stay
untestable on the early years rather than computed from a number that means something
else. Yahoo's own figures are never overwritten.

Point in time: a comparative year is taken as originally published. Where a later report
restated it, the restated figure leaks back; `restatements` measures how often that is.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from clab.data.loader import CACHE_DIR, CompanyData
from clab.errors import CreditLabError

API = "https://filings.xbrl.org"
TOLERANCE = 0.02  # relative gap allowed between a candidate and Yahoo on a shared year
IFRS = "ifrs-full:"
PLAIN_DIMENSIONS = {"concept", "entity", "period", "unit"}

Facts = dict[pd.Timestamp, dict[str, float]]  # fiscal year end -> concept -> value


@dataclass(frozen=True)
class Candidate:
    """One way of reading a statement line off the IFRS taxonomy.

    ``plus`` concepts are summed and ``minus`` concepts subtracted. A candidate with no
    ``plus`` value at all on a year has no value that year; a missing ``minus`` concept
    makes the whole candidate missing, since dropping it would change what is measured.
    """

    label: str
    plus: tuple[str, ...]
    minus: tuple[str, ...] = ()

    def value(self, facts: Mapping[str, float]) -> float | None:
        present = [facts[IFRS + c] for c in self.plus if IFRS + c in facts]
        if not present or any(IFRS + c not in facts for c in self.minus):
            return None
        return sum(present) - sum(facts[IFRS + c] for c in self.minus)

    @property
    def concepts(self) -> tuple[str, ...]:
        return tuple(IFRS + c for c in self.plus + self.minus)


def _single(concept: str) -> Candidate:
    return Candidate(concept, (concept,))


CURRENT_LEASES = "CurrentLeaseLiabilities"
NONCURRENT_LEASES = "NoncurrentLeaseLiabilities"

# Ordered: the first candidate that reproduces Yahoo on the shared years is used.
CANDIDATES: dict[tuple[str, str], tuple[Candidate, ...]] = {
    ("balance", "Total Assets"): (_single("Assets"),),
    ("balance", "Total Liabilities Net Minority Interest"): (
        _single("Liabilities"),
        Candidate("EquityAndLiabilities - Equity", ("EquityAndLiabilities",), ("Equity",)),
    ),
    ("balance", "Current Assets"): (
        _single("CurrentAssets"),
        Candidate("Assets - NoncurrentAssets", ("Assets",), ("NoncurrentAssets",)),
    ),
    ("balance", "Current Liabilities"): (_single("CurrentLiabilities"),),
    ("balance", "Working Capital"): (
        Candidate(
            "CurrentAssets - CurrentLiabilities", ("CurrentAssets",), ("CurrentLiabilities",)
        ),
        Candidate(
            "Assets - NoncurrentAssets - CurrentLiabilities",
            ("Assets",),
            ("NoncurrentAssets", "CurrentLiabilities"),
        ),
    ),
    ("balance", "Retained Earnings"): (_single("RetainedEarnings"),),
    ("balance", "Stockholders Equity"): (_single("EquityAttributableToOwnersOfParent"),),
    ("balance", "Ordinary Shares Number"): (_single("NumberOfSharesOutstanding"),),
    ("balance", "Current Debt And Capital Lease Obligation"): (
        Candidate(
            "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings + CurrentLeaseLiabilities",
            ("CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", CURRENT_LEASES),
        ),
        Candidate(
            "ShorttermBorrowings + CurrentPortionOfLongtermBorrowings + CurrentLeaseLiabilities",
            ("ShorttermBorrowings", "CurrentPortionOfLongtermBorrowings", CURRENT_LEASES),
        ),
    ),
    ("balance", "Long Term Debt And Capital Lease Obligation"): (
        Candidate(
            "LongtermBorrowings + NoncurrentLeaseLiabilities",
            ("LongtermBorrowings", NONCURRENT_LEASES),
        ),
        Candidate(
            "NoncurrentPortionOfNoncurrentBorrowings + NoncurrentLeaseLiabilities",
            ("NoncurrentPortionOfNoncurrentBorrowings", NONCURRENT_LEASES),
        ),
    ),
    ("income", "EBIT"): (_single("ProfitLossFromOperatingActivities"),),
    ("income", "Net Income"): (_single("ProfitLossAttributableToOwnersOfParent"),),
    ("cashflow", "Operating Cash Flow"): (_single("CashFlowsFromUsedInOperatingActivities"),),
}

CONCEPTS: frozenset[str] = frozenset(
    concept for options in CANDIDATES.values() for c in options for concept in c.concepts
)


def _period_end(period: str) -> pd.Timestamp:
    """The fiscal date a period string closes on.

    xBRL-JSON writes an instant, and the end of a duration, as the midnight that *follows*
    the last day: a balance sheet at 31 December 2021 is ``2022-01-01T00:00:00``.
    """
    end = period.split("/")[-1]
    stamp = pd.Timestamp(end)
    return (stamp - pd.Timedelta(days=1)).normalize() if "T" in end else stamp.normalize()


def parse(payload: Mapping) -> Facts:
    """Non-dimensional numeric facts of one filing, for the concepts this module reads.

    A fact with a segment, scenario or any other dimension is a breakdown, not the
    consolidated total, and is skipped.
    """
    facts: Facts = {}
    for fact in payload.get("facts", {}).values():
        dims = fact.get("dimensions", {})
        if set(dims) != PLAIN_DIMENSIONS or dims["concept"] not in CONCEPTS:
            continue
        try:
            value = float(fact["value"])
        except (TypeError, ValueError):
            continue
        facts.setdefault(_period_end(dims["period"]), {})[dims["concept"]] = value
    return facts


def merge(filings: Mapping[pd.Timestamp, Facts]) -> Facts:
    """One set of facts per fiscal year across several filings, keyed by period end.

    A year's own report wins over the next report's comparative of it, because the own
    report is what was public at the time; the comparative only fills concepts the own
    report lacks, or a year whose own report is missing from the repository.
    """
    merged: Facts = {}
    # Own reports first, then the rest from most recent to oldest.
    for period_end in sorted(filings, reverse=True):
        for year, facts in filings[period_end].items():
            if year == period_end:
                merged[year] = {**merged.get(year, {}), **facts}
    for period_end in sorted(filings, reverse=True):
        for year, facts in filings[period_end].items():
            if year != period_end:
                merged[year] = {**facts, **merged.get(year, {})}
    return merged


def restatements(
    filings: Mapping[pd.Timestamp, Facts], threshold: float = TOLERANCE
) -> tuple[int, int]:
    """How many comparative figures a later filing moved beyond ``threshold``, out of how many.

    Every (year, concept) a filing reports as its own year and a later filing repeats as a
    comparative is one comparison.
    """
    restated = compared = 0
    for period_end, own in filings.items():
        mine = own.get(period_end, {})
        for later_end, later in filings.items():
            if later_end <= period_end:
                continue
            for concept, value in later.get(period_end, {}).items():
                original = mine.get(concept)
                if original is None:
                    continue
                compared += 1
                restated += _gap(value, original) > threshold
    return restated, compared


def _gap(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0 if value == 0 else float("inf")
    return abs(value / reference - 1.0)


def _yahoo_years(frame: pd.DataFrame, line: str) -> pd.Series:
    if line not in frame.index:
        return pd.Series(dtype=float)
    return frame.loc[line].dropna()


def choose(
    yahoo: pd.Series, facts: Facts, options: tuple[Candidate, ...]
) -> Candidate | None:
    """The first candidate that agrees with Yahoo on every year both cover, if any."""
    for candidate in options:
        shared = [
            (candidate.value(facts[year]), reported)
            for year, reported in yahoo.items()
            if year in facts and candidate.value(facts[year]) is not None
        ]
        if shared and all(_gap(value, reported) <= TOLERANCE for value, reported in shared):
            return candidate
    return None


@dataclass(frozen=True)
class Extension:
    """What the ESEF splice added to one company."""

    data: CompanyData
    chosen: dict[str, str | None]  # line -> candidate label, or None when nothing matched
    added_years: dict[str, list[pd.Timestamp]]  # line -> fiscal years taken from ESEF


def extend(data: CompanyData, facts: Facts) -> Extension:
    """``data`` with each validated line extended to the fiscal years Yahoo lacks."""
    frames = {"balance": data.balance_sheet, "income": data.income, "cashflow": data.cashflow}
    facts = _fiscal_year_ends(facts, frames.values())
    additions: dict[str, dict[str, dict[pd.Timestamp, float]]] = {k: {} for k in frames}
    chosen: dict[str, str | None] = {}
    added_years: dict[str, list[pd.Timestamp]] = {}
    for (statement, line), options in CANDIDATES.items():
        yahoo = _yahoo_years(frames[statement], line)
        candidate = choose(yahoo, facts, options)
        chosen[line] = None if candidate is None else candidate.label
        if candidate is None:
            continue
        values = {
            year: candidate.value(year_facts)
            for year, year_facts in facts.items()
            if year not in yahoo.index and candidate.value(year_facts) is not None
        }
        if values:
            additions[statement][line] = values
            added_years[line] = sorted(values)
    extended = {name: _splice(frames[name], additions[name]) for name in frames}
    return Extension(
        data=replace(
            data,
            balance_sheet=extended["balance"],
            income=extended["income"],
            cashflow=extended["cashflow"],
        ),
        chosen=chosen,
        added_years=added_years,
    )


def _fiscal_year_ends(facts: Facts, frames) -> Facts:
    """Only the dates that close a fiscal year as Yahoo dates them.

    Filings also carry other balance sheet dates (Casino's FY2021 report restates its
    opening balance at 1 January 2020), and those are not annual statements.
    """
    closes = {(c.month, c.day) for frame in frames for c in pd.to_datetime(frame.columns)}
    return {year: f for year, f in facts.items() if (year.month, year.day) in closes}


def _splice(frame: pd.DataFrame, additions: dict[str, dict[pd.Timestamp, float]]) -> pd.DataFrame:
    """A copy of ``frame`` with new cells filled in; existing non-missing cells are kept."""
    if not additions:
        return frame
    extra = pd.DataFrame(additions).T
    combined = frame.combine_first(extra)
    return combined.reindex(columns=sorted(combined.columns, reverse=True))


def dump(filings: Mapping[pd.Timestamp, Facts]) -> str:
    """``filings`` as JSON, dates written as ISO strings, for a committed fixture."""
    return json.dumps(
        {
            period_end.date().isoformat(): {
                year.date().isoformat(): dict(sorted(facts.items()))
                for year, facts in sorted(by_year.items())
            }
            for period_end, by_year in sorted(filings.items())
        },
        indent=1,
    )


def undump(text: str) -> dict[pd.Timestamp, Facts]:
    return {
        pd.Timestamp(period_end): {pd.Timestamp(year): facts for year, facts in by_year.items()}
        for period_end, by_year in json.loads(text).items()
    }


# --- network ------------------------------------------------------------------------------

Fetcher = Callable[[str], bytes]


def http_fetcher(path: str) -> bytes:
    with urllib.request.urlopen(API + path, timeout=120) as response:
        return response.read()


def load_filings(lei: str, fetcher: Fetcher = http_fetcher, cache_dir: Path = CACHE_DIR) -> dict:
    """Every annual ESEF filing of ``lei``, parsed, keyed by the period it closes.

    Filings the repository holds without an xBRL-JSON rendering are skipped. Where it
    holds several renderings of one period (a correction, a second language), the last
    one listed is kept.
    """
    index = json.loads(_cached(f"/api/entities/{lei}/filings", fetcher, cache_dir))
    if "data" not in index:
        raise CreditLabError(f"filings.xbrl.org has no filing index for LEI {lei}")
    filings: dict[pd.Timestamp, Facts] = {}
    for filing in index["data"]:
        attributes = filing.get("attributes", {})
        url = attributes.get("json_url")
        if not url:
            continue
        parsed = parse(json.loads(_cached(url, fetcher, cache_dir)))
        if not parsed:
            continue
        # A filing's own period is the latest fiscal year it carries. The repository's
        # `period_end` attribute is not reliable for this (Unilever's reads as the
        # signing date).
        filings[max(parsed)] = parsed
    return filings


def _cached(path: str, fetcher: Fetcher, cache_dir: Path) -> bytes:
    target = Path(cache_dir) / "esef" / path.strip("/").replace("/", "_")
    if target.exists():
        return target.read_bytes()
    payload = fetcher(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return payload
