"""Checks on the synthetic portfolio: reproducibility, internal consistency and calibration."""

import numpy as np
import pandas as pd
import pytest

from ifrs17 import assumptions as A
from ifrs17.mortality import cso1980, monthly_rate
from ifrs17.simulate import add_calendar_months, simulate_all


@pytest.fixture(scope="module")
def sim():
    return simulate_all()


def test_same_seed_same_world(sim):
    again = simulate_all()
    for name in ("vt_policies", "auto_claims", "va_account_values", "expenses"):
        pd.testing.assert_frame_equal(sim[name], again[name])
    other = simulate_all(seed=7)
    assert not sim["vt_policies"]["sum_insured"].equals(other["vt_policies"]["sum_insured"])


def test_term_life_portfolio_matches_design(sim):
    p = sim["vt_policies"]
    for year, n in A.TERM_LIFE.new_policies.items():
        assert (p["issue_year"] == year).sum() == n
    assert not ((p["issue_year"] == 2025) & (p["channel"] == "promo")).any()
    assert (p["issue_age"] + p["term"] <= A.TERM_LIFE.max_expiry_age).all()
    assert p["sum_insured"].between(*A.TERM_LIFE.sum_insured_bounds).all()
    assert (p["sum_insured"] % 5_000 == 0).all()
    promo = p["channel"] == "promo"
    np.testing.assert_allclose(p.loc[promo, "annual_premium"], (0.8 * p.loc[promo, "tariff_premium"]).round(2))
    assert (p.loc[~promo, "annual_premium"] == p.loc[~promo, "tariff_premium"]).all()


