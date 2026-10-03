"""IFRS 17 discount curves from the US Treasury TNC and HQM yield curves.

Method agreed with the project owner (bottom-up, IFRS 17 B79-B80):

1. Base curve: Treasury Nominal Coupon-issue (TNC) end-of-month spot rates,
   published every half year from 0.5 to 100 years. Beyond 30 years the
   Treasury holds the forward rate constant at the 15-30 year average, so no
   further extrapolation is needed.
2. Illiquidity premium by maturity: the High Quality Market (HQM, AAA-A
   corporate bonds) end-of-month spot rate minus the TNC spot rate, net of the
   share of that spread that compensates credit risk (B79, B84(b), B85), and
   scaled by the liquidity bucket of the portfolio.
3. Discount curve = TNC + illiquidity premium, converted from semiannual to
   annual effective compounding and interpolated to monthly maturities.

Note: with ``credit_share = 0`` and an application ratio of 100%, the result is
exactly the HQM curve, because TNC + (HQM - TNC) = HQM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

HALF_YEAR_GRID = np.round(np.arange(0.5, 100.0 + 1e-9, 0.5), 1)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# --------------------------------------------------------------------------
# Reading the Treasury spreadsheets
# --------------------------------------------------------------------------
def _to_period(value) -> pd.Period | None:
    """Turn a header cell (datetime, 'Jan 2024', '2024-01', 'January 2024', ...) into a month."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)) or hasattr(value, "year"):
        try:
            return pd.Timestamp(value).to_period("M")
        except (TypeError, ValueError):
            return None
    text = str(value).strip().lower()
    m = re.match(r"^([a-z]{3})[a-z]*\.?[\s\-/]*(\d{4})$", text) or re.match(r"^(\d{4})[\s\-/]*([a-z]{3})[a-z]*$", text)
    if m:
        a, b = m.groups()
        mon, year = (a, b) if a.isalpha() else (b, a)
        if mon in MONTHS:
            return pd.Period(year=int(year), month=MONTHS[mon], freq="M")
    m = re.match(r"^(\d{4})[\-/](\d{1,2})", text)
    if m:
        return pd.Period(year=int(m.group(1)), month=int(m.group(2)), freq="M")
    return None


def read_treasury_spot_file(path) -> pd.DataFrame:
    """Read a Treasury TNC/HQM spot-rate workbook into a table indexed by month
    (rows) with maturities 0.5..100 as columns, in decimals (semiannual compounding).

    The workbooks put maturities down the first column and months across the
    columns, sometimes with the year and the month in two separate header rows.
    The parser looks for the block of rows whose first cell is a maturity on the
    half-year grid and builds month labels from the rows above it.
    """
    raw = pd.read_excel(path, header=None, sheet_name=0)
    first = pd.to_numeric(raw.iloc[:, 0], errors="coerce")
    is_maturity = first.round(1).isin(HALF_YEAR_GRID) & (first.round(1) == first)
    rows = np.flatnonzero(is_maturity.to_numpy())
    if len(rows) < 100:
        raise ValueError(f"{path}: could not find the maturity column (found {len(rows)} rows)")
    start = rows[0]
    header = raw.iloc[:start]

    months: dict[int, pd.Period] = {}
    year_carry = None
    for col in range(1, raw.shape[1]):
        cells = [header.iat[r, col] for r in range(header.shape[0])]
        period = None
        for c in reversed(cells):  # a full label such as 'Jan 2024' or a date
            period = _to_period(c)
            if period is not None:
                break
        if period is None:  # two-row header: a year somewhere above, a month name below
            year = next((int(float(c)) for c in cells if _is_year(c)), None)
            year_carry = year or year_carry
            mon = next((MONTHS[str(c).strip().lower()[:3]] for c in reversed(cells)
                        if isinstance(c, str) and str(c).strip().lower()[:3] in MONTHS), None)
            if mon and year_carry:
                period = pd.Period(year=year_carry, month=mon, freq="M")
        if period is not None:
            months[col] = period

    if not months:
        raise ValueError(f"{path}: could not read the month headers")
    data = raw.iloc[rows, list(months)].apply(pd.to_numeric, errors="coerce")
    data.index = first.iloc[rows].round(1).to_numpy()
    data.columns = list(months.values())
    table = data.T.sort_index()
    table = table[~table.index.duplicated(keep="last")].dropna(how="all")
    if table.stack().max() > 1.0:  # percent -> decimal
        table = table / 100.0
    table.index.name = "month"
    table.columns.name = "maturity_years"
    return table


