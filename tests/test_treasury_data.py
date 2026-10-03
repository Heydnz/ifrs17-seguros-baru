"""Checks on the Treasury TNC and HQM end-of-month workbooks actually used."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ifrs17.curves import UFR_BY_YEAR, curve_from_par, load_par_curves
from ifrs17.illiquidity import APPLICATION_RATIO, APPLICATION_RATIO_BY_LIQUIDITY, CREDIT_SHARE, CREDIT_SHARE_CDS
from ifrs17.treasury_curves import build_discount_curve, read_treasury_spot_file, semiannual_to_annual

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "treasury"
CLOSINGS = {"2023-12": "2023-12-29", "2024-12": "2024-12-31", "2025-12": "2025-12-31"}

pytestmark = pytest.mark.skipif(not (RAW / "tnceom_23_27.xlsx").exists(), reason="Treasury workbooks not present")


@pytest.fixture(scope="module")
def curves():
    tnc = read_treasury_spot_file(RAW / "tnceom_23_27.xlsx")
    hqm = pd.concat([read_treasury_spot_file(RAW / f) for f in ("hqmeom_19_23.xls", "hqmeom_24_28.xls")])
    return tnc, hqm[~hqm.index.duplicated(keep="last")].sort_index()


def test_every_month_of_2023_2025_is_complete(curves):
    tnc, hqm = curves
    months = pd.period_range("2023-01", "2025-12", freq="M")
    for table in (tnc, hqm):
        assert all(m in table.index for m in months)
        assert table.loc[months].notna().all().all()
        assert table.shape[1] == 200


@pytest.mark.parametrize("month", list(CLOSINGS))
def test_hqm_spread_is_positive_at_closings(curves, month):
    tnc, hqm = curves
    spread = hqm.loc[pd.Period(month, "M")] - tnc.loc[pd.Period(month, "M")]
    assert (spread > 0).all()
    assert spread.max() < 0.02  # under 200 bp, a sanity bound for AAA-A bonds


@pytest.mark.parametrize("month", list(CLOSINGS))
def test_tnc_agrees_with_smith_wilson_cross_check(curves, month):
    """Two independent fits of the Treasury market should agree within 15 bp up to 30 years."""
    tnc, _ = curves
    par = load_par_curves(RAW / "par_month_end_2023_2025.csv")
    period = pd.Period(month, "M")
    sw = curve_from_par(par.loc[CLOSINGS[month]], UFR_BY_YEAR[period.year])
    mats = np.array([1.0, 2.0, 5.0, 10.0, 20.0, 30.0])
    diff = semiannual_to_annual(tnc.loc[period, mats].to_numpy()) - sw.spot(mats)
    assert np.abs(diff).max() < 0.0015


@pytest.mark.parametrize("month", list(CLOSINGS))
def test_policy_curve_is_hqm(curves, month):
    """Chosen policy: no credit deduction and 100% for every portfolio, so the curve is HQM."""
    tnc, hqm = curves
    p = pd.Period(month, "M")
    for ratio in APPLICATION_RATIO.values():
        spot = build_discount_curve(tnc.loc[p], hqm.loc[p], CREDIT_SHARE, ratio).spot_annual
        np.testing.assert_allclose(spot, semiannual_to_annual(hqm.loc[p].to_numpy()), atol=1e-15)


@pytest.mark.parametrize("month", list(CLOSINGS))
def test_cds_option_curves_are_ordered_between_tnc_and_hqm(curves, month):
    tnc, hqm = curves
    p = pd.Period(month, "M")
    spots = {b: build_discount_curve(tnc.loc[p], hqm.loc[p], CREDIT_SHARE_CDS, r).spot_annual
             for b, r in APPLICATION_RATIO_BY_LIQUIDITY.items()}
    low_bound = semiannual_to_annual(tnc.loc[p].to_numpy())
    high_bound = semiannual_to_annual(hqm.loc[p].to_numpy())
    assert np.all(low_bound <= spots["low"] + 1e-15)
    assert np.all(spots["low"] <= spots["medium"]) and np.all(spots["medium"] <= spots["high"])
    assert np.all(spots["high"] <= high_bound + 1e-15)
