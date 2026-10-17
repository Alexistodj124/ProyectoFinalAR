# Video de respaldo de la demo (PLAN §9.3)

Video de ~4:06 que documenta la demo web en vivo (`web/`) funcionando con los modelos entrenados reales y el
**mapa nuevo** (calles realistas, carros con luces de freno y faros, un semáforo por aproximación y una tarjeta por
cruce): semáforo de tiempo fijo (mapa de arriba) contra el agente RL (mapa de abajo), misma demanda y misma semilla.
Es el plan B si la demo falla durante la presentación.

- **Archivos finales (fuera del repo, no van a git; rutas desde la raíz de `Proyecto Final/`):**
  - `video/demo_respaldo_musica.mp4`: **versión con música de fondo** (recomendada), 4:05.9 (245.93 s), 1920×1080,
    30 fps, H.264 + AAC 48 kHz estéreo, 88.5 MB; audio a −19.9 LUFS integrados, pico real −6.0 dBTP.
  - `video/demo_respaldo_musica_720p.mp4`: la misma a 1280×720 (CRF 26, AAC 128 kb/s), 23.5 MB, para
    mandar por teléfono o chat.
  - `video/demo_respaldo.mp4`: la misma imagen **sin audio** (pista de audio quitada, video copiado tal cual),
    82.3 MB.
  - `video/v1/`: los cuatro videos anteriores (mapa viejo, 3:45.5) y sus clips (`video/v1/clips/`).
- **Clips crudos:** `video/clips/*.mp4` (uno por prueba) y `video/clips/clips_log.json` (política, tiempo
  simulado final, mejora y **eventos** de cada clip: clics, zoom y reinicios en segundos desde el inicio del clip).
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
python scripts/record_demo.py --out ../video/clips                     # todos (≈12 min)
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
- Maneja **la UI real**: clics del mouse (`Input.dispatchMouseEvent`) en los botones de Modo, Vista, Hora del día,
  Velocidad, Estilo, Iluminación y Reiniciar; el deslizador de carros; la rueda del mouse para hacer zoom; clics en
  las tarjetas de los cruces; y clics sobre los carriles del mapa (modos Inyectar/Incidente) calculados con la
  geometría de `/api/network` y la misma cámara del mapa. Los `<select>` nativos no se pueden abrir en headless: el
  puntero va al select y el valor se fija como lo haría React (setter nativo + evento `change`). No se usó ningún
  comando WS paralelo.
- Headless no dibuja el cursor del sistema: el script inyecta en la página (solo durante la grabación) un
  puntero y una "onda" verde en cada clic, para que se vea qué se pulsa.
- Anota cada evento (clic, zoom listo, reinicio listo) con su segundo desde el inicio del clip en
  `clips_log.json`: son los tiempos que usa `edl.py`.
- Los cuadros JPEG se borran tras codificar (`--keep-frames` para conservarlos). Nada se escribe en el repo.

Clips (políticas = mejor semilla de cada método según `best/selection.csv`; grabados el 17-10-2026 con el mapa
nuevo, 1920×1080 a 30 fps):

| Clip | Duración | Qué graba | Política(s) |
|---|---|---|---|
| `a_mappo` | 57.8 s | Elegir MAPPO y Reiniciar desde la UI, 5× y 20×, KPIs divergen (termina en 48.4 %) | `mappo` E5/mappo/seed3 (val. 40.7) |
| `j_mapa` | 39.1 s | 1×: Vista → 12, cambios de fase en la 10a (≈5 y ≈8 s), clic en la tarjeta de la 10a, Noche, Esquemático, Realista, Día, Todo | MAPPO |
| `b_inyectar` | 39.5 s | Zoom a la entrada sur, Inyectar 40 carros en `NB_S_C15`; Vista 12 y otros 40 en `C12_W_in` | MAPPO |
| `c_hora` | 40.7 s | Todo el corredor a 20×: Pico → Mediodía → Noche (el mapa se oscurece solo) → Pico | MAPPO |
| `d_incidente` | 50.8 s | Zoom al tramo 12–10a, incidente en `NB_C12_C10` (carriles achurados, conos, barrera) y retiro | MAPPO |
| `e_comm` | 44.1 s | Reiniciar con comunicación, 20× (termina en 50.2 %) | `comm` E6/comm/seed0 (val. 42.7) |
| `i_qmix` | 38.2 s | Reiniciar con QMIX, 20× (termina en 47.8 %) | `qmix` E5/qmix/seed3 (val. 43.8) |
| `f_maxpressure` | 44.1 s | Reiniciar con max-pressure (línea base), 20× (termina en 44.8 %) | `max_pressure` |
| `h_velocidad` | 32.7 s | Pausa, Vista 12 + rueda, 1×, 5×, 20× | MAPPO |
| `g_cruce` | 65.4 s | Cambiar a `cruce_pico` (mapas lado a lado), DQN (≈45 %) y luego PPO (≈55 %) | `dqn` E4/dqn_best/seed1 (val. 25.1), `ppo` E4/ppo/seed0 (val. 29.7) |

