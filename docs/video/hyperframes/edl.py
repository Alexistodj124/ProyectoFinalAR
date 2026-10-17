#!/usr/bin/env python3
"""Genera index.html (composición raíz de HyperFrames) a partir de la lista de edición (EDL).

    python3 edl.py            # escribe index.html, chrome.html y ch01–ch08.html e imprime el guion con tiempos
    python3 edl.py --bed      # además arma la cama de música media/bgm/bed_reforma_246s.wav con ffmpeg

Cada capítulo es una lista de tomas (clip, inicio en el clip, duración en el video, velocidad).
Los subtítulos, anillos de resaltado, chips y punch-ins se anclan a tiempos del clip original
(`at(...)`), así que si cambia una toma todo lo demás se recalcula solo.
Los clips viven en media/ (copiados de ../../../../video/clips, ignorados por git). Los tiempos de los
eventos de cada clip (clics, zoom, reinicios) están en ../../../../video/clips/clips_log.json.
"""
from __future__ import annotations

import html
import json
import math
import subprocess
import sys
from pathlib import Path

FPS = 30
TITLE_DUR, CONTEXT_DUR, RESULTS_DUR, CLOSING_DUR = 5.0, 9.5, 15.0, 5.5

# Música de fondo (HeyGen "Astral Generated Music: 0bfa4630", 100 BPM; ver ../README.md §5).
# El tema tiene secciones de 8 compases (19.2 s): intro suave [0, 19.2), subida [19.2, 38.4), tema completo
# [38.4, 115.2) y final en 115.2 (cola de ~1 s). La cama une, con cruces de 80 ms en inicios de sección:
#   [24.0, 115.2) + [38.4, 115.2) + [38.4, 116.6)  ->  246.04 s
# La entrada fuerte (fuente 38.4) cae en t = 14.4 s, cuando entra el metraje de la demo; las uniones en 91.12 s y
# 167.84 s; el último cambio de sección (fuente 96.0) cae en t = 225.44 s, justo donde empieza la tarjeta de
# resultados, y el golpe final del tema (fuente 115.2) en t = 244.64 s, dentro del cierre. Por eso la demo dura
# 210.93 s: si se acorta o alarga una toma hay que compensarlo en otra (o quitar/agregar secciones enteras de
# 19.2 s a la cama) para que los resultados sigan empezando en 14.4 + 19.2·n − 0.16 s.
MUSIC_WAV = "media/bgm/heygen_0bfa4630_pulse_100bpm.wav"
MUSIC_SRC = "media/bgm/bed_reforma_246s.wav"
BED_PIECES = [(24.0, 115.2), (38.4, 115.2), (38.4, 116.6)]
BED_XFADE, BED_SR = 0.08, 44100
MUSIC_GAIN_DB = -6.0   # nivel fijo (etapa gain del data-fx-chain): ~-20 LUFS integrados en el video
MUSIC_FADE_IN, MUSIC_FADE_OUT, MUSIC_DIP = 2.0, 3.0, 0.63  # dip ~-4 dB bajo la tarjeta de resultados

DEMO_START = TITLE_DUR + CONTEXT_DUR
FOOT_SCALE = 0.875  # 1920x1080 -> 1680x945 dentro del marco
FRAME_X, FRAME_Y, FRAME_W, FRAME_H = 120, 22, 1680, 945

# Rectángulos (x, y, w, h) en coordenadas de la grabación (1920x1080). Mapas apilados: fijo arriba
# (lienzo 17,165,1610,348), RL abajo (17,559,1610,348); en el cruce aislado van lado a lado.
UI = {
    # encabezado y panel derecho
    "mejora": (1575, 18, 320, 100),         # tarjeta 1569,12,335,108, ajustada para que el anillo no toque el borde
    "kpis": (530, 12, 1028, 108),
    "modo_iny": (1653, 143, 238, 144),      # Modo con el deslizador de carros (modo Inyectar)
    "modo_inc": (1653, 143, 238, 97),       # Modo en modo Incidente
    "vista": (1653, 270, 238, 56),
    "vista_iny": (1653, 301, 238, 56),      # en Inyectar todo lo de abajo de Modo baja 31 px
    "hora": (1653, 340, 238, 96),
    "velocidad": (1653, 450, 238, 59),
    "selects": (1653, 523, 238, 171),       # Escenario + Política + Reiniciar
    "pol_reset": (1653, 588, 238, 106),     # Política + Reiniciar
    "estilo": (1653, 708, 238, 59),
    "luz": (1653, 781, 238, 59),
    # j_mapa (Vista 12): tarjeta de la 10a en el mapa RL; (Vista 10a): carriles al norte de la 10a
    "card10_rl": (1378, 615, 144, 60),
    "cola10_fijo": (872, 304, 282, 46),
    "cola10_rl": (872, 698, 282, 46),
    # b_inyectar: entrada sur de la Reforma (NB_S_C15, zoom con la rueda) y 12 calle de entrada (C12_W_in, Vista 12)
    "sur_fijo": (20, 266, 525, 145),
    "sur_rl": (20, 660, 525, 145),
    "c12_fijo": (764, 168, 72, 132),
    "c12_rl": (764, 562, 72, 132),
    # d_incidente: tramo NB_C12_C10 (carriles cerrados)
    "tramo_fijo": (508, 332, 1036, 46),
    "tramo_rl": (508, 726, 1036, 46),
    # zonas para punch-ins (se centra el rectángulo; el encuadre no se sale del metraje)
    "z_10a_fijo": (980, 239, 240, 200),     # 12 calle a la izquierda, tarjeta y semáforo de la 10a a la derecha (Vista 12);
                                            # a 1.8x el borde derecho cae en x≈1633, donde termina el lienzo (no se ve el panel)
    "z_10a_ambos": (600, 205, 226, 480),    # las dos tarjetas de la 10a (Vista 10a)
    "z_10a_norte": (800, 290, 400, 500),    # salida norte de la 10a en los dos mapas (Vista 10a)
    "z_c12_ambos": (700, 300, 240, 470),    # 12 calle en los dos mapas (b_inyectar, Vista 12)
    "z_incidente": (500, 330, 400, 430),    # inicio del tramo cerrado: conos y barrera
    "z_12_ambos": (500, 300, 400, 480),     # Reforma y 12 calle de cerca (h_velocidad)
}


def r2(x: float) -> float:
    return round(x * FPS) / FPS


def F(n: int) -> float:
    """Duración de `n` cuadros (para tomas que no duran un número redondo de décimas)."""
    return n / FPS


