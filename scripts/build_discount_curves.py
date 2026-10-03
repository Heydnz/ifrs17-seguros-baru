"""Build the IFRS 17 discount curves from the Treasury TNC and HQM end-of-month files.

Put the three workbooks downloaded from home.treasury.gov in data/raw/treasury/:

    tnceom_23_27.xlsx   TNC spot rates, end of month, 2023-
    hqmeom_19_23.xls    HQM spot rates, end of month, 2019-2023
    hqmeom_24_28.xls    HQM spot rates, end of month, 2024-

then run:

    python scripts/build_discount_curves.py                      # policy: plain HQM
    python scripts/build_discount_curves.py --credit-share 0.55  # option: deduct credit (CDS)
    python scripts/build_discount_curves.py --graded-liquidity   # option: 100/75/50% by bucket

Outputs in data/processed/:
    tnc_hqm_eom.csv                    both curves, every month, maturities 0.5..100
    discount_curves_halfyear.csv       discount curves (annual effective) for every month
                                       and liquidity bucket on the 0.5-year grid, used for
                                       the locked-in rates of each issue year (B73)
    discount_curves_monthly_<YYYY-MM>.csv  monthly maturities 1..1200 for each closing
                                           month and liquidity bucket
    discount_curves_summary.csv        spot rates at selected maturities
    tnc_vs_smith_wilson.csv            cross-check of the TNC curve against the
                                       Smith-Wilson curve built from daily par yields
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifrs17.curves import UFR_BY_YEAR, curve_from_par, load_par_curves  # noqa: E402
from ifrs17.illiquidity import (  # noqa: E402
    APPLICATION_RATIO,
    APPLICATION_RATIO_BY_LIQUIDITY,
    CREDIT_SHARE,
    CREDIT_SHARE_CDS,
)
from ifrs17.treasury_curves import (  # noqa: E402
    build_discount_curve,
    read_treasury_spot_file,
    semiannual_to_annual,
)

RAW = ROOT / "data" / "raw" / "treasury"
OUT = ROOT / "data" / "processed"
CLOSING_MONTHS = [pd.Period("2023-12", "M"), pd.Period("2024-12", "M"), pd.Period("2025-12", "M")]
CLOSING_DATES = {"2023-12": "2023-12-29", "2024-12": "2024-12-31", "2025-12": "2025-12-31"}
SUMMARY_MATURITIES = [1, 5, 10, 20, 30, 40, 60, 100]


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    tnc = read_treasury_spot_file(RAW / "tnceom_23_27.xlsx")
    hqm = pd.concat([read_treasury_spot_file(RAW / f) for f in ("hqmeom_19_23.xls", "hqmeom_24_28.xls")])
    hqm = hqm[~hqm.index.duplicated(keep="last")].sort_index()
    return tnc, hqm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credit-share", type=float, default=CREDIT_SHARE)
    parser.add_argument("--graded-liquidity", action="store_true")
    args = parser.parse_args()
    ratios = APPLICATION_RATIO_BY_LIQUIDITY if args.graded_liquidity else APPLICATION_RATIO

    tnc, hqm = load_inputs()
    missing = [m for m in CLOSING_MONTHS if m not in tnc.index or m not in hqm.index]
    if missing:
        raise SystemExit(f"closing months missing from the files: {missing}")
    OUT.mkdir(parents=True, exist_ok=True)

    both = pd.concat({"TNC": tnc, "HQM": hqm}, names=["curve", "month"])
    (100 * both).round(4).to_csv(OUT / "tnc_hqm_eom.csv")

    # Every month-end and bucket on the half-year grid (inputs for locked-in rates, B73)
    months = [m for m in tnc.index if m in hqm.index and pd.Period("2023-01", "M") <= m <= pd.Period("2025-12", "M")]
    grid_rows = []
    for month in months:
        for bucket, ratio in ratios.items():
            curve = build_discount_curve(tnc.loc[month], hqm.loc[month], args.credit_share, ratio)
            grid_rows.append(pd.Series(100 * curve.spot_annual, index=curve.maturities, name=(str(month), bucket)))
    grid = pd.DataFrame(grid_rows).round(4)
    grid.index = pd.MultiIndex.from_tuples(grid.index, names=["month", "bucket"])
    grid.columns.name = "maturity_years"
    grid.to_csv(OUT / "discount_curves_halfyear.csv")

    summary = []
    for month in CLOSING_MONTHS:
        spread_bp = 1e4 * (hqm.loc[month] - tnc.loc[month])
        tables = {}
        for bucket, ratio in ratios.items():
            tables[bucket] = build_discount_curve(tnc.loc[month], hqm.loc[month], args.credit_share, ratio).monthly_table()
        # policy curve plus the alternatives kept as options / sensitivities (par. 128)
        scenarios = [("policy", args.credit_share, ratios["high"]), ("tnc_only", 1.0, 1.0),
                     ("hqm_full_spread", 0.0, 1.0), ("cds_credit_55", CREDIT_SHARE_CDS, 1.0)]
        scenarios += [(f"cds_credit_55_{b}", CREDIT_SHARE_CDS, r) for b, r in APPLICATION_RATIO_BY_LIQUIDITY.items() if r < 1]
        for label, cs, ratio in scenarios:
            curve = build_discount_curve(tnc.loc[month], hqm.loc[month], cs, ratio)
            row = {"month": str(month), "scenario": label, "credit_share": cs, "application_ratio": ratio,
                   "spread_10y_bp": round(spread_bp.loc[10.0], 1)}
            row.update({f"{m}y": round(100 * curve.spot(m)[0], 4) for m in SUMMARY_MATURITIES})
            summary.append(row)
        pd.concat(tables, axis=1).to_csv(OUT / f"discount_curves_monthly_{month}.csv")
    pd.DataFrame(summary).to_csv(OUT / "discount_curves_summary.csv", index=False)

    # Cross-check: TNC (Treasury fitted curve) vs Smith-Wilson on daily par yields, up to 30 years
    par = load_par_curves(RAW / "par_month_end_2023_2025.csv")
    check = []
    for month in CLOSING_MONTHS:
        sw = curve_from_par(par.loc[CLOSING_DATES[str(month)]], UFR_BY_YEAR[month.year])
        for m in (1, 2, 5, 10, 20, 30):
            t_annual = semiannual_to_annual(tnc.loc[month, float(m)])
            check.append({"month": str(month), "maturity": m, "tnc_pct": round(100 * t_annual, 4),
                          "smith_wilson_pct": round(100 * sw.spot(m)[0], 4),
                          "diff_bp": round(1e4 * (t_annual - sw.spot(m)[0]), 1)})
    pd.DataFrame(check).to_csv(OUT / "tnc_vs_smith_wilson.csv", index=False)

    print(pd.DataFrame(summary).to_string(index=False))
    print(pd.DataFrame(check).to_string(index=False))


if __name__ == "__main__":
    main()
