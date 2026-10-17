# Ajuste del aprendizaje sobre la demanda calibrada

Antes de lanzar la matriz completa (E2 a E6 con 5 semillas) hay que comprobar que cada algoritmo **aprende de verdad** en los escenarios calibrados de Reforma (commit `3960102`) y fijar el presupuesto de entrenamiento. Este documento resume las corridas de sanidad, lo que se encontró, lo que se cambió (con números de antes y después) y el presupuesto final.

## 1. Protocolo de sanidad

- **Entrenamiento:** semilla 0, `python -m experiments.train --config <cfg> --total-episodes N --run-dir runs/_sanity/<nombre>` con `LIBSUMO_AS_TRACI=1` y `OMP_NUM_THREADS=1`. Hubo como máximo 5 procesos a la vez en la Mac de 10 núcleos.
- **Episodios:** 40 a 200 por corrida, según la velocidad. El ε y las demás programaciones se escalan con `total_episodes`, así que una corrida corta es una versión comprimida de la larga.
- **Evaluación:** `experiments.evaluate.evaluate` sobre el escenario de entrenamiento (`cruce_pico` o `reforma_pico`) con las semillas 1000, 1001 y 1002, nunca vistas al entrenar. Las líneas base se evaluaron igual.
- **Métricas.** Se reportan la media y el IC95 (t de Student con 3 semillas, así que los intervalos son anchos):
  - `espera`: tiempo de espera medio por vehículo **insertado** (`mean_waiting_time` del contrato §7). Es la métrica oficial de los objetivos.
  - `backlog`: porcentaje de los vehículos del archivo de rutas que SUMO no logró insertar en la hora porque su carril de entrada estaba lleno.
  - `demora total`: la espera más el `departDelay` de los insertados, más `3600 − depart` para los que nunca entraron, dividida entre **todos** los vehículos de la demanda. Es la métrica que no se puede "ganar" dejando autos fuera de la red. El script de diagnóstico es `evalx.py`, que no está en el repo. Su lógica es la de `env.validate.loaded_vehicles` aplicada al tripinfo.

## 2. Tiempo de pared por episodio (3600 s, libsumo)

Se midió con `wall_time / episodios` del `train_log.csv`, con 4 o 5 entrenamientos corriendo en paralelo, que es lo que pasa en la matriz.

| Algoritmo | Escenario | s / episodio | Comentario |
|---|---|---|---|
| Q-Learning | cruce_pico | 1.4–1.5 | |
| Dyna-Q n=10 | cruce_pico | 1.45 | la planificación tabular cuesta casi nada |
| Dyna-Q n=50 | cruce_pico | 1.6 | |
| DQN double+dueling+PER | cruce_pico | 2.0–2.2 | una actualización por paso |
| PPO (SB3) | cruce_pico | 1.6–1.7 | |
| IDQN (5 redes) | reforma_pico | 7.6–8.5 | 5 actualizaciones por paso |
| QMIX | reforma_pico | 7.1–9.0 | |
| MAPPO | reforma_pico | 5.5–5.7 | 3 actualizaciones por episodio |
| comm (DIAL) | reforma_pico | 6.6–7.0 | |

Con los YAML finales y 3 o 4 procesos en paralelo, las corridas de 200 episodios tardaron 1063 s (comm), 1167 s (QMIX), 1297 s (IDQN), unos 1150 s (MAPPO), 391 s (DQN) y 334 s (PPO).

La evaluación cuesta unos 3.5 s por episodio en `cruce_pico` y unos 8 s en `reforma_pico` (tripinfo + emisiones).

## 3. Hallazgo principal: la recompensa no veía los autos que no podían entrar

La primera tanda (v0) se corrió con los hiperparámetros originales. A primera vista todo "aprendía" y le ganaba al tiempo fijo en espera media:

