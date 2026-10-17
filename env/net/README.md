# Red de Av. La Reforma (zona 9/10, Ciudad de Guatemala)

Todo lo de esta carpeta se genera con `bash scripts/build_network.sh` (o `python -m env.build_network`). No se edita a mano.

| archivo | contenido |
|---|---|
| `osm/reforma_raw.osm.xml` | Extracto de OpenStreetMap (Overpass, bbox 14.585–14.612 N, −90.522 – −90.503 W, 1.2 MB, © colaboradores de OSM, licencia ODbL) |
| `reforma.net.xml` | Corredor: 5 cruces semaforizados = 5 TLS (agentes de MARL) |
| `cruce.net.xml` | Cruce más cargado (`C12`, 12 calle) recortado del corredor con `--keep-edges.explicit` (1 TLS) |
| `*_fixed.add.xml` | Tiempo fijo "medido en campo" (`programID="fixed"`). **PROVISIONAL Y SINTÉTICO** |
| `*_actuated.add.xml` | Programa actuado de SUMO (`programID="actuated"`, `type="actuated"`) |
| `tls_names.json` | `tls_id -> "Reforma y 12 calle"` |

## Tramo elegido

Son 5 intersecciones semaforizadas **consecutivas** de la Avenida La Reforma, de sur a norte, entre la Plaza Obelisco (16 calle) y la 5a calle. En OSM no hay más semáforos sobre Reforma entre ellas: la 13 calle, la 11 calle y la 9a–7a calle no tienen semáforo.

| TLS | nombre | nodos OSM `highway=traffic_signals` | lat, lon (centro) | calle transversal (OSM) |
|---|---|---|---|---|
| `C15` | Reforma y 15 calle | 410455814, 516392127 | 14.597197, −90.517160 | 15 calle, una vía hacia el **oeste**, 3 carriles (way 676616368) |
| `C14` | Reforma y 14 calle | 410453351, 481805124, 481805128, 481805139 | 14.598285, −90.516929 | 14 calle, una vía hacia el **este**, 3 carriles (way 400025518) |
| `C12` | Reforma y 12 calle | 410407928, 410455570, 3820122586, 3820122589 | 14.600993, −90.516561 | 12 calle, una vía hacia el **este**, 3 carriles (way 641025046) |
| `C10` | Reforma y 10a calle | 410454143, 516392077, 516392086 | 14.603621, −90.516041 | 10a calle, una vía hacia el **oeste**, 4 carriles (way 380916947) |
| `C06` | Reforma y 6a calle | 410451994, 412283345, 516392066, 4026335921, 4026335922 | 14.608470, −90.515045 | 6a calle, una vía hacia el **este**, 3 carriles (way 754396843) |

Extremos del corredor: el sur está en el semáforo de la Plaza Obelisco (nodo 410414371) y el norte en el de Reforma y 5a calle (nodo 412196554). Distancias entre cruces consecutivos: 123 m, 302 m, 296 m y 547 m. El corredor mide 1.65 km.

**Por qué este tramo.** Es el tramo pedido en el plan (~10a–16 calle) más la 6a calle, para tener 5 agentes. Las transversales son pares de una vía que alternan de sentido (15 al oeste, 14 al este, 12 al este, 10a al oeste, 6a al este), que es lo típico de la zona 9/10. Las distancias son muy desiguales (123 m frente a 547 m), y eso hace interesante la coordinación entre agentes. Además, los cruces son heterogéneos.

## Cómo se construye y por qué no es una importación directa de OSM

El plan (§6.1) proponía `netconvert --osm-files ... --tls.guess-signals --junctions.join --geometry.remove --ramps.guess`. Esa importación se conserva como diagnóstico (`python -m env.build_network --osm-raw`). En esta zona produce **280 aristas y 18 TLS**, por tres razones:
- En OSM, Reforma tiene **4 calzadas**: las 2 centrales y 2 "Carril Auxiliar".
- Hay decenas de `primary_link` y retornos en el arriate central.
- `--tls.join` une 15 y 14 calle en un solo TLS con un ciclo de 444 s.

Limpiar eso en netedit lleva días, que es justo el riesgo de PLAN §14. Por eso se aplicó la mitigación prevista: **corredor construido en XML plano con la geometría real**. `env/build_network.py` toma del extracto OSM:
- las coordenadas reales de cada cruce (media de sus nodos `traffic_signals`) y de los extremos;
- la dirección de cada transversal de una vía (de su way de aproximación);
- el número de carriles (`lanes=*`).

