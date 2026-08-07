"""The thirteen issuers, frozen before the first run.

Six suffered a documented credit event between 2022 and 2024; seven did not and
serve as the false-alarm denominator. No name is added or removed after results
are seen — that promise is only worth anything because this file is committed
before any score is computed.
"""

from __future__ import annotations

from dataclasses import dataclass

from clab.errors import CreditLabError


@dataclass(frozen=True)
class Company:
    name: str
    ticker: str
    currency: str
    sector: str
    group: str  # "stressed" or "control"


STRESSED: tuple[Company, ...] = (
    Company("Atos", "ATO.PA", "EUR", "IT services", "stressed"),
    Company("Casino Guichard", "CO.PA", "EUR", "Food retail", "stressed"),
    Company("Emeis", "EMEIS.PA", "EUR", "Healthcare", "stressed"),
    Company("Samhallsbyggnadsbolaget", "SBB-B.ST", "SEK", "Real estate", "stressed"),
    Company("Adler Group", "ADJ.DE", "EUR", "Real estate", "stressed"),
    Company("Intrum", "INTRUM.ST", "SEK", "Debt collection", "stressed"),
)

CONTROLS: tuple[Company, ...] = (
    Company("LVMH", "MC.PA", "EUR", "Luxury", "control"),
    Company("SAP", "SAP.DE", "EUR", "Software", "control"),
    Company("Air Liquide", "AI.PA", "EUR", "Industrial gases", "control"),
    Company("Nestle", "NESN.SW", "CHF", "Food", "control"),
    Company("Siemens", "SIE.DE", "EUR", "Industrials", "control"),
    Company("Unilever", "UNA.AS", "EUR", "Consumer goods", "control"),
    # Amsterdam, not London: the London line trades in pence, a unit that slips
    # silently into a market capitalisation.
    Company("Aroundtown", "AT1.DE", "EUR", "Real estate", "control"),
)

UNIVERSE: tuple[Company, ...] = STRESSED + CONTROLS


def by_ticker(ticker: str) -> Company:
    for company in UNIVERSE:
        if company.ticker == ticker:
            return company
    raise CreditLabError(f"{ticker} is not in the frozen universe")