| Corrida (v0) | Escenario | Espera [s] | Backlog | Demora total [s] |
|---|---|---|---|---|
| tiempo fijo | cruce_pico | 29.2 ± 15.0 | 0.21 % | 31.6 ± 17.4 |
| actuado | cruce_pico | 29.0 ± 2.6 | 0.72 % | 37.9 ± 11.8 |
| max-pressure | cruce_pico | 27.7 ± 1.7 | 2.53 % | 65.8 ± 38.6 |
| DQN d+d+PER, 40 ep | cruce_pico | 14.9 ± 3.3 | **4.92 %** | 97.1 ± 51.8 |
| PPO, 40 ep | cruce_pico | 13.5 ± 3.2 | **6.59 %** | 112.9 ± 20.9 |
| Q-Learning, 40 ep | cruce_pico | 19.1 ± 2.6 | **7.94 %** | 139.9 ± 35.4 |
| tiempo fijo | reforma_pico | 77.7 ± 20.0 | 0.05 % | 78.7 ± 19.3 |
| actuado | reforma_pico | 58.1 ± 16.8 | 0.80 % | 70.5 ± 17.4 |
| max-pressure | reforma_pico | 86.3 ± 23.8 | 10.73 % | 207.0 ± 33.5 |
| IDQN, 30 ep | reforma_pico | 55.8 ± 18.8 | **13.17 %** | 249.0 ± 97.3 |
| QMIX, 30 ep | reforma_pico | 299.6 ± 41.0 | 36.97 % | 775.1 ± 77.3 |

**Diagnóstico.** Todos los agentes aprendieron a **cerrar una entrada**. En el cruce, con DQN y la semilla 1000, 195 de los 2115 vehículos NB nunca entraron, mientras que la espera de los SB bajó a 3.9 s. La causa está en la recompensa `diff-waiting-time` de sumo-rl, que solo cuenta la espera acumulada de los vehículos que están **sobre** los carriles de entrada. Cuando un carril se llena, su penalización queda acotada por su capacidad (unos 37 autos por carril de 284 m), y la demanda que no cabe espera fuera de la red sin costo alguno. Con la demanda calibrada (cerca de la capacidad), dejar un acceso "estacionado" es una política óptima para esa recompensa. Además, la métrica `mean_waiting_time` premia ese comportamiento porque solo promedia sobre los vehículos insertados (nota 2 del paso anterior para el integrador).

Se descartó primero que fuera la memoria de espera de SUMO: sumo-rl ya pasa `--waiting-time-memory 1000`, no los 100 s por defecto.

**Cambio 1: recompensa de entrenamiento `diff-waiting-time-pending`** (`agents/rewards.py`, en todos los algoritmos). Los vehículos pendientes de inserción en una arista de entrada del cruce (`edge.getPendingVehicles`) también acumulan espera:

    W_t = Σ_{v en carriles de entrada} espera_acum(v) + Σ_{v pendiente en aristas de entrada} (t − t_v)
    r_t = −(W_t − W_{t−1}) / 100

Al insertarse, un vehículo pendiente "devuelve" su espera de afuera, igual que cuando un auto cruza la línea de alto en `diff-waiting-time`. Así las dos partes siguen la misma lógica telescópica. Sin backlog es idéntica a la original (lo comprueba un test). Solo cambia la señal de entrenamiento: la evaluación usa tripinfo. Se elige con el hiperparámetro `reward_fn` (`scenario` vuelve a la recompensa original).

| Corrida | Antes (v0): espera / backlog / demora | Después (v1, mismos episodios) |
|---|---|---|
| DQN 40 ep | 14.9 / 4.92 % / 97.1 | 19.7 / **0.46 %** / **34.4** |
| PPO 40 ep | 13.5 / 6.59 % / 112.9 | 12.5 / 5.10 % / 90.0 (hacía falta el cambio 2) |
| Q-Learning 40 ep | 19.1 / 7.94 % / 139.9 | 30.4 / 7.81 % / 158.2 (ver cambio 6) |
| IDQN 30 ep | 55.8 / 13.17 % / 249.0 | 54.2 / 5.77 % / 123.9 (ver cambio 4) |
| QMIX 30 ep | 299.6 / 36.97 % / 775.1 | 58.3 / 12.23 % / 270.0 (también con Huber, cambio 5) |

