"""Property and casualty under the premium allocation approach (IFRS 17 par. 53-59, B126).

Portfolios: motor (AUTO: private cars and commercial fleets), fire/home (INC) and
contractors' all risk (TRC, after the eligibility test in ``trc_eligibility``).

Groups (par. 16-18, memo section 6). Each segment and cohort is a set of contracts
classified on its expected combined ratio, risk adjustment included:
    SIG <= 95% < RES <= 100% < ONE.

Liability for remaining coverage (par. 55): premiums received less revenue recognised
and, where acquisition cash flows are deferred (motor and CAR; fire/home expenses them,
59(a)), less the acquisition cash flows not yet amortised. Revenue follows the passage
of time (B126(a)); for CAR it follows the expected incidence of claims, because the
exposure grows with the works (B126(b)). An onerous test compares the fulfilment cash
flows of the remaining coverage with that carrying amount (par. 57-58).

Liability for incurred claims: case reserves of reported claims plus IBNR with the
Bornhuetter-Ferguson logic (expected claims of each accident month x share not yet
reported), plus claims-handling costs (B65(f)). Motor and CAR are discounted (59(b));
fire/home is not, because its claims are paid within a year. The risk adjustment is the
75th percentile of a lognormal, aggregated across coverages with a 25% correlation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import assumptions as A
from .data import load
from .discounting import curve_for
from .risk_adjustment import CONFIDENCE_PC, lognormal_confidence_margin
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
MONTHS = pd.period_range("2023-01", "2028-12", freq="M")
MONTH_START = MONTHS.start_time.to_numpy().astype("datetime64[D]")
MONTH_END = (MONTHS.end_time.normalize() + pd.Timedelta(days=1)).to_numpy().astype("datetime64[D]")
SHOCK_START_YEAR = 2024

LINES = {
    "AUTO": {"table": "auto", "commission": A.MOTOR_COMMISSION, "admin": A.MOTOR_ADMIN, "levy": 0.0,
             "defer_acquisition": True, "discount": True, "revenue_pattern": "time"},
    "INC": {"table": "inc", "commission": A.FIRE["commission"], "admin": A.FIRE["admin"], "levy": A.FIRE_LEVY,
            "defer_acquisition": False, "discount": False, "revenue_pattern": "time"},
    "TRC": {"table": "trc", "commission": A.CAR["commission"], "admin": A.CAR["admin"], "levy": 0.0,
            "defer_acquisition": True, "discount": True, "revenue_pattern": "claims"},
}
COVERAGES = {"AUTO": ("PD", "RC"), "INC": ("FIRE", "CAT"), "TRC": ("CAR",)}
REPORT_MEAN = {"PD": A.REPORT_DELAY_MEAN["pd"], "RC": A.REPORT_DELAY_MEAN["rc"], "FIRE": A.REPORT_DELAY_MEAN["fire"],
               "CAT": 0.25, "CAR": A.REPORT_DELAY_MEAN["car"]}
SETTLE_MEAN = {"PD": A.SETTLEMENT_DELAY_MEAN["pd"], "FIRE": A.SETTLEMENT_DELAY_MEAN["fire"], "CAT": 4.0,
               "CAR": A.SETTLEMENT_DELAY_MEAN["car"]}


# --------------------------------------------------------------------------
# exposure, expected claims and revenue patterns
# --------------------------------------------------------------------------
@lru_cache(maxsize=None)
def policies(line: str) -> pd.DataFrame:
    df = load(f"{LINES[line]['table']}_policies").copy()
    df["end_date"] = df["expiry_date"] + pd.Timedelta(days=1)
    return df


def earned_fraction(line: str, dates) -> np.ndarray:
    """Share of each policy's revenue pattern run off at each date (rows: policies)."""
    p = policies(line)
    s = p["issue_date"].to_numpy("datetime64[D]")[:, None]
    e = p["end_date"].to_numpy("datetime64[D]")[:, None]
    d = np.asarray(dates, dtype="datetime64[D]")[None, :]
    f = np.clip((d - s).astype(float) / (e - s).astype(float), 0.0, 1.0)
    return f**2 if LINES[line]["revenue_pattern"] == "claims" else f


