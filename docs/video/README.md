# Video de respaldo de la demo (PLAN §9.3)

Video de ~3:46 que documenta la demo web en vivo (`web/`) funcionando con los modelos entrenados reales:
semáforo de tiempo fijo (izquierda) contra el agente RL (derecha), misma demanda y misma semilla. Es el
plan B si la demo falla durante la presentación.

- **Archivo final (fuera del repo, no va a git):** `../video/demo_respaldo.mp4` (desde la raíz de
  `Proyecto Final/`), 3:45.5, 1920×1080, 30 fps, H.264, 40.1 MB (38.2 MiB), sin audio (decisión deliberada, ver
  "Notas").
- **Clips crudos:** `../video/clips/*.mp4` (uno por prueba) y `../video/clips/clips_log.json` (política,
  tiempo simulado final y mejora de cada clip).
- **Fuentes de la edición (sí van a git):** `docs/video/hyperframes/` (proyecto de HyperFrames).
- **Grabador:** `scripts/record_demo.py`.

## 1. Volver a grabar los clips

Todo con el backend real y los modelos de `runs/` (en este equipo, los del repo principal):

```bash
# terminal 1: frontend compilado + backend (NO exportar LIBSUMO_AS_TRACI)
cd web/frontend && npm install && npm run build && cd ../..
source scripts/env.sh
WEB_RUNS_DIR="/ruta/a/ProyectoFinalAR/runs" python -m uvicorn web.backend.app:app --port 8000

# terminal 2: grabar
source scripts/env.sh
python scripts/record_demo.py --list                                   # clips disponibles
python scripts/record_demo.py --out ../video/clips                     # todos (≈10 min)
python scripts/record_demo.py --out ../video/clips --clips d_incidente # uno solo
python scripts/record_demo.py --screenshot /tmp/demo.png               # solo una captura
```

Cómo funciona `record_demo.py`:

- Abre Google Chrome **headless** (`--headless=new`, 1920×1080, `--force-device-scale-factor=1`,
  `--hide-scrollbars`) y lo maneja con el **Chrome DevTools Protocol** usando el paquete `websockets` del venv
  (sin Playwright ni Puppeteer).
- Espera a que la página esté **en vivo** (sin el aviso "MODO DEMO SIN BACKEND" y con KPIs numéricos) y graba
  con `Page.startScreencast` (JPEG calidad 88, se confirma cada cuadro), guardando cada cuadro con su marca de
  tiempo. Al terminar, ffmpeg arma un MP4 H.264 a **30 fps constantes** con el demuxer `concat` (duración real de
  cada cuadro) + `-vf fps=30`. La captura sale a ~28 fps.
- Maneja **la UI real**: clics del mouse (`Input.dispatchMouseEvent`) en los botones de Modo, Hora del día,
  Velocidad y Reiniciar; el deslizador de carros; la rueda del mouse para hacer zoom; y clics sobre los carriles
  del mapa (modos Inyectar/Incidente) calculados con la geometría de `/api/network` y la misma transformación de
  `NetCanvas`. Los `<select>` nativos no se pueden abrir en headless: el puntero va al select y el valor se fija
  como lo haría React (setter nativo + evento `change`). No se usó ningún comando WS paralelo.
- Headless no dibuja el cursor del sistema: el script inyecta en la página (solo durante la grabación) un
  puntero y una "onda" verde en cada clic, para que se vea qué se pulsa.
- Los cuadros JPEG se borran tras codificar (`--keep-frames` para conservarlos). Nada se escribe en el repo.

Clips (políticas = mejor semilla de cada método según `best/selection.csv`):