# Tiempos que se escriben en los data-start/data-duration: los inicios se truncan y las duraciones se redondean
# hacia arriba a 4 decimales, así un clip nunca empieza después de su cuadro ni termina antes del cuadro en que
# empieza el siguiente (una toma que termina en 14.7 y otra que empieza en 14.7333 dejan un cuadro vacío).
def fl(x: float) -> str:
    return f"{math.floor(x * 1e4 + 1e-6) / 1e4:.4f}".rstrip("0").rstrip(".")


def ce(x: float) -> str:
    return f"{math.ceil(x * 1e4 - 1e-6) / 1e4:.4f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- EDL
# (etiqueta del riel, título del capítulo, [(clip, inicio_en_clip, duración_en_video, velocidad), ...])
# Esperas de Reiniciar: la grabación queda congelada en "Cargando…" 4–6 s (freezedetect). Se dejan ~1–1.5 s y se
# corta dentro del tramo congelado (cuadros idénticos, PSNR > 54 dB: el corte no se ve) o se salta con el chip
# SALTO EN EL TIEMPO. Los ~20 s ganados se devolvieron a metraje con tráfico (Inyectar, Incidente, comm, QMIX,
# max-pressure, DQN, PPO, el cambio a Realista de noche), así que la demo sigue durando 210.93 s (6 328 cuadros).
# Cada duración tiene que ser un número entero de cuadros (F(n) = n cuadros): la línea de tiempo se arma en cuadros.
# Tramos con la «Mejora» roja que no deben salir: a_mappo 11.6–15.2, e_comm 9.5–10.2, i_qmix 8.9–10.2,
# g_cruce 11.03–13.6 (DQN) y 45.2–45.4 (PPO; entre 45.4 y 49.2 la tarjeta sube de 27 a 65 % y vuelve a 59 %).
CHAPTERS = [
    ("MAPPO", "Hora pico: fijo vs MAPPO", [
        ("a_mappo", 1.4, 3.3, 1), ("a_mappo", 7.6, 1.4, 1), ("a_mappo", 15.3, F(130), 2), ("a_mappo", 24.0, 11.2, 3)]),
    ("De cerca", "La calle de cerca", [
        ("j_mapa", 1.4, 8.6, 1), ("j_mapa", 11.3, 6.1, 1), ("j_mapa", 17.9, 7.4, 1),
        ("j_mapa", 26.0, 6.2, 1), ("j_mapa", 32.2, F(164), 1)]),
    ("Inyectar", "Inyectar tráfico", [
        ("b_inyectar", 0.8, 12.8, 1), ("b_inyectar", 13.6, 3.8, 1), ("b_inyectar", 17.4, 7.8, 2.5)]),
    ("Hora", "Hora del día", [
        ("c_hora", 1.5, 7.5, 2), ("c_hora", 16.5, 7.0, 1), ("c_hora", 23.5, 8.4, 2)]),
    ("Incidente", "Incidente en la Reforma", [
        ("d_incidente", 0.8, 10.8, 1), ("d_incidente", 11.6, 10.0, 2),
        ("d_incidente", 31.6, 5.4, 1), ("d_incidente", 37.0, F(149), 2.5)]),
    ("Políticas", "Otras políticas en el corredor", [
        ("e_comm", 1.5, 3.0, 1), ("e_comm", 36.8, 7.0, 1),
        ("i_qmix", 1.5, 3.0, 1), ("i_qmix", 30.8, 7.0, 1),
        ("f_maxpressure", 1.5, 3.0, 1), ("f_maxpressure", 37.8, F(179), 1)]),
    ("Velocidad", "Control de velocidad", [
        ("h_velocidad", 1.0, 2.0, 1), ("h_velocidad", 3.8, 12.8, 1), ("h_velocidad", 16.6, 7.9, 2)]),
    ("Cruce", "Cruce aislado: Reforma y 12 calle", [
        ("g_cruce", 1.4, 3.6, 1), ("g_cruce", 10.0, 0.9, 1), ("g_cruce", 13.8, 9.4, 2),
        ("g_cruce", 32.6, 5.1, 1), ("g_cruce", 49.5, 7.8, 2)]),
]

shots = []  # dicts con inicio global (start) y en cuadros (f0) y duración en cuadros (nf)
_f = round(DEMO_START * FPS)
for ci, (_, _, lst) in enumerate(CHAPTERS):
    for (clip, ms, dur, rate) in lst:
        nf = round(dur * FPS)
        if abs(dur * FPS - nf) > 0.01:
            raise ValueError(f"{clip} desde {ms:g} s: {dur:g} s no es un número entero de cuadros (usar F(n))")
        shots.append({"ch": ci, "clip": clip, "ms": ms, "dur": nf / FPS, "rate": rate, "start": _f / FPS,
                      "f0": _f, "nf": nf})
        _f += nf
DEMO_END_F = _f
DEMO_END = DEMO_END_F / FPS
RESULTS_START = DEMO_END
CLOSING_START = r2(RESULTS_START + RESULTS_DUR)
TOTAL = r2(CLOSING_START + CLOSING_DUR)
ch_f0 = [min(s["f0"] for s in shots if s["ch"] == ci) for ci in range(len(CHAPTERS))]
ch_f1 = ch_f0[1:] + [DEMO_END_F]
ch_start = [f / FPS for f in ch_f0]
ch_end = [f / FPS for f in ch_f1]


def at(clip: str, src_t: float, nth: int = 0) -> float:
    """Tiempo global en que se ve el segundo `src_t` del clip (en su n-ésima toma que lo contiene)."""
    hits = [s for s in shots if s["clip"] == clip and s["ms"] <= src_t <= s["ms"] + s["dur"] * s["rate"] + 1e-6]
    if len(hits) <= nth:
        raise ValueError(f"{clip} t={src_t} no está en ninguna toma")
    s = hits[nth]
    return r2(s["start"] + (src_t - s["ms"]) / s["rate"])


def shot_start(i: int) -> float:
    return shots[i]["start"]


def shot_end(i: int) -> float:
    return r2(shots[i]["start"] + shots[i]["dur"])


S = {i: (shot_start(i), shot_end(i)) for i in range(len(shots))}


def T(clip: str, k: int = 0) -> tuple[float, float]:
    """(inicio, fin) globales de la k-esima toma del clip."""
    idx = [i for i, s in enumerate(shots) if s["clip"] == clip][k]
    return S[idx]


N = len(CHAPTERS)


def kick(ci: int) -> str:
    return f"{ci + 1:02d} / {N:02d} · {CHAPTERS[ci][1].upper()}"


