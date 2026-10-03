"""Illiquidity-premium settings for the bottom-up discount rates (IFRS 17 B79-B80).

The premium is computed maturity by maturity in ``treasury_curves``:

    premium(t) = max(0, HQM(t) - TNC(t)) x (1 - credit_share) x application_ratio

Policy chosen by the project owner (2 Oct 2026): use the HQM curve as it is,
i.e. ``credit_share = 0`` and ``application_ratio = 1`` for every portfolio,
so the discount curve equals HQM. The alternatives below stay available as
options and as sensitivities to disclose (IFRS 17 par. 117(c)(iii), 120, 128).

How the credit share is estimated (for future reviews)
------------------------------------------------------
IFRS 17 does not prescribe a percentage (B78). It asks to maximise observable
inputs (B78(a)), to exclude credit risk from the curve (B79; B84(b) by analogy)
and points to credit-derivative prices as a reference (B85). The procedure:

1. Credit share from CDS evidence. For each rating r in the HQM universe
   (AAA, AA, A), the default component of the spread is the CDS premium
   divided by the bond spread over Treasuries. Longstaff, Mithal and Neis
   (2005, Journal of Finance 60(5)) measured 51% for AAA/AA and 56% for A.
   Weight by the rating mix of the HQM bond sample:
       credit_share = sum_r weight_r x default_share_r
   ``credit_share_from_cds`` implements this; with an A-heavy mix the result
   is about 55%.
2. Expected-loss floor. The deduction must at least cover the expected loss
   of an A-rated bond: annual default probability x loss given default
   (public long-term default studies). ``expected_loss_floor`` returns the
   minimum credit share = expected loss / spread; use the larger of 1 and 2.
3. Consistency. Apply the same share at every closing unless new evidence
   arrives (B54-B55), and recheck it at least once a year with updated CDS
   and default data.
4. Disclosure. Describe the method (par. 117(c)(iii)), show the curves
   (par. 120) and the sensitivity of the liabilities to the share (par. 128).
"""

from __future__ import annotations

# Chosen policy: discount at the HQM curve (no credit deduction, same for all portfolios)
CREDIT_SHARE = 0.0

# Alternative kept as an option and disclosed as a sensitivity
CREDIT_SHARE_CDS = 0.55  # Longstaff, Mithal and Neis (2005), A-heavy AAA-A mix

# CDS-based default share of the spread over Treasuries (LMN 2005, Table)
LMN_DEFAULT_SHARE = {"AAA/AA": 0.51, "A": 0.56}

# Liquidity buckets: chosen policy applies 100% everywhere; the graded set is an option
APPLICATION_RATIO = {"high": 1.00, "medium": 1.00, "low": 1.00}
APPLICATION_RATIO_BY_LIQUIDITY = {"high": 1.00, "medium": 0.75, "low": 0.50}

PORTFOLIO_LIQUIDITY = {
    "VT": "high",  # term life: no surrender value
    "RE_VT": "high",  # reinsurance held on term life (consistent with VT, par. 63)
    "AUTO": "medium",
    "INC": "medium",
    "TRC": "medium",
    "VA": "low",  # savings life: policyholder can surrender at any time
}


def application_ratio(portfolio: str, ratios: dict | None = None) -> float:
    """Share of the net premium applied to a portfolio, by its liquidity bucket."""
    ratios = APPLICATION_RATIO if ratios is None else ratios
    return ratios[PORTFOLIO_LIQUIDITY[portfolio]]


def credit_share_from_cds(rating_weights: dict[str, float], default_share: dict[str, float] | None = None) -> float:
    """Step 1: weighted CDS-based default share of the spread for a rating mix,
    e.g. {"AAA/AA": 0.2, "A": 0.8} -> 0.55."""
    default_share = LMN_DEFAULT_SHARE if default_share is None else default_share
    total = sum(rating_weights.values())
    if total <= 0 or any(w < 0 for w in rating_weights.values()):
        raise ValueError("rating weights must be non-negative and not all zero")
    return sum(w * default_share[r] for r, w in rating_weights.items()) / total


def expected_loss_floor(annual_default_probability: float, loss_given_default: float, spread: float) -> float:
    """Step 2: minimum credit share so that the expected loss is never left in the rate."""
    if spread <= 0:
        raise ValueError("spread must be positive")
    return min(1.0, annual_default_probability * loss_given_default / spread)
