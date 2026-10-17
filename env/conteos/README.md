# Conteos vehiculares

> **Los archivos actuales son SINTÉTICOS y PROVISIONALES** (los genera `python -m env.synthetic_counts`). Se reemplazan por los conteos en video del PLAN §6.2.

## Formato (contrato, docs/ARCHITECTURE.md §3)
`pico.csv` y `mediodia.csv`, en formato largo. Las líneas que empiezan con `#` son comentarios.

```
interseccion,aproximacion,movimiento,vehiculos_15min
C12,oeste,recto,119
```
- `interseccion`: el id del TLS (`C15`, `C14`, `C12`, `C10`, `C06`; ver `env/net/tls_names.json`).
- `aproximacion`: **de dónde viene** el tráfico: `sur` (Reforma hacia el norte), `norte` (Reforma hacia el sur), `este` u `oeste` (la transversal).
- `movimiento`: `recto`, `izquierda` o `derecha`, desde el punto de vista del conductor.
- `vehiculos_15min`: los vehículos contados en 15 min. Para pasar a veh/h se multiplica por 4.

Movimientos que existen en la red: desde Reforma, `recto` más el único giro legal hacia la transversal de una vía; desde la transversal, los tres. Si una fila nombra un movimiento que no existe, se ignora y se renormaliza.

## Valores sintéticos actuales (v2, calibrados)
Hora pico (`pico.csv`, 7352 veh/h en total en el corredor):
- Reforma entra con **2200 veh/h hacia el norte** (Plaza Obelisco) y **2450 veh/h hacia el sur** (5a calle), unos 730–820 veh/h por carril.
- Las transversales llevan entre 450 y 700 veh/h (15 calle 450, 14 calle 500, 12 calle 700, 10a calle 500, 6a calle 550). El reparto es 58 % recto, 30 % gira hacia Reforma norte y 12 % hacia Reforma sur (en la mañana el flujo va hacia el norte).
- De Reforma gira hacia la transversal entre 8 y 18 %, salvo los dos giros a la izquierda **permisivos en carril compartido** que están en un borde de entrada: norte→15 calle (2 %) y sur→6a calle (8 %). Con más giro, los que esperan hueco bloquean el carril izquierdo de la entrada y la cola sale de la red.
- Los flujos son **consistentes a lo largo del corredor**: lo que llega a la 14 calle es lo que siguió recto en la 15 calle más lo que entró desde la 15 calle (lo comprueba `tests/test_env_reforma.py`).

Mediodía (`mediodia.csv`, 4788 veh/h = **65 % del pico**): Reforma 1650 norte / 1350 sur (el pico va más cargado al sur, el mediodía al norte), transversales 300–470 veh/h con 56/22/22 y más giros desde Reforma.

Los otros perfiles salen de `env/scenarios.py::PROFILES`: `pico_x13` = pico × 1.3 (estrés, congestión fuerte) y `noche` = pico × 0.3. `cruce_*` usa exactamente las filas de `C12` de los mismos archivos.

## Calibración (PLAN §6.2 "Validar")
**Objetivo.** Con el tiempo fijo "medido" (`env/net/reforma_fixed.add.xml`, no se tocó), el tiempo de viaje de los vehículos que recorren **todo** el corredor debe quedar a ±15 % de la referencia de `env/validate.py` (330 s norte, 300 s sur; todavía es un PLACEHOLDER de Google Maps), **sin bloqueo**: teletransportes < 1 % de los insertados, backlog de inserción (vehículos que SUMO no pudo meter porque su borde de entrada estaba lleno) < 2 %, y colas que crecen y se vacían dentro de la red.

**Punto de partida (v1).** Con 1800/1600 veh/h en Reforma y el `vType` por defecto de SUMO, el corredor se recorría en ~160 s por sentido: el pico estaba muy por debajo de la capacidad (casi sin demora en los semáforos) y al RL le quedaba poco que mejorar.

**Procedimiento.**
1. *Comportamiento de los conductores* (`env/demand.py::VTYPE`): `accel=2.2`, `decel=4.0`, `sigma=0.6`, `tau=1.2`, `minGap=2.5`, `speedFactor=normc(0.8, 0.1, 0.6, 1.1)`. La descarga en verde baja de ~1900 a ~1530 veh/h por carril (medida con una cola saturada en la aproximación norte de `C12`, incluye la pérdida de arranque), que es lo típico de una arteria urbana con tránsito mixto. La velocidad deseada de ~40 km/h (0.8 × 50 km/h) representa la fricción que la red no modela: buses que paran, carriles auxiliares, calles sin semáforo y peatones.
2. *Escala global y reparto Reforma/transversales* (`env/synthetic_counts.py::PROFILES`), barriendo con simulaciones de 1 h y 3–10 semillas:
   - Reforma ×1.37 (norte ×1.22, sur ×1.53). Las transversales se dejan casi igual (×0.95): ya estaban cerca de la capacidad que les da el tiempo fijo (18–24 s de verde cada 110 s). La 10a calle baja de 650 a 500 veh/h porque con 650 tenía x ≈ 1 y su cola salía de la red.
   - Los giros desde las transversales se sesgan hacia el norte (30 % frente a 12 %). Así la carga del sentido norte crece aguas abajo, donde hay más espacio para la cola (507 m entre `C10` y `C06`), en vez de saturar la entrada (234 m antes de `C15`).
   - Bajan los dos giros permisivos en carril compartido de los bordes de entrada (norte→15 calle: 12 % → 2 %; sur→6a calle: 15 % → 8 %).
   - **Factor resultante**: demanda total del corredor ×1.18 (6252 → 7352 veh/h); cruce `C12` ×1.37 (3572 → 4896 veh/h).
