"""Comparaciones estadísticas entre pares de métodos clave (t de Welch) -> analysis/results/comparaciones_estadisticas.md.

    python -m analysis.stats

Réplica: semilla de entrenamiento (media de sus 10 episodios de evaluación; n=5) en los métodos aprendidos y episodio de
evaluación (n=10) en las líneas base. La prueba de Welch no supone varianzas iguales, y compara las réplicas de A con las
de B (unidades de distinto tipo cuando uno es una línea base: es conservador para el aprendido, que tiene n=5).
`p (Holm)` corrige por las comparaciones de la misma tabla. Todas las métricas son "menor es mejor".
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from analysis.data import METRICS, RESULTS_DIR, RUNS_DIR, ci95, load_csv, load_master, unit_values
from analysis.style import label

# (A, B, escenario, motivo)
PAIRS_MAIN = [
    ("mappo", "fixed", "reforma_pico", "MAPPO contra tiempo fijo"),
    ("mappo", "actuated", "reforma_pico", "MAPPO contra actuado"),
    ("mappo", "max_pressure", "reforma_pico", "MAPPO contra max-pressure"),
    ("comm", "mappo", "reforma_pico", "comunicación contra MAPPO"),
    ("comm", "idqn", "reforma_pico", "comunicación contra IDQN"),
    ("idqn_neighbor_obs", "idqn", "reforma_pico", "colas de vecinos contra IDQN"),
    ("qmix", "mappo", "reforma_pico", "QMIX contra MAPPO"),
    ("idqn", "mappo", "reforma_pico", "IDQN contra MAPPO"),
    ("qmix", "max_pressure", "reforma_pico", "QMIX contra max-pressure"),
    ("comm", "max_pressure", "reforma_pico", "comunicación contra max-pressure"),
    ("qmix_fair", "qmix", "reforma_pico", "QMIX equitativo contra QMIX"),
    ("comm_fair", "comm", "reforma_pico", "comunicación equitativa contra comunicación"),
    ("dqn_best", "fixed", "cruce_pico", "DQN contra tiempo fijo"),
    ("dqn_best", "actuated", "cruce_pico", "DQN contra actuado"),
    ("dqn_best", "max_pressure", "cruce_pico", "DQN contra max-pressure"),
    ("ppo", "fixed", "cruce_pico", "PPO contra tiempo fijo"),
    ("ppo", "max_pressure", "cruce_pico", "PPO contra max-pressure"),
    ("ppo", "dqn_best", "cruce_pico", "PPO contra DQN"),
    ("dqn_double_dueling_per", "dqn_vanilla", "cruce_pico", "DQN completo contra DQN base"),
    ("dyna_q_n50", "q_learning", "cruce_pico", "Dyna-Q n=50 contra Q-Learning"),
    ("q_learning", "fixed", "cruce_pico", "Q-Learning contra tiempo fijo"),
    ("dqn_best", "dyna_q_n50", "cruce_pico", "DQN contra Dyna-Q n=50"),
    ("mappo", "max_pressure", "reforma_pico_x13", "MAPPO contra max-pressure con +30 % de demanda"),
    ("mappo", "fixed", "reforma_pico_x13", "MAPPO contra tiempo fijo con +30 % de demanda"),
]
METRICS_CMP = ["total_delay", "max_wait_cross_streets"]


def welch(a: np.ndarray, b: np.ndarray) -> dict:
    """Prueba t de Welch de dos colas; diferencia A − B con su IC95 (Welch–Satterthwaite)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    out = {"mean_a": a.mean(), "mean_b": b.mean(), "diff": a.mean() - b.mean(), "n_a": len(a), "n_b": len(b)}
    if len(a) < 2 or len(b) < 2:
        return {**out, "p": np.nan, "diff_lo": np.nan, "diff_hi": np.nan}
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = np.sqrt(va + vb)
    if se == 0:
        return {**out, "p": 0.0 if out["diff"] else 1.0, "diff_lo": out["diff"], "diff_hi": out["diff"]}
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    t = out["diff"] / se
    p = 2 * stats.t.sf(abs(t), df)
    h = stats.t.ppf(0.975, df) * se
    return {**out, "p": float(p), "diff_lo": out["diff"] - h, "diff_hi": out["diff"] + h}


