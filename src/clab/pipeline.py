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
    CENSORED,
    MEASURED,
    MIN_OBSERVATIONS_BEFORE_EVENT,
    MISSED,
    N_RISKIEST,
    PERSISTENCE_DAYS,
    UNTESTABLE,
    alarm_date,
    classify_lead,
    eligible,
    exclude_after,
    false_alarm_months,
    forced_control_months,
    raw_flags,
)
from clab.impact import measure
from clab.pointintime import PUBLICATION_LAG_DAYS
from clab.scores import altman, merton, ohlson
from clab.scores.thresholds import academic_flags
from clab.universe import CONTROLS, STRESSED

SCORE_NAMES = ("altman", "ohlson", "merton")

# A score that refused to compute a name at all (see `failures`), as distinct from
# one that computed it but too late to be tested.
NO_SCORE = "no score"

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
    status: pd.DataFrame
    false_alarms: dict[str, float]
    forced_false_alarms: dict[str, float]
    impacts: pd.DataFrame
    failures: dict[str, str]
    common_sample: list[str]
    secondary: pd.DataFrame
    secondary_status: pd.DataFrame
    academic: pd.DataFrame
    untestable: dict[str, str]


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


def _defaults() -> dict[str, pd.Timestamp]:
    return {company.ticker: hard_event(company.ticker).date for company in STRESSED}


