"""Altman Z'' — the four-variable variant, on book values only.

The original Z uses market capitalisation in X4, which would make an accounting
score partly daily and destroy the contrast this project measures. Z'' stays a
pure annual staircase.
"""

import pandas as pd
import pytest

from clab.data.loader import CompanyData
from clab.errors import MissingLineError
from clab.scores.altman import score, z_double_prime
from clab.universe import by_ticker


def test_z_double_prime_matches_a_hand_computation():
    # 6.56*0.10 + 3.26*0.20 + 6.72*0.05 + 1.05*0.50
    # = 0.656 + 0.652 + 0.336 + 0.525 = 2.169
    assert z_double_prime(0.10, 0.20, 0.05, 0.50) == pytest.approx(2.169)


def _data(ticker: str, with_retained_earnings: bool = True) -> CompanyData:
    years = [pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]
    rows = {
        "Total Assets": [1000.0, 900.0],
        "Total Liabilities Net Minority Interest": [600.0, 550.0],
        "Working Capital": [100.0, 90.0],
        "Stockholders Equity": [400.0, 350.0],
    }
    if with_retained_earnings:
        rows["Retained Earnings"] = [200.0, 180.0]
    balance = pd.DataFrame(rows, index=years).T
    income = pd.DataFrame({"EBIT": [50.0, 45.0]}, index=years).T
    cashflow = pd.DataFrame({"Operating Cash Flow": [70.0, 60.0]}, index=years).T
    prices = pd.Series(1.0, index=pd.date_range("2022-01-01", "2024-12-31", freq="D"))
    return CompanyData(by_ticker(ticker), balance, income, cashflow, prices)


def test_score_is_negated_so_that_higher_means_riskier():
    index = pd.date_range("2024-06-01", "2024-06-30", freq="D")
    series = score(_data("MC.PA"), index)
    x1, x2, x3, x4 = 100 / 1000, 200 / 1000, 50 / 1000, 400 / 600
    assert series.iloc[0] == pytest.approx(-z_double_prime(x1, x2, x3, x4))


def test_score_is_a_staircase_not_a_daily_series():
    index = pd.date_range("2024-04-01", "2024-12-31", freq="D")
    series = score(_data("MC.PA", ), index).dropna()
    assert series.nunique() == 1


def test_score_refuses_when_retained_earnings_are_not_reported():
    index = pd.date_range("2024-06-01", "2024-06-30", freq="D")
    with pytest.raises(MissingLineError) as excinfo:
        score(_data("CO.PA", with_retained_earnings=False), index)
    assert "CO.PA" in str(excinfo.value)
