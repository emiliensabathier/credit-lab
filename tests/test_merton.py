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
