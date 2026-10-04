"""Audited-entity simulator for the term-life review case (Seguros Barú, S.A., fictional).

This script plays the role of the *audited entity*. It writes the files the entity
hands to the reviewer for the 31-Dec-2025 closing:

    data/audit_case/census.csv               policy census, cohorts 2023-2025
    data/audit_case/claims_register.csv      claims reported up to 31-Dec-2025 (paid / pending)
    data/audit_case/claims_after_close.csv   claims reported 1-Jan to 28-Feb-2026 (subsequent events)
    data/audit_case/assumptions.json         the entity's best-estimate assumptions and policies
    data/audit_case/management_package.json  the figures management reports

The management package is built with management's own code (below) and contains
DELIBERATE, SEEDED ERRORS for the exercise. The review notebook
(notebooks/08_revision_independiente_vida_temporal.ipynb) never imports this module:
it only reads the files above and recomputes everything independently.

All data are synthetic (fixed seed). Public inputs: 1980 CSO tables (SOA) and the
HQM policy discount curves already in data/. No client data or assumptions are used.

Run:  python audit_case/entity_package.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "audit_case"

SEED = 2025              # census
EXPERIENCE_SEED = 19     # deaths, lapses and claim dates
COHORTS = (2023, 2024, 2025)
N_PER_COHORT = 25_000
VALUATION_DATE = pd.Timestamp("2025-12-31")
REPORT_DATE = pd.Timestamp("2026-02-28")          # date of the auditor's report
LISTING_CUTOFF = pd.Timestamp("2025-12-19")       # seeded error: pending-claims listing cut early
MAX_TERM = 20

# --------------------------------------------------------------------------
# Assumptions document (what the entity says it does)
# --------------------------------------------------------------------------
CHANNELS = {  # share of sales, first-year commission, renewal commission, tariff discount
    "agentes": (0.55, 0.50, 0.05, 0.00),
    "bancaseguros": (0.30, 0.30, 0.10, 0.00),
    "promo": (0.15, 0.15, 0.05, 0.20),
}
ASSUMPTIONS = {
    "entity": "Seguros Barú, S.A. (ficticia)",
    "valuation_date": "2025-12-31",
    "mortality": {
        "table": "1980 CSO ANB, SOA tables 42 (male) and 36 (female)",
        "best_estimate_factor_by_attained_age": {"25-39": 0.70, "40-49": 0.75, "50+": 0.95},
        "annual_improvement": 0.01,
        "improvement_base_year": 2025,
    },
    "lapse_by_policy_year": [0.08, 0.06, 0.04],
    "expenses": {
        "underwriting_cost_per_new_policy": 150.0,
        "maintenance_per_policy_year": 60.0,
        "claim_handling_per_claim": 200.0,
        "inflation": 0.025,
    },
    "commissions": {c: {"first_year": v[1], "renewal": v[2]} for c, v in CHANNELS.items()},
    "timing": "annual steps; premiums, commissions and expenses at the start of the year; "
              "deaths and claim handling at the end of the year",
    "discount_curve": "HQM policy curve at the month before issue (locked-in), "
                      "data/processed/discount_curves_monthly_2024-12.csv, column 'high'",
    "risk_adjustment_policy": {
        "technique": "cost of capital",
        "coc_rate": 0.06,
        "risks": ["mortality +15%", "lapse +/-50% (worst)", "expenses +10% and inflation +1 pp"],
        "correlation": {"mortality-lapse": 0.0, "mortality-expense": 0.25, "lapse-expense": 0.5},
        "capital_run_off": "expected sum insured in force",
    },
    "grouping_policy": "annual cohorts; profitability assessed by sets of contracts = sales channel (par. 17)",
    "onerous_stress": "mortality +15%, lapse +/-30% (adverse), expenses +10% (par. 16(b), 19)",
    "csm_policy": "accretion at locked-in rates (B72(b)); release with coverage units = "
                  "expected sum insured in force, undiscounted (B119)",
    "lic_policy": "case reserves for reported claims; IBNR by actuarial methods; "
                  "claim handling costs (B65(f)); risk adjustment (par. 37)",
    "tariff_basis": {"table": "1980 CSO 100%", "interest": 0.04, "lapses": "none",
                     "admin_per_year": 60.0, "loading": {"<50": 0.10, "50+": 0.03}},
}


def load_cso() -> pd.DataFrame:
    cso = pd.read_csv(ROOT / "data/raw/mortality/cso1980_anb.csv", comment="#")
    return cso.set_index("age").rename(columns={"qx_male": "M", "qx_female": "F"})


def be_factor(age):
    age = np.asarray(age)
    return np.where(age < 40, 0.70, np.where(age < 50, 0.75, 0.95))


def lapse_rate(policy_year):
    rates = np.array(ASSUMPTIONS["lapse_by_policy_year"])
    return rates[np.minimum(np.asarray(policy_year), len(rates) - 1)]


def annual_dfs(curve_month: str, years: int = MAX_TERM + 1) -> np.ndarray:
    df = pd.read_csv(ROOT / f"data/processed/discount_curves_monthly_{curve_month}.csv",
                     header=[0, 1], index_col=0)
    m = df[("high", "discount_factor")].astype(float)
    return np.concatenate([[1.0], m.loc[[12 * k for k in range(1, years + 1)]].to_numpy()])


# --------------------------------------------------------------------------
# Census and experience
# --------------------------------------------------------------------------

def tariff_premium(cso, sex, age, term, si, c1, cr, disc):
    """Level annual premium on the tariff basis (CSO 100%, 4%, no lapses)."""
    v = 1 / 1.04
    out = np.empty(len(age))
    for i in range(len(age)):
        q = cso[sex[i]].to_numpy()[age[i]: age[i] + term[i]]
        kp = np.concatenate([[1.0], np.cumprod(1 - q)[:-1]])
        k = np.arange(term[i])
        a_due = np.sum(kp * v ** k)
        a_ins = np.sum(kp * q * v ** (k + 1))
        cost = si[i] * a_ins + 60.0 * a_due + 150.0
        loading = 0.10 if age[i] < 50 else 0.03
        out[i] = (1 + loading) * cost / (a_due * (1 - cr[i]) - (c1[i] - cr[i])) * (1 - disc[i])
    return np.round(out, 2)


def make_census(rng) -> pd.DataFrame:
    cso = load_cso()
    frames = []
    for cohort in COHORTS:
        n = N_PER_COHORT
        ch = rng.choice(list(CHANNELS), size=n, p=[v[0] for v in CHANNELS.values()])
        sex = rng.choice(["M", "F"], size=n, p=[0.6, 0.4])
        age = rng.triangular(25, 38, 61, size=n)
        age = np.where(ch == "promo", age + rng.normal(5, 3, n), age)
        age = np.clip(np.round(age), 25, 60).astype(int)
        term = rng.choice([10, 15, 20], size=n, p=[0.3, 0.3, 0.4])
        term = np.where(age + term > 75, 10, term)
        si = np.exp(rng.normal(np.log(100_000), 0.6, n))
        si = np.clip(np.round(si / 5_000) * 5_000, 50_000, 500_000)
        c1 = np.array([CHANNELS[c][1] for c in ch])
        cr = np.array([CHANNELS[c][2] for c in ch])
        disc = np.array([CHANNELS[c][3] for c in ch])
        frames.append(pd.DataFrame({
            "policy_id": [f"VT{cohort}-{k:05d}" for k in range(1, n + 1)],
            "cohort": cohort, "issue_date": pd.Timestamp(f"{cohort}-01-01"),
            "channel": ch, "sex": sex, "issue_age": age, "term": term,
            "sum_insured": si, "annual_premium": tariff_premium(cso, sex, age, term, si, c1, cr, disc),
        }))
    return pd.concat(frames, ignore_index=True)


ACTUAL_YEAR_EFFECT = {2023: 1.00, 2024: 1.00, 2025: 1.00}  # real experience vs best estimate


def simulate_experience(census: pd.DataFrame, rng) -> pd.DataFrame:
    cso = load_cso()
    n = len(census)
    alive = np.ones(n, bool)
    census["exit"], census["exit_date"] = "", pd.NaT
    rows = []
    for year in COHORTS:
        dur = year - census["cohort"].to_numpy()
        active = alive & (dur >= 0) & (dur < census["term"].to_numpy())
        att = census["issue_age"].to_numpy() + np.maximum(dur, 0)
        q = np.where(census["sex"].to_numpy() == "M", cso["M"].to_numpy()[att], cso["F"].to_numpy()[att])
        q = q * be_factor(att) * 0.99 ** (year - 2025) * ACTUAL_YEAR_EFFECT[year]
        dies = active & (rng.random(n) < q)
        lapses = active & ~dies & (rng.random(n) < lapse_rate(np.maximum(dur, 0)))
        for i in np.flatnonzero(dies):
            death = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=int(rng.integers(0, 365)))
            report = death + pd.Timedelta(days=int(np.exp(rng.normal(np.log(20), 1.2))))
            contestable = (death - census["issue_date"].iat[i]).days < 730
            settle = 30 + rng.exponential(60) if contestable else 10 + rng.exponential(20)
            rows.append({"policy_id": census["policy_id"].iat[i], "death_date": death,
                         "report_date": report, "payment_date": report + pd.Timedelta(days=int(settle)),
                         "contestable": contestable, "amount": census["sum_insured"].iat[i]})
        census.loc[lapses, "exit"] = "caducada"
        census.loc[lapses, "exit_date"] = pd.Timestamp(f"{year}-12-31")
        alive &= ~(dies | lapses)
    claims = pd.DataFrame(rows).sort_values("death_date", ignore_index=True)
    claims.insert(0, "claim_id", [f"SIN-{k:05d}" for k in range(1, len(claims) + 1)])
    # The administration system only knows a death once it is reported.
    known = claims[claims["report_date"] <= VALUATION_DATE].set_index("policy_id")
    hit = census["policy_id"].isin(known.index)
    census.loc[hit, "exit"] = "fallecida"
    census.loc[hit, "exit_date"] = census.loc[hit, "policy_id"].map(known["death_date"])
    census["exit"] = census["exit"].replace("", "vigente")
    return claims


# --------------------------------------------------------------------------
# Management's closing package (management's code, with seeded errors)
# --------------------------------------------------------------------------

def mgmt_projection(pol, cso, dfs, mort=1.0, lapse=1.0, expense=1.0):
    """Management's projection, policy by policy, from issue (annual steps)."""
    t = np.arange(MAX_TERM)
    age = pol["issue_age"].to_numpy()[:, None] + t
    on = t[None, :] < pol["term"].to_numpy()[:, None]
    male = (pol["sex"].to_numpy() == "M")[:, None]
    q = np.where(male, cso["M"].to_numpy()[age], cso["F"].to_numpy()[age])
    q = np.where(on, np.minimum(q * be_factor(age) * 0.99 ** t * mort, 1.0), 0.0)
    w = np.where(on, np.minimum(lapse_rate(t)[None, :] * lapse, 1.0), 0.0)
    inforce = np.cumprod(np.hstack([np.ones((len(pol), 1)), (1 - q) * (1 - w)]), axis=1)[:, :MAX_TERM] * on
    G = pol["annual_premium"].to_numpy()[:, None]
    S = pol["sum_insured"].to_numpy()[:, None]
    c1 = pol["channel"].map(lambda c: CHANNELS[c][1]).to_numpy()[:, None]
    cr = pol["channel"].map(lambda c: CHANNELS[c][2]).to_numpy()[:, None]
    infl = 1.025 ** t
    start = inforce * (G * np.where(t == 0, c1, cr) + 60.0 * infl * expense) + np.where(t == 0, 150.0, 0.0)
    end = inforce * q * (S + 200.0 * infl * expense)
    pv_in = (inforce * G * dfs[:MAX_TERM]).sum(1)
    pv_out = (start * dfs[:MAX_TERM]).sum(1) + (end * dfs[1:MAX_TERM + 1]).sum(1)
    return pv_in, pv_out, inforce * S


