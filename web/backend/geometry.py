"""Geometria de la red para el frontend: net.xml -> JSON (cacheado por archivo).

Formato (coordenadas SUMO x/y en metros, y hacia el norte):
    {"scenario", "bbox": [minx, miny, maxx, maxy], "projected": bool,
     "lanes":  [{"id", "edge", "name", "shape": [[x, y], ...], "width", "allow_passenger"}],
     "edges":  [{"id", "name", "from", "to", "shape"}],
     "junctions": [{"id", "type", "shape"}],
     "tls":    [{"id", "x", "y", "name", "links": [[indice_en_el_estado, carril, x, y, dir, carril_salida], ...]}]}
`dir` es la direccion SUMO del movimiento: "s" recto, "l"/"L" izquierda, "r"/"R" derecha, "t" vuelta en U.
Si la red tiene proyeccion geografica se agregan "lon"/"lat" a cada TLS y "bbox_lonlat".
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import sumolib

_CACHE: dict[tuple[str, float], dict] = {}
_NET_CACHE: dict[tuple[str, float], "sumolib.net.Net"] = {}
_LOCK = threading.Lock()


def _key(net_file: str) -> tuple[str, float]:
    p = Path(net_file)
    return str(p.resolve()), p.stat().st_mtime


def read_net(net_file: str):
    """sumolib Net con cache por (ruta, mtime). Lo comparten geometria y demanda."""
    k = _key(net_file)
    with _LOCK:
        if k not in _NET_CACHE:
            _NET_CACHE[k] = sumolib.net.readNet(net_file, withPrograms=True)
        return _NET_CACHE[k]


def tls_names(net_file: str) -> dict[str, str]:
    """`tls_names.json` (tls_id -> "Reforma y 12 calle") junto a la red, si existe."""
    f = Path(net_file).with_name("tls_names.json")
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def _can_project(net) -> bool:
    """La red trae proyeccion geografica Y se puede usar (sumolib necesita pyproj, que es opcional)."""
    if not net.hasGeoProj():
        return False
    try:
        net.convertXY2LonLat(*net.getBoundary()[:2])
        return True
    except Exception:
        return False


def _pts(shape, nd: int = 2) -> list[list[float]]:
    return [[round(float(x), nd), round(float(y), nd)] for x, y in shape]


def _direction(in_lane, out_lane) -> str:
    """Direccion SUMO de la conexion in_lane -> out_lane ("s", "l", "r", "t", "L", "R"); "s" si no se halla."""
    for c in in_lane.getOutgoing():
        if c.getToLane().getID() == out_lane.getID():
            return c.getDirection() or "s"
    return "s"


def export_network(net_file: str, scenario: str | None = None) -> dict:
    """Exporta la red a un dict serializable a JSON. Cacheado por archivo."""
    k = _key(net_file)
    with _LOCK:
        hit = _CACHE.get(k)
    if hit is not None:
        return hit
    net = read_net(net_file)
    projected = _can_project(net)

    lanes, edges = [], []
    for e in net.getEdges(withInternal=False):
        eid = e.getID()
        name = e.getName() or eid
        edges.append(
            {
                "id": eid,
                "name": name,
                "from": e.getFromNode().getID(),
                "to": e.getToNode().getID(),
                "shape": _pts(e.getRawShape() if hasattr(e, "getRawShape") else e.getShape()),
            }
        )
        for ln in e.getLanes():
            lanes.append(
                {
                    "id": ln.getID(),
                    "edge": eid,
                    "name": name,
                    "shape": _pts(ln.getShape()),
                    "width": round(float(ln.getWidth()), 2),
                    "allow_passenger": bool(ln.allows("passenger")),
                }
            )

    junctions = [
        {"id": n.getID(), "type": n.getType(), "shape": _pts(n.getShape())}
        for n in net.getNodes()
        if n.getShape()
    ]

    names = tls_names(net_file)
    tls = []
    for t in net.getTrafficLights():
        conns = t.getConnections()  # [(inLane, outLane, linkIndex)]
        nodes = {c[0].getEdge().getToNode() for c in conns}
        xs = [n.getCoord()[0] for n in nodes] or [0.0]
        ys = [n.getCoord()[1] for n in nodes] or [0.0]
        x, y = sum(xs) / len(xs), sum(ys) / len(ys)
        entry = {
            "id": t.getID(),
            "x": round(x, 2),
            "y": round(y, 2),
            "name": names.get(t.getID(), t.getID()),
            "links": [
                [
                    int(idx),
                    lane.getID(),
                    round(float(lane.getShape()[-1][0]), 2),
                    round(float(lane.getShape()[-1][1]), 2),
                    _direction(lane, out),
                    out.getID(),
                ]
                for lane, out, idx in sorted(conns, key=lambda c: c[2])
            ],
        }
        if projected:
            entry["lon"], entry["lat"] = (round(v, 7) for v in net.convertXY2LonLat(x, y))
        tls.append(entry)

    minx, miny, maxx, maxy = net.getBoundary()
    out = {
        "scenario": scenario,
        "bbox": [round(minx, 2), round(miny, 2), round(maxx, 2), round(maxy, 2)],
        "projected": projected,
        "lanes": lanes,
        "edges": edges,
        "junctions": junctions,
        "tls": tls,
    }
    if projected:
        lo0, la0 = net.convertXY2LonLat(minx, miny)
        lo1, la1 = net.convertXY2LonLat(maxx, maxy)
        out["bbox_lonlat"] = [round(lo0, 7), round(la0, 7), round(lo1, 7), round(la1, 7)]
    with _LOCK:
        _CACHE[k] = out
    return out
