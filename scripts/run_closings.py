"""Run the three closings of Seguros Baru and write every result table (Phases 2-6).

    python scripts/run_simulation.py      # synthetic data (Phase 1), once
    python scripts/run_closings.py        # measurement, statements and disclosures
    python scripts/run_closings.py --refresh   # ignore the cached run

Outputs go to data/results/: one CSV per statement or disclosure and dashboard.json,
which feeds the web page in docs/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifrs17 import assumptions as A  # noqa: E402
from ifrs17 import closing as C  # noqa: E402
from ifrs17 import disclosures as D  # noqa: E402
from ifrs17 import pc  # noqa: E402
from ifrs17.experience import mortality_study  # noqa: E402

OUT = ROOT / "data" / "results"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    t0 = time.time()
    res = C.run(refresh=args.refresh)
    st = C.statements(res)
    tables = {
        "balance_sheet": st["balance_sheet"].reset_index(),
        "profit_or_loss": st["profit_or_loss"].reset_index(),
        "profit_or_loss_ifrs18": D.ifrs18_profit_or_loss(st["profit_or_loss"]).reset_index(),
        "operating_cash_flows": st["cash"].reset_index(),
        "groups_gmm": st["gmm"].drop(columns=["cu_by_year", "net_cf_by_year"], errors="ignore"),
        "groups_paa": st["paa"],
        "reconciliation_100": D.reconciliation_100(res),
        "reconciliation_101": D.reconciliation_101(res),
        "revenue_106": D.revenue_analysis(res),
        "new_business_107": D.new_business(res),
        "csm_release_109": D.csm_release_bands(res).reset_index(),
        "assumptions_117": D.assumptions_table(),
        "confidence_119": D.confidence_levels(res),
        "discount_rates_120": D.discount_rates_table(),
        "sensitivities_128": D.sensitivities(res),
        "claims_development_130_auto": D.claims_development("AUTO"),
        "claims_development_130_trc": D.claims_development("TRC"),
        "maturity_132": D.maturity_analysis(res).reset_index(),
        "classification_vt": res["vt"]["classification"],
        "classification_va": res["va"]["classification"],
        "classification_paa": res["paa"]["classification"],
        "trc_eligibility": pd.concat([pc.trc_eligibility(y) for y in (2023, 2024, 2025)]),
        "mortality_study": pd.concat([mortality_study("vt", c) for c in A.CLOSINGS]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
    check = D.check_100(tables["reconciliation_100"]).abs().to_numpy().max()
    bs = tables["balance_sheet"]
    print(f"par. 100 reconciliation max difference: {check:.6f}")
    print(f"balance sheet check (assets - liabilities - equity): {bs['balance_check'].abs().max():.6f}")

    dash = {
        "balance_sheet": bs.round(0).to_dict(orient="records"),
        "profit_or_loss": tables["profit_or_loss"].round(0).to_dict(orient="records"),
        "csm_by_portfolio": st["gmm"].groupby(["closing", "portfolio"])["csm"].sum().round(0).reset_index().to_dict(orient="records"),
        "groups": st["gmm"][["closing", "portfolio", "group", "csm", "loss_component", "lrc"]].round(0).to_dict(orient="records")
        + st["paa"][["closing", "portfolio", "group", "loss_component", "lrc"]].round(0).to_dict(orient="records"),
        "revenue_by_portfolio": pd.concat([st["gmm"], st["paa"]]).groupby(["closing", "portfolio"])["insurance_revenue"].sum()
        .round(0).reset_index().to_dict(orient="records"),
        "csm_release_109": tables["csm_release_109"].round(0).to_dict(orient="records"),
        "sensitivities": tables["sensitivities_128"].round(0).to_dict(orient="records"),
        "discount_rates": tables["discount_rates_120"].round(5).to_dict(orient="records"),
        "claims_development": tables["claims_development_130_auto"].round(0).to_dict(orient="records"),
        "trc_eligibility": tables["trc_eligibility"].round(4).to_dict(orient="records"),
        "classification_paa": tables["classification_paa"].round(4).to_dict(orient="records"),
        "confidence": tables["confidence_119"].round(4).to_dict(orient="records"),
    }
    (OUT / "dashboard.json").write_text(json.dumps(dash, ensure_ascii=False, indent=1, default=float))
    print(f"{len(tables)} tables written to {OUT} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
