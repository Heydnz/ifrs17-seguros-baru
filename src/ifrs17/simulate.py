"""Synthetic portfolio and experience of Seguros Baru, 2023-2025 (Phase 1).

Everything is generated from the fixed seed in ``assumptions.SEED`` and the TRUE
parameters in ``assumptions``; no client data is used. Each block draws from its own
child random stream, so changing one product does not change the others.

The output is the entity's "administrative system": policies, premiums, claims,
payments, case reserves and expenses. It holds the full simulated truth for events
that occurred up to 31 December 2025, including reports and payments made later; the
engine must read it through ``ifrs17.data.as_of(closing)`` so that each closing only
sees what was known at that date.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import assumptions as A
from .life import older_high_si, price_term_life
from .mortality import cso1980, monthly_rate

DAYS_PER_MONTH = 365.25 / 12
ONE_DAY, ONE_MONTH = np.timedelta64(1, "D"), np.timedelta64(1, "M")
SIM_END = np.datetime64("2025-12-31")
ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ROOT / "data" / "processed" / "claims_patterns.csv"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _streams(seed: int, names):
    children = np.random.SeedSequence(seed).spawn(len(names))
    return {n: np.random.default_rng(c) for n, c in zip(names, children)}


def _month_start(year, month) -> np.ndarray:
    y, m = np.asarray(year), np.asarray(month)
    return (np.asarray((y - 1970) * 12 + (m - 1), dtype="datetime64[M]")).astype("datetime64[D]")


def _add_months(dates, months) -> np.ndarray:
    """Shift dates by a real number of months (average month length)."""
    return np.asarray(dates, dtype="datetime64[D]") + np.round(np.asarray(months) * DAYS_PER_MONTH).astype("timedelta64[D]")


def add_calendar_months(dates, months) -> np.ndarray:
    """Same day of the month, ``months`` later (clipped to the month's last day)."""
    d = np.asarray(dates, dtype="datetime64[D]")
    m0 = d.astype("datetime64[M]")
    day = (d - m0.astype("datetime64[D]")).astype(int)
    target = m0 + np.asarray(months, dtype=int).astype("timedelta64[M]")
    last = ((target + ONE_MONTH).astype("datetime64[D]") - target.astype("datetime64[D]")).astype(int) - 1
    return target.astype("datetime64[D]") + np.minimum(day, last).astype("timedelta64[D]")


def _lognormal(rng, mean, cv, size=None):
    sigma = np.sqrt(np.log1p(np.asarray(cv, float) ** 2))
    mu = np.log(mean) - sigma**2 / 2
    return rng.lognormal(mu, sigma, size)


def _triangular_ages(rng, low, mode, high, n):
    return np.floor(rng.triangular(low, mode, high + 1, n)).astype(int).clip(low, high)


def _year_fraction(dates) -> np.ndarray:
    d = np.asarray(dates, dtype="datetime64[D]")
    year = d.astype("datetime64[Y]").astype(int) + 1970
    start = d.astype("datetime64[Y]").astype("datetime64[D]")
    return year + (d - start).astype(int) / 365.25


def _inflation(dates, rate=A.EXPENSE_INFLATION):
    return (1 + rate) ** (_year_fraction(dates) - A.START_YEAR)


def _issue_months(rng, total: int) -> np.ndarray:
    return np.repeat(np.arange(1, 13), rng.multinomial(total, np.full(12, 1 / 12)))


def _age_band(age) -> np.ndarray:
    return np.select([age < 40, age < 50], ["25-39", "40-49"], "50-60")


# --------------------------------------------------------------------------
# term life (VT)
# --------------------------------------------------------------------------
def term_life_policies(rng) -> pd.DataFrame:
    p = A.TERM_LIFE
    frames = []
    for year, total in p.new_policies.items():
        months = _issue_months(rng, total)
        n = len(months)
        mix = p.channel_mix[year]
        channel = rng.choice(list(mix), n, p=list(mix.values()))
        age = _triangular_ages(rng, *p.issue_age_range[:1], p.issue_age_mode, p.issue_age_range[1], n)
        terms = np.array(list(p.term_mix))
        weights = np.array(list(p.term_mix.values()))
        term = np.empty(n, int)
        for i in range(n):
            ok = terms + age[i] <= p.max_expiry_age
            term[i] = rng.choice(terms[ok], p=weights[ok] / weights[ok].sum())
        si = np.exp(rng.normal(np.log(p.sum_insured_median), p.sum_insured_sigma, n))
        si = np.round(np.clip(si, *p.sum_insured_bounds) / 5_000) * 5_000
        frames.append(pd.DataFrame({
            "issue_year": year, "issue_month": months, "channel": channel,
            "sex": np.where(rng.random(n) < p.male_share, "M", "F"),
            "issue_age": age, "term": term, "sum_insured": si,
        }))
    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "policy_id", [f"VT-{i:06d}" for i in range(1, len(df) + 1)])
    df["issue_date"] = _month_start(df["issue_year"], df["issue_month"])
    pricing = df.copy()
    pricing["mortality_factor"] = A.PRICING_VT["mortality_factor"]
    for year, factors in A.PRICING_VT_REPRICED.items():
        rows = (pricing["issue_year"] == year) & older_high_si(pricing)
        pricing.loc[rows, "mortality_factor"] = factors["older_high_si"]
    df["tariff_premium"] = price_term_life(pricing)
    df["annual_premium"] = np.round(df["tariff_premium"] * np.where(df["channel"] == "promo", 1 - p.promo_discount, 1.0), 2)
    df["age_band"] = _age_band(df["issue_age"])
    df["cell"] = "VT|T" + df["term"].astype(str) + "|" + df["age_band"] + "|" + df["channel"]
    df["older_high_si"] = older_high_si(df)
    return df