def _known_index(as_of) -> float:
    return A.FLEET_PD_SEVERITY_INDEX_KNOWN[str(pd.Timestamp(as_of).date())]


def expected_claims_by_month(line: str, as_of) -> dict:
    """Expected claims cost by policy and occurrence month for each coverage, on the best
    estimate known at ``as_of`` (frequency x severity with trend; CAR: loss ratio x premium)."""
    p = policies(line)
    start = earned_fraction_time(line, MONTH_START)
    end = earned_fraction_time(line, MONTH_END)
    years = (p["end_date"] - p["issue_date"]).dt.days.to_numpy() / 365.25
    mid = (MONTHS.start_time + (MONTHS.end_time - MONTHS.start_time) / 2)
    t = ((mid - pd.Timestamp(f"{A.START_YEAR}-01-01")).days / 365.25).to_numpy()
    out = {}
    if line == "AUTO":
        exposure = (end - start) * years[:, None]
        for seg, s in A.MOTOR.items():
            rows = (p["segment"] == seg).to_numpy()
            pd_sev = s.severity_pd * (1 + s.severity_trend) ** t
            if seg == "flotas":
                pd_sev = pd_sev * np.where(MONTHS.year >= SHOCK_START_YEAR, _known_index(as_of), 1.0)
            rc_sev = s.severity_rc * (1 + s.severity_trend) ** t
            out.setdefault("PD", np.zeros_like(exposure))[rows] = exposure[rows] * s.frequency_pd * pd_sev
            out.setdefault("RC", np.zeros_like(exposure))[rows] = exposure[rows] * s.frequency_rc * rc_sev
    elif line == "INC":
        f = A.FIRE
        exposure = (end - start) * years[:, None]
        out["FIRE"] = exposure * f["frequency"] * f["severity"] * (1 + f["severity_trend"]) ** t
        per_policy_year = f["cat_probability"] * f["cat_loss"] / np.mean(list(f["policies"].values()))
        out["CAT"] = exposure * per_policy_year
    else:
        claims_start, claims_end = start**2, end**2  # exposure grows linearly with the works
        out["CAR"] = (claims_end - claims_start) * (A.CAR["expected_loss_ratio"] * p["premium"].to_numpy())[:, None]
    return out


def earned_fraction_time(line: str, dates) -> np.ndarray:
    p = policies(line)
    s = p["issue_date"].to_numpy("datetime64[D]")[:, None]
    e = p["end_date"].to_numpy("datetime64[D]")[:, None]
    d = np.asarray(dates, dtype="datetime64[D]")[None, :]
    return np.clip((d - s).astype(float) / (e - s).astype(float), 0.0, 1.0)


def month_pos(date) -> int:
    """Index of the month that ends at ``date`` (month-end closings)."""
    return MONTHS.get_loc(pd.Period(pd.Timestamp(date), freq="M"))


# --------------------------------------------------------------------------
# payment timing (for discounting, par. 59(b), and the liquidity analysis, par. 132)
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def cas_patterns() -> dict:
    t = pd.read_csv(ROOT / "data" / "processed" / "claims_patterns.csv")
    return {line: g.sort_values("development_year")["incremental_paid"].to_numpy() for line, g in t.groupby("line")}


def rc_pattern(segment: str) -> np.ndarray:
    return cas_patterns()["ppauto" if A.MOTOR[segment].rc_pattern == "ppauto" else "comauto"]


def outstanding_schedule(coverage: str, segment: str, accident_year: int, closing, kind: str):
    """(times in years after the closing, shares) for the outstanding amount of an accident year.

    Liability (RC) follows the CAS paid pattern from the accident year's current age; the
    short-tail coverages pay after the expected report and settlement delays.
    """
    c = pd.Timestamp(closing)
    if coverage == "RC":
        inc = rc_pattern(segment)
        age = c.year - accident_year + 1  # development years completed
        rest = inc[age:] if age < len(inc) else np.array([1.0])
        if rest.sum() <= 0:
            return np.array([0.5]), np.array([1.0])
        times = np.arange(len(rest)) + 0.5
        return times, rest / rest.sum()
    lag = SETTLE_MEAN[coverage] + (REPORT_MEAN[coverage] if kind == "ibnr" else 0.0)
    return np.array([lag / 12.0]), np.array([1.0])


