"""P&C under the PAA: classification, LRC, onerous test, LIC and the CAR eligibility test."""

import numpy as np
import pandas as pd
import pytest

from ifrs17 import pc
from ifrs17.data import load


@pytest.fixture(scope="module")
def res():
    return pc.run_all()


def test_classification_story(res):
    c = res["classification"].set_index(["line", "segment", "cohort"])["class"]
    assert c[("AUTO", "particulares", 2023)] == "SIG"
    assert c[("AUTO", "flotas", 2023)] == "RES" and c[("AUTO", "flotas", 2024)] == "RES"
    assert c[("AUTO", "flotas", 2025)] == "ONE"  # the 2024 parts inflation is known (par. 18)
    assert (c.xs("INC", level="line") == "SIG").all() and (c.xs("TRC", level="line") == "SIG").all()


def test_lrc_and_revenue(res):
    last = res["lrc"][-1].set_index("group")
    expired = last.loc[["AUTO-2023-SIG", "INC-2023-SIG"]]
    assert np.allclose(expired["revenue_cum"], expired["premium_written"])  # B126: all premium earned
    assert np.allclose(expired["lrc_excl_lc"], 0.0, atol=5.0)
    pnl = pd.concat(res["pnl"])
    total_rev = pnl.groupby("group")["insurance_revenue"].sum()
    assert total_rev["AUTO-2023-SIG"] == pytest.approx(last.loc["AUTO-2023-SIG", "premium_written"])


def test_onerous_test_for_fleets(res):
    lrc24 = res["lrc"][1].set_index("group")
    assert lrc24.loc["AUTO-2024-RES", "loss_component"] > 0  # par. 57-58 at the 2024 closing
    for lrc in res["lrc"]:
        sig = lrc[lrc["group"].str.endswith("SIG")]
        assert (sig["loss_component"] == 0).all()


@pytest.mark.parametrize("closing", ["2023-12-31", "2024-12-31", "2025-12-31"])
def test_lic_is_close_to_hindsight_for_motor(res, closing):
    i = ["2023-12-31", "2024-12-31", "2025-12-31"].index(closing)
    lic = res["lic"][i]
    est = lic.loc[lic["line"] == "AUTO", ["case", "ibnr"]].sum().sum()
    claims = load("auto_claims")
    pay = load("auto_payments").merge(claims[["claim_id", "occurrence_date"]], on="claim_id")
    actual = pay[(pay["occurrence_date"] <= closing) & (pay["payment_date"] > closing)]["amount"].sum()
    assert est == pytest.approx(actual, rel=0.15)


def test_lic_risk_adjustment_confidence(res):
    for lic in res["lic"]:
        level = lic.attrs["confidence"]["equivalent_level"]
        assert 0.65 < level < pc.CONFIDENCE_PC + 1e-9  # diversification lowers the 75% standalone level
        assert (lic["ra"] >= 0).all() and (lic["pv"] <= lic["undiscounted"] + 1e-6).all()


def test_discounting_policy(res):
    lic = res["lic"][-1]
    inc = lic[lic["line"] == "INC"]
    assert np.allclose(inc["pv"], inc["undiscounted"])  # fire/home pays within the year (59(b))
    auto_rc = lic[(lic["line"] == "AUTO") & (lic["coverage"] == "RC")]
    assert (auto_rc["pv"] < auto_rc["undiscounted"]).all()


@pytest.mark.parametrize("cohort", [2023, 2024, 2025])
def test_car_is_eligible_for_the_paa(cohort):
    t = pc.trc_eligibility(cohort)
    assert t.attrs["eligible"] and t.attrs["max_relative"] <= pc.TRC_THRESHOLD
    base = t[t["scenario"] == "base"]
    assert (base["lrc_paa"] >= 0).all()
