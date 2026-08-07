"""Merton, solved KMV-style.

The round-trip test is the one that matters: build E and sigma_E from known V and
sigma_A through the closed forms, hand those two to the solver, and require it to
return V and sigma_A. It proves the solver inverts the model it claims to invert.
"""

import numpy as np
import pytest

from clab.errors import SolverError
from clab.scores.merton import (
    distance_to_default,
    equity_from_assets,
    solve_assets,
)


def test_round_trip_recovers_the_asset_value_and_volatility():
    v, sigma_a, d, r, t = 1000.0, 0.25, 600.0, 0.03, 1.0
    e, sigma_e = equity_from_assets(v, sigma_a, d, r, t)

    v_hat, sigma_hat = solve_assets(e, sigma_e, d, r, t)

    assert v_hat == pytest.approx(v, rel=1e-6)
    assert sigma_hat == pytest.approx(sigma_a, rel=1e-6)


def test_equity_is_worth_more_than_its_intrinsic_value():
    v, sigma_a, d, r, t = 1000.0, 0.25, 600.0, 0.03, 1.0
    e, _ = equity_from_assets(v, sigma_a, d, r, t)
    assert e > v - d * np.exp(-r * t)


def test_distance_to_default_falls_as_leverage_rises():
    lightly_levered = distance_to_default(1000.0, 0.25, 300.0, 0.03, 1.0)
    heavily_levered = distance_to_default(1000.0, 0.25, 900.0, 0.03, 1.0)
    assert heavily_levered < lightly_levered


def test_solver_refuses_a_non_positive_equity_value():
    with pytest.raises(SolverError):
        solve_assets(0.0, 0.4, 600.0, 0.03, 1.0)


def test_solver_refuses_a_non_positive_default_point():
    with pytest.raises(SolverError):
        solve_assets(400.0, 0.4, 0.0, 0.03, 1.0)


@pytest.mark.parametrize(
    "v, sigma_a, d, r",
    [
        (5e10, 0.35, 3e10, 0.03),
        (2e11, 0.20, 1.5e11, 0.02),
        (8e9, 0.90, 7.5e9, 0.04),
    ],
)
def test_round_trip_recovers_the_asset_value_and_volatility_at_realistic_scale(
    v: float, sigma_a: float, d: float, r: float
):
    """The equity equation is a currency amount (order 1e9-1e11 here) and the
    volatility equation is order 1e-1; an absolute residual vector makes the
    volatility equation numerically invisible beside the equity one at this scale.
    This is the test that would have caught that bug -- the earlier round-trip test
    used values small enough (order 1e3) that the scale mismatch never surfaced.
    """
    t = 1.0
    e, sigma_e = equity_from_assets(v, sigma_a, d, r, t)

    v_hat, sigma_hat = solve_assets(e, sigma_e, d, r, t)

    assert v_hat == pytest.approx(v, rel=1e-6)
    assert sigma_hat == pytest.approx(sigma_a, rel=1e-6)


def test_solver_refuses_a_genuinely_unsolvable_input():
    """Twenty orders of magnitude between equity and debt with a near-zero equity
    volatility. An exhaustive multi-start search (V0 spanning nine orders of
    magnitude around D, sigma_A0 from 1e-6 to 2.0) never drove the residual norm
    below roughly 1e7: this is not a solvable root that a better guess would find,
    so the fix must still refuse it rather than accept whatever the solver last held.
    """
    with pytest.raises(SolverError):
        solve_assets(1.0, 0.001, 1e20, 0.03, 1.0)