Ojo al cortar: justo después de cada Reiniciar la tarjeta «Mejora» pasa unos segundos por valores sin sentido
(en rojo: `a_mappo` 11.6–15.2 s, llega a −72.7 %; `e_comm` 9.5–10.2; `i_qmix` 8.9–10.2; `g_cruce` con DQN 11.1–13.6
y con PPO 45.2–45.4, y entre 45.4 y 49.2 la tarjeta de PPO todavía salta de 27 a 65 %). `edl.py` corta esos tramos
y marca cada salto con el chip "SALTO EN EL TIEMPO"; en el video final se revisó la tarjeta cuadro a cuadro (píxeles
rojos en el recorte de la tarjeta) en toda la demo.
Además, cada Reiniciar deja la grabación congelada 4–6 s en "Cargando…": la edición deja ~1–1.5 s y corta dentro
del tramo congelado (cuadros idénticos) o salta con el chip "SALTO EN EL TIEMPO".

## 2. Volver a editar y renderizar

El proyecto está en `docs/video/hyperframes/` (HyperFrames 0.8.169, versión fijada en `package.json`; el
17-10-2026 `npx hyperframes@latest upgrade --project . --check` avisó que había salido la 0.8.169, se subió el pin
desde 0.8.168 con `npx hyperframes@latest upgrade --project .` y `npx hyperframes check` pasó sin hallazgos).
`index.html`, `compositions/chrome.html` y `compositions/ch01.html`–`ch08.html` los **genera `edl.py`** a partir de
la lista de edición (tomas, velocidades, subtítulos, anillos de resaltado, punch-ins, música): para cambiar un corte
o un texto se edita `edl.py` y se vuelve a correr. `title.html`, `context.html`, `results.html` y `closing.html` se
editan a mano. El metraje y la música viven en `media/` (ignorado por git).

La línea de tiempo de la EDL se arma en **cuadros enteros**: cada duración de toma tiene que ser un múltiplo de 1/30 s
(las que no son décimas redondas se escriben `F(n)`, n cuadros) y `edl.py` se niega a generar si no lo es. En el HTML
los inicios se truncan y las duraciones se redondean hacia arriba a 4 decimales, y antes de escribir `edl.py`
comprueba, con esos mismos valores, que cada cuadro de la demo tenga capítulo y cada cuadro de un capítulo tenga
metraje (un corte con una toma que termina en 14.7 s y la siguiente en 14.7333 s deja un cuadro vacío, que en el
video se ve como un parpadeo). Para revisarlo en el video final:
`ffmpeg -i video.mp4 -vf "crop=1500:800:210:100,blackdetect=d=0:pix_th=0.12:pic_th=0.97" -an -f null -` solo debe
encontrar las transiciones a propósito (título, contexto → demo, resultados, cierre).

```bash
cd docs/video/hyperframes
VID="/ruta/a/Proyecto Final/video"   # en este equipo: .../AprendizajRefuerzo/Proyecto Final/video
mkdir -p media && cp "$VID"/clips/*.mp4 media/
# música: descargar el original (ver §5) en media/bgm/heygen_0bfa4630_pulse_100bpm.wav y luego
python3 edl.py --bed                 # regenera index.html y los capítulos, arma la cama de música e imprime el guion
npx hyperframes check                # lint + runtime + layout + motion + contraste (debe pasar sin hallazgos)
npx hyperframes snapshot --at 32.6,40.6,173.0 -o /tmp/snaps   # cuadros sueltos para revisar anillos y punch-ins
npx hyperframes preview --background # Studio en http://localhost:3002 (editar ahí también sirve); --stop al terminar
npx hyperframes render -o "$VID/demo_respaldo_musica.mp4" --fps 30 --crf 20 --workers 1
# sin audio (misma imagen) y copia liviana para el teléfono
ffmpeg -i "$VID/demo_respaldo_musica.mp4" -map 0:v -c copy -movflags +faststart "$VID/demo_respaldo.mp4"
ffmpeg -i "$VID/demo_respaldo_musica.mp4" -vf scale=1280:-2 -c:v libx264 -crf 26 -preset slow -pix_fmt yuv420p \
  -c:a aac -b:a 128k -movflags +faststart "$VID/demo_respaldo_musica_720p.mp4"
```

