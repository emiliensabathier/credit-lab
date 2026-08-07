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
from clab.universe import CONTROLS, STRESSED

SCORE_NAMES = ("altman", "ohlson", "merton")


@dataclass(frozen=True)
class Result:
    scores: dict[str, pd.DataFrame]
    leads: pd.DataFrame
    false_alarms: dict[str, float]
    impacts: pd.DataFrame
    failures: dict[str, str]
    common_sample: list[str]


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

    return Result(
        scores=scores,
        leads=pd.DataFrame(lead_rows).T.reindex(columns=list(SCORE_NAMES)),
        false_alarms=false_alarms,
        impacts=pd.DataFrame(impact_rows),
        failures=failures,
        common_sample=common,
    )
