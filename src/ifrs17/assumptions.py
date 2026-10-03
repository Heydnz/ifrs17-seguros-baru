"""Central assumptions for Seguros Baru (memo sections 4, 9 and 12).

Three kinds of numbers live here and must not be confused:

* PRICING: the basis used to set premiums at issue. It fixes the premiums only.
* EXPECTED / BEST ESTIMATE: the unbiased valuation assumptions (IFRS 17 par. 33,
  B37-B57). At inception they equal the "expected" parameters below; they change
  at later closings only through the evidence described in memo section 12.
* TRUE: what the simulator uses to generate "actual" experience. The valuation
  never reads these; it only sees the simulated policies, claims and payments.

All money in USD. Rates are annual unless the name says otherwise. Every number is
synthetic: no client data and no real insurer's assumptions are used.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEED = 20230101
START_YEAR, END_YEAR = 2023, 2025
CLOSINGS = ("2023-12-31", "2024-12-31", "2025-12-31")

EXPENSE_INFLATION = 0.025  # the entity's own expectation, not a financial assumption (B128(b))
PREMIUM_TAX = 0.02  # Law 59 of 1996 art. 33, borne by the insurer (B65(i))
FIRE_LEVY = 0.05  # additional 5% on fire premiums for the fire brigade (B65(i))
NON_ATTRIBUTABLE_OVERHEAD_SHARE = 0.20  # expensed outside the insurance service result (B66(d))


# --------------------------------------------------------------------------
# Life: term life (VT) and savings life (VA)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TermLife:
    new_policies: dict = field(default_factory=lambda: {2023: 3000, 2024: 3000, 2025: 3000})
    channel_mix: dict = field(default_factory=lambda: {
        2023: {"agentes": 0.65, "bancaseguros": 0.20, "promo": 0.15},
        2024: {"agentes": 0.65, "bancaseguros": 0.20, "promo": 0.15},
        2025: {"agentes": 0.70, "bancaseguros": 0.30, "promo": 0.00},  # the promotion ends in 2025
    })
    male_share: float = 0.60
    issue_age_range: tuple = (25, 60)
    issue_age_mode: int = 40
    term_mix: dict = field(default_factory=lambda: {10: 0.30, 15: 0.30, 20: 0.40})
    max_expiry_age: int = 75
    sum_insured_median: float = 150_000
    sum_insured_sigma: float = 0.6
    sum_insured_bounds: tuple = (50_000, 500_000)
    promo_discount: float = 0.20
    first_year_commission: float = 0.50
    renewal_commission: float = 0.05
    underwriting_cost: float = 150.0  # per policy at issue
    maintenance_cost: float = 40.0  # per policy per year, 2023 money
    claim_cost: float = 200.0  # per death claim, 2023 money
    lapse: tuple = (0.08, 0.06, 0.04)  # by policy year; the last value applies thereafter
    claim_payment_lag: float = 1.0  # months from death to payment, on average


@dataclass(frozen=True)
class SavingsLife:
    new_policies: dict = field(default_factory=lambda: {2023: 1500, 2024: 1500, 2025: 1500})
    male_share: float = 0.55
    issue_age_range: tuple = (25, 55)
    issue_age_mode: int = 38
    maturity_age: int = 65
    annual_premium_median: float = 2_650  # mean of about USD 3,000 (memo section 4)
    annual_premium_sigma: float = 0.5
    annual_premium_bounds: tuple = (600, 20_000)
    sum_insured_multiple: float = 10.0  # death benefit = sum insured + account value (type B)
    min_sum_insured: float = 25_000
    premium_load: float = 0.05
    admin_fee_monthly: float = 5.0
    coi_table_factor: float = 1.00  # cost-of-insurance charges use 100% of CSO 1980
    surrender_charge: tuple = (0.08, 0.06, 0.04, 0.02, 0.01)  # policy years 1-5
    guaranteed_rate: float = 0.025
    # Commitment specified at inception (B98-B100): each 1 January the entity credits the
    # one-year HQM rate at the previous month end less a 1.25% spread, never below the 2.5%
    # guarantee, rounded to 0.05%. 2023 uses the January 2023 curve (the product's launch).
    crediting_spread: float = 0.0125
    declared_rate: dict = field(default_factory=lambda: {2023: 0.0370, 2024: 0.0395, 2025: 0.0340})
    first_year_commission: float = 0.40
    renewal_commission: float = 0.03
    underwriting_cost: float = 120.0
    maintenance_cost: float = 60.0
    claim_cost: float = 200.0
    lapse: tuple = (0.10, 0.08, 0.07, 0.06, 0.05, 0.07, 0.04)  # spike in year 6, when the surrender charge ends


TERM_LIFE = TermLife()
SAVINGS_LIFE = SavingsLife()

# Pricing basis for term life. The level annual premium makes the present value of premiums,
# net of commissions, premium tax and the profit margin, equal to the present value of
# claims and expenses at these assumptions. Issue ages 50 and over carry a thinner margin
# because the bank channel competes hard for them. With these values the promotional
# channel is onerous at inception and issue ages 50+ fall in the "remaining" group
# (memo section 6); see notebooks/02 for the calibration.
PRICING_VT = {"mortality_factor": 0.80, "improvement": 0.0, "interest": 0.045,
              "profit_margin": {"under_50": 0.10, "50_plus": 0.03}}
# After the 2024 mortality study the tariff for issue ages 50+ with high sums insured is
# repriced from January 2025 (memo section 12), so the 2025 cohort has no onerous group.
PRICING_VT_REPRICED = {2025: {"older_high_si": 1.20}}

# Best-estimate mortality at inception: 75% of CSO 1980 with 1% annual improvement (memo s9).
MORTALITY_FACTOR = 0.75
MORTALITY_IMPROVEMENT = 0.01
OLDER_HIGH_SI = {"min_issue_age": 50, "min_sum_insured": 250_000}

# Mortality studies received at each closing from the reinsurer, expressed as a factor on
# CSO 1980. A new insurer has too few deaths for its own experience to be credible, so the
# best estimate blends its own actual/expected with this external evidence (B41(c), B56-B57).
# The 2024 study shows worse mortality for older lives with high sums insured; the 2025 study
# shows that part of it was temporary (memo section 12).
MORTALITY_EXTERNAL_STUDY = {
    "2023-12-31": {"default": 0.75, "older_high_si": 0.75},
    "2024-12-31": {"default": 0.75, "older_high_si": 1.15},
    "2025-12-31": {"default": 0.75, "older_high_si": 0.85},
}
FULL_CREDIBILITY_DEATHS = 1_082  # limited-fluctuation standard: 90% probability within 5%

# "True" mortality used by the simulator (factor on CSO 1980, by calendar year).
MORTALITY_TRUE = {
    2023: {"default": 0.75, "older_high_si": 0.80},
    2024: {"default": 0.75, "older_high_si": 1.30},
    2025: {"default": 0.75, "older_high_si": 0.90},
}


# --------------------------------------------------------------------------
# Property and casualty
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MotorSegment:
    policies: dict
    premium_mean: dict  # by issue year
    frequency_pd: float  # own damage claims per policy-year
    frequency_rc: float  # liability claims per policy-year
    severity_pd: float  # mean, 2023 money
    severity_rc: float
    severity_cv_pd: float = 1.0
    severity_cv_rc: float = 2.0
    severity_trend: float = 0.03  # the entity's own expectation of claims inflation (B128(b))
    true_severity_shock_pd: dict = field(default_factory=dict)  # TRUE only, by occurrence year
    rc_pattern: str = "ppauto"


MOTOR = {
    "particulares": MotorSegment(
        policies={2023: 18_500, 2024: 18_500, 2025: 18_500},
        premium_mean={2023: 585.0, 2024: 600.0, 2025: 615.0},
        frequency_pd=0.09, frequency_rc=0.03, severity_pd=1_700.0, severity_rc=7_000.0,
    ),
    "flotas": MotorSegment(
        policies={2023: 1_500, 2024: 1_500, 2025: 1_500},
        # 2025 repricing is only partial because of competition, so the 2025 cohort is onerous
        premium_mean={2023: 900.0, 2024: 925.0, 2025: 980.0},
        frequency_pd=0.16, frequency_rc=0.045, severity_pd=1_700.0, severity_rc=7_000.0,
        true_severity_shock_pd={2024: 1.30, 2025: 1.30, 2026: 1.30},  # spare-parts inflation
        rc_pattern="comauto",
    ),
}
MOTOR_COMMISSION = 0.15
MOTOR_ADMIN = 0.06  # share of premium: attributable maintenance and claims handling
MOTOR_UPFRONT_SHARE = 0.70  # the rest pays in four quarterly instalments within the policy year
PREMIUM_CV = 0.30  # dispersion of individual P&C premiums around the segment mean

FIRE = {
    "policies": {2023: 8_000, 2024: 8_000, 2025: 8_000},
    "premium_mean": {2023: 500.0, 2024: 510.0, 2025: 520.0},
    "frequency": 0.03, "severity": 8_000.0, "severity_cv": 2.5, "severity_trend": 0.03,
    "cat_probability": 0.02, "cat_loss": 3_000_000.0,  # earthquake/flood load in the expected value (B39)
    "commission": 0.20, "admin": 0.06,
}

CAR = {  # contractors' all risk (TRC)
    "projects": {2023: 150, 2024: 150, 2025: 150},
    "contract_value_median": 2_500_000.0, "contract_value_sigma": 0.8,
    "premium_rate": 0.006, "duration_months": 36,
    "expected_loss_ratio": 0.55, "claims_per_project": 0.25, "severity_cv": 2.0,
    "commission": 0.12, "admin": 0.05,
}

# What the entity knows about the spare-parts price index for heavy vehicles at each date
# (external market data, B44). It explains the fleet severity increase seen in 2024 claims.
FLEET_PD_SEVERITY_INDEX_KNOWN = {"2022-12-31": 1.00, "2023-12-31": 1.00, "2024-12-31": 1.30, "2025-12-31": 1.30}

# Coefficients of variation for the P&C risk adjustment (75th percentile, lognormal).
# LRC: uncertainty of the claims of the coverage still to be provided (onerous test, par. 57).
# LIC: motor liability uses the CAS Mack fit by reserve size (data/processed/claims_cv.csv);
# the short-tail coverages use these assumptions.
PAA_LRC_CV = {("AUTO", "particulares"): 0.08, ("AUTO", "flotas"): 0.15, ("INC", "hogar_comercio"): 0.25,
              ("TRC", "construccion"): 0.35}
LIC_CV_SHORT_TAIL = {"PD": 0.15, "FIRE": 0.30, "CAT": 0.30, "CAR": 0.40}
PC_CORRELATION = 0.25  # between P&C coverages when aggregating the risk adjustment (B88(a))
ULAE_RATE = 0.03  # claims-handling costs for incurred claims, as a share of the claims reserve (B65(f))
COMBINED_RATIO_THRESHOLDS = {"SIG": 0.95, "RES": 1.00}  # memo section 6 (proposal)

# Reporting and settlement delays in months. Motor liability pays along the CAS industry
# pattern (data/processed/claims_patterns.csv); the short-tail lines use these means.
REPORT_DELAY_MEAN = {"pd": 0.5, "rc": 3.0, "fire": 1.0, "car": 2.0}
SETTLEMENT_DELAY_MEAN = {"pd": 1.5, "fire": 3.0, "car": 6.0}
LIABILITY_PARTIAL_PAYMENTS = 3
CASE_RESERVE_NOISE = 0.30  # lognormal sigma of the case estimate around the final amount
EXPENSE_NOISE = 0.05


# --------------------------------------------------------------------------
# Reinsurance held (memo section 13)
# --------------------------------------------------------------------------
REINSURANCE = {
    "quota_share": 0.40,
    "ceding_commission": 0.20,
    "reinsurer_rating": "A",
    "annual_default_probability": 0.0008,  # A-rated one-year default rate, long-run average
    "loss_given_default": 0.60,
}

# Illustrative statutory-type reserve for comparison only (memo section 9).
STATUTORY_VT = {"mortality_factor": 1.00, "interest": 0.04}