| Clip | Qué graba | Política(s) |
|---|---|---|
| `a_mappo` | Reiniciar desde la UI, 5× y 20×, KPIs divergen | `mappo` E5/mappo/seed3 (val. 40.7) |
| `b_inyectar` | Zoom a la mitad sur, Inyectar 40 carros en `NB_S_C15` y en `C12_W_in` | MAPPO |
| `c_hora` | Pico → Mediodía → Noche → Pico a 20× | MAPPO |
| `d_incidente` | Zoom al tramo 12–10a, incidente en `NB_C12_C10` on/off | MAPPO |
| `e_comm` | Reiniciar con comunicación, 20× | `comm` E6/comm/seed0 (val. 42.7) |
| `f_maxpressure` | Reiniciar con max-pressure (línea base), 20× | `max_pressure` |
| `i_qmix` | Reiniciar con QMIX, 20× | `qmix` E5/qmix/seed3 (val. 43.8) |
| `h_velocidad` | Pausa, zoom a Reforma y 12 calle, 1×, 5×, 20× | MAPPO |
| `g_cruce` | Cambiar a `cruce_pico`, DQN y luego PPO | `dqn` E4/dqn_best/seed1 (val. 25.1), `ppo` E4/ppo/seed0 (val. 29.7) |

## 2. Volver a editar y renderizar

El proyecto está en `docs/video/hyperframes/` (HyperFrames 0.8.168, versión fijada en `package.json`).
`index.html`, `compositions/chrome.html` y `compositions/ch01.html`–`ch07.html` los **genera `edl.py`** a partir de
la lista de edición (tomas, velocidades, subtítulos, anillos de resaltado, punch-ins): para cambiar un corte o un
texto se edita `edl.py` y se vuelve a correr. `title.html`, `context.html`, `results.html` y `closing.html` se
editan a mano. El metraje vive en `media/` (ignorado por git).

```bash
cd docs/video/hyperframes
mkdir -p media && cp ../../../../video/clips/*.mp4 media/   # (rutas de este equipo; o copiar a mano)
python3 edl.py                       # regenera index.html y los capítulos, imprime el guion con tiempos
npx hyperframes check                # lint + runtime + layout + motion + contraste (debe pasar sin hallazgos)
npx hyperframes preview --background # Studio en http://localhost:3002 (editar ahí también sirve); --stop al terminar
npx hyperframes render -o ../../../../video/demo_respaldo.mp4 --fps 30 --crf 20 --workers 4
```

Si se vuelven a grabar los clips, los tiempos de los eventos (clic en Reiniciar, en el carril, etc.) pueden
moverse unas décimas: revisar `edl.py` (`at("clip", segundo)`) con una hoja de contacto
(`ffmpeg -i clip.mp4 -vf "fps=1,scale=480:-1,tile=8x6" hoja.jpg`).

## 3. Guion final (storyboard) con tiempos

Diseño: tema oscuro como la app (`#0b0e14`), verde `#2ee6a6` = RL, ámbar `#ff9f43` = tiempo fijo, Montserrat +
JetBrains Mono. Durante la demo el metraje va en un marco (87.5 %) con riel de capítulos a la izquierda, barra
inferior (capítulo + qué se hace/qué mirar), anillos verdes sobre el control que se pulsa y chips que avisan cuando
el video va acelerado ("VIDEO 3×") o hay un salto de tiempo. 84 % del video es metraje real de la demo.

