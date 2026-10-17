# `agents/marl`: RL multiagente para el corredor de Reforma

Implementaciones propias, en estilo CleanRL, de los cuatro métodos de E5/E6. Cada módulo expone `train(cfg) -> run_dir` y `load_policy(run_dir) -> Policy` (contrato de `docs/ARCHITECTURE.md` §5).

| Módulo | Algoritmo | Experimento | Idea clave |
|---|---|---|---|
| `idqn.py` | IDQN: un Double-DQN por semáforo | E5, E6 (`neighbor_obs`) | Aprendices independientes, no estacionariedad |
| `qmix.py` | QMIX (Rashid et al. 2018) | E5 | CTDE, mezcla monótona con hiperredes condicionadas a s |
| `mappo.py` | MAPPO (Yu et al. 2022) | E5 | Actor compartido y crítico centralizado V(s), GAE y clip de PPO |
| `comm.py` | Mensajes aprendidos (DIAL) | E6 | Mensaje de 4 a 8 floats para los vecinos, entrenado de punta a punta |
| `common.py` | Utilidades | todos | Padding, máscaras, estado global, recompensa de equipo, bucle del env |

## Por qué implementación propia y no BenchMARL/EPyMARL
1. **Integración con sumo-rl.** sumo-rl expone un `ParallelEnv` de PettingZoo 1.24 (fijado porque sumo-rl se rompe con la 1.25). BenchMARL depende de TorchRL y de sus propios wrappers de PettingZoo, y EPyMARL usa el registro de gym de pymarl con un bucle propio. Las dos obligan a escribir un adaptador y a lidiar con versiones incompatibles en Colab. Nuestro bucle (`MultiAgentRunner`) usa directamente `make_parallel_env` de `env/reforma_env.py`, y así la demanda por semilla, el tripinfo y los incidentes funcionan igual que con los demás algoritmos.
2. **Agentes heterogéneos.** Los cruces de Reforma tienen distinto número de fases y de carriles. Hacía falta un padding estructurado y máscaras de acción en el argmax, en el softmax y en el máximo del objetivo TD. En las librerías eso supone parchear su código. Aquí son ~40 líneas.
3. **Simplicidad y docencia.** Cada algoritmo está en un archivo de 200 a 300 líneas, y sus líneas clave apuntan a las fórmulas del curso (objetivo TD, Double-Q, monotonicidad, GAE, clip). Eso sirve para el informe y para defender el código.
4. **Colab.** Las únicas dependencias son torch y numpy (ya están en el venv), no hay Ray/Hydra/TorchRL, funciona igual en Python 3.11 y 3.12, y en CPU o GPU (`device: auto`).
5. **Logs homogéneos.** Todo pasa por `experiments.common` (`resolve_run_dir`, `TrainLogger`, `episode_seed`), igual que los agentes de un solo cruce, así que las curvas de E3 a E6 se comparan directamente.

## Heterogeneidad (PLAN §5, "ojo en multiagente")
- **Padding estructurado.** La observación de sumo-rl es `[fase one-hot (n_verdes)] + [min_green] + [densidad (n_carriles)] + [cola (n_carriles)]`. Cada bloque se rellena con ceros por separado, hasta `max_verdes` y `max_carriles`. Así la columna k significa lo mismo para todos los agentes (con un padding al final, la densidad de un cruce caería en la columna de fase de otro). Si alguna observación no sigue ese formato, se usa padding al final.
- **Id del agente.** Se agrega un one-hot del agente a la entrada de las redes compartidas (QMIX, MAPPO, comm y `idqn` con `shared_params`).
- **Máscaras.** Las acciones `>= n_verdes` se enmascaran con `-1e9` en `masked_argmax`, en `masked_logits` y en el ε-greedy. Los tests comprueban que nunca se eligen.
- **Estado global** (QMIX/MAPPO). Es la concatenación de las observaciones rellenadas más la cola total de cada cruce (`state_queues`).
- **Recompensa.** `diff-waiting-time` (sumo-rl ya la divide entre 100) se multiplica por `reward_scale` (0.1 por defecto). Opcionalmente se normaliza con la desviación estándar móvil del retorno (`reward_norm`). Para QMIX y MAPPO la recompensa es de equipo (`r = Σ r_i`). IDQN y comm usan por defecto la local (`reward: local|team`).
- **Bucle robusto.** Un agente que falta en un paso conserva su última observación y recibe recompensa 0. sumo-rl solo *trunca* por tiempo y nunca *termina*, así que en el último paso se sigue haciendo bootstrap (`terminated=0`).
- **Topología.** Los vecinos salen de `env.scenarios.get_topology(net_file)`: la cadena del corredor, o el JSON de override si existe.