def pv_factor(line: str, coverage: str, segment: str, accident_year: int, closing, kind: str, curve=None) -> float:
    if not LINES[line]["discount"]:
        return 1.0
    times, shares = outstanding_schedule(coverage, segment, accident_year, closing, kind)
    curve = curve or curve_for(pd.Timestamp(closing).strftime("%Y-%m"), line)
    return float((curve.discount(times) * shares).sum())


def mean_payment_lag_years(coverage: str, segment: str = "particulares") -> float:
    """Mean time from occurrence to payment, used to discount the remaining-coverage claims."""
    if coverage == "RC":
        inc = rc_pattern(segment)
        return float((inc * (np.arange(len(inc)) + 0.5)).sum() - 0.5)  # occurrences spread over the year
    return (REPORT_MEAN[coverage] + SETTLE_MEAN[coverage]) / 12.0


# --------------------------------------------------------------------------
# Phase 2: classification at recognition (par. 16-18)
# --------------------------------------------------------------------------
PREVIOUS = {2023: "2022-12-31", 2024: "2023-12-31", 2025: "2024-12-31"}


def lrc_cv(line: str, segment: str) -> float:
    return A.PAA_LRC_CV[(line, segment)]


def classify() -> pd.DataFrame:
    rows = []
    for line in LINES:
        p = policies(line)
        for cohort, as_of in PREVIOUS.items():
            claims = expected_claims_by_month(line, as_of)
            total_claims = sum(claims.values()).sum(axis=1)
            conf = LINES[line]
            for seg, idx in p[p["issue_year"] == cohort].groupby("segment").groups.items():
                rows_mask = p.index.isin(idx)
                prem = p.loc[rows_mask, "premium"].sum()
                exp_claims = total_claims[rows_mask].sum()
                ra = float(lognormal_confidence_margin(exp_claims, lrc_cv(line, seg)))
                expenses = prem * (conf["commission"] + conf["admin"] + A.PREMIUM_TAX + conf["levy"])
                ratio = (exp_claims + ra + expenses) / prem
                label = "SIG" if ratio <= A.COMBINED_RATIO_THRESHOLDS["SIG"] else (
                    "RES" if ratio <= A.COMBINED_RATIO_THRESHOLDS["RES"] else "ONE")
                rows.append({"line": line, "segment": seg, "cohort": cohort, "policies": int(rows_mask.sum()),
                             "premium": prem, "expected_claims": exp_claims, "ra_lrc": ra,
                             "loss_ratio": exp_claims / prem, "combined_ratio": ratio, "class": label,
                             "group": f"{line}-{cohort}-{label}"})
    return pd.DataFrame(rows)


def assign_groups(classification: pd.DataFrame) -> dict:
    out = {}
    for line in LINES:
        p = policies(line)
        key = classification[classification["line"] == line].set_index(["cohort", "segment"])["group"]
        out[line] = pd.Series(key.reindex(pd.MultiIndex.from_arrays([p["issue_year"], p["segment"]])).to_numpy(),
                              index=p["policy_id"].to_numpy())
    return out


# --------------------------------------------------------------------------
# measurement at a closing
# --------------------------------------------------------------------------
@dataclass
class PaaClosing:
    closing: str
    lrc: pd.DataFrame  # by group
    lic: pd.DataFrame  # by group, coverage and accident year
    pnl: pd.DataFrame  # by group (for the period ending at the closing)


def _unreported_fraction(closing, mean_months: float) -> np.ndarray:
    """Average P(report delay > closing - t) for occurrences spread evenly in each month."""
    c = np.datetime64(pd.Timestamp(closing).date()) + np.timedelta64(1, "D")  # end of the closing day
    a = (c - MONTH_END).astype(float) / (365.25 / 12)  # months from month end to closing
    b = (c - MONTH_START).astype(float) / (365.25 / 12)
    frac = np.where(a >= 0, mean_months * (np.exp(-a / mean_months) - np.exp(-b / mean_months)) / np.maximum(b - a, 1e-9), 0.0)
    return frac


