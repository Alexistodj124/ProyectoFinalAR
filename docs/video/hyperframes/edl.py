#!/usr/bin/env python3
"""Genera index.html (composición raíz de HyperFrames) a partir de la lista de edición (EDL).

    python3 edl.py            # escribe index.html y imprime el guion con tiempos (storyboard)

Cada capítulo es una lista de tomas (clip, inicio en el clip, duración en el video, velocidad).
Los subtítulos, anillos de resaltado, chips y punch-ins se anclan a tiempos del clip original
(`at(...)`), así que si cambia una toma todo lo demás se recalcula solo.
Los clips viven en media/ (copiados de ../../../../video/clips, ignorados por git).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

FPS = 30
TITLE_DUR, CONTEXT_DUR, RESULTS_DUR, CLOSING_DUR = 5.0, 9.5, 15.0, 5.5
DEMO_START = TITLE_DUR + CONTEXT_DUR
FOOT_SCALE = 0.875  # 1920x1080 -> 1680x945 dentro del marco
FRAME_X, FRAME_Y, FRAME_W, FRAME_H = 120, 22, 1680, 945

# Rectángulos de la UI en coordenadas de la grabación (1920x1080)
UI = {
    "mejora": (1566, 9, 340, 114),
    "selects": (1658, 452, 238, 160),
    "pol_reset": (1658, 516, 238, 96),
    "inyectar": (1658, 160, 238, 92),
    "hora": (1660, 270, 234, 70),
    "velocidad": (1660, 380, 234, 50),
    "c12_izq": (284, 262, 200, 52),
    "c12_der": (1103, 262, 200, 52),
    "tramo_izq": (382, 292, 100, 330),
    "tramo_der": (1201, 292, 100, 330),
    "kpis": (528, 9, 1378, 114),
}


def r2(x: float) -> float:
    return round(x * FPS) / FPS


# --------------------------------------------------------------------------- EDL
# (clip, inicio_en_clip, duración_en_video, velocidad)
CHAPTERS = [
    ("MAPPO", "Hora pico — fijo vs MAPPO", [("a_mappo", 1.5, 14.0, 1), ("a_mappo", 15.5, 14.0, 3)]),
    ("Inyectar", "Inyectar tráfico", [("b_inyectar", 0.8, 16.0, 1), ("b_inyectar", 16.8, 8.0, 2.7)]),
    ("Hora", "Hora del día", [("c_hora", 1.5, 20.0, 1.95)]),
    ("Incidente", "Incidente en la Reforma", [
        ("d_incidente", 0.8, 11.0, 1), ("d_incidente", 11.8, 7.8, 2.5),
        ("d_incidente", 31.3, 6.0, 1), ("d_incidente", 37.3, 4.8, 2.5)]),
    ("Políticas", "Otras políticas en el corredor", [
        ("e_comm", 2.2, 6.3, 1), ("e_comm", 38.0, 5.7, 1),
        ("i_qmix", 2.2, 6.3, 1), ("i_qmix", 32.0, 5.7, 1),
        ("f_maxpressure", 2.2, 6.3, 1), ("f_maxpressure", 38.0, 5.7, 1)]),
    ("Velocidad", "Control de velocidad", [("h_velocidad", 0.8, 16.0, 1), ("h_velocidad", 16.8, 7.35, 2)]),
    ("Cruce", "Cruce aislado: Reforma y 12 calle", [
        ("g_cruce", 1.5, 9.5, 1), ("g_cruce", 11.0, 6.6, 3.5),
        ("g_cruce", 34.5, 7.5, 1), ("g_cruce", 42.0, 6.0, 3.5)]),
]

shots = []  # dicts con start global
t = DEMO_START
for ci, (_, _, lst) in enumerate(CHAPTERS):
    for (clip, ms, dur, rate) in lst:
        shots.append({"ch": ci, "clip": clip, "ms": ms, "dur": dur, "rate": rate, "start": r2(t)})
        t += dur
DEMO_END = r2(t)
RESULTS_START = DEMO_END
CLOSING_START = r2(RESULTS_START + RESULTS_DUR)
TOTAL = r2(CLOSING_START + CLOSING_DUR)
ch_start = [min(s["start"] for s in shots if s["ch"] == ci) for ci in range(len(CHAPTERS))]
ch_end = ch_start[1:] + [DEMO_END]


def at(clip: str, src_t: float, nth: int = 0) -> float:
    """Tiempo global en que se ve el segundo `src_t` del clip (en su n-ésima toma que lo contiene)."""
    hits = [s for s in shots if s["clip"] == clip and s["ms"] <= src_t <= s["ms"] + s["dur"] * s["rate"] + 1e-6]
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


# Subtítulos: (inicio, fin, capítulo, texto)
CAPTIONS = [
    (ch_start[0], at("a_mappo", 9.0), 0, "Elegimos MAPPO (la mejor semilla) y pulsamos Reiniciar: los dos lados arrancan con la misma demanda."),
    (at("a_mappo", 9.0), T("a_mappo", 1)[0], 0, "A 5×: la espera del agente (verde) crece mucho menos que la del semáforo fijo (ámbar)."),
    (T("a_mappo", 1)[0], at("a_mappo", 45.0), 0, "A 20× las curvas de espera y de cola se separan y ya no se vuelven a juntar."),
    (at("a_mappo", 45.0), ch_end[0], 0, "Tarjeta «Mejora»: ≈47 % menos espera promedio en vivo a los 15 min simulados."),
    (ch_start[1], at("b_inyectar", 9.5), 1, "Modo Inyectar, 40 carros: un clic en la entrada sur de la Reforma."),
    (at("b_inyectar", 9.5), T("b_inyectar", 1)[0], 1, "Otro clic: 40 carros más en la 12 calle. Las colas rojas crecen en los dos lados."),
    (T("b_inyectar", 1)[0], ch_end[1], 1, "El agente desahoga las colas antes y la mejora se mantiene alrededor de 50 %."),
    (ch_start[2], at("c_hora", 17.2), 2, "Mediodía: la demanda baja de ≈7 350 a ≈4 800 veh/h (perfil que el agente no vio al entrenar)."),
    (at("c_hora", 17.2), at("c_hora", 32.2), 2, "Noche: ≈2 200 veh/h. Casi no hay colas en ningún lado y las curvas se juntan."),
    (at("c_hora", 32.2), ch_end[2], 2, "Y de regreso a la hora pico."),
    (ch_start[3], at("d_incidente", 4.6), 3, "Zoom con la rueda del mouse al tramo de la Reforma entre la 12 y la 10a calle."),
    (at("d_incidente", 4.6), T("d_incidente", 1)[0], 3, "Incidente hacia el norte: 2 de 3 carriles rectos cerrados; la cola crece hacia atrás."),
    (T("d_incidente", 1)[0], T("d_incidente", 2)[0], 3, "Con el tramo cerrado, la cola del lado RL sigue siendo mucho menor que la del tiempo fijo."),
    (T("d_incidente", 2)[0], ch_end[3], 3, "Otro clic retira el incidente: se reabren los carriles y la cola se disipa."),
    (T("e_comm")[0], T("e_comm", 1)[0], 4, "Comm (E6): agentes que aprenden a enviarse mensajes con sus vecinos. Reiniciar…"),
    (T("e_comm", 1)[0], T("i_qmix")[0], 4, "…unos 12 min simulados después: ≈48 % menos espera que el tiempo fijo."),
    (T("i_qmix")[0], T("i_qmix", 1)[0], 4, "QMIX (E5): un valor conjunto que se descompone por intersección. Reiniciar…"),
    (T("i_qmix", 1)[0], T("f_maxpressure")[0], 4, "…unos 10 min simulados después: también ≈48 % de mejora en vivo."),
    (T("f_maxpressure")[0], T("f_maxpressure", 1)[0], 4, "Max-pressure: regla clásica, sin aprendizaje (verde a la fase con más presión)."),
    (T("f_maxpressure", 1)[0], ch_end[4], 4, "Línea base muy fuerte: ≈44 % en vivo y la menor demora total en la evaluación."),
    (ch_start[5], at("h_velocidad", 7.6), 5, "Pausa congela la simulación; con la rueda hacemos zoom a Reforma y 12 calle."),
    (at("h_velocidad", 7.6), T("h_velocidad", 1)[0], 5, "1×: tiempo real. Cada barra en la línea de alto es la luz de ese carril."),
    (T("h_velocidad", 1)[0], ch_end[5], 5, "5× y 20×: más segundos simulados por segundo (dos SUMO en paralelo, en lock-step)."),
    (ch_start[6], at("g_cruce", 9.0), 6, "Cambiamos al cruce más cargado (1 semáforo) y elegimos DQN (E4)."),
    (at("g_cruce", 9.0), T("g_cruce", 2)[0], 6, "DQN a 20×: mira la cola de la 12 calle y la tarjeta «Mejora»."),
    (T("g_cruce", 2)[0], T("g_cruce", 3)[0], 6, "Ahora PPO (E4): misma demanda y semilla, otro algoritmo de un solo agente."),
    (T("g_cruce", 3)[0], ch_end[6], 6, "PPO: más de 50 % menos espera en vivo a los ~10 min simulados."),
]

# Chips (inicio, fin, texto): velocidad del VIDEO (no de la simulación) y saltos de tiempo
CHIPS = []
for i, s in enumerate(shots):
    if s["rate"] != 1:
        r = s["rate"]
        rr = round(r) if abs(r - round(r)) < 0.06 else r
        CHIPS.append((s["start"], shot_end(i), f"VIDEO {rr:g}×".replace(".", ",")))
for c in ("e_comm", "i_qmix", "f_maxpressure"):
    CHIPS.append((T(c, 1)[0], T(c, 1)[1], "SALTO EN EL TIEMPO"))

# Anillos de resaltado (inicio, fin, rect UI)
RINGS = [
    (at("a_mappo", 1.8), at("a_mappo", 6.0), "pol_reset"),
    (at("a_mappo", 45.0), r2(ch_end[0] - 0.5), "mejora"),
    (at("b_inyectar", 2.6), at("b_inyectar", 5.2), "inyectar"),
    (at("b_inyectar", 12.4), at("b_inyectar", 16.6), "c12_izq"),
    (at("b_inyectar", 12.4), at("b_inyectar", 16.6), "c12_der"),
    (at("c_hora", 2.0), at("c_hora", 8.0), "hora"),
    (at("c_hora", 17.0), at("c_hora", 23.0), "hora"),
    (at("c_hora", 32.0), at("c_hora", 38.0), "hora"),
    (at("d_incidente", 5.6), at("d_incidente", 11.6), "tramo_izq"),
    (at("d_incidente", 5.6), at("d_incidente", 11.6), "tramo_der"),
    (T("e_comm")[0] + 0.1, at("e_comm", 6.0), "pol_reset"),
    (T("e_comm", 1)[0] + 0.4, r2(T("e_comm", 1)[1] - 0.3), "mejora"),
    (T("i_qmix")[0] + 0.1, at("i_qmix", 6.0), "pol_reset"),
    (T("i_qmix", 1)[0] + 0.4, r2(T("i_qmix", 1)[1] - 0.3), "mejora"),
    (T("f_maxpressure")[0] + 0.1, at("f_maxpressure", 6.0), "pol_reset"),
    (T("f_maxpressure", 1)[0] + 0.4, r2(T("f_maxpressure", 1)[1] - 0.3), "mejora"),
    (at("h_velocidad", 1.0), at("h_velocidad", 3.4), "velocidad"),
    (at("h_velocidad", 7.2), at("h_velocidad", 10.0), "velocidad"),
    (at("h_velocidad", 17.2), at("h_velocidad", 21.0), "velocidad"),
    (at("h_velocidad", 24.2), at("h_velocidad", 28.4), "velocidad"),
    (at("g_cruce", 1.6), at("g_cruce", 5.0), "selects"),
    (at("g_cruce", 22.0), r2(T("g_cruce", 1)[1] - 0.2), "mejora"),
    (at("g_cruce", 34.6), at("g_cruce", 37.0), "pol_reset"),
    (at("g_cruce", 50.0), r2(ch_end[6] - 0.4), "mejora"),
]

# Punch-ins del marco (inicio, fin, rect UI de destino, escala)
PUNCHES = [
    (at("a_mappo", 45.0), ch_end[0], "mejora", 1.4),
    (T("f_maxpressure", 1)[0] + 0.2, ch_end[4], "mejora", 1.4),
    (at("g_cruce", 50.0), ch_end[6], "mejora", 1.4),
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


def build_chapter(ci: int) -> str:
    """Sub-composición de un capítulo: metraje (con cámara), anillos, subtítulos y chips en tiempo LOCAL."""
    cid = f"ch{ci + 1:02d}"
    t0, dur = ch_start[ci], r2(ch_end[ci] - ch_start[ci])
    loc = lambda x: r2(x - t0)  # noqa: E731
    vids, rings, caps, chips = [], [], [], []
    for i, s in enumerate(shots):
        if s["ch"] != ci:
            continue
        vids.append(
            f'          <video id="{cid}-v{i:02d}" class="clip vid" src="../media/{s["clip"]}.mp4" data-start="{loc(s["start"]):g}" '
            f'data-duration="{s["dur"]:g}" data-media-start="{s["ms"]:g}" data-playback-rate="{s["rate"]:g}" '
            f'data-track-index="1" data-hf-media-start-basis="local" muted playsinline></video>')
    rdata, cdata, kdata, pdata = [], [], [], []
    for i, (a, b, key) in enumerate(RINGS):
        if not in_chapter(ci, a):
            continue
        x, y, w, h = UI[key]
        rings.append(
            f'          <div id="{cid}-ring{i:02d}" class="clip ring" data-start="{loc(a):g}" data-duration="{r2(b - a):g}" '
            f'data-track-index="{2 if len(rdata) < 3 else 5}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"></div>')
        rdata.append([loc(a), loc(b)])
    for i, (a, b, c, text) in enumerate(CAPTIONS):
        if c != ci:
            continue
        caps.append(
            f'      <div id="{cid}-cap{i:02d}" class="clip caption" data-start="{loc(a):g}" data-duration="{r2(b - a):g}" '
            f'data-track-index="3" data-k="{esc(kick(ci))}">{esc(text)}</div>')
        cdata.append([loc(a), loc(b)])
    for i, (a, b, text) in enumerate(CHIPS):
        if not in_chapter(ci, a):
            continue
        chips.append(
            f'      <div id="{cid}-chip{i:02d}" class="clip chip" data-start="{loc(a):g}" data-duration="{r2(b - a):g}" '
            f'data-track-index="4">{esc(text)}</div>')
        kdata.append([loc(a), loc(b)])
    for a, b, key, sc in PUNCHES:
        if in_chapter(ci, a):
            pdata.append([loc(a), loc(b), sc, *punch_xy(UI[key], sc)])
    data = json.dumps({"dur": dur, "rings": rdata, "caps": cdata, "chips": kdata, "punches": pdata, "first": ci == 0})
    return (CHAPTER_TEMPLATE.replace("@CID@", cid).replace("@DUR@", f"{dur:g}").replace("@DATA@", data)
            .replace("@VIDEOS@", "\n".join(vids)).replace("@RINGS@", "\n".join(rings))
            .replace("@CAPTIONS@", "\n".join(caps)).replace("@CHIPS@", "\n".join(chips)))


def build_index() -> str:
    slots = []
    for ci in range(N):
        cid = f"ch{ci + 1:02d}"
        slots.append(
            f'      <div id="el-{cid}" class="slot" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html"\n'
            f'        data-start="{ch_start[ci]:g}" data-duration="{r2(ch_end[ci] - ch_start[ci]):g}" data-track-index="1" '
            f'data-width="1920" data-height="1080"></div>')
    rail = "\n".join(
        f'        <div class="rail-n" id="rail{i}"><span class="rail-num">{i + 1:02d}</span><span class="rail-lab">{esc(c[0])}</span></div>'
        for i, c in enumerate(CHAPTERS))
    js = {"demoStart": DEMO_START, "demoEnd": DEMO_END, "chStart": ch_start}
    return (INDEX_TEMPLATE.replace("@TOTAL@", f"{TOTAL:g}").replace("@DEMO_START@", f"{DEMO_START:g}")
            .replace("@DEMO_DUR@", f"{r2(DEMO_END - DEMO_START):g}").replace("@RESULTS_START@", f"{RESULTS_START:g}")
            .replace("@CLOSING_START@", f"{CLOSING_START:g}").replace("@RESULTS_DUR@", f"{RESULTS_DUR:g}")
            .replace("@CLOSING_DUR@", f"{CLOSING_DUR:g}").replace("@TITLE_DUR@", f"{TITLE_DUR:g}")
            .replace("@CONTEXT_DUR@", f"{CONTEXT_DUR:g}").replace("@SLOTS@", "\n".join(slots))
            .replace("@RAIL@", rail).replace("@DATA@", json.dumps(js)))


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
          <div id="@CID@-cam">
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
        #rail { position: absolute; left: 0; top: 300px; width: 120px; height: 480px; }
        #rail-line { position: absolute; left: 22px; top: 6px; width: 2px; height: 450px; background: #232a38; }
        .rail-n { position: relative; height: 66px; padding-left: 32px; color: #7b8496; }
        .rail-num { display: block; font-family: "JetBrains Mono", monospace; font-size: 24px; font-weight: 700; }
        .rail-lab { display: block; font-size: 13px; font-weight: 700; letter-spacing: 0.01em; text-transform: uppercase; }
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
            tl.to("#rail-mark", { y: i * 66, duration: 0.45, ease: "power3.inOut" }, Math.max(0, t0 - 0.2));
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
    data = {"dur": r2(DEMO_END - DEMO_START), "chStart": [r2(x - DEMO_START) for x in ch_start]}
    return (CHROME_TEMPLATE.replace("@DEMO_DUR@", f"{r2(DEMO_END - DEMO_START):g}").replace("@RAIL@", rail)
            .replace("@DATA@", json.dumps(data)))


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


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    (here / "index.html").write_text(build_index())
    for ci in range(N):
        (here / "compositions" / f"ch{ci + 1:02d}.html").write_text(build_chapter(ci))
    (here / "compositions" / "chrome.html").write_text(build_chrome())
    print(storyboard())
    print(f"duración total: {TOTAL:.2f} s · metraje de demo: {DEMO_END - DEMO_START:.1f} s "
          f"({100 * (DEMO_END - DEMO_START) / TOTAL:.0f} %)")
