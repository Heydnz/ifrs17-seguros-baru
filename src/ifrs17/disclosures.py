"""Disclosures produced by the engine (IFRS 17 par. 93-132; memo section 15).

Every function returns a tidy DataFrame that the Excel workbook and the dashboard use.
Amounts are in USD; liabilities are positive and the reinsurance held is shown as an
asset (positive) in its own tables, as par. 98 requires separate reconciliations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import assumptions as A
from . import closing as C
from . import pc, savings, term_life
from .data import life_inforce, load
from .discounting import curve_for
from .experience import mortality_study
from .life import BEST_ESTIMATE, project_term
from .risk_adjustment import aggregate, term_life_risk_adjustment
from .treasury_curves import DiscountCurve

PORTFOLIO_NAMES = {"VT": "Vida temporal", "VA": "Vida con ahorro", "AUTO": "Autos", "INC": "Incendio/hogar",
                   "TRC": "Todo riesgo construcción", "RE_VT": "Reaseguro cedido (vida temporal)"}
LAST = A.CLOSINGS[-1]


# --------------------------------------------------------------------------
# par. 100 and 103: LRC excluding loss component, loss component, LIC
# --------------------------------------------------------------------------
def reconciliation_100(res: dict) -> pd.DataFrame:
    rows = []
    for key, port in (("vt", "VT"), ("va", "VA")):
        prev_lic = {}
        for out in res[key]["closings"]:
            lic = out.lic.set_index("group")
            det = out.details.set_index("group")
            for g, r in out.results.items():
                p, mv, o, c = r.pnl, r.movements, r.opening, r.closing
                lc_fin = p["lc_ratio"] * (p["ifie_pnl"] - mv["finance"]["csm"]) if p["lc_ratio"] else 0.0
                onerous = mv["new_contracts"]["loss"] + (p["ise_onerous_losses_and_reversals"] - p["revenue_loss_component_exclusion"]
                                                         - mv["new_contracts"]["loss"]) - (-p["revenue_loss_component_exclusion"])
                finance = mv["finance"]["pv"] + mv["finance"]["csm"]
                ra_lic_open = prev_lic.get(g, (0.0, 0.0))[1]
                lines = {
                    "opening": (o.lrc - o.loss_component, o.loss_component, lic.loc[g, "opening"] + ra_lic_open),
                    "insurance_revenue": (-p["insurance_revenue"], 0.0, 0.0),
                    "incurred_claims_and_expenses": (0.0, 0.0, det.loc[g, "act_outflows"]),
                    "acquisition_amortisation": (p["ise_acquisition_amortisation"], 0.0, 0.0),
                    "onerous_losses_and_reversals": (0.0, onerous, 0.0),
                    "past_service_lic": (0.0, 0.0, lic.loc[g, "past_service"] + lic.loc[g, "closing_ra"] - ra_lic_open),
                    "investment_components": (-det.loc[g, "act_investment_component"], 0.0, det.loc[g, "act_investment_component"]),
                    "insurance_finance": (finance - lc_fin, lc_fin, 0.0),
                    "premiums_received": (det.loc[g, "act_premiums"], 0.0, 0.0),
                    "claims_and_expenses_paid": (0.0, 0.0, -(det.loc[g, "act_outflows"] - lic.loc[g, "incurred_current"]
                                                              + lic.loc[g, "investment_component_incurred"] if "investment_component_incurred" in lic else
                                                              det.loc[g, "act_outflows"] - lic.loc[g, "incurred_current"])
                                                      + lic.loc[g, "paid"] - (det.loc[g, "act_investment_component"]
                                                                              - (lic.loc[g, "investment_component_incurred"] if "investment_component_incurred" in lic else 0.0))),
                    "acquisition_paid": (-det.loc[g, "act_acquisition"], 0.0, 0.0),
                }
                for line, (a, b, cc) in lines.items():
                    rows.append({"closing": out.closing, "portfolio": port, "group": g, "line": line,
                                 "lrc_excl_lc": a, "loss_component": b, "lic": cc})
                rows.append({"closing": out.closing, "portfolio": port, "group": g, "line": "closing",
                             "lrc_excl_lc": c.lrc - c.loss_component, "loss_component": c.loss_component,
                             "lic": lic.loc[g, "closing_pv"] + lic.loc[g, "closing_ra"]})
                prev_lic[g] = (lic.loc[g, "closing_pv"], lic.loc[g, "closing_ra"])
    # PAA portfolios: LIC split into PV and RA (par. 100(c))
    prev = {}
    for lrc, pnl, lic in zip(res["paa"]["lrc"], res["paa"]["pnl"], res["paa"]["lic"]):
        m = lrc.merge(pnl, on=["closing", "line", "group"], how="left")
        for _, r in m.iterrows():
            g = r["group"]
            o = prev.get(g, {"lrc": 0.0, "lc": 0.0})
            deferred = pc.LINES[r["line"]]["defer_acquisition"]
            gl = lic[lic["group"] == g]
            expenses = r["premium_taxes"] + r["attributable_expenses"] + (0.0 if deferred else r["acquisition_expense"])
            lines = {
                "opening": (o["lrc"], o["lc"], r["lic_open_pv"], r["lic_open_ra"]),
                "insurance_revenue": (-r["insurance_revenue"], 0.0, 0.0, 0.0),
                "incurred_claims_and_expenses": (0.0, 0.0, r["incurred_claims_current"] + expenses, 0.0),
                "acquisition_amortisation": (r["acquisition_expense"] if deferred else 0.0, 0.0, 0.0, 0.0),
                "onerous_losses_and_reversals": (0.0, r["onerous_losses"], 0.0, 0.0),
                "past_service_lic": (0.0, 0.0, r["past_service_changes"], r["ra_lic_change"]),
                "insurance_finance": (0.0, 0.0, r["ifie"], 0.0),
                "premiums_received": (r["premiums_received"], 0.0, 0.0, 0.0),
                "claims_and_expenses_paid": (0.0, 0.0, -(r["lic_paid"] + expenses), 0.0),
                "acquisition_paid": (-r["acq_paid"] if deferred else 0.0, 0.0, 0.0, 0.0),
            }
            for line, (a, b, cpv, cra) in lines.items():
                rows.append({"closing": r["closing"], "portfolio": r["line"], "group": g, "line": line,
                             "lrc_excl_lc": a, "loss_component": b, "lic": cpv + cra, "lic_pv": cpv, "lic_ra": cra})
            rows.append({"closing": r["closing"], "portfolio": r["line"], "group": g, "line": "closing",
                         "lrc_excl_lc": r["lrc_excl_lc"], "loss_component": r["loss_component"],
                         "lic": gl["pv"].sum() + gl["ra"].sum(), "lic_pv": gl["pv"].sum(), "lic_ra": gl["ra"].sum()})
            prev[g] = {"lrc": r["lrc_excl_lc"], "lc": r["loss_component"]}
    df = pd.DataFrame(rows).fillna({"lic_pv": np.nan, "lic_ra": np.nan})
    return df


def check_100(table: pd.DataFrame) -> pd.DataFrame:
    """Opening plus movements minus closing, by portfolio, closing and column (should be zero)."""
    cols = ["lrc_excl_lc", "loss_component", "lic"]
    mov = table[table["line"] != "closing"].groupby(["portfolio", "closing"])[cols].sum()
    clo = table[table["line"] == "closing"].groupby(["portfolio", "closing"])[cols].sum()
    return (mov - clo).round(6)


# --------------------------------------------------------------------------
# par. 101 and 104: PV of future cash flows, RA and CSM (GMM, issued and held)
# --------------------------------------------------------------------------
LINE_101 = {
    "future_service_csm": "Cambios en estimaciones que ajustan el CSM (104(a)(i))",
    "future_service_onerous": "Cambios que no ajustan el CSM: pérdidas y reversiones (104(a)(ii))",
    "loss_recovery_income": "Recuperación de pérdidas del reaseguro (66A, 66(c)(i))",
    "new_contracts": "Contratos reconocidos en el periodo (104(a)(iii))",
    "csm_release": "CSM reconocido por servicios prestados (104(b)(i))",
    "ra_release": "Cambio del ajuste por riesgo (104(b)(ii))",
    "experience": "Ajustes por experiencia (104(b)(iii))",
    "finance": "Ingresos o gastos financieros de seguros (105(c))",
    "premiums_received": "Primas recibidas (105(a)(i))",
    "claims_and_expenses_incurred": "Siniestros y gastos incurridos transferidos al LIC (105(a)(iii))",
    "investment_components": "Componentes de inversión (105(a)(iii))",
    "acquisition_cash_flows": "Flujos de adquisición pagados (105(a)(ii))",
}


def reconciliation_101(res: dict) -> pd.DataFrame:
    rows = []
    sources = [("VT", [(o.closing, o.results) for o in res["vt"]["closings"]], 1.0),
               ("VA", [(o.closing, o.results) for o in res["va"]["closings"]], 1.0),
               ("RE_VT", [(o["closing"], o["results"]) for o in res["re"]["closings"]], -1.0)]
    for port, items, sign in sources:
        for closing, results in items:
            for g, r in results.items():
                o, c = r.opening, r.closing
                rows.append({"closing": closing, "portfolio": port, "group": g, "line": "opening",
                             "pv": sign * o.pv_current, "ra": sign * o.ra, "csm": sign * o.csm})
                for line, v in r.movements.items():
                    rows.append({"closing": closing, "portfolio": port, "group": g, "line": line,
                                 "pv": sign * v["pv"], "ra": sign * v["ra"], "csm": sign * v["csm"]})
                rows.append({"closing": closing, "portfolio": port, "group": g, "line": "closing",
                             "pv": sign * c.pv_current, "ra": sign * c.ra, "csm": sign * c.csm})
    df = pd.DataFrame(rows)
    df["total"] = df[["pv", "ra", "csm"]].sum(axis=1)
    return df


# --------------------------------------------------------------------------
# par. 106-109
# --------------------------------------------------------------------------
def revenue_analysis(res: dict) -> pd.DataFrame:
    rows = []
    for key, port in (("vt", "VT"), ("va", "VA")):
        for out in res[key]["closings"]:
            for g, r in out.results.items():
                p = r.pnl
                rows.append({"closing": out.closing, "portfolio": port, "group": g,
                             "expected_claims_and_expenses": p["revenue_expected_claims_expenses"],
                             "loss_component_exclusion": p["revenue_loss_component_exclusion"],
                             "ra_release": p["revenue_ra_release"], "csm_release": p["revenue_csm_release"],
                             "acquisition_recovery": p["revenue_acquisition_recovery"],
                             "insurance_revenue": p["insurance_revenue"]})
    return pd.DataFrame(rows)


def new_business(res: dict) -> pd.DataFrame:
    rows = []
    for key, port in (("vt", "VT"), ("va", "VA")):
        for out in res[key]["closings"]:
            det = out.details.set_index("group")
            for g, r in out.results.items():
                if not det.loc[g, "nb_pv_inflows"]:
                    continue
                rows.append({"closing": out.closing, "portfolio": port, "group": g, "onerous": g.endswith("ONE"),
                             "pv_acquisition_outflows": det.loc[g, "nb_acquisition"],
                             "pv_other_outflows": det.loc[g, "nb_pv_outflows"] - det.loc[g, "nb_acquisition"],
                             "pv_inflows": -det.loc[g, "nb_pv_inflows"], "ra": det.loc[g, "nb_ra"],
                             "csm": r.movements["new_contracts"]["csm"], "loss": r.movements["new_contracts"]["loss"]})
    return pd.DataFrame(rows)


BANDS = [("1", 0, 1), ("2", 1, 2), ("3", 2, 3), ("4", 3, 4), ("5", 4, 5), ("6-10", 5, 10), (">10", 10, 200)]


def csm_release_bands(res: dict, closing: str = LAST) -> pd.DataFrame:
    """Expected recognition of the closing CSM in profit or loss, by year band (par. 109)."""
    rows = []
    for key, port in (("vt", "VT"), ("va", "VA")):
        out = next(o for o in res[key]["closings"] if o.closing == closing)
        det = out.details.set_index("group")
        for g, r in out.results.items():
            cu = np.asarray(det.loc[g, "cu_by_year"], float)
            if not cu.size or cu.sum() == 0:
                continue
            for band, a, b in BANDS:
                rows.append({"portfolio": port, "group": g, "band": band, "csm": r.closing.csm * cu[a:b].sum() / cu.sum()})
            if port == "VT":  # the treaty of the same cohort runs off with the ceded sum insured
                t = "RE-" + g.split("-")[1]
                re_r = next(o for o in res["re"]["closings"] if o["closing"] == closing)["results"][t]
                share = cu.sum() / sum(np.asarray(det.loc[h, "cu_by_year"], float).sum() for h in det.index
                                       if h.split("-")[1] == g.split("-")[1] and len(det.loc[h, "cu_by_year"]))
                for band, a, b in BANDS:
                    rows.append({"portfolio": "RE_VT", "group": t, "band": band,
                                 "csm": -re_r.closing.csm * share * cu[a:b].sum() / cu.sum()})
    df = pd.DataFrame(rows)
    return df.groupby(["portfolio", "band"], sort=False)["csm"].sum().unstack("band")[[b for b, _, _ in BANDS]]


# --------------------------------------------------------------------------
# par. 117-120: assumptions, discount rates and confidence level
# --------------------------------------------------------------------------
def discount_rates_table() -> pd.DataFrame:
    rows = []
    for c in A.CLOSINGS:
        month = c[:7]
        for port in ("VT", "VA", "AUTO", "TRC"):
            curve = curve_for(month, port)
            rows.append({"closing": c, "portfolio": port, **{f"{m}y": float(curve.spot(float(m))[0]) for m in (1, 5, 10, 20, 30, 40)}})
    return pd.DataFrame(rows)


def assumptions_table() -> pd.DataFrame:
    rows = []
    for c in A.CLOSINGS:
        st = mortality_study("vt", c)
        for _, r in st.iterrows():
            rows.append({"closing": c, "assumption": f"mortalidad ({r['segment']})", "value": r["best_estimate_factor"],
                         "basis": "factor sobre CSO 1980", "own_factor": r["own_factor"], "credibility": r["credibility"]})
    rows += [{"closing": "todos", "assumption": "mejora de mortalidad", "value": A.MORTALITY_IMPROVEMENT, "basis": "anual"},
             {"closing": "todos", "assumption": "caducidad vida temporal (años 1, 2, 3+)", "value": str(A.TERM_LIFE.lapse), "basis": "anual"},
             {"closing": "todos", "assumption": "caducidad vida con ahorro (años 1-7+)", "value": str(A.SAVINGS_LIFE.lapse), "basis": "anual"},
             {"closing": "todos", "assumption": "inflación de gastos", "value": A.EXPENSE_INFLATION, "basis": "anual"},
             {"closing": "todos", "assumption": "diferencial de tasa acreditada", "value": A.SAVINGS_LIFE.crediting_spread,
              "basis": "HQM a 1 año menos diferencial, mínimo 2,5% (B98)"}]
    return pd.DataFrame(rows)


def _vt_context(res: dict, closing: str = LAST):
    pol = res["vt"]["policies"]
    inforce = life_inforce("vt", closing).merge(pol[["policy_id", "group"]], on="policy_id")
    t1 = pd.Timestamp(closing)
    e1 = ((t1.year - inforce["issue_date"].dt.year) * 12 + (t1.month - inforce["issue_date"].dt.month) + 1).to_numpy()
    _, f1 = term_life.basis_at(closing)
    return term_life.with_factors(inforce, f1), e1, curve_for(closing[:7], "VT")


def confidence_levels(res: dict, closing: str = LAST) -> pd.DataFrame:
    """Confidence level of the risk adjustment (par. 119): life by a normal approximation
    (sigma = 99.5% capital / 2.576), P&C from the lognormal aggregation."""
    pols, e1, curve = _vt_context(res, closing)
    ra = term_life_risk_adjustment(pols, BEST_ESTIMATE, curve.discount, elapsed=e1)
    scr = float(aggregate(ra.shocks.sum(axis=0))[0])
    ra_total = sum(r.closing.ra for r in next(o for o in res["vt"]["closings"] if o.closing == closing).results.values())
    sigma = scr / norm.ppf(0.995)
    life_level = float(norm.cdf(ra_total / sigma)) if sigma else 1.0
    pcl = res["paa"]["lic"][A.CLOSINGS.index(closing)].attrs["confidence"]
    return pd.DataFrame([
        {"portfolio": "Vida temporal", "technique": "costo de capital 6%", "risk_adjustment": ra_total,
         "capital_99_5": scr, "confidence_level": life_level},
        {"portfolio": "Daños (LIC)", "technique": "percentil 75, lognormal, correlación 25%", "risk_adjustment": pcl["ra_total"],
         "capital_99_5": np.nan, "confidence_level": pcl["equivalent_level"]},
    ])


# --------------------------------------------------------------------------
# par. 128: sensitivities at the last closing
# --------------------------------------------------------------------------
def _shifted(curve: DiscountCurve, shift: float) -> DiscountCurve:
    return DiscountCurve(maturities=curve.maturities, spot_annual=np.maximum(curve.spot_annual + shift, -0.99))


def sensitivities(res: dict, closing: str = LAST) -> pd.DataFrame:
    """Effect on profit or loss and on equity of reasonably possible changes (par. 128(a)).

    Non-financial changes adjust the CSM unless they exceed it (onerous groups take them in
    profit or loss); the quota share recovers 40% of underlying losses (66(c)(i)), so the
    net effect on profit is 60% of the gross for term-life mortality. Rate changes move the
    current-rate PV: term life and its reinsurance in OCI, the rest and the assets in profit.
    """
    rows = []
    pols, e1, curve = _vt_context(res, closing)
    out = next(o for o in res["vt"]["closings"] if o.closing == closing)
    states = {g: r.closing for g, r in out.results.items()}
    base = project_term(pols, BEST_ESTIMATE, elapsed=e1).present_values(curve.discount)["net_outflow"].to_numpy()
    groups = pols["group"].to_numpy()
    for name, kw in (("mortalidad +10%", {"mortality_multiplier": 1.10}), ("mortalidad -10%", {"mortality_multiplier": 0.90}),
                     ("caducidad +10%", {"lapse_multiplier": 1.10}), ("caducidad -10%", {"lapse_multiplier": 0.90}),
                     ("gastos +10%", {"expense_multiplier": 1.10})):
        shocked = project_term(pols, BEST_ESTIMATE.stressed(**kw), elapsed=e1).present_values(curve.discount)["net_outflow"].to_numpy()
        pnl = 0.0
        for g in np.unique(groups):
            d = (shocked - base)[groups == g].sum()
            s = states[g]
            if d > 0:
                pnl -= max(d - s.csm, 0.0)
            else:
                pnl += min(-d, s.loss_component)
        net = pnl * (1 - A.REINSURANCE["quota_share"]) if "mortalidad" in name else pnl
        rows.append({"portfolio": "VT", "change": name, "profit_gross": pnl, "equity_gross": pnl,
                     "profit_net": net, "equity_net": net})
    for shift in (0.01, -0.01):
        shocked = project_term(pols, BEST_ESTIMATE, elapsed=e1).present_values(_shifted(curve, shift).discount)["net_outflow"].to_numpy()
        d = (shocked - base).sum()
        rows.append({"portfolio": "VT", "change": f"tasas {'+' if shift > 0 else '-'}100 pb", "profit_gross": 0.0,
                     "equity_gross": -d, "profit_net": 0.0, "equity_net": -d * (1 - A.REINSURANCE["quota_share"])})
    # savings life: same logic; a rate change also moves the projected crediting (B74(b)), all in profit
    va_rows = _savings_sensitivities(res, closing)
    rows += va_rows
    # P&C: claims +5% on the LIC and the remaining coverage; rates on the discounted LIC
    lic = res["paa"]["lic"][A.CLOSINGS.index(closing)]
    lrc = res["paa"]["lrc"][A.CLOSINGS.index(closing)]
    for line in pc.LINES:
        l_line = lic[lic["line"] == line]
        r_line = lrc[lrc["line"] == line]
        extra_lc = np.maximum(r_line["fcf_remaining"] + 0.05 * (r_line["pv_claims_remaining"] + r_line["ra_remaining"])
                              - r_line["lrc_excl_lc"], 0.0) - r_line["loss_component"]
        effect = -(0.05 * (l_line["pv"].sum() + l_line["ra"].sum()) + extra_lc.sum())
        rows.append({"portfolio": line, "change": "siniestros +5%", "profit_gross": effect, "equity_gross": effect,
                     "profit_net": effect, "equity_net": effect})
        if pc.LINES[line]["discount"]:
            for shift in (0.01, -0.01):
                c_s = _shifted(curve_for(closing[:7], line), shift)
                d = sum(row.pv * (pc.pv_factor(line, row.coverage, row.segment, row.accident_year, closing, "case", curve=c_s)
                                  / pc.pv_factor(line, row.coverage, row.segment, row.accident_year, closing, "case") - 1)
                        for row in l_line.itertuples())
                rows.append({"portfolio": line, "change": f"tasas {'+' if shift > 0 else '-'}100 pb", "profit_gross": -d,
                             "equity_gross": -d, "profit_net": -d, "equity_net": -d})
    st = C.statements(res)["balance_sheet"].loc[closing]
    for shift in (0.01, -0.01):
        d_oci = -C.FVOCI_DURATION * shift * st["investments_fvoci"]
        d_pl = -0.5 * shift * st["investments_fvpl"]
        rows.append({"portfolio": "Inversiones", "change": f"tasas {'+' if shift > 0 else '-'}100 pb", "profit_gross": d_pl,
                     "equity_gross": d_pl + d_oci, "profit_net": d_pl, "equity_net": d_pl + d_oci})
    return pd.DataFrame(rows)


def _savings_sensitivities(res: dict, closing: str) -> list:
    t1 = pd.Timestamp(closing)
    pol = res["va"]["policies"]
    inf = life_inforce("va", closing).merge(pol[["policy_id", "group"]], on="policy_id").reset_index(drop=True)
    e1 = ((t1.year - inf["issue_date"].dt.year) * 12 + (t1.month - inf["issue_date"].dt.month) + 1).to_numpy()
    av = load("va_account_values")
    av = av[av["closing"] == t1].set_index("policy_id")["account_value"].reindex(inf["policy_id"]).fillna(0.0).to_numpy()
    f1 = savings.mortality_factors("vt", closing)
    sub = savings.with_factors(inf, f1)
    cal = (t1.year - savings.BASE_YEAR) * 12 + t1.month
    T = int(((savings.P.maturity_age - inf["issue_age"]) * 12 - e1).max())
    out = next(o for o in res["va"]["closings"] if o.closing == closing)
    states = {g: r.closing for g, r in out.results.items()}
    groups = inf["group"].to_numpy()

    def net_by_group(basis, curve):
        cr = savings.crediting_rates(np.full(len(inf), cal), T, savings.year_rate_function(curve, t1.year + 1, t1.year))
        pr = savings.project_savings(sub, basis, e1, av, cr)
        D = savings._discount(pr, curve, np.zeros(len(inf)), np.zeros(len(inf)))
        return {g: savings.pv(pr, D, groups == g)["net"] for g in np.unique(groups)}

    curve = curve_for(closing[:7], "VA")
    base = net_by_group(savings.BEST_ESTIMATE, curve)
    rows = []
    for name, kw in (("mortalidad +10%", {"mortality_multiplier": 1.10}), ("caducidad +10%", {"lapse_multiplier": 1.10}),
                     ("caducidad -10%", {"lapse_multiplier": 0.90}), ("gastos +10%", {"expense_multiplier": 1.10})):
        shocked = net_by_group(savings.BEST_ESTIMATE.stressed(**kw), curve)
        pnl = 0.0
        for g, v in shocked.items():
            d = v - base[g]
            pnl += -max(d - states[g].csm, 0.0) if d > 0 else min(-d, states[g].loss_component)
        rows.append({"portfolio": "VA", "change": name, "profit_gross": pnl, "equity_gross": pnl, "profit_net": pnl, "equity_net": pnl})
    for shift in (0.01, -0.01):
        shocked = net_by_group(savings.BEST_ESTIMATE, _shifted(curve, shift))
        d = sum(shocked.values()) - sum(base.values())
        rows.append({"portfolio": "VA", "change": f"tasas {'+' if shift > 0 else '-'}100 pb", "profit_gross": -d,
                     "equity_gross": -d, "profit_net": -d, "equity_net": -d})
    return rows


# --------------------------------------------------------------------------
# par. 130 and 132
# --------------------------------------------------------------------------
def claims_development(line: str = "AUTO") -> pd.DataFrame:
    """Undiscounted estimates of ultimate claims by accident year at each closing, cumulative
    payments and the reconciliation to the LIC (par. 130)."""
    groups = pc.assign_groups(pc.classify())[line]
    claims = load(f"{pc.LINES[line]['table']}_claims")
    pay = load(f"{pc.LINES[line]['table']}_payments").merge(claims[["claim_id", "occurrence_date"]], on="claim_id")
    rows = []
    for c in A.CLOSINGS:
        lic = pc.lic_at(line, c, groups)
        paid = pay[pay["payment_date"] <= c].assign(ay=lambda d: d["occurrence_date"].dt.year).groupby("ay")["amount"].sum()
        for ay, g in lic.groupby("accident_year"):
            rows.append({"closing": c, "accident_year": int(ay), "paid_to_date": float(paid.get(ay, 0.0)),
                         "outstanding_undiscounted": g["undiscounted"].sum(), "lic_pv": g["pv"].sum()})
    df = pd.DataFrame(rows)
    df["ultimate_estimate"] = df["paid_to_date"] + df["outstanding_undiscounted"]
    return df


def maturity_analysis(res: dict, closing: str = LAST) -> pd.DataFrame:
    """Undiscounted net cash outflows expected in each of the next five years and after (par. 132(b)(i)).
    Groups measured with the PAA show only their LIC (132(b))."""
    rows = []
    for key, port in (("vt", "VT"), ("va", "VA")):
        out = next(o for o in res[key]["closings"] if o.closing == closing)
        lic = out.lic.set_index("group")
        for g in out.results:
            cf = np.asarray(out.details.set_index("group").loc[g, "net_cf_by_year"], float)
            years = np.zeros(6)
            years[: min(5, cf.size)] = cf[:5]
            years[5] = cf[5:].sum()
            years[0] += lic.loc[g, "closing_pv"]
            rows.append({"portfolio": port, **{f"año {i + 1}": years[i] for i in range(5)}, "más de 5 años": years[5]})
    lic = res["paa"]["lic"][A.CLOSINGS.index(closing)]
    for line in pc.LINES:
        years = np.zeros(6)
        for row in lic[lic["line"] == line].itertuples():
            for kind, amt in (("case", row.case), ("ibnr", row.ibnr)):
                times, shares = pc.outstanding_schedule(row.coverage, row.segment, row.accident_year, closing, kind)
                for t, s in zip(times, shares):
                    years[min(int(t), 5)] += amt * (1 + A.ULAE_RATE) * s
        rows.append({"portfolio": line, **{f"año {i + 1}": years[i] for i in range(5)}, "más de 5 años": years[5]})
    return pd.DataFrame(rows).groupby("portfolio", sort=False).sum()


def ifrs18_profit_or_loss(pl: pd.DataFrame) -> pd.DataFrame:
    """The same profit or loss in the IFRS 18 categories (Annex A): insurance is the main
    business activity, so investment income and insurance finance results are operating
    (IFRS 18.55-58, 18.64); there is no financing or income-tax line in scope."""
    out = pd.DataFrame(index=pl.index)
    out["insurance_service_result"] = pl["insurance_service_result"]
    out["investment_income"] = pl["investment_income"]
    out["insurance_finance"] = pl["insurance_finance_expenses"] + pl["reinsurance_finance_income"]
    out["other_operating_expenses"] = pl["other_operating_expenses"]
    out["operating_profit"] = out.sum(axis=1)  # IFRS 18.69(a)
    out["profit_before_financing_and_income_taxes"] = out["operating_profit"]  # 18.69(b): no investing or financing items
    out["profit"] = pl["profit_before_tax"]
    return out