La espera por vehículo insertado **sube** un poco porque ya no se excluye a los más demorados. La demora total baja entre 2 y 3 veces.

## 4. Cambios por algoritmo

Salvo que se diga otra cosa, cada fila compara dos corridas con la misma semilla, el mismo número de episodios y la recompensa del cambio 1.

### Cambio 2. PPO: normalización de la recompensa (`norm_reward: true`)
La recompensa (con backlog) tiene colas pesadas: |r| va de unos 0.1 a más de 50 por paso. Sin escalar, la pérdida del valor domina y la política apenas se mueve. Se envuelve el entorno en `VecNormalize(norm_obs=False, norm_reward=True)`. La observación ya está en [0, 1], así que el modelo guardado no necesita estadísticas. El log sigue mostrando la recompensa original.

| PPO 40 ep | Espera | Backlog | Demora total |
|---|---|---|---|
| sin normalizar (v1) | 12.5 ± 0.5 | 5.10 % | 90.0 ± 39.6 |
| `norm_reward` (v2) | 16.0 ± 1.1 | 1.31 % | 35.8 ± 19.2 |
| `norm_reward`, 100 ep | 17.1 ± 7.1 | 0.31 % | **20.8 ± 16.9** |
| `norm_reward`, 200 ep | 15.2 ± 2.8 | 1.16 % | 30.5 ± 35.5 |

### Cambio 3. DQN: `reward_scale` 0.1, `lr` 2.5e-4 y `target_update` 2000
Con la recompensa sin escalar, la pérdida Huber trabaja casi siempre en su tramo lineal (regresión L1) y las Q se sobreestiman: `q_mean` llegó a +40 cuando el retorno medio por paso era negativo. Con lr 1e-3, la corrida de 200 episodios "olvidó" la buena política y el backlog volvió.

| DQN d+d+PER | Episodios | Espera | Backlog | Demora total |
|---|---|---|---|---|
| r × 1, lr 1e-3, target 500 | 100 | 25.4 ± 17.6 | 0.31 % | 32.1 ± 23.2 |
| r × 0.1, lr 1e-3, target 500 | 100 | 20.4 ± 5.3 | 0.14 % | 27.8 ± 28.0 |
| r × 0.1, lr 1e-3, target 500 | 200 | 16.7 ± 2.0 | 3.71 % | 75.9 ± 41.4 |
| **r × 0.1, lr 2.5e-4, target 2000** (final) | 200 | 18.5 ± 7.5 | 0.29 % | **23.7 ± 19.7** |

### Cambio 4. IDQN y comm: recompensa de equipo, `reward_scale` 0.02, `lr` 1e-4 y Polyak `tau` 0.005
Con recompensa local, IDQN y comm dejaron 200 a 900 vehículos sin entrar por `NB_S_C15` y `SB_N_C06`, las dos entradas del corredor. El cruce aguas abajo (C14, cuyo enlace con C15 mide solo 86 m) puede llenar su acceso corto con una penalización acotada y empujar la cola hacia C15, que no tiene forma de resolverla. Es una externalidad que una recompensa local no castiga. Con la recompensa de equipo `r = Σ r_i` (el IQL cooperativo estándar, la misma recompensa que QMIX y MAPPO), cada agente paga los desbordes que provoca. Además, E5 compara entonces solo el grado de centralización, no la recompensa. `reward_scale` 0.02 sobre la suma de 5 cruces equivale a 0.1 por cruce.

| 80 episodios | Espera | Backlog | Demora total |
|---|---|---|---|
| IDQN local, lr 5e-4, target duro 500 (v2) | 65.2 ± 57.6 | 11.63 % | 197.4 ± 163.2 |
| IDQN local, lr 2.5e-4, target duro 2000 | 77.4 ± 52.3 | 9.93 % | 195.2 ± 149.1 |
| IDQN equipo, lr 5e-4, target duro 500 | 64.6 ± 15.3 | 4.35 % | 115.7 ± 76.7 |
| **IDQN equipo, lr 1e-4, tau 0.005** (final) | **47.3 ± 4.4** | 3.66 % | 89.7 ± 31.4 |
| comm local, lr 5e-4, target duro 500 (v2) | 40.3 ± 3.4 | 11.43 % | 196.7 ± 34.2 |
| comm equipo, lr 5e-4, target duro 500 | 58.6 ± 10.4 | 0.10 % | 60.7 ± 6.8 |
| **comm equipo, lr 1e-4, tau 0.005** (final) | 67.8 ± 9.0 | 1.09 % | 75.5 ± 16.0 |