| Tiempo | Escena | Texto en pantalla (resumen) |
|---|---|---|
| 0:00–0:05 | Título | "Semáforos inteligentes en Av. La Reforma" · "Demo en vivo · RL multiagente · CC3104 UVG" |
| 0:05–0:14.5 | Contexto | Línea del corredor con distancias reales: 15, 14, 12, 10a y 6a calle (zona 9 / zona 10, 1.65 km); "Izquierda: semáforo de tiempo fijo · Derecha: agente RL entrenado · misma demanda y semilla" |
| 0:14.5–0:42.5 | 01 Hora pico — fijo vs MAPPO (`a_mappo`, 1× y luego 3×) | Elegir MAPPO y Reiniciar → a 5× la espera verde crece menos → a 20× las curvas se separan → punch-in a «Mejora» ≈47 % |
| 0:42.5–1:06.5 | 02 Inyectar tráfico (`b_inyectar`) | Modo Inyectar, 40 carros en la entrada sur → otros 40 en la 12 calle (anillos en la 12 calle) → la mejora se mantiene ≈50 % |
| 1:06.5–1:26.5 | 03 Hora del día (`c_hora`, 2×) | Mediodía ≈4 800 veh/h → Noche ≈2 200 veh/h → de vuelta a Pico |
| 1:26.5–1:56.1 | 04 Incidente (`d_incidente`) | Zoom con la rueda al tramo 12–10a → incidente: 2 de 3 carriles rectos cerrados (anillos en el tramo) → cola menor del lado RL → se retira y la cola se disipa |
| 1:56.1–2:32.1 | 05 Otras políticas (`e_comm`, `i_qmix`, `f_maxpressure`) | Comm: Reiniciar → salto a ~12 min, ≈48 % · QMIX: Reiniciar → salto a ~10 min, ≈48 % · Max-pressure (regla clásica): ≈44 %, punch-in; "la menor demora total en la evaluación" |
| 2:32.1–2:55.5 | 06 Control de velocidad (`h_velocidad`) | Pausa + zoom a Reforma y 12 calle → 1× tiempo real (barras = luz de cada carril) → 5× y 20× |
| 2:55.5–3:25.0 | 07 Cruce aislado 12 calle (`g_cruce`) | Cambiar a `cruce_pico` + DQN → 20× → PPO → "más de 50 % menos espera en vivo", punch-in |
| 3:25.0–3:40.0 | Resultados | Demora total por vehículo, hora pico, 10 semillas de evaluación × 5 de entrenamiento. Corredor: fijo 79.1 s, actuado 63.4 (−20 %), MAPPO 46.8 (−41 %), comm 46.2 (−42 %), QMIX con equidad 46.5 (−41 %), max-pressure 41.7 (−47 %). Cruce 12 calle: fijo 33.6 s, DQN 21.1 (−37 %), PPO 23.8 (−29 %), max-pressure 19.8 (−41 %). "Los agentes RL bajan la demora ≈40 % frente al tiempo fijo… y max-pressure sigue siendo una línea base muy fuerte". Línea de robustez (E7, MAPPO de la demo, 10 semillas): con el incidente 12→10a 165 s vs 198 s del fijo (−17 %); con +30 % de demanda no generaliza (373 vs 346 s; comm sí: 282 s). Letra pequeña: conteos sintéticos/provisionales; la espera en vivo no es esta métrica |
| 3:40.0–3:45.5 | Cierre | "CC3104 Aprendizaje por Refuerzo · UVG · 2026" · github.com/Alexistodj124/ProyectoFinalAR |

Las cifras de resultados se volvieron a calcular desde `runs/E1/baselines/eval.csv` y `runs/E*/**/eval.csv`
(promedio de `total_delay`) el 17-10-2026; la línea de robustez sale de `runs/E7/robustness.csv` (E7 terminó
durante la edición: `marl_best` = E5/mappo/seed3, la misma corrida de la demo; `comm_best` = E6/comm/seed0).

## 4. Pruebas de la demo (17-10-2026, backend real, semilla 1000)

Backend desde este worktree con `WEB_RUNS_DIR` = `runs/` del repo principal; pruebas por WebSocket (cliente propio)
y por la UI (Chrome headless). "Mejora" = (espera fijo − espera RL) / espera fijo, métrica en vivo de la demo.

**Comparaciones en `reforma_pico` (mejora a 2.5 / 5 / 10 / 15 min simulados):**

| Política | 2.5 min | 5 min | 10 min | 15 min | Espera fijo / RL a 15 min (s) |
|---|---|---|---|---|---|
| MAPPO E5/mappo/seed3 | 65.8 % | 50.9 % | 48.1 % | 47.2 % | 47.2 / 25.0 |
| comm E6/comm/seed0 | 53.9 % | 50.3 % | 50.6 % | 47.8 % | 47.3 / 24.7 |
| QMIX E5/qmix/seed3 | 55.9 % | 49.1 % | 47.8 % | 47.1 % | 47.3 / 25.0 |
| max-pressure | 55.9 % | 46.6 % | 47.1 % | 43.0 % | 47.2 / 26.9 |

