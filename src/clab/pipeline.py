"""Orchestration.

Failures are isolated per company: a name that raises is recorded and published,
not silently dropped and not allowed to take the other twelve down with it. Casino
is the known case — it does not report retained earnings, so Altman refuses on it —
and the report says so rather than hiding a gap in a table.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from clab.data.loader import CompanyData
from clab.errors import CreditLabError
from clab.events import fallen_angel, hard_event
from clab.horserace import (
    MIN_OBSERVATIONS_BEFORE_EVENT,
    N_RISKIEST,
    PERSISTENCE_DAYS,
    alarm_date,
    false_alarm_months,
    lead_months,
    raw_flags,
)
from clab.impact import measure
from clab.pointintime import PUBLICATION_LAG_DAYS
from clab.scores import altman, merton, ohlson
from clab.scores.thresholds import academic_flags
from clab.universe import CONTROLS, STRESSED

SCORE_NAMES = ("altman", "ohlson", "merton")

VARIANTS: tuple[dict, ...] = (
    {"label": "headline", "lag_days": 90, "persistence": 20, "n_riskiest": 3},
    {"label": "lag 60", "lag_days": 60, "persistence": 20, "n_riskiest": 3},
    {"label": "lag 120", "lag_days": 120, "persistence": 20, "n_riskiest": 3},
    {"label": "persistence 10", "lag_days": 90, "persistence": 10, "n_riskiest": 3},
    {"label": "persistence 40", "lag_days": 90, "persistence": 40, "n_riskiest": 3},
    {"label": "tercile", "lag_days": 90, "persistence": 20, "n_riskiest": 4},
)


@dataclass(frozen=True)
class Result:
    scores: dict[str, pd.DataFrame]
    leads: pd.DataFrame
    false_alarms: dict[str, float]
    impacts: pd.DataFrame
    failures: dict[str, str]
    common_sample: list[str]
    secondary: pd.DataFrame
    academic: pd.DataFrame
    insufficient: dict[str, str]


def build_scores(
    loaded: dict[str, CompanyData],
    rates: pd.DataFrame,
    deflator: pd.Series,
    fx: pd.DataFrame,
    lag_days: int = PUBLICATION_LAG_DAYS,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    index = sorted({date for data in loaded.values() for date in data.prices.index})
    index = pd.DatetimeIndex(index)
    frames: dict[str, dict[str, pd.Series]] = {name: {} for name in SCORE_NAMES}
    failures: dict[str, str] = {}

    for ticker, data in loaded.items():
        currency = data.company.currency
        # Explicit calls rather than a dict of closures: a lambda capturing the loop
        # variable is both a ruff B023 error and a genuine late-binding trap.
        for name in SCORE_NAMES:
            try:
                if name == "altman":
                    series = altman.score(data, index, lag_days)
                elif name == "ohlson":
                    series = ohlson.score(data, index, deflator, fx[currency], lag_days)
                else:
                    series = merton.score(data, index, rates[currency], lag_days)
                frames[name][ticker] = series
            except CreditLabError as error:
                failures[f"{name}:{ticker}"] = str(error)

    return {name: pd.DataFrame(columns) for name, columns in frames.items()}, failures


def run(
    loaded: dict[str, CompanyData],
    rates: pd.DataFrame,
    deflator: pd.Series,
    fx: pd.DataFrame,
    lag_days: int = PUBLICATION_LAG_DAYS,
    n_riskiest: int = N_RISKIEST,
    persistence: int = PERSISTENCE_DAYS,
) -> Result:
    scores, failures = build_scores(loaded, rates, deflator, fx, lag_days)

    control_tickers = [company.ticker for company in CONTROLS]
    lead_rows: dict[str, dict[str, float | None]] = {}
    impact_rows: list[dict[str, object]] = []
    false_alarms: dict[str, float] = {}

    for name, frame in scores.items():
        flags = raw_flags(frame, n_riskiest)
        # `false_alarm_months` refuses a control with no column rather than skipping it
        # silently. A control legitimately has none when this score refused on it, and
        # that refusal is already recorded in `failures` and published in the report --
        # so filtering here drops nothing from view.
        present_controls = [t for t in control_tickers if t in flags.columns]
        false_alarms[name] = false_alarm_months(flags, present_controls, persistence)

        for company in STRESSED:
            if company.ticker not in flags.columns:
                lead_rows.setdefault(company.ticker, {})[name] = None
                continue
            target = hard_event(company.ticker).date
            alarm = alarm_date(flags[company.ticker], persistence)
            lead_rows.setdefault(company.ticker, {})[name] = lead_months(alarm, target)
            if alarm is not None and alarm < target:
                # `measure` refuses a truncated forward window or a zero price. That
                # refusal costs one row, not the whole run: isolating it here is the
                # same contract `build_scores` honours above, and without it a single
                # event near the edge of the price history would lose all thirteen
                # companies' results.
                try:
                    impact = measure(loaded[company.ticker].prices, alarm, target)
                except CreditLabError as error:
                    failures[f"impact:{name}:{company.ticker}"] = str(error)
                    continue
                impact_rows.append(
                    {
                        "ticker": company.ticker,
                        "score": name,
                        "alarm": alarm,
                        "target": target,
                        "avoided": impact.avoided,
                        "already_suffered": impact.already_suffered,
                        "after_target": impact.after_target,
                        "fallen_angel": (
                            fallen_angel(company.ticker).date
                            if fallen_angel(company.ticker)
                            else None
                        ),
                    }
                )

    common = [
        company.ticker
        for company in STRESSED
        if all(company.ticker in scores[name].columns for name in SCORE_NAMES)
        and all(scores[name][company.ticker].notna().any() for name in SCORE_NAMES)
    ]

    # A score can have a column for a stressed name and still not have enough history
    # in front of that name's event to state a lead time honestly. Emeis' proceeding
    # opens before any statement in the fixture is published, so no accounting score
    # ever reaches MIN_OBSERVATIONS_BEFORE_EVENT for it -- that is the finding, not a
    # bug, and it is recorded here rather than silently producing a number anyway.
    insufficient: dict[str, str] = {}
    for name, frame in scores.items():
        for company in STRESSED:
            if company.ticker not in frame.columns:
                continue
            target = hard_event(company.ticker).date
            observed = frame[company.ticker].loc[:target].notna().sum()
            if observed < MIN_OBSERVATIONS_BEFORE_EVENT:
                message = (
                    f"{company.ticker}: only {observed} {name} observations before "
                    f"{target.date()}; a lead time computed on that is a number, not a "
                    "measurement"
                )
                insufficient[f"{name}:{company.ticker}"] = message
                lead_rows.setdefault(company.ticker, {})[name] = None

    secondary = secondary_leads(scores, n_riskiest, persistence)
    academic = academic_flags(scores)

    return Result(
        scores=scores,
        leads=pd.DataFrame(lead_rows).T.reindex(columns=list(SCORE_NAMES)),
        false_alarms=false_alarms,
        impacts=pd.DataFrame(impact_rows),
        failures=failures,
        common_sample=common,
        secondary=secondary,
        academic=academic,
        insufficient=insufficient,
    )


def secondary_leads(
    scores: dict[str, pd.DataFrame],
    n_riskiest: int = N_RISKIEST,
    persistence: int = PERSISTENCE_DAYS,
) -> pd.DataFrame:
    """Lead times against the fallen-angel target, for the two names that have one.

    Published beside the primary table, never averaged into it: two observations are
    a cross-check, not a statistic.
    """
    rows: dict[str, dict[str, float | None]] = {}
    for name, frame in scores.items():
        flags = raw_flags(frame, n_riskiest)
        for company in STRESSED:
            event = fallen_angel(company.ticker)
            if event is None or company.ticker not in flags.columns:
                continue
            alarm = alarm_date(flags[company.ticker], persistence)
            rows.setdefault(company.ticker, {})[name] = lead_months(alarm, event.date)
    return pd.DataFrame(rows).T.reindex(columns=list(SCORE_NAMES))


def robustness(
    loaded: dict[str, CompanyData],
    rates: pd.DataFrame,
    deflator: pd.Series,
    fx: pd.DataFrame,
) -> pd.DataFrame:
    """Median lead per score under each convention.

    A ranking that flips between variants is a null result, and reads as one.
    """
    rows = []
    for variant in VARIANTS:
        result = run(
            loaded,
            rates,
            deflator,
            fx,
            lag_days=variant["lag_days"],
            n_riskiest=variant["n_riskiest"],
            persistence=variant["persistence"],
        )
        row = {"variant": variant["label"]}
        row.update({name: result.leads[name].median() for name in SCORE_NAMES})
        rows.append(row)
    return pd.DataFrame(rows).set_index("variant")
