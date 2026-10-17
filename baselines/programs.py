"""Utilidades para los programas de semáforo de las líneas base (tiempo fijo y actuado)."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from env.scenarios import REPO_ROOT, Scenario

CACHE_DIR = REPO_ROOT / "runs" / "cache" / "actuated"


def is_green_phase(state: str) -> bool:
    """Fase de verde = tiene alguna luz verde y ninguna amarilla (misma regla que sumo-rl)."""
    return "y" not in state.lower() and any(c in "Gg" for c in state)


def build_actuated_additional(net_file: str, min_green: int, max_green: int, out_path: str | Path) -> Path:
    """Escribe un .add.xml con un `tlLogic type="actuated" programID="actuated"` por semáforo.

    Reutiliza las fases (estados) del programa estático de la red; a cada fase de verde le pone
    minDur/maxDur y las fases de transición (amarillo / todo rojo) quedan con su duración fija.
    SUMO crea solo los detectores de inducción del controlador actuado.
    """
    root = ET.Element("additional")
    seen: set[str] = set()
    for _, el in ET.iterparse(net_file, events=("end",)):
        if el.tag != "tlLogic" or el.get("id") in seen:
            continue
        seen.add(el.get("id"))
        logic = ET.SubElement(root, "tlLogic", id=el.get("id"), type="actuated", programID="actuated", offset="0")
        for ph in el.findall("phase"):
            state, dur = ph.get("state"), float(ph.get("duration"))
            if is_green_phase(state):
                dur = min(max(dur, min_green), max_green)
                ET.SubElement(
                    logic, "phase", duration=f"{dur:g}", minDur=str(min_green), maxDur=str(max_green), state=state
                )
            else:
                ET.SubElement(logic, "phase", duration=f"{dur:g}", state=state)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def ensure_actuated(sc: Scenario, min_green: int | None = None, max_green: int | None = None) -> Scenario:
    """Devuelve el escenario con `actuated_additional` listo: usa el de la rama del entorno si existe
    y, si no (escenarios toy), genera uno desde la red y lo deja en caché (runs/cache/actuated)."""
    if sc.actuated_additional and Path(sc.actuated_additional).exists():
        return sc
    lo, hi = min_green or sc.min_green, max_green or sc.max_green
    net = Path(sc.net_file)
    key = f"{net.resolve()}|{net.stat().st_mtime_ns}|{lo}|{hi}"
    path = CACHE_DIR / f"{net.name.split('.')[0]}_{hashlib.md5(key.encode()).hexdigest()[:10]}.add.xml"
    if not path.exists():
        build_actuated_additional(sc.net_file, lo, hi, path)
    return sc.with_(actuated_additional=str(path))


def activate_program(sumo_env, program_id: str) -> list[str]:
    """Fuerza `program_id` en cada semáforo que lo tenga. Devuelve los semáforos donde NO existe."""
    missing = []
    conn = sumo_env.sumo
    for ts_id in sumo_env.traffic_signals:
        if program_id in {lg.programID for lg in conn.trafficlight.getAllProgramLogics(ts_id)}:
            conn.trafficlight.setProgram(ts_id, program_id)
        else:
            missing.append(ts_id)
    return missing
