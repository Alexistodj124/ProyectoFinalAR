# Demo web en vivo: semáforo fijo vs. agente RL

Dos simulaciones SUMO corren **en lock-step** (mismo escenario, misma semilla, misma demanda). La única diferencia es quién controla los semáforos: el programa de tiempo fijo o una política (por defecto max-pressure; un modelo entrenado si se carga). El navegador dibuja las dos redes lado a lado y muestra las métricas en vivo.

## Arquitectura

```
Navegador (web/frontend, React + Canvas)
   |  GET /api/network | /api/scenarios | /api/policies | /api/status
   |  WS  /ws      <-- estado ~10 Hz (JSON)         --> comandos JSON
   v
FastAPI (web/backend/app.py)         <- bucle de eventos asyncio, nunca toca TraCI
   |  cola de comandos (Future)       ^ publish(estado ya serializado, thread-safe)
   v                                  |
SimManager (web/backend/sim_manager.py)  -- UN hilo "sim-manager" con todo el TraCI
   |-- Sim "fijo": make_parallel_env(fixed_ts=True, program="fixed")
   |-- Sim "rl"  : make_parallel_env(...) + Policy (agents.registry.load_policy)
   '-- SharedDemand (demand_driver.py): misma demanda en ambas sims, inyectada por TraCI
          |-- env.demand.DemandGenerator.spawn(conn, t)   (escenarios Reforma, si está)
          '-- respaldo: agenda del .rou.xml del escenario (toy_*) + inyecciones del usuario
```

Puntos clave:

- **1 s de granularidad.** `Sim.step()` reproduce `SumoEnvironment.step` de sumo-rl pero segundo a segundo (`spawn -> _sumo_step -> ts.update`), y cada `delta_time` calcula las observaciones y llama a `policy.act(obs)` + `_apply_actions`. La animación es fluida y la política decide igual que en entrenamiento.
- **Una sola conexión TraCI por sim, en un solo hilo.** El bucle de FastAPI solo manda comandos por una cola y reparte el último estado serializado; si un cliente es lento se saltan cuadros.
- **Sin `LIBSUMO_AS_TRACI`.** Con dos simulaciones a la vez hace falta TraCI por socket (`web/backend/__init__.py` lo quita del entorno). Si lo ves activo, el backend se niega a arrancar.
- **Demanda idéntica.** SUMO arranca con un `.rou.xml` vacío; todos los vehículos entran por TraCI con el mismo `t` en las dos sims (la RNG interna de SUMO se desincroniza en cuanto los semáforos difieren, por eso no se usan flujos probabilísticos nativos). Hay una prueba que lo verifica: con el mismo control, las métricas de las dos sims son idénticas.
- **Auto-reinicio.** Al llegar a `scenario.num_seconds` la simulación se reconstruye (mismo escenario, semilla, incidentes y hora del día) y `episode` aumenta.

## Cómo correrlo

```bash
# 1) Backend (desde la raíz del repo; NO exportar LIBSUMO_AS_TRACI)
source scripts/env.sh
python -m uvicorn web.backend.app:app --port 8000
#   escenario inicial: WEB_SCENARIO=toy_grid2x2 (por defecto reforma_pico si existe, si no toy_grid2x2)

# 2) Frontend en desarrollo (otra terminal)
cd web/frontend && npm install && npm run dev      # http://localhost:5173 (CORS ya permitido)

# 3) Producción / ensayo: compilar el frontend y abrir solo el backend
cd web/frontend && npm run build                   # genera web/frontend/dist
#   el backend sirve dist/ en http://localhost:8000/
```

Pruebas: `python -m pytest -q tests/test_web_backend.py` (~30 s, levanta un uvicorn real en un puerto libre; no usa `TestClient` porque pide `httpx`, que no está en el entorno).

### API

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/network?scenario=` | `{bbox, projected, lanes[{id,edge,name,shape,width,allow_passenger}], edges[], junctions[], tls[{id,x,y,name,links[[índice,carril,x,y]]}]}` en coordenadas SUMO (m, y hacia el norte). Con proyección geográfica agrega `lon/lat` por TLS y `bbox_lonlat`. `links[i]` dice qué carácter del string de estado del semáforo corresponde a qué carril/línea de alto. |
| GET | `/api/scenarios` | nombre, descripción, `net_available` (existe el net.xml) y `available` (además hay demanda) |
| GET | `/api/policies` | baselines + toda corrida `runs/<exp>/<nombre>/seed<k>/` con modelo guardado (`model.pt`, `model.zip`, `qtable.npz`...) |
| GET | `/api/status`, `/api/state` | estado del hilo de simulación / último mensaje |
| WS | `/ws` | ver abajo |

### WebSocket

Servidor -> cliente (≈10 Hz; solo hay mensaje cuando la sim avanzó, es decir ≈1/s a 1×, 5/s a 5×, 10/s a 20×; en pausa, un latido por segundo):

```json
{"type": "state", "t": 312, "episode": 1, "speed": 5.0, "scenario": "reforma_pico",
 "profile": "pico", "incidents": ["edge42"], "policy": {"algo": "max_pressure", "label": "...", "warning": null},
 "improvement_pct": 18.4,
 "sims": {"fijo": {"vehicles": [[id, x, y, angle, speed], ...],
                    "tls": {"<tls_id>": "GGrrGGrr"},
                    "metrics": {"mean_wait": 21.3, "queue": 40, "throughput": 1320.0, "arrived": 210, "n_vehicles": 75}},
          "rl":   { ... }}}
