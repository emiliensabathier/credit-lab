"""Every failure this package can produce, named.

Nothing here is caught and swallowed: a raise means a number could not be produced
honestly, and producing one anyway would be worse than refusing.
"""

from __future__ import annotations


class CreditLabError(Exception):
    """Base class for every deliberate refusal in this package."""


class MissingLineError(CreditLabError):
    """A required accounting line is absent from the reported statements."""


class SolverError(CreditLabError):
    """A numerical solver failed to converge on a usable root."""


class CurrencyMismatchError(CreditLabError):
    """Reporting currency and trading currency differ, with no conversion supplied."""


class InsufficientHistoryError(CreditLabError):
    """Not enough observations before the event to state a lead time."""
