# Semáforos inteligentes en Av. La Reforma con RL multiagente

Proyecto final de CC3104 Aprendizaje por Refuerzo (UVG, ciclo 2, 2026). Simulamos en SUMO un corredor de Av. La Reforma (zona 9/10, 5 semáforos) y un cruce recortado de él, y comparamos agentes RL (Q-Learning, Dyna-Q, DQN y sus variantes, PPO, IDQN, QMIX, MAPPO y un agente con comunicación aprendida) contra tres líneas base: tiempo fijo, actuado y max-pressure. Los experimentos son E1 a E8 (`experiments/configs/README.md`).

Guía rápida: [instalar](#instalación) -> [probar](#prueba-de-humo) -> [matriz completa](#matriz-completa) -> [análisis](#análisis-de-resultados) -> [demo web](#demo-web) -> [informe PDF](#informe-pdf).

## Instalación
Necesita Python 3.11 (SUMO, libsumo y sumo-rl se instalan con pip, sin instalar SUMO aparte). Para el frontend de la demo hace falta Node; para el PDF, Google Chrome.

```bash
bash scripts/setup_env.sh      # crea ../.venv (compartido entre worktrees) e instala requirements.txt
source scripts/env.sh          # activa el venv y exporta SUMO_HOME y PYTHONPATH
python -m pytest -q            # pruebas; con -m "not slow" se saltan las simulaciones largas
```
- Con `uv` instalado, `setup_env.sh` crea el venv con Python 3.11; si no, usa `python3 -m venv`. `VENV=.venv bash scripts/setup_env.sh` lo deja dentro del repo.
- `pettingzoo==1.24.3` queda fijo en `requirements.txt` porque `sumo-rl` 1.4.5 se rompe con la 1.25 o posterior.
- No hace falta exportar `LIBSUMO_AS_TRACI`: `train`, `evaluate`, `robustness` y `run_matrix` lo ponen (libsumo corre una sola simulación por proceso; con `--no-libsumo` usan TraCI normal, por ejemplo para abrir `sumo-gui`). La demo web **no** lo usa, porque corre dos simulaciones a la vez.
- Todo se corre desde la raíz del repo y después de `source scripts/env.sh`.

## Reconstruir la red y la demanda
La red, los programas fijo y actuado y los nombres de los semáforos ya vienen en `env/net/`. Para regenerarlos desde el extracto de OpenStreetMap y los conteos:
```bash
bash scripts/build_network.sh   # env/conteos (solo si son sintéticos) -> env/net/*.net.xml + programas + tls_names.json
python -m env.validate          # tiempo de viaje del corredor con tiempo fijo vs. la referencia (imprime CALIBRACION OK si cumple)
```
La demanda de cada episodio se genera al vuelo con la semilla del episodio (`env/demand.py`, caché en `env/routes/cache/`). Detalle de la red y de la calibración: `env/net/README.md` y `env/conteos/README.md`.

## Prueba de humo
```bash
python -m experiments.run_matrix --dry-run        # lista los 88 trabajos de la matriz y marca los que ya tienen DONE
python -m experiments.run_matrix --quick          # toda la matriz en versión mínima (120 s simulados, 2 episodios); sale en runs/_quick/
python -m experiments.run_matrix --quick --exp E3 --seeds 0 --jobs 2
```

## Matriz completa
```bash
python -m experiments.run_matrix --jobs 8         # E1 a E8, semillas 0 a 4, 200 episodios por corrida: unas 4 a 5 h con 8 núcleos
```
Fases, en este orden (cada una espera a la anterior): E1 (evaluación de las líneas base); E2 a E6 y las variantes con equidad de E8 (entrenamiento, un proceso por config x semilla); E7 (robustez); recolección de E8. Un trabajo con `DONE` en su carpeta se salta, así que se puede relanzar tras un corte (`--force` los ignora). `runs/manifest.csv` guarda estado, código de salida y tiempo de cada trabajo.

Por experimento (misma fase 2 con `--jobs N` para paralelizar):
```bash
python -m experiments.run_matrix --exp E1                       # líneas base (un solo proceso)
python -m experiments.run_matrix --exp E2 --jobs 8              # Q-Learning y Dyna-Q (cruce_pico)
python -m experiments.run_matrix --exp E3 --jobs 8              # variantes de DQN
python -m experiments.run_matrix --exp E4 --jobs 8              # DQN vs PPO
python -m experiments.run_matrix --exp E5 --jobs 8              # IDQN, QMIX, MAPPO (reforma_pico)
python -m experiments.run_matrix --exp E6 --jobs 8              # IDQN con vecinos, comm
python -m experiments.run_matrix --exp E8 --jobs 8              # qmix_fair y comm_fair + recolección de equidad
python -m experiments.run_matrix --exp E7                       # robustez; necesita E3 a E6 terminados
python -m experiments.run_matrix --glob 'experiments/configs/E5/mappo*.yaml' --seeds 0 1   # solo algunas configs y semillas
```
Una sola corrida y su selección de checkpoint:
```bash
python -m experiments.train --config experiments/configs/E5/qmix.yaml --seed 0 --eval
python -m experiments.train --config experiments/configs/E5/qmix.yaml --seed 0 --select-only --eval   # repite la selección de una corrida ya entrenada
```
Cada corrida deja en `runs/<EXP>/<nombre>/seed<k>/`: `config.yaml`, `train_log.csv`, `checkpoints/`, `best/` (el checkpoint elegido), `selection.csv`, `eval.csv` y `DONE`. E7 escribe `runs/E7/robustness.csv` y E8 `runs/E8/fairness.csv`. `runs/` no se versiona.

## Evaluación
Todas las políticas se evalúan con el mismo código (`experiments/evaluate.py`): una fila por episodio, solo desde el tripinfo de SUMO y el archivo de rutas.
```bash
# líneas base en un escenario
python -m experiments.evaluate --algo fixed actuated max_pressure --scenarios reforma_pico --out /tmp/baselines.csv
# un modelo entrenado (carga run_dir/best si existe y lo imprime; si no, el último modelo)
python -m experiments.evaluate --algo qmix --run runs/E5/qmix/seed0 --scenarios reforma_pico reforma_mediodia
# la configuración de E1
python -m experiments.evaluate --config experiments/configs/E1/baselines.yaml --out-dir runs/E1/baselines
```
Sin `--seeds` usa las `EVAL_SEEDS` (1000 a 1009). Las columnas y su definición están en `docs/ARCHITECTURE.md` §7.

## Análisis de resultados
```bash
python -m analysis.make_all     # figuras -> docs/figures/ (png y pdf), tablas -> analysis/results/*.md; salta lo que no tiene datos
```
Opciones: `--runs-dir`, `--fig-dir`, `--table-dir`, `--latex`. Cada tabla y figura muestra media ± IC95, con la demora total y el backlog junto a la espera media.

## Demo web
Dos simulaciones en paralelo (tiempo fijo contra una política) con el mismo tráfico, dibujadas en el navegador. Usa el modelo `best/` de la corrida que elijas.
```bash
cd web/frontend && npm install && npm run build && cd ../..    # una vez: genera web/frontend/dist
source scripts/env.sh
python -m uvicorn web.backend.app:app --port 8000               # http://localhost:8000
```
`WEB_SCENARIO=cruce_pico` cambia el escenario inicial y `WEB_RUNS_DIR=/ruta/a/runs` apunta a otras corridas (por ejemplo las traídas de Colab). Detalles, API y guion de demo: `web/README.md`.

## Informe PDF
```bash
python docs/informe/render_pdf.py --pdf           # borrador: docs/informe/informe.pdf (muestra los marcadores pendientes)
python docs/informe/render_pdf.py --pdf --final   # entrega: oculta los marcadores RESULTADOS y COMPLETAR
```
Convierte `docs/informe/informe.md` a HTML con KaTeX y lo imprime con Chrome headless (no necesita LaTeX ni pandoc). Los resultados se pegan desde `analysis/results/`; ver `docs/informe/README.md`.

## Google Colab (opcional)
La matriz completa corre en la Mac; Colab sirve para semillas extra, presupuestos más largos o repetir corridas. Guía, tiempos y problemas comunes: [docs/COLAB.md](docs/COLAB.md). Cuadernos: `notebooks/colab_train.ipynb` (entrenar) y `notebooks/colab_analysis.ipynb` (figuras y tablas).

## Estructura
Las interfaces entre módulos están en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

| Carpeta | Contenido |
|---|---|
| `env/` | Red de Reforma (`net/`), conteos (`conteos/`), demanda (`demand.py`), escenarios y semillas (`scenarios.py`), fábrica de entornos (`reforma_env.py`), incidentes y validación |
| `baselines/` | Tiempo fijo, actuado, max-pressure |
| `agents/` | Q-Learning y Dyna-Q (`tabular/`), DQN con Double, Dueling y PER (`dqn/`), PPO (`ppo/`), IDQN, QMIX, MAPPO y comunicación (`marl/`), recompensas (`rewards.py`) y registro |
| `experiments/` | Configs YAML de E1 a E8 (`configs/`), `train.py`, `evaluate.py`, `metrics.py`, `robustness.py` (E7 y recolección de E8), `run_matrix.py` |
| `analysis/` | `make_all.py`, `plots.py`, `tables.py`, `data.py` |
| `web/` | Demo en vivo (FastAPI en `backend/`, React en `frontend/`) |
| `docs/` | `ARCHITECTURE.md`, `ajuste_aprendizaje.md`, `COLAB.md`, informe (`informe/`) y figuras generadas |
| `notebooks/` | Cuadernos de Google Colab (se generan con `scripts/colab_make_notebooks.py`) |
| `scripts/` | Entorno (`setup_env.sh`, `env.sh`), red (`build_network.sh`) y Colab |
| `tests/` | Pruebas con pytest |

## Decisiones de diseño
- **Conteos sintéticos, PROVISIONALES.** `env/conteos/{pico,mediodia}.csv` no son conteos de campo: los genera `env/synthetic_counts.py` y se calibraron contra un tiempo de viaje de referencia que tampoco es medido (330 s hacia el norte y 300 s hacia el sur, un placeholder en `env/validate.py`). El ciclo del tiempo fijo es igual de sintético (reparto de Webster). Con datos reales se reemplazan los CSV y se reconstruye con `scripts/build_network.sh`, que no pisa conteos que ya no sean sintéticos.
- **Recompensa con el backlog de inserción.** La recompensa de sumo-rl solo cuenta la espera de los autos que están en los carriles de entrada, y los agentes aprendían a cerrar una entrada: los autos que no cabían esperaban afuera sin costo. `diff-waiting-time-pending` (`agents/rewards.py`) suma la espera de los vehículos que SUMO no pudo insertar. La recompensa solo se usa para entrenar; la evaluación no la usa (`docs/ajuste_aprendizaje.md` §3).
- **`total_delay` como métrica principal.** `mean_waiting_time` promedia solo sobre los vehículos insertados y premia dejar autos fuera. `total_delay` cuenta a todos los vehículos de la demanda (el que nunca entró cuenta como si hubiera esperado afuera hasta el final), junto con `backlog_pct`.
- **Selección de checkpoint por validación.** Cada corrida guarda checkpoints cada 20 episodios y se queda con el de menor `total_delay` en `VAL_SEEDS` (2000 a 2004). La evaluación final carga ese `best/` y usa `EVAL_SEEDS` (1000 a 1009). Las semillas de entrenamiento, validación y evaluación son familias disjuntas, y E7 elige qué semilla de entrenamiento evaluar sin mirar `EVAL_SEEDS`.
- **Max-pressure es una línea base fuerte.** Usa conjuntos de carriles (no enlaces), presión por ocupación y hace cumplir `max_green`. Los agentes RL tienen que ganarle a él, no solo al tiempo fijo.
- **Mismo presupuesto, varias semillas.** Dentro de cada experimento, todos los algoritmos usan los mismos pasos de entorno (200 episodios) y 5 semillas de entrenamiento; se reporta media ± IC95.
- **Equidad (E8).** Las variantes `qmix_fair` y `comm_fair` penalizan la espera máxima por aproximación, para ver si el agente sacrifica a las calles transversales.

## Resultados

<!-- RESULTADOS -->