Lo que hace que IDQN y comm dejen de cerrar las entradas es la recompensa de equipo. Bajar la `lr` sin cambiar la recompensa no ayudó. El aprendiz más lento (lr 1e-4 + Polyak) se dejó igual en IDQN, QMIX y comm, para que los tres métodos de valor de E5/E6 compartan hiperparámetros. Con 80 episodios, comm salió algo peor con él que con la copia dura (75.5 contra 60.7 de demora). Con los 200 episodios del presupuesto final quedó en 38.3 (sección 5), así que la diferencia es ruido.

### Cambio 5. QMIX: pérdida Huber, `reward_scale` 0.02, `lr` 1e-4 y Polyak `tau` 0.005
Con MSE, lr 5e-4 y copia dura cada 500 pasos, QMIX **divergía**: la pérdida crecía de 0.25 a 2.3, la espera del sistema subía de 2 a 58 s apenas ε llegaba a 0.05, y había 52 teletransportes por episodio. Primero se pasó a Huber (la misma pérdida de DQN e IDQN). Después se escaló la recompensa de equipo y, al final, se puso un objetivo suave con lr menor.

| QMIX | Episodios | Espera | Backlog | Demora total | Telep. |
|---|---|---|---|---|---|
| MSE, r × 0.1, lr 5e-4, duro 500 (v0, recompensa vieja) | 30 | 299.6 ± 41.0 | 36.97 % | 775.1 ± 77.3 | 51.7 |
| Huber, r × 0.1, lr 5e-4, duro 500 | 80 | 137.5 ± 33.0 | 5.30 % | 184.1 ± 68.1 | 9.7 |
| Huber, r × 0.02, lr 5e-4, duro 500 | 80 | 150.0 ± 68.2 | 6.17 % | 191.2 ± 112.1 | 36.3 |
| Huber, r × 0.02, lr 2.5e-4, duro 2000 | 80 | 62.8 ± 12.4 | 1.08 % | 92.7 ± 14.1 | 0.3 |
| VDN, r × 0.02, lr 5e-4, duro 500 (diagnóstico) | 80 | 56.4 ± 0.4 | 1.42 % | 71.2 ± 8.0 | 1.0 |
| **Huber, r × 0.02, lr 1e-4, tau 0.005** (final) | 80 | **37.0 ± 2.4** | 0.14 % | **38.5 ± 2.5** | 0 |

Con VDN, la versión estable sin hiperredes, ya funcionaba con lr 5e-4. Eso indica que la inestabilidad venía de la mezcladora con objetivos que se movían rápido, y que el objetivo suave lo resuelve.

### Cambio 6. MAPPO: tasa de aprendizaje con decaimiento lineal (`anneal_lr: true`)
MAPPO aprendió desde el principio sin cambios (80 ep: espera 43.4 ± 5.7, demora 75.2 ± 9.5). Con lr constante 5e-4 y 200 episodios, el retorno de entrenamiento empeoró después de unos 100 episodios: el promedio de 20 episodios pasó de −250 a −891. Se agregó el decaimiento lineal de la lr a 0, que es el valor por defecto de CleanRL.

| MAPPO | Episodios | Espera | Backlog | Demora total | Retorno de entrenamiento (bloques de 20 ep) |
|---|---|---|---|---|---|
| lr constante 5e-4 | 80 | 43.4 ± 5.7 | 3.02 % | 75.2 ± 9.5 | −1511, −250, −260, −272 |
| lr constante 5e-4 | 200 | 42.4 ± 6.1 | 3.59 % | 78.7 ± 11.6 | … −272, −558, −891, −763, −711, −382, −393 |
| **`anneal_lr`** (final) | 200 | **39.8 ± 4.8** | 3.40 % | **71.9 ± 23.4** | −1473, −929, −896, −771, −550, −389, −235, −598, −531, −365 |

