# Matriz de experimentos E1 a E8

Cada experimento vive en `experiments/configs/<EXP>/*.yaml` (formato en `docs/ARCHITECTURE.md` §6). Se corren con `experiments.run_matrix`; los resultados quedan en `runs/<EXP>/<nombre>/seed<k>/` y se resumen con `python -m analysis.make_all`.

Reglas comunes (PLAN §8): 5 semillas de entrenamiento (`TRAIN_SEEDS = 0..4`), selección del checkpoint con `VAL_SEEDS = 2000..2004`, evaluación final en 10 episodios con `EVAL_SEEDS = 1000..1009` (nunca vistas en el entrenamiento ni usadas para elegir nada), mismo presupuesto de entorno para todos los algoritmos RL de un experimento, y reporte como media ± IC95. Las tres familias de semillas (y las de los episodios de entrenamiento, `episode_seed >= 10 000`) son disjuntas.

| Exp | Pregunta | Configs (`experiments/configs/...`) | Escenarios | Semillas | Presupuesto |
|---|---|---|---|---|---|
| E1 | ¿Qué tan bueno es lo actual? | `E1/baselines.yaml`: fijo, actuado, max-pressure | todos (`cruce_*`, `reforma_*`) | solo evaluación (10) | sin entrenamiento |
| E2 | ¿Cuánto ayuda planificar? | `E2/qlearning*.yaml`, `E2/dyna_q*.yaml` (variando pasos de planificación) | `cruce_pico`; eval también en `cruce_mediodia` | 5 | `total_episodes` igual en todas |
| E3 | ¿Qué variante de DQN aporta más? | `E3/dqn_*.yaml`: base, double, dueling, per y combinaciones | `cruce_pico` | 5 | igual en todas |
| E4 | ¿Value-based o policy-based? | `E4/dqn*.yaml`, `E4/ppo*.yaml` | `cruce_pico` | 5 | pasos de entorno iguales |
| E5 | ¿Ayuda entrenar centralizado? | `E5/idqn*.yaml`, `E5/qmix*.yaml`, `E5/mappo*.yaml` | `reforma_pico` | 5 | igual en todas |
| E6 | ¿Mejora la ola verde con comunicación? | `E6/idqn_*`, `E6/comm*.yaml` (IDQN con y sin `neighbor_obs`, mensajes aprendidos) | `reforma_pico` | 5 | igual que E5 |
| E7 | ¿Generaliza el mejor agente? | `E7/robustness.yaml` | `<base>_pico`, `_mediodia`, `_pico_x13`, `_pico` + incidente | los mejores run_dir de E3/E4/E5/E6 | solo evaluación |
| E8 | ¿Se sacrifica a las calles transversales? | `E8/fairness.yaml` (reúne `eval.csv` de todo) + `E8/qmix_fair.yaml`, `E8/comm_fair.yaml` (variantes con penalización de equidad) | `cruce_pico`, `reforma_pico` | 5 (variantes) / las de cada experimento | igual que E5/E6 para las variantes |

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
- Fases en orden: E1, luego E2 a E6 y las configs de entrenamiento de E8 (en paralelo con `--jobs N`, un proceso con su propio libsumo cada uno), luego E7, luego la recolección de E8.
- Una corrida con `DONE` en su carpeta se salta; E7/E8 se recalculan si alguna corrida terminó después que ellos. `--force` ignora los `DONE`.
- `runs/manifest.csv` guarda estado, código de salida y tiempo de cada trabajo. Con `--quick` todo va a `runs/_quick/`.

## Checkpoints y selección del modelo (bloque `eval` de cada YAML)
```yaml
eval:
  scenarios: [cruce_pico, cruce_mediodia]   # evaluación final (EVAL_SEEDS)
  every_episodes: 20                        # checkpoint cada 20 episodios y al final
  val_seeds: 2                              # VAL_SEEDS[:2] para elegir el checkpoint
```
- Cada algoritmo deja `seed<k>/checkpoints/ep{N:04d}/` (modelo o tabla Q + `config.yaml`; PPO también `vecnormalize.pkl`). Cada carpeta se carga con `load_policy` igual que el `run_dir`. El modelo final (= el último checkpoint) sigue en el `run_dir`.
- Al terminar de entrenar, `experiments.train` evalúa cada checkpoint en el escenario **de entrenamiento** con `VAL_SEEDS[:val_seeds]` y la duración completa (`num_seconds`). El criterio es `total_delay` (demora total contando el backlog de inserción, ver `docs/ajuste_aprendizaje.md`) y, si `experiments/evaluate.py` no lo reporta, `mean_waiting_time`. El mejor se copia a `seed<k>/best/` y todos los puntajes quedan en `seed<k>/selection.csv` (`checkpoint, episode, criterion, score, total_delay, mean_waiting_time, ..., selected`); los episodios sueltos, en `selection_episodes.csv`.
- La evaluación final (`eval.csv`) y E7 cargan `experiments.common.policy_dir(run_dir)`: `best/` si existe, si no el `run_dir`.
- Por qué: en las corridas de sanidad la política del último episodio oscilaba mucho (QMIX: 38.5 s de demora total con 80 episodios contra 59.7 s con 200). Elegir con semillas aparte corrige eso sin tocar `EVAL_SEEDS`.
- Costo: `checkpoints × val_seeds` episodios de evaluación. Medido con 4 procesos en paralelo y 2 semillas: unos 3.2 s por checkpoint en `cruce_pico` y unos 11 s en `reforma_pico`. Con 200 episodios y `every_episodes: 20` (10 checkpoints) son unos 35 s por corrida en el cruce y unos 110 a 120 s en el corredor, cerca del 10 % del entrenamiento (en la matriz E2–E6 + E8 con 5 semillas: unos 5 800 proceso·s, unos 12 min de pared con `--jobs 8`). Si solo hay un checkpoint (p. ej. `--quick`) se copia sin evaluar.
- `--no-select` (en `experiments.train` y `experiments.run_matrix`) se salta la selección y evalúa el último modelo. `python -m experiments.train --config X.yaml --seed k --select-only [--eval]` repite la selección de una corrida ya entrenada.