def management_package(census, register):
    cso = load_cso()
    dfs = annual_dfs("2024-12")
    c25 = census[census["cohort"] == 2025].copy()
    pv_in, pv_out, cu = mgmt_projection(c25, cso, dfs)
    c25["pv_in"], c25["pv_out"] = pv_in, pv_out

    # RA. SEEDED ERROR: only the mortality shock is applied (policy says mortality,
    # lapse and expenses). Capital run off with expected sum insured in force.
    s_in, s_out, _ = mgmt_projection(c25, cso, dfs, mort=1.15)
    cap0 = (s_out - s_in) - (pv_out - pv_in)
    runoff = (cu * dfs[1:MAX_TERM + 1]).sum(1) / cu[:, 0]
    c25["ra"] = 0.06 * cap0 * runoff

    # Grouping: sets = sales channel (par. 17) -- management's judgement.
    for name, lapse in (("up", 1.3), ("down", 0.7)):
        s_in, s_out, _ = mgmt_projection(c25, cso, dfs, 1.15, lapse, 1.10)
        c25[f"fcf_stress_{name}"] = s_out - s_in
    sets = c25.groupby("channel")[["pv_in", "pv_out", "fcf_stress_up", "fcf_stress_down", "ra"]].sum()
    net = sets["pv_out"] - sets["pv_in"] + sets["ra"]
    net_st = np.maximum(sets["fcf_stress_up"], sets["fcf_stress_down"]) + sets["ra"]
    sets["group"] = np.where(net > 0, "ONE", np.where(net_st <= 0, "SIG", "RES"))
    c25["group"] = "VT-2025-" + c25["channel"].map(sets["group"])

    g = c25.groupby("group").agg(n_policies=("policy_id", "size"), sum_insured=("sum_insured", "sum"),
                                 pv_inflows=("pv_in", "sum"), pv_outflows=("pv_out", "sum"),
                                 risk_adjustment=("ra", "sum"))
    fcf_ra = g["pv_outflows"] - g["pv_inflows"] + g["risk_adjustment"]
    g["csm"] = np.maximum(0.0, -fcf_ra)
    g["loss_component"] = np.maximum(0.0, fcf_ra)

    # CSM 2025. SEEDED ERRORS: interest at the 4% tariff rate (not locked-in, B72(b))
    # and straight-line release over the SI-weighted average term (not coverage units, B119).
    c25["si_term"] = c25["sum_insured"] * c25["term"]
    avg_term = c25.groupby("group")["si_term"].sum() / c25.groupby("group")["sum_insured"].sum()
    roll = pd.DataFrame({"opening": g["csm"]})
    roll["interest"] = roll["opening"] * 0.04
    roll["release"] = -(roll["opening"] + roll["interest"]) / avg_term
    roll["closing"] = roll.sum(axis=1)

    # LIC at 31-Dec-2025. SEEDED ERRORS: pending listing cut on 19-Dec (completeness);
    # IBNR = 25% of expected Q4 claims; no claim-handling costs, no RA, undiscounted.
    pending = register[(register["status"] == "pendiente") & (register["report_date"] <= LISTING_CUTOFF)]
    inforce = census[(census["cohort"] + census["term"] > 2025) &
                     ~((census["exit"] != "vigente") & (census["exit_date"] < pd.Timestamp("2025-01-01")))]
    att = inforce["issue_age"].to_numpy() + 2025 - inforce["cohort"].to_numpy()
    q = np.where(inforce["sex"].to_numpy() == "M", cso["M"].to_numpy()[att], cso["F"].to_numpy()[att])
    expected_q4 = float((q * be_factor(att) * inforce["sum_insured"].to_numpy()).sum() / 4)
    lic = {"rbns": float(pending["amount"].sum()), "ibnr": 0.25 * expected_q4,
           "claim_handling": 0.0, "risk_adjustment": 0.0, "discounting": 0.0}
    lic["total"] = sum(lic.values())

    r = lambda d: {k: round(float(v), 2) for k, v in d.items()}
    return {
        "entity": "Seguros Barú, S.A. (ficticia)",
        "valuation_date": "2025-12-31",
        "cohort_2025_initial_recognition": {grp: r(row) for grp, row in g.iterrows()},
        "sets_classification": {ch: grp for ch, grp in sets["group"].items()},
        "csm_rollforward_2025": {grp: r(row) for grp, row in roll.iterrows()},
        "lic_2025": r(lic),
        "pending_claims_listing": pending["claim_id"].tolist(),
        "notes": {
            "ra": "Cost of capital 6%; capital = mortality +15% shock, run off with sum insured in force.",
            "csm_interest": "4% (tariff technical rate).",
            "csm_release": "Straight line over the SI-weighted average term of the group.",
            "ibnr": "25% of expected claims of Q4-2025.",
            "listing": "Pending claims listing from the claims system, extracted 19-Dec-2025.",
        },
    }


