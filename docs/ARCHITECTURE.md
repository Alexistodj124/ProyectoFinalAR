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
- Reforma:
  - `reforma_{pico,mediodia,pico_x13,noche}`: el corredor completo, `env/net/reforma.net.xml` (4–5 TLS).
  - `cruce_{pico,...}`: el cruce más cargado recortado del corredor, `env/net/cruce.net.xml` (1 TLS).
  - Cada red `X.net.xml` trae `X_fixed.add.xml` (programa de tiempo fijo "medido", el `programID` lo define la rama del entorno) y `X_actuated.add.xml` (programa `actuated`).
- Semillas: `TRAIN_SEEDS = [0..4]`, `VAL_SEEDS = [2000..2004]` y `EVAL_SEEDS = [1000..1009]`, que nunca se mezclan. `VAL_SEEDS` (se agrega a `env/scenarios.py` en la rama de checkpoints) se usa **solo** para elegir el mejor checkpoint de una corrida (ver §6); la tabla final de resultados usa siempre `EVAL_SEEDS`.
- `get_topology(net_file) -> {"order", "neighbors", "xy"}`: cadena de semáforos ordenados a lo largo del corredor. Sirve para observar a los vecinos y para la comunicación.

## 2. Fábrica de entornos (`env/reforma_env.py`, ya en `main`)
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
- `env.reset(seed=k)` regenera la demanda con la semilla `k` (si el escenario la genera). Al entrenar se usa `env.reset(seed=experiments.common.episode_seed(seed, ep))`, así cada episodio ve una realización distinta pero reproducible. Al evaluar se usan las `EVAL_SEEDS`.
- Funciona con los escenarios toy y con Reforma, incluye `tripinfo_path` y acepta rutas con espacios (el repo está bajo `Proyecto Final/`). Por eso `additional_sumo_cmd` se arma con `_ArgList`.

## 2b. Utilidades de entrenamiento (`experiments/common.py`, ya en `main`)
`load_config`, `resolve_run_dir(cfg)`, `save_config`, `set_seed`, `episode_seed(seed, ep)` y `TrainLogger(run_dir).log_episode(**fila)`, que escribe `train_log.csv` y TensorBoard. Todos los algoritmos los usan, para que los logs sean homogéneos.

**Recompensa de entrenamiento y métrica de evaluación son cosas distintas.** Los aprendices pasan `reward_fn` (de `agents/rewards.py`, por defecto `diff-waiting-time-pending`, hiperparámetro `reward_fn: scenario` para volver a la original de sumo-rl) a `make_parallel_env(...)` por los `**sumo_rl_overrides`, y eso pisa el `reward_fn` del `Scenario`. `diff-waiting-time-pending` suma a la espera de los carriles de entrada la de los vehículos que SUMO no pudo insertar (`edge.getPendingVehicles`); sin ella, cerrar una entrada era una política óptima (docs/ajuste_aprendizaje.md §3). La **evaluación nunca usa la recompensa**: sale solo del tripinfo de SUMO y del archivo de rutas (§7).

## 3. Demanda (`env/demand.py`, ya en `main`)
- `env/conteos/{pico,mediodia}.csv`, formato largo: `interseccion,aproximacion,movimiento,vehiculos_15min` (movimiento ∈ {recto, izquierda, derecha}). Por ahora son **sintéticos y provisionales**, calibrados contra el tiempo de viaje de referencia (lo dice un comentario en el CSV y `env/conteos/README.md`).
- `routes_for(scenario, seed, scale=None) -> str`: genera (con caché en `env/routes/cache/`) un `.rou.xml` con llegadas de Poisson que reproducen los conteos × `PROFILES[profile]["scale"]`. Es determinista por semilla, y semillas distintas dan llegadas distintas. Todos los vehículos llevan `id`, `depart` explícito y el `vType` calibrado `auto`; de ahí sale `loaded` en §7.
- `DemandGenerator(scenario, profile="pico", seed=0)` para la demo web (`scenario` es un nombre o un `Scenario`; `profile` ∈ `PROFILES`):
  - `rates() -> {"profile", "scale", "veh_h", "by_entry"}` y `set_profile(profile)` (cambia la hora del día sin cambiar los ids de ruta).
  - `arrivals(s) -> [(vehicle_id, route_idx)]`: las llegadas del segundo entero `s` salen de una RNG con semilla `(seed, s)`, así que no dependen de cuántas veces se llame ni de quién llame.
  - `spawn(conn, t) -> int`: inyecta por TraCI todas las llegadas en `(último t, t]` y devuelve cuántas entraron. Lleva **un cursor por conexión**, así dos simulaciones (A y B) reciben los mismos ids, rutas e instantes.
  - `inject(conns, edge, n) -> [ids]`: `n` vehículos en `edge` por la ruta más probable, con los mismos ids en todas las conexiones (devuelve los que **todas** aceptaron).
  - **Robustez:** un vehículo (o ruta) que SUMO rechaza, p. ej. una ruta por una arista cerrada a `passenger`, se omite individualmente y se registra a nivel debug. El cursor avanza siempre (segundo a segundo y en un `finally`), por lo que ningún segundo se reintenta y no hay ids duplicados. Solo una conexión caída (`FatalTraCIError`) se propaga.