# Subtítulos: (inicio, fin, capítulo, texto). Van en la banda de abajo, fuera del metraje.
CAPTIONS = [
    # 01 MAPPO (a_mappo): MAPPO 2.1, Reiniciar 3.5, [corte 4.7->7.6 dentro de "Cargando…"], listo 7.9, 5x 8.4 |
    #    corte 9->15.3 (Mejora negativa) | 20x 23.1
    (ch_start[0], T("a_mappo", 2)[0], 0, "MAPPO (la mejor semilla) y Reiniciar: arriba el tiempo fijo, abajo el agente."),
    (T("a_mappo", 2)[0], T("a_mappo", 3)[0], 0, "A 5×: la espera del agente (verde) crece mucho menos que la del semáforo fijo (ámbar)."),
    (T("a_mappo", 3)[0], at("a_mappo", 45.0), 0, "A 20× las curvas de espera y de cola se separan y ya no se vuelven a juntar."),
    (at("a_mappo", 45.0), ch_end[0], 0, "Tarjeta «Mejora»: ≈48 % menos espera promedio en vivo a los ~13 min simulados."),
    # 02 La calle de cerca (j_mapa, 1x): Vista 12 2.2, cambios de fase en la 10a 5.2 y 8.2, tarjeta 12.0,
    #    Noche 18.4, Esquemático 26.4, Realista 32.3, Día 33.8, Todo 35.3
    (ch_start[1], at("j_mapa", 4.8), 1, "Vista → 12: los dos mapas vuelan juntos a la 12 calle."),
    (at("j_mapa", 4.8), T("j_mapa", 1)[0], 1, "Nadie toca nada: el semáforo de la 10a cambia solo, destella y su reloj vuelve a 0 s."),
    (T("j_mapa", 1)[0], at("j_mapa", 13.6), 1, "Clic en la tarjeta de la 10a: el mapa viaja a ese cruce."),
    (at("j_mapa", 13.6), T("j_mapa", 2)[0], 1, "Mismo instante: el fijo da verde a la 10a calle; el agente, a la Reforma."),
    (T("j_mapa", 2)[0], at("j_mapa", 20.4), 1, "Iluminación → Noche: faros, alumbrado y luces de freno."),
    (at("j_mapa", 20.4), T("j_mapa", 3)[0], 1, "De noche se nota más: arriba la fila de luces de freno en la 10a es larga; abajo, corta."),
    (T("j_mapa", 3)[0], T("j_mapa", 4)[0], 1, "Esquemático, el dibujo original: rojo = detenido. La cola del fijo en la 10a salta a la vista."),
    (T("j_mapa", 4)[0], ch_end[1], 1, "De vuelta a Realista y a Día; Vista → Todo regresa al corredor completo."),
    # 03 Inyectar (b_inyectar): zoom 1.6-2.5, Inyectar 3.3, 40 carros 4.1, clic NB_S_C15 5.2 | Vista 12 14.1,
    #    clic C12_W_in 16.4
    (ch_start[2], at("b_inyectar", 6.0), 2, "Modo Inyectar, 40 carros: zoom con la rueda y un clic en la entrada sur de la Reforma."),
    (at("b_inyectar", 6.0), T("b_inyectar", 1)[0], 2, "Los 40 carros entran a la vez en las dos simulaciones (mismo comando)."),
    (T("b_inyectar", 1)[0], T("b_inyectar", 2)[0], 2, "Vista → 12 y otro clic: 40 carros más bajando por la 12 calle."),
    (T("b_inyectar", 2)[0], ch_end[2], 2, "El agente desahoga la 12 calle antes que el fijo; la mejora se mantiene cerca de 51 %."),
    # 04 Hora del día (c_hora, todo el corredor a 20x): Mediodía 2.7, Noche 17.6, Pico 32.5
    (ch_start[3], at("c_hora", 17.4), 3, "Mediodía: la demanda baja de ≈7 350 a ≈4 800 veh/h, un perfil que el agente no vio."),
    (at("c_hora", 17.4), at("c_hora", 25.0), 3, "Noche: ≈2 200 veh/h. El mapa se oscurece solo (Iluminación en Auto) y prende los faros."),
    (at("c_hora", 25.0), at("c_hora", 32.4), 3, "Casi no hay colas: ≈20 carros detenidos arriba contra ≈10 abajo."),
    (at("c_hora", 32.4), ch_end[3], 3, "Y de regreso a la hora pico: amanece y las colas vuelven a crecer."),
    # 05 Incidente (d_incidente): zoom 1.6-2.8, Incidente 4.6, clic 5.6, 20x 9.3 | 5x 32.1, retiro 33.0, 20x 36.8
    (ch_start[4], at("d_incidente", 4.5), 4, "Zoom con la rueda al tramo de la Reforma entre la 12 y la 10a calle."),
    (at("d_incidente", 4.5), T("d_incidente", 1)[0], 4, "Modo Incidente y un clic: 2 de 3 carriles hacia el norte cerrados, con conos y barrera."),
    (T("d_incidente", 1)[0], T("d_incidente", 2)[0], 4, "Con el tramo cerrado, el fijo llega a ≈170 carros detenidos; el agente se queda en 70–90."),
    (T("d_incidente", 2)[0], ch_end[4], 4, "Otro clic retira el incidente: se quitan conos y barrera y los carriles se reabren."),
    # 06 Políticas (e_comm, i_qmix, f_maxpressure): política 1.7, Reiniciar 3.0, ~1.5 s de "Cargando…" | salto al
    #    final del clip
    (T("e_comm")[0], T("e_comm", 1)[0], 5, "Comm (E6): agentes que se mandan mensajes. Reiniciar…"),
    (T("e_comm", 1)[0], T("i_qmix")[0], 5, "…de 10 a 12 min simulados después: ≈50 % menos espera que el tiempo fijo."),
    (T("i_qmix")[0], T("i_qmix", 1)[0], 5, "QMIX (E5): valor conjunto, repartido por cruce. Reiniciar…"),
    (T("i_qmix", 1)[0], T("f_maxpressure")[0], 5, "…de 8 a 10 min simulados después: ≈48 % de mejora en vivo."),
    (T("f_maxpressure")[0], T("f_maxpressure", 1)[0], 5, "Max-pressure: regla clásica, sin aprendizaje. Reiniciar…"),
    (T("f_maxpressure", 1)[0], ch_end[5], 5, "Línea base muy fuerte: ≈45 % en vivo y la menor demora total en la evaluación."),
    # 07 Velocidad (h_velocidad): Pausa 1.5, [corte 3.0->3.8, en pausa], Vista 12 4.4, rueda 6.6-7.1, 1x 9.0,
    #    5x 18.7, 20x 25.5. Entre 12.2 y 16.6 el fijo tiene verde en la Reforma en un solo sentido (flecha ← verde y
    #    → roja en su tarjeta, reloj 20-24 s; la aproximación de la izquierda sigue en rojo con cola) y el agente en la
    #    12 calle (6-10 s); se ve en los semáforos del acercamiento.
    (ch_start[6], at("h_velocidad", 8.4), 6, "Pausa congela la simulación; Vista → 12 y la rueda del mouse acercan Reforma y 12 calle."),
    (at("h_velocidad", 8.4), at("h_velocidad", 12.2), 6, "1×: tiempo real. Los carros frenan con luces rojas en la línea de alto."),
    (at("h_velocidad", 12.2), T("h_velocidad", 2)[0], 6, "Mismo instante: el fijo da verde a la Reforma en un sentido (←); el agente, a la 12 calle."),
    (T("h_velocidad", 2)[0], ch_end[6], 6, "5× y 20×: más segundos simulados por segundo (dos SUMO en paralelo, en lock-step)."),
    # 08 Cruce (g_cruce): cruce_pico 1.7, DQN 3.0, Reiniciar 4.3, ~0.5 s de "Cargando…" [corte 5.0->10.0: lado a
    #    lado desde 8.5, listo y quieto hasta el 20x de 10.2] | corte 10.9->13.8 (Mejora negativa desde 11.03; SALTO
    #    EN EL TIEMPO) | 1x desde 32.6 (DQN 46 -> 44 %), PPO 35.1, Reiniciar 36.4, ~1.3 s de "Cargando…" | salto a
    #    49.5 (desde ahí la tarjeta queda entre 50.5 y 59.9 %)
    (ch_start[7], T("g_cruce", 1)[0], 7, "Cambiamos al cruce más cargado (1 semáforo), elegimos DQN (E4) y Reiniciar."),
    (T("g_cruce", 1)[0], at("g_cruce", 34.8), 7, "Aquí los mapas van lado a lado (izquierda fijo, derecha DQN). A 20× la mejora sube a ≈45 %."),
    (at("g_cruce", 34.8), T("g_cruce", 4)[0], 7, "Ahora PPO (E4): misma demanda y semilla. Reiniciar…"),
    (T("g_cruce", 4)[0], ch_end[7], 7, "PPO: ≈55 % menos espera en vivo (oscila entre 50 y 60 %) a los ~7 min simulados."),
]