**`cruce_pico`:** DQN E4/dqn_best/seed1 43.8 / 38.4 / 45.9 / 52.0 %; PPO E4/ppo/seed0 59.3 / 51.1 / 54.9 / 56.9 %.

**Comandos (todos OK, aplicados a las dos sims):**

- `inject` 40 carros en `NB_S_C15` y en `C12_W_in`: ack con 40 vehículos; la cola sube en ambos lados (por WS, a
  los 2 min simulados, la mejora bajó de 72.7 % a 58.4 % en el minuto siguiente; en el clip, inyectando a los 4 min,
  se mantuvo ≈50 %).
- `time_of_day`: pico 7 352 veh/h → mediodía 4 788 → noche 2 206 → pico. Correcto; la espera promedio cambia
  despacio porque es acumulada.
- `incident` en `NB_C12_C10` on/off: cierra los carriles rectos (queda la bahía izquierda), la cola crece aguas
  arriba (cola 154 vs 106 a los 2 min) y al retirarlo se disipa.
- `speed` 0 / 1 / 5 / 20 → 0.00 / ≈1 / 5.00 / 19.99 s simulados por segundo real (incluso con otro proceso usando
  2 núcleos y MAPPO decidiendo).
- `reset` con escenario + política: 4–6 s. Una corrida de otra red (DQN en `reforma_pico`) se rechaza con un error
  claro y la simulación anterior sigue; un borde inexistente en `inject` también se rechaza.
- `python -m pytest -q tests/test_web_backend.py`: **15 passed** (antes y después de los arreglos).

**Bugs encontrados y corregidos (`web/`):**

1. *Cambiar de escenario y pulsar Reiniciar mandaba la política anterior.* Al pasar de `reforma_pico` (con MAPPO) a
   `cruce_pico`, el `<select>` mostraba "Max-pressure" pero el estado de React seguía con MAPPO, y Reiniciar fallaba
   con "se entreno en reforma_pico y no sirve para cruce_pico". Arreglo en `web/frontend/src/App.tsx`: si la lista
   de políticas cambia y la elegida ya no está, se usa la primera (la que el select muestra). Verificado en la UI.
2. *La última etiqueta del eje X de las gráficas ("10m") salía cortada* en el borde derecho
   (`web/frontend/src/LineChart.tsx`, se alinea a la derecha).
3. *Documentación desactualizada en `web/README.md`:* las demandas (decía pico ≈6 250, mediodía ≈4 200, noche ≈1 900;
   son ≈7 350 / 4 800 / 2 200 en el corredor y ≈4 900 en el cruce) y la nota de ensayo (decía que la ventaja de
   max-pressure caía a ≈3 % a los 10 min; ahora se mantiene en ≈43–47 %).

**Puntos débiles observados (no se tocaron):**

- La tarjeta y las curvas usan la espera en vivo (acumulada), que arranca muy alta los primeros minutos (60–70 %)
  y no se parece a la demora total de la evaluación (≈40 %): en el video se aclara.
- El panel derecho dice "Agente RL · Max-pressure" aunque max-pressure no aprende; el video lo aclara con texto.
- En el modo Incidente, el resaltado rojo del carril cerrado casi no se ve debajo de la cola; se ve la cola.
- A zoom 1 el corredor es una franja angosta (1.6 km de alto); para inyectar y para el incidente se hizo zoom con la
  rueda.
- En `clips_log.json` hay mejoras de 43–56 % según el momento; los resultados oficiales son los de la tarjeta final.

## 5. Notas

- Música: no hay sesión de HeyGen y el motor local de música no tiene dependencias (no se instala nada en el venv
  compartido), así que el video va en silencio a propósito.
- `npx hyperframes usage --json` devolvió `status: unknown` (uso desconocido).
- La app de escritorio de HyperFrames ("Framey") permite seguir editando por chat: `npx hyperframes open .` desde
  `docs/video/hyperframes/`.
