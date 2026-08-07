"""Hand-curated credit event timeline.

No free data source publishes rating history, so these dates were sourced one by
one from primary documents. That research changed the design: it showed the
"fallen angel" target exists for only two of the six names, and that Aroundtown
never had an event at all — which is why it sits in the control group.

Primary target rule, applied uniformly: the date on which the first
court-supervised restructuring proceeding became public (conciliation, accelerated
safeguard, English Part 26A plan, Chapter 11). Where no proceeding exists, the
first SD/D rating assigned by an agency. SBB is the only name taking that fallback.

Where the opening date and the announcement date differ by a day or two, the public
date is used; both are recorded in the description.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from clab.errors import CreditLabError


@dataclass(frozen=True)
class CreditEvent:
    ticker: str
    date: pd.Timestamp
    kind: str  # "proceeding", "rating_default", or "fallen_angel"
    description: str
    source: str


HARD_EVENTS: tuple[CreditEvent, ...] = (
    CreditEvent(
        "EMEIS.PA",
        pd.Timestamp("2022-04-20"),
        "proceeding",
        "First conciliation proceeding opened by the Nanterre Commercial Court. The "
        "protocol was concluded on 2022-06-03 and approved on 2022-06-10, the judgment "
        "recording the 2022-04-20 opening.",
        "ORPEA press release, 2022-06-12 (Businesswire 20220612005056)",
    ),
    CreditEvent(
        "ADJ.DE",
        pd.Timestamp("2023-04-12"),
        "proceeding",
        "Part 26A restructuring plan of AGPS BondCo plc sanctioned by the English High "
        "Court (Leech J.); written judgment 2023-04-21. Overturned on appeal 2024-01-23, "
        "which does not undo the fact of the proceeding.",
        "English High Court sanction, 2023-04-12",
    ),
    CreditEvent(
        "CO.PA",
        pd.Timestamp("2023-05-26"),
        "proceeding",
        "Conciliation proceeding opened by the President of the Paris Commercial Court "
        "on 2023-05-25, announced by the company on 2023-05-26.",
        "Groupe Casino press release, 2023-05-26 (GlobeNewswire 2676847)",
    ),
    CreditEvent(
        "ATO.PA",
        pd.Timestamp("2024-03-26"),
        "proceeding",
        "Conciliation proceeding opened by order of the President of the Pontoise "
        "Commercial Court on 2024-03-25, announced 2024-03-26; transferred to Nanterre "
        "on 2024-05-30, accelerated safeguard opened 2024-07-24.",
        "Atos press release, 2024-03-26",
    ),
    CreditEvent(
        "SBB-B.ST",
        pd.Timestamp("2024-07-03"),
        "rating_default",
        "S&P assigned SD after a distressed exchange of bonds at a deep discount. SBB "
        "never entered a court-supervised proceeding, so it is the only name measured "
        "under the fallback rule.",
        "S&P Global Ratings action, 2024-07-03",
    ),
    CreditEvent(
        "INTRUM.ST",
        pd.Timestamp("2024-11-15"),
        "proceeding",
        "Voluntary Chapter 11 petition filed in the U.S. Bankruptcy Court for the "
        "Southern District of Texas; prepackaged solicitation launched 2024-10-18, plan "
        "confirmed 2024-12-31.",
        "Intrum press release, 2024-11-15",
    ),
)

FALLEN_ANGELS: tuple[CreditEvent, ...] = (
    CreditEvent(
        "ATO.PA",
        pd.Timestamp("2022-07-13"),
        "fallen_angel",
        "S&P lowered Atos from BBB- to BB, negative outlook: loss of investment grade.",
        "Atos press release, 2022-07-13",
    ),
    CreditEvent(
        "SBB-B.ST",
        pd.Timestamp("2023-05-08"),
        "fallen_angel",
        "S&P lowered SBB from BBB- to BB+, negative outlook, alongside the dividend halt.",
        "S&P Global Ratings research update, 2023-05-08",
    ),
)


def hard_event(ticker: str) -> CreditEvent:
    for event in HARD_EVENTS:
        if event.ticker == ticker:
            return event
    raise CreditLabError(f"{ticker} has no recorded credit event")


def fallen_angel(ticker: str) -> CreditEvent | None:
    for event in FALLEN_ANGELS:
        if event.ticker == ticker:
            return event
    return None
