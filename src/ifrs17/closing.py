"""Closings of Seguros Baru: every portfolio, the investments and the financial statements (Phase 6).

``run()`` measures all portfolios for 2023-2025 (term life, savings life, reinsurance
held and the three PAA portfolios) and caches the result. ``statements()`` builds the
statement of financial position (par. 78-79), the statement of profit or loss and OCI
(par. 80-92) and checks that assets less liabilities equal equity.

Investments (IFRS 9) are kept deliberately simple: the assets backing term life net of
reinsurance are a Treasury bond portfolio at fair value through OCI with an 8-year
duration (memo section 3), rebalanced at each year end; everything else is held in short
Treasuries at fair value through profit or loss earning the one-year rate. Income tax is
out of scope.
"""

from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import assumptions as A
from . import pc, reinsurance, savings, term_life
from .data import load

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
CACHE = RESULTS / "run.pkl"
CAPITAL = 20_000_000.0
FVOCI_DURATION = 8.0
YEARS = [2023, 2024, 2025]


def run(refresh: bool = False) -> dict:
    if CACHE.exists() and not refresh:
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    vt = term_life.run_all()
    re = reinsurance.run_all(vt)
    va = savings.run_all()
    paa = pc.run_all()
    out = {"vt": vt, "re": re, "va": va, "paa": paa}
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(out, f)
    return out


# --------------------------------------------------------------------------
# group-level tables
# --------------------------------------------------------------------------
def gmm_table(res: dict) -> pd.DataFrame:
    """One row per GMM group and closing: balances, P&L and cash flows (contracts issued and held)."""
    rows = []
    for key, portfolio in (("vt", "VT"), ("va", "VA")):
        for out in res[key]["closings"]:
            lic = out.lic.set_index("group")
            det = out.details.set_index("group")
            for g, r in out.results.items():
                c, p, mv = r.closing, r.pnl, r.movements
                rows.append({
                    "closing": out.closing, "portfolio": portfolio, "group": g, "held": False,
                    "pv": c.pv_current, "ra": c.ra, "csm": c.csm, "loss_component": c.loss_component,
                    "lrc": c.lrc, "lic_pv": lic.loc[g, "closing_pv"], "lic_ra": lic.loc[g, "closing_ra"],
                    "insurance_revenue": p["insurance_revenue"],
                    "ise": p["insurance_service_expenses"] + lic.loc[g, "past_service"]
                    + lic.loc[g, "closing_ra"] - (lic_prev_ra(res, key, out.closing, g)),
                    "ise_past_service": lic.loc[g, "past_service"],
                    "ifie_pnl": p["ifie_pnl"], "ifie_oci": p["ifie_oci"],
                    "premiums_received": mv["premiums_received"]["pv"], "acquisition_paid": -mv["acquisition_cash_flows"]["pv"],
                    "investment_components": -mv["investment_components"]["pv"], "lic_paid": -lic.loc[g, "paid"],
                    "csm_release": -mv["csm_release"]["csm"], "ra_release": -mv["ra_release"]["ra"],
                    "nb_pv_inflows": det.loc[g, "nb_pv_inflows"], "nb_pv_outflows": det.loc[g, "nb_pv_outflows"],
                    "nb_acquisition": det.loc[g, "nb_acquisition"], "nb_ra": det.loc[g, "nb_ra"],
                    "nb_csm": mv["new_contracts"]["csm"], "nb_loss": mv["new_contracts"]["loss"],
                    "cu_by_year": det.loc[g, "cu_by_year"] if "cu_by_year" in det else [],
                    "net_cf_by_year": det.loc[g, "net_cf_by_year"] if "net_cf_by_year" in det else [],
                })
    for out in res["re"]["closings"]:
        rec = out["recoverable_incurred"]
        for t, r in out["results"].items():
            pr = reinsurance.presentation(r)
            c = r.closing
            prev = _prev_recoverable(res, out["closing"], t)
            rows.append({
                "closing": out["closing"], "portfolio": "RE_VT", "group": t, "held": True,
                "pv": -c.pv_current, "ra": -c.ra, "csm": -c.csm, "loss_component": -c.loss_component,
                "lrc": -c.lrc, "lic_pv": -rec.loc[t, "ceded_lic_ben"], "lic_ra": 0.0,
                "insurance_revenue": 0.0, "ise": 0.0, "ise_past_service": 0.0,
                "reinsurance_allocation": pr["allocation_of_premiums_paid"],
                "reinsurance_recovered": pr["amounts_recovered"] + (rec.loc[t, "ceded_lic_ben"] - prev - rec.loc[t, "ceded_act_ben"]
                                                                    + rec.loc[t, "ceded_paid_ben"]),
                "ifie_pnl": pr["finance_pnl"], "ifie_oci": pr["finance_oci"],
                "premiums_received": -r.movements["premiums_received"]["pv"], "acquisition_paid": 0.0,
                "investment_components": 0.0, "lic_paid": -rec.loc[t, "ceded_paid_ben"],
                "csm_release": -r.movements["csm_release"]["csm"], "ra_release": -r.movements["ra_release"]["ra"],
                "nb_csm": -r.movements["new_contracts"]["csm"], "nb_loss": 0.0,
                "loss_recovery_income": pr["loss_recovery_income"],
            })
    return pd.DataFrame(rows)