def _true_q(policies: pd.DataFrame, ages: np.ndarray, years: np.ndarray, segment_rule=None) -> np.ndarray:
    table = cso1980()
    base = np.where(policies["sex"].to_numpy() == "M", table["M"].to_numpy()[np.minimum(ages, 99)],
                    table["F"].to_numpy()[np.minimum(ages, 99)])
    seg = older_high_si(policies) if segment_rule is None else segment_rule
    years = np.asarray(years)
    factor = np.ones(len(years))
    for y in np.unique(years):
        f = A.MORTALITY_TRUE[int(y)]
        factor = np.where(years == y, np.where(seg, f["older_high_si"], f["default"]), factor)
    return np.clip(base * factor, 0, 1)


def _run_life_experience(rng, policies, lapse_table, monthly_lapse: bool, step=None):
    """Month-by-month survival of life policies from issue to 31 Dec 2025.

    Returns exit month index (or -1), exit reason and per-month in-force flags. ``step`` is an
    optional callback for account mechanics: step(month_index, active_mask, death_mask, lapse_mask).
    """
    n = len(policies)
    start = (policies["issue_year"].to_numpy() - A.START_YEAR) * 12 + policies["issue_month"].to_numpy() - 1
    term_m = policies["term"].to_numpy() * 12 if "term" in policies else np.full(n, 10_000)
    alive = np.zeros(n, bool)
    exit_month = np.full(n, -1)
    reason = np.full(n, "", dtype=object)
    lapse_table = np.asarray(lapse_table)
    for t in range((A.END_YEAR - A.START_YEAR + 1) * 12):
        alive |= start == t
        dur = t - start  # policy month index, 0 at issue
        active = alive & (dur >= 0) & (dur < term_m)
        year = A.START_YEAR + t // 12
        ages = policies["issue_age"].to_numpy() + np.maximum(dur, 0) // 12
        q = _true_q(policies, ages, np.full(n, year))
        die = active & (rng.random(n) < monthly_rate(q))
        pol_year = np.maximum(dur, 0) // 12 + 1
        rate = lapse_table[np.minimum(pol_year - 1, len(lapse_table) - 1)]
        if monthly_lapse:
            lapse = active & ~die & (rng.random(n) < monthly_rate(rate))
        else:
            at_anniv = ((dur + 1) % 12 == 0) & (dur + 1 < term_m)
            lapse = active & ~die & at_anniv & (rng.random(n) < rate)
        if step is not None:
            step(t, active, die, lapse)
        exit_month = np.where(die | lapse, t, exit_month)
        reason = np.where(die, "death", np.where(lapse, "lapse", reason))
        alive &= ~(die | lapse)
    return exit_month, reason


