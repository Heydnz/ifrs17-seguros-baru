"""Term life end to end: classification at recognition and the three closings (memo sections 6, 11-12)."""

import numpy as np
import pandas as pd
import pytest

from ifrs17.term_life import run_all


@pytest.fixture(scope="module")
def vt():
    return run_all()


def _closing(vt, date):
    return next(o for o in vt["closings"] if o.closing == date)


def test_classification_follows_the_design(vt):
    c = vt["classification"]
    promo = c[c["cell"].str.endswith("promo")]
    share_one = promo.groupby("cohort").apply(lambda d: d.loc[d["class"] == "ONE", "policies"].sum() / d["policies"].sum())
    assert (share_one > 0.9).all()  # the 20% discount makes the promotion onerous (par. 16(a))
    assert not ((c["cohort"] == 2025) & (c["class"] == "ONE")).any()  # no promotion, repriced tariff
    older = c[c["cell"].str.contains("50-60") & ~c["cell"].str.endswith("promo")]
    assert (older["class"] != "ONE").all() and (older["class"] == "RES").mean() > 0.6
    young = c[c["cell"].str.contains("25-39") & ~c["cell"].str.endswith("promo")]
    assert (young["class"] == "SIG").all()
    assert set(vt["policies"]["group"].dropna().unique()) == set(c["group"])
    assert vt["policies"]["group"].notna().all()


def test_no_gain_at_recognition_and_losses_for_onerous_groups(vt):
    for out in vt["closings"]:
        for g, r in out.results.items():
            nb = r.movements["new_contracts"]
            if g.endswith("ONE") and nb["pv"]:
                assert nb["csm"] == 0 and nb["loss"] > 0
            else:
                assert nb["loss"] == 0 and nb["csm"] == pytest.approx(-(nb["pv"] + nb["ra"]))


def test_signs_and_balances(vt):
    for out in vt["closings"]:
        for g, r in out.results.items():
            s = r.closing
            assert s.csm >= 0 and s.loss_component >= 0
            assert not (s.csm > 0 and s.loss_component > 0)
            assert s.loss_component <= s.pv_outflows_locked + s.ra + 1e-6  # par. 50(a) ratio stays below 1


def test_scripted_story_2024_onerous_2025_reversal(vt):
    r24 = _closing(vt, "2024-12-31").results["VT-2023-RES"]
    assert r24.pnl["ise_onerous_losses_and_reversals"] > 0 and r24.closing.loss_component > 0 and r24.closing.csm == 0
    r25 = _closing(vt, "2025-12-31").results["VT-2023-RES"]
    assert r25.closing.loss_component == 0 and r25.closing.csm > 0  # par. 50(b): reversal first, then CSM


def test_accretion_is_interest_at_locked_rates(vt):
    for out in vt["closings"][1:]:
        for g, r in out.results.items():
            if r.opening.pv_outflows_locked == 0:  # recognised in this period
                continue
            x = r.pnl["ifie_pnl"] - r.movements["finance"]["csm"]
            # interest on the opening PV and on the cash flows of the year, at 4%-6% locked rates
            assert abs(x) < 0.08 * (r.opening.pv_outflows_locked + r.opening.ra)


def test_oci_option_puts_rate_effects_in_oci(vt):
    for out in vt["closings"]:
        for r in out.results.values():
            total_finance = r.movements["finance"]["pv"] + r.movements["finance"]["csm"]
            assert r.pnl["ifie_pnl"] + r.pnl["ifie_oci"] == pytest.approx(total_finance)


def test_lic_rolls_forward(vt):
    lic = pd.concat([o.lic for o in vt["closings"]])
    roll = lic["opening"] + lic["incurred_current"] + lic["past_service"] + lic["paid"]
    np.testing.assert_allclose(roll, lic["closing_pv"], atol=1e-6)
    assert (lic["closing_pv"] >= 0).all()