La mejora en la evaluación es chica y queda dentro del IC. El decaimiento se mantiene porque garantiza que la política final no se aleje de la mejor alcanzada al terminar el presupuesto, que es la que se evalúa. MAPPO todavía deja unos 3 % de backlog en `NB_S_C15`, la entrada sur del corredor.

### Cambio 7. Q-Learning y Dyna-Q: 4 niveles de cola y el peor carril (`thresholds: [0.15, 0.45, 0.8]`, `agg: max`)
El estado tabular original (fase, bandera de verde mínimo y nivel bajo/medio/alto de la cola media de cada aproximación) no distingue un acceso **lleno** de uno solo "alto", ni ve un carril trabado dentro de una aproximación. Los agentes tabulares convergían a un ciclo con verdes mínimos (cambiar de fase apenas se puede). Q-Learning y Dyna-Q (n=10 y n=50) llegaron incluso a la **misma** secuencia efectiva de fases y a métricas idénticas en las tres semillas. Ese ciclo pierde capacidad con los amarillos y deja salir de la red la cola NB. Bajar γ a 0.9 no ayudó (backlog 8.3 %). Lo que ayudó fue agregar un nivel "lleno" (≥ 0.8) y usar el **máximo** de la aproximación: 3 × 2 × 4³ = 384 estados en el cruce.

| Tabular | Episodios | Espera | Backlog | Demora total |
|---|---|---|---|---|
| Q-L, 3 niveles, media (v1) | 40 | 30.4 ± 3.8 | 7.81 % | 158.2 ± 60.3 |
| Q-L, 4 niveles, media | 80 | 15.8 ± 3.7 | 6.50 % | 113.0 ± 29.4 |
| Q-L, 4 niveles, media | 200 | 17.8 ± 12.0 | 5.03 % | 110.8 ± 20.7 |
| Q-L, 4 niveles, media, γ = 0.9 | 200 | 14.1 ± 0.6 | 8.30 % | 138.0 ± 34.3 |
| **Q-L, 4 niveles, max** (final) | 200 | 18.7 ± 3.9 | **2.07 %** | **44.2 ± 56.9** |
| Dyna-Q n=10, 3 niveles, media | 80 | 15.8 ± 3.7 | 6.50 % | 113.0 ± 29.4 |
| **Dyna-Q n=10, 4 niveles, max** (final) | 200 | 13.7 ± 0.1 | 6.71 % | 113.4 ± 26.1 |

El cambio ayudó claramente a Q-Learning pero no a Dyna-Q con esta semilla. La planificación reproduce resultados guardados de estados que en realidad son distintos (estado no markoviano) y amplifica el sesgo hacia el ciclo de verdes mínimos. Se mantiene la misma representación para Q-L y Dyna-Q, para que E2 compare solo la planificación. Que Dyna-Q no supere a Q-Learning en este problema es un resultado esperable de E2 y debe discutirse como tal.

## 5. Resultado de sanidad con la configuración final

La semilla de entrenamiento es 0 y la evaluación usa las semillas 1000 a 1002. "vs fijo" compara la espera media, que es la métrica de los objetivos. La demora total se agrega para que el lector vea el backlog.

Son los YAML finales de `experiments/configs/` con 200 episodios. Las únicas excepciones son las corridas marcadas con *, que usan exactamente los mismos hiperparámetros con `--total-episodes` explícito.

