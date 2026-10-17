# Proyecto Final — Semáforos inteligentes en Av. La Reforma con RL multiagente

**Curso:** CC3104 Aprendizaje por Refuerzo · UVG · Ciclo 2, 2026
**Equipo:** 3+ integrantes · **Plazo:** ~5 semanas (presentación en semana 20)

---

## 1. Resumen

Simular en **SUMO** un tramo real de **Av. La Reforma (Zona 9/10)** con 4–5 semáforos consecutivos, calibrado con **conteos propios en video**, y entrenar agentes RL que controlen los semáforos. Se compara, con el mismo protocolo, desde Q-Learning tabular en un cruce hasta **QMIX / MAPPO** en el corredor completo, contra tres líneas base sin RL. Todo se muestra en una **interfaz web en vivo** donde el público puede inyectar carros, cambiar la hora del día y provocar incidentes, viendo lado a lado el semáforo fijo frente al agente RL.

**Pregunta de investigación:** ¿cuánto reduce el RL multiagente el tiempo de espera en un corredor real de Guatemala frente al control actual, y se mantiene esa mejora ante condiciones que no vio en el entrenamiento?

---

## 2. Decisiones tomadas

| Aspecto | Decisión |
|---|---|
| Simulador | SUMO + `sumo-rl` (Gymnasium para 1 agente, PettingZoo para multiagente) |
| Escenario | Corredor real de Av. La Reforma importado de OpenStreetMap |
| Demanda | Conteos propios en video (hora pico y mediodía) |
| Interfaz | FastAPI + WebSocket + React, que controla SUMO vía TraCI |
| Interacción en vivo | Inyectar carros · cambiar hora del día · provocar incidente · comparación lado a lado |
| Estado | Colas + densidad por carril + fase actual (one-hot) + bandera de verde mínimo |
| Acción | Elegir la siguiente fase verde cada 5 s (amarillo 3 s automático, verde mínimo 10 s) |
| Recompensa | Reducción del tiempo de espera acumulado (`diff-waiting-time`) |
| Algoritmos con 1 agente | Q-Learning tabular, Dyna-Q, DQN (Double + Dueling + PER), PPO |
| Algoritmos multiagente | IDQN, QMIX, MAPPO, comunicación entre semáforos |
| Líneas base | Tiempo fijo, actuado (SUMO), max-pressure |
| Robustez | Hora no vista, carril cerrado, demanda +30 %, equidad entre calles |
| Cómputo | Mac (desarrollo y demo) + Google Colab (entrenamientos y semillas) |
| Entregables | Informe tipo paper, repo reproducible, demo en vivo + video, slides |

---

## 3. Prioridades de alcance

Se eligió **todo**, y en 5 semanas es mucho. Para no quedarse sin nada que mostrar, el trabajo se ordena en tres niveles. Se termina un nivel antes de pasar al siguiente.

| Nivel | Contenido |
|---|---|
| **Imprescindible** (sin esto no hay proyecto) | Corredor en SUMO calibrado · 3 líneas base · Q-Learning tabular + DQN en 1 cruce · IDQN + QMIX en el corredor · demo web con inyección de carros y comparación lado a lado · pruebas de robustez · informe |
| **Importante** | Dyna-Q · PPO · MAPPO · hora del día e incidentes en la interfaz · ablación de las variantes de DQN |
| **Si da tiempo** | Comunicación entre semáforos · emisiones de CO₂ como métrica extra |

---

## 4. Cómo aparece cada tema del curso