## Contrato de salida que usa el análisis
- Entrenamiento: `train_log.csv` (`episode, env_steps, return, mean_waiting_time, wall_time`) en cada `seed<k>/`.
- Selección: `selection.csv` y `best/` (sección anterior).
- Evaluación: `eval.csv` con las columnas del contrato §7 más `method` (nombre de la config), `train_seed` y `exp`. Se calcula con el checkpoint de `best/`.
- E7: `runs/E7/robustness.csv` (añade `variant`, `base`, `incident`, `train_seed`, `selection`, `policy_dir`) y `runs/E7/robustness_summary.csv` (media ± IC95 por método, base y variante; columna `ci_over`); E8: `runs/E8/fairness.csv`.

## E7: qué semilla de entrenamiento se evalúa
Cada entrada de `learned` en `E7/robustness.yaml` elige sus corridas **sin mirar `EVAL_SEEDS`** (elegir la mejor semilla por su `eval.csv` y después reportarla en las mismas semillas sesga E7 a favor del agente):
- `select: best` (por defecto): la semilla con el mejor puntaje de validación del checkpoint elegido (`selection.csv`, `VAL_SEEDS`). Primero las que se eligieron por `total_delay`, después por `mean_waiting_time`; si una corrida no tiene `selection.csv`, cuenta el retorno medio del último 10 % del entrenamiento.
- `select: all`: todas las semillas de entrenamiento. `robustness_summary.csv` promedia cada semilla sobre sus episodios de evaluación y da la media ± IC95 **entre semillas de entrenamiento** (`ci_over = train_seeds`). Es la opción más honesta, pero cuesta 5 veces más.
- `select: first` o `run_dir:` fijo, para pruebas.

## E7 y el incidente
`E7/robustness.yaml` tiene `incident.edge: null` como marcador: con la red de Reforma ya creada se puede fijar la arista; si queda en `null`, `experiments.robustness.default_incident_edge` toma la primera arista que une dos semáforos del corredor. El cierre dura de `start` a `end` segundos.

## E8 y la variante con penalización
En las corridas de sanidad QMIX dejó una calle transversal sin servir hasta 1573 s. La variante (PLAN §8.2, último párrafo) usa la recompensa `diff-waiting-time-pending-fair` de `agents/rewards.py`:

    M_t = máx. sobre aproximaciones de la espera del vehículo que más lleva esperando en ella
          (espera acumulada en los carriles de este cruce, o tiempo pendiente de inserción)
    r_t = r_t^pending − fair_lambda · (M_t − M_{t−1}) / 100

Está en las mismas unidades que la recompensa base: mientras la cabeza de una cola desatendida sigue esperando, el agente paga `fair_lambda` "vehículos equivalentes" extra; cuando se la atiende, `M` baja y el término se devuelve (es telescópico, igual que la recompensa base). Una calle transversal con pocos autos casi no pesa en la espera sumada, pero `M_t` crece 5 s en cada paso solo por ella. `fair_lambda = 0.5` (por defecto) hace que el vehículo que más espera cuente 1.5 veces: es un empujón moderado que no cambia el orden de magnitud de la recompensa.

Sanidad (semilla 0, 50 episodios en `reforma_pico`, selección con 5 checkpoints, evaluación en las semillas 1000 a 1002; demora total calculada aparte desde el tripinfo):

| Corrida | Espera media [s] | Demora total [s] | Backlog | Espera máx. transversal [s] (media / máx.) |
|---|---|---|---|---|
| QMIX | 46.2 | 50.6 | 0.33 % | 328 / 414 |
| QMIX fair, λ = 1 | 42.3 | 44.6 | 0.10 % | 342 / 376 |
| QMIX fair, λ = 0.5 | 41.0 | 41.9 | 0.00 % | 288 / 399 |
| comm | 58.2 | 66.4 | 0.66 % | **1269 / 1470** |
| comm fair, λ = 1 | 55.3 | 128.5 | 6.03 % | 430 / 498 |
| comm fair, λ = 0.5 | 42.0 | 125.6 | 5.60 % | 268 / 328 |

La penalización elimina el hambre de la calle transversal que aparece con comm (1269 s → 268–430 s) y con QMIX mejora o empata todo. Pero los checkpoints de comm fair que se eligieron dejan un 5–6 % de backlog: la selección usó `mean_waiting_time`, porque esta rama todavía no tiene `total_delay` en `evaluate.py`, y esa métrica premia el bloqueo de entradas. Con λ = 1, el checkpoint del episodio 40 tenía 88 s de demora y 2 % de backlog. Con `total_delay` como criterio se elegiría otro. Es una sola semilla corta: la matriz con 5 semillas y 200 episodios decide. λ = 0.5 queda por defecto porque fue igual o mejor que λ = 1 en las dos familias.

`E8/qmix_fair.yaml` y `E8/comm_fair.yaml` usan el mismo presupuesto e hiperparámetros que `E5/qmix.yaml` y `E6/comm.yaml`; `run_matrix` los entrena en la fase 2 (con selección y evaluación final) y `E8/fairness.yaml` también reúne sus `eval.csv`. El trade-off se lee comparando `qmix` contra `qmix_fair` y `comm` contra `comm_fair` (espera media y demora total contra `max_wait_cross_streets`).
