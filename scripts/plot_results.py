"""Figures for the README and the memo from data/results (run scripts/run_closings.py first)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data" / "results"
FIG = ROOT / "docs" / "figures"
BLUE, RED, GREY, GREEN, ORANGE = "#1f4e79", "#c0392b", "#7f7f7f", "#2e7d32", "#e67e22"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def millions(x, _=None):
    return f"{x / 1e6:,.1f}"


def csm_story():
    g = pd.read_csv(RES / "groups_gmm.csv")
    g = g[g["portfolio"] == "VT"]
    groups = ["VT-2023-SIG", "VT-2023-RES", "VT-2023-ONE", "VT-2024-SIG", "VT-2024-RES", "VT-2024-ONE", "VT-2025-SIG", "VT-2025-RES"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    for ax, c in zip(axes, ["2023-12-31", "2024-12-31", "2025-12-31"]):
        d = g[g["closing"] == c].set_index("group").reindex(groups)
        x = range(len(groups))
        ax.bar(x, d["csm"].fillna(0) / 1e6, color=BLUE, label="CSM")
        ax.bar(x, -d["loss_component"].fillna(0) / 1e6, color=RED, label="Componente de pérdida (negativo)")
        ax.set_xticks(list(x), [s.replace("VT-", "") for s in groups], rotation=60, ha="right")
        ax.set_title(f"31-dic-{c[:4]}")
        ax.axhline(0, color=GREY, lw=0.8)
    axes[0].set_ylabel("USD millones")
    axes[0].legend(frameon=False, loc="upper right", fontsize=8)
    fig.suptitle("Vida temporal: CSM y componente de pérdida por grupo", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "vida_temporal_csm.png", dpi=160)


def profit():
    pl = pd.read_csv(RES / "profit_or_loss.csv").set_index("year")
    parts = [("insurance_service_result", "Resultado del servicio de seguros", BLUE),
             ("net_financial_result", "Resultado financiero neto", GREEN),
             ("other_operating_expenses", "Otros gastos", GREY)]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    w = 0.25
    for i, (col, lab, color) in enumerate(parts):
        ax.bar([y + (i - 1) * w for y in pl.index], pl[col] / 1e6, width=w, color=color, label=lab)
    ax.plot(pl.index, pl["profit_before_tax"] / 1e6, "o-", color="black", label="Resultado antes de impuestos")
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_xticks(pl.index)
    ax.set_ylabel("USD millones")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Seguros Barú: composición del resultado", loc="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "resultado_por_anio.png", dpi=160)


def claims_development():
    d = pd.read_csv(RES / "claims_development_130_auto.csv")
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    for ay, color in zip([2023, 2024, 2025], [BLUE, ORANGE, GREEN]):
        s = d[d["accident_year"] == ay]
        ax.plot(s["closing"].str[:4], s["ultimate_estimate"] / 1e6, "o-", color=color, label=f"Ocurrencia {ay}: última estimada")
        ax.plot(s["closing"].str[:4], s["paid_to_date"] / 1e6, "s--", color=color, alpha=0.6, label=f"Ocurrencia {ay}: pagado")
    ax.set_ylabel("USD millones")
    ax.set_xlabel("Cierre")
    ax.legend(frameon=False, fontsize=7, ncol=2)
    ax.set_title("Autos: desarrollo de siniestros (par. 130)", loc="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "desarrollo_autos.png", dpi=160)


def trc():
    t = pd.read_csv(RES / "trc_eligibility.csv")
    t = t[t["lrc_gmm"] > 0]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    for (cohort, sc), g in t.groupby(["cohort", "scenario"]):
        if cohort != 2025:
            continue
        ax.plot(g["year_end"], 100 * g["relative"], marker="o", label=sc)
    ax.axhspan(-5, 5, color=GREEN, alpha=0.08)
    ax.axhline(5, color=GREEN, lw=0.8, ls="--")
    ax.axhline(-5, color=GREEN, lw=0.8, ls="--")
    ax.set_ylabel("(PAA - GMM) / GMM, %")
    ax.set_xlabel("Cierre")
    ax.set_title("TRC 2025: LRC por PAA frente a GMM (umbral 5%)", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "trc_elegibilidad.png", dpi=160)


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    csm_story()
    profit()
    claims_development()
    trc()
    print("figures written to", FIG)