# Chips (inicio, fin, texto): saltos de tiempo y velocidad del VIDEO (no de la simulación), uno por toma
# (a_mappo y g_cruce saltan el tramo de la «Mejora» negativa: el reloj simulado avanza ~30 s y ~70 s)
JUMPS = ({T(c, 1)[0] for c in ("e_comm", "i_qmix", "f_maxpressure")}
         | {T("a_mappo", 2)[0], T("g_cruce", 2)[0], T("g_cruce", 4)[0]})
CHIPS = []
for i, s in enumerate(shots):
    parts = ["SALTO EN EL TIEMPO"] if s["start"] in JUMPS else []
    if s["rate"] != 1:
        r = s["rate"]
        rr = round(r) if abs(r - round(r)) < 0.06 else r
        parts.append(f"VIDEO {rr:g}×".replace(".", ","))
    if parts:
        CHIPS.append((s["start"], shot_end(i), " · ".join(parts)))

# Anillos de resaltado (inicio, fin, rect UI): sobre el control que se pulsa o la zona del mapa que cambia
RINGS = [
    (at("a_mappo", 1.8), at("a_mappo", 4.6), "pol_reset"),
    (at("a_mappo", 7.9), r2(T("a_mappo", 1)[1] - 0.05), "velocidad"),
    (at("a_mappo", 45.0), r2(ch_end[0] - 0.5), "mejora"),
    (at("j_mapa", 1.6), at("j_mapa", 3.3), "vista"),
    (at("j_mapa", 11.4), at("j_mapa", 12.4), "card10_rl"),
    (at("j_mapa", 17.95), at("j_mapa", 19.6), "luz"),
    (at("j_mapa", 26.05), at("j_mapa", 27.5), "estilo"),
    (at("j_mapa", 27.6), at("j_mapa", 31.3), "cola10_fijo"),
    (at("j_mapa", 27.6), at("j_mapa", 31.3), "cola10_rl"),
    (at("j_mapa", 32.2), at("j_mapa", 33.25), "estilo"),
    (at("j_mapa", 33.3), at("j_mapa", 34.6), "luz"),
    (at("j_mapa", 34.8), at("j_mapa", 36.7), "vista"),
    (at("b_inyectar", 2.8), at("b_inyectar", 5.0), "modo_iny"),
    (at("b_inyectar", 5.1), at("b_inyectar", 8.6), "sur_fijo"),
    (at("b_inyectar", 5.1), at("b_inyectar", 8.6), "sur_rl"),
    (at("b_inyectar", 13.7), at("b_inyectar", 15.2), "vista_iny"),
    (at("b_inyectar", 16.2), at("b_inyectar", 19.6), "c12_fijo"),
    (at("b_inyectar", 16.2), at("b_inyectar", 19.6), "c12_rl"),
    (at("c_hora", 2.0), at("c_hora", 7.5), "hora"),
    (at("c_hora", 17.0), at("c_hora", 20.5), "hora"),
    (at("c_hora", 32.0), at("c_hora", 36.0), "hora"),
    (at("d_incidente", 4.1), at("d_incidente", 5.4), "modo_inc"),
    (at("d_incidente", 5.6), at("d_incidente", 7.5), "tramo_fijo"),
    (at("d_incidente", 5.6), at("d_incidente", 7.5), "tramo_rl"),
    (at("d_incidente", 32.6), at("d_incidente", 35.4), "tramo_fijo"),
    (at("d_incidente", 32.6), at("d_incidente", 35.4), "tramo_rl"),
    (T("e_comm")[0] + 0.1, at("e_comm", 4.3), "pol_reset"),
    (T("e_comm", 1)[0] + 0.4, r2(T("e_comm", 1)[1] - 0.3), "mejora"),
    (T("i_qmix")[0] + 0.1, at("i_qmix", 4.3), "pol_reset"),
    (T("i_qmix", 1)[0] + 0.4, r2(T("i_qmix", 1)[1] - 0.3), "mejora"),
    (T("f_maxpressure")[0] + 0.1, at("f_maxpressure", 4.3), "pol_reset"),
    (at("h_velocidad", 1.1), at("h_velocidad", 2.8), "velocidad"),
    (at("h_velocidad", 4.0), at("h_velocidad", 5.6), "vista"),
    (at("h_velocidad", 8.6), at("h_velocidad", 10.2), "velocidad"),
    (at("h_velocidad", 18.3), at("h_velocidad", 21.2), "velocidad"),
    (at("h_velocidad", 25.1), at("h_velocidad", 28.2), "velocidad"),
    (at("g_cruce", 1.5), at("g_cruce", 4.9), "selects"),
    (at("g_cruce", 22.0), at("g_cruce", 34.5), "mejora"),
    (at("g_cruce", 34.7), at("g_cruce", 37.5), "pol_reset"),
]