3. *Validación*: `python -m env.validate` (tiempo fijo, semillas 1000–1002) y `python -m experiments.evaluate` para las tres líneas base. El tiempo de viaje responde de forma muy no lineal cerca de la capacidad: con 2150 veh/h hacia el norte da 280 s y con 2250 da 356 s. Los valores elegidos quedan a mitad de la banda y el promedio de las 10 `EVAL_SEEDS` da NB 335 s y SB 304 s.

**Antes / después** (semillas 1000–1002, 3600 s, `experiments.evaluate`; NB/SB = tiempo de viaje medio del corredor completo; espera = espera media por vehículo insertado; insertados = veh/h que entraron a la red; backlog = % de vehículos del archivo de rutas que no se pudieron insertar):

| escenario | programa | NB [s] antes → después | SB [s] antes → después | espera [s] | teletransp. | insertados [veh/h] | backlog |
|---|---|---|---|---|---|---|---|
| `reforma_pico` | fijo | 161 → **342** (+3.5 %) | 162 → **305** (+1.5 %) | 33.0 → 77.7 | 0 → 0 | 6225 → 7328 | 0.0 → 0.1 % |
| `reforma_pico` | actuado | 172 → 299 | 156 → 235 | 20.1 → 58.1 | 0 → 0 | 6225 → 7273 | 0.0 → 0.8 % |
| `reforma_mediodia` | fijo | 156 → 202 | 157 → 203 | 28.0 → 29.9 | 0 → 0 | 4172 → 4745 | 0.1 → 0.1 % |
| `reforma_mediodia` | actuado | 161 → 204 | 148 → 187 | 14.1 → 17.8 | 0 → 0 | 4172 → 4745 | 0.1 → 0.1 % |
| `reforma_pico_x13` | fijo | 171 → 457 | 167 → 383 | 52.2 → 118.8 | 0 → 0 | 7764 → 8031 | 2.9 → 16.0 % |
| `reforma_pico_x13` | actuado | 198 → 372 | 171 → 325 | 36.7 → 82.2 | 0 → 0 | 7979 → 8037 | 0.2 → 16.0 % |
| `cruce_pico` | fijo | – | – | 16.3 → 29.2 | 0 → 0 | 3531 → 4842 | 0.0 → 0.2 % |
| `cruce_pico` | actuado | – | – | 10.3 → 29.0 | 0 → 0 | 3531 → 4817 | 0.0 → 0.7 % |

Lectura:
- En el pico, el tiempo fijo cumple el criterio (+3.5 % / +1.5 %, sin teletransportes, backlog 0.1 %). El actuado ya baja la espera 25 % (77.7 → 58.1 s), así que hay margen real para los métodos adaptativos.
- Colas: el número de vehículos detenidos sube durante los primeros 30–40 min (~50 → ~180) y luego fluctúa. Las colas que más crecen están en los dos enlaces largos de 507 m (`C06` norte y `C10` sur, los movimientos críticos con x ≈ 0.95), pero no salen de la red (`env.validate` reporta la razón cola fin/mitad ≈ 1.2–1.3).
- `pico_x13` es congestión fuerte a propósito: 16 % de backlog, sobre todo en las dos entradas de Reforma, y sin teletransportes en fijo ni en actuado.
- La tabla de max-pressure está en `env/net/README.md` (sección Validación).

## Cómo reemplazarlos con conteos reales
1. Grabar 15 min por intersección en hora pico (≈ 7:00 o 17:30) y a mediodía, y contar por aproximación y movimiento (PLAN §6.2).
2. Escribir `pico.csv` y `mediodia.csv` con el mismo formato y **quitar la línea `# SINTETICO`**, así `scripts/build_network.sh` ya no los sobrescribe.
3. Si solo se contaron 2 o 3 intersecciones, se completan las demás con proporciones razonables y se anota en el informe. Las aproximaciones de Reforma en los extremos (`C15 sur` y `C06 norte`) definen el flujo que entra al corredor. En los cruces intermedios solo se usan las **proporciones** de giro.
4. Regenerar con `bash scripts/build_network.sh`, que recalcula los repartos de verde del tiempo fijo y las rutas estáticas. La caché `env/routes/cache/` se invalida sola, porque su nombre incluye un hash de los conteos.
5. Validar con `python -m env.validate` contra el tiempo de Google Maps y actualizar `REFERENCE_S`. Si el tiempo fijo queda fuera de ±15 %, se recalibra solo el `vType` (`env/demand.py::VTYPE`), porque los conteos ya son medidos.

## Cómo se convierten en rutas (`env/demand.py`)
Es el modelo de proporciones de giro (como `jtrrouter`), resuelto de forma exacta:
- Cada borde de entrada recibe su flujo contado multiplicado por la escala del perfil.
- En cada cruce se elige el movimiento con la probabilidad `conteo(movimiento) / conteo(aproximación)`.
- Se enumeran todas las rutas y a cada una se le asignan llegadas de Poisson, de forma determinista según la semilla.
