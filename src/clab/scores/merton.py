"""Merton's structural model, solved KMV-style.

Equity is a call option on the firm's assets struck at the default point:

    E      = V*N(d1) - D*exp(-r*T)*N(d2)
    sigma_E = (V/E) * N(d1) * sigma_A

Neither V nor sigma_A is observable, so the two equations are solved together for
the two unknowns. Failure to converge raises rather than returning the last iterate:
a distance-to-default computed from an unconverged asset value looks exactly like a
converged one on a chart.

The default point follows the KMV convention: short-term debt plus half of long-term
debt. The drift is the risk-free rate rather than an estimated asset drift -- the
risk-neutral convention, stated rather than fitted on a year of data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import root
from scipy.stats import norm

from clab.data.loader import CompanyData, line
from clab.errors import SolverError
from clab.pointintime import PUBLICATION_LAG_DAYS, step_series

VOL_WINDOW_DAYS = 252
HORIZON_YEARS = 1.0
TRADING_DAYS = 252

# The lease-inclusive lines, verified present on all thirteen issuers. The bare
# "Current Debt" / "Long Term Debt" lines are absent for Nestle, so using them would
# force a per-company fallback -- and a default point that quietly means one thing for
# twelve names and another for the thirteenth is exactly the silent inconsistency this
# package refuses elsewhere. Including capitalised leases is also the better read: Casino
# and Emeis run on leased stores and facilities, and excluding those obligations would
# understate their default point substantially.
CURRENT_DEBT_LINE = "Current Debt And Capital Lease Obligation"
LONG_TERM_DEBT_LINE = "Long Term Debt And Capital Lease Obligation"

# Fallback starting points for sigma_A, tried in order only when the primary guess
# (sigma_E * E / (E + D)) fails to converge. That primary guess collapses toward zero
# at extreme leverage -- E a fraction of a percent of D -- and starts the solver in a
# numerically flat region where it drives sigma_A to underflow instead of climbing
# toward the true root, even though a root exists nearby. Verified against this
# project's own thirteen-issuer universe: every real date that failed on the primary
# guess (Casino and Emeis, both deep in distress) converged on the first candidate
# here. This is a bounded, deterministic retry, not an unbounded search: it still
# raises SolverError if every candidate fails.
SIGMA_A0_FALLBACKS: tuple[float, ...] = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)


def _d1_d2(v: float, sigma_a: float, d: float, r: float, t: float) -> tuple[float, float]:
    d1 = (np.log(v / d) + (r + 0.5 * sigma_a**2) * t) / (sigma_a * np.sqrt(t))
    return d1, d1 - sigma_a * np.sqrt(t)


def equity_from_assets(
    v: float, sigma_a: float, d: float, r: float, t: float
) -> tuple[float, float]:
    """Closed-form equity value and equity volatility implied by known assets."""
    d1, d2 = _d1_d2(v, sigma_a, d, r, t)
    e = v * norm.cdf(d1) - d * np.exp(-r * t) * norm.cdf(d2)
    sigma_e = (v / e) * norm.cdf(d1) * sigma_a
    return float(e), float(sigma_e)


def solve_assets(e: float, sigma_e: float, d: float, r: float, t: float) -> tuple[float, float]:
    """Back out asset value and asset volatility from observed equity.

    Solved in log(V), log(sigma_A) with relative residuals. The equity equation is a
    currency amount -- order 1e9 or larger for a real issuer -- while the volatility
    equation is order 1e-1; an absolute residual vector lets `hybr` drive the equity
    residual to zero while the volatility equation stays numerically invisible beside
    it, which is exactly the failure this reformulation removes. Relative residuals
    put both equations on the same order of magnitude regardless of company size.
    Solving in log-space makes V and sigma_A positive by construction, so the
    discontinuous non-positive-iterate clamp a trust-region method handled badly is
    no longer needed, and a converged root can no longer be non-positive.
    """
    if e <= 0:
        raise SolverError(f"equity value {e} is not positive; Merton has no meaning here")
    if d <= 0:
        raise SolverError(f"default point {d} is not positive; Merton has no meaning here")
    if sigma_e <= 0:
        raise SolverError(f"equity volatility {sigma_e} is not positive")

    def residuals(log_unknowns: np.ndarray) -> list[float]:
        v, sigma_a = np.exp(log_unknowns)
        e_hat, sigma_e_hat = equity_from_assets(v, sigma_a, d, r, t)
        return [e_hat / e - 1.0, sigma_e_hat / sigma_e - 1.0]

    log_v0 = np.log(e + d)
    guess = np.array([log_v0, np.log(sigma_e * e / (e + d))])
    solution = root(residuals, guess, method="hybr")
    for sigma_a0 in SIGMA_A0_FALLBACKS:
        if solution.success:
            break
        solution = root(residuals, np.array([log_v0, np.log(sigma_a0)]), method="hybr")

    if not solution.success:
        raise SolverError(
            f"Merton solver did not converge for E={e:.4g}, sigma_E={sigma_e:.4g}, "
            f"D={d:.4g}: {solution.message}"
        )
    v, sigma_a = (float(x) for x in np.exp(solution.x))
    return v, sigma_a


def distance_to_default(v: float, sigma_a: float, d: float, r: float, t: float) -> float:
    return float((np.log(v / d) + (r - 0.5 * sigma_a**2) * t) / (sigma_a * np.sqrt(t)))


def default_point(short_term_debt: float, long_term_debt: float) -> float:
    return short_term_debt + 0.5 * long_term_debt


def score(
    data: CompanyData,
    index: pd.DatetimeIndex,
    rates: pd.Series,
    lag_days: int = PUBLICATION_LAG_DAYS,
) -> pd.Series:
    """Daily -DtD, using only what was public on each date."""
    ticker = data.company.ticker
    shares = line(data.balance_sheet, "Ordinary Shares Number", ticker)
    current_debt = line(data.balance_sheet, CURRENT_DEBT_LINE, ticker)
    long_term_debt = line(data.balance_sheet, LONG_TERM_DEBT_LINE, ticker)

    prices = data.prices.reindex(index).ffill()
    returns = np.log(prices / prices.shift(1))
    sigma_e = returns.rolling(VOL_WINDOW_DAYS).std() * np.sqrt(TRADING_DAYS)

    shares_step = step_series(shares.dropna().sort_index(), index, lag_days)
    debt_step = step_series(
        default_point(current_debt, long_term_debt).dropna().sort_index(), index, lag_days
    )

    values: dict[pd.Timestamp, float] = {}
    for date in index:
        equity = prices.get(date, np.nan) * shares_step.get(date, np.nan)
        volatility = sigma_e.get(date, np.nan)
        debt = debt_step.get(date, np.nan)
        rate = rates.asof(date)
        if not np.isfinite([equity, volatility, debt, rate]).all():
            continue
        v, sigma_a = solve_assets(
            float(equity), float(volatility), float(debt), float(rate), HORIZON_YEARS
        )
        values[date] = -distance_to_default(v, sigma_a, float(debt), float(rate), HORIZON_YEARS)

    return pd.Series(values).reindex(index)
