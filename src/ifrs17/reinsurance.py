"""Reinsurance held: 40% quota share of term life, one treaty per underwriting year (memo section 13).

Each treaty is a group of one contract measured with the GMM (par. 60-70A). The engine
is run from the reinsurer's side (premiums in, recoveries out), so its carrying amount is
the cedant's asset and its CSM is the cedant's net cost (positive) or gain (negative).

* Cash flows are consistent with the underlying groups (par. 63): 40% of the premiums
  less the 20% ceding commission (which does not depend on claims, so it reduces the
  premiums paid, par. 86(b)) and 40% of the death benefits, reduced for the expected
  default of an A-rated reinsurer (par. 63; changes in that risk never adjust the CSM, 67).
* The risk adjustment is the risk transferred: 40% of the underlying one (par. 64).
* Coverage units are the ceded sum insured in force.
* Loss-recovery component (66A-66B, B119C-B119F): when an underlying group is onerous at
  recognition or becomes more onerous, the treaty recognises income equal to the loss x
  40% (the share of claims it is expected to recover) and adjusts its CSM; reversals of the
  underlying loss reverse it; the component then follows the underlying loss component
  and its release is excluded from the allocation of premiums paid.
* Finance income or expenses follow the OCI option of term life (par. 88(b)).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import assumptions as A
from .gmm import GroupState, PeriodInputs, run_period

Q = A.REINSURANCE["quota_share"]
CC = A.REINSURANCE["ceding_commission"]
EXPECTED_DURATION_YEARS = 8.0  # average time to a recovery for the default adjustment
DEFAULT_FACTOR = float(np.exp(-A.REINSURANCE["annual_default_probability"] * A.REINSURANCE["loss_given_default"]
                              * EXPECTED_DURATION_YEARS))


def treaty_of(group: str) -> str:
    return "RE-" + group.split("-")[1]


def _cohort_sums(details: pd.DataFrame) -> pd.DataFrame:
    d = details.copy()
    d["treaty"] = d["group"].map(treaty_of)
    num = d.select_dtypes("number").columns
    return d.groupby("treaty")[list(num)].sum()


def run_all(vt: dict) -> dict:
    """Measure the treaties from the term-life results of ``term_life.run_all``."""
    states, outputs = {}, []
    for out in vt["closings"]:
        det = out.details.copy()
        sums = _cohort_sums(det)
        # underlying onerous movements of the period, by treaty
        under = []
        for g, r in out.results.items():
            under.append({"treaty": treaty_of(g),
                          "loss": r.movements["new_contracts"]["loss"],
                          # losses and reversals from future-service changes of the underlying group (48, 50(b))
                          "fs_onerous": r.pnl["ise_onerous_losses_and_reversals"] - r.pnl["revenue_loss_component_exclusion"]
                          - r.movements["new_contracts"]["loss"],
                          "lc_allocation": r.pnl["loss_component_allocation"],
                          "lc_close": r.closing.loss_component,
                          "csm_accretion_rate": r.opening.csm and (r.movements["finance"]["csm"] / max(r.opening.csm, 1e-9))})
        under = pd.DataFrame(under).groupby("treaty").sum(numeric_only=True)
        results = {}
        for t, s in sums.iterrows():
            st = states.get(t, GroupState())
            x = PeriodInputs(
                nb_pv_inflows=Q * (1 - CC) * s["ceded_nb_prem_L"],
                nb_pv_outflows=Q * DEFAULT_FACTOR * s["ceded_nb_ben_L"],
                nb_ra=Q * s["nb_ra"],
                nb_csm_accretion=float(det.loc[det["group"].map(treaty_of) == t, "nb_csm_accretion"].mean()),
                exp_premiums=Q * (1 - CC) * s["ceded_exp_prem"],
                exp_outflows=Q * DEFAULT_FACTOR * s["ceded_exp_ben"],
                expected_close_pv_locked=Q * (DEFAULT_FACTOR * s["ceded_expected_close_ben_L"] - (1 - CC) * s["ceded_expected_close_prem_L"]),
                csm_accretion_rate=float(det.loc[det["group"].map(treaty_of) == t, "csm_accretion_rate"].max()),
                act_premiums=Q * (1 - CC) * s["ceded_act_prem"],
                act_outflows=Q * s["ceded_act_ben"],  # no default has occurred: actual recoveries in full
                close_pv_locked=Q * (DEFAULT_FACTOR * s["ceded_close_ben_L"] - (1 - CC) * s["ceded_close_prem_L"]),
                close_pv_current=Q * (DEFAULT_FACTOR * s["ceded_close_ben_C"] - (1 - CC) * s["ceded_close_prem_C"]),
                close_pv_outflows_locked=Q * DEFAULT_FACTOR * s["ceded_close_ben_L"],
                close_ra=Q * s["close_ra"],
                close_ra_old_basis=Q * s["close_ra_old_basis"],
                cu_period=Q * s["cu_period"],
                cu_future=Q * s["cu_future"],
                loss_recovery_income=Q * (under.loc[t, "loss"] + under.loc[t, "fs_onerous"]) if t in under.index else 0.0,
                loss_recovery_reversal=Q * under.loc[t, "lc_allocation"] if t in under.index else 0.0,
            )
            results[t] = run_period(st, x, reinsurance=True, oci=True)
        for t, r in results.items():
            states[t] = r.closing
        lic = det.assign(treaty=det["group"].map(treaty_of)).groupby("treaty")[["ceded_lic_ben", "ceded_paid_ben", "ceded_act_ben"]].sum() * Q
        outputs.append({"closing": out.closing, "results": results, "recoverable_incurred": lic})
    return {"closings": outputs, "states": states}


def presentation(result) -> dict:
    """Cedant's view of one period (par. 82, 86): allocation of premiums paid and amounts recovered."""
    p = result.pnl
    lr_income = p.get("loss_recovery_income", 0.0)
    lr_rev = p.get("loss_recovery_reversal", 0.0)
    allocation = p["insurance_revenue"] - lr_rev
    recovered = p["ise_incurred_claims_expenses"] + lr_income - lr_rev
    return {"allocation_of_premiums_paid": -allocation, "amounts_recovered": recovered,
            "loss_recovery_income": lr_income, "loss_recovery_reversal": -lr_rev,
            # the carrying amount is the cedant's asset, so its accretion is finance income for the cedant
            "net_result": recovered - allocation, "finance_pnl": p["ifie_pnl"], "finance_oci": p["ifie_oci"],
            "asset": result.closing.lrc}
