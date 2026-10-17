# Arquitectura y contratos entre módulos

Este archivo fija las interfaces que comparten todas las ramas. Si un módulo cumple su contrato, se puede integrar sin tocar los demás. Para cambiar un contrato hay que editar este archivo en `main`.

## 0. Entorno de trabajo
- Python 3.11, venv compartido en `../.venv` (fuera del repo, así lo usan todos los worktrees). Antes de correr cualquier cosa: `source scripts/env.sh`, que exporta `SUMO_HOME` y `PYTHONPATH`.
- Todo se corre desde la raíz del repo: `python -m experiments.train --config ...`, `python -m pytest`.
- Para entrenar: `export LIBSUMO_AS_TRACI=1`. La demo web **no** lo usa, porque corre dos simulaciones a la vez.
- `pettingzoo==1.24.3` queda fijo, porque sumo-rl 1.4.5 se rompe con la 1.25 o posterior.
- Las salidas van en `runs/` (ignorado por git). Las tablas y figuras finales se copian a `analysis/results/` y `docs/figures/`.

## 1. Escenarios (`env/scenarios.py`, ya en `main`)
- `get_scenario(name, **overrides) -> Scenario`, y `SCENARIOS` con todos los nombres.
- Toy, para desarrollar ya: `toy_single` (1 TLS) y `toy_grid2x2` (4 TLS), con las redes de sumo-rl.
- Reforma (los crea la rama `feat/env-reforma`):
  - `reforma_{pico,mediodia,pico_x13,noche}`: el corredor completo, `env/net/reforma.net.xml` (4–5 TLS).
  - `cruce_{pico,...}`: el cruce más cargado recortado del corredor, `env/net/cruce.net.xml` (1 TLS).
  - Cada red `X.net.xml` trae `X_fixed.add.xml` (programa de tiempo fijo "medido", el `programID` lo define la rama del entorno) y `X_actuated.add.xml` (programa `actuated`).
- Semillas: `TRAIN_SEEDS = [0..4]` y `EVAL_SEEDS = [1000..1009]`, que nunca se mezclan.
- `get_topology(net_file) -> {"order", "neighbors", "xy"}`: cadena de semáforos ordenados a lo largo del corredor. Sirve para observar a los vecinos y para la comunicación.

## 2. Fábrica de entornos (`env/reforma_env.py`, rama `feat/env-reforma`)
```python
make_parallel_env(scenario, seed=0, *, num_seconds=None, fixed_ts=False, program=None,
                  tripinfo_path=None, emissions=False, incident=None, use_gui=False,
                  out_csv=None, **sumo_rl_overrides) -> pettingzoo.ParallelEnv
make_gym_env(scenario, seed=0, **same) -> gymnasium.Env      # solo escenarios con 1 TLS
get_sumo_env(env) -> sumo_rl.SumoEnvironment                  # para .traffic_signals y .sumo (TraCI)
```
- `scenario` es un nombre o un `Scenario`. Pasa `delta_time`, `yellow_time`, `min_green`, `max_green` y `reward_fn` desde el Scenario. Si la demanda se genera, la ruta sale de `env.demand.routes_for(scenario, seed)`. Además pone `sumo_seed=seed`, `sumo_warnings=False` y `time_to_teleport` con un valor razonable (p. ej. 300) para que no haya bloqueos eternos.
- `fixed_ts=True` + `program="fixed"|"actuated"` carga el `.add.xml` que corresponde y activa ese programa.
- `tripinfo_path`: agrega `--tripinfo-output <path> --tripinfo-output.write-unfinished` (y `--device.emissions.probability 1` si `emissions=True`).
- `incident={"edge" o "lane": id, "start": s, "end": s}`: cierra el carril para `passenger` entre esos tiempos con TraCI. Se usa en E7 y en la demo.
- `make_gym_env` envuelve el entorno paralelo de 1 agente como `gymnasium.Env` (obs `Box` y acción `Discrete`) para SB3 y los agentes de 1 agente.

