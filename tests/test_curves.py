"""Tests for the discount-curve module (IFRS 17 paragraph 36, B72-B85)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ifrs17.curves import (
    CONVERGENCE_TOLERANCE,
    MIN_ALPHA,
    UFR_BY_YEAR,
    calibrate_smith_wilson,
    convergence_point,
    curve_from_par,
    load_par_curves,
    weighted_average_spot,
    with_illiquidity_premium,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "treasury" / "par_month_end_2023_2025.csv"
CLOSINGS = ["2023-12-29", "2024-12-31", "2025-12-31"]


@pytest.fixture(scope="module")
def par():
    return load_par_curves(DATA)


@pytest.fixture(scope="module")
def closing_curves(par):
    return {d: curve_from_par(par.loc[d], UFR_BY_YEAR[pd.Timestamp(d).year]) for d in CLOSINGS}


def test_snapshot_has_36_month_ends(par):
    assert len(par) == 36
    assert par.index.min() == pd.Timestamp("2023-01-31")
    assert par.index.max() == pd.Timestamp("2025-12-31")
    assert par.notna().all().all()


@pytest.mark.parametrize("date", CLOSINGS)
def test_reprices_every_treasury_instrument(closing_curves, date):
    """B44 / B78(a): the curve must not contradict observable market prices."""
    curve = closing_curves[date]
    prices, times, C = curve.meta["instruments"]
    np.testing.assert_allclose(C @ curve.discount(times), prices, atol=1e-10)


@pytest.mark.parametrize("date", CLOSINGS)
def test_converges_to_ufr(closing_curves, date):
    curve = closing_curves[date]
    cp = convergence_point(curve.llp)
    assert cp == 70.0
    gap = abs(curve.forward_intensity(cp)[0] - np.log1p(curve.ufr))
    assert gap <= CONVERGENCE_TOLERANCE + 1e-9
    assert curve.alpha >= MIN_ALPHA


@pytest.mark.parametrize("date", CLOSINGS)
def test_discount_factors_are_positive_and_decreasing(closing_curves, date):
    df = closing_curves[date].discount(np.arange(0.5, 120.5, 0.5))
    assert np.all(df > 0)
    assert np.all(np.diff(df) < 0)


def test_flat_curve_at_ufr_is_reproduced_exactly():
    """If the market already sits on the UFR, Smith-Wilson adds nothing."""
    ufr = 0.033
    mats = np.array([1.0, 2.0, 5.0, 10.0, 30.0])
    prices = (1 + ufr) ** (-mats)
    curve = calibrate_smith_wilson(prices, mats, np.eye(len(mats)), ufr)
    t = np.array([0.5, 3.0, 17.0, 45.0, 100.0])
    np.testing.assert_allclose(curve.spot(t), ufr, atol=1e-12)
    assert curve.alpha == MIN_ALPHA


def test_illiquidity_premium_shifts_liquid_part_and_keeps_ufr(closing_curves):
    base = closing_curves["2025-12-31"]
    shifted = with_illiquidity_premium(base, 0.005)
    mats = np.arange(1.0, 31.0)
    np.testing.assert_allclose(shifted.spot(mats) - base.spot(mats), 0.005, atol=1e-10)
    cp = convergence_point(shifted.llp)
    assert abs(shifted.forward_intensity(cp)[0] - np.log1p(shifted.ufr)) <= CONVERGENCE_TOLERANCE + 1e-9
    assert with_illiquidity_premium(base, 0.0) is base


def test_locked_in_average_is_bounded_and_weight_invariant(par):
    year = par.loc["2024"]
    curves = [curve_from_par(row, UFR_BY_YEAR[2024]) for _, row in year.iterrows()]
    mats = np.arange(1.0, 41.0)
    spots = np.vstack([c.spot(mats) for c in curves])
    avg = weighted_average_spot(curves, np.arange(1, 13), mats)
    assert np.all(avg >= spots.min(axis=0) - 1e-12)
    assert np.all(avg <= spots.max(axis=0) + 1e-12)
    np.testing.assert_allclose(avg, weighted_average_spot(curves, 10 * np.arange(1, 13), mats))
    one_month = weighted_average_spot(curves, np.eye(12)[3], mats)
    np.testing.assert_allclose(one_month, spots[3])


def test_weighted_average_rejects_bad_weights(closing_curves):
    curves = list(closing_curves.values())
    with pytest.raises(ValueError):
        weighted_average_spot(curves, [0, 0, 0], [1.0])
    with pytest.raises(ValueError):
        weighted_average_spot(curves, [1, -1, 1], [1.0])