Con eso escribe `nod/edg/con/tll` y llama a `netconvert --proj.plain-geo --proj.utm`. La red queda georreferenciada en UTM 15N, así que `traci.simulation.convertGeo` devuelve lat/lon reales para la web.

Modelo de cada cruce:
- **Reforma**: bulevar dividido con 3 carriles por sentido a 50 km/h. Cada cruce del bulevar es **un solo nodo y un solo TLS**: el arriate queda dentro del área de la intersección.
- **Bahías de giro a la izquierda**: un 4.º carril exclusivo, en SB en `C12` y en NB en `C10`.
- **Transversales**: de una vía, a 40 km/h, con una cuadra antes (170 m) y una después (150 m) del cruce. Los carriles que sobran respecto al ancho de salida son solo de giro a la izquierda.
- **Giros**: desde Reforma solo existe el giro legal hacia la transversal de una vía (derecha o izquierda según su sentido). Desde la transversal hay recto, izquierda y derecha. Sin vueltas en U.
- **Conexiones e índices de enlace explícitos**: así las fases son exactamente las definidas en `green_phases()`.

| TLS | fases verdes (acción `Discrete(n)`) | carriles de entrada | dim. obs (sumo-rl) |
|---|---|---|---|
| `C15` | 2: Reforma (izq. permisiva) · 15 calle | 9 | 21 |
| `C14` | 3: Reforma · adelanto SB + izq. protegida · 14 calle | 9 | 22 |
| `C12` | 3: Reforma · adelanto SB + izq. protegida (bahía) · 12 calle | 10 | 24 |
| `C10` | 3: Reforma · adelanto NB + izq. protegida (bahía) · 10a calle (4 carriles) | 11 | 26 |
| `C06` | 3: Reforma · adelanto SB + izq. protegida · 6a calle | 9 | 22 |

La dimensión de la observación es `n_green + 1 + 2·carriles` (fase one-hot, bandera de verde mínimo, densidad y cola por carril). QMIX/MAPPO con parámetros compartidos necesitan relleno y máscara de acciones (PLAN §5).

`env.scenarios.get_topology(reforma.net.xml)` devuelve el orden correcto `C15 → C14 → C12 → C10 → C06`, así que no hace falta `reforma_topology.json`.

## Programas base
- **Tiempo fijo (`fixed`)**: ciclo común de 110 s. El verde se reparte según Webster, `g_i ∝ y_i = q_i / (carriles·1800)`, con los conteos de `env/conteos/pico.csv`, y hay verdes mínimos. Los offsets forman una onda verde hacia el norte a 40 km/h. Es un **"ciclo medido" sintético y PROVISIONAL**: cuando se cronometren los semáforos reales (PLAN §6.1), se reemplazan las duraciones en `CORRIDOR`/`webster_greens()` o directamente en el `.add.xml`.
- **Actuado (`actuated`)**: mismas fases. Reforma va de 15 a 70 s, la izquierda protegida de 8 a 25 s y la transversal de 10 a 50 s, con `max-gap` de 3 s.
- `make_parallel_env(..., fixed_ts=True, program="fixed"|"actuated")` carga el `.add.xml`, y SUMO activa el último programa cargado. `tests/test_env_reforma.py` lo comprueba con `traci.trafficlight.getProgram`.
- El programa `0` de la red (el que usa sumo-rl para definir las fases del agente) tiene las mismas fases verdes, con duraciones por defecto.

## Validación (`python -m env.validate`)
`python -m env.validate [--program fixed|actuated] [--scenario ...] [--seeds ...]` corre el programa base y mide el tiempo de viaje de los vehículos que recorren **todo** el corredor (`NB_S_C15 → NB_C06_N` y `SB_N_C06 → SB_C15_S`). Lo compara con la referencia de "Google Maps" (`REFERENCE_S`: 330 s NB y 300 s SB, todavía un **PLACEHOLDER** hasta consultar el valor real a la hora de los conteos). También reporta la espera media, los insertados, el backlog de inserción, los teletransportes y la razón cola fin/mitad. Con tiempo fijo en `reforma_pico` imprime `CALIBRACION OK` cuando se cumple todo: ±15 % en los dos sentidos, teletransportes < 1 % y backlog < 2 %.

**Calibración v2** (procedimiento y factores en `env/conteos/README.md`). Antes, con tiempo fijo, el corredor se recorría en ~160 s por sentido, sin teletransportes: el pico era demasiado liviano. Ahora, con tiempo fijo y las semillas 1000–1002:

