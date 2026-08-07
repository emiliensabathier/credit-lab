"""The loader is the only module allowed to touch the network, so it is the only
module that has to be injectable. These tests never touch it."""

import pandas as pd
import pytest

from clab.data.loader import CompanyData, line, load_company, load_rates
from clab.errors import CurrencyMismatchError, MissingLineError
from clab.universe import by_ticker


def _frame(rows: dict[str, list[float]], years: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=[pd.Timestamp(y) for y in years]).T


def test_line_returns_the_row_when_present():
    frame = _frame({"Total Assets": [100.0, 90.0]}, ["2024-12-31", "2023-12-31"])
    assert line(frame, "Total Assets", "X.PA").iloc[0] == 100.0


def test_line_names_the_company_and_the_line_when_absent():
    frame = _frame({"Total Assets": [100.0]}, ["2024-12-31"])
    with pytest.raises(MissingLineError) as excinfo:
        line(frame, "Retained Earnings", "CO.PA")
    assert "CO.PA" in str(excinfo.value)
    assert "Retained Earnings" in str(excinfo.value)


def test_load_company_refuses_a_currency_mismatch():
    company = by_ticker("MC.PA")

    def fetcher(ticker: str) -> dict:
        return {
            "balance_sheet": _frame({"Total Assets": [1.0]}, ["2024-12-31"]),
            "income": _frame({"EBIT": [1.0]}, ["2024-12-31"]),
            "cashflow": _frame({"Operating Cash Flow": [1.0]}, ["2024-12-31"]),
            "prices": pd.Series([1.0], index=[pd.Timestamp("2024-12-31")]),
            "currency": "GBp",
            "financial_currency": "EUR",
        }

    with pytest.raises(CurrencyMismatchError):
        load_company(company, fetcher=fetcher)


def test_load_company_returns_company_data_when_currencies_agree():
    company = by_ticker("MC.PA")

    def fetcher(ticker: str) -> dict:
        return {
            "balance_sheet": _frame({"Total Assets": [1.0]}, ["2024-12-31"]),
            "income": _frame({"EBIT": [1.0]}, ["2024-12-31"]),
            "cashflow": _frame({"Operating Cash Flow": [1.0]}, ["2024-12-31"]),
            "prices": pd.Series([1.0], index=[pd.Timestamp("2024-12-31")]),
            "currency": "EUR",
            "financial_currency": "EUR",
        }

    data = load_company(company, fetcher=fetcher)
    assert isinstance(data, CompanyData)
    assert data.company.ticker == "MC.PA"


def test_load_rates_converts_percent_to_decimal_and_forward_fills():
    def fetcher(series_id: str) -> pd.Series:
        return pd.Series(
            [2.0, 2.5],
            index=[pd.Timestamp("2023-01-01"), pd.Timestamp("2023-03-01")],
        )

    rates = load_rates(fetcher=fetcher)
    assert set(rates.columns) == {"EUR", "SEK", "CHF"}
    assert rates.loc[pd.Timestamp("2023-02-01"), "EUR"] == pytest.approx(0.02)
    assert rates.loc[pd.Timestamp("2023-03-15"), "EUR"] == pytest.approx(0.025)