## 4. Política (`agents/base.py`, ya en `main`)
```python
class Policy:
    name: str; fixed_ts: bool = False; program: str | None = None
    def reset(self, sumo_env): ...                       # después de env.reset()
    def act(self, obs: dict[str, np.ndarray]) -> dict[str, int]: ...
```
Las políticas de 1 agente reciben un dict con una sola llave. Max-pressure usa `self.sumo_env.traffic_signals[ts]` y TraCI: para cada fase de verde toma el **conjunto** de carriles de entrada y de salida que abre (cada carril una vez), con presión = Σ ocupación de entrada − Σ ocupación de salida (autos × (2.5 m + largo) / largo del carril), y hace cumplir `max_green` (sumo-rl no lo hace). Sumar por enlace controlado favorecía siempre a las fases de Reforma (8 enlaces) sobre las transversales (5) y trababa el corredor calibrado.

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
`run_dir` por defecto: `runs/<exp>/<name>/seed<seed>/`. Adentro van: `config.yaml` (resuelto), `train_log.csv` (una fila por episodio con `episode, env_steps, return, mean_waiting_time, wall_time`), el modelo final (`model.pt` / `qtable.npz` / etc., el del **último** episodio) y los eventos de TensorBoard en `tb/`.

**Selección de checkpoint** (rama `feat/checkpoints-validacion`, en curso): durante el entrenamiento se guardan `run_dir/checkpoints/ep<N>/` y se evalúan con `VAL_SEEDS = 2000..2004`; el mejor se copia a `run_dir/best/`. La política final de un experimento es la de `best/`, no la del último episodio (las curvas de DQN y de los métodos MARL de valor oscilan incluso con ε = 0.05). `python -m experiments.evaluate --run <run_dir>` carga de `<run_dir>/best` si existe y lo imprime; si no, usa el modelo del último episodio. Las semillas de validación nunca entran en las tablas finales: eso sigue siendo `EVAL_SEEDS`.

## 7. Evaluación (`experiments/evaluate.py` y `experiments/metrics.py`, ya en `main`)
```python
evaluate(policy, scenario, seeds=EVAL_SEEDS, *, num_seconds=None, incident=None, out_dir=None,
         method=None, keep_tripinfo=True) -> pd.DataFrame
summarize(df, by=["method","scenario"]) -> pd.DataFrame     # <métrica>_mean y <métrica>_ci95 (t de Student)
```
Hay una fila por episodio. Columnas originales: `method, scenario, seed, mean_waiting_time, mean_travel_time, mean_queue, max_queue, throughput_veh_h, mean_stops, p95_wait_by_approach (json), max_wait_cross_streets, co2_kg, arrived, teleported`. Columnas de demanda (se agregan al final, `summarize` también las cubre): `loaded, inserted, backlog_pct, mean_depart_delay, total_delay`.

**Por qué hacen falta.** `mean_waiting_time` es el promedio sobre los vehículos *insertados*. Un controlador que deja una entrada llena mantiene fuera de la red parte de la demanda sin costo en esa métrica (docs/ajuste_aprendizaje.md §3). Las columnas siguientes cuentan a todos los vehículos de la demanda:
- `loaded`: vehículos del `.rou.xml` del episodio con `depart < num_seconds` (misma regla que `env.validate.loaded_vehicles`). Si el escenario usa `<flow>` probabilísticos (los `toy_*`), la demanda no se puede enumerar y `loaded = inserted` (sin backlog).
- `inserted`: vehículos que SUMO sí metió en la red (filas del tripinfo, incluidos los que siguen dentro al terminar).
- `backlog_pct = 100 · (loaded − inserted) / loaded`.
- `mean_depart_delay`: media de `departDelay` (segundos que esperó *afuera* antes de entrar) sobre los insertados.
- `total_delay = [ Σ_insertados (waitingTime + departDelay) + Σ_nunca insertados (num_seconds − depart) ] / loaded`, en segundos por vehículo de la demanda. Un auto que nunca entró cuenta como si hubiera esperado afuera hasta el final del episodio, así que `total_delay` no se puede reducir dejando autos fuera.