def holm(ps: list[float]) -> list[float]:
    ps = np.asarray(ps, float)
    order = np.argsort(np.where(np.isnan(ps), np.inf, ps))
    adj = np.full(len(ps), np.nan)
    run, m = 0.0, int(np.sum(~np.isnan(ps)))
    for rank, i in enumerate(order[:m]):
        run = max(run, (m - rank) * ps[i])
        adj[i] = min(1.0, run)
    return list(adj)


def fmt_p(p: float) -> str:
    return "-" if pd.isna(p) else ("<0.001" if p < 0.001 else f"{p:.3f}")


def _units(df: pd.DataFrame, method: str, scenario: str, metric: str):
    d = df[(df["method"] == method) & (df["scenario"] == scenario)]
    if d.empty or metric not in d or d[metric].isna().all():
        return None
    return unit_values(d, metric)


def comparison_frame(master: pd.DataFrame, pairs=PAIRS_MAIN, metrics=METRICS_CMP) -> pd.DataFrame:
    rows = []
    for a, b, sc, why in pairs:
        for m in metrics:
            ua, ub = _units(master, a, sc, m), _units(master, b, sc, m)
            if ua is None or ub is None:
                continue
            r = welch(ua[0], ub[0])
            overlap = not (r["mean_a"] + ci95(ua[0]) < r["mean_b"] - ci95(ub[0]) or
                           r["mean_b"] + ci95(ub[0]) < r["mean_a"] - ci95(ua[0])) if len(ua[0]) > 1 and len(ub[0]) > 1 else np.nan
            rows.append({"comparación": why, "A": a, "B": b, "A_lab": label(a), "B_lab": label(b), "escenario": sc, "metrica": m,
                         "unidad_A": ua[1], "unidad_B": ub[1],
                         **r, "ci_se_solapan": overlap})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_holm"] = holm(out["p"].tolist())
    return out


def verdict(r) -> str:
    if pd.isna(r["p"]):
        return "-"
    if r["p_holm"] < 0.05:
        return f"favorece a {r['A_lab'] if r['diff'] < 0 else r['B_lab']} (p Holm < 0.05)"
    if r["p"] < 0.05:
        return f"favorece a {r['A_lab'] if r['diff'] < 0 else r['B_lab']}, solo sin corregir (p < 0.05)"
    return "sin diferencia detectable"


def to_md(frame: pd.DataFrame, title: str, note: str) -> str:
    lines = [f"# {title}", "", note, ""]
    for sc in dict.fromkeys(frame["escenario"]):
        for m in dict.fromkeys(frame["metrica"]):
            f = frame[(frame["escenario"] == sc) & (frame["metrica"] == m)]
            if f.empty:
                continue
            lines += [f"## {sc}: {METRICS[m][0]}", "",
                      "| Comparación (A contra B) | A (media) | B (media) | A − B [IC95] | A − B (%) | n (A / B) | p (Welch) | p (Holm) | IC95 se solapan | Veredicto |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|"]
            for _, r in f.iterrows():
                pct = 100 * r["diff"] / r["mean_b"] if r["mean_b"] else np.nan
                lines.append(f"| {r['comparación']} | {r['mean_a']:.1f} | {r['mean_b']:.1f} | {r['diff']:+.1f} [{r['diff_lo']:+.1f}, {r['diff_hi']:+.1f}] | "
                             f"{pct:+.1f} % | {r['n_a']} / {r['n_b']} | {fmt_p(r['p'])} | {fmt_p(r['p_holm'])} | "
                             f"{'sí' if r['ci_se_solapan'] is True else ('no' if r['ci_se_solapan'] is False else '-')} | {verdict(r)} |")
            lines.append("")
    return "\n".join(lines)


