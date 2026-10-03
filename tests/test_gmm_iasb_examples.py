"""The GMM engine reproduces the IASB Illustrative Examples on IFRS 17.

Inputs come from the examples (paragraph references below); the expected results are the
figures the IASB publishes, which are rounded to whole currency units, so the tests allow
for that rounding. Source: IFRS 17 Illustrative Examples (IASB), Examples 1, 2, 7, 8 and 12C.
"""

import pytest

from ifrs17.gmm import GroupState, PeriodInputs, run_period

I = 0.05


def pv(flows, i=I):
    return sum(cf / (1 + i) ** (t + 1) for t, cf in enumerate(flows))


def three_years(outflows, ra_by_year, premium=900.0, ra0=120.0, changes=None, cu_period=(100, 100, 100)):
    """Run a 3-year group: premium at the start, claims at each year end (Examples 1-2, 8)."""
    changes = changes or {}
    flows = list(outflows)
    state, results = GroupState(), []
    for year in range(3):
        remaining_before = flows[year:]
        if year == 0:
            nb = dict(nb_pv_inflows=premium, nb_pv_outflows=pv(flows), nb_ra=ra0, nb_csm_accretion=I,
                      exp_premiums=premium, act_premiums=premium)
            opening_pv = 0.0
        else:
            nb, opening_pv = {}, state.pv_locked
        expected_close = (opening_pv + (pv(flows) - premium if year == 0 else 0.0) + (premium if year == 0 else 0.0)) * (1 + I) - flows[year]
        actual = changes.get(("actual", year), flows[year])
        if ("estimate", year) in changes:
            flows = flows[: year + 1] + changes[("estimate", year)]
        close_pv = pv(flows[year + 1:])
        ra_old = ra_by_year["old"][year]
        x = PeriodInputs(**nb, exp_outflows=remaining_before[0], act_outflows=actual,
                         expected_close_pv_locked=expected_close, csm_accretion_rate=I if year else 0.0,
                         close_pv_locked=close_pv, close_pv_current=close_pv, close_pv_outflows_locked=close_pv,
                         close_ra=ra_by_year["new"][year], close_ra_old_basis=ra_old,
                         cu_period=cu_period[year], cu_future=100 * (2 - year))
        r = run_period(state, x)
        results.append(r)
        state = r.closing
    return results


def profit(r):
    return r.pnl["insurance_service_result"] - r.pnl["ifie_pnl"]


def test_example_1_initial_recognition():
    """IE4-IE11: CSM 235 for the profitable group, loss 309 for the onerous one."""
    a = run_period(GroupState(), PeriodInputs(nb_pv_inflows=900, nb_pv_outflows=pv([200] * 3), nb_ra=120))
    assert a.movements["new_contracts"]["csm"] == pytest.approx(235, abs=0.5)
    b = run_period(GroupState(), PeriodInputs(nb_pv_inflows=900, nb_pv_outflows=pv([400] * 3), nb_ra=120))
    assert b.movements["new_contracts"]["loss"] == pytest.approx(309, abs=0.5)
    assert b.movements["new_contracts"]["csm"] == 0


def test_example_2a_favourable_changes():
    """IE12-IE23: year 2 claims 150 instead of 200 and year 3 estimate 140 with RA 30."""
    ra = {"old": [80, 40, 0], "new": [80, 30, 0]}
    r = three_years([200, 200, 200], ra, changes={("actual", 1): 150, ("estimate", 1): [140]})
    y1, y2, y3 = r
    assert y1.closing.csm == pytest.approx(165, abs=1)
    assert y1.closing.lrc == pytest.approx(617, abs=1)
    assert y1.movements["finance"]["pv"] == pytest.approx(27, abs=1)
    assert y1.movements["csm_release"]["csm"] == pytest.approx(-82, abs=1)
    assert profit(y1) == pytest.approx(83, abs=1)
    assert y2.movements["future_service_csm"]["pv"] == pytest.approx(-58, abs=1)
    assert y2.movements["future_service_csm"]["csm"] == pytest.approx(68, abs=1)
    assert y2.movements["experience"]["pv"] == pytest.approx(-50, abs=1e-9)
    assert y2.movements["csm_release"]["csm"] == pytest.approx(-121, abs=1)
    assert y2.closing.lrc == pytest.approx(283, abs=1)
    assert profit(y2) == pytest.approx(184, abs=1)
    assert y3.movements["csm_release"]["csm"] == pytest.approx(-126, abs=1)
    assert profit(y3) == pytest.approx(143, abs=1)
    assert y3.closing.lrc == pytest.approx(0, abs=1e-9)
    assert sum(profit(y) for y in r) == pytest.approx(410, abs=1e-6)  # 900 - 200 - 150 - 140


def test_example_2b_group_becomes_onerous():
    """IE24-IE28: year 2 claims 400 and year 3 estimate 450 with RA 88; loss 113 when the CSM runs out."""
    ra = {"old": [80, 40, 0], "new": [80, 88, 0]}
    y1, y2, y3 = three_years([200, 200, 200], ra, changes={("actual", 1): 400, ("estimate", 1): [450]})
    assert y2.movements["future_service_csm"]["csm"] == pytest.approx(-173, abs=1)
    assert y2.pnl["ise_onerous_losses_and_reversals"] == pytest.approx(113, abs=1)
    assert y2.closing.csm == 0
    assert y2.closing.lrc == pytest.approx(517, abs=1)
    assert profit(y2) == pytest.approx(-300, abs=1)
    assert profit(y3) == pytest.approx(67, abs=1)
    assert y3.closing.loss_component == pytest.approx(0, abs=1e-9)  # par. 52
    assert sum(profit(y) for y in (y1, y2, y3)) == pytest.approx(-150, abs=1e-6)


