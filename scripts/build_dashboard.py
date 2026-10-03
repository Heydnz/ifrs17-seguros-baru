"""Build the dashboard page (Phase 7) from data/results.

    python scripts/run_closings.py
    python scripts/build_dashboard.py                 # docs/index.html for GitHub Pages
    python scripts/build_dashboard.py --fragment PATH # same page without the html/head/body shell

The data are embedded in the page, so it works as a single static file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data" / "results"
TEMPLATE = ROOT / "scripts" / "dashboard_template.html"
YEARS = [2023, 2024, 2025]
CLOSINGS = ["2023-12-31", "2024-12-31", "2025-12-31"]
PORT = {"VT": "Vida temporal", "VA": "Vida con ahorro", "AUTO": "Autos", "INC": "Incendio/hogar",
        "TRC": "Todo riesgo construcción", "RE_VT": "Reaseguro cedido"}


def r0(x):
    return float(round(float(x), 0))


def data() -> dict:
    bs = pd.read_csv(RES / "balance_sheet.csv").set_index("closing")
    pl = pd.read_csv(RES / "profit_or_loss.csv").set_index("year")
    gmm = pd.read_csv(RES / "groups_gmm.csv")
    paa = pd.read_csv(RES / "groups_paa.csv")
    r101 = pd.read_csv(RES / "reconciliation_101.csv")
    out = {"years": YEARS}
    out["pl"] = [
        {"label": "Ingresos por seguros", "key": "insurance_revenue"},
        {"label": "Gastos del servicio de seguros", "key": "insurance_service_expenses"},
        {"label": "Resultado neto del reaseguro cedido", "key": "net_reinsurance"},
        {"label": "Resultado del servicio de seguros", "key": "insurance_service_result", "total": True},
        {"label": "Ingresos de inversiones", "key": "investment_income"},
        {"label": "Gastos financieros de seguros", "key": "insurance_finance_expenses"},
        {"label": "Ingresos financieros del reaseguro", "key": "reinsurance_finance_income"},
        {"label": "Resultado financiero neto", "key": "net_financial_result", "total": True},
        {"label": "Otros gastos no atribuibles", "key": "other_operating_expenses"},
        {"label": "Resultado antes de impuestos", "key": "profit_before_tax", "total": True, "grand": True},
        {"label": "Otro resultado integral", "key": "oci"},
        {"label": "Resultado integral total", "key": "total_comprehensive_income", "total": True},
    ]
    pl["oci"] = pl["oci_insurance_finance"] + pl["oci_reinsurance_finance"] + pl["oci_fvoci_assets"]
    for row in out["pl"]:
        row["values"] = [r0(pl.loc[y, row["key"]]) for y in YEARS]
    out["bs"] = [
        {"label": "Inversiones a valor razonable con cambios en resultados", "key": "investments_fvpl"},
        {"label": "Inversiones a valor razonable con cambios en ORI", "key": "investments_fvoci"},
        {"label": "Activos por contratos de seguro", "key": "insurance_contract_assets"},
        {"label": "Activos por reaseguro cedido", "key": "reinsurance_contract_assets"},
        {"label": "Total activos", "key": "total_assets", "total": True},
        {"label": "Pasivos por contratos de seguro", "key": "insurance_contract_liabilities"},
        {"label": "Capital social", "key": "share_capital"},
        {"label": "Resultados acumulados", "key": "retained_earnings"},
        {"label": "Reservas de ORI", "key": "reserves"},
        {"label": "Total patrimonio", "key": "total_equity", "total": True, "grand": True},
    ]
    bs["reserves"] = bs["insurance_finance_reserve"] + bs["fvoci_reserve"]
    for row in out["bs"]:
        row["values"] = [r0(bs.loc[c, row["key"]]) for c in CLOSINGS]
    out["check"] = [r0(bs.loc[c, "balance_check"]) for c in CLOSINGS]

    steps = [("new_contracts", "Contratos nuevos"), ("finance", "Acreción"), ("future_service_csm", "Cambios de servicio futuro"),
             ("loss_recovery_income", "Recuperación de pérdidas"), ("csm_release", "Liberación por servicios")]
    wf = {}
    for port in ("VT", "VA", "RE_VT"):
        for c, y in zip(CLOSINGS, YEARS):
            sub = r101[(r101["portfolio"] == port) & (r101["closing"] == c)].groupby("line")["csm"].sum()
            wf[f"{port}-{y}"] = {"opening": r0(sub.get("opening", 0.0)), "closing": r0(sub.get("closing", 0.0)),
                                 "steps": [{"label": lab, "value": r0(sub.get(k, 0.0))} for k, lab in steps if abs(sub.get(k, 0.0)) > 0.5]}
    out["waterfall"] = wf

    groups = []
    for _, g in gmm.iterrows():
        cls = g["group"].split("-")[-1] if not g["held"] else "RE"
        groups.append({"closing": int(g["closing"][:4]), "portfolio": g["portfolio"], "group": g["group"], "class": cls,
                       "model": "GMM", "csm": r0(-g["csm"] if g["held"] else g["csm"]),
                       "lc": r0(abs(g["loss_component"])), "carrying": r0(g["lrc"] + g["lic_pv"] + g["lic_ra"])})
    for _, g in paa.iterrows():
        groups.append({"closing": int(g["closing"][:4]), "portfolio": g["portfolio"], "group": g["group"],
                       "class": g["group"].split("-")[-1], "model": "PAA", "csm": None, "lc": r0(g["loss_component"]),
                       "carrying": r0(g["lrc"] + g["lic_pv"] + g["lic_ra"])})
    out["groups"] = groups
    rev = pd.concat([gmm[~gmm["held"]], paa]).groupby(["closing", "portfolio"])["insurance_revenue"].sum()
    out["revenue"] = {p: [r0(rev.get((c, p), 0.0)) for c in CLOSINGS] for p in ("AUTO", "INC", "TRC", "VT", "VA")}
    bands = pd.read_csv(RES / "csm_release_109.csv").set_index("portfolio")
    out["bands"] = {"labels": list(bands.columns), "series": {p: [r0(v) for v in bands.loc[p]] for p in bands.index}}
    sens = pd.read_csv(RES / "sensitivities_128.csv")
    out["sens"] = [{"portfolio": r.portfolio, "change": r.change, "profit": r0(r.profit_net), "equity": r0(r.equity_net)}
                   for r in sens.itertuples() if abs(r.equity_net) > 0.5 or abs(r.profit_net) > 0.5]
    trc = pd.read_csv(RES / "trc_eligibility.csv")
    trc = trc[(trc["lrc_gmm"] > 0)]
    out["trc"] = {str(k): {s: [[int(y), round(100 * v, 2)] for y, v in zip(g2["year_end"], g2["relative"])]
                           for s, g2 in g.groupby("scenario")} for k, g in trc.groupby("cohort")}
    conf = pd.read_csv(RES / "confidence_119.csv")
    out["confidence"] = [{"portfolio": r.portfolio, "level": round(float(r.confidence_level), 3)} for r in conf.itertuples()]
    out["portfolios"] = PORT
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragment", type=Path)
    args = ap.parse_args()
    body = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(data(), ensure_ascii=False))
    if args.fragment:
        args.fragment.write_text(body)
        print("fragment:", args.fragment)
    page = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + body.replace("</style>", "</style>\n</head>\n<body>", 1) + "\n</body>\n</html>\n")
    (ROOT / "docs" / "index.html").write_text(page)
    print("docs/index.html written")


if __name__ == "__main__":
    main()
