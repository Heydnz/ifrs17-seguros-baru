"""Experience studies that update the best-estimate assumptions at each closing (B54-B57).

Mortality: actual deaths against the deaths expected under CSO 1980 (factor 1, with
the 1% improvement), by segment, over all exposure from 2023 to the closing date. A
new insurer has few deaths, so the entity's own ratio is blended with the reinsurer's
study by limited-fluctuation credibility:

    Z = min(1, sqrt(deaths / 1,082))       (90% probability of being within 5%)
    factor = Z x own actual/expected + (1 - Z) x reinsurer study

Only deaths reported by the closing date count; deaths that occurred but were not yet
reported are unknown to the entity at that date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import assumptions as A
from .data import load
from .life import older_high_si
from .mortality import BASE_YEAR, cso1980, monthly_rate

INITIAL_CLOSING = "2022-12-31"  # pseudo-date: the assumptions set when the products were launched


def _exposure_months(policies: pd.DataFrame, closing: pd.Timestamp) -> list[tuple[np.ndarray, int, np.ndarray]]:
    """For each calendar month up to the closing: (row mask, calendar year, attained ages)."""
    start = (policies["issue_date"].dt.year - A.START_YEAR) * 12 + policies["issue_date"].dt.month - 1
    last_known = (closing.year - A.START_YEAR) * 12 + closing.month - 1
    out = []
    for t in range(last_known + 1):
        live = (start <= t).to_numpy() & policies["_active_until"].ge(t).to_numpy()
        dur = t - start.to_numpy()
        ages = np.minimum(policies["issue_age"].to_numpy() + np.maximum(dur, 0) // 12, 99)
        out.append((live, A.START_YEAR + t // 12, ages))
    return out


def mortality_study(product: str, closing) -> pd.DataFrame:
    """Actual and expected deaths by segment, own factor, credibility and the blended factor."""
    c = pd.Timestamp(closing)
    pol = load(f"{product}_policies")
    pol = pol[pol["issue_date"] <= c].copy()
    claims = load(f"{product}_claims")
    known_deaths = claims[(claims["report_date"] <= c) & (claims["occurrence_date"] <= c)]
    exit_ = pol["exit_date"].where(pol["exit_date"] <= c)
    exit_month = (exit_.dt.year - A.START_YEAR) * 12 + exit_.dt.month - 1
    pol["_active_until"] = exit_month.fillna(10_000).astype(int)
    pol["_segment"] = np.where(older_high_si(pol), "older_high_si", "default")
    table = cso1980()
    q_base = np.where(pol["sex"].to_numpy()[:, None] == "M", table["M"].to_numpy()[None, :], table["F"].to_numpy()[None, :])
    expected = {"default": 0.0, "older_high_si": 0.0}
    exposure = {"default": 0.0, "older_high_si": 0.0}
    for live, year, ages in _exposure_months(pol, c):
        q = q_base[np.arange(len(pol)), ages] * (1 - A.MORTALITY_IMPROVEMENT) ** (year - BASE_YEAR)
        qm = monthly_rate(q)
        for seg in expected:
            m = live & (pol["_segment"].to_numpy() == seg)
            expected[seg] += qm[m].sum()
            exposure[seg] += m.sum() / 12
    seg_of = pol.set_index("policy_id")["_segment"]
    actual = known_deaths["policy_id"].map(seg_of).value_counts()
    study = A.MORTALITY_EXTERNAL_STUDY[str(c.date())]
    rows = []
    for seg in ("default", "older_high_si"):
        d = int(actual.get(seg, 0))
        own = d / expected[seg] if expected[seg] > 0 else np.nan
        z = min(1.0, np.sqrt(d / A.FULL_CREDIBILITY_DEATHS))
        factor = z * (own if np.isfinite(own) else 0.0) + (1 - z) * study[seg]
        rows.append({"closing": str(c.date()), "segment": seg, "exposure_years": exposure[seg], "deaths": d,
                     "expected_cso80": expected[seg], "own_factor": own, "credibility": z,
                     "external_study": study[seg], "best_estimate_factor": factor})
    return pd.DataFrame(rows)


def mortality_factors(product: str, closing) -> dict:
    """Best-estimate factors on CSO 1980 by segment at a closing (initial assumptions before 2023)."""
    if str(pd.Timestamp(closing).date()) == INITIAL_CLOSING:
        return {"default": A.MORTALITY_FACTOR, "older_high_si": A.MORTALITY_FACTOR}
    s = mortality_study(product, closing).set_index("segment")["best_estimate_factor"]
    return s.to_dict()
