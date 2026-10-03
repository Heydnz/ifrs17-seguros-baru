"""Risk adjustment for non-financial risk (IFRS 17 par. 37, B86-B92; memo section 10).

Life (term and savings life): cost of capital.

    RA = CoC x sum_k SCR_k / 12 x D(k + 1)        (monthly steps, 6% a year)

* SCR_0 is the one-year 99.5% capital for non-financial risks at the valuation date:
  the increase in the best-estimate liability (PV of outflows minus inflows) under each
  instantaneous, permanent shock, aggregated with a correlation matrix in the spirit of
  the Solvency II standard formula (life module):

      mortality +15%, lapse +50% or -50% (the worse), expenses +10% and inflation +1 pp

* SCR_k runs off with the expected sum insured in force (the coverage units), a common
  driver-based simplification that keeps capital proportional to the risk still covered.
* Only insurance, lapse and expense risk enter; operational risk is excluded (B89).

P&C (motor, fire/home, CAR): confidence level. The PV of the claims is lognormal with the
line's coefficient of variation, and the risk adjustment is the 75th percentile minus the
mean (par. 119 discloses the level).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from .life import TermBasis, project_term

COST_OF_CAPITAL = 0.06
CONFIDENCE_PC = 0.75

LIFE_SHOCKS = {"mortality": 0.15, "lapse": 0.50, "expense": 0.10, "inflation": 0.01}
# Correlations between life risks (Solvency II Delegated Regulation 2015/35, Annex IV, life module)
LIFE_CORRELATION = {
    ("mortality", "lapse"): 0.0,
    ("mortality", "expense"): 0.25,
    ("lapse", "expense"): 0.5,
}
LIFE_RISKS = ("mortality", "lapse", "expense")


def correlation_matrix(risks=LIFE_RISKS, pairs=LIFE_CORRELATION) -> np.ndarray:
    m = np.eye(len(risks))
    for i, a in enumerate(risks):
        for j, b in enumerate(risks):
            if i != j:
                m[i, j] = pairs.get((a, b), pairs.get((b, a), 0.0))
    return m


def aggregate(shocks: np.ndarray, corr: np.ndarray | None = None) -> np.ndarray:
    """sqrt(s' C s) row by row; ``shocks`` has one column per risk in LIFE_RISKS order."""
    corr = correlation_matrix() if corr is None else corr
    s = np.atleast_2d(shocks)
    return np.sqrt(np.einsum("ni,ij,nj->n", s, corr, s))


@dataclass
class LifeRiskAdjustment:
    policy_id: np.ndarray
    shocks: np.ndarray  # (n, 3) undiversified capital by risk at the valuation date
    runoff_pv: np.ndarray  # (n,) sum_k CU_k / CU_0 / 12 x D(k + 1)

    def by_policy(self, cost_of_capital: float = COST_OF_CAPITAL) -> np.ndarray:
        return cost_of_capital * aggregate(self.shocks) * self.runoff_pv

    def for_group(self, mask=None, cost_of_capital: float = COST_OF_CAPITAL) -> float:
        """Risk adjustment of a set of policies, diversified across policies and risks.

        The capital of the set is the correlation-aggregate of its summed shocks, run off with
        the set's own coverage-unit weighted pattern.
        """
        mask = np.ones(len(self.policy_id), bool) if mask is None else np.asarray(mask)
        s = self.shocks[mask]
        if not len(s):
            return 0.0
        scr0 = float(aggregate(s.sum(axis=0))[0])
        weights = aggregate(s)
        runoff = float(np.average(self.runoff_pv[mask], weights=weights)) if weights.sum() > 0 else 0.0
        return cost_of_capital * scr0 * runoff


def term_life_risk_adjustment(policies, basis: TermBasis, discount, elapsed=0) -> LifeRiskAdjustment:
    """Shocked minus base best-estimate liability for each policy, and the run-off factor."""
    base_proj = project_term(policies, basis, elapsed)
    base = base_proj.present_values(discount)["net_outflow"].to_numpy()

    def bel(**kw):
        return project_term(policies, basis.stressed(**kw), elapsed).present_values(discount)["net_outflow"].to_numpy()

    mort = np.maximum(bel(mortality_multiplier=basis.mortality_multiplier * (1 + LIFE_SHOCKS["mortality"])) - base, 0.0)
    lapse_up = bel(lapse_multiplier=basis.lapse_multiplier * (1 + LIFE_SHOCKS["lapse"])) - base
    lapse_down = bel(lapse_multiplier=basis.lapse_multiplier * (1 - LIFE_SHOCKS["lapse"])) - base
    lapse = np.maximum(np.maximum(lapse_up, lapse_down), 0.0)
    expense = np.maximum(bel(expense_multiplier=basis.expense_multiplier * (1 + LIFE_SHOCKS["expense"]),
                             expense_inflation=basis.expense_inflation + LIFE_SHOCKS["inflation"]) - base, 0.0)

    cu = base_proj.coverage_units
    k = np.arange(base_proj.months)
    d_end = np.asarray(discount((k + 1) / 12.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = np.where(cu[:, :1] > 0, cu / cu[:, :1], 0.0)
    runoff = rel @ d_end / 12.0
    return LifeRiskAdjustment(base_proj.policy_id, np.column_stack([mort, lapse, expense]), runoff)


def lognormal_confidence_margin(mean, cv, level: float = CONFIDENCE_PC):
    """Percentile minus mean of a lognormal with the given mean and coefficient of variation."""
    mean, cv = np.asarray(mean, float), np.asarray(cv, float)
    sigma = np.sqrt(np.log1p(cv**2))
    mu = np.log(np.where(mean > 0, mean, 1.0)) - sigma**2 / 2
    return np.where(mean > 0, np.exp(mu + sigma * norm.ppf(level)) - mean, 0.0)


def equivalent_confidence_level(ra: float, std: float) -> float:
    """Normal-approximation confidence level implied by a risk adjustment (par. 119)."""
    return float(norm.cdf(ra / std)) if std > 0 else 1.0