| Método | Escenario | Espera media [s] | vs fijo | Backlog | Demora total [s] |
|---|---|---|---|---|---|
| tiempo fijo | cruce_pico | 29.2 ± 15.0 | — | 0.21 % | 31.6 ± 17.4 |
| actuado | cruce_pico | 29.0 ± 2.6 | −1 % | 0.72 % | 37.9 ± 11.8 |
| max-pressure | cruce_pico | 27.7 ± 1.7 | −5 % | 2.53 % | 65.8 ± 38.6 |
| Q-Learning | cruce_pico | 18.7 ± 3.9 | −36 % | 2.07 % | 44.2 ± 56.9 |
| Dyna-Q n=10 | cruce_pico | 13.7 ± 0.1 | −53 % | 6.71 % | 113.4 ± 26.1 |
| DQN d+d+PER | cruce_pico | 18.5 ± 7.5 | **−37 %** | 0.29 % | 23.7 ± 19.7 |
| PPO | cruce_pico | 15.2 ± 2.8 | **−48 %** | 1.16 % | 30.5 ± 35.5 |
| PPO, 100 ep* | cruce_pico | 17.1 ± 7.1 | −41 % | 0.31 % | 20.8 ± 16.9 |
| tiempo fijo | reforma_pico | 77.7 ± 20.0 | — | 0.05 % | 78.7 ± 19.3 |
| actuado | reforma_pico | 58.1 ± 16.8 | −25 % | 0.80 % | 70.5 ± 17.4 |
| max-pressure | reforma_pico | 86.3 ± 23.8 | +11 % | 10.73 % | 207.0 ± 33.5 |
| IDQN | reforma_pico | 50.4 ± 5.4 | **−35 %** | 4.32 % | 98.8 ± 25.8 |
| QMIX | reforma_pico | 58.4 ± 12.2 | **−25 %** | 0.20 % | 59.7 ± 13.0 |
| QMIX, 80 ep* | reforma_pico | 37.0 ± 2.4 | −52 % | 0.14 % | 38.5 ± 2.5 |
| MAPPO | reforma_pico | 39.8 ± 4.8 | **−49 %** | 3.40 % | 71.9 ± 23.4 |
| comm (E6) | reforma_pico | 37.0 ± 8.6 | −52 % | 0.11 % | 38.3 ± 8.4 |

Las diferencias entre QMIX con 80 y con 200 episodios, y entre PPO con 100 y con 200, muestran cuánto varía la política del último episodio de una misma corrida. Con 5 semillas de entrenamiento y 10 de evaluación, la matriz va a promediar ese ruido.

**Objetivos:**
- **DQN y PPO le ganan al tiempo fijo en `cruce_pico`** en espera media: 18.5 y 15.2 a 17.1 s, contra 29.2 s. En demora total, contando el backlog, quedan **a la par o algo mejor** (23.7 y 20.8 a 30.5 s, contra 31.6 s); los IC95 se solapan con 3 semillas.
- **En `reforma_pico`, los tres métodos de E5 (IDQN, QMIX y MAPPO) le ganan al tiempo fijo en espera media** (50.4, 58.4 y 39.8 s, contra 77.7 s); comm también (37.0 s). En demora total, QMIX (59.7 s) y comm (38.3 s) también mejoran al fijo (78.7 s), y MAPPO queda a la par (71.9 s). IDQN la empeora (98.8 s), porque todavía deja 4 % de backlog en la entrada NB.
- QMIX deja sin servir una calle transversal en una de las semillas (espera máxima de 1573 s). Hay que vigilarlo en E8 (equidad).
- **Max-pressure no es la referencia que hay que vencer.** En el cruce es la mejor línea base en espera media (27.7 s), aunque con 2.5 % de backlog. En el corredor calibrado se traba (nota 1 del paso anterior para el integrador). Ganarle en el cruce no era requisito. DQN y PPO le ganan en espera, pero con 3 semillas no se puede afirmar una mejora robusta en todas las métricas.
- Los métodos tabulares aprenden (el retorno mejora de −4800 a −400) y le ganan al fijo en espera, pero siguen dejando backlog (2 % Q-L y 7 % Dyna-Q). Su demora total es peor y muy variable. Es una limitación del estado discreto, parcialmente observable: no ve los vehículos pendientes ni cuánto lleva la fase en verde. Es un resultado de E2 en sí mismo (PLAN §14).

## 6. Presupuesto final (PLAN §8)

