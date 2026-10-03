"""Cross-check curves: Smith-Wilson fitted to the daily Treasury par yields.

    python scripts/build_curves.py

These curves are NOT the IFRS 17 discount curves (see build_discount_curves.py).
They are an independent check of the Treasury TNC curve up to 30 years.

Outputs (annual effective spot rates, in percent):
    data/processed/rf_spot_month_end.csv    36 month-ends x maturities 1..60
    data/processed/rf_spot_closing.csv      the three year-end valuation dates
    data/processed/rf_curve_parameters.csv  UFR and alpha by date
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifrs17.curves import UFR_BY_YEAR, curve_from_par, load_par_curves  # noqa: E402

CLOSINGS = pd.to_datetime(["2023-12-29", "2024-12-31", "2025-12-31"])
MATURITIES = np.arange(1, 61)


def main() -> None:
    par = load_par_curves(ROOT / "data" / "raw" / "treasury" / "par_month_end_2023_2025.csv")
    curves = {d: curve_from_par(row, UFR_BY_YEAR[d.year]) for d, row in par.iterrows()}

    spots = pd.DataFrame(
        {d.date(): 100 * c.spot(MATURITIES) for d, c in curves.items()},
        index=pd.Index(MATURITIES, name="maturity_years"),
    ).T.round(4)
    spots.index.name = "date"
    params = pd.DataFrame(
        {"ufr_pct": [100 * c.ufr for c in curves.values()], "alpha": [round(c.alpha, 6) for c in curves.values()]},
        index=pd.Index([d.date() for d in curves], name="date"),
    )

    out = ROOT / "data" / "processed"
    out.mkdir(parents=True, exist_ok=True)
    spots.to_csv(out / "rf_spot_month_end.csv")
    spots.loc[[d.date() for d in CLOSINGS]].to_csv(out / "rf_spot_closing.csv")
    params.to_csv(out / "rf_curve_parameters.csv")
    print(spots.loc[[d.date() for d in CLOSINGS], [1, 5, 10, 20, 30, 40, 60]])
    print(params.loc[[d.date() for d in CLOSINGS]])


if __name__ == "__main__":
    main()
