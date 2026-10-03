"""Industry claims-development patterns and reserve uncertainty from the CAS Loss
Reserving Database (Schedule P, accident years 1988-1997), as packaged in the
open-source ``chainladder`` library (``load_sample("clrd")``).

    pip install chainladder
    python scripts/build_claims_patterns.py

Outputs in data/processed/:
    claims_patterns.csv  paid development pattern by development year (1..10) for
                         private passenger auto liability (ppauto) and commercial
                         auto liability (comauto), industry total, volume-weighted LDFs
    claims_cv.csv        reserve coefficient of variation as a function of reserve
                         size, fitted on Mack chain-ladder results by company:
                         log(cv) = a + b * log(reserve in USD thousands)

The CAS database has no property line, so short-tail patterns (motor own damage,
fire/home, contractors' all risk) are set as documented assumptions in
``ifrs17.assumptions``.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import chainladder as cl
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
LINES = {"ppauto": "Private passenger auto liability/medical", "comauto": "Commercial auto/truck liability/medical"}


def main() -> None:
    warnings.filterwarnings("ignore")
    clrd = cl.load_sample("clrd")
    patterns, cvs = [], []
    for lob, name in LINES.items():
        sub = clrd[clrd["LOB"] == lob]
        paid = sub["CumPaidLoss"].sum()
        dev = cl.Development(average="volume").fit(paid)
        cdf = dev.cdf_.values[0, 0, 0, :]  # age-to-ultimate from development year k to 10
        pct_paid = np.append(1.0 / cdf, 1.0)  # cumulative share paid at end of years 1..10
        incr = np.diff(np.concatenate([[0.0], pct_paid]))
        for k in range(10):
            patterns.append({"line": lob, "description": name, "development_year": k + 1,
                             "cumulative_paid": round(pct_paid[k], 6), "incremental_paid": round(incr[k], 6)})

        rows = []
        for i in range(sub.shape[0]):
            tri = sub["CumPaidLoss"].iloc[i]
            v = tri.values[0, 0]
            if np.isnan(v).all() or np.nanmin(v[:, 0]) <= 0:
                continue
            try:
                mack = cl.MackChainladder().fit(tri)
            except Exception:  # noqa: BLE001 - some company triangles are degenerate
                continue
            reserve = float(np.nansum(mack.ibnr_.values))
            se = float(mack.total_mack_std_err_.values.flatten()[0])
            if reserve > 0 and 0 < se / reserve < 5:
                rows.append((reserve, se / reserve))
        d = pd.DataFrame(rows, columns=["reserve", "cv"])
        b, a = np.polyfit(np.log(d["reserve"]), np.log(d["cv"]), 1)
        cvs.append({"line": lob, "companies": len(d), "a": round(a, 6), "b": round(b, 6),
                    "median_cv": round(d["cv"].median(), 4), "units": "reserve in USD thousands"})

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(patterns).to_csv(OUT / "claims_patterns.csv", index=False)
    pd.DataFrame(cvs).to_csv(OUT / "claims_cv.csv", index=False)
    print(pd.DataFrame(patterns).pivot(index="development_year", columns="line", values="cumulative_paid"))
    print(pd.DataFrame(cvs))


if __name__ == "__main__":
    main()
