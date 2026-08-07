"""The universe is frozen before the first run; these tests are the padlock."""

from clab.universe import CONTROLS, STRESSED, UNIVERSE, by_ticker


def test_universe_holds_six_stressed_and_seven_controls():
    assert len(STRESSED) == 6
    assert len(CONTROLS) == 7
    assert len(UNIVERSE) == 13


def test_every_ticker_is_unique():
    tickers = [company.ticker for company in UNIVERSE]
    assert len(set(tickers)) == len(tickers)


def test_aroundtown_is_a_control_not_a_stressed_name():
    # It suffered the same 2022-2023 property crunch as SBB and Adler but never
    # fell below BBB- and never entered a proceeding. It is the hardest control.
    assert by_ticker("AT1.DE").group == "control"


def test_stressed_names_span_more_than_one_sector():
    assert len({company.sector for company in STRESSED}) >= 4


def test_by_ticker_raises_on_an_unknown_ticker():
    import pytest

    from clab.errors import CreditLabError

    with pytest.raises(CreditLabError):
        by_ticker("NOPE.XX")