def lic_at(line: str, closing, groups: pd.Series) -> pd.DataFrame:
    """Case reserves, IBNR, claims-handling costs and PV by group, coverage and accident year."""
    c = pd.Timestamp(closing)
    p = policies(line)
    claims = load(f"{LINES[line]['table']}_claims")
    cases = load(f"{LINES[line]['table']}_case_reserves")
    cases = cases[cases["closing"] == c].merge(claims[["claim_id", "policy_id", "coverage", "occurrence_date", "segment"]], on="claim_id")
    cases["group"] = cases["policy_id"].map(groups)
    cases["ay"] = cases["occurrence_date"].dt.year
    exp = expected_claims_by_month(line, c)
    pos = month_pos(c)
    rows = []
    gid = groups.reindex(p["policy_id"]).to_numpy()
    for cov, matrix in exp.items():
        frac = _unreported_fraction(c, REPORT_MEAN[cov])[: pos + 1]
        ibnr_pm = matrix[:, : pos + 1] * frac[None, :]
        ay_of_month = MONTHS.year[: pos + 1]
        for seg in p["segment"].unique():
            seg_rows = (p["segment"] == seg).to_numpy()
            for g in np.unique(gid[seg_rows]):
                r = seg_rows & (gid == g)
                for ay in np.unique(ay_of_month):
                    ibnr = ibnr_pm[r][:, ay_of_month == ay].sum()
                    case = cases[(cases["group"] == g) & (cases["coverage"] == cov) & (cases["ay"] == ay) & (cases["segment"] == seg)]["case_reserve"].sum()
                    if ibnr == 0 and case == 0:
                        continue
                    f_case = pv_factor(line, cov, seg, ay, c, "case")
                    f_ibnr = pv_factor(line, cov, seg, ay, c, "ibnr")
                    undisc = (case + ibnr) * (1 + A.ULAE_RATE)
                    pv = (case * f_case + ibnr * f_ibnr) * (1 + A.ULAE_RATE)
                    rows.append({"closing": str(c.date()), "line": line, "group": g, "segment": seg, "coverage": cov,
                                 "accident_year": int(ay), "case": case, "ibnr": ibnr, "ulae": (case + ibnr) * A.ULAE_RATE,
                                 "undiscounted": undisc, "pv": pv})
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def claims_cv_fit() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / "processed" / "claims_cv.csv").set_index("line")


def lic_cv(coverage: str, segment: str, reserve: float) -> float:
    if coverage == "RC":
        fit = claims_cv_fit().loc["ppauto" if A.MOTOR[segment].rc_pattern == "ppauto" else "comauto"]
        return float(np.exp(fit["a"] + fit["b"] * np.log(max(reserve, 1.0) / 1000.0)))
    return A.LIC_CV_SHORT_TAIL[coverage]


def risk_adjustment_lic(lic: pd.DataFrame) -> pd.DataFrame:
    """75th-percentile margin per coverage cell, diversified across all P&C cells and allocated back."""
    if lic.empty:
        return lic.assign(ra=0.0)
    cells = lic.groupby(["line", "segment", "coverage"])["pv"].sum().reset_index()
    cells["cv"] = [lic_cv(cv, seg, r) for cv, seg, r in zip(cells["coverage"], cells["segment"], cells["pv"])]
    cells["ra_standalone"] = lognormal_confidence_margin(cells["pv"].to_numpy(), cells["cv"].to_numpy())
    sd = (cells["pv"] * cells["cv"]).to_numpy()
    corr = np.full((len(sd), len(sd)), A.PC_CORRELATION)
    np.fill_diagonal(corr, 1.0)
    total_sd = float(np.sqrt(sd @ corr @ sd))
    total_mean = float(cells["pv"].sum())
    ra_total = float(lognormal_confidence_margin(total_mean, total_sd / total_mean)) if total_mean > 0 else 0.0
    cells["ra"] = cells["ra_standalone"] * ra_total / cells["ra_standalone"].sum()
    out = lic.merge(cells[["line", "segment", "coverage", "ra", "pv"]].rename(columns={"pv": "cell_pv", "ra": "cell_ra"}),
                    on=["line", "segment", "coverage"])
    out["ra"] = out["cell_ra"] * out["pv"] / out["cell_pv"]
    out.attrs["confidence"] = {"ra_total": ra_total, "sd_total": total_sd, "mean_total": total_mean,
                               "equivalent_level": float(norm.cdf(ra_total / total_sd)) if total_sd else 1.0}
    return out.drop(columns=["cell_pv", "cell_ra"])