| Experimento | `total_episodes` | Pasos de entorno por agente | Por qué |
|---|---|---|---|
| E2 (Q-L, Dyna-Q n5/n10/n50) | 200 | 144 000 | El retorno tabular sigue bajando hasta unos 150 episodios |
| E3 (4 variantes de DQN) | 200 | 144 000 | DQN se estabiliza hacia los 60–80 episodios (retorno de −40 a −120). Con 200 queda margen y el ε termina en el episodio 100 |
| E4 (dqn_best, PPO) | 200 | 144 000 | Igual que E3. PPO se estabiliza hacia los 80 episodios |
| E5 (IDQN, QMIX, MAPPO) | 200 | 144 000 decisiones por agente | Con 80 episodios los métodos de valor seguían mejorando. Con 200 (retorno de equipo por bloque de 20 episodios): QMIX se estabiliza desde el episodio 60–80 (−385, −165, −357, −118, …, −172), comm desde el 100 (−245, −191, …, −99) y MAPPO desde el 120–140. IDQN sigue mejorando despacio hasta el final (−2004, −1521, …, −1294), así que es el único que **no** llega del todo a la meseta |
| E6 (IDQN + colas vecinas, comm) | 200 | 144 000 | Igual que E5, para poder comparar |

Dentro de cada experimento, todos los algoritmos tienen el mismo número de pasos de entorno (episodios de 720 decisiones de 5 s).

**Tiempo estimado de la matriz** (`run_matrix --exp E2 E3 E4 E5 E6 --seeds 0 1 2 3 4 --jobs 8`), con los s/episodio de la sección 2 y la evaluación final con 10 semillas en los escenarios de `eval`:

| Exp | Corridas | Entrenamiento [proceso·s] | Evaluación [proceso·s] |
|---|---|---|---|
| E2 | 20 | ≈ 6 100 | ≈ 1 400 |
| E3 | 20 | ≈ 7 800 | ≈ 1 400 |
| E4 | 10 | ≈ 3 600 | ≈ 700 |
| E5 | 15 | ≈ 20 400 | ≈ 3 900 |
| E6 | 10 | ≈ 14 200 | ≈ 2 600 |
| **Total** | 75 | ≈ 52 000 | ≈ 10 000 |

Son unos 62 000 proceso·s. Divididos entre 8 trabajos dan unas 2.2 h ideales. Con 8 procesos el SUMO de cada uno va algo más lento que con 5 (factor de 1.25 a 1.3), y al final quedan las corridas largas de E5/E6 (unos 30 min cada una). La estimación queda en **unas 3 h a 3.5 h**, más unos 10 min de E1, E7 y E8. Entra con holgura en la ventana de 6 a 10 h, aunque otros procesos compartan la CPU. No hace falta Colab. Si se quisiera, E5/E6 (25 corridas, unos 2/3 del costo) son lo que conviene mandar a Colab, una sesión por semilla.

## 7. Notas y limitaciones
- Todo esto es **una sola semilla de entrenamiento** evaluada con 3 semillas de demanda. Los IC95 son anchos y la diferencia entre variantes de DQN de E3 queda dentro del ruido: vanilla 27.4 / 29.0, double 17.8 / 37.7, double+dueling 17.1 / 66.0, d+d+PER 20.4 / 27.8 (espera / demora total, 100 episodios, lr 1e-3). Por eso `E4/dqn_best.yaml` conserva los tres flags. Si E3 con 5 semillas muestra una ganadora clara, hay que cambiarlo.
- La política que se evalúa es la del **último** episodio. Las curvas de DQN y de los métodos MARL de valor siguen oscilando incluso con ε = 0.05. Elegir el mejor checkpoint con una validación aparte mejoraría los números, pero no se hizo para no tocar `experiments/`.
- `idqn_neighbor_obs` no se corrió por separado. Usa el mismo aprendiz y los mismos hiperparámetros que IDQN y solo agrega las colas de los vecinos a la entrada.
- La comparación con `mean_waiting_time` sola sigue siendo engañosa cuando hay backlog. Se recomienda que `experiments/metrics.py` agregue el backlog de inserción o la demora total (ver las notas para el integrador del reporte).
