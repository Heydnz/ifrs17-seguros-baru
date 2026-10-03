"""Term life (VT): groups, classification at recognition and GMM measurement at each closing.

Phase 2 (aggregation and recognition, par. 14-28)
    Portfolio VT; one cohort per calendar year of issue; each cell (term x issue-age band x
    channel) recognised in a month is classified on its own fulfilment cash flows at that
    date (par. 17):
      ONE  onerous at recognition: fulfilment cash flows are a net outflow (par. 16(a), 47);
      SIG  no significant possibility of becoming onerous: still profitable under the
           combined stress mortality +15%, expenses +10% and lapses -30% or +30% (par. 16(b), 19);
      RES  the rest (par. 16(c)).
    The assumptions are those in force at recognition (the previous closing), the curve is the
    end-of-month curve of the month of issue, and the risk adjustment is the cost of capital.

Phase 3 (GMM, par. 32-52)
    Each closing re-projects every group with the new best estimate and feeds the analysis
    of change in ``gmm.run_period``. Term life uses the OCI option (par. 88(b), B131): the
    finance expense in profit or loss is the accretion at locked-in rates and the effect of
    changes in current rates goes to OCI.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import assumptions as A
from .data import life_inforce, load
from .discounting import curve_for, weighted_curve
from .experience import INITIAL_CLOSING, mortality_factors
from .gmm import GroupState, PeriodInputs, run_period
from .life import BEST_ESTIMATE, TermBasis, project_term, segment_mortality_factor
from .risk_adjustment import COST_OF_CAPITAL, term_life_risk_adjustment

PRODUCT, PORTFOLIO = "vt", "VT"
PREVIOUS = {"2023-12-31": INITIAL_CLOSING, "2024-12-31": "2023-12-31", "2025-12-31": "2024-12-31"}
STRESS = {"mortality_multiplier": 1.15, "expense_multiplier": 1.10, "lapse": (0.7, 1.3)}
OUTFLOW_ITEMS = ("claims", "maintenance", "premium_tax", "commissions", "underwriting")
IBNR_SHARE_OF_LAST_MONTH = 0.5  # report delay study: deaths are reported 0.5 months later on average
RA_LIC_DURATION_YEARS = 1 / 12  # cost of capital held while an incurred claim is settled


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def basis_at(closing) -> tuple[TermBasis, dict]:
    return BEST_ESTIMATE, mortality_factors(PRODUCT, closing)


def with_factors(policies: pd.DataFrame, factors: dict) -> pd.DataFrame:
    out = policies.copy()
    out["mortality_factor"] = segment_mortality_factor(out, factors)
    return out


def month_index(dates) -> np.ndarray:
    d = pd.to_datetime(pd.Series(dates))
    return ((d.dt.year - A.START_YEAR) * 12 + d.dt.month - 1).to_numpy()


def _pv_items(proj, factors_main: np.ndarray, factors_claims: np.ndarray, from_month=None) -> dict:
    """PV per policy of each item, with discount matrices (rows: policies) for start-of-month
    items and for death claims. ``from_month`` (per policy) excludes earlier projection months."""
    out = {}
    k = np.arange(proj.months)
    keep = np.ones_like(proj.inforce, bool) if from_month is None else k[None, :] >= np.asarray(from_month)[:, None]
    for item in ("premiums",) + OUTFLOW_ITEMS:
        cf = getattr(proj, item) * keep
        d = factors_claims if item == "claims" else factors_main
        out[item] = (cf * d).sum(axis=1)
    out["outflows"] = sum(out[i] for i in OUTFLOW_ITEMS)
    out["net"] = out["outflows"] - out["premiums"]
    return out


def _current_matrices(proj, curve):
    """Discount from the valuation date on the current curve, for start-of-month items and claims."""
    k = np.arange(proj.months, dtype=float)
    n = proj.inforce.shape[0]
    main = np.broadcast_to(curve.discount(k / 12.0), (n, proj.months))
    claims = np.broadcast_to(curve.discount((k + proj.claim_time_offset) / 12.0), (n, proj.months))
    return main, claims


# --------------------------------------------------------------------------
# Phase 2: classification at recognition
# --------------------------------------------------------------------------
def classify(policies: pd.DataFrame | None = None) -> pd.DataFrame:
    pol_all = load("vt_policies") if policies is None else policies
    rows = []
    for year in sorted(pol_all["issue_year"].unique()):
        basis, factors = basis_at(PREVIOUS[f"{year}-12-31"])
        cohort = with_factors(pol_all[pol_all["issue_year"] == year], factors)
        for month in range(1, 13):
            sub = cohort[cohort["issue_month"] == month].reset_index(drop=True)
            if sub.empty:
                continue
            curve = curve_for(f"{year}-{month:02d}", PORTFOLIO)
            base = project_term(sub, basis).present_values(curve.discount)["net_outflow"].to_numpy()
            ra = term_life_risk_adjustment(sub, basis, curve.discount)
            stressed = []
            for lm in STRESS["lapse"]:
                b = basis.stressed(mortality_multiplier=STRESS["mortality_multiplier"],
                                   expense_multiplier=STRESS["expense_multiplier"], lapse_multiplier=lm)
                stressed.append(project_term(sub, b).present_values(curve.discount)["net_outflow"].to_numpy())
            for cell, idx in sub.groupby("cell").groups.items():
                mask = sub.index.isin(idx)
                ra_cell = ra.for_group(mask)
                fcf = base[mask].sum() + ra_cell
                fcf_stress = max(s[mask].sum() for s in stressed) + ra_cell
                premiums = (sub.loc[mask, "annual_premium"]).sum()
                label = "ONE" if fcf > 0 else ("RES" if fcf_stress > 0 else "SIG")
                rows.append({"cohort": year, "issue_month": month, "cell": cell, "policies": int(mask.sum()),
                             "annual_premium": premiums, "fcf": fcf, "fcf_stressed": fcf_stress,
                             "ra": ra_cell, "class": label, "group": f"VT-{year}-{label}"})
    return pd.DataFrame(rows)


def assign_groups(classification: pd.DataFrame, policies: pd.DataFrame | None = None) -> pd.DataFrame:
    pol = load("vt_policies") if policies is None else policies
    key = classification.set_index(["cohort", "issue_month", "cell"])["group"]
    idx = pd.MultiIndex.from_arrays([pol["issue_year"], pol["issue_month"], pol["cell"]])
    out = pol.copy()
    out["group"] = key.reindex(idx).to_numpy()
    return out


# --------------------------------------------------------------------------
# Phase 3: measurement at each closing
# --------------------------------------------------------------------------
@dataclass
class ClosingOutput:
    closing: str
    results: dict  # group -> gmm.PeriodResult
    lic: pd.DataFrame
    details: pd.DataFrame


def _locked_curves(policies: pd.DataFrame) -> dict:
    curves = {}
    for g, sub in policies.groupby("group"):
        w = sub.groupby("issue_month")["annual_premium"].sum()
        year = int(sub["issue_year"].iloc[0])
        curves[g] = weighted_curve([f"{year}-{m:02d}" for m in w.index], w.to_numpy(), PORTFOLIO)
    return curves


def _actuals(policies: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
    """Premiums, commissions and taxes paid in (t0, t1] per policy, as known at t1."""
    tx = load("vt_transactions")
    tx = tx[(tx["date"] > t0) & (tx["date"] <= t1) & tx["policy_id"].isin(policies["policy_id"])]
    issue = policies.set_index("policy_id")["issue_date"]
    first = tx["date"].eq(tx["policy_id"].map(issue))
    piv = pd.DataFrame({
        "premiums": tx[tx["type"] == "premium"].groupby("policy_id")["amount"].sum(),
        "acq_commission": tx[(tx["type"] == "commission") & first].groupby("policy_id")["amount"].sum(),
        "renewal_commission": tx[(tx["type"] == "commission") & ~first].groupby("policy_id")["amount"].sum(),
        "premium_tax": tx[tx["type"] == "premium_tax"].groupby("policy_id")["amount"].sum(),
    })
    return piv.reindex(policies["policy_id"]).fillna(0.0)


def _months_in_force(policies: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp) -> np.ndarray:
    """Whole months each policy was in force within (t0, t1], as known at t1."""
    start = np.maximum(month_index(policies["issue_date"]), (t0.year - A.START_YEAR) * 12 + t0.month)
    end_cap = (t1.year - A.START_YEAR) * 12 + t1.month - 1
    exit_ = policies["exit_date"].where(policies["exit_date"] <= t1)
    exit_idx = month_index(exit_.fillna(pd.Timestamp("2100-01-01")))
    lapse = policies["exit_reason"].isin(["lapse", "surrender"]).to_numpy() & exit_.notna().to_numpy()
    end = np.where(lapse, exit_idx - 1, np.minimum(exit_idx, end_cap))
    end = np.minimum(end, end_cap)
    return np.maximum(end - start + 1, 0)


def value_closing(closing: str, policies: pd.DataFrame, states: dict, lic_open: dict) -> ClosingOutput:
    t1 = pd.Timestamp(closing)
    t0 = pd.Timestamp(PREVIOUS[closing]) if PREVIOUS[closing] != INITIAL_CLOSING else pd.Timestamp("2022-12-31")
    b0, f0 = basis_at(PREVIOUS[closing])
    b1, f1 = basis_at(closing)
    current = curve_for(t1.strftime("%Y-%m"), PORTFOLIO)
    locked = _locked_curves(policies[policies["issue_date"] <= t1])

    gid = policies.set_index("policy_id")["group"]
    known = load("vt_policies").set_index("policy_id")
    pol_t1 = known.loc[known["issue_date"] <= t1].reset_index()
    pol_t1["group"] = pol_t1["policy_id"].map(gid)
    # exits known at t1 (exits after t1 are not known yet)
    late = pol_t1["exit_date"] > t1
    pol_t1.loc[late, ["exit_date", "exit_reason"]] = [pd.NaT, "inforce"]

    open_ids = set(life_inforce(PRODUCT, t0)["policy_id"]) if PREVIOUS[closing] != INITIAL_CLOSING else set()
    close_ids = set(life_inforce(PRODUCT, t1)["policy_id"])
    opening = pol_t1[pol_t1["policy_id"].isin(open_ids)].reset_index(drop=True)
    nb = pol_t1[(pol_t1["issue_date"] > t0)].reset_index(drop=True)
    closing_pol = pol_t1[pol_t1["policy_id"].isin(close_ids)].reset_index(drop=True)

    e0 = (t0.year - opening["issue_date"].dt.year) * 12 + (t0.month - opening["issue_date"].dt.month) + 1
    e1 = (t1.year - closing_pol["issue_date"].dt.year) * 12 + (t1.month - closing_pol["issue_date"].dt.month) + 1
    p_nb = 13 - nb["issue_month"].to_numpy() if len(nb) else np.zeros(0, int)

    proj_open = project_term(with_factors(opening, f0), b0, elapsed=e0.to_numpy()) if len(opening) else None
    proj_nb = project_term(with_factors(nb, f0), b0, elapsed=0) if len(nb) else None
    cl_old = with_factors(closing_pol, f0)
    cl_new = with_factors(closing_pol, f1)
    proj_close_old = project_term(cl_old, b0, elapsed=e1.to_numpy())
    proj_close_new = project_term(cl_new, b1, elapsed=e1.to_numpy())
    ra_new = term_life_risk_adjustment(cl_new, b1, current.discount, elapsed=e1.to_numpy())
    ra_old = term_life_risk_adjustment(cl_old, b0, current.discount, elapsed=e1.to_numpy())
    pv_close_cur = _pv_items(proj_close_new, *_current_matrices(proj_close_new, current))

    actual_all = _actuals(pol_t1, t0, t1)
    months_if = pd.Series(_months_in_force(pol_t1, t0, t1), index=pol_t1["policy_id"])
    expenses = load("expenses")
    exp_period = expenses[(expenses["portfolio"] == PORTFOLIO)
                          & (pd.PeriodIndex(expenses["month"], freq="M").start_time > t0)
                          & (pd.PeriodIndex(expenses["month"], freq="M").start_time <= t1)]
    underwriting_total = exp_period.loc[exp_period["type"] == "acquisition_underwriting", "amount"].sum()
    maintenance_total = exp_period.loc[exp_period["type"] == "maintenance", "amount"].sum()

    claims = load("vt_claims").merge(pol_t1[["policy_id", "group"]], on="policy_id", how="left")
    claims["cost"] = claims["amount"] + claims["claim_expense"]
    reported = claims[claims["report_date"] <= t1]
    incurred_now = reported[(reported["occurrence_date"] > t0)]
    paid = claims[(claims["payment_date"] > t0) & (claims["payment_date"] <= t1)]
    outstanding = reported[reported["payment_date"] > t1]

    results, lic_rows, detail_rows = {}, [], []
    for g in sorted(pol_t1["group"].dropna().unique()):
        L = locked[g]
        st = states.get(g, GroupState())
        m_open = (opening["group"] == g).to_numpy()
        m_nb = (nb["group"] == g).to_numpy() if len(nb) else np.zeros(0, bool)
        m_cl = (closing_pol["group"] == g).to_numpy()

        x = PeriodInputs()
        exp_close = 0.0
        ceded = dict.fromkeys(["exp_prem", "exp_ben", "exp_ben_last", "expected_close_prem_L", "expected_close_ben_L",
                               "nb_prem_L", "nb_ben_L", "close_prem_L", "close_ben_L", "close_prem_C", "close_ben_C",
                               "act_prem", "act_ben", "lic_ben"], 0.0)
        exp = {"premiums": 0.0, "outflows": 0.0, "acq": 0.0, "claims_last_month": 0.0}

        def expected_part(proj, mask, s, p):
            """Expected cash flows inside the period and PV at t1 (locked) of those after it."""
            nonlocal exp_close
            k = np.arange(proj.months)
            inside = k[None, :] < np.asarray(p)[:, None]
            sel = lambda a: a[mask]  # noqa: E731
            for item, key in (("premiums", "premiums"),):
                exp[key] += (sel(getattr(proj, item)) * inside[mask]).sum()
            first = (k[None, :] == 0) & (np.asarray(s)[:, None] == 0)
            acq = sel(proj.underwriting) + sel(proj.commissions) * first[mask]
            exp["acq"] += (acq * inside[mask]).sum()
            out = sum(sel(getattr(proj, i)) for i in ("claims", "maintenance", "premium_tax")) + sel(proj.commissions) * ~first[mask]
            exp["outflows"] += (out * inside[mask]).sum()
            last = k[None, :] == (np.asarray(p)[:, None] - 1)
            exp["claims_last_month"] += (sel(proj.claims) * last[mask]).sum()
            sm = np.asarray(s, float)[mask]
            pm = np.asarray(p, float)[mask]
            main, clm = _discount_matrices_sub(proj, mask, L, sm, pm)
            after = ~inside[mask]
            net = (sum(sel(getattr(proj, i)) for i in OUTFLOW_ITEMS) - sel(proj.premiums)) * after
            claims_part = sel(proj.claims) * after
            exp_close += ((net - claims_part) * main).sum() + (claims_part * clm).sum()
            ceded["exp_prem"] += (sel(proj.premiums) * inside[mask]).sum()
            ceded["exp_ben"] += (sel(proj.benefits) * inside[mask]).sum()
            ceded["exp_ben_last"] += (sel(proj.benefits) * last[mask]).sum()
            ceded["expected_close_prem_L"] += (sel(proj.premiums) * after * main).sum()
            ceded["expected_close_ben_L"] += (sel(proj.benefits) * after * clm).sum()

        if m_open.any():
            expected_part(proj_open, m_open, e0.to_numpy(), np.full(len(opening), 12))
        if m_nb.any():
            expected_part(proj_nb, m_nb, np.zeros(len(nb)), p_nb)
            nb_sub = nb[m_nb]
            main0, clm0 = _discount_matrices_sub(proj_nb, m_nb, L, np.zeros(m_nb.sum()), np.zeros(m_nb.sum()))
            pv_nb = {}
            for item in ("premiums",) + OUTFLOW_ITEMS:
                d = clm0 if item == "claims" else main0
                pv_nb[item] = (getattr(proj_nb, item)[m_nb] * d).sum()
            ceded["nb_prem_L"] = pv_nb["premiums"]
            ceded["nb_ben_L"] = (proj_nb.benefits[m_nb] * clm0).sum()
            ra_nb = term_life_risk_adjustment(with_factors(nb_sub, f0), b0, L.discount)
            x.nb_pv_inflows = pv_nb["premiums"]
            x.nb_pv_outflows = sum(pv_nb[i] for i in OUTFLOW_ITEMS)
            x.nb_ra = ra_nb.for_group()
            act_nb = actual_all.loc[nb_sub["policy_id"]]
            n_nb_total = len(nb)
            x.nb_acquisition = act_nb["acq_commission"].sum() + underwriting_total * m_nb.sum() / max(n_nb_total, 1)
            # CSM interest from each recognition month to the period end, weighted by premium
            w = nb_sub["annual_premium"].to_numpy()
            rates = np.array([1.0 / L.discount(pm / 12.0)[0] - 1.0 for pm in p_nb[m_nb]])
            x.nb_csm_accretion = float(np.average(rates, weights=w))
        x.exp_premiums, x.exp_outflows, x.exp_acquisition = exp["premiums"], exp["outflows"], exp["acq"]
        x.expected_close_pv_locked = exp_close
        # opening CSM accretes at the locked forward rate for the group's average age (B72(b))
        if m_open.any():
            age = np.average(e0.to_numpy()[m_open], weights=opening.loc[m_open, "sum_insured"]) / 12.0
            x.csm_accretion_rate = float(L.discount(age)[0] / L.discount(age + 1.0)[0] - 1.0)

        # actuals of the period
        gpol = pol_t1["group"] == g
        act = actual_all.loc[pol_t1.loc[gpol, "policy_id"]]
        x.act_premiums = act["premiums"].sum()
        x.act_acquisition = x.nb_acquisition
        if_months = months_if.loc[pol_t1.loc[gpol, "policy_id"]]
        maint_share = if_months.sum() / max(months_if.sum(), 1)
        ibnr = IBNR_SHARE_OF_LAST_MONTH * exp["claims_last_month"]
        inc_g = incurred_now[incurred_now["group"] == g]["cost"].sum()
        x.act_outflows = inc_g + ibnr + act["renewal_commission"].sum() + act["premium_tax"].sum() + maintenance_total * maint_share

        # closing measurement (new basis) and the old basis for the analysis of change
        if m_cl.any():
            s1 = e1.to_numpy()[m_cl].astype(float)
            mainL, clmL = _discount_matrices_sub(proj_close_new, m_cl, L, s1, np.zeros(m_cl.sum()))
            mainL_o, clmL_o = _discount_matrices_sub(proj_close_old, m_cl, L, s1, np.zeros(m_cl.sum()))
            def pv_locked(proj, main, clm):  # noqa: E306
                tot, out = 0.0, 0.0
                for item in ("premiums",) + OUTFLOW_ITEMS:
                    d = clm if item == "claims" else main
                    v = (getattr(proj, item)[m_cl] * d).sum()
                    if item == "premiums":
                        tot -= v
                    else:
                        tot += v
                        out += v
                return tot, out
            x.close_pv_locked, x.close_pv_outflows_locked = pv_locked(proj_close_new, mainL, clmL)
            mainC, clmC = _current_matrices(proj_close_new, current)
            ceded["close_prem_L"] = (proj_close_new.premiums[m_cl] * mainL).sum()
            ceded["close_ben_L"] = (proj_close_new.benefits[m_cl] * clmL).sum()
            ceded["close_prem_C"] = (proj_close_new.premiums[m_cl] * mainC[m_cl]).sum()
            ceded["close_ben_C"] = (proj_close_new.benefits[m_cl] * clmC[m_cl]).sum()
            x.close_pv_current = pv_close_cur["net"][m_cl].sum()
            x.close_ra = ra_new.for_group(m_cl)
            x.close_ra_old_basis = ra_old.for_group(m_cl)
            x.cu_future = proj_close_new.coverage_units[m_cl].sum()
            future_policy_months = proj_close_new.inforce[m_cl].sum()
            by_year = lambda a: np.add.reduceat(a, np.arange(0, a.size, 12)) if a.size else np.zeros(0)  # noqa: E731
            ceded["cu_by_year"] = by_year(proj_close_new.coverage_units[m_cl].sum(axis=0)).tolist()
            net_cf = sum(getattr(proj_close_new, i)[m_cl] for i in OUTFLOW_ITEMS) - proj_close_new.premiums[m_cl]
            ceded["net_cf_by_year"] = by_year(net_cf.sum(axis=0)).tolist()
        else:
            future_policy_months = 0.0
        x.cu_period = float((if_months * pol_t1.loc[gpol].set_index("policy_id")["sum_insured"]).sum())
        share = if_months.sum() / (if_months.sum() + future_policy_months) if (if_months.sum() + future_policy_months) else 1.0
        x.acquisition_allocation = (st.acquisition_unallocated + x.nb_acquisition) * share

        r = run_period(st, x, oci=True)
        results[g] = r

        # liability for incurred claims (par. 40(b), B... ); undiscounted: paid within weeks
        lic_open_g = lic_open.get(g, 0.0)
        out_g = outstanding[outstanding["group"] == g]["cost"].sum()
        lic_close = out_g + ibnr
        paid_g = paid[paid["group"] == g]["cost"].sum()
        incurred_current = inc_g + ibnr
        past = lic_close - lic_open_g - incurred_current + paid_g
        ra_lic = COST_OF_CAPITAL * RA_LIC_DURATION_YEARS * lic_close
        lic_rows.append({"closing": closing, "group": g, "opening": lic_open_g, "incurred_current": incurred_current,
                         "past_service": past, "paid": -paid_g, "closing_pv": lic_close, "closing_ra": ra_lic,
                         "ibnr": ibnr})
        ceded.setdefault("cu_by_year", [])
        ceded.setdefault("net_cf_by_year", [])
        ceded["act_prem"] = x.act_premiums
        ceded["act_ben"] = incurred_now[incurred_now["group"] == g]["amount"].sum() + IBNR_SHARE_OF_LAST_MONTH * ceded["exp_ben_last"]
        ceded["lic_ben"] = outstanding[outstanding["group"] == g]["amount"].sum() + IBNR_SHARE_OF_LAST_MONTH * ceded["exp_ben_last"]
        ceded["paid_ben"] = paid[paid["group"] == g]["amount"].sum()
        patterns = {"cu_by_year": ceded.pop("cu_by_year"), "net_cf_by_year": ceded.pop("net_cf_by_year")}
        detail_rows.append({"closing": closing, "group": g, **{k: v for k, v in x.__dict__.items()}, **patterns,
                            **{f"ceded_{k}": v for k, v in ceded.items()},
                            "mortality_default": f1["default"], "mortality_older_high_si": f1["older_high_si"]})
    return ClosingOutput(closing, results, pd.DataFrame(lic_rows), pd.DataFrame(detail_rows))


def _discount_matrices_sub(proj, mask, curve, s, p):
    """Locked discount to the date p months after the projection start, rows of ``mask`` only."""
    k = np.arange(proj.months, dtype=float)
    s = np.asarray(s, float)
    p = np.asarray(p, float)
    lim = curve.maturities[-1]
    t_main = np.minimum((s[:, None] + k[None, :]) / 12.0, lim)
    t_clm = np.minimum((s[:, None] + k[None, :] + proj.claim_time_offset) / 12.0, lim)
    anchor = curve.discount(np.minimum((s + p) / 12.0, lim))[:, None]
    main = curve.discount(t_main.ravel()).reshape(t_main.shape) / anchor
    clm = curve.discount(t_clm.ravel()).reshape(t_clm.shape) / anchor
    return main, clm


def run_all(closings=A.CLOSINGS) -> dict:
    """Classification, groups and the three closings of term life."""
    classification = classify()
    policies = assign_groups(classification)
    states, lic_balance, outputs = {}, {}, []
    for c in closings:
        out = value_closing(c, policies, states, lic_balance)
        for g, r in out.results.items():
            states[g] = r.closing
        lic_balance = out.lic.set_index("group")["closing_pv"].to_dict()
        outputs.append(out)
    return {"classification": classification, "policies": policies, "closings": outputs, "states": states}