| Tema del curso | Dónde aparece en el proyecto |
|---|---|
| Intro RL | Vocabulario aplicado: agente = semáforo, entorno = SUMO, recompensa = espera evitada |
| Multi-armed bandits | Exploración ε-greedy y su decaimiento; discusión exploración vs. explotación en tráfico real |
| MDP | Formulación formal (sección 5); discusión de la observabilidad parcial (un semáforo no ve todo el corredor) |
| Programación dinámica | Justifica por qué no aplica directamente: no se conoce P(s'\|s,a) de SUMO. Se puede incluir value iteration sobre el modelo aprendido por Dyna-Q como contraste |
| Monte Carlo | Evaluación de políticas: retorno promedio sobre episodios completos con semillas de evaluación |
| TD (Q-Learning) | Agente tabular en 1 cruce con estado discretizado |
| Value Function Approximation | Paso de la tabla a la red: por qué el estado continuo exige aproximación |
| Policy Gradient (PPO) | Agente PPO en 1 cruce; contraste value-based vs. policy-based |
| Planning & Learning (Dyna-Q) | Modelo aprendido del cruce + planificación; eficiencia de muestras frente a Q-Learning |
| Deep RL I (DQN y variantes) | DQN con Double, Dueling y PER, más ablación de cada variante |
| Deep RL II (Actor-Critic) | PPO/MAPPO son actor-crítico; discusión de por qué SAC/TD3 no aplican (acción discreta) |
| MARL I (fundamentos) | Corredor como juego cooperativo; no estacionariedad con IDQN; dilemas de coordinación (ola verde) |
| MARL II (CTDE, QMIX, comunicación) | QMIX y MAPPO con entrenamiento centralizado; canal de mensajes entre vecinos |
| CleanRL y tendencias | Implementaciones base estilo CleanRL; comparación con el estado del arte en control de semáforos |
| Saberes actitudinales | Equidad entre calles, peatones no modelados, ambulancias, brecha entre simulación y realidad |

---

## 5. Formulación del MDP

**Agente:** cada intersección semaforizada del corredor (4–5 agentes).

**Estado / observación** (por agente, default de `sumo-rl`):
- Fase verde actual (one-hot)
- Bandera: ¿ya cumplió el verde mínimo?
- Por cada carril de entrada: densidad (autos / capacidad) y cola (autos detenidos / capacidad)

**Acción:** índice de la siguiente fase verde. Se decide cada `delta_time = 5 s`. Si cambia de fase, SUMO inserta un amarillo de 3 s. No puede cambiar antes de `min_green = 10 s`.

**Recompensa:** `r_t = W_{t-1} − W_t`, donde `W` es el tiempo de espera acumulado de los autos detenidos en los carriles de entrada. Es positiva si la acción redujo la espera.

**Episodio:** 1 hora simulada (3600 s → 720 decisiones por agente).

**Factor de descuento:** γ = 0.99.

**Versión tabular (Q-Learning y Dyna-Q):** la cola de cada aproximación se discretiza en {baja, media, alta}. Con 4 aproximaciones y 4 fases quedan 3⁴ × 4 = 324 estados, que es manejable.

**Ojo en multiagente:** las intersecciones reales de Reforma no son idénticas (número de carriles y de fases distinto). Para QMIX y MAPPO con parámetros compartidos hay que rellenar las observaciones y enmascarar las acciones inválidas, o usar una red por agente.

---

## 6. Escenario y demanda

### 6.1 Mapa
1. Elegir el tramo en la semana 1: 4–5 intersecciones semaforizadas consecutivas de Av. La Reforma. Recorrerlo y anotar el número de carriles, los giros permitidos y las fases reales de cada semáforo.
2. Exportar el área desde OpenStreetMap y convertirla con `netconvert` (`--tls.guess-signals`, `--junctions.join`, `--geometry.remove`, `--ramps.guess`).
3. Corregir a mano en **netedit**: carriles, giros prohibidos y programas de fases para que coincidan con lo observado.
4. Medir el ciclo real de algunos semáforos (cronómetro en campo) y usarlo como la línea base **tiempo fijo**. Así la comparación es contra "lo que hay hoy".

### 6.2 Conteos en video
- Grabar 15 min en cada intersección (o en las 2–3 principales) en **hora pico** (≈ 7:00 o 17:30) y **mediodía**.
- Contar los carros por aproximación y por movimiento (recto, izquierda, derecha). Dividirlo entre el equipo; se puede apoyar con un contador simple o con un detector (YOLO) si alguien quiere.
- Convertir los conteos en rutas de SUMO con `routeSampler.py` (genera rutas que reproducen los conteos por calle) o con `jtrrouter` (proporciones de giro).
- Validar: comparar el tiempo de viaje simulado del tramo con el que reporta Google Maps a esa hora.

### 6.3 Perfiles de demanda
| Perfil | Uso |
|---|---|
| Hora pico (conteos) | **Entrenamiento** |
| Mediodía (conteos) | Evaluación: hora no vista |
| Hora pico +30 % | Evaluación: estrés |
| Noche (pico × 0.3, sintético) | Evaluación extra y opción en la interfaz |

---

## 7. Algoritmos

### 7.1 Líneas base (sin RL)
- **Tiempo fijo:** el ciclo medido en campo.
- **Actuado:** semáforo `actuated` de SUMO (extiende el verde si detecta autos).
- **Max-pressure:** elige la fase que maximiza (autos que entran − autos que salen). Se implementa en ~30 líneas con TraCI.

### 7.2 Fase 1 — un cruce (el más cargado del corredor)
| Algoritmo | Implementación | Nota |
|---|---|---|
| Q-Learning tabular | Propia | Estado discretizado, ε-greedy con decaimiento |
| Dyna-Q | Propia (sobre lo anterior) | n = 5, 10, 50 pasos de planificación: comparar la eficiencia de muestras |
| DQN | Estilo CleanRL o Stable-Baselines3 | Ablación: vanilla → +Double → +Dueling → +PER |
| PPO | Stable-Baselines3 o CleanRL | Contraste con DQN |

Hiperparámetros iniciales de DQN: lr 1e-3, buffer 50k, batch 64, actualización del target cada 500 pasos, ε de 1.0 a 0.05 en el 50 % del entrenamiento, red 2×64.

### 7.3 Fase 2 — corredor completo
| Algoritmo | Implementación | Nota |
|---|---|---|
| IDQN | Un DQN por semáforo (reutiliza la fase 1) | Línea base multiagente |
| QMIX | BenchMARL / EPyMARL, o propia (~300 líneas) | Red mezcladora condicionada al estado global (colas de todo el corredor) |
| MAPPO | BenchMARL / EPyMARL | Crítico centralizado |
| Comunicación | Propia sobre IDQN o MAPPO | Primero: agregar a la observación las colas de los vecinos. Luego: un mensaje aprendido (vector de 4–8 valores) que cada agente envía a sus vecinos |

> Verificar en la semana 1 qué librería multiagente se integra mejor con el entorno PettingZoo de `sumo-rl`. Si ninguna encaja rápido, implementar QMIX propio en estilo CleanRL.

**Truco de velocidad:** para entrenar, usar `LIBSUMO_AS_TRACI=1` (mucho más rápido que TraCI). La demo usa TraCI normal porque necesita varias simulaciones a la vez.

---

## 8. Protocolo experimental

- **Semillas:** 5 semillas de entrenamiento por algoritmo; evaluación en 10 episodios con semillas de demanda **distintas** a las de entrenamiento.
- **Presupuesto igual:** todos los algoritmos RL con el mismo número de pasos de entorno (por ejemplo, 100 episodios = 72k decisiones por agente; ajustar en la semana 2 según la velocidad).
- **Reporte:** media ± intervalo de confianza del 95 %; curvas de aprendizaje con banda de desviación estándar.
- **Registro:** TensorBoard o Weights & Biases; cada corrida guarda su config (YAML) y su semilla.

### 8.1 Métricas
| Métrica | Fuente |
|---|---|
| Tiempo de espera promedio por vehículo | `tripinfo` de SUMO |
| Tiempo de viaje promedio del tramo | `tripinfo` |
| Longitud de cola promedio y máxima | TraCI |
| Throughput (vehículos que salen / hora) | TraCI |
| Número de paradas por vehículo | `tripinfo` |
| **Equidad:** espera p95 por aproximación y espera máxima en las calles transversales | `tripinfo` por calle de origen |
| CO₂ (si da tiempo) | Salida de emisiones de SUMO |

### 8.2 Matriz de experimentos
| Experimento | Compara | Pregunta |
|---|---|---|
| E1 | Líneas base entre sí | ¿Qué tan bueno es lo actual? |
| E2 | Q-Learning vs. Dyna-Q | ¿Cuánto ayuda planificar? |
| E3 | Ablación de DQN | ¿Qué variante aporta más? |
| E4 | DQN vs. PPO (1 cruce) | ¿Value-based o policy-based? |
| E5 | IDQN vs. QMIX vs. MAPPO | ¿Ayuda entrenar centralizado? |
| E6 | Con y sin comunicación | ¿Mejora la ola verde? |
| E7 | Mejor agente en hora no vista, +30 % e incidente | ¿Generaliza? |
| E8 | Equidad de todos los métodos | ¿Se sacrifica a las calles transversales? |

Si la equidad sale mal en E8, se agrega una variante con penalización en la recompensa por la espera máxima, y se reporta el trade-off.

---

## 9. Interfaz web en vivo

### 9.1 Arquitectura
```
React (mapa de Reforma en Canvas/Leaflet + panel de controles + gráficas en vivo)
        │  WebSocket (estado ~10 fps)   ▲  comandos (JSON)
        ▼                               │
FastAPI ── SimManager ──┬── SUMO "A" (TraCI, label="fijo")  ← semáforo tiempo fijo
                        └── SUMO "B" (TraCI, label="rl")    ← agente entrenado (PyTorch, inferencia)
                 └── DemandGenerator (misma demanda y semilla para A y B)
```

- Las dos simulaciones avanzan **sincronizadas** paso a paso y con la **misma demanda**. La única diferencia es quién controla los semáforos.
- Cada tick, el backend envía: posiciones de los vehículos, fase de cada semáforo y métricas acumuladas (espera promedio, cola, throughput).
- El frontend dibuja la red a partir de la geometría del `.net.xml` (exportada una vez a GeoJSON).

### 9.2 Comandos (se aplican a A y B a la vez)
| Control | Implementación con TraCI |
|---|---|
| Inyectar carros | Clic en una calle → `traci.route.add` + `traci.vehicle.add` × N |
| Hora del día | `DemandGenerator` cambia las tasas de llegada (pico / mediodía / noche) |
| Incidente | `traci.lane.setDisallowed(lane, ["passenger"])` o un vehículo detenido en el carril; botón para quitarlo |
| Velocidad | Pausa / 1× / 5× / 20× |

### 9.3 Respaldo
Grabar un video de la demo funcionando, por si falla algo el día de la presentación.

---

## 10. Estructura del repositorio
```
proyecto-semaforos/
├── README.md               # cómo reproducir cada tabla y gráfica
├── env/
│   ├── net/                # reforma.net.xml, archivos de netedit
│   ├── routes/             # pico.rou.xml, mediodia.rou.xml, ...
│   ├── conteos/            # CSV de conteos en video
│   └── reforma_env.py      # wrapper sobre sumo-rl
├── baselines/              # fijo, actuado, max_pressure
├── agents/
│   ├── tabular/            # q_learning.py, dyna_q.py
│   ├── dqn/                # dqn.py con flags double/dueling/per
│   ├── ppo/
│   └── marl/               # idqn.py, qmix.py, mappo, comm/
├── experiments/
│   ├── configs/            # YAML por experimento
│   ├── train.py
│   └── evaluate.py         # genera las métricas de la sección 8
├── analysis/               # notebooks de gráficas y tablas
├── web/
│   ├── backend/            # FastAPI + SimManager + DemandGenerator
│   └── frontend/           # React
└── docs/                   # informe, slides, figuras
```

---

## 11. Roles (equipo de 3–4)

| Rol | Responsable de |
|---|---|
| **A — Entorno y datos** | Mapa OSM y netedit, conteos en video, rutas, validación, líneas base, script de métricas |
| **B — RL de 1 agente** | Q-Learning, Dyna-Q, DQN + ablación, PPO, pipeline de entrenamiento en Colab |
| **C — RL multiagente** | IDQN, QMIX, MAPPO, comunicación, pruebas de robustez |
| **D — Demo web** | FastAPI, SimManager, React, video de respaldo |

Con 3 integrantes: A toma el backend de la demo después de la semana 2 (ya conoce TraCI) y B toma el frontend en la semana 4. Todos escriben su sección del informe.

---

## 12. Cronograma

| Semana | Fechas | Entregable al final de la semana |
|---|---|---|
| **1** | 19–25 oct | Tramo elegido y recorrido · conteos grabados · red en SUMO corriendo · `sumo-rl` funcionando en Mac y Colab · líneas base fijo y actuado · librería multiagente elegida |
| **2** | 26 oct–1 nov | Rutas calibradas y validadas · max-pressure · Q-Learning + Dyna-Q + DQN en 1 cruce con curvas · esqueleto del backend (una simulación por WebSocket) |
| **3** | 2–8 nov | Ablación DQN + PPO · IDQN en el corredor · primera versión de QMIX · frontend dibujando el mapa en vivo |
| **4** | 9–15 nov | QMIX + MAPPO afinados (5 semillas) · comunicación (si da tiempo) · comparación lado a lado + inyección + hora + incidente en la demo · pruebas de robustez E7–E8 |
| **5** | 16–22 nov | Corridas finales y tablas · informe completo · slides · video de respaldo · ensayo de la presentación |

**Punto de control:** si al final de la semana 3 QMIX no aprende, se congela el alcance multiagente en IDQN + QMIX (reportando el análisis de la falla) y no se hacen MAPPO ni comunicación.

---

## 13. Informe tipo paper (estructura)
1. Introducción: el tráfico en Guatemala y la motivación
2. Trabajo relacionado: control de semáforos con RL, max-pressure, MARL
3. Formulación MDP / Dec-POMDP
4. Escenario: Reforma, conteos, calibración y validación
5. Métodos: líneas base y algoritmos
6. Protocolo experimental
7. Resultados E1–E8
8. Robustez y equidad
9. Ética y limitaciones: peatones, ambulancias, transporte público, sim-to-real, quién gana y quién pierde
10. Conclusiones y trabajo futuro
11. Declaración del uso de IA (requisito del curso)

---

## 14. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| El mapa de OSM queda sucio o mal conectado | Limpiarlo en netedit; si se atasca más de 3 días, dibujar el tramo en netedit a mano con la geometría real |
| Conteos insuficientes o inconsistentes | Completar con validación contra Google Maps; documentarlo como limitación |
| SUMO lento en Colab | `libsumo`, episodios más cortos para depurar, semillas en paralelo en varias sesiones |
| QMIX/MAPPO no convergen | Empezar con 2 intersecciones; observaciones normalizadas; si no funciona, reportar el diagnóstico (también cuenta como resultado) |
| La demo falla en la presentación | Video de respaldo; modelo y simulaciones precargados; probarla en la computadora de la presentación |
| Intersecciones heterogéneas en QMIX | Relleno de observaciones y máscara de acciones, o redes por agente sin compartir parámetros |

---

## 15. Pendientes por decidir
- [ ] Tramo exacto de Reforma (qué 4–5 intersecciones)
- [ ] Asignación de roles A–D
- [ ] Horarios de grabación de conteos
- [ ] Librería multiagente (BenchMARL, EPyMARL o propia) tras la prueba de la semana 1