def e7_frame(runs_dir) -> pd.DataFrame:
    """E7: agente aprendido (una semilla de entrenamiento) contra líneas base en cada variante; réplicas = episodios."""
    rob = load_csv(runs_dir, "E7/robustness.csv")
    if rob.empty:
        return rob
    rob = rob.assign(train_seed=np.nan)
    pairs = []
    for fam, learned in (("cruce", ["dqn_best", "ppo"]), ("reforma", ["marl_best", "comm_best"])):
        for v in dict.fromkeys(rob[rob["base"] == fam]["variant"]):
            sc = rob[(rob["base"] == fam) & (rob["variant"] == v)]["scenario"].iloc[0]
            for l in learned:
                for b in ("fixed", "max_pressure"):
                    pairs.append((l, b, sc, f"{label(l, 'E7')} contra {label(b).lower()}, {v}"))
    # los escenarios se repiten entre variantes (pico e incidente comparten escenario): se filtra por variante
    rows = []
    for a, b, sc, why in pairs:
        v = why.rsplit(", ", 1)[1]
        d = rob[(rob["variant"] == v) & (rob["scenario"] == sc)]
        for m in METRICS_CMP[:1]:
            ua, ub = _units(d, a, sc, m), _units(d, b, sc, m)
            if ua is None or ub is None:
                continue
            r = welch(ua[0], ub[0])
            rows.append({"comparación": why, "A": a, "B": b, "A_lab": label(a, "E7"), "B_lab": label(b, "E7"),
                         "escenario": f"{sc} [{v}]", "metrica": m, "unidad_A": ua[1],
                         "unidad_B": ub[1], **r, "ci_se_solapan": np.nan})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_holm"] = holm(out["p"].tolist())
    return out


def make_stats(runs_dir=RUNS_DIR, out_dir=RESULTS_DIR) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    master = load_master(runs_dir)
    if master.empty:
        return []
    frame = comparison_frame(master)
    if frame.empty:
        return []
    note = ("Prueba t de Welch (dos colas) sobre las réplicas: semilla de entrenamiento (media de sus 10 episodios de evaluación, n=5) "
            "en los métodos aprendidos y episodio de evaluación (n=10, semillas 1000 a 1009) en las líneas base. A − B < 0 favorece a A "
            "(menor demora o menor espera). `p (Holm)` corrige por el número de comparaciones de TODA la tabla de este archivo "
            "(no por escenario). Con n=5 el poder es bajo: «sin diferencia detectable» no prueba que sean iguales. "
            "«IC95 se solapan» compara los intervalos de cada media. Las comparaciones entre pares de métodos aprendidos usan n=5 contra n=5.")
    md = to_md(frame, "Comparaciones estadísticas de los pares clave", note)
    e7 = e7_frame(runs_dir)
    if not e7.empty:
        md += "\n\n" + to_md(e7, "E7: agente aprendido contra líneas base fuera de la hora de entrenamiento",
                             "Réplicas = 10 episodios de evaluación de UNA sola semilla de entrenamiento elegida por validación "
                             "(la varianza entre semillas de entrenamiento no está incluida: las diferencias significativas aquí "
                             "valen para esa semilla). Holm por las comparaciones de esta tabla.")
    p = out_dir / "comparaciones_estadisticas.md"
    p.write_text(md + "\n")
    allf = pd.concat([frame.assign(origen="matriz"), e7.assign(origen="E7")], ignore_index=True) if not e7.empty else frame
    c = out_dir / "comparaciones_estadisticas.csv"
    allf.to_csv(c, index=False)
    return [p, c]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=str(RUNS_DIR))
    ap.add_argument("--out-dir", default=str(RESULTS_DIR))
    a = ap.parse_args(argv)
    paths = make_stats(a.runs_dir, a.out_dir)
    print("\n".join(map(str, paths)) if paths else "sin datos")


if __name__ == "__main__":
    main()
