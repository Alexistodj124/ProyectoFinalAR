# Demo web en vivo: semáforo fijo vs. agente RL (corredor Reforma)

Dos simulaciones SUMO corren **en lock-step** (mismo escenario, misma semilla, misma demanda). La única diferencia es quién controla los semáforos: el programa de tiempo fijo `fixed` del corredor (`env/net/reforma_fixed.add.xml`) o una política (por defecto max-pressure; un modelo entrenado si se elige uno). El navegador dibuja las dos redes lado a lado, con el estado de cada semáforo en su línea de alto, y muestra las métricas en vivo.

## Arquitectura

```
Navegador (web/frontend, React + Canvas)
   |  GET /api/network | /api/scenarios | /api/policies | /api/status
   |  WS  /ws      <-- estado (JSON)         --> comandos JSON
   v
FastAPI (web/backend/app.py)         <- bucle de eventos asyncio, nunca toca TraCI
   |  cola de comandos (Future)       ^ publish(estado ya serializado, thread-safe)
   v                                  |
SimManager (web/backend/sim_manager.py)  -- UN hilo "sim-manager" con todo el TraCI
   |-- Sim "fijo": make_parallel_env(fixed_ts=True, program="fixed")   (SUMO corre su programa, nunca se aplican acciones)
   |-- Sim "rl"  : make_parallel_env(...) + Policy (agents.registry.load_policy)
   '-- SharedDemand (demand_driver.py): misma demanda en ambas sims, inyectada por TraCI
          |-- UN env.demand.DemandGenerator(scenario, profile, seed) para las dos (escenarios reforma_* y cruce_*)
          '-- respaldo: agenda del .rou.xml del escenario (toy_*) + inyecciones del usuario
```

Puntos clave:

- **1 s de granularidad.** `Sim.step()` reproduce `SumoEnvironment.step` de sumo-rl pero segundo a segundo (`spawn -> _sumo_step -> ts.update`), y cada `delta_time` calcula las observaciones y llama a `policy.act(obs)` + `_apply_actions`. La política decide igual que en entrenamiento. En la sim "fijo" (`fixed_ts`) no se calculan observaciones ni se aplican acciones.
- **Una sola conexión TraCI por sim, en un solo hilo.** El bucle de FastAPI solo manda comandos por una cola y reparte el último estado serializado; si un cliente es lento se saltan cuadros.
- **Sin `LIBSUMO_AS_TRACI`.** Con dos simulaciones a la vez hace falta TraCI por socket (`web/backend/__init__.py` lo quita del entorno). Si lo ves activo, el backend se niega a arrancar.
- **Demanda idéntica.** SUMO arranca con un `.rou.xml` vacío y todos los vehículos entran por TraCI. En Reforma hay **un solo** `DemandGenerator`: las llegadas del segundo `s` salen de una RNG con semilla `(seed, s)` y el generador lleva un cursor por conexión, así que las dos sims reciben los mismos ids, rutas e instantes (la RNG interna de SUMO se desincroniza en cuanto los semáforos difieren, por eso no se usan flujos nativos). Hay pruebas que lo verifican.
- **Auto-reinicio.** Al llegar a `scenario.num_seconds` (3600 s) la simulación se reconstruye (mismo escenario, semilla, incidentes y hora del día) y `episode` aumenta.
- **Suavizado en el navegador.** El servidor manda un mensaje por cada paso de simulación que se avanza (≈1.3 msg/s a 1×, ≈5 a 5×, ≈10 a 20×). El lienzo interpola la posición de cada vehículo entre los dos últimos mensajes (con ~1 mensaje de retraso), así que a 1× el movimiento sigue siendo fluido.

## Cómo correrlo

Todo desde la raíz del repo. Necesitas Node (solo para compilar el frontend) y el venv del proyecto.

