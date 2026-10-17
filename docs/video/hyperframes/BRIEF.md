---
workflow: general-video
flow: automation
storyboard: no
message: "Con la misma demanda y semilla, los agentes RL bajan la espera ~40 % frente al semáforo de tiempo fijo en la Av. La Reforma (y max-pressure sigue siendo una línea base muy fuerte)."
destination: archivo-respaldo-presentacion
aspect: 1920x1080
language: es
audience: "Catedrático y compañeros de CC3104 (UVG) durante la presentación final; respaldo si la demo en vivo falla."
length: "≈4:06 (pedido 4:00–4:20 tras el mapa nuevo; antes ≈3:46), ≥75 % metraje real de la demo (86 %)"
angle: demo-documentada
narration: no
---

## Intent

Video de respaldo de la demo web en vivo del proyecto "Semáforos inteligentes en Av. La Reforma con RL
multiagente" (CC3104 Aprendizaje por Refuerzo, UVG, Guatemala). El usuario pidió (en sus palabras): "haz el
video de respaldo de la demo: córrelo, haz las diferentes pruebas de diferentes formas, al final edítalo con
HyperFrames, únelo todo en un video, agrégale títulos y cosas así, bien chilero, para que quede documentado.
Está dedicado en su mayoría a la demo." Tono: moderno, limpio, tema oscuro igual que la app; verde = RL,
ámbar/rojo = tiempo fijo. Sin voz en off. El usuario no estaba disponible: este brief lo escribió el agente a
partir del encargo (sin entrevista).

## Assets

- `Proyecto Final/video/clips/*.mp4` — grabaciones reales de la demo (Chrome headless + CDP, `scripts/record_demo.py`), copiadas a `media/` (ignorado por git) para el render. Desde el 17-10-2026 son las del **mapa nuevo** (calles realistas, carros con luces, semáforos y tarjetas por cruce, Vista/Estilo/Iluminación); las del mapa anterior quedaron en `video/v1/clips/`.
- Resultados: `runs/E1/baselines/eval.csv` y `runs/E*/**/eval.csv` del repo principal (demora total por vehículo, hora pico, 10 semillas de evaluación × 5 de entrenamiento).

## Customizations

- Tarjeta de título (~5 s), contexto del corredor con las 5 intersecciones (~9 s), segmentos de demo con barra inferior (capítulo + 1 línea de qué se hace y qué mirar), punch-ins sutiles en la zona relevante y en los KPI/mejora, tarjeta de resultados honesta (~14 s) y cierre (~5 s).
- Indicar cuando un tramo del metraje va acelerado (chip "video 2×"), para no engañar sobre la velocidad de la simulación.
- Mapa nuevo (17-10-2026): los mapas van apilados (fijo arriba, RL abajo; lado a lado solo en el cruce aislado), 8 capítulos con uno dedicado al mapa ("La calle de cerca": Vista a la 12 calle, semáforos que cambian solos con su reloj y destello, tarjetas, noche con faros, esquemático vs realista), punch-ins a los acercamientos interesantes y subtítulos que describen lo que ahora se ve (luces de freno, tarjetas, relojes de fase).

## Notes

- Música: primero el video salió en silencio (sin sesión de HeyGen). El 17-10-2026, con la sesión OAuth activa, se
  agregó una cama instrumental del catálogo de HeyGen (100 BPM, "understated electronic pulse") mezclada a
  −20 LUFS con fundidos de 2 s / 3 s; la versión sin audio se conserva. Detalle y licencia en ../README.md §5.
- Conteos de tráfico sintéticos/provisionales: decirlo en letra pequeña en la tarjeta de resultados.
- La espera en vivo de la demo (`mean_wait`) no es la métrica de evaluación (demora total por vehículo): no mezclarlas.
- Render autónomo: el usuario pidió explícitamente renderizar sin preguntar (está fuera).
- Re-edición con el mapa nuevo (17-10-2026): la cama de música se volvió a descargar (misma pista HeyGen) y se armó otra de 246 s; los videos anteriores quedaron en `video/v1/`.
- Revisión 1 (17-10-2026): se quitaron ~19 s de esperas congeladas tras cada Reiniciar ("Cargando…") y ese tiempo
  se devolvió a metraje con tráfico, así que la duración y la cama de música no cambian; la última toma de PPO empieza
  después del valor rojo de la «Mejora»; subtítulos ajustados a lo que se ve; CLI fijado en 0.8.169.
- Revisión 2 (17-10-2026): la línea de tiempo de `edl.py` se arma en cuadros enteros (había dos cuadros sueltos sin
  metraje en 0:49.43 y 2:26.97 por redondeo) y `edl.py` comprueba que ningún corte deje un cuadro vacío; chips de
  SALTO EN EL TIEMPO también en los saltos de MAPPO y DQN; espera del cruce recortada de ~2.8 s a ~1 s (el tiempo
  pasó a max-pressure y a DQN a 1× antes de PPO); punch-in de la 10a reencuadrado; subtítulo del capítulo 07
  corregido (el fijo da verde a la Reforma en un solo sentido).
