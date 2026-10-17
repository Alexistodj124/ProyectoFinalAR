# Render del mapa (feat/ui-calles)

Dibujo del mapa de la demo en Canvas 2D, sin librerías. Dos estilos:

- **Realista** (por defecto): banquetas, asfalto, arriate, marcas viales, carros vistos desde arriba y
  semáforos con luces.
- **Esquemático**: el dibujo original (carriles como líneas y carros coloreados por velocidad).

Lo usa `NetCanvas.tsx`, que dibuja una vez por cuadro (rAF), con este orden:

1. `drawRoad`: fondo, banquetas, calzada, cruces, arriate y árboles, marcas viales y alumbrado de noche.
2. `drawIncidents`: tramos cerrados con rayado, conos y barrera.
3. `drawStopBars`: barra de color en la línea de alto de cada carril.
4. `CarRenderer.drawHeadlights`: haces de los faros, solo de noche.
5. `CarRenderer.draw`: sombras, carrocerías, luces de freno y calaveras.
6. `drawHeads`: semáforos físicos, solo con zoom.
7. `drawFlashes`: anillo al cambiar de fase.
8. `drawStreetLabels`, `drawBadges` y `drawCompass`, en pantalla.

## Contratos

- **`camera.ts`** (terminado; no cambiar firmas): convierte del mundo SUMO (metros, y hacia el norte) a la
  pantalla (px CSS).
  - Aplica zoom y desplazamiento de `View` y una rotación que pone el eje largo de la red en el lado largo
    del lienzo. Reforma va de norte a sur: en un lienzo ancho se dibuja horizontal con el norte a la derecha.
  - `applyWorld(g, cam, dpr)` permite dibujar en metros, incluidos anchos de línea y guiones. Invierte el
    eje y, así que el texto **siempre** va en `applyScreen`.
  - `toScreen`, `toWorld` y `screenDir` sirven para cosas de tamaño fijo en pantalla.
  - `screenAngle(cam, angSUMO)` da la rotación de un sprite dibujado apuntando hacia arriba.
  - Si el eje de la red va casi de este a oeste se desempata con el este a la derecha (lienzo ancho) o arriba
    (alto). `clampView` corre una vista para que el final de la red quede en el borde del lienzo (lo usa el
    App al acercar a un cruce).
- **`theme.ts`** (terminado): paletas `DAY` y `NIGHT`, y `palette(night)` para la transición.
  - También define `CAR_COLORS`, `CAR`, las medidas de las marcas y `LOD`, los px por metro a partir de los
    cuales se dibuja cada detalle.
  - Ningún módulo define colores sueltos: todo sale de la paleta.
- **`road.ts`, `cars.ts`, `signals.ts`**: las firmas exportadas son el contrato con `NetCanvas`. Se pueden
  agregar campos opcionales o funciones nuevas, pero no cambiar las existentes.
  - `NetCanvas` pasa los opcionales: `drawStopBars(..., pal, night)` y `drawStreetLabels(..., pal, badges)`
    con las tarjetas del cuadro anterior, para que los nombres no queden debajo.
  - Tarjetas (`drawBadges`): `SignalTracker` sigue la luz del recto de **cada aproximación**; el temporizador
    y el destello se reinician cuando cambia cualquiera (también en fases con adelanto/retraso). Si los
    sentidos de un eje no coinciden, la fila dibuja una flecha de color por sentido, orientada en pantalla.
    Hasta el primer cambio observado el temporizador muestra un guion.
  - Colocación: cada candidata se mete primero en el lienzo y se evalua donde queda (colas, semaforos,
    cruce, otras tarjetas, brújula). Lienzos de menos de 600 px de ancho o 260 px de alto usan pastillas
    compactas; si el cruce llena la vista, la tarjeta pasa a pastilla en una esquina, sin línea guía.
  - Toda función de dibujo deja el contexto en `applyScreen(g, dpr)`, con `globalAlpha = 1`,
    `globalCompositeOperation = "source-over"`, sin sombra (`shadowBlur = 0`) y sin guiones.

## Datos disponibles (`types.ts`, `network.ts`)

- **`Network`** trae:
  - `lanes`: id, edge, shape y width. En SUMO el índice 0 es el carril de la derecha y el más alto el de la
    izquierda, junto al sentido contrario en una calle dividida.
  - `edges`: id, name, from y to. En Reforma los nombres son "Avenida La Reforma", "12 calle", etc.
  - `junctions`: polígonos `shape`. En los cruces semaforizados son de unos 40 × 30 m; en los extremos son
    degenerados.
  - `tls`: id, name, x, y y `controlled`. Cada elemento de `controlled` es
    `{lane, idx[], dirs[], x, y}`: `idx` son las posiciones en la cadena de estado y `dirs[i]` la dirección
    SUMO del enlace (`s`, `l`/`L`, `r`/`R`, `t`).
  - `bbox`.
- **Estado de cada simulación:** `TickMessage.sims[k].tls[id]` es la cadena `rRgGyY` (un carácter por
  enlace; `g` es verde con cesión). `TickMessage.closed_lanes` lista los carriles cerrados y `incidents` los
  bordes con incidente. `profile` vale `"noche"` para activar el modo noche.
- **Geometría de Reforma:**
  - Los bordes `NB_*` (norte) y `SB_*` (sur) corren pegados, con unos 3.1 m entre los bordes de sus carriles
    interiores: ahí va el arriate.
  - Las calles transversales son de un sentido (`Cxx_W_in` entra desde el oeste, `Cxx_E_out` sale al este,
    etc.).
  - Todos los carriles miden 3.2 m.
  - Red de 509 × 1636 m, con 5 semáforos: C15, C14, C12, C10 y C06.
- **El mock** (`mock.ts`, modo sin backend) manda una red sin `junctions`, sin `edges` y sin `dirs`. Todo
  debe degradar con elegancia: nada de excepciones.

## Rendimiento

- Hasta 1500 vehículos por lienzo y 2 lienzos a 60 fps.
- Precalcular la geometría (`Path2D` en metros) en `build*Model` y los sprites una sola vez.
- Nada de `shadowBlur` por vehículo: el brillo se hace con sprites y `globalCompositeOperation = "lighter"`.
