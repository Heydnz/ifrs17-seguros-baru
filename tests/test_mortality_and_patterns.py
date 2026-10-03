"""Checks on the external data behind the non-financial assumptions (CSO 1980 and CAS patterns)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ifrs17.mortality import cso1980, monthly_rate, qx

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


def test_cso1980_table_shape_and_known_values():
    t = cso1980()
    assert list(t.index) == list(range(100))
    # spot values from SOA tables 42 (male ANB) and 36 (female ANB)
    assert t.loc[40, "M"] == pytest.approx(0.00302)
    assert t.loc[40, "F"] == pytest.approx(0.00242)
    assert t.loc[65, "M"] == pytest.approx(0.02542)
    assert t.loc[65, "F"] == pytest.approx(0.01459)


def test_cso1980_shape_is_sensible():
    t = cso1980()
    adult = t.loc[30:98]
    assert (adult["M"].diff().dropna() > 0).all()  # increasing with age from 30
    assert (adult["F"].diff().dropna() > 0).all()
    assert (t.loc[15:98, "M"] > t.loc[15:98, "F"]).all()  # men die younger at every adult age


def test_qx_factor_improvement_and_closure():
    base = qx("M", [40])[0]
    assert qx("M", [40], factor=0.75)[0] == pytest.approx(0.75 * base)
    assert qx("M", [40], factor=0.75, improvement=0.01, years_from_base=2)[0] == pytest.approx(0.75 * base * 0.99**2)
    assert qx("F", [99, 105]).tolist() == [1.0, 1.0]
    assert qx("M", [98], factor=50.0)[0] == 1.0  # capped


def test_monthly_rate_compounds_back_to_annual():
    q = np.array([0.0, 0.003, 0.1, 1.0])
    m = monthly_rate(q)
    np.testing.assert_allclose(1 - (1 - m) ** 12, q, atol=1e-15)


@pytest.mark.skipif(not (PROCESSED / "claims_patterns.csv").exists(), reason="run scripts/build_claims_patterns.py")
def test_cas_patterns_are_proper_and_liability_is_long_tailed():
    p = pd.read_csv(PROCESSED / "claims_patterns.csv")
    for line, g in p.groupby("line"):
        g = g.sort_values("development_year")
        assert len(g) == 10
        assert g["cumulative_paid"].is_monotonic_increasing
        assert g["cumulative_paid"].iloc[-1] == pytest.approx(1.0)
        assert g["incremental_paid"].sum() == pytest.approx(1.0, abs=1e-6)
    first = p[p["development_year"] == 1].set_index("line")["cumulative_paid"]
    assert first["comauto"] < first["ppauto"] < 0.5  # commercial auto pays slower


@pytest.mark.skipif(not (PROCESSED / "claims_cv.csv").exists(), reason="run scripts/build_claims_patterns.py")
def test_reserve_cv_falls_with_size():
    cv = pd.read_csv(PROCESSED / "claims_cv.csv").set_index("line")
    assert (cv["b"] < 0).all()  # bigger books are relatively less uncertain
    assert (cv["companies"] > 50).all()
