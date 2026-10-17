"""Figura 1 del informe: el corredor de Reforma dibujado desde env/net/reforma.net.xml (sin simular).

    source scripts/env.sh && python docs/informe/figura_escenario.py

Escribe docs/figures/escenario_corredor.{png,pdf}: carriles de la red, los 5 semáforos etiquetados,
el cruce C12 (escenario `cruce_*`) resaltado y la arista del incidente de E7 (`NB_C12_C10`).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import sumolib  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
NET = ROOT / "env" / "net" / "reforma.net.xml"
OUT = ROOT / "docs" / "figures" / "escenario_corredor"
NAMES = {"C15": "15 calle", "C14": "14 calle", "C12": "12 calle", "C10": "10a calle", "C06": "6a calle"}
INCIDENT_EDGE = "NB_C12_C10"


def main() -> None:
    net = sumolib.net.readNet(str(NET), withInternal=False)
    fig, ax = plt.subplots(figsize=(4.6, 7.2))
    for edge in net.getEdges():
        reforma = "Reforma" in (edge.getName() or "") or edge.getID().startswith(("NB_", "SB_"))
        color = "#d62728" if edge.getID() == INCIDENT_EDGE else ("#555555" if reforma else "#9a9a9a")
        for lane in edge.getLanes():
            xs, ys = zip(*lane.getShape())
            ax.plot(xs, ys, color=color, lw=1.1 if reforma else 0.9, solid_capstyle="butt", zorder=1)
    for tls in net.getTrafficLights():
        nodes = {c[0].getEdge().getToNode() for c in tls.getConnections()}
        x = sum(n.getCoord()[0] for n in nodes) / len(nodes)
        y = sum(n.getCoord()[1] for n in nodes) / len(nodes)
        tid = tls.getID()
        hi = tid == "C12"
        ax.scatter([x], [y], s=110 if hi else 70, color="#1f77b4" if hi else "#2ca02c",
                   edgecolor="black", zorder=3)
        ax.annotate(f"{tid}  {NAMES.get(tid, '')}" + ("  (cruce_*)" if hi else ""), (x, y),
                    xytext=(14, -3), textcoords="offset points", fontsize=8.5,
                    fontweight="bold" if hi else "normal", zorder=4)
    ax.plot([], [], color="#d62728", lw=2, label="incidente E7 (NB_C12_C10)")
    ax.scatter([], [], s=60, color="#2ca02c", edgecolor="black", label="semáforo (agente)")
    ax.legend(loc="lower right", fontsize=7.5, frameon=False)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m] (UTM 15N, relativo)", fontsize=8)
    ax.set_ylabel("y [m] (norte arriba)", fontsize=8)
    ax.tick_params(labelsize=7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title("Corredor de Av. La Reforma en SUMO", fontsize=10)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT.with_suffix(".png"), dpi=190)
    fig.savefig(OUT.with_suffix(".pdf"))
    print(f"[figura] {OUT.with_suffix('.png')}")


if __name__ == "__main__":
    main()
