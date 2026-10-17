---
message: "Con la misma demanda y semilla, los agentes RL bajan la espera ~40 % frente al semáforo de tiempo fijo en la Av. La Reforma (y max-pressure sigue siendo una línea base muy fuerte)."
audience: "CC3104 (UVG), presentación final"
mode: autonomous
canvas: 1920x1080
fps: 30
duration: 245.93
---

# Storyboard — Demo de respaldo (mapa nuevo)

Arco: título → contexto (qué se compara) → 8 capítulos de demo real (cada uno: qué se hace + qué mirar) →
resultados honestos → cierre. Ritmo: tarjetas cortas, metraje 86 %. Duración: la manda el metraje (EDL en `edl.py`).
Los tiempos exactos de cada toma, subtítulo y chip los imprime `python3 edl.py`; el guion completo con tiempos está en
`../README.md` §3. En el corredor los mapas van apilados (fijo arriba, RL abajo); en el cruce aislado, lado a lado.

## Frame 1
status: built
src: compositions/title.html
time: 0–5 s
shape: blueprint `titlecard-reveal` (una revelación contenida + quietud), semáforo rojo→amarillo→verde
beat: "Semáforos inteligentes en Av. La Reforma" · "Demo en vivo · RL multiagente · CC3104 UVG"

## Frame 2
status: built
src: compositions/context.html
time: 5–14.5 s
shape: rules `svg-path-draw` (corredor) + `waterfall-entry` (estaciones) + `scale-swap-transition` (tarjetas fijo/RL)
beat: 5 intersecciones con distancias reales (15, 14, 12, 10a, 6a calle; zona 9/10); mapa de arriba = fijo, mapa de abajo = RL, misma demanda y semilla

## Frame 3
status: built
src: compositions/chrome.html (marco, riel de 8 capítulos, EN VIVO) + compositions/ch01.html … ch08.html
time: 14.5–225.43 s
shape: metraje real con rules `viewport-change` (punch-ins a «Mejora» y a acercamientos del mapa), `waterfall-entry` (barra inferior), anillos de resaltado sobre el control pulsado o la zona del mapa que cambia
beat: 01 MAPPO · 02 La calle de cerca (Vista 12, semáforos que cambian solos con reloj y destello, tarjetas, noche con faros, esquemático vs realista) · 03 Inyectar · 04 Hora del día (la noche oscurece el mapa sola) · 05 Incidente (carriles achurados, conos y barrera) · 06 comm/QMIX/max-pressure · 07 Velocidad (1× con luces de freno de cerca) · 08 Cruce DQN/PPO (lado a lado)

## Frame 4
status: built
src: compositions/results.html
time: 225.43–240.43 s
shape: rules `stat-bars-and-fills` + `counting-dynamic-scale` (barras con conteo)
beat: demora total por vehículo, 10×5 semillas; corredor y cruce; RL ≈−40 % vs fijo; max-pressure muy fuerte; conteos sintéticos

## Frame 5
status: built
src: compositions/closing.html
time: 240.43–245.93 s
shape: blueprint `titlecard-reveal` (variante de cierre) + fundido a negro
beat: "CC3104 Aprendizaje por Refuerzo · UVG · 2026" · github.com/Alexistodj124/ProyectoFinalAR
