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
Con tiempo fijo, `reforma_pico` y semilla 0, el corredor completo se recorre en unos 160 s en cada sentido, sin teletransportes. La referencia de "Google Maps" en `env/validate.py` es un **PLACEHOLDER** (330 s NB y 300 s SB) hasta que se consulte el valor real a la hora de los conteos. Si la simulación queda muy por debajo, se calibra subiendo la demanda (conteos reales) o ajustando el `vType` en `env/demand.py`.

## Limitaciones conocidas
- No se modelan los carriles auxiliares de Reforma ni las transversales sin semáforo (13, 11, 9a–7a calle), que en la realidad meten y sacan tráfico a media cuadra.
- No hay peatones, buses ni motos: solo `passenger`.
- Los tiempos y los conteos son sintéticos (ver `env/conteos/README.md`).
