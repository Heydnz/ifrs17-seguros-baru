"""General measurement model (GMM): one reporting period of one group (IFRS 17 par. 40-52, B96-B97, B119-B125).

The engine is product-agnostic. The product modules project cash flows and hand it
present values; the engine applies the standard: it sets the contractual service
margin (CSM) of new contracts, accretes it, adjusts it for changes relating to future
service, releases it with coverage units, tracks the loss component of onerous groups
and splits every movement into the lines of the reconciliations in par. 101 and 104.

Sign convention: amounts are seen from the issuer. Present values are "outflows minus
inflows", so a liability is positive. For contracts issued the CSM is never negative;
for reinsurance contracts held (``reinsurance=True``) the CSM can take either sign and
the loss component is replaced by the loss-recovery component (par. 66-66B).

Analysis of change used in each period (all present values of future cash flows):

    expected closing PV (locked rates) = opening PV + new contracts + expected premiums
                                         - expected claims, expenses and investment components
                                         + accretion at locked rates            (B72(b))
    future service  = closing PV at locked rates on the new basis - expected closing PV
                      + premium and investment-component experience            (B96(a)-(c))
    current service = actual minus expected claims and expenses                (B97(c))
    finance         = accretion + change in (current - locked) PV              (B97(a), 87)

Policy choices encoded here (memo sections 11-12):
* experience adjustments on premiums are treated as relating to future service (B96(a));
* the risk adjustment is not disaggregated (par. 81): its change from the opening balance
  to the closing balance on the old basis is the release for current service, and the
  change from the old to the new basis is future service (B96(d));
* the loss component takes a fixed share of the expected claims and expenses released,
  of the risk-adjustment release and of the finance expense at locked rates, equal to the
  loss component over the PV of outflows plus risk adjustment at the start of the period
  (par. 50(a)-52; IASB Illustrative Example 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass
class GroupState:
    pv_current: float = 0.0  # PV of future cash flows at current rates (outflows - inflows)
    pv_locked: float = 0.0  # same cash flows at the rates locked in at initial recognition
    pv_outflows_locked: float = 0.0  # PV of future outflows only, for the loss-component ratio
    ra: float = 0.0
    csm: float = 0.0
    loss_component: float = 0.0  # contracts issued: part of the LRC; reinsurance: loss-recovery component
    acquisition_unallocated: float = 0.0  # acquisition cash flows still to be recovered in revenue (B125)

    @property
    def lrc(self) -> float:
        return self.pv_current + self.ra + self.csm


@dataclass
class PeriodInputs:
    # contracts recognised in the period, measured at recognition at locked rates
    nb_pv_inflows: float = 0.0
    nb_pv_outflows: float = 0.0
    nb_ra: float = 0.0
    nb_csm_accretion: float = 0.0  # interest rate from recognition to the period end (e.g. 0.05)
    nb_acquisition: float = 0.0  # acquisition cash flows of the new contracts (included in nb_pv_outflows)
    # expected cash flows of the period on the opening basis (nominal)
    exp_premiums: float = 0.0
    exp_outflows: float = 0.0  # claims and expenses incurred, excluding investment components and acquisition
    exp_investment_component: float = 0.0
    exp_acquisition: float = 0.0  # acquisition cash flows expected in the period (paid at recognition)
    expected_close_pv_locked: float = 0.0  # PV at the period end of the expected remaining cash flows
    csm_accretion_rate: float = 0.0  # locked-in rate for the opening CSM over the period
    # actual cash flows of the period
    act_premiums: float = 0.0
    act_outflows: float = 0.0  # incurred: paid or transferred to the liability for incurred claims
    act_investment_component: float = 0.0
    act_acquisition: float = 0.0
    # closing measurement on the new basis
    close_pv_locked: float = 0.0
    close_pv_current: float = 0.0
    close_pv_outflows_locked: float = 0.0
    close_ra: float = 0.0
    close_ra_old_basis: float | None = None  # same in-force and rates, opening assumptions
    # coverage units (B119): provided in the period and expected in the future
    cu_period: float = 0.0
    cu_future: float = 0.0
    acquisition_allocation: float | None = None  # B125 amount for the period; default: time share via units
    # reinsurance held: loss-recovery adjustments (par. 66A, 66(c)(i)-(ii), B119C-B119F)
    loss_recovery_income: float = 0.0
    loss_recovery_reversal: float = 0.0  # mirrors the allocation out of the underlying loss component (B119F)


@dataclass
class PeriodResult:
    opening: GroupState
    closing: GroupState
    movements: dict = field(default_factory=dict)
    pnl: dict = field(default_factory=dict)


def _split_onerous(adjustment: float, csm_available: float, loss_component: float, reinsurance: bool):
    """Allocate a change in fulfilment cash flows relating to future service (positive = unfavourable).

    Returns (to_csm, to_loss_component, loss_in_pnl). For contracts issued an increase beyond the
    CSM is a loss (par. 48) and a decrease first reverses the loss component (par. 50(b)).
    """
    if reinsurance:
        return -adjustment, 0.0, 0.0
    if adjustment > 0:
        absorbed = min(adjustment, max(csm_available, 0.0))
        excess = adjustment - absorbed
        return -absorbed, excess, excess
    decrease = -adjustment
    reversal = min(decrease, loss_component)
    return decrease - reversal, -reversal, -reversal


def run_period(opening: GroupState, x: PeriodInputs, reinsurance: bool = False, oci: bool = False) -> PeriodResult:
    s = replace(opening)
    mv: dict = {}

    # 1. contracts recognised in the period (par. 38, 47, 28, 44(a))
    nb_pv = x.nb_pv_outflows - x.nb_pv_inflows
    nb_fcf = nb_pv + x.nb_ra
    if reinsurance or nb_fcf <= 0:
        nb_csm, to_lc, loss = -nb_fcf, 0.0, 0.0  # no gain at recognition; reinsurance: net cost or gain (65)
    else:
        nb_csm, to_lc, loss = 0.0, nb_fcf, nb_fcf  # onerous on recognition (47)
    nb_csm_interest = nb_csm * x.nb_csm_accretion
    mv["new_contracts"] = {"pv": nb_pv, "ra": x.nb_ra, "csm": nb_csm, "loss": loss}
    s.loss_component += to_lc
    s.acquisition_unallocated += x.nb_acquisition

    # 2. loss-component ratio at the start of the period, after new contracts (par. 50(a))
    pv_out_start = opening.pv_outflows_locked + x.nb_pv_outflows - x.nb_acquisition
    denom = pv_out_start + opening.ra + x.nb_ra
    lc_ratio = s.loss_component / denom if (not reinsurance and s.loss_component > 0 and denom > 0) else 0.0

    # 3. accretion at locked rates (B72(b)) and finance effect of current rates (B97(a))
    expected_cf = x.exp_premiums - x.exp_outflows - x.exp_investment_component - x.exp_acquisition
    pv_accretion = x.expected_close_pv_locked - (opening.pv_locked + nb_pv + expected_cf)
    csm_accretion = opening.csm * x.csm_accretion_rate + nb_csm_interest
    gap_open = opening.pv_current - opening.pv_locked
    gap_close = x.close_pv_current - x.close_pv_locked
    rate_effect = gap_close - gap_open

    # 4. changes relating to future service, measured at locked rates (B96, B72(c))
    premium_experience = x.exp_premiums - x.act_premiums  # received less than expected -> PV higher
    ic_experience = x.act_investment_component - x.exp_investment_component
    acq_experience = x.act_acquisition - x.exp_acquisition
    pv_future = (x.close_pv_locked - x.expected_close_pv_locked) + premium_experience + ic_experience + acq_experience
    ra_old = x.close_ra if x.close_ra_old_basis is None else x.close_ra_old_basis
    ra_future = x.close_ra - ra_old
    ra_release = opening.ra + x.nb_ra - ra_old

    # 5. systematic allocation to the loss component (par. 50(a), 51), before future-service changes
    lc_alloc_service = lc_ratio * (x.exp_outflows + ra_release)
    lc_alloc_finance = lc_ratio * pv_accretion
    s.loss_component += -lc_alloc_service + lc_alloc_finance
    if not reinsurance and x.cu_future == 0 and s.loss_component > 0:
        # par. 52: nothing may remain in the loss component at the end of the coverage period
        lc_alloc_service += s.loss_component
        s.loss_component = 0.0
    if not reinsurance:
        s.loss_component = max(s.loss_component, 0.0)

    csm_before = opening.csm + nb_csm + csm_accretion
    # reinsurance held: income on initial recognition of onerous underlying contracts adjusts the CSM (66A)
    if reinsurance:
        csm_before += x.loss_recovery_income
        s.loss_component += x.loss_recovery_income - x.loss_recovery_reversal
    to_csm, to_lc, fs_loss = _split_onerous(pv_future + ra_future, csm_before, s.loss_component, reinsurance)
    s.loss_component += to_lc

    # 6. CSM release for services provided (44(e), B119)
    csm_pre_release = csm_before + to_csm
    total_cu = x.cu_period + x.cu_future
    release_share = x.cu_period / total_cu if total_cu > 0 else 1.0
    csm_release = csm_pre_release * release_share
    s.csm = csm_pre_release - csm_release

    # acquisition cash flows recovered in revenue (B125)
    if x.acquisition_allocation is None:
        acq_alloc = s.acquisition_unallocated * release_share
    else:
        acq_alloc = x.acquisition_allocation
    s.acquisition_unallocated -= acq_alloc

    s.pv_current = x.close_pv_current
    s.pv_locked = x.close_pv_locked
    s.pv_outflows_locked = x.close_pv_outflows_locked
    s.ra = x.close_ra

    # reconciliation lines (par. 101, 103-104); fs split between CSM-adjusting and onerous parts
    fs_total = pv_future + ra_future
    share_csm = (-to_csm / fs_total) if (fs_total and not reinsurance) else 1.0
    share_csm = 1.0 if reinsurance else share_csm
    mv["future_service_csm"] = {"pv": pv_future * share_csm, "ra": ra_future * share_csm, "csm": to_csm}
    mv["future_service_onerous"] = {"pv": pv_future * (1 - share_csm), "ra": ra_future * (1 - share_csm), "csm": 0.0}
    if reinsurance and x.loss_recovery_income:
        mv["loss_recovery_income"] = {"pv": 0.0, "ra": 0.0, "csm": x.loss_recovery_income}
    mv["csm_release"] = {"pv": 0.0, "ra": 0.0, "csm": -csm_release}
    mv["ra_release"] = {"pv": 0.0, "ra": -ra_release, "csm": 0.0}
    mv["experience"] = {"pv": x.act_outflows - x.exp_outflows, "ra": 0.0, "csm": 0.0}
    mv["finance"] = {"pv": pv_accretion + rate_effect, "ra": 0.0, "csm": csm_accretion}
    mv["premiums_received"] = {"pv": x.act_premiums, "ra": 0.0, "csm": 0.0}
    mv["claims_and_expenses_incurred"] = {"pv": -x.act_outflows, "ra": 0.0, "csm": 0.0}
    mv["investment_components"] = {"pv": -x.act_investment_component, "ra": 0.0, "csm": 0.0}
    mv["acquisition_cash_flows"] = {"pv": -x.act_acquisition, "ra": 0.0, "csm": 0.0}

    # profit or loss (par. 83-84, B121-B125); reinsurance amounts are expenses/recoveries, not revenue
    lc_alloc_revenue = lc_alloc_service
    revenue = (x.exp_outflows + ra_release + csm_release + acq_alloc) - lc_alloc_revenue
    ise_claims = x.act_outflows
    ise_onerous = loss + fs_loss  # losses on onerous groups and their reversals (negative)
    ise = ise_claims + acq_alloc + ise_onerous - lc_alloc_revenue
    ifie_pnl = pv_accretion + csm_accretion if oci else pv_accretion + csm_accretion + rate_effect
    ifie_oci = rate_effect if oci else 0.0
    pnl = {
        "insurance_revenue": revenue,
        "revenue_expected_claims_expenses": x.exp_outflows,
        "revenue_ra_release": ra_release,
        "revenue_loss_component_exclusion": -lc_alloc_revenue,  # par. 49, B123(a)(i)
        "revenue_csm_release": csm_release,
        "revenue_acquisition_recovery": acq_alloc,
        "ise_incurred_claims_expenses": ise_claims,
        "ise_acquisition_amortisation": acq_alloc,
        "ise_onerous_losses_and_reversals": ise_onerous - lc_alloc_revenue,
        "insurance_service_expenses": ise,
        "insurance_service_result": revenue - ise,
        "ifie_pnl": ifie_pnl,
        "ifie_oci": ifie_oci,
        "lc_ratio": lc_ratio,
        "loss_component_allocation": lc_alloc_service - lc_alloc_finance,
    }
    if reinsurance:
        pnl["loss_recovery_income"] = x.loss_recovery_income
        pnl["loss_recovery_reversal"] = x.loss_recovery_reversal
    _check_roll(opening, s, mv)
    return PeriodResult(opening=opening, closing=s, movements=mv, pnl=pnl)


def _check_roll(opening: GroupState, closing: GroupState, mv: dict, tol: float = 1e-6) -> None:
    for col, attr in (("pv", "pv_current"), ("ra", "ra"), ("csm", "csm")):
        total = getattr(opening, attr) + sum(v[col] for v in mv.values())
        if abs(total - getattr(closing, attr)) > tol * max(1.0, abs(total)):
            raise AssertionError(f"{col} does not roll forward: {total} vs {getattr(closing, attr)}")
