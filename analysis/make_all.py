"""Genera todas las figuras y tablas que tengan datos; los experimentos sin resultados se omiten.

    python -m analysis.make_all [--runs-dir runs] [--fig-dir docs/figures] [--table-dir analysis/results] [--latex]

Salidas: docs/figures/*.png|pdf y analysis/results/*.md (RESUMEN.md se escribe a mano, no se regenera).
"""
from __future__ import annotations

import argparse
import traceback

from analysis import plots, stats, tables
from analysis.data import FIG_DIR, RESULTS_DIR, RUNS_DIR

EXPS = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]
MARL = ["idqn", "idqn_neighbor_obs", "qmix", "mappo", "comm", "qmix_fair", "comm_fair"]
SINGLE = ["q_learning", "dyna_q_n5", "dyna_q_n10", "dyna_q_n50", "dqn_vanilla", "dqn_double", "dqn_double_dueling",
          "dqn_double_dueling_per", "dqn_best", "ppo"]


def make_all(runs_dir=RUNS_DIR, fig_dir=FIG_DIR, table_dir=RESULTS_DIR, latex=False, exps=EXPS) -> dict[str, list]:
    made: dict[str, list] = {}
    for exp in exps:
        out = []
        try:
            if exp == "E7":
                out += plots.robustness_plot(runs_dir, fig_dir) + plots.degradation_plot(runs_dir, fig_dir)
            elif exp == "E8":
                out += (plots.fairness_plot(runs_dir, fig_dir) + plots.tradeoff_plot(runs_dir, fig_dir, "reforma_pico")
                        + plots.tradeoff_plot(runs_dir, fig_dir, "cruce_pico") + plots.co2_plot(runs_dir, fig_dir))
            else:
                out += plots.eval_bars(exp, runs_dir, fig_dir) + plots.learning_curves(exp, runs_dir, fig_dir)
            out += tables.make_tables(exp, runs_dir, table_dir, latex)
        except Exception:  # one broken experiment must not stop the rest
            print(f"[{exp}] ERROR\n{traceback.format_exc()}")
        made[exp] = out
        print(f"[{exp}] {len(out)} files" if out else f"[{exp}] no data, skipped")
    extra = []
    try:
        extra += plots.headline_plot(runs_dir, fig_dir)
        extra += plots.selection_plot(runs_dir, fig_dir, methods=MARL, name="seleccion_validacion_marl",
                                      title="Oscilación de la validación entre checkpoints: métodos multiagente")
        extra += plots.selection_plot(runs_dir, fig_dir, methods=SINGLE, name="seleccion_validacion_agente_unico",
                                      title="Oscilación de la validación entre checkpoints: agente único")
        extra += stats.make_stats(runs_dir, table_dir)
    except Exception:
        print(f"[extra] ERROR\n{traceback.format_exc()}")
    made["extra"] = extra
    print(f"[extra] {len(extra)} files")
    return made


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=str(RUNS_DIR))
    ap.add_argument("--fig-dir", default=str(FIG_DIR))
    ap.add_argument("--table-dir", default=str(RESULTS_DIR))
    ap.add_argument("--latex", action="store_true")
    a = ap.parse_args(argv)
    make_all(a.runs_dir, a.fig_dir, a.table_dir, a.latex)


if __name__ == "__main__":
    main()