def _death_dates(rng, exit_month, mask):
    idx = np.where(mask)[0]
    month_start = _month_start(A.START_YEAR + exit_month[idx] // 12, exit_month[idx] % 12 + 1)
    days_in = np.floor(rng.random(len(idx)) * 28).astype(int)
    death = month_start + days_in.astype("timedelta64[D]")
    report = _add_months(death, rng.exponential(0.5, len(idx)))
    paid = report + np.full(len(idx), 15).astype("timedelta64[D]")
    return idx, death, report, paid


def simulate_term_life(rng) -> dict:
    pol = term_life_policies(rng)
    exit_month, reason = _run_life_experience(rng, pol, A.TERM_LIFE.lapse, monthly_lapse=False)
    pol["exit_reason"] = np.where(reason == "", "inforce", reason)
    exit_date = np.full(len(pol), np.datetime64("NaT", "D"), dtype="datetime64[D]")
    lapse = reason == "lapse"
    # a lapse takes effect at the anniversary that follows the last month in force
    exit_date[lapse] = _month_start(A.START_YEAR + (exit_month[lapse] + 1) // 12, (exit_month[lapse] + 1) % 12 + 1)
    idx, death, report, paid = _death_dates(rng, exit_month, reason == "death")
    exit_date[idx] = death
    pol["exit_date"] = exit_date

    rows = []
    issue = pol["issue_date"].to_numpy(dtype="datetime64[D]")
    end = np.where(np.isnat(exit_date), SIM_END, exit_date)
    for i in range(len(pol)):
        k = 0
        while True:
            due = (issue[i].astype("datetime64[M]") + np.timedelta64(12 * k, "M")).astype("datetime64[D]")
            if due > SIM_END or due >= end[i] or k >= pol.at[i, "term"]:
                break
            prem = pol.at[i, "annual_premium"]
            rate = A.TERM_LIFE.first_year_commission if k == 0 else A.TERM_LIFE.renewal_commission
            rows += [(pol.at[i, "policy_id"], due, "premium", prem),
                     (pol.at[i, "policy_id"], due, "commission", round(prem * rate, 2)),
                     (pol.at[i, "policy_id"], due, "premium_tax", round(prem * A.PREMIUM_TAX, 2))]
            k += 1
    tx = pd.DataFrame(rows, columns=["policy_id", "date", "type", "amount"])

    claims = pd.DataFrame({
        "claim_id": [f"VTC-{j:05d}" for j in range(1, len(idx) + 1)],
        "policy_id": pol["policy_id"].to_numpy()[idx],
        "occurrence_date": death, "report_date": report, "payment_date": paid,
        "amount": pol["sum_insured"].to_numpy()[idx],
        "claim_expense": np.round(A.TERM_LIFE.claim_cost * _inflation(death) * (1 + rng.normal(0, A.EXPENSE_NOISE, len(idx))), 2),
    })
    return {"vt_policies": pol, "vt_transactions": tx, "vt_claims": claims}


# --------------------------------------------------------------------------
# savings life (VA): universal life type B
# --------------------------------------------------------------------------
def savings_life_policies(rng) -> pd.DataFrame:
    p = A.SAVINGS_LIFE
    frames = []
    for year, total in p.new_policies.items():
        months = _issue_months(rng, total)
        n = len(months)
        prem = np.exp(rng.normal(np.log(p.annual_premium_median), p.annual_premium_sigma, n))
        prem = np.round(np.clip(prem, *p.annual_premium_bounds) / 10) * 10
        age = _triangular_ages(rng, p.issue_age_range[0], p.issue_age_mode, p.issue_age_range[1], n)
        frames.append(pd.DataFrame({
            "issue_year": year, "issue_month": months,
            "sex": np.where(rng.random(n) < p.male_share, "M", "F"),
            "issue_age": age, "annual_premium": prem,
            "sum_insured": np.maximum(np.round(prem * p.sum_insured_multiple / 1_000) * 1_000, p.min_sum_insured),
        }))
    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "policy_id", [f"VA-{i:06d}" for i in range(1, len(df) + 1)])
    df["issue_date"] = _month_start(df["issue_year"], df["issue_month"])
    df["term"] = p.maturity_age - df["issue_age"]
    df["age_band"] = _age_band(df["issue_age"])
    df["cell"] = "VA|" + df["age_band"]
    return df


def surrender_charge(policy_year) -> np.ndarray:
    sc = np.asarray(A.SAVINGS_LIFE.surrender_charge)
    y = np.asarray(policy_year)
    return np.where(y <= len(sc), sc[np.clip(y - 1, 0, len(sc) - 1)], 0.0)


def simulate_savings_life(rng) -> dict:
    p = A.SAVINGS_LIFE
    pol = savings_life_policies(rng)
    n = len(pol)
    start = (pol["issue_year"].to_numpy() - A.START_YEAR) * 12 + pol["issue_month"].to_numpy() - 1
    av = np.zeros(n)
    table = cso1980()
    sex_m = pol["sex"].to_numpy() == "M"
    rows, ledger, snapshots = [], [], []
    benefit = {}

    def step(t, active, die, lapse):
        nonlocal av
        dur = t - start
        year = A.START_YEAR + t // 12
        ages = np.minimum(pol["issue_age"].to_numpy() + np.maximum(dur, 0) // 12, 99)
        due = active & (dur % 12 == 0)
        prem = np.where(due, pol["annual_premium"].to_numpy(), 0.0)
        load = prem * p.premium_load
        q = np.where(sex_m, table["M"].to_numpy()[ages], table["F"].to_numpy()[ages]) * p.coi_table_factor
        coi = np.where(active, pol["sum_insured"].to_numpy() * q / 12, 0.0)
        admin = np.where(active, p.admin_fee_monthly, 0.0)
        opening = av.sum()
        av = av + prem - load - coi - admin
        interest = np.where(active, av * ((1 + p.declared_rate[year]) ** (1 / 12) - 1), 0.0)
        av = np.where(active, av + interest, av)
        pol_year = np.maximum(dur, 0) // 12 + 1
        sc_amt = av * surrender_charge(pol_year)
        out_death = np.where(die, av + pol["sum_insured"].to_numpy(), 0.0)
        out_surr = np.where(lapse, av - sc_amt, 0.0)
        for i in np.where(die)[0]:
            benefit[i] = (av[i], pol["sum_insured"].iat[i], sc_amt[i])
        ledger.append({
            "month": t, "premiums": prem.sum(), "premium_load": load.sum(), "coi": coi.sum(),
            "admin_fee": admin.sum(), "interest": interest.sum(), "opening": opening,
            "death_av": av[die].sum(), "surrender_av": av[lapse].sum(), "surrender_charge": sc_amt[lapse].sum(),
        })
        date = _month_start(year, t % 12 + 1)
        for i in np.where(due)[0]:
            rate = p.first_year_commission if dur[i] == 0 else p.renewal_commission
            rows.extend([(pol["policy_id"].iat[i], date, "premium", prem[i]),
                         (pol["policy_id"].iat[i], date, "commission", round(prem[i] * rate, 2)),
                         (pol["policy_id"].iat[i], date, "premium_tax", round(prem[i] * A.PREMIUM_TAX, 2))])
        month_end = (date.astype("datetime64[M]") + ONE_MONTH).astype("datetime64[D]") - ONE_DAY
        for i in np.where(lapse)[0]:
            rows.append((pol["policy_id"].iat[i], month_end, "surrender", round(out_surr[i], 2)))
        av = np.where(die | lapse, 0.0, av)
        if t % 12 == 11:
            alive_after = active & ~die & ~lapse
            snapshots.append(pd.DataFrame({
                "policy_id": pol["policy_id"].to_numpy()[alive_after], "closing": month_end,
                "account_value": np.round(av[alive_after], 2),
                "surrender_value": np.round(av[alive_after] * (1 - surrender_charge(pol_year[alive_after])), 2),
            }))

    exit_month, reason = _run_life_experience(rng, pol, p.lapse, monthly_lapse=True, step=step)
    pol["exit_reason"] = np.where(reason == "", "inforce", reason)
    exit_date = np.full(n, np.datetime64("NaT", "D"), dtype="datetime64[D]")
    sur = reason == "lapse"
    exit_date[sur] = (_month_start(A.START_YEAR + exit_month[sur] // 12, exit_month[sur] % 12 + 1).astype("datetime64[M]")
                      + ONE_MONTH).astype("datetime64[D]") - ONE_DAY
    idx, death, report, paid = _death_dates(rng, exit_month, reason == "death")
    exit_date[idx] = death
    pol["exit_date"] = exit_date
    pol.loc[sur, "exit_reason"] = "surrender"
    claims = pd.DataFrame({
        "claim_id": [f"VAC-{j:05d}" for j in range(1, len(idx) + 1)],
        "policy_id": pol["policy_id"].to_numpy()[idx],
        "occurrence_date": death, "report_date": report, "payment_date": paid,
        "account_value": [round(benefit[i][0], 2) for i in idx],
        "sum_insured": [benefit[i][1] for i in idx],
        "surrender_charge": [round(benefit[i][2], 2) for i in idx],
        "claim_expense": np.round(p.claim_cost * _inflation(death) * (1 + rng.normal(0, A.EXPENSE_NOISE, len(idx))), 2),
    })
    claims["amount"] = claims["account_value"] + claims["sum_insured"]
    ledger = pd.DataFrame(ledger)
    ledger.insert(0, "month_start", _month_start(A.START_YEAR + ledger["month"] // 12, ledger["month"] % 12 + 1))
    return {"va_policies": pol, "va_transactions": pd.DataFrame(rows, columns=["policy_id", "date", "type", "amount"]),
            "va_claims": claims, "va_account_ledger": ledger.drop(columns="month"),
            "va_account_values": pd.concat(snapshots, ignore_index=True)}


# --------------------------------------------------------------------------
# property and casualty
# --------------------------------------------------------------------------
def _pc_policies(rng, prefix, counts, premium_mean, extra=None) -> pd.DataFrame:
    frames = []
    for year, n in counts.items():
        day = rng.integers(0, 365 if year % 4 else 366, n)
        issue = np.datetime64(f"{year}-01-01") + day.astype("timedelta64[D]")
        prem = np.round(_lognormal(rng, premium_mean[year], A.PREMIUM_CV, n), 2)
        frames.append(pd.DataFrame({"issue_year": year, "issue_date": issue, "premium": prem}))
    df = pd.concat(frames, ignore_index=True).sort_values("issue_date", kind="stable").reset_index(drop=True)
    df.insert(0, "policy_id", [f"{prefix}-{i:06d}" for i in range(1, len(df) + 1)])
    if extra:
        for k, v in extra.items():
            df[k] = v
    return df


def _payment_dates_from_pattern(rng, occurrence, report, pattern: np.ndarray, size: int):
    """Payment dates for liability claims, following an industry paid pattern by accident year."""
    ay_start = occurrence.astype("datetime64[Y]").astype("datetime64[D]")
    k = rng.choice(len(pattern), size, p=pattern / pattern.sum())
    t = ay_start + np.round((k + rng.random(size)) * 365.25).astype("timedelta64[D]")
    late = _add_months(report, rng.exponential(1.0, size))
    return np.where(t < report, late, t)


def _claims_for(rng, policies, line, coverage, freq, sev_mean_fn, sev_cv, duration_months, report_mean,
                settle_mean=None, pattern=None, exposure="uniform"):
    counts = rng.poisson(freq * duration_months / 12, len(policies))
    pol_idx = np.repeat(np.arange(len(policies)), counts)
    m = len(pol_idx)
    u = rng.random(m)
    frac = np.sqrt(u) if exposure == "linear" else u  # exposure growing linearly for CAR
    occ = _add_months(policies["issue_date"].to_numpy(dtype="datetime64[D]")[pol_idx], frac * duration_months)
    keep = occ <= SIM_END
    pol_idx, occ = pol_idx[keep], occ[keep]
    m = len(pol_idx)
    mean = sev_mean_fn(policies.iloc[pol_idx], occ)
    ultimate = np.round(_lognormal(rng, mean, sev_cv, m), 2)
    report = _add_months(occ, rng.exponential(report_mean, m))
    claims = pd.DataFrame({
        "policy_id": policies["policy_id"].to_numpy()[pol_idx], "line": line, "coverage": coverage,
        "occurrence_date": occ, "report_date": report, "ultimate": ultimate,
    })
    if pattern is None:
        paid = _add_months(report, rng.exponential(settle_mean, m))
        pays = pd.DataFrame({"row": np.arange(m), "payment_date": paid, "amount": ultimate})
    else:
        n_pay = A.LIABILITY_PARTIAL_PAYMENTS
        shares = rng.dirichlet(np.ones(n_pay), m)
        dates = np.column_stack([_payment_dates_from_pattern(rng, occ, report, pattern, m) for _ in range(n_pay)])
        dates.sort(axis=1)
        amounts = np.round(shares * ultimate[:, None], 2)
        amounts[:, -1] = ultimate - amounts[:, :-1].sum(axis=1)
        pays = pd.DataFrame({"row": np.repeat(np.arange(m), n_pay), "payment_date": dates.ravel(), "amount": amounts.ravel()})
    return claims, pays


def _premium_schedule(policies, upfront_mask, commission, levy=0.0):
    """Premium instalments with the commission and taxes paid when each instalment is received."""
    n = len(policies)
    up = np.asarray(upfront_mask)
    reps = np.where(up, 1, 4)
    idx = np.repeat(np.arange(n), reps)
    k = np.concatenate([np.arange(r) for r in reps]) if n else np.array([], int)
    dates = add_calendar_months(policies["issue_date"].to_numpy(dtype="datetime64[D]")[idx], 3 * k)
    amount = np.round(policies["premium"].to_numpy()[idx] / reps[idx], 2)
    df = pd.DataFrame({"policy_id": policies["policy_id"].to_numpy()[idx], "date": dates, "premium": amount})
    df["commission"] = np.round(df["premium"] * commission, 2)
    df["premium_tax"] = np.round(df["premium"] * A.PREMIUM_TAX, 2)
    if levy:
        df["fire_levy"] = np.round(df["premium"] * levy, 2)
    return df


def simulate_motor(rng, pattern_table: pd.DataFrame) -> dict:
    pols, pays_all, claims_all, prem_all = [], [], [], []
    for seg, s in A.MOTOR.items():
        pol = _pc_policies(rng, "AUTO-P" if seg == "particulares" else "AUTO-F", s.policies, s.premium_mean,
                           {"line": "AUTO", "segment": seg})
        pol["instalments"] = np.where(rng.random(len(pol)) < A.MOTOR_UPFRONT_SHARE, 1, 4)
        pol["expiry_date"] = pol["issue_date"] + pd.DateOffset(years=1) - pd.Timedelta(days=1)
        pols.append(pol)
        prem_all.append(_premium_schedule(pol, pol["instalments"] == 1, A.MOTOR_COMMISSION))

        def pd_mean(p, occ, s=s):
            yf = _year_fraction(occ)
            shock = np.array([s.true_severity_shock_pd.get(int(y), 1.0) for y in np.floor(yf)])
            return s.severity_pd * (1 + s.severity_trend) ** (yf - A.START_YEAR) * shock

        def rc_mean(p, occ, s=s):
            return s.severity_rc * (1 + s.severity_trend) ** (_year_fraction(occ) - A.START_YEAR)

        pattern = pattern_table.query("line == @s.rc_pattern").sort_values("development_year")["incremental_paid"].to_numpy()
        for cov, freq, fn, cv, kw in (
            ("PD", s.frequency_pd, pd_mean, s.severity_cv_pd, {"settle_mean": A.SETTLEMENT_DELAY_MEAN["pd"]}),
            ("RC", s.frequency_rc, rc_mean, s.severity_cv_rc, {"pattern": pattern}),
        ):
            c, p = _claims_for(rng, pol, "AUTO", cov, freq, fn, cv, 12, A.REPORT_DELAY_MEAN[cov.lower()], **kw)
            c["segment"] = seg
            p["row"] += sum(len(x) for x in claims_all)
            claims_all.append(c)
            pays_all.append(p)
    return _finish_pc("AUTO", pols, claims_all, pays_all, prem_all)


def simulate_fire(rng) -> dict:
    f = A.FIRE
    pol = _pc_policies(rng, "INC", f["policies"], f["premium_mean"], {"line": "INC", "segment": "hogar_comercio", "instalments": 1})
    pol["expiry_date"] = pol["issue_date"] + pd.DateOffset(years=1) - pd.Timedelta(days=1)
    prem = _premium_schedule(pol, np.ones(len(pol), bool), f["commission"], levy=A.FIRE_LEVY)

    def mean(p, occ):
        return f["severity"] * (1 + f["severity_trend"]) ** (_year_fraction(occ) - A.START_YEAR)

    c, p = _claims_for(rng, pol, "INC", "FIRE", f["frequency"], mean, f["severity_cv"], 12, A.REPORT_DELAY_MEAN["fire"],
                       settle_mean=A.SETTLEMENT_DELAY_MEAN["fire"])
    c["segment"] = "hogar_comercio"
    claims, pays = [c], [p]
    for year in range(A.START_YEAR, A.END_YEAR + 1):  # catastrophe: one aggregate event at most per year
        if rng.random() < f["cat_probability"]:
            occ = np.datetime64(f"{year}-01-01") + np.timedelta64(int(rng.integers(0, 365)), "D")
            inforce = pol[(pol["issue_date"] <= occ) & (pol["expiry_date"] >= occ)]
            cat = pd.DataFrame({"policy_id": [inforce["policy_id"].iloc[0]], "line": "INC", "coverage": "CAT",
                                "occurrence_date": [occ], "report_date": [occ + np.timedelta64(7, "D")], "ultimate": [f["cat_loss"]],
                                "segment": "hogar_comercio"})
            p2 = pd.DataFrame({"row": [sum(len(x) for x in claims)], "payment_date": [occ + np.timedelta64(120, "D")], "amount": [f["cat_loss"]]})
            claims.append(cat)
            pays.append(p2)
    return _finish_pc("INC", [pol], claims, pays, [prem])


def simulate_car(rng) -> dict:
    c = A.CAR
    frames = []
    for year, n in c["projects"].items():
        day = rng.integers(0, 365, n)
        value = np.round(np.exp(rng.normal(np.log(c["contract_value_median"]), c["contract_value_sigma"], n)), -3)
        frames.append(pd.DataFrame({"issue_year": year, "issue_date": np.datetime64(f"{year}-01-01") + day.astype("timedelta64[D]"),
                                    "contract_value": value, "premium": np.round(value * c["premium_rate"], 2)}))
    pol = pd.concat(frames, ignore_index=True).sort_values("issue_date", kind="stable").reset_index(drop=True)
    pol.insert(0, "policy_id", [f"TRC-{i:04d}" for i in range(1, len(pol) + 1)])
    pol["line"], pol["segment"], pol["instalments"] = "TRC", "construccion", 1
    pol["expiry_date"] = pol["issue_date"] + pd.DateOffset(months=c["duration_months"]) - pd.Timedelta(days=1)
    prem = _premium_schedule(pol, np.ones(len(pol), bool), c["commission"])

    def mean(p, occ):
        return c["expected_loss_ratio"] * p["premium"].to_numpy() / c["claims_per_project"]

    cl, pays = _claims_for(rng, pol, "TRC", "CAR", c["claims_per_project"] * 12 / c["duration_months"], mean,
                           c["severity_cv"], c["duration_months"], A.REPORT_DELAY_MEAN["car"],
                           settle_mean=A.SETTLEMENT_DELAY_MEAN["car"], exposure="linear")
    cl["segment"] = "construccion"
    return _finish_pc("TRC", [pol], [cl], [pays], [prem])


def _finish_pc(line, pols, claims, pays, prems) -> dict:
    pol = pd.concat(pols, ignore_index=True)
    cl = pd.concat(claims, ignore_index=True)
    cl = cl.sort_values(["occurrence_date", "policy_id"], kind="stable")
    order = cl.index.to_numpy()
    new_id = {old: f"{line}C-{i:06d}" for i, old in enumerate(order, start=1)}
    cl = cl.reset_index(drop=True)
    cl.insert(0, "claim_id", [new_id[o] for o in order])
    pay = pd.concat(pays, ignore_index=True)
    pay.insert(0, "claim_id", pay.pop("row").map(new_id))
    pay = pay.sort_values(["claim_id", "payment_date"], kind="stable").reset_index(drop=True)
    return {f"{line.lower()}_policies": pol, f"{line.lower()}_premiums": pd.concat(prems, ignore_index=True),
            f"{line.lower()}_claims": cl, f"{line.lower()}_payments": pay}


def case_reserves(rng, claims: pd.DataFrame, payments: pd.DataFrame, closings=A.CLOSINGS) -> pd.DataFrame:
    """Claims-handler estimate of the outstanding amount of each open reported claim at each closing."""
    out = []
    for closing in closings:
        c = np.datetime64(closing)
        open_ = claims[(claims["report_date"] <= c)]
        paid = payments[payments["payment_date"] <= c].groupby("claim_id")["amount"].sum()
        remaining = open_["ultimate"].to_numpy() - open_["claim_id"].map(paid).fillna(0.0).to_numpy()
        is_open = remaining > 0.005
        sigma = A.CASE_RESERVE_NOISE
        noise = rng.lognormal(-sigma**2 / 2, sigma, is_open.sum())
        out.append(pd.DataFrame({"claim_id": open_["claim_id"].to_numpy()[is_open], "closing": c,
                                 "case_reserve": np.round(remaining[is_open] * noise, 2)}))
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------
# expenses (other than commissions and premium taxes, which sit with the premiums)
# --------------------------------------------------------------------------
def simulate_expenses(rng, out: dict) -> pd.DataFrame:
    months = pd.period_range(f"{A.START_YEAR}-01", f"{A.END_YEAR}-12", freq="M")
    rows = []

    def noise():
        return 1 + rng.normal(0, A.EXPENSE_NOISE)

    for prod, pols, prm in (("VT", out["vt_policies"], A.TERM_LIFE), ("VA", out["va_policies"], A.SAVINGS_LIFE)):
        issue = pols["issue_date"].dt.to_period("M")
        exit_ = pd.to_datetime(pols["exit_date"]).dt.to_period("M")
        for m in months:
            infl = (1 + A.EXPENSE_INFLATION) ** ((m.year - A.START_YEAR) + (m.month - 1) / 12)
            new = int((issue == m).sum())
            inforce = int(((issue <= m) & (exit_.isna() | (exit_ >= m))).sum())
            rows.append((prod, m, "acquisition_underwriting", round(new * prm.underwriting_cost * infl * noise(), 2)))
            rows.append((prod, m, "maintenance", round(inforce * prm.maintenance_cost / 12 * infl * noise(), 2)))
    for line, admin in (("auto", A.MOTOR_ADMIN), ("inc", A.FIRE["admin"]), ("trc", A.CAR["admin"])):
        pol = out[f"{line}_policies"]
        start = pol["issue_date"].to_numpy(dtype="datetime64[D]")
        end = pol["expiry_date"].to_numpy(dtype="datetime64[D]") + ONE_DAY
        span = (end - start).astype(int)
        for m in months:
            ms, me = np.datetime64(m.start_time.date(), "D"), np.datetime64(m.end_time.date(), "D") + ONE_DAY
            days = np.maximum((np.minimum(end, me) - np.maximum(start, ms)).astype(int), 0)
            earned = float((pol["premium"].to_numpy() * days / span).sum())
            rows.append((line.upper(), m, "maintenance_and_claims_handling", round(earned * admin * noise(), 2)))
    base = 1_200_000 / 12
    for m in months:
        infl = (1 + A.EXPENSE_INFLATION) ** ((m.year - A.START_YEAR) + (m.month - 1) / 12)
        rows.append(("ENTITY", m, "non_attributable_overhead", round(base * infl * noise(), 2)))
    df = pd.DataFrame(rows, columns=["portfolio", "month", "type", "amount"])
    df["month"] = df["month"].astype(str)
    return df


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def simulate_all(seed: int = A.SEED) -> dict:
    rngs = _streams(seed, ["vt", "va", "auto", "inc", "trc", "case", "expenses"])
    patterns = pd.read_csv(PATTERNS)
    out = {}
    out.update(simulate_term_life(rngs["vt"]))
    out.update(simulate_savings_life(rngs["va"]))
    out.update(simulate_motor(rngs["auto"], patterns))
    out.update(simulate_fire(rngs["inc"]))
    out.update(simulate_car(rngs["trc"]))
    for line in ("auto", "inc", "trc"):
        out[f"{line}_case_reserves"] = case_reserves(rngs["case"], out[f"{line}_claims"], out[f"{line}_payments"])
    out["expenses"] = simulate_expenses(rngs["expenses"], out)
    return out


def write(out: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in out.items():
        df.to_csv(folder / f"{name}.csv", index=False, date_format="%Y-%m-%d")