Con poco disco libre conviene `--workers 1`: con un solo proceso HyperFrames codifica mientras captura; con varios
guarda cada cuadro en disco antes (~14 GB para este video). El render tarda ≈4.5 min en este equipo
(M4). Los avisos "sparse keyframes" de los clips no afectan el render (extrae los cuadros en orden); si molestan en
el Studio, recodificar los clips con `-g 30`.

Si se vuelven a grabar los clips, los tiempos de los eventos (clic en Reiniciar, en el carril, etc.) pueden
moverse unas décimas: revisar `edl.py` (`at("clip", segundo)`) contra los `events` de `clips_log.json` y con una
hoja de contacto (`ffmpeg -i clip.mp4 -vf "fps=1,scale=480:-1,tile=4x3" hoja.jpg`). Los rectángulos de la UI
(diccionario `UI` de `edl.py`) están en coordenadas de la grabación (1920×1080): panel derecho en x = 1653,
w = 238; mapa fijo 17,165,1610,348 y mapa RL 17,559,1610,348; en el modo Inyectar los grupos de abajo de Modo bajan
31 px y en Incidente suben 16 px.

## 3. Guion final (storyboard) con tiempos

Diseño: tema oscuro como la app (`#0b0e14`), verde `#2ee6a6` = RL, ámbar `#ff9f43` = tiempo fijo, Montserrat +
JetBrains Mono. Durante la demo el metraje va en un marco (87.5 %) con riel de 8 capítulos a la izquierda, barra
inferior (capítulo + qué se hace/qué mirar, fuera del metraje), anillos verdes sobre el control que se pulsa o la
zona del mapa que cambia, punch-ins a los acercamientos y chips que avisan cuando el video va acelerado
("VIDEO 3×") o hay un salto de tiempo. 86 % del video es metraje real de la demo.