# Punch-ins del marco (inicio, fin, rect UI de destino, escala)
PUNCHES = [
    (at("a_mappo", 45.0), ch_end[0], "mejora", 1.4),
    (at("j_mapa", 4.3), r2(T("j_mapa")[1]), "z_10a_fijo", 1.8),
    (at("j_mapa", 13.5), r2(T("j_mapa", 1)[1]), "z_10a_ambos", 1.7),
    (at("j_mapa", 20.2), r2(T("j_mapa", 2)[1]), "z_10a_norte", 1.8),
    (at("b_inyectar", 21.0), ch_end[2], "z_c12_ambos", 1.6),
    (at("d_incidente", 7.6), r2(T("d_incidente")[1]), "z_incidente", 1.7),
    (T("f_maxpressure", 1)[0] + 0.2, ch_end[5], "mejora", 1.4),
    (at("h_velocidad", 10.6), r2(T("h_velocidad", 1)[1]), "z_12_ambos", 1.75),
    (at("g_cruce", 52.0), ch_end[7], "mejora", 1.4),
]


def punch_xy(rect, s):
    x, y, w, h = rect
    cx, cy = (x + w / 2) * FOOT_SCALE, (y + h / 2) * FOOT_SCALE
    tx = min(0.0, max(FRAME_W - s * FRAME_W, FRAME_W / 2 - s * cx))
    ty = min(0.0, max(FRAME_H - s * FRAME_H, FRAME_H / 2 - s * cy))
    return round(tx, 1), round(ty, 1)


# --------------------------------------------------------------------------- HTML
def esc(s: str) -> str:
    return html.escape(s, quote=True)


def in_chapter(ci: int, a: float) -> bool:
    return ch_start[ci] - 1e-6 <= a < ch_end[ci] - 1e-6


def lanes(intervals, tracks, per_track=3):
    """Asigna a cada intervalo (a, b) el primer carril de `tracks` libre y con menos de `per_track` elementos
    (solo para que el timeline del Studio se lea bien; el lint avisa desde 4 elementos por carril)."""
    busy = {k: -1.0 for k in tracks}
    used = {k: 0 for k in tracks}
    out = []
    for a, b in intervals:
        k = next((k for k in tracks if busy[k] <= a + 1e-6 and used[k] < per_track), tracks[-1])
        busy[k], used[k] = b, used[k] + 1
        out.append(k)
    return out


def build_chapter(ci: int) -> str:
    """Sub-composición de un capítulo: metraje (con cámara), anillos, subtítulos y chips en tiempo LOCAL."""
    cid = f"ch{ci + 1:02d}"
    t0, dur = ch_start[ci], (ch_f1[ci] - ch_f0[ci]) / FPS
    loc = lambda x: r2(x - t0)  # noqa: E731
    vids, rings, caps, chips = [], [], [], []
    for i, s in enumerate(shots):
        if s["ch"] != ci:
            continue
        vids.append(
            f'          <video id="{cid}-v{i:02d}" class="clip vid" src="../media/{s["clip"]}.mp4" '
            f'data-start="{fl((s["f0"] - ch_f0[ci]) / FPS)}" data-duration="{ce(s["nf"] / FPS)}" '
            f'data-media-start="{s["ms"]:g}" data-playback-rate="{s["rate"]:g}" '
            f'data-track-index="1" data-hf-media-start-basis="local" muted playsinline></video>')
    rdata, cdata, kdata, pdata = [], [], [], []
    my_rings = [(i, a, b, key) for i, (a, b, key) in enumerate(RINGS) if in_chapter(ci, a)]
    for (i, a, b, key), track in zip(my_rings, lanes([(a, b) for _, a, b, _ in my_rings], [2, 5, 6, 7])):
        x, y, w, h = UI[key]
        rings.append(
            f'          <div id="{cid}-ring{i:02d}" class="clip ring" data-start="{fl(loc(a))}" data-duration="{ce(r2(b - a))}" '
            f'data-track-index="{track}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"></div>')
        rdata.append([loc(a), loc(b)])
    for i, (a, b, c, text) in enumerate(CAPTIONS):
        if c != ci:
            continue
        caps.append(
            f'      <div id="{cid}-cap{i:02d}" class="clip caption" data-start="{fl(loc(a))}" data-duration="{ce(r2(b - a))}" '
            f'data-track-index="3" data-k="{esc(kick(ci))}">{esc(text)}</div>')
        cdata.append([loc(a), loc(b)])
    for i, (a, b, text) in enumerate(CHIPS):
        if not in_chapter(ci, a):
            continue
        chips.append(
            f'      <div id="{cid}-chip{i:02d}" class="clip chip" data-start="{fl(loc(a))}" data-duration="{ce(r2(b - a))}" '
            f'data-track-index="4">{esc(text)}</div>')
        kdata.append([loc(a), loc(b)])
    for a, b, key, sc in PUNCHES:
        if in_chapter(ci, a):
            pdata.append([loc(a), loc(b), sc, *punch_xy(UI[key], sc)])
    data = json.dumps({"dur": dur, "rings": rdata, "caps": cdata, "chips": kdata, "punches": pdata, "first": ci == 0})
    return (CHAPTER_TEMPLATE.replace("@CID@", cid).replace("@DUR@", ce(dur)).replace("@DATA@", data)
            .replace("@VIDEOS@", "\n".join(vids)).replace("@RINGS@", "\n".join(rings))
            .replace("@CAPTIONS@", "\n".join(caps)).replace("@CHIPS@", "\n".join(chips)))


