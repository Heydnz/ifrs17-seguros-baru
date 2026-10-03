"""Tests for the TNC + illiquidity premium discount curves."""

import numpy as np
import pandas as pd
import pytest

from ifrs17.treasury_curves import (
    HALF_YEAR_GRID,
    build_discount_curve,
    illiquidity_premium,
    read_treasury_spot_file,
    semiannual_to_annual,
)


def _toy_curves():
    t = HALF_YEAR_GRID
    tnc = pd.Series(0.040 + 0.006 * (1 - np.exp(-t / 8)), index=t)  # upward sloping
    hqm = tnc + 0.0060 + 0.0020 * np.exp(-t / 10)  # 60-80 bp spread
    return tnc, hqm


def test_grid_has_200_maturities():
    assert len(HALF_YEAR_GRID) == 200
    assert HALF_YEAR_GRID[0] == 0.5 and HALF_YEAR_GRID[-1] == 100.0


def test_full_spread_reproduces_hqm():
    """TNC + (HQM - TNC) = HQM: the identity behind the 'full spread' option."""
    tnc, hqm = _toy_curves()
    curve = build_discount_curve(tnc, hqm, credit_share=0.0, application_ratio=1.0)
    np.testing.assert_allclose(curve.spot_annual, semiannual_to_annual(hqm.to_numpy()), atol=1e-15)


def test_full_credit_share_gives_tnc():
    tnc, hqm = _toy_curves()
    curve = build_discount_curve(tnc, hqm, credit_share=1.0)
    np.testing.assert_allclose(curve.spot_annual, semiannual_to_annual(tnc.to_numpy()), atol=1e-15)


def test_premium_scales_and_is_floored():
    tnc, hqm = _toy_curves()
    full = illiquidity_premium(hqm, tnc, 0.0)
    np.testing.assert_allclose(illiquidity_premium(hqm, tnc, 0.55, 0.5), full * 0.45 * 0.5)
    inverted = illiquidity_premium(tnc, hqm, 0.0)  # negative spread
    assert (inverted == 0).all()
    with pytest.raises(ValueError):
        illiquidity_premium(hqm, tnc, 1.2)
    with pytest.raises(ValueError):
        illiquidity_premium(hqm, tnc, 0.5, 1.5)


def test_curve_lies_between_tnc_and_hqm():
    tnc, hqm = _toy_curves()
    curve = build_discount_curve(tnc, hqm, credit_share=0.55)
    assert np.all(curve.spot_annual >= semiannual_to_annual(tnc.to_numpy()) - 1e-15)
    assert np.all(curve.spot_annual <= semiannual_to_annual(hqm.to_numpy()) + 1e-15)


def test_monthly_interpolation():
    tnc, hqm = _toy_curves()
    curve = build_discount_curve(tnc, hqm, credit_share=0.55)
    table = curve.monthly_table()
    assert len(table) == 1200
    # grid points are reproduced exactly (every 6 months)
    np.testing.assert_allclose(table.loc[6::6, "spot_annual"].to_numpy(), curve.spot_annual, rtol=1e-12)
    # short end: flat at the 0.5-year rate
    np.testing.assert_allclose(table.loc[1:5, "spot_annual"].to_numpy(), curve.spot_annual[0], rtol=1e-12)
    # discount factors decrease and the monthly rate is consistent with the annual one
    assert np.all(np.diff(table["discount_factor"]) < 0)
    np.testing.assert_allclose((1 + table["spot_monthly"]) ** 12 - 1, table["spot_annual"], rtol=1e-12)


def test_missing_maturities_are_rejected():
    tnc, hqm = _toy_curves()
    with pytest.raises(ValueError):
        build_discount_curve(tnc.iloc[:-1], hqm, credit_share=0.5)


def _write_workbook(path, two_row_header: bool):
    months = pd.period_range("2024-11", "2025-01", freq="M")
    rows = [["Treasury HQM spot rates (toy file)"] + [None] * len(months), [None] * (len(months) + 1)]
    if two_row_header:
        rows.append([None] + [m.year for m in months])
        rows.append(["Maturity"] + [m.strftime("%b") for m in months])
    else:
        rows.append(["Maturity"] + [m.strftime("%b %Y") for m in months])
    for t in HALF_YEAR_GRID:
        rows.append([t] + [4.0 + 0.01 * t + 0.1 * i for i in range(len(months))])  # percent
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    return months


@pytest.mark.parametrize("two_row_header", [False, True])
def test_reads_treasury_layouts(tmp_path, two_row_header):
    path = tmp_path / "toy.xlsx"
    months = _write_workbook(path, two_row_header)
    table = read_treasury_spot_file(path)
    assert list(table.index) == list(months)
    assert table.shape == (3, 200)
    assert table.loc[months[0], 0.5] == pytest.approx(0.04005)
    assert table.loc[months[2], 100.0] == pytest.approx(0.052)