def _expected_deaths(policies: pd.DataFrame) -> float:
    """Sum of true monthly death probabilities over the months each policy was exposed."""
    table = cso1980()
    total = 0.0
    start = (policies["issue_year"] - A.START_YEAR) * 12 + policies["issue_month"] - 1
    exit_ = pd.to_datetime(policies["exit_date"])
    last = np.where(exit_.isna(), 35, (exit_.dt.year - A.START_YEAR) * 12 + exit_.dt.month - 1)
    rule = (policies["issue_age"] >= 50) & (policies["sum_insured"] >= 250_000)
    for t in range(36):
        live = (start <= t) & (last >= t)
        dur = t - start[live]
        age = (policies.loc[live, "issue_age"] + dur // 12).clip(upper=99).to_numpy()
        q = np.where(policies.loc[live, "sex"] == "M", table["M"].to_numpy()[age], table["F"].to_numpy()[age])
        f = A.MORTALITY_TRUE[A.START_YEAR + t // 12]
        q = q * np.where(rule[live], f["older_high_si"], f["default"])
        total += monthly_rate(q).sum()
    return total


@pytest.mark.parametrize("product", ["vt", "va"])
def test_deaths_agree_with_true_mortality(sim, product):
    pol = sim[f"{product}_policies"]
    actual = (pol["exit_reason"] == "death").sum()
    expected = _expected_deaths(pol)
    assert abs(actual - expected) < 3.5 * np.sqrt(expected) + 1  # Poisson band


def test_term_life_lapses_at_anniversaries(sim):
    p = sim["vt_policies"]
    lapsed = p[p["exit_reason"] == "lapse"]
    months = (pd.to_datetime(lapsed["exit_date"]).dt.month - lapsed["issue_month"]) % 12
    assert (months == 0).all()
    assert (pd.to_datetime(lapsed["exit_date"]).dt.day == 1).all()
    first_year = (lapsed["issue_year"] == 2023) & (pd.to_datetime(lapsed["exit_date"]).dt.year == 2024)
    rate = first_year.sum() / (p["issue_year"] == 2023).sum()
    assert rate == pytest.approx(A.TERM_LIFE.lapse[0], abs=0.02)


def test_term_life_premiums_follow_the_policy_record(sim):
    tx = sim["vt_transactions"]
    prem = tx[tx["type"] == "premium"].groupby("policy_id")["amount"].agg(["size", "first"])
    pol = sim["vt_policies"].set_index("policy_id")
    np.testing.assert_allclose(prem["first"], pol.loc[prem.index, "annual_premium"])
    comm = tx[tx["type"] == "commission"].groupby("policy_id")["amount"].sum()
    np.testing.assert_allclose(comm.loc[prem.index], prem["first"] * (0.5 + 0.05 * (prem["size"] - 1)), atol=0.02)


def test_savings_accounts(sim):
    av = sim["va_account_values"]
    assert (av["account_value"] >= 0).all()
    assert (av["surrender_value"] <= av["account_value"]).all()
    led = sim["va_account_ledger"]
    assert (led["coi"] > 0).all() and (led["interest"] > 0).all()
    tx = sim["va_transactions"]
    surr = tx[tx["type"] == "surrender"]
    assert len(surr) == (sim["va_policies"]["exit_reason"] == "surrender").sum()


@pytest.mark.parametrize("line", ["auto", "inc", "trc"])
def test_claims_and_payments_are_consistent(sim, line):
    cl, pay = sim[f"{line}_claims"], sim[f"{line}_payments"]
    total = pay.groupby("claim_id")["amount"].sum()
    np.testing.assert_allclose(total.loc[cl["claim_id"]].to_numpy(), cl["ultimate"].to_numpy(), atol=0.02)
    first_pay = pay.groupby("claim_id")["payment_date"].min()
    cl = cl.set_index("claim_id")
    assert (cl["occurrence_date"] <= cl["report_date"]).all()
    assert (cl.loc[first_pay.index, "report_date"] <= first_pay).all()
    assert (cl["occurrence_date"] <= np.datetime64("2025-12-31")).all()
    pol = sim[f"{line}_policies"].set_index("policy_id")
    cover = pol.loc[cl["policy_id"]]
    assert (cl["occurrence_date"].to_numpy() >= cover["issue_date"].to_numpy()).all()


@pytest.mark.parametrize("line", ["auto", "inc", "trc"])
def test_premium_schedule_adds_up(sim, line):
    prem = sim[f"{line}_premiums"].groupby("policy_id")["premium"].sum()
    pol = sim[f"{line}_policies"].set_index("policy_id")["premium"]
    np.testing.assert_allclose(prem.loc[pol.index], pol, atol=0.03)


def test_case_reserves_only_for_open_reported_claims(sim):
    cr, cl = sim["auto_case_reserves"], sim["auto_claims"].set_index("claim_id")
    assert (cl.loc[cr["claim_id"], "report_date"].to_numpy() <= cr["closing"].to_numpy()).all()
    assert (cr["case_reserve"] > 0).all()


def test_motor_frequency_and_flotas_shock(sim):
    cl, pol = sim["auto_claims"], sim["auto_policies"]
    acc23 = cl[(cl["occurrence_date"].astype("datetime64[ns]").dt.year == 2023)]
    # 2023 policies issue uniformly through the year, so 2023 exposure is about half a year each
    for seg, s in A.MOTOR.items():
        n_pd = ((acc23["segment"] == seg) & (acc23["coverage"] == "PD")).sum()
        expected = s.frequency_pd * s.policies[2023] * 0.5
        assert abs(n_pd - expected) < 4 * np.sqrt(expected)
    sev = cl[cl["coverage"] == "PD"].assign(y=lambda d: d["occurrence_date"].astype("datetime64[ns]").dt.year)
    ratio = sev.groupby(["segment", "y"])["ultimate"].mean().unstack("segment")
    rel = ratio["flotas"] / ratio["particulares"]
    assert rel[2023] < 1.15 and rel[2025] > 1.15  # spare-parts inflation hits fleets from 2024


def test_add_calendar_months_clips_to_month_end():
    d = np.array(["2023-01-31", "2023-11-30"], dtype="datetime64[D]")
    out = add_calendar_months(d, [1, 3])
    assert out.tolist() == [np.datetime64("2023-02-28"), np.datetime64("2024-02-29")]
