"""Altman Z'', the four-variable variant for non-manufacturers.

    Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4

with X1 working capital over assets, X2 retained earnings over assets, X3 EBIT over
assets, X4 book equity over total liabilities.

The original Z is deliberately not used: its X4 divides market capitalisation by book
liabilities, which would make this score move daily. The whole point of the horse race
is annual accounting against daily market data, and blurring that line here would make
the comparison meaningless.

Returned negated, so that higher means riskier for every score in this package.
"""

from __future__ import annotations

import pandas as pd

from clab.data.loader import CompanyData, line
from clab.pointintime import PUBLICATION_LAG_DAYS, step_series


def z_double_prime(x1: float, x2: float, x3: float, x4: float) -> float:
    return 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4


def score(
    data: CompanyData,
    index: pd.DatetimeIndex,
    lag_days: int = PUBLICATION_LAG_DAYS,
) -> pd.Series:
    ticker = data.company.ticker
    assets = line(data.balance_sheet, "Total Assets", ticker)
    liabilities = line(data.balance_sheet, "Total Liabilities Net Minority Interest", ticker)
    working_capital = line(data.balance_sheet, "Working Capital", ticker)
    retained = line(data.balance_sheet, "Retained Earnings", ticker)
    equity = line(data.balance_sheet, "Stockholders Equity", ticker)
    ebit = line(data.income, "EBIT", ticker)

    annual = z_double_prime(
        working_capital / assets,
        retained / assets,
        ebit / assets,
        equity / liabilities,
    )
    return -step_series(annual.dropna().sort_index(), index, lag_days)