def lic_prev_ra(res, key, closing, group) -> float:
    closings = [o.closing for o in res[key]["closings"]]
    i = closings.index(closing)
    if i == 0:
        return 0.0
    prev = res[key]["closings"][i - 1].lic.set_index("group")
    return float(prev.loc[group, "closing_ra"]) if group in prev.index else 0.0


def _prev_recoverable(res, closing, treaty) -> float:
    closings = [o["closing"] for o in res["re"]["closings"]]
    i = closings.index(closing)
    if i == 0:
        return 0.0
    prev = res["re"]["closings"][i - 1]["recoverable_incurred"]
    return float(prev.loc[treaty, "ceded_lic_ben"]) if treaty in prev.index else 0.0


def paa_table(res: dict) -> pd.DataFrame:
    rows = []
    for lrc, pnl, lic in zip(res["paa"]["lrc"], res["paa"]["pnl"], res["paa"]["lic"]):
        m = lrc.merge(pnl, on=["closing", "line", "group"], how="left")
        for _, r in m.iterrows():
            gl = lic[lic["group"] == r["group"]]
            rows.append({
                "closing": r["closing"], "portfolio": r["line"], "group": r["group"], "held": False,
                "lrc_excl_lc": r["lrc_excl_lc"], "loss_component": r["loss_component"],
                "lrc": r["lrc_excl_lc"] + r["loss_component"], "lic_pv": gl["pv"].sum(), "lic_ra": gl["ra"].sum(),
                "insurance_revenue": r["insurance_revenue"], "ise": r["insurance_service_expenses"],
                "ise_past_service": r["past_service_changes"], "ifie_pnl": r["ifie"], "ifie_oci": 0.0,
                "premiums_received": r["premiums_received"], "acquisition_paid": r["acq_paid"],
                "lic_paid": r["lic_paid"], "taxes_paid": r["premium_taxes"], "expenses_paid": r["attributable_expenses"],
                "incurred_current": r["incurred_claims_current"], "acquisition_expense": r["acquisition_expense"],
                "onerous": r["onerous_losses"],
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# cash, investments and statements
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _tnc() -> pd.DataFrame:
    t = pd.read_csv(ROOT / "data" / "processed" / "tnc_hqm_eom.csv")
    t = t[t["curve"] == "TNC"].set_index("month").drop(columns="curve")
    t.columns = t.columns.astype(float)
    return t / 100.0


def tnc_rate(month: str, maturity: float) -> float:
    semi = float(_tnc().loc[month, maturity])
    return (1 + semi / 2) ** 2 - 1


def operating_cash_flows() -> pd.DataFrame:
    """Cash in and out of insurance operations by calendar year, straight from the records."""
    rows = []
    for y in YEARS:
        lo, hi = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")
        r = {"year": y}
        for prod in ("vt", "va"):
            tx = load(f"{prod}_transactions")
            tx = tx[(tx["date"] >= lo) & (tx["date"] <= hi)]
            r[f"{prod}_premiums"] = tx.loc[tx["type"] == "premium", "amount"].sum()
            r[f"{prod}_commissions"] = -tx.loc[tx["type"] == "commission", "amount"].sum()
            r[f"{prod}_taxes"] = -tx.loc[tx["type"] == "premium_tax", "amount"].sum()
            r[f"{prod}_surrenders"] = -tx.loc[tx["type"] == "surrender", "amount"].sum()
            cl = load(f"{prod}_claims")
            cl = cl[(cl["payment_date"] >= lo) & (cl["payment_date"] <= hi)]
            r[f"{prod}_claims"] = -(cl["amount"] + cl["claim_expense"]).sum()
            if prod == "vt":
                r["re_premiums"] = -A.REINSURANCE["quota_share"] * (1 - A.REINSURANCE["ceding_commission"]) * r["vt_premiums"]
                r["re_recoveries"] = A.REINSURANCE["quota_share"] * cl["amount"].sum()
        for line in ("auto", "inc", "trc"):
            pr = load(f"{line}_premiums")
            pr = pr[(pr["date"] >= lo) & (pr["date"] <= hi)]
            r[f"{line}_premiums"] = pr["premium"].sum()
            r[f"{line}_commissions"] = -pr["commission"].sum()
            r[f"{line}_taxes"] = -(pr["premium_tax"].sum() + (pr["fire_levy"].sum() if "fire_levy" in pr else 0.0))
            pay = load(f"{line}_payments")
            r[f"{line}_claims"] = -pay[(pay["payment_date"] >= lo) & (pay["payment_date"] <= hi)]["amount"].sum()
        ex = load("expenses")
        ex = ex[ex["month"].str[:4] == str(y)]
        r["expenses_attributable"] = -ex.loc[ex["portfolio"] != "ENTITY", "amount"].sum()
        r["expenses_other"] = -ex.loc[ex["portfolio"] == "ENTITY", "amount"].sum()
        rows.append(r)
    df = pd.DataFrame(rows).set_index("year")
    df["net_operating"] = df.sum(axis=1)
    return df


def statements(res: dict | None = None) -> dict:
    res = run() if res is None else res
    g = gmm_table(res)
    p = paa_table(res)
    cash = operating_cash_flows()
    closings = list(A.CLOSINGS)
    bs, pl = [], []
    fv_oci = ac_oci = 0.0
    fvpl = CAPITAL
    retained = oci_ins = oci_re = 0.0
    book_yield = None
    prev_month = "2023-01"
    for y, c in zip(YEARS, closings):
        gg, pp = g[g["closing"] == c], p[p["closing"] == c]
        month = f"{y}-12"
        # investment income on opening balances and half a year on the year's net operating cash
        y_short = tnc_rate(prev_month, 1.0)
        y_long_open, y_long_close = tnc_rate(prev_month, FVOCI_DURATION), tnc_rate(month, FVOCI_DURATION)
        book_yield = y_long_open if book_yield is None else book_yield
        income_fvpl = fvpl * y_short + cash.loc[y, "net_operating"] * y_short / 2
        income_oci = ac_oci * book_yield
        price_change = -FVOCI_DURATION * (y_long_close - y_long_open) * fv_oci if y > YEARS[0] else 0.0
        total_assets_before = fvpl + fv_oci + cash.loc[y, "net_operating"] + income_fvpl + income_oci + price_change
        # rebalance: hold the term-life liability net of reinsurance in the FVOCI portfolio
        vt = gg[gg["portfolio"].isin(["VT", "RE_VT"])]
        target = CAPITAL + max(0.0, (vt["lrc"] + vt["lic_pv"] + vt["lic_ra"]).sum())  # capital and term-life funds
        fv_new = fv_oci + income_oci + price_change
        buy = target - fv_new
        book_yield = (book_yield * (ac_oci + income_oci) + y_long_close * max(buy, 0.0)) / max(ac_oci + income_oci + max(buy, 0.0), 1.0)
        ac_oci = ac_oci + income_oci + buy
        fv_oci = target
        fvpl = total_assets_before - fv_oci
        reserve_fvoci = fv_oci - ac_oci

        issued = pd.concat([gg[~gg["held"]], pp])
        held = gg[gg["held"]]
        liab_by_port = issued.assign(total=issued["lrc"] + issued["lic_pv"] + issued["lic_ra"]).groupby(["portfolio", "group"])["total"].sum()
        contract_liab = liab_by_port[liab_by_port > 0].sum()
        contract_asset = -liab_by_port[liab_by_port < 0].sum()
        re_asset = -(held["lrc"] + held["lic_pv"]).sum()

        revenue = issued["insurance_revenue"].sum()
        ise = issued["ise"].sum()
        re_net = (held["reinsurance_allocation"] + held["reinsurance_recovered"]).sum()
        isr = revenue - ise + re_net
        ifie_issued = issued["ifie_pnl"].sum()
        ifie_held = held["ifie_pnl"].sum()
        inv_income = income_fvpl + income_oci
        other = cash.loc[y, "expenses_other"]
        profit = isr + inv_income - ifie_issued + ifie_held + other
        oci_ins_y = -issued["ifie_oci"].sum()
        oci_re_y = held["ifie_oci"].sum()
        oci_assets_y = price_change
        retained += profit
        oci_ins += oci_ins_y
        oci_re += oci_re_y
        equity = CAPITAL + retained + oci_ins + oci_re + reserve_fvoci
        assets = fvpl + fv_oci + contract_asset + re_asset
        liabilities = contract_liab
        pl.append({"year": y, "insurance_revenue": revenue, "insurance_service_expenses": -ise,
                   "net_reinsurance": re_net, "insurance_service_result": isr, "investment_income": inv_income,
                   "insurance_finance_expenses": -ifie_issued, "reinsurance_finance_income": ifie_held,
                   "net_financial_result": inv_income - ifie_issued + ifie_held, "other_operating_expenses": other,
                   "profit_before_tax": profit, "oci_insurance_finance": oci_ins_y, "oci_reinsurance_finance": oci_re_y,
                   "oci_fvoci_assets": oci_assets_y, "total_comprehensive_income": profit + oci_ins_y + oci_re_y + oci_assets_y})
        bs.append({"closing": c, "investments_fvpl": fvpl, "investments_fvoci": fv_oci,
                   "insurance_contract_assets": contract_asset, "reinsurance_contract_assets": re_asset,
                   "total_assets": assets, "insurance_contract_liabilities": contract_liab, "total_liabilities": liabilities,
                   "share_capital": CAPITAL, "retained_earnings": retained, "insurance_finance_reserve": oci_ins + oci_re,
                   "fvoci_reserve": reserve_fvoci, "total_equity": equity,
                   "balance_check": assets - liabilities - equity})
        prev_month = month
    return {"balance_sheet": pd.DataFrame(bs).set_index("closing"), "profit_or_loss": pd.DataFrame(pl).set_index("year"),
            "cash": cash, "gmm": g, "paa": p}