## 3. Demanda (`env/demand.py`, rama `feat/env-reforma`)
- `env/conteos/{pico,mediodia}.csv`, formato largo: `interseccion,aproximacion,movimiento,vehiculos_15min` (movimiento ∈ {recto, izquierda, derecha}). Por ahora son **sintéticos y provisionales** (lo dice un comentario en el CSV y `env/conteos/README.md`).
- `routes_for(scenario, seed, scale=None) -> str`: genera (con caché en `env/routes/cache/`) un `.rou.xml` con llegadas de Poisson que reproducen los conteos × `PROFILES[profile]["scale"]`. Es determinista por semilla, y semillas distintas dan llegadas distintas.
- `DemandGenerator(net_file, profile)` para la demo web: `rates()` por hora del día y `spawn(traci_conn, t)` para inyectar vehículos en línea con la misma semilla en A y B.

## 4. Política (`agents/base.py`, ya en `main`)
```python
class Policy:
    name: str; fixed_ts: bool = False; program: str | None = None
    def reset(self, sumo_env): ...                       # después de env.reset()
    def act(self, obs: dict[str, np.ndarray]) -> dict[str, int]: ...
```
Las políticas de 1 agente reciben un dict con una sola llave. Max-pressure usa `self.sumo_env.traffic_signals[ts]` (lanes, out_lanes, `get_pressure`-like) y TraCI.

## 5. Registro de algoritmos (`agents/registry.py`, ya en `main`, no se edita)
| algo | módulo | escenario típico |
|---|---|---|
| fixed, actuated, max_pressure | `baselines.*` → `make_policy(cfg)` | todos |
| qlearning, dyna_q | `agents.tabular.*` | cruce_* |
| dqn (flags `double`, `dueling`, `per`), ppo | `agents.dqn.dqn`, `agents.ppo.ppo` | cruce_* |
| idqn (flag `neighbor_obs`), qmix, mappo, comm | `agents.marl.*` | reforma_* |

Cada módulo que aprende expone `train(cfg) -> run_dir` y `load_policy(run_dir) -> Policy`.

## 6. Configuración de una corrida (YAML en `experiments/configs/<EXP>/<nombre>.yaml`)
```yaml
exp: E3                 # E1..E8
algo: dqn
name: dqn_double        # opcional, por defecto = algo
scenario: cruce_pico
seed: 0                 # train.py lo puede sobreescribir con --seed
total_episodes: 100     # presupuesto igual para todos (PLAN §8)
num_seconds: 3600       # se baja para pruebas rápidas
hparams: {...}          # propios del algoritmo
eval: {scenarios: [cruce_pico, cruce_mediodia], every_episodes: 10, episodes: 3}
```
`run_dir` por defecto: `runs/<exp>/<name>/seed<seed>/`. Adentro van: `config.yaml` (resuelto), `train_log.csv` (una fila por episodio con `episode, env_steps, return, mean_waiting_time, wall_time`), los checkpoints (`model.pt` / `qtable.npz` / etc.) y los eventos de TensorBoard en `tb/`.

## 7. Evaluación (`experiments/evaluate.py`, rama `feat/baselines-eval`)
```python
evaluate(policy, scenario, seeds=EVAL_SEEDS, *, num_seconds=None, incident=None, out_dir=None) -> pd.DataFrame
summarize(df, by=["method","scenario"]) -> pd.DataFrame     # media ± IC95 (t de Student)
```
Hay una fila por episodio con estas columnas: `method, scenario, seed, mean_waiting_time, mean_travel_time, mean_queue, max_queue, throughput_veh_h, mean_stops, p95_wait_by_approach (json), max_wait_cross_streets, co2_kg, arrived, teleported`. La CLI es `python -m experiments.evaluate --algo dqn --run runs/... --scenarios cruce_pico cruce_mediodia`.

## 8. Demo web (`web/`, ramas `feat/web-backend` y `feat/web-frontend`)
- El backend (FastAPI) expone `GET /api/network` (GeoJSON de carriles y TLS), `GET /api/scenarios` y `WS /ws`.
- Por el WS, cada tick se envía un JSON `{"t", "sims": {"fijo": {...}, "rl": {...}}}`, donde cada sim trae `{"vehicles": [[id,x,y,angle,speed],...], "tls": {id: state_string}, "metrics": {"mean_wait","queue","throughput","arrived"}}`.
- Comandos que manda el cliente (JSON): `{"cmd":"inject","edge":id,"n":k}`, `{"cmd":"time_of_day","profile":"pico|mediodia|noche"}`, `{"cmd":"incident","edge":id,"on":true|false}`, `{"cmd":"speed","value":0|1|5|20}`, `{"cmd":"reset","scenario":..., "policy":{"algo":..,"run":..}}`.