```

- `angle` es el rumbo de SUMO en grados (0 = norte, sentido horario); con `speed` (m/s) el frontend puede interpolar entre dos mensajes consecutivos (recomendado: dibujar con ~1 mensaje de retraso e interpolar con `t`).
- `mean_wait` = espera acumulada promedio de los vehículos que ya terminaron más los que están en la red; `queue` = vehículos detenidos (v < 0.1 m/s); `throughput` = llegadas/hora en una ventana móvil de 300 s simulados; `improvement_pct` = (espera fijo − espera rl) / espera fijo × 100.
- Máximo 1500 vehículos por sim por mensaje.
- Mensajes con otro `type` (`ack`, `loading`, `error`) no llevan `sims`: el cliente debe ignorarlos si no los usa.

Cliente -> servidor (cada comando recibe `{"type":"ack","cmd":...,"ok":true|false,"result"|"error":...}` solo en el socket que lo mandó). Todos se aplican a las **dos** sims en el mismo segundo simulado:

| Comando | Efecto |
|---|---|
| `{"cmd":"inject","edge":id,"n":k}` | `k` vehículos (2 por segundo) por la ruta más larga desde ese borde hasta una salida de la red (acepta id de carril); mismos ids/ruta/instante en ambas |
| `{"cmd":"time_of_day","profile":"pico\|mediodia\|noche\|pico_x13"}` | `DemandGenerator.set_profile`; sin él, escala la agenda del `.rou.xml` (pico 1.0, mediodía 0.7, noche 0.3, pico_x13 1.3) |
| `{"cmd":"incident","edge":id,"on":true\|false}` | `lane.setDisallowed(["passenger"])` en todos los carriles del borde y reruteo de los vehículos afectados; `false` restaura los permisos originales. Mientras está cerrado se descartan las llegadas cuya ruta lo cruza |
| `{"cmd":"speed","value":0\|1\|5\|20}` | segundos simulados por segundo real (acepta cualquier valor 0–60) |
| `{"cmd":"reset","scenario":..., "policy":{"algo":..., "run":...}, "seed":1000}` | reconstruye todo (cuesta ~1–3 s, mientras se emite `{"type":"loading"}`); borra incidentes y hora del día. Si falla, la simulación anterior sigue corriendo |

## Cargar un modelo entrenado

1. Entrena (Colab o local) con `experiments/train.py`; el resultado queda en `runs/<exp>/<nombre>/seed<k>/` con `config.yaml` y el checkpoint. Si se entrenó en Colab, copia esa carpeta a `runs/` del repo local.
2. `GET /api/policies` la lista sola (`kind: "trained"`, `id` = ruta relativa a `runs/`).
3. Desde el frontend (selector de política) o a mano:
   ```json
   {"cmd":"reset","scenario":"reforma_pico","policy":{"algo":"idqn","run":"E4/idqn_nb/seed0"}}
   ```
   `run` puede ser relativo a `runs/` o a la raíz del repo; **solo se aceptan carpetas dentro de `runs/`** (los checkpoints de PyTorch son pickles). El backend llama `agents.registry.load_policy(algo, run)`; la política se usa solo en inferencia y se aplica a la sim "rl". Debe haberse entrenado sobre el mismo escenario (mismas dimensiones de observación).
4. Sin modelo (o si `baselines.max_pressure` aún no existe) se usa max-pressure, y como último recurso una política cíclica; `policy.warning` en el estado lo avisa.

## Guion de la presentación (≈5 min)

1. Abrir `http://localhost:8000` (o `:5173`), escenario **Reforma, hora pico**, velocidad **5×**. Señalar: izquierda semáforos de tiempo fijo, derecha el agente; mismos carros, misma semilla.
2. Dejar correr ~1 min simulado y señalar las métricas: espera promedio, cola y `improvement_pct`.
3. **Inyectar carros**: clic en una calle del corredor (n = 30). Ver cómo la cola crece en "fijo" y el agente reasigna verde.
4. **Hora del día**: pasar a *mediodía* y luego a *noche*; mostrar que el agente no se rompe en demanda que no vio al entrenar.
5. **Incidente**: cerrar un carril del corredor; observar la cola aguas arriba y cómo responde cada controlador. Quitar el incidente.
6. Subir a **20×** para mostrar el efecto acumulado y volver a **1×** o **pausa** para señalar un cruce concreto.
7. Cerrar con `reset` a otro escenario o política (p. ej. max-pressure vs. QMIX) si hay tiempo.

## Video de respaldo

Antes de la presentación grabar un video de la demo completa (pantalla completa, el guion de arriba, con el audio de narración) y guardarlo fuera del navegador (USB + nube). Si falla SUMO, el puerto o el proyector, se reproduce el video. Verificar el día anterior que el backend arranca en la máquina de la presentación (`python -m pytest -q tests/test_web_backend.py`).
