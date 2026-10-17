# Matriz de experimentos E1 a E8

Cada experimento vive en `experiments/configs/<EXP>/*.yaml` (formato en `docs/ARCHITECTURE.md` §6). Se corren con `experiments.run_matrix`; los resultados quedan en `runs/<EXP>/<nombre>/seed<k>/` y se resumen con `python -m analysis.make_all`.

Reglas comunes (PLAN §8): 5 semillas de entrenamiento (`TRAIN_SEEDS = 0..4`), evaluación final en 10 episodios con `EVAL_SEEDS = 1000..1009` (nunca vistas en el entrenamiento), mismo presupuesto de entorno para todos los algoritmos RL de un experimento, y reporte como media ± IC95.

| Exp | Pregunta | Configs (`experiments/configs/...`) | Escenarios | Semillas | Presupuesto |
|---|---|---|---|---|---|
| E1 | ¿Qué tan bueno es lo actual? | `E1/baselines.yaml`: fijo, actuado, max-pressure | todos (`cruce_*`, `reforma_*`) | solo evaluación (10) | sin entrenamiento |
| E2 | ¿Cuánto ayuda planificar? | `E2/qlearning*.yaml`, `E2/dyna_q*.yaml` (variando pasos de planificación) | `cruce_pico`; eval también en `cruce_mediodia` | 5 | `total_episodes` igual en todas |
| E3 | ¿Qué variante de DQN aporta más? | `E3/dqn_*.yaml`: base, double, dueling, per y combinaciones | `cruce_pico` | 5 | igual en todas |
| E4 | ¿Value-based o policy-based? | `E4/dqn*.yaml`, `E4/ppo*.yaml` | `cruce_pico` | 5 | pasos de entorno iguales |
| E5 | ¿Ayuda entrenar centralizado? | `E5/idqn*.yaml`, `E5/qmix*.yaml`, `E5/mappo*.yaml` | `reforma_pico` | 5 | igual en todas |
| E6 | ¿Mejora la ola verde con comunicación? | `E6/idqn_*`, `E6/comm*.yaml` (IDQN con y sin `neighbor_obs`, mensajes aprendidos) | `reforma_pico` | 5 | igual que E5 |
| E7 | ¿Generaliza el mejor agente? | `E7/robustness.yaml` | `<base>_pico`, `_mediodia`, `_pico_x13`, `_pico` + incidente | los mejores run_dir de E3/E4/E5/E6 | solo evaluación |
| E8 | ¿Se sacrifica a las calles transversales? | `E8/fairness.yaml` (reúne `eval.csv` de todo) | `cruce_pico`, `reforma_pico` | las de cada experimento | solo cómputo de tablas |

Los YAML de E1 a E6 los aportan las ramas de líneas base y de algoritmos; `E7/` y `E8/` son de la rama de experimentos.

## Cómo correr

```bash
source scripts/env.sh
python -m experiments.run_matrix --dry-run                       # qué correría (marca los DONE)
python -m experiments.run_matrix --quick --exp E3                # prueba de humo (120 s, 2 episodios)
python -m experiments.run_matrix --exp E3 E4 --seeds 0 1 2 --jobs 4
python -m experiments.run_matrix --glob 'experiments/configs/E5/mappo*.yaml'
python -m experiments.train --config experiments/configs/E3/dqn_double.yaml --seed 0 --eval   # una sola corrida
```
- Fases en orden: E1, luego E2 a E6 (en paralelo con `--jobs N`, un proceso con su propio libsumo cada uno), luego E7, luego E8.
- Una corrida con `DONE` en su carpeta se salta; E7/E8 se recalculan si alguna corrida terminó después que ellos. `--force` ignora los `DONE`.
- `runs/manifest.csv` guarda estado, código de salida y tiempo de cada trabajo. Con `--quick` todo va a `runs/_quick/`.

## Contrato de salida que usa el análisis
- Entrenamiento: `train_log.csv` (`episode, env_steps, return, mean_waiting_time, wall_time`) en cada `seed<k>/`.
- Evaluación: `eval.csv` con las columnas del contrato §7 más `method` (nombre de la config), `train_seed` y `exp`.
- E7: `runs/E7/robustness.csv` (añade `variant`, `base`, `incident`); E8: `runs/E8/fairness.csv`.

## E7 y el incidente
`E7/robustness.yaml` tiene `incident.edge: null` como marcador: con la red de Reforma ya creada se puede fijar la arista; si queda en `null`, `experiments.robustness.default_incident_edge` toma la primera arista que une dos semáforos del corredor. El cierre dura de `start` a `end` segundos.

## E8 y la variante con penalización
Si la equidad sale mal, se entrena una variante con `r_t - lambda * espera_máxima_transversal` y se reporta el trade-off espera media contra espera máxima (PLAN §8.2, último párrafo). `E8/fairness.yaml` lo documenta en `penalized_variant`; la implementación del término de recompensa corresponde a la rama MARL.