def lrc_at(line: str, closing, groups: pd.Series) -> pd.DataFrame:
    """Carrying amount of the LRC by group and the onerous test (par. 55, 57-58)."""
    c = pd.Timestamp(closing)
    conf = LINES[line]
    p = policies(line).copy()
    p["group"] = p["policy_id"].map(groups)
    p = p[p["issue_date"] <= c]
    prem = load(f"{conf['table']}_premiums")
    prem = prem[prem["date"] <= c].merge(p[["policy_id", "group"]], on="policy_id")
    f = earned_fraction(line, [np.datetime64(c.date()) + np.timedelta64(1, "D")])[:, 0]
    f = pd.Series(f, index=policies(line)["policy_id"]).reindex(p["policy_id"]).to_numpy()
    p["revenue_cum"] = p["premium"] * f
    p["acq_expected"] = p["premium"] * conf["commission"]
    p["acq_amortised_cum"] = p["acq_expected"] * f
    received = prem.groupby("group")["premium"].sum()
    acq_paid = prem.groupby("group")["commission"].sum()
    taxes_paid = prem.groupby("group")["premium_tax"].sum() + (prem.groupby("group")["fire_levy"].sum() if "fire_levy" in prem else 0.0)

    # remaining coverage: expected claims after the closing and future premium receipts
    exp = expected_claims_by_month(line, c)
    pos = month_pos(c)
    rows_all = policies(line)["policy_id"].isin(p["policy_id"]).to_numpy()
    curve = curve_for(c.strftime("%Y-%m"), line)
    future_months_t = (np.arange(len(MONTHS)) - pos - 0.5) / 12.0  # mid-month, years after closing
    pv_claims = np.zeros(rows_all.sum())
    for cov, matrix in exp.items():
        m = matrix[rows_all][:, pos + 1:]
        if conf["discount"]:
            seg = "particulares"
            lag = mean_payment_lag_years(cov, seg)
            d = curve.discount(np.maximum(future_months_t[pos + 1:] + lag, 0.0))
            pv_claims += m @ d
        else:
            pv_claims += m.sum(axis=1)
    p["pv_claims_remaining"] = pv_claims
    future_prem = load(f"{conf['table']}_premiums")
    future_prem = future_prem[(future_prem["date"] > c)].merge(p[["policy_id", "group"]], on="policy_id")
    out = []
    for g, sub in p.groupby("group"):
        seg = sub["segment"].iloc[0]
        unearned = (sub["premium"] - sub["revenue_cum"]).sum()
        fut = future_prem[future_prem["group"] == g]
        fut_receipts = fut["premium"].sum()
        fut_acq_tax = fut["commission"].sum() + fut["premium_tax"].sum() + (fut["fire_levy"].sum() if "fire_levy" in fut else 0.0)
        claims_rem = sub["pv_claims_remaining"].sum()
        ra_rem = float(lognormal_confidence_margin(claims_rem, lrc_cv(line, seg)))
        maint = conf["admin"] * unearned
        fcf_remaining = claims_rem + ra_rem + maint + fut_acq_tax - fut_receipts
        lrc_excl = received.get(g, 0.0) - sub["revenue_cum"].sum()
        if conf["defer_acquisition"]:
            lrc_excl -= acq_paid.get(g, 0.0) - sub["acq_amortised_cum"].sum()
        lc = max(0.0, fcf_remaining - lrc_excl)
        out.append({"closing": str(c.date()), "line": line, "group": g, "premium_written": sub["premium"].sum(),
                    "premiums_received_cum": received.get(g, 0.0), "revenue_cum": sub["revenue_cum"].sum(),
                    "acq_paid_cum": acq_paid.get(g, 0.0), "acq_amortised_cum": sub["acq_amortised_cum"].sum(),
                    "taxes_paid_cum": taxes_paid.get(g, 0.0) if hasattr(taxes_paid, "get") else 0.0,
                    "unearned_premium": unearned, "future_receipts": fut_receipts,
                    "pv_claims_remaining": claims_rem, "ra_remaining": ra_rem, "fcf_remaining": fcf_remaining,
                    "lrc_excl_lc": lrc_excl, "loss_component": lc})
    return pd.DataFrame(out)


