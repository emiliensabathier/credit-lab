"""Ohlson's O-score (1980, model one), applied as written.

    O = -1.32 - 0.407*SIZE + 6.03*TLTA - 1.43*WCTA + 0.0757*CLCA
        - 1.72*OENEG - 2.37*NITA - 1.83*FUTL + 0.285*INTWO - 0.521*CHIN

SIZE is defined on the US GNP price level, so total assets are converted to dollars
at the rate of the day and deflated. Two honest caveats, both in the README rather
than hidden here: the deflator base is 2017=100 rather than 1968=100, a constant
shift in O that a rank rule is indifferent to; and FUTL uses operating cash flow as
the proxy for funds from operations, the closest line the data source reports.

Already oriented: a higher O means a higher probability of default.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from clab.data.loader import CompanyData, line
from clab.pointintime import PUBLICATION_LAG_DAYS, step_series


def o_score(
    *,
    size: float,
    tlta: float,
    wcta: float,
    clca: float,
    oeneg: float,
    nita: float,
    futl: float,
    intwo: float,
    chin: float,
) -> float:
    return (
        -1.32
        - 0.407 * size
        + 6.03 * tlta
        - 1.43 * wcta
        + 0.0757 * clca
        - 1.72 * oeneg
        - 2.37 * nita
        - 1.83 * futl
        + 0.285 * intwo
        - 0.521 * chin
    )


def probability(o: float) -> float:
    return 1.0 / (1.0 + np.exp(-o))


def score(
    data: CompanyData,
    index: pd.DatetimeIndex,
    deflator: pd.Series,
    fx: pd.Series,
    lag_days: int = PUBLICATION_LAG_DAYS,
) -> pd.Series:
    ticker = data.company.ticker
    assets = line(data.balance_sheet, "Total Assets", ticker)
    liabilities = line(data.balance_sheet, "Total Liabilities Net Minority Interest", ticker)
    working_capital = line(data.balance_sheet, "Working Capital", ticker)
    current_assets = line(data.balance_sheet, "Current Assets", ticker)
    current_liabilities = line(data.balance_sheet, "Current Liabilities", ticker)
    net_income = line(data.income, "Net Income", ticker)
    operating_cash = line(data.cashflow, "Operating Cash Flow", ticker)

    fiscal_ends = sorted(assets.dropna().index)
    # A statement with no column for a year reads as NaN there, as a NaN cell already does,
    # so that year scores NaN instead of failing the whole name.
    (liabilities, working_capital, current_assets, current_liabilities, net_income,
     operating_cash) = (
        series.reindex(fiscal_ends)
        for series in (liabilities, working_capital, current_assets, current_liabilities,
                       net_income, operating_cash)
    )
    values: dict[pd.Timestamp, float] = {}
    for position, end in enumerate(fiscal_ends):
        rate = float(fx.asof(end))
        level = float(deflator.asof(end))
        assets_usd_deflated = float(assets[end]) * rate / level
        previous = fiscal_ends[position - 1] if position > 0 else None
        current_ni = float(net_income[end])
        previous_ni = float(net_income[previous]) if previous is not None else current_ni
        denominator = abs(current_ni) + abs(previous_ni)
        values[end] = o_score(
            size=float(np.log(assets_usd_deflated)),
            tlta=float(liabilities[end] / assets[end]),
            wcta=float(working_capital[end] / assets[end]),
            clca=float(current_liabilities[end] / current_assets[end]),
            oeneg=1.0 if liabilities[end] > assets[end] else 0.0,
            nita=current_ni / float(assets[end]),
            futl=float(operating_cash[end] / liabilities[end]),
            intwo=1.0 if (current_ni < 0 and previous_ni < 0) else 0.0,
            chin=(current_ni - previous_ni) / denominator if denominator else 0.0,
        )

    annual = pd.Series(values).sort_index()
    return step_series(annual, index, lag_days)
