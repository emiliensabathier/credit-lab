"""The event timeline is hand-curated data; these tests guard its invariants."""

import pandas as pd
import pytest

from clab.errors import CreditLabError
from clab.events import FALLEN_ANGELS, HARD_EVENTS, fallen_angel, hard_event
from clab.universe import STRESSED


def test_every_stressed_name_has_exactly_one_hard_event():
    tickers = [event.ticker for event in HARD_EVENTS]
    assert sorted(tickers) == sorted(company.ticker for company in STRESSED)


def test_no_control_name_has_an_event():
    event_tickers = {event.ticker for event in HARD_EVENTS + FALLEN_ANGELS}
    assert "AT1.DE" not in event_tickers
    assert "MC.PA" not in event_tickers


def test_every_event_carries_a_source():
    for event in HARD_EVENTS + FALLEN_ANGELS:
        assert event.source.strip(), f"{event.ticker} has an unsourced date"


def test_only_two_names_have_a_fallen_angel_date():
    # Casino and Adler were already speculative grade before the window, Emeis has
    # no public S&P rating, Intrum was already rated below BBB-. This asymmetry is
    # published, not averaged away.
    assert sorted(event.ticker for event in FALLEN_ANGELS) == ["ATO.PA", "SBB-B.ST"]


def test_sbb_is_the_only_name_measured_on_a_rating_rather_than_a_proceeding():
    fallbacks = [event.ticker for event in HARD_EVENTS if event.kind == "rating_default"]
    assert fallbacks == ["SBB-B.ST"]


def test_emeis_event_is_the_earliest_of_the_six():
    earliest = min(HARD_EVENTS, key=lambda event: event.date)
    assert earliest.ticker == "EMEIS.PA"
    assert earliest.date == pd.Timestamp("2022-04-20")


def test_hard_event_raises_for_a_control_name():
    with pytest.raises(CreditLabError):
        hard_event("MC.PA")


def test_fallen_angel_returns_none_when_the_name_never_fell():
    assert fallen_angel("CO.PA") is None