def score_events(
    scores: dict[str, pd.DataFrame],
    targets: dict[str, pd.Timestamp],
    n_riskiest: int = N_RISKIEST,
    persistence: int = PERSISTENCE_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lead (months) and status for every (ticker, score) pair against `targets`.

    `scores` must already have defaulted names removed from the ranking. A ticker a
    score refused to compute gets NO_SCORE rather than a lead-time verdict.
    """
    leads: dict[str, dict[str, float | None]] = {ticker: {} for ticker in targets}
    status: dict[str, dict[str, str]] = {ticker: {} for ticker in targets}
    for name, frame in scores.items():
        flags = raw_flags(frame, n_riskiest)
        sessions = eligible(frame, n_riskiest)
        for ticker, target in targets.items():
            if ticker not in frame.columns:
                leads[ticker][name], status[ticker][name] = None, NO_SCORE
                continue
            lead = classify_lead(flags[ticker], sessions[ticker], target, persistence)
            leads[ticker][name], status[ticker][name] = lead.months, lead.status
    columns = [name for name in SCORE_NAMES if name in scores]
    return (
        pd.DataFrame(leads).T.reindex(columns=columns).astype(float),
        pd.DataFrame(status).T.reindex(columns=columns),
    )


def run(
    loaded: dict[str, CompanyData],
    rates: pd.DataFrame,
    deflator: pd.Series,
    fx: pd.DataFrame,
    lag_days: int = PUBLICATION_LAG_DAYS,
    n_riskiest: int = N_RISKIEST,
    persistence: int = PERSISTENCE_DAYS,
    prebuilt: tuple[dict[str, pd.DataFrame], dict[str, str]] | None = None,
) -> Result:
    """Run the full comparison.

    `prebuilt`, when given, is the `(scores, failures)` pair `build_scores` would
    have returned for this `loaded`/`rates`/`deflator`/`fx`/`lag_days` combination --
    passing it in skips rebuilding the score frames. The caller owns the consistency
    of that pair: scores built under a different `lag_days` than the one requested
    here would silently mislabel the result, since nothing downstream re-derives
    `lag_days` from the scores themselves.
    """
    scores, built_failures = (
        prebuilt if prebuilt is not None else build_scores(loaded, rates, deflator, fx, lag_days)
    )
    failures = dict(built_failures)
    defaults = _defaults()
    # Ranked frames: a name leaves the cross-section on its default date. The published
    # `scores` stay unmasked so the per-company charts still show the whole path.
    ranked = {name: exclude_after(frame, defaults) for name, frame in scores.items()}

    leads, status = score_events(ranked, defaults, n_riskiest, persistence)

    control_tickers = [company.ticker for company in CONTROLS]
    stressed_tickers = [company.ticker for company in STRESSED]
    # False alarms are counted only up to the last credit event. After it every
    # stressed name has left the ranking and the rule ranks controls against each
    # other, flagging `n_riskiest` of them by construction.
    last_event = max(defaults.values())
    false_alarms: dict[str, float] = {}
    forced_false_alarms: dict[str, float] = {}
    for name, frame in ranked.items():
        window = frame[frame.index < last_event]
        # `false_alarm_months` refuses a control with no column rather than skipping it
        # silently. A control legitimately has none when this score refused on it, and
        # that refusal is already recorded in `failures` and published in the report --
        # so filtering here drops nothing from view.
        flags = raw_flags(window, n_riskiest)
        present_controls = [t for t in control_tickers if t in flags.columns]
        false_alarms[name] = false_alarm_months(flags, present_controls, persistence)
        forced_false_alarms[name] = forced_control_months(
            eligible(window, n_riskiest), stressed_tickers, n_riskiest
        )

    impact_rows = _impacts(loaded, ranked, leads, status, failures, n_riskiest, persistence)

    common = [
        ticker
        for ticker in status.index
        if status.loc[ticker].isin([MEASURED, CENSORED, MISSED]).all()
    ]

    untestable: dict[str, str] = {}
    for name, frame in ranked.items():
        sessions = eligible(frame, n_riskiest)
        for ticker, target in defaults.items():
            if status.loc[ticker, name] != UNTESTABLE:
                continue
            observed = int(sessions[ticker][sessions.index < target].sum())
            untestable[f"{name}:{ticker}"] = (
                f"{ticker}: only {observed} ranked {name} sessions before {target.date()}, "
                f"{MIN_OBSERVATIONS_BEFORE_EVENT} required; the event is untestable on "
                "this data, which says nothing about the score"
            )

    secondary, secondary_status = secondary_leads(ranked, n_riskiest, persistence)

    return Result(
        scores=scores,
        leads=leads,
        status=status,
        false_alarms=false_alarms,
        forced_false_alarms=forced_false_alarms,
        impacts=pd.DataFrame(impact_rows),
        failures=failures,
        common_sample=common,
        secondary=secondary,
        secondary_status=secondary_status,
        academic=academic_flags(scores),
        untestable=untestable,
    )


def _impacts(
    loaded: dict[str, CompanyData],
    ranked: dict[str, pd.DataFrame],
    leads: pd.DataFrame,
    status: pd.DataFrame,
    failures: dict[str, str],
    n_riskiest: int,
    persistence: int,
) -> list[dict[str, object]]:
    """One row per alarm that came in time, with what it was worth.

    `failures` is extended in place with per-row `measure` refusals: a refusal costs
    one row, not the whole run -- the same contract `build_scores` honours.
    """
    rows: list[dict[str, object]] = []
    for name, frame in ranked.items():
        flags = raw_flags(frame, n_riskiest)
        for company in STRESSED:
            ticker = company.ticker
            if status.loc[ticker, name] not in (MEASURED, CENSORED):
                continue
            target = hard_event(ticker).date
            alarm = alarm_date(flags[ticker], persistence)
            try:
                impact = measure(loaded[ticker].prices, alarm, target)
            except CreditLabError as error:
                failures[f"impact:{name}:{ticker}"] = str(error)
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "score": name,
                    "alarm": alarm,
                    "target": target,
                    "lead": leads.loc[ticker, name],
                    "censored": status.loc[ticker, name] == CENSORED,
                    "avoided": impact.avoided,
                    "already_suffered": impact.already_suffered,
                    "after_target": impact.after_target,
                }
            )
    return rows


def secondary_leads(
    ranked: dict[str, pd.DataFrame],
    n_riskiest: int = N_RISKIEST,
    persistence: int = PERSISTENCE_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leads and statuses against the fallen-angel target, for the two names that have one.

    Published beside the primary table, never averaged into it: two observations are
    a cross-check, not a statistic.
    """
    targets = {
        company.ticker: fallen_angel(company.ticker).date
        for company in STRESSED
        if fallen_angel(company.ticker) is not None
    }
    return score_events(ranked, targets, n_riskiest, persistence)


def robustness(
    loaded: dict[str, CompanyData],
    rates: pd.DataFrame,
    deflator: pd.Series,
    fx: pd.DataFrame,
) -> pd.DataFrame:
    """Per score and convention: events testable, alarms in time, censored, median.

    The median is taken over measured leads only. A censored lead is a lower bound,
    and a median that pooled lower bounds with measurements would be neither; with
    the counts beside it, a median over one or two leads reads as what it is.

    Scores depend only on the publication lag; persistence and quartile width change
    how they are ranked, not what they are. Building once per distinct lag turns six
    full pipeline runs into three, which is the difference between a test suite that
    runs and one that times out.

    A ranking that flips between variants is a null result, and reads as one.
    """
    built = {
        lag: build_scores(loaded, rates, deflator, fx, lag)
        for lag in sorted({variant["lag_days"] for variant in VARIANTS})
    }
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
            prebuilt=built[variant["lag_days"]],
        )
        row: dict[tuple[str, str], float] = {}
        for name in SCORE_NAMES:
            status = result.status[name]
            row[(name, "testable")] = int(status.isin([MEASURED, CENSORED, MISSED]).sum())
            row[(name, "in time")] = int(status.isin([MEASURED, CENSORED]).sum())
            row[(name, "censored")] = int((status == CENSORED).sum())
            row[(name, "median measured")] = result.leads[name][status == MEASURED].median()
        rows.append(row)
    table = pd.DataFrame(rows, index=pd.Index([v["label"] for v in VARIANTS], name="variant"))
    table.columns = pd.MultiIndex.from_tuples(table.columns)
    return table
