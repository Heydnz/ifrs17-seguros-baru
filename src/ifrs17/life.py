"""Monthly cash-flow projection and pricing for term life (IFRS 17 par. 33-35, B61-B66).

One projection serves three purposes: pricing at issue (with the pricing basis),
classifying groups at inception, and measuring the fulfilment cash flows at each
closing (with the best-estimate basis of that closing).

Conventions
-----------
* Month ``k`` of a projection runs from time ``k`` to ``k + 1`` (in months from the
  projection start). Policies are issued on the first day of a month.
* Premiums are annual, due at each policy anniversary while the policy is in force;
  commissions, premium tax and maintenance are paid with them or monthly at time ``k``.
* Deaths happen mid-month and are paid ``claim_payment_lag`` months later, so death
  claims of month ``k`` are discounted at time ``k + 0.5 + lag``.
* Lapses happen at the anniversary, when the next premium is not paid.
* Coverage units are the sum insured in force at the start of each month (B119).
* The ``elapsed`` months shift the projection to a valuation date: the result is the
  expected cash flow of a policy that is in force at that date (B61-B62).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from . import assumptions as A
from .mortality import BASE_YEAR, MAX_AGE, cso1980, monthly_rate


@dataclass(frozen=True)
class TermBasis:
    """Assumptions for one projection. The multipliers exist for stresses and sensitivities."""

    mortality_factor: float = A.MORTALITY_FACTOR  # used when the policies carry no own factor
    improvement: float = A.MORTALITY_IMPROVEMENT
    lapse: tuple = A.TERM_LIFE.lapse
    mortality_multiplier: float = 1.0
    lapse_multiplier: float = 1.0
    expense_multiplier: float = 1.0
    expense_inflation: float = A.EXPENSE_INFLATION
    first_year_commission: float = A.TERM_LIFE.first_year_commission
    renewal_commission: float = A.TERM_LIFE.renewal_commission
    premium_tax: float = A.PREMIUM_TAX
    underwriting_cost: float = A.TERM_LIFE.underwriting_cost
    maintenance_cost: float = A.TERM_LIFE.maintenance_cost
    claim_cost: float = A.TERM_LIFE.claim_cost
    claim_payment_lag: float = A.TERM_LIFE.claim_payment_lag

    def stressed(self, **kwargs) -> "TermBasis":
        return replace(self, **kwargs)


BEST_ESTIMATE = TermBasis()
PRICING = TermBasis(mortality_factor=A.PRICING_VT["mortality_factor"], improvement=A.PRICING_VT["improvement"])

CASH_FLOW_ITEMS = ("premiums", "commissions", "premium_tax", "underwriting", "maintenance", "claims")


@dataclass
class TermProjection:
    """Expected cash flows per policy (rows) and projection month (columns)."""

    policy_id: np.ndarray
    inforce: np.ndarray
    deaths: np.ndarray
    lapses: np.ndarray
    premiums: np.ndarray
    commissions: np.ndarray
    premium_tax: np.ndarray
    underwriting: np.ndarray
    maintenance: np.ndarray
    claims: np.ndarray
    coverage_units: np.ndarray
    claim_time_offset: float
    benefits: np.ndarray = None  # death benefits only (sum insured), the part a quota share cedes

    @property
    def months(self) -> int:
        return self.inforce.shape[1]

    def times(self, item: str) -> np.ndarray:
        """Payment time in months from the projection start for each column."""
        k = np.arange(self.months, dtype=float)
        return k + self.claim_time_offset if item == "claims" else k

    def present_values(self, discount) -> pd.DataFrame:
        """PV per policy of each cash-flow item; ``discount`` maps years to discount factors."""
        out = {"policy_id": self.policy_id}
        for item in CASH_FLOW_ITEMS:
            out[item] = getattr(self, item) @ np.asarray(discount(self.times(item) / 12.0))
        df = pd.DataFrame(out)
        df["outflows"] = df[["commissions", "premium_tax", "underwriting", "maintenance", "claims"]].sum(axis=1)
        df["net_outflow"] = df["outflows"] - df["premiums"]
        return df

    def totals(self) -> pd.DataFrame:
        """Expected cash flows summed over policies, one row per projection month."""
        data = {item: getattr(self, item).sum(axis=0) for item in CASH_FLOW_ITEMS}
        data.update(inforce=self.inforce.sum(axis=0), deaths=self.deaths.sum(axis=0),
                    lapses=self.lapses.sum(axis=0), coverage_units=self.coverage_units.sum(axis=0))
        return pd.DataFrame(data).rename_axis("month")


def flat_discount(annual_rate: float):
    return lambda t_years: (1.0 + annual_rate) ** (-np.asarray(t_years, dtype=float))


def older_high_si(policies: pd.DataFrame) -> np.ndarray:
    rule = A.OLDER_HIGH_SI
    return ((policies["issue_age"] >= rule["min_issue_age"]) & (policies["sum_insured"] >= rule["min_sum_insured"])).to_numpy()


def segment_mortality_factor(policies: pd.DataFrame, factors: dict) -> np.ndarray:
    """Factor on CSO 1980 for each policy, from {'default': f, 'older_high_si': g}."""
    return np.where(older_high_si(policies), factors["older_high_si"], factors["default"])


def project_term(policies: pd.DataFrame, basis: TermBasis = BEST_ESTIMATE, elapsed=0,
                 annual_premium=None) -> TermProjection:
    """Project expected monthly cash flows for term-life policies.

    ``policies`` needs: issue_age, sex ('M'/'F'), term (years), sum_insured, issue_year,
    issue_month and, unless ``annual_premium`` is given, annual_premium. An optional
    ``mortality_factor`` column overrides the basis factor policy by policy. ``elapsed``
    (scalar or per policy) is the number of whole months already run at the valuation date.
    """
    n = len(policies)
    e = np.broadcast_to(np.asarray(elapsed, dtype=int), (n,))
    term_m = policies["term"].to_numpy(dtype=int) * 12
    remaining = term_m - e
    if (remaining < 0).any():
        raise ValueError("elapsed beyond the policy term")
    horizon = int(remaining.max()) if n else 0
    k = np.arange(horizon)
    m_abs = e[:, None] + k[None, :]
    active = k[None, :] < remaining[:, None]

    issue_age = policies["issue_age"].to_numpy(dtype=int)
    age = np.minimum(issue_age[:, None] + m_abs // 12, MAX_AGE)
    cal_index = (policies["issue_year"].to_numpy(dtype=int) - BASE_YEAR)[:, None] * 12 \
        + (policies["issue_month"].to_numpy(dtype=int) - 1)[:, None] + m_abs
    cal_years = cal_index // 12

    table = cso1980()
    base_q = np.where(policies["sex"].to_numpy()[:, None] == "M", table["M"].to_numpy()[age], table["F"].to_numpy()[age])
    factor = policies["mortality_factor"].to_numpy(float) if "mortality_factor" in policies else np.full(n, basis.mortality_factor)
    q = base_q * factor[:, None] * basis.mortality_multiplier * (1.0 - basis.improvement) ** np.maximum(cal_years, 0)
    q = np.where(age >= MAX_AGE, 1.0, np.clip(q, 0.0, 1.0))
    qm = np.where(active, monthly_rate(q), 0.0)

    policy_year = m_abs // 12 + 1
    lapse_table = np.asarray(basis.lapse, dtype=float)
    lapse_rate = lapse_table[np.minimum(policy_year - 1, len(lapse_table) - 1)] * basis.lapse_multiplier
    anniversary_next = ((m_abs + 1) % 12 == 0) & ((m_abs + 1) < term_m[:, None])
    lapse_rate = np.where(anniversary_next & active, np.clip(lapse_rate, 0.0, 1.0), 0.0)

    survive = (1.0 - qm) * (1.0 - lapse_rate)
    inforce = np.concatenate([np.ones((n, 1)), np.cumprod(survive, axis=1)[:, :-1]], axis=1) if horizon else np.zeros((n, 0))
    inforce = np.where(active, inforce, 0.0)
    deaths = inforce * qm
    lapses = inforce * (1.0 - qm) * lapse_rate

    premium = policies["annual_premium"].to_numpy(float) if annual_premium is None else np.broadcast_to(np.asarray(annual_premium, float), (n,))
    due = (m_abs % 12 == 0) & active
    premiums = np.where(due, inforce * premium[:, None], 0.0)
    commission_rate = np.where(policy_year == 1, basis.first_year_commission, basis.renewal_commission)
    inflation = (1.0 + basis.expense_inflation) ** (np.maximum(cal_index, 0) / 12.0)
    underwriting = np.where(m_abs == 0, basis.underwriting_cost * basis.expense_multiplier * inflation, 0.0) * inforce
    maintenance = inforce * basis.maintenance_cost / 12.0 * inflation * basis.expense_multiplier
    claims = deaths * (policies["sum_insured"].to_numpy(float)[:, None] + basis.claim_cost * inflation * basis.expense_multiplier)

    return TermProjection(
        policy_id=policies["policy_id"].to_numpy() if "policy_id" in policies else np.arange(n),
        inforce=inforce, deaths=deaths, lapses=lapses, premiums=premiums,
        commissions=premiums * commission_rate, premium_tax=premiums * basis.premium_tax,
        underwriting=underwriting, maintenance=maintenance, claims=claims,
        coverage_units=inforce * policies["sum_insured"].to_numpy(float)[:, None],
        claim_time_offset=0.5 + basis.claim_payment_lag,
        benefits=deaths * policies["sum_insured"].to_numpy(float)[:, None],
    )


def pricing_margin(policies: pd.DataFrame, margins: dict = A.PRICING_VT["profit_margin"]) -> np.ndarray:
    return np.where(policies["issue_age"].to_numpy() >= 50, margins["50_plus"], margins["under_50"])


def price_term_life(policies: pd.DataFrame, basis: TermBasis = PRICING, interest: float = A.PRICING_VT["interest"],
                    profit_margin=None) -> np.ndarray:
    """Level annual premium (tariff) for each policy, rounded to cents.

    Solves PV(P x (1 - commission rate - premium tax - margin)) = PV(claims + underwriting + maintenance).
    ``profit_margin`` is a share of each premium, scalar or per policy (default: by issue age).
    """
    profit_margin = pricing_margin(policies) if profit_margin is None else np.asarray(profit_margin, float)
    unit = project_term(policies, basis, elapsed=0, annual_premium=1.0)
    pv = unit.present_values(flat_discount(interest))
    net_income_per_unit = pv["premiums"] - pv["commissions"] - pv["premium_tax"] - profit_margin * pv["premiums"]
    fixed = pv["claims"] + pv["underwriting"] + pv["maintenance"]
    return np.round((fixed / net_income_per_unit).to_numpy(), 2)
