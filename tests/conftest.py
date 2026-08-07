"""Synthetic inputs: thirteen names, two fiscal years, one year of prices.

Small enough to reason about, complete enough to exercise the whole pipeline
offline. The frozen fixture in tests/fixtures/ is the separate, real-data guard.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from clab.data.loader import CompanyData
from clab.universe import UNIVERSE

CALENDAR = pd.date_range("2022-01-03", "2025-12-31", freq="B")


def _company_data(ticker: str, drift: float, break_line: bool) -> CompanyData:
    years = [pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]
    rows = {
        "Total Assets": [1000.0, 1000.0],
        "Total Liabilities Net Minority Interest": [600.0 + drift, 550.0],
        "Working Capital": [100.0 - drift, 100.0],
        "Current Assets": [300.0, 300.0],
        "Current Liabilities": [250.0, 250.0],
        "Stockholders Equity": [400.0 - drift, 450.0],
        "Ordinary Shares Number": [100.0, 100.0],
        "Current Debt And Capital Lease Obligation": [100.0, 100.0],
        "Long Term Debt And Capital Lease Obligation": [400.0 + drift, 400.0],
    }
    if not break_line:
        rows["Retained Earnings"] = [200.0 - drift, 220.0]
    balance = pd.DataFrame(rows, index=years).T
    income = pd.DataFrame(
        {"EBIT": [50.0 - drift, 60.0], "Net Income": [30.0 - drift, 40.0]}, index=years
    ).T
    cashflow = pd.DataFrame({"Operating Cash Flow": [70.0 - drift, 80.0]}, index=years).T

    rng = np.random.default_rng(abs(hash(ticker)) % (2**32))
    steps = rng.normal(-drift / 5000.0, 0.01, len(CALENDAR))
    prices = pd.Series(50.0 * np.exp(np.cumsum(steps)), index=CALENDAR)

    from clab.universe import by_ticker

    return CompanyData(by_ticker(ticker), balance, income, cashflow, prices)


def synthetic_inputs(break_ticker: str | None = None) -> dict:
    stressed = {"ATO.PA", "CO.PA", "EMEIS.PA", "SBB-B.ST", "ADJ.DE", "INTRUM.ST"}
    loaded = {
        company.ticker: _company_data(
            company.ticker,
            drift=120.0 if company.ticker in stressed else 0.0,
            break_line=(company.ticker == break_ticker),
        )
        for company in UNIVERSE
    }
    rates = pd.DataFrame(
        {code: pd.Series(0.02, index=CALENDAR) for code in ("EUR", "SEK", "CHF")}
    )
    return {
        "loaded": loaded,
        "rates": rates,
        "deflator": pd.Series(120.0, index=CALENDAR),
        "fx": pd.DataFrame(
            {code: pd.Series(1.1, index=CALENDAR) for code in ("EUR", "SEK", "CHF")}
        ),
    }
