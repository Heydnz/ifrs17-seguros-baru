"""Discount curves used by the valuation (memo section 8; IFRS 17 par. 36, B72-B85).

* current curve: the end-of-month curve of the closing month for the portfolio's
  liquidity bucket (par. 36, B72(a));
* locked-in curve of a group: the average of the end-of-month curves of the months in
  which its contracts were recognised, weighted by the premiums written in each month
  (B72(b)-(c), B73). It is fixed once the group closes at the end of its cohort year.

Locked-in rates are used forward-consistently: a cash flow at time t of a contract that
has run e years since recognition is discounted to the valuation date with
D_L(e + t) / D_L(e), so that the accretion follows the forwards of the original curve.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .illiquidity import APPLICATION_RATIO, PORTFOLIO_LIQUIDITY
from .treasury_curves import DiscountCurve

ROOT = Path(__file__).resolve().parents[2]
CURVES = ROOT / "data" / "processed" / "discount_curves_halfyear.csv"


@lru_cache(maxsize=1)
def _grid() -> pd.DataFrame:
    df = pd.read_csv(CURVES, index_col=[0, 1])
    df.columns = df.columns.astype(float)
    return df / 100.0


def bucket_of(portfolio: str) -> str:
    return PORTFOLIO_LIQUIDITY[portfolio]


def curve_for(month, portfolio: str = "VT") -> DiscountCurve:
    """End-of-month curve for a portfolio (policy: HQM for every bucket, see illiquidity.py)."""
    key = str(pd.Period(month, freq="M"))
    row = _grid().loc[(key, bucket_of(portfolio))]
    if APPLICATION_RATIO[bucket_of(portfolio)] != 1.0:
        raise NotImplementedError("rebuild data/processed curves for a graded liquidity option")
    return DiscountCurve(maturities=row.index.to_numpy(float), spot_annual=row.to_numpy(float))


def weighted_curve(months, weights, portfolio: str = "VT") -> DiscountCurve:
    """Premium-weighted average of monthly curves (B73), averaging log discount factors."""
    months = [str(pd.Period(m, freq="M")) for m in months]
    w = np.asarray(weights, float)
    if w.sum() <= 0:
        raise ValueError("weights must be positive")
    w = w / w.sum()
    curves = [curve_for(m, portfolio) for m in months]
    mats = curves[0].maturities
    log_df = sum(wi * (-mats * np.log1p(c.spot_annual)) for wi, c in zip(w, curves))
    return DiscountCurve(maturities=mats, spot_annual=np.expm1(-log_df / mats))


def forward_discount(curve: DiscountCurve, elapsed_years, t_years) -> np.ndarray:
    """D(e + t) / D(e) for each policy (rows) and payment time (columns)."""
    e = np.atleast_1d(np.asarray(elapsed_years, float))[:, None]
    t = np.atleast_1d(np.asarray(t_years, float))[None, :]
    total = np.minimum(e + t, curve.maturities[-1])
    shape = np.broadcast_shapes(e.shape, t.shape)
    d_total = curve.discount(np.broadcast_to(total, shape).ravel()).reshape(shape)
    d_e = curve.discount(np.minimum(e[:, 0], curve.maturities[-1]))[:, None]
    return d_total / d_e


def flat_curve(rate: float, horizon: float = 100.0) -> DiscountCurve:
    grid = np.arange(0.5, horizon + 0.5, 0.5)
    return DiscountCurve(maturities=grid, spot_annual=np.full(grid.shape, rate))
