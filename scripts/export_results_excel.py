"""Excel reconciliation of the closings, with live formulas (Phase 6).

    python scripts/run_closings.py
    python scripts/export_results_excel.py

Writes excel/Cierres_IFRS17_Seguros_Baru.xlsx. Amounts that come from the Python engine
are blue values; every subtotal, every closing balance and every opening balance after
the first year is an Excel formula, and each sheet ends with control cells that compare
the formulas with the engine (they must show zero).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data" / "results"
OUT = ROOT / "excel" / "Cierres_IFRS17_Seguros_Baru.xlsx"

F = "Arial"
BLUE, GREEN, BLACK = "0000FF", "008000", "000000"
HEAD = PatternFill("solid", fgColor="DDE6F0")
SUB = PatternFill("solid", fgColor="F2F2F2")
CHECK = PatternFill("solid", fgColor="E2EFDA")
THIN = Border(bottom=Side(style="thin", color="999999"))
NUM = '#,##0;(#,##0);"-"'
PCT = "0.00%"
YEARS = ["2023", "2024", "2025"]
CLOSINGS = ["2023-12-31", "2024-12-31", "2025-12-31"]
NAMES = {"VT": "Vida temporal", "VA": "Vida con ahorro", "AUTO": "Autos", "INC": "Incendio/hogar",
         "TRC": "Todo riesgo construcción", "RE_VT": "Reaseguro cedido sobre vida temporal"}
CHECKS: list[str] = []


def fnt(color=BLACK, bold=False, italic=False, size=10):
    return Font(name=F, color=color, bold=bold, italic=italic, size=size)


def put(ws, r, c, v, color=BLACK, bold=False, fmt=None, fill=None, italic=False):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = fnt(color, bold, italic)
    if fmt:
        cell.number_format = fmt
    if fill:
        cell.fill = fill
    return cell


def header(ws, r, labels, start=1):
    for j, lab in enumerate(labels, start=start):
        c = put(ws, r, j, lab, bold=True, fill=HEAD)
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        c.border = THIN
    ws.row_dimensions[r].height = 32


def title(ws, text, note):
    put(ws, 1, 1, text, bold=True).font = fnt(bold=True, size=13)
    put(ws, 2, 1, note, italic=True)


def widths(ws, w):
    for j, x in enumerate(w, start=1):
        ws.column_dimensions[get_column_letter(j)].width = x


# --------------------------------------------------------------------------
def sheet_cover(wb):
    ws = wb.active
    ws.title = "Portada"
    title(ws, "Seguros Barú, S.A. — Cierres IFRS 17 de 2023, 2024 y 2025",
          "Aseguradora ficticia; datos sintéticos generados con semilla fija. Cifras en USD.")
    rows = [
        ("Leyenda", ""),
        ("Azul", "valor calculado por el motor en Python (src/ifrs17)"),
        ("Negro", "fórmula de Excel"),
        ("Verde", "vínculo a otra hoja"),
        ("Fondo verde claro", "celda de control: debe ser cero"),
        ("", ""),
        ("Hoja", "Contenido"),
        ("EEFF", "Estado de situación financiera (par. 78-79) y de resultados y ORI (par. 80-92)"),
        ("Conc_100", "Conciliación LRC sin componente de pérdida, componente de pérdida y LIC (par. 100, 103)"),
        ("Conc_101", "Conciliación de valor presente, ajuste por riesgo y CSM, contratos GMM y reaseguro (par. 101, 104)"),
        ("Ingresos_106", "Análisis de los ingresos por seguros de los grupos GMM (par. 106)"),
        ("NegocioNuevo_107", "Efecto de los contratos reconocidos en el periodo (par. 107)"),
        ("CSM_109", "Reconocimiento esperado del CSM por bandas de años (par. 109)"),
        ("Supuestos", "Supuestos, curvas de descuento y nivel de confianza (par. 117, 119, 120)"),
        ("Sensibilidades_128", "Efecto en resultados y patrimonio de cambios razonablemente posibles (par. 128)"),
        ("Desarrollo_130", "Desarrollo de siniestros de autos y TRC (par. 130)"),
        ("Liquidez_132", "Vencimientos de flujos netos esperados (par. 132)"),
        ("Controles", "Resumen de todas las celdas de control"),
    ]
    for i, (a, b) in enumerate(rows, start=4):
        put(ws, i, 1, a, bold=a in ("Leyenda", "Hoja"))
        put(ws, i, 2, b)
    put(ws, 5, 1, "Azul", BLUE)
    put(ws, 7, 1, "Verde", GREEN)
    ws.cell(row=8, column=1).fill = CHECK
    widths(ws, [22, 100])


def sheet_statements(wb, bs: pd.DataFrame, pl: pd.DataFrame):
    ws = wb.create_sheet("EEFF")
    title(ws, "Estados financieros", "Sin impuesto sobre la renta (fuera de alcance). Presentación con NIC 1; ver el anexo IFRS 18 al final.")
    header(ws, 4, ["Estado de situación financiera", *[f"31-dic-{y}" for y in YEARS]])
    lines = [("Inversiones a valor razonable con cambios en resultados", "investments_fvpl"),
             ("Inversiones a valor razonable con cambios en ORI", "investments_fvoci"),
             ("Activos por contratos de seguro", "insurance_contract_assets"),
             ("Activos por contratos de reaseguro cedido", "reinsurance_contract_assets")]
    r = 5
    for lab, col in lines:
        put(ws, r, 1, lab)
        for j, c in enumerate(CLOSINGS, start=2):
            put(ws, r, j, float(bs.loc[c, col]), BLUE, fmt=NUM)
        r += 1
    put(ws, r, 1, "Total activos", bold=True)
    for j in range(2, 5):
        L = get_column_letter(j)
        put(ws, r, j, f"=SUM({L}5:{L}{r - 1})", bold=True, fmt=NUM, fill=SUB)
    ta = r
    r += 2
    put(ws, r, 1, "Pasivos por contratos de seguro")
    for j, c in enumerate(CLOSINGS, start=2):
        put(ws, r, j, float(bs.loc[c, "insurance_contract_liabilities"]), BLUE, fmt=NUM)
    tl = r
    r += 2
    eq0 = r
    put(ws, r, 1, "Capital social")
    for j, c in enumerate(CLOSINGS, start=2):
        put(ws, r, j, float(bs.loc[c, "share_capital"]), BLUE, fmt=NUM)
    re_row, ins_row, oci_row = r + 1, r + 2, r + 3
    put(ws, re_row, 1, "Resultados acumulados")
    put(ws, ins_row, 1, "Reserva de finanzas de seguros (ORI)")
    put(ws, oci_row, 1, "Reserva de inversiones a valor razonable con cambios en ORI")
    # profit or loss block positions (filled below)
    pl_top = oci_row + 6
    pl_rows = {}
    lines_pl = [("Ingresos por seguros", "insurance_revenue"), ("Gastos del servicio de seguros", "insurance_service_expenses"),
                ("Resultado neto de los contratos de reaseguro cedido", "net_reinsurance")]
    rr = pl_top + 1
    for lab, col in lines_pl:
        pl_rows[col] = rr
        rr += 1
    pl_rows["isr"] = rr
    rr += 2
    for lab, col in [("Ingresos de inversiones", "investment_income"), ("Gastos financieros de seguros emitidos", "insurance_finance_expenses"),
                     ("Ingresos financieros del reaseguro cedido", "reinsurance_finance_income")]:
        pl_rows[col] = rr
        rr += 1
    pl_rows["fin"] = rr
    rr += 2
    pl_rows["other_operating_expenses"] = rr
    pl_rows["profit"] = rr + 2
    oci_lines = [("Finanzas de seguros emitidos", "oci_insurance_finance"), ("Finanzas del reaseguro cedido", "oci_reinsurance_finance"),
                 ("Inversiones a valor razonable con cambios en ORI", "oci_fvoci_assets")]
    o = pl_rows["profit"] + 3
    for _, col in oci_lines:
        pl_rows[col] = o
        o += 1
    pl_rows["tci"] = o + 1

    for j in range(2, 5):
        L, P = get_column_letter(j), get_column_letter(j - 1)
        prev = lambda row: f"{P}{row}+" if j > 2 else ""  # noqa: E731
        put(ws, re_row, j, f"={prev(re_row)}{L}{pl_rows['profit']}", GREEN if j == 2 else BLACK, fmt=NUM)
        put(ws, ins_row, j, f"={prev(ins_row)}{L}{pl_rows['oci_insurance_finance']}+{L}{pl_rows['oci_reinsurance_finance']}", fmt=NUM)
        put(ws, oci_row, j, f"={prev(oci_row)}{L}{pl_rows['oci_fvoci_assets']}", fmt=NUM)
        put(ws, oci_row + 1, j, f"=SUM({L}{eq0}:{L}{oci_row})", bold=True, fmt=NUM, fill=SUB)
        put(ws, oci_row + 2, j, f"={L}{ta}-{L}{tl}-{L}{oci_row + 1}", fmt=NUM, fill=CHECK)
        CHECKS.append(f"EEFF!{L}{oci_row + 2}")
    put(ws, oci_row + 1, 1, "Total patrimonio", bold=True)
    put(ws, oci_row + 2, 1, "Control: activos - pasivos - patrimonio", italic=True)

    header(ws, pl_top, ["Estado de resultados y otro resultado integral", *YEARS])
    labels = dict(lines_pl + [("Ingresos de inversiones", "investment_income"), ("Gastos financieros de seguros emitidos", "insurance_finance_expenses"),
                              ("Ingresos financieros del reaseguro cedido", "reinsurance_finance_income"),
                              ("Otros gastos de operación (no atribuibles, B66(d))", "other_operating_expenses")] + oci_lines)
    inv = {v: k for k, v in labels.items()}
    for col, row in pl_rows.items():
        if col in inv:
            put(ws, row, 1, inv[col])
            for j, y in enumerate(YEARS, start=2):
                put(ws, row, j, float(pl.loc[int(y), col]), BLUE, fmt=NUM)
    for j in range(2, 5):
        L = get_column_letter(j)
        put(ws, pl_rows["isr"], j, f"=SUM({L}{pl_rows['insurance_revenue']}:{L}{pl_rows['net_reinsurance']})", bold=True, fmt=NUM, fill=SUB)
        put(ws, pl_rows["fin"], j, f"=SUM({L}{pl_rows['investment_income']}:{L}{pl_rows['reinsurance_finance_income']})", bold=True, fmt=NUM, fill=SUB)
        put(ws, pl_rows["profit"], j, f"={L}{pl_rows['isr']}+{L}{pl_rows['fin']}+{L}{pl_rows['other_operating_expenses']}", bold=True, fmt=NUM, fill=SUB)
        first_oci = pl_rows["oci_insurance_finance"]
        put(ws, pl_rows["tci"], j, f"={L}{pl_rows['profit']}+SUM({L}{first_oci}:{L}{pl_rows['oci_fvoci_assets']})", bold=True, fmt=NUM, fill=SUB)
        put(ws, pl_rows["tci"] + 1, j, f"={L}{pl_rows['profit']}-{float(pl.loc[int(YEARS[j - 2]), 'profit_before_tax'])}", fmt=NUM, fill=CHECK)
        CHECKS.append(f"EEFF!{L}{pl_rows['tci'] + 1}")
    put(ws, pl_rows["isr"], 1, "Resultado del servicio de seguros", bold=True)
    put(ws, pl_rows["fin"], 1, "Resultado financiero neto", bold=True)
    put(ws, pl_rows["profit"], 1, "Resultado del año antes de impuestos", bold=True)
    put(ws, pl_rows["profit"] + 2, 1, "Otro resultado integral (partidas que se reclasificarán)", bold=True)
    put(ws, pl_rows["tci"], 1, "Resultado integral total", bold=True)
    put(ws, pl_rows["tci"] + 1, 1, "Control: resultado de la fórmula - resultado del motor", italic=True)
    widths(ws, [62, 18, 18, 18])


def roll_block(ws, r, label, lines, cols, data, opening_from=None, closing_engine=None):
    """One reconciliation block: rows = lines, columns = cols, closing = SUM, opening linked."""
    header(ws, r, [label, *[c[0] for c in cols], "Total"])
    first = r + 1
    for i, (key, lab) in enumerate(lines):
        row = first + i
        put(ws, row, 1, lab)
        for j, (_, col) in enumerate(cols, start=2):
            if key == "opening" and opening_from is not None:
                put(ws, row, j, f"={get_column_letter(j)}{opening_from}", GREEN, fmt=NUM)
            else:
                put(ws, row, j, float(data.get((key, col), 0.0)), BLUE, fmt=NUM)
        nc = len(cols) + 2
        put(ws, row, nc, f"=SUM({get_column_letter(2)}{row}:{get_column_letter(nc - 1)}{row})", fmt=NUM)
    close = first + len(lines)
    put(ws, close, 1, "Saldo final", bold=True)
    for j in range(2, len(cols) + 3):
        L = get_column_letter(j)
        put(ws, close, j, f"=SUM({L}{first}:{L}{close - 1})", bold=True, fmt=NUM, fill=SUB)
    put(ws, close + 1, 1, "Control: saldo final de la fórmula - saldo del motor", italic=True)
    for j, (_, col) in enumerate(cols, start=2):
        L = get_column_letter(j)
        put(ws, close + 1, j, f"={L}{close}-{float(closing_engine.get(col, 0.0))}", fmt=NUM, fill=CHECK)
        CHECKS.append(f"{ws.title}!{L}{close + 1}")
    return close, close + 3


LINES_100 = [("opening", "Saldo inicial"), ("insurance_revenue", "Ingresos por seguros"),
             ("incurred_claims_and_expenses", "Siniestros y otros gastos incurridos"),
             ("acquisition_amortisation", "Amortización de flujos de adquisición"),
             ("onerous_losses_and_reversals", "Pérdidas y reversiones en grupos onerosos"),
             ("past_service_lic", "Cambios del LIC por servicio pasado"),
             ("investment_components", "Componentes de inversión"),
             ("insurance_finance", "Ingresos o gastos financieros de seguros"),
             ("premiums_received", "Primas recibidas"), ("claims_and_expenses_paid", "Siniestros y gastos pagados"),
             ("acquisition_paid", "Flujos de adquisición pagados")]


def sheet_100(wb, t):
    ws = wb.create_sheet("Conc_100")
    title(ws, "Conciliación del pasivo por cobertura restante y por siniestros incurridos (par. 100, 103)",
          "Contratos emitidos por portafolio. Los saldos iniciales de 2024 y 2025 son el saldo final del año anterior (fórmula).")
    cols = [("LRC sin componente de pérdida", "lrc_excl_lc"), ("Componente de pérdida", "loss_component"), ("LIC", "lic")]
    r = 4
    for port in ["VT", "VA", "AUTO", "INC", "TRC"]:
        put(ws, r, 1, NAMES[port], bold=True).font = fnt(bold=True, size=12)
        r += 1
        prev_close = None
        for c, y in zip(CLOSINGS, YEARS):
            sub = t[(t["portfolio"] == port) & (t["closing"] == c)]
            if sub.empty:
                continue
            agg = sub.groupby("line")[[x[1] for x in cols]].sum()
            data = {(line, col): agg.loc[line, col] for line in agg.index for col in agg.columns}
            close_engine = {col: agg.loc["closing", col] for col in agg.columns}
            prev_close, r = roll_block(ws, r, f"{NAMES[port]} — {y}", LINES_100, cols, data, prev_close, close_engine)
        r += 1
    widths(ws, [48, 20, 20, 20, 20])


LINES_101 = [("opening", "Saldo inicial"), ("future_service_csm", "Cambios en estimaciones que ajustan el CSM"),
             ("future_service_onerous", "Cambios que no ajustan el CSM (onerosos)"),
             ("loss_recovery_income", "Recuperación de pérdidas (reaseguro, 66A)"),
             ("new_contracts", "Contratos reconocidos en el periodo"), ("csm_release", "CSM reconocido por servicios"),
             ("ra_release", "Cambio del ajuste por riesgo por riesgo vencido"), ("experience", "Ajustes por experiencia"),
             ("finance", "Ingresos o gastos financieros de seguros"), ("premiums_received", "Primas recibidas / pagadas"),
             ("claims_and_expenses_incurred", "Siniestros y gastos incurridos / recuperaciones"),
             ("investment_components", "Componentes de inversión"), ("acquisition_cash_flows", "Flujos de adquisición pagados")]


def sheet_101(wb, t):
    ws = wb.create_sheet("Conc_101")
    title(ws, "Conciliación del valor presente de los flujos, el ajuste por riesgo y el CSM (par. 101, 104)",
          "Contratos medidos con el GMM. El reaseguro cedido se muestra como activo (signo positivo) y por separado (par. 98).")
    cols = [("Valor presente de flujos futuros", "pv"), ("Ajuste por riesgo no financiero", "ra"), ("Margen contractual de servicio", "csm")]
    r = 4
    for port in ["VT", "VA", "RE_VT"]:
        put(ws, r, 1, NAMES[port], bold=True).font = fnt(bold=True, size=12)
        r += 1
        prev_close = None
        for c, y in zip(CLOSINGS, YEARS):
            sub = t[(t["portfolio"] == port) & (t["closing"] == c)]
            agg = sub.groupby("line")[["pv", "ra", "csm"]].sum()
            data = {(line, col): agg.loc[line, col] for line in agg.index for col in agg.columns}
            close_engine = {col: agg.loc["closing", col] for col in agg.columns}
            prev_close, r = roll_block(ws, r, f"{NAMES[port]} — {y}", LINES_101, cols, data, prev_close, close_engine)
        r += 1
    widths(ws, [48, 22, 22, 22, 20])


def simple_table(wb, name, heading, note, df, number_cols, total_col=None, pct_cols=()):
    ws = wb.create_sheet(name)
    title(ws, heading, note)
    header(ws, 4, list(df.columns) + ([total_col[0]] if total_col else []))
    for i, row in enumerate(df.itertuples(index=False), start=5):
        for j, v in enumerate(row, start=1):
            col = df.columns[j - 1]
            fmt = PCT if col in pct_cols else (NUM if col in number_cols else None)
            put(ws, i, j, v if not isinstance(v, float) or pd.notna(v) else None, BLUE if col in number_cols or col in pct_cols else BLACK, fmt=fmt)
        if total_col:
            a = get_column_letter(df.columns.get_loc(total_col[1]) + 1)
            b = get_column_letter(df.columns.get_loc(total_col[2]) + 1)
            put(ws, i, len(df.columns) + 1, f"=SUM({a}{i}:{b}{i})", fmt=NUM)
    widths(ws, [24] * (len(df.columns) + 1))
    return ws


def main() -> None:
    bs = pd.read_csv(RES / "balance_sheet.csv").set_index("closing")
    pl = pd.read_csv(RES / "profit_or_loss.csv").set_index("year")
    wb = Workbook()
    sheet_cover(wb)
    sheet_statements(wb, bs, pl)
    sheet_100(wb, pd.read_csv(RES / "reconciliation_100.csv"))
    sheet_101(wb, pd.read_csv(RES / "reconciliation_101.csv"))

    rev = pd.read_csv(RES / "revenue_106.csv").groupby(["closing", "portfolio"]).sum(numeric_only=True).reset_index()
    cols = ["expected_claims_and_expenses", "loss_component_exclusion", "ra_release", "csm_release", "acquisition_recovery"]
    ws = simple_table(wb, "Ingresos_106", "Análisis de los ingresos por seguros, grupos GMM (par. 106)",
                      "Siniestros y gastos esperados, liberación del ajuste por riesgo y del CSM, y recuperación de adquisición (B121-B125).",
                      rev[["closing", "portfolio", *cols, "insurance_revenue"]], cols + ["insurance_revenue"],
                      total_col=("Total por fórmula", cols[0], cols[-1]))
    n = len(rev)
    put(ws, 5 + n, 1, "Control: total por fórmula - ingresos del motor", italic=True)
    for i in range(5, 5 + n):
        put(ws, i, 10, f"=I{i}-H{i}", fmt=NUM, fill=CHECK)
        CHECKS.append(f"Ingresos_106!J{i}")

    nb = pd.read_csv(RES / "new_business_107.csv").groupby(["closing", "portfolio", "onerous"]).sum(numeric_only=True).reset_index()
    c107 = ["pv_acquisition_outflows", "pv_other_outflows", "pv_inflows", "ra", "csm"]
    ws = simple_table(wb, "NegocioNuevo_107", "Contratos reconocidos en el periodo (par. 107)",
                      "Salidas (con adquisición aparte), entradas, ajuste por riesgo y CSM; los grupos onerosos van aparte. La suma es la pérdida inicial.",
                      nb[["closing", "portfolio", "onerous", *c107, "loss"]], c107 + ["loss"], total_col=("Suma = pérdida", c107[0], c107[-1]))
    for i in range(5, 5 + len(nb)):
        put(ws, i, 11, f"=J{i}-I{i}", fmt=NUM, fill=CHECK)
        CHECKS.append(f"NegocioNuevo_107!K{i}")
    put(ws, 4, 11, "Control: suma - pérdida", bold=True, fill=HEAD)

    csm = pd.read_csv(RES / "csm_release_109.csv")
    bands = [c for c in csm.columns if c != "portfolio"]
    simple_table(wb, "CSM_109", "Reconocimiento esperado del CSM al 31-dic-2025 (par. 109)",
                 "Años en que se espera reconocer el CSM según las unidades de cobertura futuras, sin acreción futura. El reaseguro se muestra con signo de costo (negativo).",
                 csm, bands, total_col=("Total", bands[0], bands[-1]))

    ws = wb.create_sheet("Supuestos")
    title(ws, "Supuestos, curvas y nivel de confianza (par. 117, 119, 120)", "Factores de mortalidad por cierre, curvas spot (anual efectiva) y nivel de confianza.")
    r = 4
    for name, df, pct in (("Supuestos", pd.read_csv(RES / "assumptions_117.csv"), ()),
                          ("Curvas de descuento (spot anual)", pd.read_csv(RES / "discount_rates_120.csv"), ("1y", "5y", "10y", "20y", "30y", "40y")),
                          ("Nivel de confianza del ajuste por riesgo", pd.read_csv(RES / "confidence_119.csv"), ("confidence_level",))):
        put(ws, r, 1, name, bold=True)
        header(ws, r + 1, list(df.columns))
        for i, row in enumerate(df.itertuples(index=False), start=r + 2):
            for j, v in enumerate(row, start=1):
                col = df.columns[j - 1]
                put(ws, i, j, None if (isinstance(v, float) and pd.isna(v)) else v, BLUE,
                    fmt=PCT if col in pct else (NUM if isinstance(v, float) and abs(v) > 10 else None))
        r += len(df) + 4
    widths(ws, [22] * 8)

    sens = pd.read_csv(RES / "sensitivities_128.csv")
    simple_table(wb, "Sensibilidades_128", "Sensibilidades al 31-dic-2025 (par. 128(a))",
                 "Efecto en resultados y patrimonio, bruto y neto de reaseguro. Los cambios no financieros que absorbe el CSM no afectan el resultado.",
                 sens, ["profit_gross", "equity_gross", "profit_net", "equity_net"])

    ws = wb.create_sheet("Desarrollo_130")
    title(ws, "Desarrollo de siniestros (par. 130)", "Estimación no descontada del último costo por año de accidente en cada cierre; última = pagado + pendiente (fórmula).")
    r = 4
    for line in ("auto", "trc"):
        df = pd.read_csv(RES / f"claims_development_130_{line}.csv")
        put(ws, r, 1, "Autos" if line == "auto" else "Todo riesgo construcción", bold=True)
        header(ws, r + 1, ["Cierre", "Año de accidente", "Pagado acumulado", "Pendiente no descontado", "Última estimación (fórmula)",
                           "LIC descontado (sin ajuste por riesgo)", "Efecto del descuento (fórmula)"])
        for i, row in enumerate(df.itertuples(index=False), start=r + 2):
            put(ws, i, 1, row.closing)
            put(ws, i, 2, int(row.accident_year))
            put(ws, i, 3, float(row.paid_to_date), BLUE, fmt=NUM)
            put(ws, i, 4, float(row.outstanding_undiscounted), BLUE, fmt=NUM)
            put(ws, i, 5, f"=C{i}+D{i}", fmt=NUM)
            put(ws, i, 6, float(row.lic_pv), BLUE, fmt=NUM)
            put(ws, i, 7, f"=F{i}-D{i}", fmt=NUM)
        r += len(df) + 4
    widths(ws, [14, 16, 20, 22, 24, 26, 24])

    mat = pd.read_csv(RES / "maturity_132.csv")
    yrs = [c for c in mat.columns if c != "portfolio"]
    simple_table(wb, "Liquidez_132", "Flujos netos esperados no descontados al 31-dic-2025 (par. 132(b)(i))",
                 "Salidas netas positivas. Vida incluye primas futuras (entradas, negativas) y el LIC; daños solo el LIC (132(b)).",
                 mat, yrs, total_col=("Total", yrs[0], yrs[-1]))

    ws = wb.create_sheet("Controles")
    title(ws, "Resumen de controles", "Cada celda enlaza a un control de otra hoja; el total absoluto debe ser cero.")
    header(ws, 4, ["Celda", "Valor"])
    for i, ref in enumerate(CHECKS, start=5):
        sheet, cell = ref.split("!")
        put(ws, i, 1, ref)
        put(ws, i, 2, f"='{sheet}'!{cell}", GREEN, fmt=NUM)
    put(ws, 5 + len(CHECKS), 1, "Suma de valores absolutos", bold=True)
    put(ws, 5 + len(CHECKS), 2, f"=SUMPRODUCT(ABS(B5:B{4 + len(CHECKS)}))", bold=True, fmt='#,##0.00', fill=CHECK)
    widths(ws, [36, 20])

    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    print(f"{OUT} with {len(CHECKS)} control cells")


if __name__ == "__main__":
    main()
