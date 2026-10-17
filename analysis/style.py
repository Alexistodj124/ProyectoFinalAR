"""Nombres, colores y estilo comunes de todas las figuras (matplotlib).

Convención de color (la misma en todas las figuras):
    líneas base  -> familia de grises (fijo claro, actuado medio, max-pressure oscuro)
    agente único -> familia de azules (tabular, DQN y sus variantes, PPO)
    multiagente  -> verdes (IDQN, QMIX: aprendizaje de valor) y violetas (MAPPO, comunicación)
    variantes "equitativas" y "mejor semilla" -> el color de su método base con rayas
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

BASELINES = ["fixed", "actuated", "max_pressure"]

# orden canónico de las series en leyendas, barras y tablas
ORDER = ["fixed", "actuated", "max_pressure",
         "q_learning", "dyna_q_n5", "dyna_q_n10", "dyna_q_n50",
         "dqn_vanilla", "dqn_double", "dqn_double_dueling", "dqn_double_dueling_per", "dqn_best", "ppo",
         "idqn", "idqn_neighbor_obs", "qmix", "mappo", "comm", "qmix_fair", "comm_fair",
         "marl_best", "comm_best"]

LABELS = {
    "fixed": "Tiempo fijo", "actuated": "Actuado", "max_pressure": "Max-pressure",
    "q_learning": "Q-Learning", "dyna_q_n5": "Dyna-Q n=5", "dyna_q_n10": "Dyna-Q n=10", "dyna_q_n50": "Dyna-Q n=50",
    "dqn_vanilla": "DQN base", "dqn_double": "DQN + Double", "dqn_double_dueling": "DQN + Double + Dueling",
    "dqn_double_dueling_per": "DQN + Double + Dueling + PER", "dqn_best": "DQN mejor (E4)", "ppo": "PPO",
    "idqn": "IDQN", "idqn_neighbor_obs": "IDQN + colas de vecinos", "qmix": "QMIX", "mappo": "MAPPO",
    "comm": "Comunicación (DIAL)", "qmix_fair": "QMIX equitativo", "comm_fair": "Comunicación equitativa",
    "marl_best": "MAPPO (semilla elegida)", "comm_best": "Comunicación (semilla elegida)",
}
# etiquetas cuando el método viene de E7 (una sola semilla de entrenamiento elegida por validación)
LABELS_E7 = {"dqn_best": "DQN (semilla elegida)", "ppo": "PPO (semilla elegida)"}
SHORT = {  # etiquetas cortas para ejes con muchas barras
    "fixed": "Fijo", "actuated": "Actuado", "max_pressure": "Max-pressure", "q_learning": "Q-Learning",
    "dyna_q_n5": "Dyna n=5", "dyna_q_n10": "Dyna n=10", "dyna_q_n50": "Dyna n=50", "dqn_vanilla": "DQN base",
    "dqn_double": "+Double", "dqn_double_dueling": "+Dueling", "dqn_double_dueling_per": "+PER", "dqn_best": "DQN",
    "ppo": "PPO", "idqn": "IDQN", "idqn_neighbor_obs": "IDQN+vec.", "qmix": "QMIX", "mappo": "MAPPO",
    "comm": "Comunic.", "qmix_fair": "QMIX eq.", "comm_fair": "Comunic. eq.", "marl_best": "MAPPO*", "comm_best": "Comunic.*",
}

COLORS = {
    "fixed": "#bdbdbd", "actuated": "#8c8c8c", "max_pressure": "#4a4a4a",
    "q_learning": "#9ecae1", "dyna_q_n5": "#6baed6", "dyna_q_n10": "#3a8bc4", "dyna_q_n50": "#1c5fa0",
    "dqn_vanilla": "#7fb3e0", "dqn_double": "#3b7fc0", "dqn_double_dueling": "#1f5aa6",
    "dqn_double_dueling_per": "#0b3a7a", "dqn_best": "#0b3a7a", "ppo": "#00a3c4",
    "idqn": "#8fd19e", "idqn_neighbor_obs": "#3fae6a", "qmix": "#0b6e3a",
    "mappo": "#5b2a96", "comm": "#a678d4", "qmix_fair": "#0b6e3a", "comm_fair": "#a678d4",
    "marl_best": "#5b2a96", "comm_best": "#a678d4",
}
HATCH = {"qmix_fair": "///", "comm_fair": "///", "marl_best": "..", "comm_best": ".."}
_FALLBACK = ["#d95f02", "#e6ab02", "#e7298a", "#66a61e", "#a6761d", "#666666"]

# familias para los gráficos de resumen
FAMILY_NAMES = {"baseline": "Líneas base", "single": "Agente único", "marl": "Multiagente"}


def family(m: str) -> str:
    if m in BASELINES:
        return "baseline"
    if m in ("idqn", "idqn_neighbor_obs", "qmix", "mappo", "comm", "qmix_fair", "comm_fair", "marl_best", "comm_best"):
        return "marl"
    return "single"


def label(m: str, ctx: str | None = None, short: bool = False) -> str:
    if ctx == "E7" and m in LABELS_E7:
        return LABELS_E7[m]
    return (SHORT if short else LABELS).get(m, m)


def color(m: str) -> str:
    if m in COLORS:
        return COLORS[m]
    return _FALLBACK[sum(map(ord, str(m))) % len(_FALLBACK)]


def sort_methods(methods) -> list[str]:
    """Orden canónico; los métodos desconocidos van al final por orden alfabético."""
    ms = list(dict.fromkeys(methods))
    return sorted(ms, key=lambda m: (ORDER.index(m) if m in ORDER else len(ORDER), str(m)))


SCEN_LABELS = {
    "cruce_pico": "Cruce C12\nhora pico", "cruce_mediodia": "Cruce C12\nmediodía", "cruce_pico_x13": "Cruce C12\npico +30 %",
    "reforma_pico": "Corredor\nhora pico", "reforma_mediodia": "Corredor\nmediodía", "reforma_pico_x13": "Corredor\npico +30 %",
}
VARIANT_LABELS = {"pico": "Pico\n(entrenamiento)", "mediodia": "Mediodía\n(hora no vista)", "pico_x13": "Pico +30 %\n(más demanda)",
                  "pico_incident": "Pico +\nincidente"}


def scen_label(s: str, flat: bool = False) -> str:
    t = SCEN_LABELS.get(s, s)
    return t.replace("\n", " ") if flat else t


def variant_label(v: str, flat: bool = False) -> str:
    t = VARIANT_LABELS.get(v, v)
    return t.replace("\n", " ") if flat else t


# aproximaciones (carriles de entrada) -> nombre legible. Reforma: NB/SB; el resto son calles transversales.
def approach_label(a: str) -> str:
    cal = {"C15": "15", "C14": "14", "C12": "12", "C10": "10", "C06": "6"}
    dirs = {"W": "oeste", "E": "este", "N": "norte", "S": "sur"}
    parts = a.split("_")
    if len(parts) == 3 and parts[2] == "in" and parts[0] in cal:  # C06_W_in
        return f"Transv. {cal[parts[0]]}ª ({dirs.get(parts[1], parts[1])})"
    if parts[0] == "NB" and len(parts) == 3 and parts[1] == "S":  # NB_S_C15: entrada sur del corredor
        return "Reforma ↑ (entra por C15)"
    if parts[0] == "SB" and len(parts) == 3 and parts[1] == "N":
        return "Reforma ↓ (entra por C06)"
    if parts[0] in ("NB", "SB") and len(parts) == 3:  # NB_C14_C12: tramo Reforma norte entre calles
        return f"Reforma {'↑' if parts[0] == 'NB' else '↓'} (C{parts[1][1:]}→C{parts[2][1:]})"
    return a


def is_cross_street(a: str) -> bool:
    return not a.startswith(("NB", "SB"))


def apply_style() -> None:
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 190, "savefig.bbox": "tight", "figure.facecolor": "white",
        "font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.labelsize": 11, "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
        "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True, "hatch.linewidth": 0.8,
        "figure.constrained_layout.use": True,
    })


def legend_handles(methods, ctx: str | None = None):
    hs = []
    for m in methods:
        hs.append(Patch(facecolor=color(m), edgecolor="#333333" if m in HATCH else color(m), hatch=HATCH.get(m, ""),
                        label=label(m, ctx)))
    return hs


def fig_legend(fig, handles, ncol: int, note: str | None = None) -> None:
    """Leyenda bajo los paneles; la nota (n, IC95...) va como título de la leyenda, así nunca se pisan."""
    import textwrap
    title = "\n".join(textwrap.wrap(note, int(fig.get_size_inches()[0] * 12.5))) if note else None
    leg = fig.legend(handles=handles, loc="outside lower center", ncol=ncol, title=title)
    if title:
        leg.get_title().set_fontsize(8.5)
        leg.get_title().set_color("#555555")
        leg.get_title().set_multialignment("center")


def legend_below(fig, methods, ctx: str | None = None, ncol: int | None = None, note: str | None = None) -> None:
    hs = legend_handles(methods, ctx)
    ncol = ncol or min(len(hs), 4 if len(hs) <= 8 else 5)
    fig_legend(fig, hs, ncol, note)


def footnote(fig, note: str, size: float = 8.5) -> None:
    """Nota al pie debajo de todo (leyenda incluida); con savefig(bbox_inches="tight") se amplía el lienzo."""
    import textwrap
    note = "\n".join(textwrap.wrap(note, int(fig.get_size_inches()[0] * 12.5)))
    fig.canvas.draw()
    bb = fig.get_tightbbox(fig.canvas.get_renderer())  # pulgadas
    rend = fig.canvas.get_renderer()
    low = min([bb.y0] + [lg.get_window_extent(rend).y0 / fig.dpi for lg in fig.legends])
    y = low / fig.get_size_inches()[1] - 0.012
    fig.text(0.5, y, note, ha="center", va="top", fontsize=size, color="#555555")