| Tiempo | Escena | Texto en pantalla (resumen) |
|---|---|---|
| 0:00–0:05 | Título | "Semáforos inteligentes en Av. La Reforma" · "Demo en vivo · RL multiagente · CC3104 UVG" |
| 0:05–0:14.5 | Contexto | Línea del corredor con distancias reales: 15, 14, 12, 10a y 6a calle (zona 9 / zona 10, 1.65 km); "Mapa de arriba: semáforo fijo · Mapa de abajo: agente RL entrenado · misma demanda y semilla" |
| 0:14.5–0:34.7 | 01 Hora pico: fijo vs MAPPO (`a_mappo`, 1×, 2× y 3×) | Elegir MAPPO y Reiniciar (≈1.5 s de "Cargando…") → salto en el tiempo y a 5× la espera verde crece menos → a 20× las curvas se separan → punch-in a «Mejora» ≈48 % a los ~13 min simulados |
| 0:34.7–1:08.5 | 02 La calle de cerca (`j_mapa`, 1×) | Vista → 12 (anillo en Vista) → punch-in a la 12 calle y la 10a: el semáforo de la 10a cambia solo, destella y su reloj vuelve a 0 s → clic en la tarjeta de la 10a → punch-in a las dos tarjetas (el fijo da verde a la 10a calle, el agente a la Reforma) → Noche: punch-in a la fila de luces de freno → Esquemático: rojo = detenido, anillos en la cola del fijo → Realista (de noche), Día, Todo |
| 1:08.5–1:32.9 | 03 Inyectar tráfico (`b_inyectar`) | Modo Inyectar, 40 carros en la entrada sur (anillos en ese tramo de los dos mapas) y los carros entrando → Vista 12, otros 40 en la 12 calle → punch-in a la 12 calle, mejora ≈51 % |
| 1:32.9–1:55.8 | 04 Hora del día (`c_hora`, 2×, 1× y 2×) | Mediodía ≈4 800 veh/h → Noche ≈2 200 veh/h, el mapa se oscurece solo y prende los faros → casi sin colas → de vuelta a Pico |
| 1:55.8–2:27.0 | 05 Incidente (`d_incidente`) | Zoom al tramo 12–10a → Modo Incidente: 2 de 3 carriles cerrados (anillos en el tramo, punch-in a conos y barrera) → el fijo llega a ≈170 carros detenidos, el agente 70–90 → otro clic: se quitan conos y barrera y se reabren los carriles |
| 2:27.0–2:55.9 | 06 Otras políticas (`e_comm`, `i_qmix`, `f_maxpressure`) | Comm: Reiniciar → salto a 10–12 min simulados, ≈50 % · QMIX: Reiniciar → salto a 8–10 min, ≈48 % · Max-pressure (regla clásica, sin aprendizaje): ≈45 %, punch-in; "la menor demora total en la evaluación" |
| 2:55.9–3:18.6 | 07 Control de velocidad (`h_velocidad`) | Pausa + Vista 12 + rueda → 1× tiempo real, punch-in a la Reforma y la 12 calle con luces de freno (mismo instante: el fijo da verde a la Reforma en un solo sentido, el agente a la 12 calle) → 5× y 20× |
| 3:18.6–3:45.4 | 08 Cruce aislado 12 calle (`g_cruce`) | Cambiar a `cruce_pico` + DQN (≈0.5 s de "Cargando…" y 0.9 s del cruce recién cargado, mapas lado a lado) → 20× (video 2×, salto en el tiempo), la mejora sube a ≈45 % (los últimos 2.5 s antes de PPO a 1×) → PPO y Reiniciar → salto a ~2.5 min simulados: ≈55 % (oscila entre 50 y 60 %) hasta los ~7.5 min, punch-in |
| 3:45.4–4:00.4 | Resultados | Demora total por vehículo, hora pico, 10 semillas de evaluación × 5 de entrenamiento. Corredor: fijo 79.1 s, actuado 63.4 (−20 %), MAPPO 46.8 (−41 %), comm 46.2 (−42 %), QMIX con equidad 46.5 (−41 %), max-pressure 41.7 (−47 %). Cruce 12 calle: fijo 33.6 s, DQN 21.1 (−37 %), PPO 23.8 (−29 %), max-pressure 19.8 (−41 %). "Los agentes RL bajan la demora ≈40 % frente al tiempo fijo… y max-pressure sigue siendo una línea base muy fuerte". Línea de robustez (E7, MAPPO de la demo, 10 semillas): con el incidente 12→10a 165 s vs 198 s del fijo (−17 %); con +30 % de demanda no generaliza (373 vs 346 s; comm sí: 282 s). Letra pequeña: conteos sintéticos/provisionales; la espera en vivo no es esta métrica |
| 4:00.4–4:05.9 | Cierre | "CC3104 Aprendizaje por Refuerzo · UVG · 2026" · github.com/Alexistodj124/ProyectoFinalAR |

Las cifras de resultados se volvieron a calcular desde `runs/E1/baselines/eval.csv` y `runs/E*/**/eval.csv`
(promedio de `total_delay`) el 17-10-2026; la línea de robustez sale de `runs/E7/robustness.csv` (E7 terminó
durante la edición: `marl_best` = E5/mappo/seed3, la misma corrida de la demo; `comm_best` = E6/comm/seed0).
Las mejoras en vivo de los subtítulos son las que muestra la tarjeta «Mejora» en el cuadro correspondiente.

## 4. Pruebas de la demo (17-10-2026, backend real, semilla 1000)

Backend desde este worktree con `WEB_RUNS_DIR` = `runs/` del repo principal; pruebas por WebSocket (cliente propio)
y por la UI (Chrome headless). "Mejora" = (espera fijo − espera RL) / espera fijo, métrica en vivo de la demo.
(Estas pruebas son de la primera grabación; los clips del mapa nuevo dan valores parecidos, ver la tabla de §1.)

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
- El panel de abajo dice "Agente RL · Max-pressure" aunque max-pressure no aprende; el video lo aclara con texto.
- En `clips_log.json` hay mejoras de 43–56 % según el momento; los resultados oficiales son los de la tarjeta final.

## 5. Notas

