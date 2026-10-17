---
workflow: general-video
flow: automation
storyboard: no
message: "Con la misma demanda y semilla, los agentes RL bajan la espera ~40 % frente al semáforo de tiempo fijo en la Av. La Reforma (y max-pressure sigue siendo una línea base muy fuerte)."
destination: archivo-respaldo-presentacion
aspect: 1920x1080
language: es
audience: "Catedrático y compañeros de CC3104 (UVG) durante la presentación final; respaldo si la demo en vivo falla."
length: "≈3:30 (rango pedido 2.5–4 min, ≥75 % metraje real de la demo)"
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

- ../../../../video/clips/*.mp4 — grabaciones reales de la demo (Chrome headless + CDP, `scripts/record_demo.py`), copiadas a `media/` (ignorado por git) para el render.
- Resultados: `runs/E1/baselines/eval.csv` y `runs/E*/**/eval.csv` del repo principal (demora total por vehículo, hora pico, 10 semillas de evaluación × 5 de entrenamiento).

## Customizations

- Tarjeta de título (~5 s), contexto del corredor con las 5 intersecciones (~9 s), segmentos de demo con barra inferior (capítulo + 1 línea de qué se hace y qué mirar), punch-ins sutiles en la zona relevante y en los KPI/mejora, tarjeta de resultados honesta (~14 s) y cierre (~5 s).
- Indicar cuando un tramo del metraje va acelerado (chip "video 2×"), para no engañar sobre la velocidad de la simulación.

## Notes

- Música: opcional solo si se resolvía sin autenticación paga. `hyperframes auth status`: sin sesión de HeyGen y el motor local (MusicGen) sin dependencias (no se permite pip install en el venv compartido) → video en silencio, decisión deliberada.
- Conteos de tráfico sintéticos/provisionales: decirlo en letra pequeña en la tarjeta de resultados.
- La espera en vivo de la demo (`mean_wait`) no es la métrica de evaluación (demora total por vehículo): no mezclarlas.
- Render autónomo: el usuario pidió explícitamente renderizar sin preguntar (está fuera).