Las demás convenciones (tripinfo con `--tripinfo-output.write-unfinished`, cola = vehículos con v < 0.1 m/s en los carriles de entrada, calle transversal = nombre de arista sin "Reforma") están en el docstring de `experiments/metrics.py`.

**CLI.** `python -m experiments.evaluate --algo dqn --run runs/... --scenarios cruce_pico cruce_mediodia`:
- `--out FILE` guarda el CSV de todas las filas y `<FILE>_summary.csv`; `--out-dir DIR` guarda `DIR/eval.csv`, `DIR/eval_summary.csv` y `DIR/eval_<método>_<escenario>.csv` (lo usa `run_matrix`). `--keep-tripinfo` guarda además `DIR/tripinfo/*.xml` (pesados en `reforma_*`; por defecto no). `analysis.data.load_eval` ignora los `eval_summary.csv` y los `eval_<método>_<escenario>.csv` cuando existe `eval.csv`, para no contar filas dos veces.
- `--run` apunta al `run_dir`. Si trae `best/` se carga de ahí y se imprime cuál se usó.

## 8. Demo web (`web/`, ya en `main`; detalles y demo en `web/README.md`)
- El backend (FastAPI, `web/backend/app.py`) expone `GET /api/network?scenario=`, `GET /api/scenarios`, `GET /api/policies?scenario=`, `GET /api/status`, `GET /api/state` y `WS /ws`. No usa `LIBSUMO_AS_TRACI` (dos simulaciones a la vez por TraCI de socket).
- `GET /api/network` (`web/backend/geometry.py`) devuelve la red en coordenadas SUMO (metros, y hacia el norte):
  ```
  {"scenario", "bbox": [minx, miny, maxx, maxy], "projected": bool,
   "lanes":  [{"id", "edge", "name", "shape": [[x, y], ...], "width", "allow_passenger"}],
   "edges":  [{"id", "name", "from", "to", "shape"}],
   "junctions": [{"id", "type", "shape"}],
   "tls":    [{"id", "x", "y", "name", "links": [[indice_en_el_estado, carril, x, y], ...]}]}
  ```
  `tls[].name` sale de `env/net/tls_names.json` ("Reforma y 12 calle"); `links[i]` dice qué carácter del string de estado del semáforo corresponde a qué carril y a qué línea de alto. Con proyección geográfica y `pyproj` se agregan `lon/lat` por TLS y `bbox_lonlat`.
- **Mensajes del WebSocket, servidor → cliente**, todos con `"type"`:
  - `state` (uno por paso de simulación; en pausa, un latido por segundo): `{"type":"state","t","episode","speed","scenario","profile","demand_veh_h","incidents":[edge...],"policy":{"algo","label","warning"},"improvement_pct","sims":{"fijo":{...},"rl":{...}}}`. Cada sim trae `{"vehicles": [[id,x,y,angle,speed],...], "tls": {id: state_string}, "metrics": {"mean_wait","queue","throughput","arrived","n_vehicles"}}` (máximo 1500 vehículos por sim).
  - `ack`: respuesta a un comando, solo al socket que lo mandó: `{"type":"ack","cmd","ok":true,"result"}` o `{"type":"ack","cmd","ok":false,"error"}`.
  - `loading` (`{"type":"loading","scenario"}`, mientras se reconstruyen las sims) y `error` (`{"type":"error","message"}`); ninguno lleva `sims`.
- **Comandos cliente → servidor** (JSON, se aplican a las dos sims en el mismo segundo simulado): `{"cmd":"inject","edge":id,"n":k}`, `{"cmd":"time_of_day","profile":"pico|mediodia|noche|pico_x13"}`, `{"cmd":"incident","edge":id,"on":true|false}`, `{"cmd":"speed","value":0|1|5|20}` (cualquier valor 0–60) y `{"cmd":"reset","scenario":..., "policy":{"algo":..,"run":..}, "seed":1000}`.
- Las métricas en vivo (`mean_wait`, `queue`, `throughput`) son una vista rápida de la demo, **no** las de §7: `mean_wait` incluye a los vehículos que siguen en la red pero no cuenta backlog.
