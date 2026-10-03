"""Savings life (VA): universal life type B under the GMM (memo sections 5, 7 and 12).

The account value earns a declared rate. The entity specified its commitment at
inception (B98-B100): each year it credits the one-year market rate (HQM) less a fixed
1.25% spread, never below the 2.5% guarantee. Consequences:

* projected crediting follows the forward rates of the curve used for discounting, so
  that cash flows and discount rates move together (B74(b));
* differences between actual and expected crediting, and changes in the forward rates,
  are financial effects (B97(a)) and go to insurance finance income or expenses, while
  changes in mortality, lapses and expenses adjust the CSM (B96);
* the investment component is the surrender value (account value less surrender
  charge): it is excluded from revenue and expenses (par. 85, B123) and differences
  between expected and actual amounts in the period adjust the CSM (B96(c));
* coverage units add the expected cost-of-insurance charge (insurance coverage) and 1%
  a year of the account value (investment-return service, B119B), memo section 12;
* the risk adjustment is the cost of capital, with capital running off with the sum
  insured in force.

All finance income or expenses of this portfolio are in profit or loss (par. 88(a)).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import assumptions as A
from .data import life_inforce, load
from .discounting import curve_for, weighted_curve
from .experience import INITIAL_CLOSING, mortality_factors
from .gmm import GroupState, PeriodInputs, run_period
from .mortality import BASE_YEAR, MAX_AGE, cso1980, monthly_rate
from .risk_adjustment import COST_OF_CAPITAL, LIFE_SHOCKS, aggregate

P = A.SAVINGS_LIFE
PRODUCT, PORTFOLIO = "va", "VA"
PREVIOUS = {"2023-12-31": INITIAL_CLOSING, "2024-12-31": "2023-12-31", "2025-12-31": "2024-12-31"}
INVESTMENT_RETURN_SERVICE_FEE = 0.01  # weight of the account value in the coverage units (B119B)
IBNR_SHARE_OF_LAST_MONTH = 0.5


@dataclass(frozen=True)
class SavingsBasis:
    mortality_factor: float = A.MORTALITY_FACTOR
    improvement: float = A.MORTALITY_IMPROVEMENT
    lapse: tuple = P.lapse
    mortality_multiplier: float = 1.0
    lapse_multiplier: float = 1.0
    expense_multiplier: float = 1.0
    expense_inflation: float = A.EXPENSE_INFLATION
    claim_payment_lag: float = 1.0

    def stressed(self, **kw) -> "SavingsBasis":
        return replace(self, **kw)


BEST_ESTIMATE = SavingsBasis()
ITEMS_OUT = ("death_insurance", "commissions", "premium_tax", "maintenance", "underwriting")


@dataclass
class SavingsProjection:
    policy_id: np.ndarray
    inforce: np.ndarray
    account: np.ndarray  # expected account value per policy in force at the start of each month
    premiums: np.ndarray
    commissions: np.ndarray
    premium_tax: np.ndarray
    maintenance: np.ndarray
    underwriting: np.ndarray
    death_insurance: np.ndarray  # sum insured + surrender charge + claim cost on death
    investment_component: np.ndarray  # surrender values, account value less charge on death, maturities
    coverage_units: np.ndarray
    claim_lag: float
    first_month_is_issue: np.ndarray = field(default=None)

    @property
    def months(self) -> int:
        return self.inforce.shape[1]


def surrender_charge(policy_year) -> np.ndarray:
    sc = np.asarray(P.surrender_charge)
    y = np.asarray(policy_year)
    return np.where(y <= len(sc), sc[np.clip(y - 1, 0, len(sc) - 1)], 0.0)


def crediting_rates(start_cal_index: np.ndarray, months: int, year_rates) -> np.ndarray:
    """Annual crediting rate for each policy and projection month, by calendar year."""
    cal_year = BASE_YEAR + (np.asarray(start_cal_index)[:, None] + np.arange(months)[None, :]) // 12
    years = np.unique(cal_year)
    lookup = np.array([year_rates(int(y)) for y in years])
    return lookup[np.searchsorted(years, cal_year)]


def year_rate_function(curve, anchor_year: int, valuation_year: int, actual_years: dict | None = None):
    """Declared rates for past years; for later years the one-year forward of ``curve`` less the
    spread, floored at the guarantee (the commitment of B98). ``anchor_year`` is the calendar
    year at which ``curve`` starts."""
    actual = dict(P.declared_rate if actual_years is None else actual_years)

    def rate(year):
        if year <= valuation_year and year in actual:
            return actual[year]
        j = max(year - anchor_year, 0)
        fwd = curve.discount(float(j))[0] / curve.discount(float(j + 1))[0] - 1.0 if j > 0 else curve.spot(1.0)[0]
        return max(P.guaranteed_rate, float(fwd) - P.crediting_spread)

    return rate


def project_savings(policies: pd.DataFrame, basis: SavingsBasis, elapsed, account_start, crediting: np.ndarray) -> SavingsProjection:
    """Monthly projection of type-B universal life from ``elapsed`` months after issue.

    ``account_start`` is the account value at the projection start (0 at issue) and
    ``crediting`` the annual rate per policy and month.
    """
    n = len(policies)
    e = np.broadcast_to(np.asarray(elapsed, int), (n,))
    term_m = (P.maturity_age - policies["issue_age"].to_numpy(int)) * 12
    remaining = term_m - e
    T = int(remaining.max()) if n else 0
    table = cso1980()
    male = policies["sex"].to_numpy() == "M"
    si = policies["sum_insured"].to_numpy(float)
    prem = policies["annual_premium"].to_numpy(float)
    factor = policies["mortality_factor"].to_numpy(float) if "mortality_factor" in policies else np.full(n, basis.mortality_factor)
    cal0 = ((policies["issue_year"].to_numpy(int) - BASE_YEAR) * 12 + policies["issue_month"].to_numpy(int) - 1 + e)
    lapse_tab = np.asarray(basis.lapse)
    out = {k: np.zeros((n, T)) for k in ("inforce", "account", "premiums", "commissions", "premium_tax", "maintenance",
                                          "underwriting", "death_insurance", "investment_component", "coverage_units")}
    inforce = np.ones(n)
    av = np.asarray(account_start, float).copy()
    for k in range(T):
        m = e + k
        active = k < remaining
        if not active.any():
            break
        age = np.minimum(policies["issue_age"].to_numpy(int) + m // 12, MAX_AGE)
        cal = cal0 + k
        q_cso = np.where(male, table["M"].to_numpy()[age], table["F"].to_numpy()[age])
        q_be = np.clip(q_cso * factor * basis.mortality_multiplier * (1 - basis.improvement) ** np.maximum(cal // 12, 0), 0, 1)
        qm = np.where(active, monthly_rate(q_be), 0.0)
        pol_year = m // 12 + 1
        lm = np.where(active, monthly_rate(np.clip(lapse_tab[np.minimum(pol_year - 1, len(lapse_tab) - 1)] * basis.lapse_multiplier, 0, 1)), 0.0)
        infl = (1 + basis.expense_inflation) ** (np.maximum(cal, 0) / 12.0) * basis.expense_multiplier
        due = active & (m % 12 == 0)
        p_in = np.where(due, prem, 0.0)
        out["inforce"][:, k] = inforce * active
        out["account"][:, k] = av * active
        out["premiums"][:, k] = inforce * p_in
        out["commissions"][:, k] = inforce * p_in * np.where(m == 0, P.first_year_commission, P.renewal_commission)
        out["premium_tax"][:, k] = inforce * p_in * A.PREMIUM_TAX
        out["maintenance"][:, k] = inforce * active * P.maintenance_cost / 12 * infl
        out["underwriting"][:, k] = inforce * (m == 0) * P.underwriting_cost * infl
        coi = si * q_cso * P.coi_table_factor / 12
        av = av + p_in * (1 - P.premium_load) - np.where(active, coi + P.admin_fee_monthly, 0.0)
        av = np.where(active, av * (1 + crediting[:, k]) ** (1 / 12), av)
        av = np.maximum(av, 0.0)
        out["coverage_units"][:, k] = inforce * active * (coi + INVESTMENT_RETURN_SERVICE_FEE / 12 * av)
        sc = surrender_charge(pol_year) * av
        deaths = inforce * qm
        lapses = (inforce - deaths) * lm
        maturing = active & (k == remaining - 1)
        out["death_insurance"][:, k] = deaths * (si + sc + P.claim_cost * infl)
        out["investment_component"][:, k] = deaths * (av - sc) + lapses * (av - sc) + np.where(maturing, (inforce - deaths - lapses) * av, 0.0)
        inforce = np.where(maturing, 0.0, inforce - deaths - lapses)
    return SavingsProjection(policy_id=policies["policy_id"].to_numpy(), claim_lag=basis.claim_payment_lag,
                             first_month_is_issue=(e == 0), **out)


def _discount(proj: SavingsProjection, curve, s, anchor_offset) -> dict:
    """Locked (forward-consistent from each issue) or current discount matrices by timing type."""
    k = np.arange(proj.months, dtype=float)
    lim = curve.maturities[-1]
    s = np.asarray(s, float)[:, None]
    a = np.asarray(anchor_offset, float)[:, None]
    base = curve.discount(np.minimum((s + a)[:, 0] / 12.0, lim))[:, None]

    def d(off):
        t = np.minimum((s + k[None, :] + off) / 12.0, lim)
        return curve.discount(t.ravel()).reshape(t.shape) / base

    return {"start": d(0.0), "end": d(1.0), "death": d(0.5 + proj.claim_lag)}


def pv(proj: SavingsProjection, D: dict, mask=None, after=None) -> dict:
    mask = np.ones(proj.inforce.shape[0], bool) if mask is None else mask
    keep = np.ones_like(proj.inforce[mask], bool) if after is None else (np.arange(proj.months)[None, :] >= np.asarray(after)[mask][:, None])
    timing = {"premiums": "start", "commissions": "start", "premium_tax": "start", "maintenance": "start",
              "underwriting": "start", "death_insurance": "death", "investment_component": "end"}
    out = {i: float((getattr(proj, i)[mask] * keep * D[t][mask]).sum()) for i, t in timing.items()}
    out["outflows"] = sum(out[i] for i in ITEMS_OUT) + out["investment_component"]
    out["net"] = out["outflows"] - out["premiums"]
    return out


def risk_capital(policies, basis, elapsed, av, crediting, D, mask_groups: dict) -> dict:
    """Undiversified shocks (mortality, lapse, expense) by group and the run-off factor."""
    base = project_savings(policies, basis, elapsed, av, crediting)

    def net(b):
        pr = project_savings(policies, b, elapsed, av, crediting)
        return {g: pv(pr, D, m)["net"] for g, m in mask_groups.items()}

    b0 = {g: pv(base, D, m)["net"] for g, m in mask_groups.items()}
    mort = net(basis.stressed(mortality_multiplier=basis.mortality_multiplier * (1 + LIFE_SHOCKS["mortality"])))
    lup = net(basis.stressed(lapse_multiplier=basis.lapse_multiplier * (1 + LIFE_SHOCKS["lapse"])))
    ldn = net(basis.stressed(lapse_multiplier=basis.lapse_multiplier * (1 - LIFE_SHOCKS["lapse"])))
    exp_ = net(basis.stressed(expense_multiplier=basis.expense_multiplier * (1 + LIFE_SHOCKS["expense"]),
                              expense_inflation=basis.expense_inflation + LIFE_SHOCKS["inflation"]))
    out = {}
    k = np.arange(base.months)
    for g, m in mask_groups.items():
        shocks = np.array([max(mort[g] - b0[g], 0.0), max(lup[g] - b0[g], ldn[g] - b0[g], 0.0), max(exp_[g] - b0[g], 0.0)])
        # capital runs off with the death benefit at risk in force (sum insured), not with the
        # coverage units, which grow with the account value
        at_risk = (base.inforce[m] * policies["sum_insured"].to_numpy(float)[m][:, None]).sum(axis=0)
        runoff = float((at_risk / at_risk[0]) @ D["end"][m].mean(axis=0) / 12.0) if at_risk.size and at_risk[0] > 0 else 0.0
        out[g] = {"shocks": shocks, "runoff": runoff, "ra": COST_OF_CAPITAL * float(aggregate(shocks)[0]) * runoff,
                  "net": b0[g], "projection": base}
    return out


# --------------------------------------------------------------------------
# classification at recognition (par. 16-19)
# --------------------------------------------------------------------------
def with_factors(policies: pd.DataFrame, factors: dict) -> pd.DataFrame:
    out = policies.copy()
    out["mortality_factor"] = factors["default"]
    return out


def classify() -> pd.DataFrame:
    pol = load("va_policies")
    rows = []
    for year in sorted(pol["issue_year"].unique()):
        factors = mortality_factors("vt", PREVIOUS[f"{year}-12-31"])  # one mortality study for both life products
        cohort = with_factors(pol[pol["issue_year"] == year], factors)
        for month in range(1, 13):
            sub = cohort[cohort["issue_month"] == month].reset_index(drop=True)
            if sub.empty:
                continue
            curve = curve_for(f"{year}-{month:02d}", PORTFOLIO)
            rate = year_rate_function(curve, year, year)  # the cohort year's declared rate is known
            start_cal = (year - BASE_YEAR) * 12 + month - 1
            cr = crediting_rates(np.full(len(sub), start_cal), int(((P.maturity_age - sub["issue_age"]) * 12).max()), rate)
            proj = project_savings(sub, BEST_ESTIMATE, 0, np.zeros(len(sub)), cr)
            D = _discount(proj, curve, np.zeros(len(sub)), np.zeros(len(sub)))
            masks = {cell: sub.index.isin(idx) for cell, idx in sub.groupby("cell").groups.items()}
            rc = risk_capital(sub, BEST_ESTIMATE, 0, np.zeros(len(sub)), cr, D, masks)
            stressed = []
            for lm in (0.7, 1.3):
                b = BEST_ESTIMATE.stressed(mortality_multiplier=1.15, expense_multiplier=1.10, lapse_multiplier=lm)
                pr = project_savings(sub, b, 0, np.zeros(len(sub)), cr)
                stressed.append({c: pv(pr, D, m)["net"] for c, m in masks.items()})
            for cell, m in masks.items():
                fcf = rc[cell]["net"] + rc[cell]["ra"]
                fcf_s = max(s[cell] for s in stressed) + rc[cell]["ra"]
                label = "ONE" if fcf > 0 else ("RES" if fcf_s > 0 else "SIG")
                rows.append({"cohort": year, "issue_month": month, "cell": cell, "policies": int(m.sum()),
                             "annual_premium": sub.loc[m, "annual_premium"].sum(), "fcf": fcf, "fcf_stressed": fcf_s,
                             "ra": rc[cell]["ra"], "class": label, "group": f"VA-{year}-{label}"})
    return pd.DataFrame(rows)


def assign_groups(classification: pd.DataFrame) -> pd.DataFrame:
    pol = load("va_policies")
    key = classification.set_index(["cohort", "issue_month", "cell"])["group"]
    pol = pol.copy()
    pol["group"] = key.reindex(pd.MultiIndex.from_arrays([pol["issue_year"], pol["issue_month"], pol["cell"]])).to_numpy()
    return pol


# --------------------------------------------------------------------------
# measurement at each closing
# --------------------------------------------------------------------------
@dataclass
class ClosingOutput:
    closing: str
    results: dict
    lic: pd.DataFrame
    details: pd.DataFrame


def _locked_curves(policies):
    out = {}
    for g, sub in policies.groupby("group"):
        w = sub.groupby("issue_month")["annual_premium"].sum()
        y = int(sub["issue_year"].iloc[0])
        out[g] = (weighted_curve([f"{y}-{m:02d}" for m in w.index], w.to_numpy(), PORTFOLIO), y)
    return out


def value_closing(closing: str, policies: pd.DataFrame, states: dict, lic_open: dict) -> ClosingOutput:
    t1 = pd.Timestamp(closing)
    prev = PREVIOUS[closing]
    t0 = pd.Timestamp("2022-12-31") if prev == INITIAL_CLOSING else pd.Timestamp(prev)
    f0, f1 = mortality_factors("vt", prev), mortality_factors("vt", closing)
    current = curve_for(t1.strftime("%Y-%m"), PORTFOLIO)
    locked = _locked_curves(policies[policies["issue_date"] <= t1])
    gid = policies.set_index("policy_id")["group"]
    pol = load("va_policies")
    pol = pol[pol["issue_date"] <= t1].copy()
    pol["group"] = pol["policy_id"].map(gid)
    late = pol["exit_date"] > t1
    pol.loc[late, ["exit_date", "exit_reason"]] = [pd.NaT, "inforce"]
    av_tab = load("va_account_values")

    def av_at(ids, date):
        a = av_tab[av_tab["closing"] == pd.Timestamp(date)].set_index("policy_id")["account_value"]
        return a.reindex(ids).fillna(0.0).to_numpy()

    open_ids = set(life_inforce(PRODUCT, t0)["policy_id"]) if prev != INITIAL_CLOSING else set()
    close_ids = set(life_inforce(PRODUCT, t1)["policy_id"])
    opening = pol[pol["policy_id"].isin(open_ids)].reset_index(drop=True)
    nb = pol[pol["issue_date"] > t0].reset_index(drop=True)
    clo = pol[pol["policy_id"].isin(close_ids)].reset_index(drop=True)
    e0 = ((t0.year - opening["issue_date"].dt.year) * 12 + (t0.month - opening["issue_date"].dt.month) + 1).to_numpy()
    e1 = ((t1.year - clo["issue_date"].dt.year) * 12 + (t1.month - clo["issue_date"].dt.month) + 1).to_numpy()
    p_nb = (13 - nb["issue_month"].to_numpy()) if len(nb) else np.zeros(0, int)
    cal_open = (t0.year - BASE_YEAR) * 12 + t0.month  # first month after t0
    cal_close = (t1.year - BASE_YEAR) * 12 + t1.month

    tx = load("va_transactions")
    tx = tx[(tx["date"] > t0) & (tx["date"] <= t1)]
    claims = load("va_claims").merge(pol[["policy_id", "group"]], on="policy_id", how="left")
    claims["ic"] = claims["account_value"] - claims["surrender_charge"]
    claims["insurance"] = claims["sum_insured"] + claims["surrender_charge"] + claims["claim_expense"]
    reported = claims[claims["report_date"] <= t1]
    inc_now = reported[reported["occurrence_date"] > t0]
    paid = claims[(claims["payment_date"] > t0) & (claims["payment_date"] <= t1)]
    outstanding = reported[reported["payment_date"] > t1]
    expenses = load("expenses")
    ex = expenses[(expenses["portfolio"] == PORTFOLIO) & (pd.PeriodIndex(expenses["month"], freq="M").start_time > t0)
                  & (pd.PeriodIndex(expenses["month"], freq="M").start_time <= t1)]
    uw_total = ex.loc[ex["type"] == "acquisition_underwriting", "amount"].sum()
    maint_total = ex.loc[ex["type"] == "maintenance", "amount"].sum()

    # closing measurement on current rates, shared by all groups (one projection, masks by group)
    groups_here = sorted(pol["group"].dropna().unique())
    if len(clo):
        T_all = int(((P.maturity_age - clo["issue_age"]) * 12 - e1).max())
        av1_all = av_at(clo["policy_id"], t1)
        cr_C_all = crediting_rates(np.full(len(clo), cal_close), T_all, year_rate_function(current, t1.year + 1, t1.year))
        clo1, clo0 = with_factors(clo, f1), with_factors(clo, f0)
        prC_all = project_savings(clo1, BEST_ESTIMATE, e1, av1_all, cr_C_all)
        DC_all = _discount(prC_all, current, np.zeros(len(clo)), np.zeros(len(clo)))
        masks = {g: (clo["group"] == g).to_numpy() for g in groups_here if (clo["group"] == g).any()}
        ra_new_all = risk_capital(clo1, BEST_ESTIMATE, e1, av1_all, cr_C_all, DC_all, masks)
        ra_old_all = risk_capital(clo0, BEST_ESTIMATE, e1, av1_all, cr_C_all, DC_all, masks)

    results, lic_rows, details = {}, [], []
    for g in groups_here:
        L, anchor = locked[g]
        st = states.get(g, GroupState())
        mo = (opening["group"] == g).to_numpy()
        mn = (nb["group"] == g).to_numpy() if len(nb) else np.zeros(0, bool)
        mc = (clo["group"] == g).to_numpy()
        x = PeriodInputs()
        extra = {"cu_by_year": [], "net_cf_by_year": []}
        acc = {"prem": 0.0, "out": 0.0, "ic": 0.0, "acq": 0.0, "close": 0.0, "last": 0.0}

        def expected(sub, s, p, av0, start_cal):
            """Expected path with the period's actual crediting and locked forwards afterwards (B97(a))."""
            rate = year_rate_function(L, anchor, t1.year)
            cr = crediting_rates(start_cal, int(((P.maturity_age - sub["issue_age"]) * 12 - s).max()), rate)
            pr = project_savings(with_factors(sub, f0), BEST_ESTIMATE, s, av0, cr)
            k = np.arange(pr.months)
            inside = k[None, :] < np.asarray(p)[:, None]
            first = pr.first_month_is_issue[:, None] & (k[None, :] == 0)
            acc["prem"] += (pr.premiums * inside).sum()
            acq = pr.underwriting + pr.commissions * first
            acc["acq"] += (acq * inside).sum()
            acc["out"] += ((pr.death_insurance + pr.maintenance + pr.premium_tax + pr.commissions * ~first) * inside).sum()
            acc["ic"] += (pr.investment_component * inside).sum()
            acc["last"] += ((pr.death_insurance + pr.investment_component * 0) * (k[None, :] == np.asarray(p)[:, None] - 1)).sum()
            D = _discount(pr, L, s, p)
            acc["close"] += pv(pr, D, after=np.asarray(p))["net"]
            return pr

        if mo.any():
            sub = opening[mo].reset_index(drop=True)
            expected(sub, e0[mo], np.full(mo.sum(), 12), av_at(sub["policy_id"], t0), np.full(mo.sum(), cal_open))
        if mn.any():
            sub = nb[mn].reset_index(drop=True)
            start_cal = ((sub["issue_year"] - BASE_YEAR) * 12 + sub["issue_month"] - 1).to_numpy()
            prn = expected(sub, np.zeros(len(sub), int), p_nb[mn], np.zeros(len(sub)), start_cal)
            D0 = _discount(prn, L, np.zeros(len(sub)), np.zeros(len(sub)))
            v = pv(prn, D0)
            x.nb_pv_inflows, x.nb_pv_outflows = v["premiums"], v["outflows"]
            rate = year_rate_function(L, anchor, int(sub["issue_year"].iloc[0]))
            cr = crediting_rates(start_cal, prn.months, rate)
            x.nb_ra = risk_capital(with_factors(sub, f0), BEST_ESTIMATE, 0, np.zeros(len(sub)), cr, D0, {g: np.ones(len(sub), bool)})[g]["ra"]
            first_comm = tx[(tx["type"] == "commission") & tx["policy_id"].isin(sub["policy_id"])]
            first_comm = first_comm[first_comm["date"].values == sub.set_index("policy_id").loc[first_comm["policy_id"], "issue_date"].values]
            x.nb_acquisition = first_comm["amount"].sum() + uw_total * len(sub) / max(len(nb), 1)
            w = sub["annual_premium"].to_numpy()
            x.nb_csm_accretion = float(np.average([1.0 / L.discount(pm / 12.0)[0] - 1.0 for pm in p_nb[mn]], weights=w))
        x.exp_premiums, x.exp_outflows, x.exp_investment_component, x.exp_acquisition = acc["prem"], acc["out"], acc["ic"], acc["acq"]
        x.expected_close_pv_locked = acc["close"]
        if mo.any():
            age = np.average(e0[mo], weights=opening.loc[mo, "annual_premium"]) / 12.0
            x.csm_accretion_rate = float(L.discount(age)[0] / L.discount(age + 1.0)[0] - 1.0)

        gp = pol[pol["group"] == g]["policy_id"]
        gtx = tx[tx["policy_id"].isin(gp)]
        issue = pol.set_index("policy_id")["issue_date"]
        is_first = gtx["date"].values == issue.reindex(gtx["policy_id"]).values
        x.act_premiums = gtx.loc[gtx["type"] == "premium", "amount"].sum()
        x.act_acquisition = x.nb_acquisition
        g_inc = inc_now[inc_now["group"] == g]
        ibnr = IBNR_SHARE_OF_LAST_MONTH * acc["last"]
        months_g = len(gp)  # maintenance shared by policies on the books
        share = months_g / max(len(pol), 1)
        x.act_outflows = (g_inc["insurance"].sum() + ibnr + gtx.loc[(gtx["type"] == "commission") & ~is_first, "amount"].sum()
                          + gtx.loc[gtx["type"] == "premium_tax", "amount"].sum() + maint_total * share)
        x.act_investment_component = g_inc["ic"].sum() + gtx.loc[gtx["type"] == "surrender", "amount"].sum()

        if mc.any():
            sub = clo[mc].reset_index(drop=True)
            s1 = e1[mc]
            av1 = av_at(sub["policy_id"], t1)
            T = int(((P.maturity_age - sub["issue_age"]) * 12 - s1).max())
            cr_L = crediting_rates(np.full(len(sub), cal_close), T, year_rate_function(L, anchor, t1.year))
            prL = project_savings(with_factors(sub, f1), BEST_ESTIMATE, s1, av1, cr_L)
            DL = _discount(prL, L, s1, np.zeros(len(sub)))
            vL = pv(prL, DL)
            x.close_pv_locked, x.close_pv_outflows_locked = vL["net"], vL["outflows"]
            x.close_pv_current = pv(prC_all, DC_all, mc)["net"]
            x.close_ra = ra_new_all[g]["ra"]
            x.close_ra_old_basis = ra_old_all[g]["ra"]
            x.cu_future = float(prC_all.coverage_units[mc].sum())
            fut_months = float(prC_all.inforce[mc].sum())
            by_year = lambda a: np.add.reduceat(a, np.arange(0, a.size, 12)) if a.size else np.zeros(0)  # noqa: E731
            extra["cu_by_year"] = by_year(prC_all.coverage_units[mc].sum(axis=0)).tolist()
            net = sum(getattr(prC_all, i)[mc] for i in ITEMS_OUT) + prC_all.investment_component[mc] - prC_all.premiums[mc]
            extra["net_cf_by_year"] = by_year(net.sum(axis=0)).tolist()
        else:
            fut_months = 0.0
        # coverage units provided: cost-of-insurance and the investment-return fee in the period
        led = load("va_account_ledger")
        led = led[(led["month_start"] > t0) & (led["month_start"] <= t1)]
        g_share_av = av_at(gp, t1).sum() / max(av_tab[av_tab["closing"] == t1]["account_value"].sum(), 1.0)
        x.cu_period = float((led["coi"].sum() + INVESTMENT_RETURN_SERVICE_FEE / 12 * led["opening"].sum()) * g_share_av) if len(led) else 0.0
        policy_months = float(gp.size * 12)
        sh = policy_months / (policy_months + fut_months) if policy_months + fut_months else 1.0
        x.acquisition_allocation = (st.acquisition_unallocated + x.nb_acquisition) * sh

        r = run_period(st, x, oci=False)
        results[g] = r
        out_g = outstanding[outstanding["group"] == g][["ic", "insurance"]].sum().sum()
        paid_g = paid[paid["group"] == g][["ic", "insurance"]].sum().sum()
        lic_close = out_g + ibnr
        inc_cur = g_inc[["ic", "insurance"]].sum().sum() + ibnr
        lic_rows.append({"closing": closing, "group": g, "opening": lic_open.get(g, 0.0), "incurred_current": inc_cur,
                         "past_service": lic_close - lic_open.get(g, 0.0) - inc_cur + paid_g, "paid": -paid_g,
                         "closing_pv": lic_close, "closing_ra": COST_OF_CAPITAL / 12 * lic_close, "ibnr": ibnr,
                         "investment_component_incurred": g_inc["ic"].sum()})
        details.append({"closing": closing, "group": g, **x.__dict__, **extra})
    return ClosingOutput(closing, results, pd.DataFrame(lic_rows), pd.DataFrame(details))


def run_all(closings=A.CLOSINGS) -> dict:
    classification = classify()
    policies = assign_groups(classification)
    states, lic, outs = {}, {}, []
    for c in closings:
        o = value_closing(c, policies, states, lic)
        for g, r in o.results.items():
            states[g] = r.closing
        lic = o.lic.set_index("group")["closing_pv"].to_dict()
        outs.append(o)
    return {"classification": classification, "policies": policies, "closings": outs, "states": states}