def paid_by_group(line: str, groups: pd.Series, t0, t1) -> pd.DataFrame:
    claims = load(f"{LINES[line]['table']}_claims")
    pay = load(f"{LINES[line]['table']}_payments")
    pay = pay[(pay["payment_date"] > pd.Timestamp(t0)) & (pay["payment_date"] <= pd.Timestamp(t1))]
    pay = pay.merge(claims[["claim_id", "policy_id", "occurrence_date"]], on="claim_id")
    pay["group"] = pay["policy_id"].map(groups)
    pay["current"] = pay["occurrence_date"] > pd.Timestamp(t0)
    return pay.groupby(["group", "current"])["amount"].sum().unstack(fill_value=0.0)


def run_all(closings=A.CLOSINGS) -> dict:
    classification = classify()
    groups = assign_groups(classification)
    out = {"classification": classification, "groups": groups, "lrc": [], "lic": [], "pnl": []}
    prev = {"lrc": None, "lic": None}
    t0 = pd.Timestamp("2022-12-31")
    expenses = load("expenses")
    for c in closings:
        t1 = pd.Timestamp(c)
        lrc = pd.concat([lrc_at(line, c, groups[line]) for line in LINES], ignore_index=True)
        lic = risk_adjustment_lic(pd.concat([lic_at(line, c, groups[line]) for line in LINES], ignore_index=True))
        lic["current"] = lic["accident_year"] == t1.year
        pnl = []
        for _, r in lrc.iterrows():
            g, line = r["group"], r["line"]
            conf = LINES[line]
            o = prev["lrc"].set_index("group").loc[g] if (prev["lrc"] is not None and g in set(prev["lrc"]["group"])) else None
            def d(col):  # movement in the period of a cumulative column  # noqa: E306
                return r[col] - (o[col] if o is not None else 0.0)
            gl = lic[lic["group"] == g]
            gl_prev = prev["lic"][prev["lic"]["group"] == g] if prev["lic"] is not None else pd.DataFrame(columns=lic.columns)
            paid = paid_by_group(line, groups[line], t0, t1)
            paid_cur = paid.loc[g, True] if (g in paid.index and True in paid.columns) else 0.0
            paid_prior = paid.loc[g, False] if (g in paid.index and False in paid.columns) else 0.0
            open_pv, open_ra = gl_prev["pv"].sum(), gl_prev["ra"].sum()
            unwind = 0.0
            if conf["discount"] and not gl_prev.empty:
                c0 = curve_for(t0.strftime("%Y-%m"), line)
                for row in gl_prev.itertuples():  # interest while each opening payment is outstanding, up to one year
                    times, shares = outstanding_schedule(row.coverage, row.segment, row.accident_year, t0, "case")
                    w = shares * c0.discount(times)
                    growth = 1.0 / c0.discount(np.minimum(times, 1.0)) - 1.0
                    unwind += row.pv * float((w * growth).sum() / w.sum())
            close_prior_pv = gl.loc[~gl["current"], "pv"].sum()
            # rate effect: the prior-year claims re-measured at the opening curve vs the closing curve
            rate_effect = 0.0
            if conf["discount"] and not gl_prev.empty:
                at_open = sum(row.pv / max(pv_factor(line, row.coverage, row.segment, row.accident_year, c, "case"), 1e-9)
                              * pv_factor(line, row.coverage, row.segment, row.accident_year, c, "case",
                                          curve=curve_for(t0.strftime("%Y-%m"), line))
                              for row in gl[~gl["current"]].itertuples())
                rate_effect = close_prior_pv - at_open
            finance = unwind + rate_effect
            past = close_prior_pv - open_pv + paid_prior - finance
            incurred_cur = gl.loc[gl["current"], "pv"].sum() + paid_cur
            ra_close = gl["ra"].sum()
            admin = expenses[(expenses["portfolio"] == line)
                             & (pd.PeriodIndex(expenses["month"], freq="M").start_time > t0)
                             & (pd.PeriodIndex(expenses["month"], freq="M").start_time <= t1)]["amount"].sum()
            line_rev = lrc[lrc["line"] == line]
            rev_share = d("revenue_cum") / max((line_rev["revenue_cum"] - (prev["lrc"].set_index("group").reindex(line_rev["group"])["revenue_cum"].fillna(0).to_numpy() if prev["lrc"] is not None else 0)).sum(), 1e-9)
            acq = d("acq_amortised_cum") if conf["defer_acquisition"] else d("acq_paid_cum")
            lc_change = r["loss_component"] - (o["loss_component"] if o is not None else 0.0)
            ise_claims = incurred_cur + past + (ra_close - open_ra)
            ise = ise_claims + acq + d("taxes_paid_cum") + admin * rev_share + lc_change
            pnl.append({"closing": c, "line": line, "group": g, "insurance_revenue": d("revenue_cum"),
                        "incurred_claims_current": incurred_cur, "past_service_changes": past,
                        "ra_lic_change": ra_close - open_ra, "acquisition_expense": acq, "premium_taxes": d("taxes_paid_cum"),
                        "attributable_expenses": admin * rev_share, "onerous_losses": lc_change,
                        "insurance_service_expenses": ise, "insurance_service_result": d("revenue_cum") - ise,
                        "ifie": finance, "lic_open_pv": open_pv, "lic_open_ra": open_ra, "lic_paid": paid_cur + paid_prior,
                        "lic_close_pv": gl["pv"].sum(), "lic_close_ra": ra_close, "premiums_received": d("premiums_received_cum"),
                        "acq_paid": d("acq_paid_cum")})
        out["lrc"].append(lrc)
        out["lic"].append(lic)
        out["pnl"].append(pd.DataFrame(pnl))
        prev = {"lrc": lrc, "lic": lic}
        t0 = t1
    return out