def build_index() -> str:
    slots = []
    for ci in range(N):
        cid = f"ch{ci + 1:02d}"
        slots.append(
            f'      <div id="el-{cid}" class="slot" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html"\n'
            f'        data-start="{fl(ch_start[ci])}" data-duration="{ce((ch_f1[ci] - ch_f0[ci]) / FPS)}" data-track-index="1" '
            f'data-width="1920" data-height="1080"></div>')
    lane = [
        {"t": 0, "v": 0}, {"t": MUSIC_FADE_IN, "v": 1},
        {"t": r2(RESULTS_START - 0.6), "v": 1}, {"t": r2(RESULTS_START + 0.6), "v": MUSIC_DIP},
        {"t": r2(TOTAL - MUSIC_FADE_OUT), "v": MUSIC_DIP}, {"t": TOTAL, "v": 0},
    ]
    music = (
        f'      <audio id="music-bed" src="{MUSIC_SRC}" data-start="0" data-duration="{fl(TOTAL)}" data-track-index="10" '
        f'data-volume="1"\n'
        f"        data-fx-chain='{json.dumps({'version': 1, 'nodes': [{'type': 'gain', 'id': 'g1', 'label': 'Nivel de la cama', 'params': {'gain': MUSIC_GAIN_DB}}]})}'\n"
        f"        data-automation='{json.dumps({'version': 1, 'lanes': [{'target': 'volume', 'points': lane}]})}'></audio>"
    )
    return (INDEX_TEMPLATE.replace("@MUSIC@", music).replace("@TOTAL@", fl(TOTAL)).replace("@DEMO_START@", fl(DEMO_START))
            .replace("@DEMO_DUR@", ce(DEMO_END - DEMO_START)).replace("@RESULTS_START@", fl(RESULTS_START))
            .replace("@CLOSING_START@", fl(CLOSING_START)).replace("@RESULTS_DUR@", f"{RESULTS_DUR:g}")
            .replace("@CLOSING_DUR@", f"{CLOSING_DUR:g}").replace("@TITLE_DUR@", f"{TITLE_DUR:g}")
            .replace("@CONTEXT_DUR@", f"{CONTEXT_DUR:g}").replace("@SLOTS@", "\n".join(slots)))


FRAME_CSS = f"left: {FRAME_X}px; top: {FRAME_Y}px; width: {FRAME_W}px; height: {FRAME_H}px;"

CHAPTER_TEMPLATE = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <!-- GENERADO por ../edl.py (capítulo @CID@): editar la EDL ahí y volver a correr `python3 edl.py` -->
  </head>
  <body>
    <template id="@CID@-template">
      <style>
        #root { position: absolute; inset: 0; font-family: "Montserrat", sans-serif; color: #e8ecf3; }
        #@CID@-frame { position: absolute; """ + FRAME_CSS + """ overflow: hidden; border-radius: 16px; background: #0b0e14; }
        #@CID@-cam { position: absolute; left: 0; top: 0; width: """ + str(FRAME_W) + """px; height: """ + str(FRAME_H) + """px; transform-origin: 0 0; }
        #@CID@-footage { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; transform: scale(""" + str(FOOT_SCALE) + """); transform-origin: 0 0; }
        #@CID@-footage .vid { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; object-fit: cover; }
        #@CID@-footage .ring { position: absolute; border: 5px solid #2ee6a6; border-radius: 16px; margin: -6px 0 0 -6px; padding: 6px;
          box-sizing: content-box; box-shadow: 0 0 28px rgba(46, 230, 166, 0.55), inset 0 0 18px rgba(46, 230, 166, 0.25); }
        #root .caption { position: absolute; left: 120px; top: 986px; width: 1680px; height: 84px; font-size: 30px; font-weight: 700;
          letter-spacing: -0.01em; white-space: nowrap; }
        #root .caption::before { content: attr(data-k); display: block; margin-bottom: 8px; font-family: "JetBrains Mono", monospace;
          font-size: 20px; font-weight: 400; letter-spacing: 0.12em; color: #2ee6a6; }
        #root .chip { position: absolute; right: 120px; top: 982px; height: 32px; padding: 0 14px; border-radius: 8px;
          background: #1b2434; border: 2px solid #3a4a6a; color: #e2e8f2; font-family: "JetBrains Mono", monospace;
          font-size: 18px; line-height: 28px; letter-spacing: 0.08em; white-space: nowrap; }
      </style>

      <div id="root" data-composition-id="@CID@" data-width="1920" data-height="1080" data-duration="@DUR@">
        <div id="@CID@-frame">
          <div id="@CID@-cam" data-layout-allow-overflow>
            <div id="@CID@-footage">
@VIDEOS@
@RINGS@
            </div>
          </div>
        </div>
