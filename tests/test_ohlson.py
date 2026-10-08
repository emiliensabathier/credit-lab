"""Ohlson O-score, nine variables, applied as written."""

import pandas as pd
import pytest

from clab.scores.ohlson import o_score, probability


def test_o_score_matches_a_hand_computation():
    # -1.32 - 0.407*10 + 6.03*0.6 - 1.43*0.1 + 0.0757*1.2
    #       - 1.72*0 - 2.37*0.05 - 1.83*0.12 + 0.285*0 - 0.521*0.1
    # = -1.32 - 4.07 + 3.618 - 0.143 + 0.09084 - 0.1185 - 0.2196 - 0.0521
    value = o_score(
        size=10.0, tlta=0.6, wcta=0.1, clca=1.2, oeneg=0.0,
        nita=0.05, futl=0.12, intwo=0.0, chin=0.1,
    )
    assert value == pytest.approx(-2.21436, abs=1e-5)


def test_probability_is_the_logistic_of_the_score():
    assert probability(0.0) == pytest.approx(0.5)
    assert probability(10.0) > 0.999
    assert probability(-10.0) < 0.001


def test_oeneg_flags_negative_book_equity():
    with_flag = o_score(
        size=10.0, tlta=1.2, wcta=0.1, clca=1.2, oeneg=1.0,
        nita=0.05, futl=0.12, intwo=0.0, chin=0.1,
    )
    without_flag = o_score(
        size=10.0, tlta=1.2, wcta=0.1, clca=1.2, oeneg=0.0,
        nita=0.05, futl=0.12, intwo=0.0, chin=0.1,
    )
    assert with_flag == pytest.approx(without_flag - 1.72)


def test_score_is_a_staircase_that_starts_at_publication():
    from clab.data.loader import CompanyData
    from clab.scores.ohlson import score
    from clab.universe import by_ticker

    years = [pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]
    balance = pd.DataFrame(
        {
            "Total Assets": [1000.0, 900.0],
            "Total Liabilities Net Minority Interest": [600.0, 550.0],
            "Working Capital": [100.0, 90.0],
            "Current Assets": [300.0, 280.0],
            "Current Liabilities": [250.0, 240.0],
        },
        index=years,
    ).T
    income = pd.DataFrame({"Net Income": [50.0, 45.0]}, index=years).T
    cashflow = pd.DataFrame({"Operating Cash Flow": [70.0, 60.0]}, index=years).T
    prices = pd.Series(1.0, index=pd.date_range("2022-01-01", "2024-12-31", freq="D"))
    data = CompanyData(by_ticker("MC.PA"), balance, income, cashflow, prices)

    calendar = pd.date_range("2023-01-01", "2024-12-31", freq="D")
    # fx/deflator must cover every fiscal year end used by asof(), including the
    # earliest one (2022-12-31), which falls before `calendar` itself: in production
    # these series are loaded from FRED/Yahoo over a much longer history than the
    # output index, exactly as they are here.
    rate_history = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    deflator = pd.Series(120.0, index=rate_history)
    fx = pd.Series(1.1, index=rate_history)

    series = score(data, calendar, deflator, fx)
    # known_at(2022-12-31, 90) is 2023-03-31: the value published that day must hold,
    # unchanged, all the way through the day before the next publication.
    assert series.loc[pd.Timestamp("2023-03-31")] == series.loc[pd.Timestamp("2024-03-29")]
    assert series.loc[pd.Timestamp("2024-03-30")] != series.loc[pd.Timestamp("2024-03-29")]
    assert series.loc[pd.Timestamp("2023-01-01")] != series.loc[pd.Timestamp("2023-01-01")]  # NaN


def test_a_year_missing_from_one_statement_scores_nan_instead_of_failing():
    from clab.data.loader import CompanyData
    from clab.scores.ohlson import score
    from clab.universe import by_ticker

    years = [pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]
    balance = pd.DataFrame(
        {
            "Total Assets": [1000.0, 900.0],
            "Total Liabilities Net Minority Interest": [600.0, 550.0],
            "Working Capital": [100.0, 90.0],
            "Current Assets": [300.0, 280.0],
            "Current Liabilities": [250.0, 240.0],
        },
        index=years,
    ).T
    income = pd.DataFrame({"Net Income": [50.0, 45.0]}, index=years).T
    # The cash flow statement has no 2022 column at all, as when a balance sheet is
    # extended from a filing that the cash flow line could not be validated against.
    cashflow = pd.DataFrame({"Operating Cash Flow": [70.0]}, index=years[:1]).T
    data = CompanyData(by_ticker("MC.PA"), balance, income, cashflow, pd.Series(dtype=float))
    history = pd.date_range("2022-01-01", "2024-12-31", freq="D")

    series = score(data, pd.date_range("2023-01-01", "2024-12-31", freq="D"),
                   pd.Series(120.0, index=history), pd.Series(1.1, index=history))

    assert series.loc["2023-03-31":"2024-03-29"].isna().all()
    assert series.loc["2024-03-30":].notna().all()