def test_example_7_acquisition_cash_flows():
    """IE72-IE80 (no discounting): revenue 300 a year includes 30 of acquisition cash flows recovered."""
    state = GroupState()
    revenue, expenses = [], []
    for year in range(3):
        nb = dict(nb_pv_inflows=900, nb_pv_outflows=600 + 90, nb_ra=15, nb_acquisition=90,
                  exp_premiums=900, act_premiums=900, exp_acquisition=90, act_acquisition=90) if year == 0 else {}
        expected_close = 200 * (2 - year)
        x = PeriodInputs(**nb, exp_outflows=200, act_outflows=200, expected_close_pv_locked=expected_close,
                         close_pv_locked=expected_close, close_pv_current=expected_close,
                         close_pv_outflows_locked=expected_close, close_ra=5 * (2 - year),
                         cu_period=1, cu_future=2 - year)
        r = run_period(state, x)
        if year == 0:
            assert r.movements["new_contracts"]["csm"] == pytest.approx(195)
        revenue.append(r.pnl["insurance_revenue"])
        expenses.append(r.pnl["insurance_service_expenses"])
        state = r.closing
    assert revenue == pytest.approx([300, 300, 300])
    assert expenses == pytest.approx([230, 230, 230])


def test_example_8_reversal_of_losses():
    """IE81-IE98: premium 800, outflows 400 a year, RA 240; year 3 estimate falls to 100."""
    ra = {"old": [160, 80, 0], "new": [160, 80, 0]}
    # IE8 recognises the CSM created by the year-end reversal only in Year 3 (IE94-IE97); the
    # example is reproduced by attributing no coverage units of Year 2 to that CSM. Seguros Baru
    # applies par. 44(e) and B119 as in Example 2A (see test_csm_after_reversal_is_shared).
    y1, y2, y3 = three_years([400, 400, 400], ra, premium=800, ra0=240, changes={("estimate", 1): [100]},
                             cu_period=(100, 0, 100))
    assert y1.movements["new_contracts"]["loss"] == pytest.approx(529, abs=1)
    assert y1.pnl["lc_ratio"] == pytest.approx(0.398, abs=0.0005)
    assert y1.closing.loss_component == pytest.approx(359, abs=1.5)
    assert y1.pnl["insurance_revenue"] == pytest.approx(289, abs=1)
    # incurred claims 400 less the 191 allocated to the loss component; the 529 loss is shown apart
    assert y1.pnl["ise_incurred_claims_expenses"] + y1.pnl["revenue_loss_component_exclusion"] == pytest.approx(209, abs=1)
    assert y1.pnl["insurance_service_expenses"] == pytest.approx(209 + 529, abs=1.5)
    assert y2.pnl["insurance_revenue"] == pytest.approx(289, abs=1)
    assert y2.closing.loss_component == 0
    assert y2.closing.csm == pytest.approx(103, abs=1.5)
    assert y3.pnl["insurance_revenue"] == pytest.approx(287, abs=1.5)


def test_example_12c_loss_recovery_component():
    """IE138A-IE138O (no discounting): 30% of claims ceded for 315; recoveries expected 270;
    the onerous underlying group lost 90, so the loss-recovery component starts at 27 (B119D).

    The reinsurance held is run from the reinsurer's side (premiums in, recoveries out), so
    the carrying amount is the cedant's asset and the CSM is the cedant's net cost (with sign).
    """
    x = PeriodInputs(nb_pv_inflows=315, nb_pv_outflows=270, exp_premiums=315, act_premiums=315,
                     exp_outflows=90, act_outflows=90, expected_close_pv_locked=180, close_pv_locked=180,
                     close_pv_current=180, close_pv_outflows_locked=180, cu_period=1, cu_future=2,
                     loss_recovery_income=27, loss_recovery_reversal=9)
    r = run_period(GroupState(), x, reinsurance=True)
    assert r.movements["new_contracts"]["csm"] == pytest.approx(45)
    assert r.movements["csm_release"]["csm"] == pytest.approx(-24)  # 72 / 3
    assert r.closing.csm == pytest.approx(48)
    assert r.closing.loss_component == pytest.approx(18)
    assert r.closing.lrc == pytest.approx(228)  # the cedant's asset at the end of year 1


def test_csm_after_reversal_is_shared_with_the_current_period():
    """Default policy (par. 44(e), B119): the CSM at the period end, after all adjustments, is
    allocated to the units of the current and future periods, so half is recognised in Year 2."""
    ra = {"old": [160, 80, 0], "new": [160, 80, 0]}
    y1, y2, y3 = three_years([400, 400, 400], ra, premium=800, ra0=240, changes={("estimate", 1): [100]})
    pre_release = y2.closing.csm - y2.movements["csm_release"]["csm"]
    assert pre_release == pytest.approx(285.71 - 183.54, abs=0.01)  # PV decrease less remaining loss component
    assert y2.movements["csm_release"]["csm"] == pytest.approx(-pre_release / 2)
    total = sum(profit(y) for y in (y1, y2, y3))
    assert total == pytest.approx(800 - 400 - 400 - 100, abs=1e-6)