@CAPTIONS@
@CHIPS@
      </div>

      <script>
        (function () {
          const D = @DATA@;
          const root = document.querySelector('[data-composition-id="@CID@"]');
          const q = (s) => root.querySelectorAll(s);
          const tl = gsap.timeline({ paused: true });
          if (D.first) tl.fromTo("#@CID@-frame", { opacity: 0, scale: 0.96 }, { opacity: 1, scale: 1, duration: 0.6, ease: "power3.out" }, 0);
          // subtítulos: sube y entra (waterfall-entry contenido), sale rápido
          q(".caption").forEach((el, i) => {
            const [a, b] = D.caps[i];
            tl.fromTo(el, { y: 22, opacity: 0 }, { y: 0, opacity: 1, duration: 0.45, ease: "expo.out" }, a + 0.05);
            if (b - a > 1.2 && b < D.dur - 0.05) tl.to(el, { opacity: 0, duration: 0.2, ease: "power1.in" }, b - 0.2);
          });
          q(".chip").forEach((el, i) => {
            const [a] = D.chips[i];
            tl.fromTo(el, { scale: 0.7, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2)" }, a + 0.05);
          });
          // anillos de resaltado sobre la UI real
          q(".ring").forEach((el, i) => {
            const [a, b] = D.rings[i];
            tl.fromTo(el, { scale: 1.25, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.4, ease: "power3.out" }, a);
            const pulses = Math.max(0, Math.floor((b - a - 0.9) / 0.5));
            if (pulses > 0) tl.to(el, { scale: 1.05, duration: 0.25, ease: "sine.inOut", yoyo: true, repeat: pulses - 1 }, a + 0.45);
            tl.to(el, { opacity: 0, duration: 0.25 }, b - 0.25);
          });
          // punch-ins (viewport-change: un solo envoltorio con escala + traslación)
          D.punches.forEach(([a, b, s, x, y]) => {
            tl.fromTo("#@CID@-cam", { scale: 1, x: 0, y: 0 }, { scale: s, x: x, y: y, duration: 0.9, ease: "power3.inOut", immediateRender: false }, a);
            tl.to("#@CID@-cam", { scale: 1, x: 0, y: 0, duration: 0.45, ease: "power2.inOut" }, b - 0.45);
          });
          window.__timelines["@CID@"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
"""

INDEX_TEMPLATE = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>Demo de respaldo · Semáforos inteligentes en Av. La Reforma</title>
    <!-- GENERADO por edl.py: editar la EDL ahí y volver a correr `python3 edl.py` -->
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #0b0e14; }
      #root { position: relative; width: 100%; height: 100%; overflow: hidden; background: #0b0e14;
        font-family: "Montserrat", sans-serif; color: #e8ecf3; }
      #bg-glow { position: absolute; inset: -80px; background:
        radial-gradient(820px 560px at 12% 88%, rgba(46, 230, 166, 0.10), transparent 70%),
        radial-gradient(760px 520px at 92% 8%, rgba(255, 159, 67, 0.07), transparent 70%); }
      #bg-grid { position: absolute; inset: 0; background-image:
        linear-gradient(rgba(139, 149, 167, 0.06) 2px, transparent 2px),
        linear-gradient(90deg, rgba(139, 149, 167, 0.06) 2px, transparent 2px); background-size: 120px 120px; }
      .slot { position: absolute; inset: 0; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="@TOTAL@">
      <div id="bg-glow"></div>
      <div id="bg-grid"></div>

      <!-- Marco, riel de capítulos y etiqueta EN VIVO (solo durante la demo) -->
      <div id="el-chrome" class="slot" data-composition-id="chrome" data-composition-src="compositions/chrome.html"
        data-start="@DEMO_START@" data-duration="@DEMO_DUR@" data-track-index="0" data-width="1920" data-height="1080"></div>

      <!-- Capítulos de la demo (metraje real) -->
@SLOTS@

      <!-- Tarjetas -->
      <div id="el-title" class="slot" data-composition-id="title" data-composition-src="compositions/title.html"
        data-start="0" data-duration="@TITLE_DUR@" data-track-index="2" data-width="1920" data-height="1080"></div>
      <div id="el-context" class="slot" data-composition-id="context" data-composition-src="compositions/context.html"
        data-start="@TITLE_DUR@" data-duration="@CONTEXT_DUR@" data-track-index="2" data-width="1920" data-height="1080"></div>
      <div id="el-results" class="slot" data-composition-id="results" data-composition-src="compositions/results.html"
        data-start="@RESULTS_START@" data-duration="@RESULTS_DUR@" data-track-index="2" data-width="1920" data-height="1080"></div>
      <div id="el-closing" class="slot" data-composition-id="closing" data-composition-src="compositions/closing.html"
        data-start="@CLOSING_START@" data-duration="@CLOSING_DUR@" data-track-index="2" data-width="1920" data-height="1080"></div>

      <!-- Música de fondo: fundido de entrada 2 s, baja ~4 dB en resultados, fundido de salida 3 s -->
@MUSIC@
    </div>

    <script>
      (function () {
        const tl = gsap.timeline({ paused: true });
        tl.fromTo("#bg-glow", { x: -30, y: 10 }, { x: 30, y: -10, duration: @TOTAL@, ease: "none" }, 0);
        window.__timelines["main"] = tl;
      })();
    </script>
  </body>
</html>
"""

RAIL_STEP = 66
RAIL_H = N * RAIL_STEP
RAIL_TOP = round(FRAME_Y + FRAME_H / 2 - RAIL_H / 2)

CHROME_TEMPLATE = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <!-- GENERADO por ../edl.py: marco, riel de capítulos y etiqueta EN VIVO durante toda la demo -->
  </head>
  <body>
    <template id="chrome-template">
      <style>
        #root { position: absolute; inset: 0; font-family: "Montserrat", sans-serif; color: #e8ecf3; }
        #frame-shadow { position: absolute; """ + FRAME_CSS + """ border-radius: 16px; background: #0b0e14;
          box-shadow: 0 0 0 2px #232a38, 0 30px 90px rgba(0, 0, 0, 0.55); }
        #band-line { position: absolute; left: 120px; top: 978px; width: 1680px; height: 2px; background: #232a38; }
        #rail { position: absolute; left: 0; top: """ + str(RAIL_TOP) + """px; width: 120px; height: """ + str(RAIL_H) + """px; }
        #rail-line { position: absolute; left: 22px; top: 6px; width: 2px; height: """ + str(RAIL_H - 30) + """px; background: #232a38; }
        .rail-n { position: relative; height: """ + str(RAIL_STEP) + """px; padding-left: 32px; color: #7b8496; }
        .rail-num { display: block; font-family: "JetBrains Mono", monospace; font-size: 24px; font-weight: 700; }
        .rail-lab { display: block; font-size: 13px; font-weight: 700; letter-spacing: 0.01em; text-transform: uppercase; white-space: nowrap; }
        #rail-mark { position: absolute; left: 16px; top: 8px; width: 14px; height: 14px; border-radius: 50%;
          background: #2ee6a6; box-shadow: 0 0 16px rgba(46, 230, 166, 0.8); }
        #live { position: absolute; right: 26px; top: 360px; width: 70px; height: 360px; }
        #live-dot { position: absolute; left: 26px; top: 0; width: 18px; height: 18px; border-radius: 50%; background: #2ee6a6;
          box-shadow: 0 0 18px rgba(46, 230, 166, 0.9); }
        #live-txt { position: absolute; left: 35px; top: 40px; width: 320px; height: 26px; transform: rotate(90deg);
          transform-origin: 0 0; font-family: "JetBrains Mono", monospace; font-size: 18px; letter-spacing: 0.22em;
          color: #7d869a; white-space: nowrap; }
      </style>

      <div id="root" data-composition-id="chrome" data-width="1920" data-height="1080" data-duration="@DEMO_DUR@">
        <div id="frame-shadow"></div>
        <div id="band-line"></div>
        <div id="rail">
          <div id="rail-line"></div>
          <div id="rail-mark"></div>
@RAIL@
        </div>
        <div id="live"><div id="live-dot"></div><div id="live-txt">DEMO EN VIVO · SUMO + RL</div></div>
      </div>

      <script>
        (function () {
          const D = @DATA@;
          const tl = gsap.timeline({ paused: true });
          tl.fromTo("#frame-shadow, #band-line", { opacity: 0 }, { opacity: 1, duration: 0.6, ease: "power2.out" }, 0);
          tl.fromTo("#rail, #live", { opacity: 0 }, { opacity: 1, duration: 0.6 }, 0.2);
          // riel: marca y color del capítulo activo
          D.chStart.forEach((t0, i) => {
            tl.to("#rail-mark", { y: i * D.step, duration: 0.45, ease: "power3.inOut" }, Math.max(0, t0 - 0.2));
            tl.to("#rail" + i, { color: "#2ee6a6", duration: 0.3 }, t0);
            if (i > 0) tl.to("#rail" + (i - 1), { color: "#aab3c4", duration: 0.3 }, t0);
          });
          tl.fromTo("#live-dot", { opacity: 1 }, { opacity: 0.25, duration: 0.8, ease: "sine.inOut", yoyo: true,
            repeat: Math.floor(D.dur / 0.8) - 2 }, 0);
          window.__timelines["chrome"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
"""


def build_chrome() -> str:
    rail = "\n".join(
        f'          <div class="rail-n" id="rail{i}"><span class="rail-num">{i + 1:02d}</span><span class="rail-lab">{esc(c[0])}</span></div>'
        for i, c in enumerate(CHAPTERS))
    data = {"dur": r2(DEMO_END - DEMO_START), "step": RAIL_STEP, "chStart": [r2(x - DEMO_START) for x in ch_start]}
    return (CHROME_TEMPLATE.replace("@DEMO_DUR@", ce(DEMO_END - DEMO_START)).replace("@RAIL@", rail)
            .replace("@DATA@", json.dumps(data)))


# --------------------------------------------------------------------------- música
def bed_sections() -> list[float]:
    """Tiempos (en el video) en que la cama empieza una sección de 8 compases del tema."""
    out, t0 = [], 0.0
    for k, (a, b) in enumerate(BED_PIECES):
        start = t0 - (BED_XFADE if k else 0.0)
        s = 0.0
        while s <= b + 1e-6:
            if s >= a - 1e-6:
                out.append(round(start + s - a, 2))
            s += 19.2
        t0 = start + (b - a)
    return out


def build_bed(here: Path) -> None:
    """Arma la cama con ffmpeg (muestras exactas a 44.1 kHz, cruces triangulares de 80 ms)."""
    parts, chain, prev = [], [], None
    for k, (a, b) in enumerate(BED_PIECES):
        parts.append(f"[0:a]atrim=start_sample={round(a * BED_SR)}:end_sample={round(b * BED_SR)},asetpts=PTS-STARTPTS[p{k}]")
    for k in range(1, len(BED_PIECES)):
        left = "p0" if k == 1 else f"x{k - 1}"
        out = "out" if k == len(BED_PIECES) - 1 else f"x{k}"
        chain.append(f"[{left}][p{k}]acrossfade=d={BED_XFADE}:c1=tri:c2=tri[{out}]")
        prev = out
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(here / MUSIC_WAV), "-filter_complex", ";".join(parts + chain),
           "-map", f"[{prev}]", "-c:a", "pcm_s16le", str(here / MUSIC_SRC)]
    subprocess.run(cmd, check=True)
    print("cama:", " ".join(cmd[cmd.index("-filter_complex") + 1:cmd.index("-map")]))


def storyboard() -> str:
    def mmss(x):
        return f"{int(x // 60)}:{x % 60:04.1f}"
    out = [f"0:00.0–{mmss(TITLE_DUR)}  Título", f"{mmss(TITLE_DUR)}–{mmss(DEMO_START)}  Contexto: corredor y fijo vs RL"]
    for ci, (_, name, _) in enumerate(CHAPTERS):
        out.append(f"{mmss(ch_start[ci])}–{mmss(ch_end[ci])}  {ci + 1:02d} {name}")
        for i, s in enumerate(shots):
            if s["ch"] == ci:
                out.append(f"      {mmss(s['start'])}  {s['clip']}.mp4 desde {s['ms']:g} s, {s['dur']:g} s a {s['rate']:g}×")
    out.append(f"{mmss(RESULTS_START)}–{mmss(CLOSING_START)}  Resultados")
    out.append(f"{mmss(CLOSING_START)}–{mmss(TOTAL)}  Cierre")
    return "\n".join(out)


def check_cuts() -> list[str]:
    """Con los valores tal como quedan escritos en el HTML, cada cuadro de la demo tiene un capítulo y cada cuadro
    de un capítulo tiene una toma (sin cuadros vacíos en los cortes)."""
    bad = []
    slots = [(float(fl(ch_start[ci])), float(ce((ch_f1[ci] - ch_f0[ci]) / FPS))) for ci in range(N)]
    for k in range(round(DEMO_START * FPS), DEMO_END_F):
        if not any(a <= k / FPS < a + d for a, d in slots):
            bad.append(f"cuadro {k} ({k / FPS:.3f} s) sin capítulo")
    for ci in range(N):
        vids = [(float(fl((s["f0"] - ch_f0[ci]) / FPS)), float(ce(s["nf"] / FPS))) for s in shots if s["ch"] == ci]
        for k in range(ch_f1[ci] - ch_f0[ci]):
            if not any(a <= k / FPS < a + d for a, d in vids):
                bad.append(f"ch{ci + 1:02d}: cuadro local {k} ({ch_start[ci] + k / FPS:.3f} s) sin metraje")
    return bad


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    gaps = check_cuts()
    if gaps:
        sys.exit("ERROR, cuadros vacíos en los cortes:\n  " + "\n  ".join(gaps))
    (here / "index.html").write_text(build_index())
    for ci in range(N):
        (here / "compositions" / f"ch{ci + 1:02d}.html").write_text(build_chapter(ci))
    (here / "compositions" / "chrome.html").write_text(build_chrome())
    for old in sorted((here / "compositions").glob("ch[0-9][0-9].html")):
        if int(old.stem[2:]) > N:
            old.unlink()
    if "--bed" in sys.argv:
        build_bed(here)
    print(storyboard())
    secs = bed_sections()
    near = min(secs, key=lambda s: abs(s - RESULTS_START))
    print(f"duración total: {TOTAL:.2f} s · metraje de demo: {DEMO_END - DEMO_START:.1f} s "
          f"({100 * (DEMO_END - DEMO_START) / TOTAL:.0f} %)")
    print(f"música: entrada fuerte en {secs[0]:.2f} s (demo en {DEMO_START:g} s); sección más cercana a los "
          f"resultados ({RESULTS_START:.2f} s): {near:.2f} s; cama de "
          f"{sum(b - a for a, b in BED_PIECES) - BED_XFADE * (len(BED_PIECES) - 1):.2f} s")
    long = [c[3] for c in CAPTIONS if len(c[3]) > 96]
    if long:
        print("AVISO subtítulos largos:", *long, sep="\n  ")
