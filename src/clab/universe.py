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
    # Legal Entity Identifier, the key of the issuer's ESEF filings; None where
    # filings.xbrl.org holds none (SAP, Siemens, and Nestle, which is not an EU issuer).
    lei: str | None = None


STRESSED: tuple[Company, ...] = (
    Company("Atos", "ATO.PA", "EUR", "IT services", "stressed", "5493001EZOOA66PTBR68"),
    Company("Casino Guichard", "CO.PA", "EUR", "Food retail", "stressed", "969500VHL8F83GBL6L29"),
    Company("Emeis", "EMEIS.PA", "EUR", "Healthcare", "stressed", "969500LHIH3NT7PK1V89"),
    Company(
        "Samhallsbyggnadsbolaget", "SBB-B.ST", "SEK", "Real estate", "stressed",
        "549300HX9MRFY47AH564",
    ),
    Company("Adler Group", "ADJ.DE", "EUR", "Real estate", "stressed", "391200OYYFJ3DWAMEC69"),
    Company("Intrum", "INTRUM.ST", "SEK", "Debt collection", "stressed", "549300UNCO2FCUWXX470"),
)

CONTROLS: tuple[Company, ...] = (
    Company("LVMH", "MC.PA", "EUR", "Luxury", "control", "IOG4E947OATN0KJYSD45"),
    Company("SAP", "SAP.DE", "EUR", "Software", "control"),
    Company("Air Liquide", "AI.PA", "EUR", "Industrial gases", "control", "969500MMPQVHK671GT54"),
    Company("Nestle", "NESN.SW", "CHF", "Food", "control"),
    Company("Siemens", "SIE.DE", "EUR", "Industrials", "control"),
    Company("Unilever", "UNA.AS", "EUR", "Consumer goods", "control", "549300MKFYEKVRWML317"),
    # Amsterdam, not London: the London line trades in pence, a unit that slips
    # silently into a market capitalisation.
    Company("Aroundtown", "AT1.DE", "EUR", "Real estate", "control", "529900H4DWG3KWMBMQ39"),
)

UNIVERSE: tuple[Company, ...] = STRESSED + CONTROLS


def by_ticker(ticker: str) -> Company:
    for company in UNIVERSE:
        if company.ticker == ticker:
            return company
    raise CreditLabError(f"{ticker} is not in the frozen universe")