def main(experience_seed: int = EXPERIENCE_SEED, write: bool = True):
    census = make_census(np.random.default_rng(SEED))
    claims = simulate_experience(census, np.random.default_rng(experience_seed))
    reg = claims[claims["report_date"] <= VALUATION_DATE].copy()
    paid = reg["payment_date"] <= VALUATION_DATE
    reg["status"] = np.where(paid, "pagado", "pendiente")
    reg.loc[~paid, "payment_date"] = pd.NaT
    after = claims[(claims["death_date"] <= VALUATION_DATE) & (claims["report_date"] > VALUATION_DATE)
                   & (claims["report_date"] <= REPORT_DATE)].drop(columns="payment_date")
    package = management_package(census, reg)
    if not write:
        return census, claims, reg, after, package

    OUT.mkdir(parents=True, exist_ok=True)
    census.to_csv(OUT / "census.csv", index=False, date_format="%Y-%m-%d")
    reg.to_csv(OUT / "claims_register.csv", index=False, date_format="%Y-%m-%d")
    after.to_csv(OUT / "claims_after_close.csv", index=False, date_format="%Y-%m-%d")
    (OUT / "assumptions.json").write_text(json.dumps(ASSUMPTIONS, indent=2, ensure_ascii=False))
    (OUT / "management_package.json").write_text(json.dumps(package, indent=2, ensure_ascii=False))
    return census, claims, reg, after, package


if __name__ == "__main__":
    c, cl, reg, after, pkg = main()
    print(c["exit"].value_counts(), len(cl), len(reg), len(after))
    print(json.dumps(pkg["cohort_2025_initial_recognition"], indent=1))
    print(pkg["sets_classification"], json.dumps(pkg["csm_rollforward_2025"], indent=1), pkg["lic_2025"])
