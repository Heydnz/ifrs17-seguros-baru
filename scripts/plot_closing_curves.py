"""Plot the IFRS 17 discount curve against TNC and HQM at the three closings.

Writes docs/figures/curvas_cierre.png (small multiples, one panel per closing).
"""

from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifrs17.illiquidity import CREDIT_SHARE, CREDIT_SHARE_CDS  # noqa: E402
from ifrs17.treasury_curves import build_discount_curve, read_treasury_spot_file, semiannual_to_annual  # noqa: E402

RAW = ROOT / "data" / "raw" / "treasury"
INK, QUIET, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e1"
C_IFRS, C_HQM, C_TNC = "#2a78d6", "#eb6834", "#8a8984"
TITLES = {"2023-12": "31 dic 2023", "2024-12": "31 dic 2024", "2025-12": "31 dic 2025"}
LABEL_OFFSET = {"2023-12": (24, 0.45), "2024-12": (24, 0.40), "2025-12": (1.5, 0.42)}  # label clear of the lines


def main() -> None:
    tnc = read_treasury_spot_file(RAW / "tnceom_23_27.xlsx")
    hqm = pd.concat([read_treasury_spot_file(RAW / f) for f in ("hqmeom_19_23.xls", "hqmeom_24_28.xls")])
    hqm = hqm[~hqm.index.duplicated(keep="last")]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5})
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.6), dpi=160, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    t = tnc.columns.to_numpy(dtype=float)
    keep = t <= 60
    for ax, month in zip(axes, TITLES):
        p = pd.Period(month, "M")
        ifrs = build_discount_curve(tnc.loc[p], hqm.loc[p], CREDIT_SHARE, 1.0).spot_annual
        option = build_discount_curve(tnc.loc[p], hqm.loc[p], CREDIT_SHARE_CDS, 1.0).spot_annual
        series = [("Curva IFRS 17 = HQM (corporativos AAA–A)", 100 * ifrs, C_IFRS, 2.2, "-"),
                  (f"Opción: {CREDIT_SHARE_CDS:.0%} del diferencial como crédito", 100 * option, C_HQM, 1.6, "--"),
                  ("TNC (Tesoro)", 100 * semiannual_to_annual(tnc.loc[p].to_numpy()), C_TNC, 1.6, "-")]
        ax.set_facecolor(SURFACE)
        for label, y, color, lw, ls in series:
            ax.plot(t[keep], y[keep], color=color, lw=lw, ls=ls, label=label, zorder=3 if color == C_IFRS else 2)
        y20 = 100 * ifrs[t == 20.0][0]
        ax.annotate(f"{y20:.2f}% a 20 años".replace(".", ","), xy=(20, y20), xytext=(LABEL_OFFSET[month][0], y20 + LABEL_OFFSET[month][1]),
                    fontsize=9, color=INK, arrowprops=dict(arrowstyle="-", color=QUIET, lw=0.8))
        ax.set_title(TITLES[month], loc="left", fontsize=11, color=INK, fontweight="bold", pad=6)
        ax.set_xlim(0, 60)
        ax.set_ylim(3.2, 6.6)
        ax.set_xlabel("Plazo (años)", color=QUIET)
        ax.grid(axis="y", color=GRID, lw=0.8)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        for sp in ["left", "bottom"]:
            ax.spines[sp].set_color("#b9b8b2")
        ax.tick_params(colors=QUIET)
    axes[0].set_ylabel("Tasa spot anual efectiva (%)", color=QUIET)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.055, 0.905), ncol=3, frameon=False, fontsize=9.5)
    fig.suptitle("La curva IFRS 17 es la HQM: de 72 a 123 pb sobre el Tesoro entre 10 y 30 años",
                 x=0.06, ha="left", y=0.975, fontsize=13, fontweight="bold", color=INK)
    fig.text(0.06, 0.02, "Política: curva HQM sin deducción de crédito. La línea punteada muestra la opción con deducción por CDS. "
             "Fuente: Tesoro de EE. UU., curvas TNC y HQM de fin de mes.", fontsize=8.5, color=QUIET)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.80, bottom=0.17, wspace=0.08)
    out = ROOT / "docs" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "curvas_cierre.png", facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