- **Música de fondo (versión `demo_respaldo_musica*.mp4`).** Fuente: catálogo de audio de **HeyGen**
  (`GET https://api.heygen.com/v3/audio/sounds?type=music`, búsqueda "downtempo electronic 100 bpm subtle beat
  data technology"), pista `0bfa4630ecda4bf79874e858869ed93e`, "Astral Generated Music: 0bfa4630" (música
  generada por IA de HeyGen; descripción del catálogo: "understated electronic pulse, 100 BPM, professional and
  technical"), WAV de 122 s, 44.1 kHz estéreo, instrumental. Descargada con la sesión OAuth de HeyGen del usuario
  (plan FREE; la búsqueda y la descarga no pidieron créditos); la primera vez el 17-10-2026 y otra vez el mismo día
  para la versión del mapa nuevo (el WAV anterior se había perdido). Original en
  `docs/video/hyperframes/media/bgm/heygen_0bfa4630_pulse_100bpm.wav` (ignorado por git).
  - **Licencia:** la respuesta de la API no trae un campo de licencia. El uso queda sujeto a los Términos de
    Servicio de HeyGen de la cuenta que la descargó; no se encontró un texto público específico de licencia para
    la biblioteca de música. Para la presentación del curso no hay problema práctico, pero **antes de publicar el
    video o usarlo comercialmente hay que confirmarlo en heygen.com** (o usar la versión sin audio).
  - **Cómo se obtiene:** `npx hyperframes media-use resolve --type bgm` necesita el CLI `heygen`, que no está
    instalado. Se usa la librería del motor de audio de la misma skill
    (`~/.claude/skills/media-use/audio/scripts/lib/heygen.mjs`: `searchSounds(query, "music", heygenAuthHeaders(),
    {limit: 50})`, buscar el resultado con ese `id` y `downloadTo(audio_url, destino)`), que usa directamente la
    credencial de `~/.heygen/credentials`. No se instala nada.
  - **Estructura del tema:** 100 BPM, secciones de 8 compases (19.2 s): intro suave [0, 19.2) a ≈−32 dBFS RMS,
    subida [19.2, 38.4) a ≈−25, tema completo [38.4, 115.2) a ≈−15 (con la parte más fuerte en [76.8, 96)), y el
    golpe final en 115.2 con ~1 s de cola.
  - **Cama de 246.04 s:** con ffmpeg (muestras exactas a 44.1 kHz) se unen `[24.0, 115.2)` + `[38.4, 115.2)` +
    `[38.4, 116.6)` con cruces de 80 ms (`atrim` + `acrossfade`, curvas triangulares). Así la entrada fuerte del
    tema cae en t = 14.4 s, cuando aparece el metraje de la demo; las uniones caen en inicios de sección (91.12 s y
    167.84 s, sin clics: el salto máximo entre muestras en la unión es igual al del resto del tema); el último
    cambio de sección (fuente 96.0) cae en t = 225.44 s, donde empieza la tarjeta de resultados (225.43 s), y el
    golpe final en t = 244.64 s, dentro del cierre. `python3 edl.py --bed` la arma (constantes `BED_PIECES`):
    ```bash
    ffmpeg -i media/bgm/heygen_0bfa4630_pulse_100bpm.wav -filter_complex \
      "[0:a]atrim=start_sample=1058400:end_sample=5080320,asetpts=PTS-STARTPTS[p0];\
       [0:a]atrim=start_sample=1693440:end_sample=5080320,asetpts=PTS-STARTPTS[p1];\
       [0:a]atrim=start_sample=1693440:end_sample=5142060,asetpts=PTS-STARTPTS[p2];\
       [p0][p1]acrossfade=d=0.08:c1=tri:c2=tri[x1];[x1][p2]acrossfade=d=0.08:c1=tri:c2=tri[out]" \
      -map "[out]" -c:a pcm_s16le media/bgm/bed_reforma_246s.wav
    ```
  - **Mezcla** (en `edl.py` → `<audio id="music-bed">` de `index.html`, con `/hyperframes-audio`): etapa `gain`
    de −6 dB en `data-fx-chain` y una línea de volumen en `data-automation`: fundido de entrada de 2 s, baja a 0.63
    (≈ −4 dB) bajo la tarjeta de resultados para leer tranquilo, y fundido de salida de 3 s al final. Resultado
    medido en el video final con `ffmpeg -af ebur128=peak=true`: −19.9 LUFS integrados, LRA 5.8 LU, pico
    real −6.0 dBTP.
- `npx hyperframes usage --json` devolvió `{"status":"unknown","reason":"unsupported_auth"}` (uso desconocido).
- La app de escritorio de HyperFrames ("Framey") permite seguir editando por chat: `npx hyperframes open .` desde
  `docs/video/hyperframes/`.
