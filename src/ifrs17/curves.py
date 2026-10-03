"""Discount curves for IFRS 17 (paragraph 36 and B72-B85).

Bottom-up construction (B80):

1. US Treasury par yields (CMT) at each valuation date are the liquid,
   (almost) credit-risk-free input (B79).
2. A Smith-Wilson curve is calibrated so that it reprices every observed
   Treasury instrument exactly (B44, B78(a)) and is extrapolated beyond the
   last liquid point towards an ultimate forward rate (UFR).
3. An illiquidity premium is added to the liquid part and the curve is
   re-extrapolated to the same UFR (see ``with_illiquidity_premium``).
4. Locked-in curves for groups of contracts are premium-weighted averages
   of the month-end curves of the issue year (B72(b), B73).

Conventions
-----------
* Input yields are in decimals (4.25% -> 0.0425).
* Bills (maturity <= 6 months) are zero-coupon: price = 1 / (1 + y * t).
* Notes and bonds (maturity >= 1 year) are par bonds with semiannual
  coupons y/2, priced at 1.
* Output spot rates are annual effective rates: r(t) = P(t) ** (-1 / t) - 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import brentq

TENOR_YEARS: dict[str, float] = {
    "1M": 1 / 12,
    "2M": 2 / 12,
    "3M": 3 / 12,
    "4M": 4 / 12,
    "6M": 0.5,
    "1Y": 1.0,
    "2Y": 2.0,
    "3Y": 3.0,
    "5Y": 5.0,
    "7Y": 7.0,
    "10Y": 10.0,
    "20Y": 20.0,
    "30Y": 30.0,
}

# Smith-Wilson parameters (EIOPA methodology used as public reference).
LAST_LIQUID_POINT = 30.0  # longest Treasury par yield
MIN_ALPHA = 0.05
CONVERGENCE_TOLERANCE = 1e-4  # 1 bp, continuous compounding

# EIOPA UFR in force at each year-end valuation. USD uses the same 2% inflation
# target as EUR, so the UFR matches: 3.45% during 2023, 3.30% from 1 Jan 2024.
UFR_BY_YEAR: dict[int, float] = {2023: 0.0345, 2024: 0.0330, 2025: 0.0330}


def convergence_point(llp: float = LAST_LIQUID_POINT) -> float:
    """EIOPA convergence point: max(LLP + 40, 60) years."""
    return max(llp + 40.0, 60.0)


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def load_par_curves(path: str) -> pd.DataFrame:
    """Load par yields (in percent) indexed by date; return decimals."""
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    missing = [c for c in TENOR_YEARS if c not in df.columns]
    if missing:
        raise ValueError(f"missing tenor columns: {missing}")
    return df[list(TENOR_YEARS)] / 100.0


# --------------------------------------------------------------------------
# Instruments
# --------------------------------------------------------------------------
def instrument_cash_flows(par_yields: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cash-flow matrix of the observed Treasury instruments.

    Returns ``(prices, times, C)`` where ``C[i, j]`` is the cash flow of
    instrument ``i`` at time ``times[j]``.
    """
    bill_times = [TENOR_YEARS[k] for k in par_yields.index if TENOR_YEARS[k] < 0.5]
    coupon_grid = np.arange(0.5, LAST_LIQUID_POINT + 1e-9, 0.5)
    times = np.unique(np.round(np.concatenate([bill_times, coupon_grid]), 12))

    prices, rows = [], []
    for tenor, y in par_yields.items():
        t = TENOR_YEARS[tenor]
        cf = np.zeros_like(times)
        if t <= 0.5:  # bill: zero coupon, simple-interest price
            cf[np.isclose(times, t)] = 1.0
            prices.append(1.0 / (1.0 + y * t))
        else:  # par bond, semiannual coupon
            pay = (times > 1e-12) & (times <= t + 1e-9) & np.isclose((times * 2) % 1, 0)
            cf[pay] = y / 2.0
            cf[np.isclose(times, t)] += 1.0
            prices.append(1.0)
        rows.append(cf)
    return np.array(prices), times, np.array(rows)


# --------------------------------------------------------------------------
# Smith-Wilson
# --------------------------------------------------------------------------
def _wilson(t: np.ndarray, u: np.ndarray, alpha: float, omega: float) -> np.ndarray:
    t = np.atleast_1d(t).astype(float)[:, None]
    u = np.atleast_1d(u).astype(float)[None, :]
    lo, hi = np.minimum(t, u), np.maximum(t, u)
    return np.exp(-omega * (t + u)) * (
        alpha * lo - 0.5 * np.exp(-alpha * hi) * (np.exp(alpha * lo) - np.exp(-alpha * lo))
    )