def _is_year(cell) -> bool:
    try:
        v = float(cell)
    except (TypeError, ValueError):
        return False
    return 1970 <= v <= 2100 and v == int(v)


# --------------------------------------------------------------------------
# Curve construction
# --------------------------------------------------------------------------
def semiannual_to_annual(rate):
    return (1.0 + np.asarray(rate, dtype=float) / 2.0) ** 2 - 1.0


def illiquidity_premium(hqm: pd.Series, tnc: pd.Series, credit_share: float, application_ratio: float = 1.0) -> pd.Series:
    """(HQM - TNC) by maturity, floored at zero, net of the credit share and
    scaled by the liquidity bucket (semiannual compounding, decimals)."""
    if not 0.0 <= credit_share <= 1.0:
        raise ValueError("credit_share must be between 0 and 1")
    if not 0.0 <= application_ratio <= 1.0:
        raise ValueError("application_ratio must be between 0 and 1")
    spread = (hqm - tnc).clip(lower=0.0)
    return spread * (1.0 - credit_share) * application_ratio


@dataclass
class DiscountCurve:
    """Spot curve on the half-year grid (annual effective) with monthly interpolation."""

    maturities: np.ndarray  # 0.5 .. 100
    spot_annual: np.ndarray

    def discount(self, t) -> np.ndarray:
        """Discount factors. Log-linear between grid points (constant forward over
        each half year); below 0.5 years the 0.5-year spot rate is held flat."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        if np.any(t < 0) or np.any(t > self.maturities[-1] + 1e-9):
            raise ValueError("maturity outside 0..100 years")
        log_df = -self.maturities * np.log1p(self.spot_annual)
        out = np.interp(t, self.maturities, log_df)
        short = t < self.maturities[0]
        out[short] = -t[short] * np.log1p(self.spot_annual[0])
        return np.exp(out)

    def spot(self, t) -> np.ndarray:
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return self.discount(t) ** (-1.0 / t) - 1.0

    def monthly_table(self, months: int = 1200) -> pd.DataFrame:
        """Monthly maturities 1..months: discount factor, annual effective spot
        rate and its monthly equivalent (1 + r) ** (1 / 12) - 1."""
        m = np.arange(1, months + 1)
        t = m / 12.0
        df = self.discount(t)
        spot = df ** (-1.0 / t) - 1.0
        return pd.DataFrame(
            {"discount_factor": df, "spot_annual": spot, "spot_monthly": (1.0 + spot) ** (1.0 / 12.0) - 1.0},
            index=pd.Index(m, name="maturity_months"),
        )


def build_discount_curve(tnc: pd.Series, hqm: pd.Series, credit_share: float, application_ratio: float = 1.0) -> DiscountCurve:
    """TNC + illiquidity premium for one month (both inputs semiannual, decimals)."""
    tnc = tnc.reindex(HALF_YEAR_GRID)
    hqm = hqm.reindex(HALF_YEAR_GRID)
    if tnc.isna().any() or hqm.isna().any():
        raise ValueError("TNC and HQM must cover every maturity from 0.5 to 100 years")
    semi = tnc + illiquidity_premium(hqm, tnc, credit_share, application_ratio)
    return DiscountCurve(maturities=HALF_YEAR_GRID.astype(float), spot_annual=semiannual_to_annual(semi.to_numpy()))