```bash
# 1) Compilar el frontend (una vez, o cada vez que cambie web/frontend/src)
cd web/frontend && npm install && npm run build && cd ../..      # genera web/frontend/dist

# 2) Arrancar el backend (NO exportar LIBSUMO_AS_TRACI; reforma_pico es el escenario inicial)
source scripts/env.sh
python -m uvicorn web.backend.app:app --port 8000

# 3) Abrir http://localhost:8000
```

- El backend sirve `web/frontend/dist/` en `/`, junto con `/api/*` y `/ws`, así que no hace falta nada más. Tarda ~4 s en arrancar (abre dos SUMO). La página dice "MODO DEMO SIN BACKEND" (datos falsos del navegador, no es SUMO) si no logra conectarse al WebSocket.
- Escenario inicial distinto: `WEB_SCENARIO=cruce_pico python -m uvicorn ...` (o cambiarlo en la página y pulsar *Reiniciar*).
- Modelos entrenados en otra carpeta (otro worktree, o un `runs/` descargado de Colab): `WEB_RUNS_DIR=/ruta/a/runs python -m uvicorn ...`. Por defecto es `runs/` del repo.
- Desarrollo del frontend con recarga en caliente: `cd web/frontend && npm run dev` (http://localhost:5173, hace proxy a `:8000`).
- Para parar: `Ctrl+C` en la terminal del backend.

Pruebas: `python -m pytest -q tests/test_web_backend.py` (~30 s; levanta un uvicorn real y dos SUMO a la vez; no usa `TestClient` porque pide `httpx`, que no está en el entorno).

### API

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/network?scenario=` | `{bbox, projected, lanes[{id,edge,name,shape,width,allow_passenger}], edges[], junctions[], tls[{id,x,y,name,links[[índice,carril,x,y]]}]}` en coordenadas SUMO (m, y hacia el norte). `name` sale de `env/net/tls_names.json` ("Reforma y 12 calle"). `links[i]` dice qué carácter del string de estado del semáforo corresponde a qué carril y a qué línea de alto (x, y). Si la red tiene proyección geográfica y `pyproj` está instalado, agrega `lon/lat` por TLS y `bbox_lonlat`. |
| GET | `/api/scenarios` | nombre, descripción, `net_available` (existe el net.xml) y `available` (además hay demanda) |
| GET | `/api/policies?scenario=` | baselines + toda corrida `runs/**/seed<k>/` con `config.yaml` y modelo guardado (`model.pt`, `model.zip`, `qtable.npz`...). Cada una trae `compatible` (¿sirve en `scenario`? por defecto el actual): MARL solo en `reforma_*`, 1 agente solo en `cruce_*`. |
| GET | `/api/status`, `/api/state` | estado del hilo de simulación / último mensaje |
| WS | `/ws` | ver abajo |

### WebSocket

Servidor -> cliente (solo hay mensaje cuando la sim avanzó; en pausa, un latido por segundo):

```json
{"type": "state", "t": 312, "episode": 1, "speed": 5.0, "scenario": "reforma_pico",
 "profile": "pico", "demand_veh_h": 7352, "incidents": ["NB_C12_C10"],
 "policy": {"algo": "max_pressure", "label": "Max-pressure", "warning": null},
 "improvement_pct": 18.4,
 "sims": {"fijo": {"vehicles": [[id, x, y, angle, speed], ...],
                    "tls": {"C12": "GGGGGGGgrrrrr"},
                    "metrics": {"mean_wait": 21.3, "queue": 40, "throughput": 1320.0, "arrived": 210, "n_vehicles": 75}},
          "rl":   { ... }}}
```

- `angle` es el rumbo de SUMO en grados (0 = norte, sentido horario). `tls[id][i]` es el estado del enlace `i` de ese semáforo (ver `links` en `/api/network`).
- `mean_wait` = espera acumulada promedio de los vehículos que ya terminaron más los que están en la red; `queue` = vehículos detenidos (v < 0.1 m/s); `throughput` = llegadas/hora en una ventana móvil de 300 s simulados; `improvement_pct` = (espera fijo − espera rl) / espera fijo × 100.
- `policy.warning` avisa si se usó un respaldo (política cíclica) o si la política lanzó una excepción (se mantiene la fase actual).
- Máximo 1500 vehículos por sim por mensaje.
- Otros `type` (`ack`, `loading`, `error`) no llevan `sims`; el frontend los muestra como avisos pequeños (toasts).

Cliente -> servidor (cada comando recibe `{"type":"ack","cmd":...,"ok":true|false,"result"|"error":...}` solo en el socket que lo mandó). Todos se aplican a las **dos** sims en el mismo segundo simulado:

| Comando | Efecto |
|---|---|
| `{"cmd":"inject","edge":id,"n":k}` | `k` vehículos (4 por segundo) en ese borde (acepta id de carril: `C12_W_in` o `C12_W_in_1`), por la ruta más probable de `DemandGenerator.inject`; mismos ids/ruta/instante en ambas. Bordes fuera de las rutas del generador usan la ruta más larga hasta una salida. |
| `{"cmd":"time_of_day","profile":"pico\|mediodia\|noche\|pico_x13"}` | `DemandGenerator.set_profile`; responde la demanda en veh/h (corredor: pico ≈ 7350, mediodía ≈ 4800, noche ≈ 2200; cruce de la 12 calle en pico ≈ 4900). En escenarios toy escala la agenda del `.rou.xml`. |
| `{"cmd":"incident","edge":id,"on":true\|false}` | Convención de `env/incidents.py` (la de E7): `lane.setDisallowed(["passenger"])` en todos los carriles de paso del borde **menos uno**, sin cortar ningún movimiento (un borde de salida sin conexiones se rechaza) (un borde de 1 carril se cierra entero) y reruteo de los vehículos afectados; `false` restaura los permisos originales. En `NB_C12_C10` el único carril abierto es la bahía de giro a la izquierda, así que el tráfico recto hacia el norte se detiene. Los vehículos cuya ruta ya no es transitable se descartan (igual en las dos sims). |
| `{"cmd":"speed","value":0\|1\|5\|20}` | segundos simulados por segundo real (acepta cualquier valor 0–60) |
| `{"cmd":"reset","scenario":..., "policy":{"algo":..., "run":...}, "seed":1000}` | reconstruye todo (cuesta ~1–3 s, mientras se emite `{"type":"loading"}`); borra incidentes y hora del día. Si falla (p. ej. un modelo de otra red), la simulación anterior sigue corriendo. |

## Cargar un modelo entrenado

1. Entrena (Colab o local) con `experiments/train.py`; el resultado queda en `runs/<exp>/<nombre>/seed<k>/` con `config.yaml` y el checkpoint. Si se entrenó en Colab, copia esa carpeta a `runs/` del repo local (o usa `WEB_RUNS_DIR`).
2. En la página: elige el **escenario** en el panel derecho (p. ej. *Corredor Reforma, hora pico*); la lista de **Política RL** se actualiza sola y solo muestra lo que sirve en esa red:
   - corredor `reforma_*`: *Max-pressure*, *Actuado* y las corridas MARL (`idqn`, `qmix`, `mappo`, `comm`);
   - cruce `cruce_*`: las corridas de 1 agente (`qlearning`, `dyna_q`, `dqn`, `ppo`).
   Elige la corrida y pulsa **Reiniciar**. La etiqueta del panel derecho queda como "Agente RL · idqn (…)".
3. A mano, por WebSocket o con `curl http://localhost:8000/api/policies?scenario=reforma_pico`:
   ```json
   {"cmd":"reset","scenario":"reforma_pico","policy":{"algo":"idqn","run":"E5/idqn_nb/seed0"}}
   ```
   `run` es relativo a `runs/` (o a la raíz del repo); **solo se aceptan carpetas dentro de `runs/`** (los checkpoints de PyTorch son pickles). El backend llama `agents.registry.load_policy(algo, run)` y la política se usa solo en inferencia, en la sim "rl". Una corrida entrenada en otra red se rechaza con un aviso.
4. Sin modelo se usa max-pressure (`baselines.max_pressure`), y como último recurso una política cíclica; `policy.warning` lo avisa.

## Guion de demo (≈2 min)

Antes: backend arrancado, página abierta en `http://localhost:8000`, pantalla completa (F11), escenario **Corredor Reforma, hora pico**, política elegida y **Reiniciar** pulsado (ahí empieza el reloj simulado).

| Tiempo | Qué hacer | Qué decir |
|---|---|---|
| 0:00 | Velocidad **5×**. Señalar los dos mapas. | "Misma avenida, mismos carros, misma semilla. A la izquierda los semáforos con el tiempo fijo medido; a la derecha, el agente." |
| 0:15 | Señalar las tarjetas de arriba y las gráficas. | "Espera promedio, cola y vehículos por hora, en vivo. La tarjeta verde es la mejora del agente sobre el tiempo fijo." |
| 0:35 | Modo **Inyectar**, clic en `Reforma y 12 calle` (calle transversal, 20 carros). | "Si de pronto llegan 20 carros a la 12 calle, vemos cuánto tarda cada controlador en reaccionar." |
| 1:00 | **Hora del día**: *Mediodía* y luego *Noche*. | "Cambia la demanda a una hora que el agente no vio al entrenar." |
| 1:20 | Modo **Incidente**, clic en la Reforma entre la 12 y la 10a calle (hacia el norte). | "Cerramos carriles: se forma cola aguas arriba. Se ve cómo se acomoda cada controlador." Quitar el incidente con otro clic. |
| 1:45 | **20×** unos segundos y volver a **1×** o **Pausa** sobre un cruce. | "A 20× se ve el efecto acumulado en las gráficas." |
| 2:00 | Cerrar con la tarjeta de mejora. | Resumir el número. |

Notas para el ensayo:
- La tarjeta de mejora arranca alta y se estabiliza con el tiempo. Medido en `reforma_pico` con la semilla 1000 (octubre 2026, `docs/video/README.md`): MAPPO (`E5/mappo/seed3`) ≈51 % a los 5 min simulados, ≈48 % a los 10 y ≈47 % a los 15; comm (`E6/comm/seed0`) ≈50/51/48 %; QMIX (`E5/qmix/seed3`) ≈49/48/47 %; max-pressure ≈47/47/43 %. En `cruce_pico`: DQN (`E4/dqn_best/seed1`) ≈38/46/52 %, PPO (`E4/ppo/seed0`) ≈51/55/57 %. Es la espera en vivo de la demo, no la demora total de la evaluación (§7). Ensaya con el modelo definitivo y deja el escenario corriendo ~1 min antes de empezar a hablar.
- Un clic en el mapa de la izquierda o el de la derecha vale igual: el comando se aplica a las dos sims.
- Si algo falla en vivo: *Reiniciar* (1–3 s), o reproducir el video de respaldo.

## Video de respaldo (PLAN §9.3)

Antes de la presentación, grabar la demo completa funcionando con el modelo definitivo y guardar el archivo fuera del navegador (USB + nube).

1. Backend arrancado y página en pantalla completa con la política elegida; **Reiniciar** para empezar en t = 0.
2. macOS: `Cmd+Shift+5` -> *Grabar pantalla completa* -> Opciones -> micrófono (para narrar). (Alternativa: OBS Studio, 1920×1080 a 30 fps.)
3. Seguir el guion de arriba (≈2 min) a ritmo tranquilo; si un paso sale mal, repetirlo desde *Reiniciar* y recortar después.
4. Detener con el botón de la barra de menú, y exportar a `.mp4` (QuickTime: *Archivo -> Exportar como -> 1080p*).
5. Probar el archivo en la máquina y el proyector de la presentación, y tener a mano el comando para volver a arrancar el backend (`source scripts/env.sh && python -m uvicorn web.backend.app:app --port 8000`).

Verificar el día anterior que el backend arranca en la máquina de la presentación (`python -m pytest -q tests/test_web_backend.py`).