## Diseño de cada método
- **IDQN.** Hay una red, un optimizador, un replay y una red objetivo por agente (`shared_params: false`). El objetivo es Double-DQN con máscara y la pérdida es Huber. Con `neighbor_obs: true` se agregan a la entrada los vectores de cola por carril de cada vecino (comunicación v1). El docstring discute la no estacionariedad.
- **QMIX.** La red de agente es una MLP compartida (sin GRU: la observación ya trae la fase y la bandera de verde mínimo, y así el replay sigue siendo por transición). Los pesos de la mezcladora salen de hiperredes de s con `abs()` y ELU, lo que da `∂Q_tot/∂Q_i ≥ 0` y, por lo tanto, IGM. El replay guarda transiciones conjuntas, el objetivo es Double-Q con máscaras, la red objetivo se actualiza en duro (o suave con `tau<1`) y el gradiente se recorta. La misma función `train_joint` acepta `mixer: vdn|none`.
- **MAPPO.** El actor es compartido (Tanh, inicialización ortogonal 0.01) y el crítico es V(s). La GAE se calcula sobre la recompensa de equipo, con bootstrap V(s_T) en la truncación. La pérdida usa clip de PPO, entropía, clip de la pérdida de valor y normalización móvil del valor. El rollout es un episodio o `n_steps` pasos (el config de E5 usa 240, es decir, 3 actualizaciones por episodio).
- **Comm (DIAL).** El mensaje es `m_j = tanh(f([o_j, id_j]))`, con dimensión `msg_dim` (6 por defecto). La red Q de i recibe `[o_i, id_i, m_vecinos]`. El replay guarda observaciones, no mensajes: al entrenar, los mensajes se recalculan con el codificador actual, y el gradiente del TD de i atraviesa `m_j` y llega al emisor j. El ruido opcional `msg_noise` hace el papel del DRU de DIAL. El aprendiz es `train_joint` con `mixer: none` y recompensa local (comparable con `idqn_neighbor_obs`). Con `mixer: qmix` queda QMIX + comunicación.

Nota sobre E6: `comm` comparte parámetros (más el id) y `idqn_neighbor_obs` no. Para una ablación estricta se puede correr `idqn` con `shared_params: true, neighbor_obs: true`.

## Uso
```bash
source scripts/env.sh && export LIBSUMO_AS_TRACI=1
python -c "from experiments.common import load_config; from agents.marl import qmix; \
  print(qmix.train(load_config('experiments/configs/E5/qmix.yaml', seed=0)))"
# o, cuando esté en main: python -m experiments.train --config experiments/configs/E5/qmix.yaml --seed 0
```
`train_log.csv`: `episode, env_steps, return` (equipo, sin escalar), `mean_waiting_time` (promedio de `system_mean_waiting_time` en el episodio), `epsilon` o `entropy`, `loss`, `episode_time`, `wall_time`. El checkpoint `model.pt` incluye la `MultiAgentSpec`, de modo que `load_policy` no necesita SUMO.

Tests: `python -m pytest -q tests/test_marl.py tests/test_marl_toy.py`. Incluyen un entorno falso heterogéneo (2, 4 y 3 fases; 4, 8 y 6 carriles; un agente que a veces falta) y entrenamientos cortos en `toy_grid2x2`.
