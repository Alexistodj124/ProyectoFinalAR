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

## Valores sintéticos actuales (hora pico)
- Reforma entra con 1800 veh/h hacia el norte y 1600 veh/h hacia el sur. Cerca del 12–18 % gira hacia la transversal.
- Las transversales llevan entre 450 y 700 veh/h; la 12 calle es la más cargada. El reparto es 68/16/16 entre recto, izquierda y derecha.
- Los flujos son **consistentes a lo largo del corredor**: lo que llega a la 14 calle es lo que siguió recto en la 15 calle más lo que entró desde la 15 calle.
- El mediodía es cerca del 65 % del pico, con sentidos más parejos y más giros.

## Cómo reemplazarlos con conteos reales
1. Grabar 15 min por intersección en hora pico (≈ 7:00 o 17:30) y a mediodía, y contar por aproximación y movimiento (PLAN §6.2).
2. Escribir `pico.csv` y `mediodia.csv` con el mismo formato y **quitar la línea `# SINTETICO`**, así `scripts/build_network.sh` ya no los sobrescribe.
3. Si solo se contaron 2 o 3 intersecciones, se completan las demás con proporciones razonables y se anota en el informe. Las aproximaciones de Reforma en los extremos (`C15 sur` y `C06 norte`) definen el flujo que entra al corredor. En los cruces intermedios solo se usan las **proporciones** de giro.
4. Regenerar con `bash scripts/build_network.sh`, que recalcula los repartos de verde del tiempo fijo y las rutas estáticas. La caché `env/routes/cache/` se invalida sola, porque su nombre incluye un hash de los conteos.
5. Validar con `python -m env.validate` contra el tiempo de Google Maps y actualizar `REFERENCE_S`.

## Cómo se convierten en rutas (`env/demand.py`)
Es el modelo de proporciones de giro (como `jtrrouter`), resuelto de forma exacta:
- Cada borde de entrada recibe su flujo contado multiplicado por la escala del perfil.
- En cada cruce se elige el movimiento con la probabilidad `conteo(movimiento) / conteo(aproximación)`.
- Se enumeran todas las rutas y a cada una se le asignan llegadas de Poisson, de forma determinista según la semilla.