# --------------------------------------------------------------------------
# Phase 2: PAA eligibility of CAR (par. 53(a), 54; memo section 7)
# --------------------------------------------------------------------------
TRC_SCENARIOS = {
    "base": {},
    "claims_+20%": {"claims": 1.20},
    "claims_-20%": {"claims": 0.80},
    "rates_+100bp": {"shift": 0.01},
    "rates_-100bp": {"shift": -0.01},
    "works_slower": {"warp": 1.5},  # the remaining progress of the works is back-loaded
    "works_faster": {"warp": 0.67},
}
TRC_THRESHOLD = 0.05


def trc_eligibility(cohort: int, threshold: float = TRC_THRESHOLD) -> pd.DataFrame:
    """LRC under the PAA and under the GMM at each year end of the coverage, by scenario.

    Both measurements are equal in substance at the first year end. Each scenario is then
    learnt at that date and applies to the coverage still to be provided:
    * the GMM absorbs the change in fulfilment cash flows in the CSM (par. 44(c)) and
      releases the CSM on the revised coverage units (B119); a change in rates is a
      financial effect that does not touch the CSM (B97(a));
    * the PAA keeps premiums received less revenue, with revenue following the revised
      expected incidence of claims (B126(b)); it is never discounted (par. 56).
    The group is eligible when every difference is within ``threshold`` of the GMM LRC.
    """
    c = A.CAR
    p = policies("TRC")
    p = p[p["issue_year"] == cohort]
    start = ((p["issue_date"] - pd.Timestamp(f"{cohort}-01-01")).dt.days / (365.25 / 12)).to_numpy()
    prem = p["premium"].to_numpy()
    T = float(c["duration_months"])
    end_m = int(np.ceil(start.max() + T))
    grid = np.arange(end_m + 2, dtype=float)
    lag = A.REPORT_DELAY_MEAN["car"] + A.SETTLEMENT_DELAY_MEAN["car"]
    curve = curve_for(f"{cohort}-01", "TRC")
    closings = [12 * k for k in range(1, int(np.ceil(end_m / 12)) + 1)]
    acq_rate, admin = c["commission"], c["admin"]
    elr, cv = c["expected_loss_ratio"], A.PAA_LRC_CV[("TRC", "construccion")]
    time_share = np.clip((grid[None, :] - start[:, None]) / T, 0.0, 1.0)
    F0 = time_share**2  # expected incidence of claims: exposure grows linearly with the works
    tau1 = closings[0]

    def revised(warp):
        if warp == 1.0:
            return F0
        f1 = F0[:, [tau1]]
        rest = np.clip((F0 - f1) / np.where(1 - f1 > 0, 1 - f1, 1.0), 0.0, 1.0)
        return np.where(grid[None, :] <= tau1, F0, f1 + (1 - f1) * rest**warp)

    def pv_remaining(F, t_now, scale=1.0, shift=0.0):
        k = int(t_now)
        dF = np.diff(F, axis=1)[:, k:]
        dT = np.diff(time_share, axis=1)[:, k:]
        tf = grid[k + 1:] - 0.5 - t_now
        tc = np.maximum(tf + lag, 0.0) / 12.0
        tm = np.maximum(tf, 0.0) / 12.0
        claims = ((elr * prem * scale)[:, None] * dF) @ (curve.discount(tc) * np.exp(-shift * tc))
        maint = ((admin * prem)[:, None] * dT) @ (curve.discount(tm) * np.exp(-shift * tm))
        return claims, maint

    # initial recognition of each project at its start (locked rates = the cohort curve)
    pc0, pm0 = pv_remaining(F0, 0.0)
    d_start = curve.discount(start / 12.0)
    pc0, pm0 = pc0 / d_start, pm0 / d_start
    fcf0 = pc0 + pm0 + lognormal_confidence_margin(pc0, cv) + prem * (acq_rate + A.PREMIUM_TAX) - prem
    csm0 = np.maximum(-fcf0, 0.0)
    r = float(curve.spot(1.0)[0])
    csm_tau1 = csm0 * (1 + r) ** (np.maximum(tau1 - start, 0) / 12.0) * (1 - F0[:, tau1])

    rows = []
    for name, sc in TRC_SCENARIOS.items():
        scale, shift, warp = sc.get("claims", 1.0), sc.get("shift", 0.0), sc.get("warp", 1.0)
        F = revised(warp)
        # change in estimates learnt at the first year end, measured at locked rates
        c_new, m_new = pv_remaining(F, tau1, scale)
        c_old, m_old = pv_remaining(F0, tau1)
        delta = (c_new + m_new + lognormal_confidence_margin(c_new, cv)) - (c_old + m_old + lognormal_confidence_margin(c_old, cv))
        csm_after = np.maximum(csm_tau1 - delta, 0.0)
        loss = np.maximum(delta - csm_tau1, 0.0)
        for j, tau in enumerate(closings):
            if j == 0:
                pc, pm = pv_remaining(F0, tau)
                csm = csm_tau1
            else:
                pc, pm = pv_remaining(F, tau, scale, shift)
                rem = np.where(1 - F[:, tau1] > 0, (1 - F[:, tau]) / (1 - F[:, tau1]), 0.0)
                csm = csm_after * (1 + r) ** ((tau - tau1) / 12.0) * rem
            gmm = float((pc + pm + lognormal_confidence_margin(pc, cv) + csm).sum())
            Fp = F0 if j == 0 else F
            paa = float((prem * (1 - acq_rate) * (1 - Fp[:, tau])).sum())
            rows.append({"cohort": cohort, "scenario": name, "year_end": cohort + j, "lrc_gmm": gmm, "lrc_paa": paa,
                         "difference": paa - gmm, "relative": (paa - gmm) / gmm if gmm else 0.0,
                         "loss_if_gmm": float(loss.sum())})
    out = pd.DataFrame(rows)
    live = out["lrc_gmm"] > 0
    out.attrs["eligible"] = bool((out.loc[live, "relative"].abs() <= threshold).all())
    out.attrs["max_relative"] = float(out.loc[live, "relative"].abs().max())
    return out