@dataclass
class SmithWilsonCurve:
    """Smith-Wilson discount curve calibrated to coupon instruments."""

    times: np.ndarray  # cash-flow dates of the calibration instruments
    weights: np.ndarray  # C^T zeta
    ufr: float  # annual effective
    alpha: float
    llp: float = LAST_LIQUID_POINT
    meta: dict = field(default_factory=dict)

    @property
    def omega(self) -> float:
        return float(np.log1p(self.ufr))

    def discount(self, t) -> np.ndarray:
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return np.exp(-self.omega * t) + _wilson(t, self.times, self.alpha, self.omega) @ self.weights

    def spot(self, t) -> np.ndarray:
        """Annual effective spot rates."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return self.discount(t) ** (-1.0 / t) - 1.0

    def forward_intensity(self, t, h: float = 1e-4) -> np.ndarray:
        """Instantaneous forward rate, continuous compounding."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return -(np.log(self.discount(t + h)) - np.log(self.discount(t - h))) / (2 * h)

    def forward_annual(self, t) -> np.ndarray:
        """One-year forward rate starting at t, annual effective."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return self.discount(t) / self.discount(t + 1.0) - 1.0


def _fit(prices, times, C, ufr, alpha, llp, meta=None) -> SmithWilsonCurve:
    omega = np.log1p(ufr)
    mu = np.exp(-omega * times)
    W = _wilson(times, times, alpha, omega)
    zeta = np.linalg.solve(C @ W @ C.T, prices - C @ mu)
    return SmithWilsonCurve(times=times, weights=C.T @ zeta, ufr=ufr, alpha=alpha, llp=llp, meta=meta or {})


def calibrate_smith_wilson(
    prices: np.ndarray,
    times: np.ndarray,
    C: np.ndarray,
    ufr: float,
    llp: float = LAST_LIQUID_POINT,
    tol: float = CONVERGENCE_TOLERANCE,
    alpha_min: float = MIN_ALPHA,
) -> SmithWilsonCurve:
    """Fit Smith-Wilson and choose the smallest alpha >= alpha_min such that the
    forward intensity at the convergence point is within ``tol`` of ln(1 + UFR)."""
    cp = convergence_point(llp)
    omega = np.log1p(ufr)

    def gap(a: float) -> float:
        curve = _fit(prices, times, C, ufr, a, llp)
        return abs(curve.forward_intensity(cp)[0] - omega) - tol

    alpha = alpha_min
    if gap(alpha_min) > 0:
        alpha = brentq(gap, alpha_min, 2.0, xtol=1e-10)
    return _fit(prices, times, C, ufr, alpha, llp, meta={"convergence_point": cp})


def curve_from_par(par_yields: pd.Series, ufr: float, llp: float = LAST_LIQUID_POINT) -> SmithWilsonCurve:
    """Risk-free curve for one valuation date from Treasury par yields."""
    prices, times, C = instrument_cash_flows(par_yields.dropna())
    curve = calibrate_smith_wilson(prices, times, C, ufr, llp)
    curve.meta["instruments"] = (prices, times, C)
    return curve


# --------------------------------------------------------------------------
# Illiquidity premium (B80)
# --------------------------------------------------------------------------
def with_illiquidity_premium(curve: SmithWilsonCurve, premium: float) -> SmithWilsonCurve:
    """Add a constant illiquidity premium to the annual spot rates of the liquid
    part (1..LLP) and re-extrapolate to the same UFR.

    Following the EIOPA treatment of the volatility adjustment, the premium
    applies to the observable part of the curve; the extrapolated part still
    converges to the UFR, which is a long-term macro anchor.
    """
    if premium == 0:
        return curve
    mats = np.arange(1.0, curve.llp + 1e-9, 1.0)
    shifted = (1.0 + curve.spot(mats) + premium) ** (-mats)
    C = np.eye(len(mats))
    out = calibrate_smith_wilson(shifted, mats, C, curve.ufr, curve.llp)
    out.meta["illiquidity_premium"] = premium
    return out


# --------------------------------------------------------------------------
# Locked-in curves (B72(b), B73)
# --------------------------------------------------------------------------
def weighted_average_spot(curves: list[SmithWilsonCurve], weights, maturities) -> np.ndarray:
    """Weighted average of annual spot rates, e.g. month-end curves of the
    issue year weighted by premiums written in each month (B73)."""
    w = np.asarray(weights, dtype=float)
    if np.any(w < 0) or w.sum() <= 0:
        raise ValueError("weights must be non-negative and not all zero")
    w = w / w.sum()
    spots = np.vstack([c.spot(maturities) for c in curves])
    return w @ spots


def spot_table(curves: dict, maturities) -> pd.DataFrame:
    """Annual spot rates (decimals) by valuation date and maturity."""
    return pd.DataFrame({d: c.spot(maturities) for d, c in curves.items()}, index=pd.Index(maturities, name="maturity")).T
