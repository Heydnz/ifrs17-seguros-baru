"""Savings life (investment component) and the quota share on term life (memo sections 5, 12 and 13)."""

import numpy as np
import pandas as pd
import pytest

from ifrs17 import assumptions as A
from ifrs17 import reinsurance, savings, term_life
from ifrs17.discounting import curve_for

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def va():
    return savings.run_all()


@pytest.fixture(scope="module")
def vt():
    return term_life.run_all()


@pytest.fixture(scope="module")
def re(vt):
    return reinsurance.run_all(vt)


def test_declared_rates_follow_the_commitment():
    """B98: one-year HQM at the previous year end less 1.25%, floored at 2.5%, to 0.05%."""
    for year, month in ((2023, "2023-01"), (2024, "2023-12"), (2025, "2024-12")):
        r = curve_for(month, "VA").spot(1.0)[0] - A.SAVINGS_LIFE.crediting_spread
        assert A.SAVINGS_LIFE.declared_rate[year] == pytest.approx(max(0.025, round(r / 0.0005) * 0.0005))


def test_savings_groups_are_profitable(va):
    assert not (va["classification"]["class"] == "ONE").any()


def test_investment_component_is_kept_out_of_revenue(va):
    for out in va["closings"]:
        for g, r in out.results.items():
            d = out.details.set_index("group").loc[g]
            # revenue covers insurance service only: far below premiums, and surrenders do not count
            assert r.pnl["insurance_revenue"] < 0.5 * d["act_premiums"] + 1e-6 or d["act_premiums"] == 0
            assert r.movements["investment_components"]["pv"] == pytest.approx(-d["act_investment_component"])


def test_savings_csm_runs_off_slowly(va):
    last = va["closings"][-1]
    for g, r in last.results.items():
        released = -r.movements["csm_release"]["csm"]
        assert 0 < released < 0.1 * (r.closing.csm + released)  # decades of coverage remain


def test_reinsurance_recovers_40pct_of_initial_losses(vt, re):
    first = re["closings"][0]["results"]["RE-2023"]
    vt23 = vt["closings"][0].results["VT-2023-ONE"]
    under = vt23.pnl["ise_onerous_losses_and_reversals"] - vt23.pnl["revenue_loss_component_exclusion"]
    assert first.pnl["loss_recovery_income"] == pytest.approx(A.REINSURANCE["quota_share"] * under)
    assert first.closing.loss_component == pytest.approx(A.REINSURANCE["quota_share"] * vt23.closing.loss_component, rel=1e-6)


def test_loss_recovery_component_follows_the_underlying(vt, re):
    for o_vt, o_re in zip(vt["closings"], re["closings"]):
        for t, r in o_re["results"].items():
            lc = sum(res.closing.loss_component for g, res in o_vt.results.items() if reinsurance.treaty_of(g) == t)
            assert r.closing.loss_component == pytest.approx(A.REINSURANCE["quota_share"] * lc, rel=1e-6, abs=1e-6)


def test_reversal_in_2025_reduces_recoveries(re):
    r = re["closings"][-1]["results"]["RE-2023"]
    assert r.pnl["loss_recovery_income"] < 0  # 66(c)(ii): reversal of underlying losses


def test_reinsurance_is_a_net_cost_and_an_asset(re):
    for o in re["closings"]:
        for t, r in o["results"].items():
            assert r.closing.lrc > 0  # cedant's asset
            p = reinsurance.presentation(r)
            assert p["allocation_of_premiums_paid"] < 0 and p["amounts_recovered"] >= 0