| | NB [s] | SB [s] | espera [s] | backlog | teletransp. | cola fin/mitad |
|---|---|---|---|---|---|---|
| referencia (placeholder) | 330 | 300 | | < 2 % | < 1 % | |
| v1 (antes) | 161 | 162 | 33.0 | 0.0 % | 0 | |
| **v2 fijo** | **342 (+3.5 %)** | **305 (+1.5 %)** | 77.7 | 0.05 % | 0 | 1.27 |
| v2 actuado | 299 | 235 | 58.1 | 0.8 % | 0 | 1.20 |

Con las 10 `EVAL_SEEDS`, el tiempo fijo da NB 335 s y SB 304 s.

**Líneas base actuales (E1).** `python -m experiments.run_matrix --exp E1`: 10 semillas de evaluación (1000–1009), 3600 s, media ± IC95, con el max-pressure corregido (`baselines/max_pressure.py`: conjuntos de carriles, presión por ocupación y `max_green`). Demora total = s por vehículo **demandado**, contando a los que no lograron entrar (`docs/ARCHITECTURE.md` §7). Ninguna línea base tuvo teletransportes. Tabla completa: `analysis/results/E1_eval.md`.

| escenario | método | demora total [s] | espera media [s] | backlog | tiempo de viaje [s] | espera máx. transversal [s] |
|---|---|---|---|---|---|---|
| `reforma_pico` | fijo | 79.1 ± 8.5 | 77.1 ± 7.7 | 0.18 % | 228.5 | 524 |
| `reforma_pico` | actuado | 63.4 ± 6.1 | 57.9 ± 4.7 | 0.37 % | 200.3 | 832 |
| `reforma_pico` | max-pressure | **41.7 ± 2.5** | **40.1 ± 2.0** | 0.12 % | 203.0 | 420 |
| `reforma_mediodia` | fijo | 30.4 ± 0.3 | 29.9 ± 0.3 | 0.04 % | 143.2 | 161 |
| `reforma_mediodia` | actuado | **18.7 ± 0.5** | **18.2 ± 0.5** | 0.04 % | 131.9 | 124 |
| `reforma_mediodia` | max-pressure | 21.1 ± 0.3 | 20.5 ± 0.3 | 0.04 % | 138.0 | 158 |
| `reforma_pico_x13` | fijo | 345.7 ± 9.7 | 123.1 ± 3.5 | 15.71 % | 301.3 | 666 |
| `reforma_pico_x13` | actuado | 320.4 ± 11.9 | 79.4 ± 3.8 | 15.18 % | 228.9 | 422 |
| `reforma_pico_x13` | max-pressure | **252.2 ± 11.5** | **60.2 ± 5.3** | 12.69 % | 259.8 | 1049 |
| `cruce_pico` | fijo | 33.6 ± 6.7 | 31.3 ± 5.1 | 0.25 % | 102.4 | 113 |
| `cruce_pico` | actuado | 38.0 ± 6.4 | 29.0 ± 1.0 | 0.80 % | 98.6 | 100 |
| `cruce_pico` | max-pressure | **19.8 ± 5.8** | **16.7 ± 2.0** | 0.27 % | 90.9 | 271 |

Max-pressure es la mejor línea base en hora pico y con +30 % de demanda; a mediodía en el corredor gana el actuado. Su costo es la equidad: en el cruce hace esperar más a la transversal (espera máxima 271 s contra 113 s del fijo). La primera versión de max-pressure (presión sumada por enlace controlado, vehículos detenidos) favorecía siempre a las fases de Reforma, dejaba sin verde a las transversales de una vía y trababa el corredor (en `reforma_pico`, 3 semillas: 10.7 % de backlog y 9.7 teletransportes por episodio); esos números ya no aplican. En `reforma_pico_x13` las tres líneas base dejan entre 12.7 % y 15.7 % de la demanda fuera de la red: por eso hay que mirar la demora total y el backlog, no solo la espera media, que promedia sobre los vehículos insertados.

## Limitaciones conocidas
- No se modelan los carriles auxiliares de Reforma ni las transversales sin semáforo (13, 11, 9a–7a calle), que en la realidad meten y sacan tráfico a media cuadra.
- No hay peatones, buses ni motos: solo `passenger`.
- Los tiempos y los conteos son sintéticos (ver `env/conteos/README.md`).
