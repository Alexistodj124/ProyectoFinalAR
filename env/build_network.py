"""Reproducible build of the Av. La Reforma networks (env/net/).

    python -m env.build_network            # corridor + cruce + baseline programs
    python -m env.build_network --osm-raw  # also try the direct OSM import (diagnostic only)

Pipeline (see env/net/README.md for the rationale):
1. Read env/net/osm/reforma_raw.osm.xml (Overpass extract; downloaded if missing) and take
   from it the real coordinates of the 5 signalized crossings (mean of their
   highway=traffic_signals nodes), the corridor ends (Plaza Obelisco, 5a calle) and the
   direction of each one-way cross street.
2. Write a clean plain-XML corridor (nod/edg/tll) with that geometry and the OSM lane
   counts, and run netconvert -> env/net/reforma.net.xml. Each crossing of the divided
   boulevard is ONE node and ONE TLS; connections and link indices are explicit, so
   the green phases are exactly the ones defined below (2-3 per TLS, heterogeneous).
3. Baseline programs: <net>_fixed.add.xml (synthetic "field-measured" common cycle with
   Webster splits from env/conteos/pico.csv + green-wave offsets, PROVISIONAL) and
   <net>_actuated.add.xml (type="actuated").
4. Cut the busiest crossing (C12) out of the corridor with --keep-edges.explicit ->
   env/net/cruce.net.xml (+ its two add files).

The direct OSM import (netconvert --osm-files ... --tls.guess-signals --tls.join
--junctions.join --geometry.remove --ramps.guess) is kept as `--osm-raw`: on this area it
yields 18 TLS (auxiliary roads, links and median U-turns) and merges 15+14 calle into one
TLS with a 444 s cycle, so it is not usable for RL without days of netedit work
(PLAN §14 mitigation -> hand-built corridor with real geometry).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NET_DIR = ROOT / "env" / "net"
OSM_FILE = NET_DIR / "osm" / "reforma_raw.osm.xml"
COUNTS_DIR = ROOT / "env" / "conteos"
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = (14.585, -90.522, 14.612, -90.503)  # S, W, N, E

# ---------------------------------------------------------------------------------
# Corridor specification (south -> north). OSM ids are the provenance of each value.
#   cross_dir: one-way direction of the cross street ("EB" = eastbound, "WB" = westbound)
#   x_in / x_out: lanes of the cross street approach / exit (OSM lanes=*)
#   pocket: Reforma direction with an exclusive left-turn lane (4th lane) or None
#   protected: Reforma direction with a protected (leading) left phase or None
# ---------------------------------------------------------------------------------
CORRIDOR = [
    dict(id="C15", name="Reforma y 15 calle", cross="15 calle", cross_dir="WB", x_in=3, x_out=2,
         pocket=None, protected=None, osm_signals=[410455814, 516392127], osm_way=676616368,
         fallback=(14.59720, -90.51716)),
    dict(id="C14", name="Reforma y 14 calle", cross="14 calle", cross_dir="EB", x_in=3, x_out=2,
         pocket=None, protected="SB", osm_signals=[410453351, 481805124, 481805128, 481805139],
         osm_way=400025518, fallback=(14.59827, -90.51693)),
    dict(id="C12", name="Reforma y 12 calle", cross="12 calle", cross_dir="EB", x_in=3, x_out=3,
         pocket="SB", protected="SB", osm_signals=[410407928, 410455570, 3820122586, 3820122589],
         osm_way=641025046, fallback=(14.60097, -90.51646)),
    dict(id="C10", name="Reforma y 10a calle", cross="10a calle", cross_dir="WB", x_in=4, x_out=2,
         pocket="NB", protected="NB", osm_signals=[410454143, 516392077, 516392086], osm_way=380916947,
         fallback=(14.60362, -90.51597)),
    dict(id="C06", name="Reforma y 6a calle", cross="6a calle", cross_dir="EB", x_in=3, x_out=2,
         pocket=None, protected="SB", osm_signals=[410451994, 412283345, 516392066, 4026335921, 4026335922],
         osm_way=754396843, fallback=(14.60847, -90.51512)),
]
SOUTH_END = dict(osm=410414371, fallback=(14.59511, -90.51786))  # Plaza Obelisco signal (16 calle)
NORTH_END = dict(osm=412196554, fallback=(14.60985, -90.51487))  # Reforma y 5a calle signal
BUSIEST = "C12"  # busiest crossing by counted demand (see env/conteos) -> cruce.net.xml

REFORMA_LANES, REFORMA_SPEED, CROSS_SPEED = 3, 13.89, 11.11  # 50 km/h, 40 km/h
X_APPROACH_M, X_EXIT_M = 170.0, 150.0  # one block of each cross street
SAT_FLOW = 1800.0  # veh/h/lane (Webster)
CYCLE, YELLOW = 110, 3  # common "measured" cycle (PROVISIONAL)


# --------------------------------------------------------------------- OSM reading
def download_osm(path: Path = OSM_FILE) -> None:
    s, w, n, e = BBOX
    q = f'[out:xml][timeout:60];(way["highway"]({s},{w},{n},{e});>;);out body;'
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": "CC3104-UVG-student-project/1.0"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(urllib.request.urlopen(req, timeout=120).read())


def read_osm(path: Path = OSM_FILE):
    if not path.exists():
        try:
            download_osm(path)
        except Exception as exc:  # offline: fall back to the coordinates stored above
            print(f"[build_network] OSM unavailable ({exc}); using fallback coordinates")
            return {}, {}
    root = ET.parse(path).getroot()
    nodes = {int(n.get("id")): (float(n.get("lat")), float(n.get("lon"))) for n in root.iter("node")}
    ways = {int(w.get("id")): [int(nd.get("ref")) for nd in w.iter("nd")] for w in root.iter("way")}
    return nodes, ways


def geo_layout(nodes, ways) -> dict:
    """lat/lon of every corridor point, taken from OSM when available."""
    def mean(ids, fb):
        pts = [nodes[i] for i in ids if i in nodes]
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else fb

    lay = {"S": mean([SOUTH_END["osm"]], SOUTH_END["fallback"]), "N": mean([NORTH_END["osm"]], NORTH_END["fallback"])}
    for c in CORRIDOR:
        lay[c["id"]] = mean(c["osm_signals"], c["fallback"])
        w = ways.get(c["osm_way"])
        lay[c["id"] + "_way0"] = nodes[w[0]] if w and w[0] in nodes else None
    return lay


# ------------------------------------------------------------- local metric frame
LAT0, LON0 = 14.6025, -90.5160
KX, KY = 111_320 * math.cos(math.radians(LAT0)), 110_574  # m per degree


def to_xy(p):
    return ((p[1] - LON0) * KX, (p[0] - LAT0) * KY)


def to_lonlat(x, y):
    return (LON0 + x / KX, LAT0 + y / KY)


# --------------------------------------------------------------- plain XML writer
def _cross_vector(c, lay, axis):
    """Unit vector of the cross street's travel direction (from its OSM approach way)."""
    ax, ay = axis
    east = (ay, -ax)  # right-hand normal of the northbound axis
    if lay.get(c["id"] + "_way0"):
        p0, pc = to_xy(lay[c["id"] + "_way0"]), to_xy(lay[c["id"]])
        vx, vy = pc[0] - p0[0], pc[1] - p0[1]
        n = math.hypot(vx, vy)
        vx, vy = vx / n, vy / n
    else:
        vx, vy = (-east[0], -east[1]) if c["cross_dir"] == "WB" else east
    # sanity: the direction must agree with cross_dir
    s = vx * east[0] + vy * east[1]
    assert (s > 0) == (c["cross_dir"] == "EB"), f"{c['id']}: OSM direction disagrees with cross_dir"
    return vx, vy


def build_plain(lay, out: Path) -> dict:
    """Write reforma.{nod,edg,tll}.xml into `out`; return link metadata per TLS."""
    xy = {k: to_xy(v) for k, v in lay.items() if v and not k.endswith("_way0")}
    s, n = xy["S"], xy["N"]
    axis = ((n[0] - s[0]), (n[1] - s[1]))
    L = math.hypot(*axis)
    axis = (axis[0] / L, axis[1] / L)

    nod, edg, con, tll = [], [], [], []
    chain = ["S"] + [c["id"] for c in CORRIDOR] + ["N"]

    def node(i, p, tls=False):
        lon, lat = to_lonlat(*p)
        t = f' type="traffic_light" tl="{i}" tlType="static"' if tls else ' type="priority"'
        nod.append(f'    <node id="{i}" x="{lon:.7f}" y="{lat:.7f}"{t}/>')

    node("S", s)
    node("N", n)
    for c in CORRIDOR:
        node(c["id"], xy[c["id"]], tls=True)

    def edge(i, a, b, lanes, speed, prio, name):
        edg.append(f'    <edge id="{i}" from="{a}" to="{b}" numLanes="{lanes}" speed="{speed}" '
                   f'priority="{prio}" name="{name}"/>')

    # Reforma: NB and SB carriageways between consecutive nodes (pocket = 4th lane on the block)
    spec = {c["id"]: c for c in CORRIDOR}
    for a, b in zip(chain, chain[1:]):
        nb_l = REFORMA_LANES + (1 if b in spec and spec[b]["pocket"] == "NB" else 0)
        sb_l = REFORMA_LANES + (1 if a in spec and spec[a]["pocket"] == "SB" else 0)
        edge(f"NB_{a}_{b}", a, b, nb_l, REFORMA_SPEED, 3, "Avenida La Reforma")
        edge(f"SB_{b}_{a}", b, a, sb_l, REFORMA_SPEED, 3, "Avenida La Reforma")

    links = {}
    for k, c in enumerate(CORRIDOR):
        cid, p = c["id"], xy[c["id"]]
        vx, vy = _cross_vector(c, lay, axis)
        src, dst = ("W", "E") if c["cross_dir"] == "EB" else ("E", "W")
        node(f"{cid}_{src}", (p[0] - vx * X_APPROACH_M, p[1] - vy * X_APPROACH_M))
        node(f"{cid}_{dst}", (p[0] + vx * X_EXIT_M, p[1] + vy * X_EXIT_M))
        x_in, x_out = f"{cid}_{src}_in", f"{cid}_{dst}_out"
        edge(x_in, f"{cid}_{src}", cid, c["x_in"], CROSS_SPEED, 2, c["cross"])
        edge(x_out, cid, f"{cid}_{dst}", c["x_out"], CROSS_SPEED, 2, c["cross"])

        prev, nxt = chain[k], chain[k + 2]
        nb_in, nb_out = f"NB_{prev}_{cid}", f"NB_{cid}_{nxt}"
        sb_in, sb_out = f"SB_{nxt}_{cid}", f"SB_{cid}_{prev}"
        nb_n = REFORMA_LANES + (c["pocket"] == "NB")
        sb_n = REFORMA_LANES + (c["pocket"] == "SB")
        R = REFORMA_LANES
        conns = []  # (from, to, fromLane, toLane, approach, dir)
        # Reforma through: lane i -> lane i
        conns += [(nb_in, nb_out, i, i, "NB", "s") for i in range(R)]
        conns += [(sb_in, sb_out, i, i, "SB", "s") for i in range(R)]
        # Reforma turns onto the one-way cross street (only legal direction)
        if c["cross_dir"] == "EB":  # exit to the east: NB turns right, SB turns left
            conns.append((nb_in, x_out, 0, 0, "NB", "r"))
            conns.append((sb_in, x_out, sb_n - 1, c["x_out"] - 1, "SB", "l"))
        else:  # exit to the west: SB turns right, NB turns left
            conns.append((sb_in, x_out, 0, 0, "SB", "r"))
            conns.append((nb_in, x_out, nb_n - 1, c["x_out"] - 1, "NB", "l"))
        # cross street: through (lanes merge onto x_out), right / left onto Reforma
        # (lanes beyond the exit width become left-only lanes, so no target lane is fed twice)
        n_thr = min(c["x_in"], c["x_out"])
        conns += [(x_in, x_out, i, i, "X", "s") for i in range(n_thr)]
        right_out, left_out = (sb_out, nb_out) if c["cross_dir"] == "EB" else (nb_out, sb_out)
        conns.append((x_in, right_out, 0, 0, "X", "r"))
        left_lanes = list(range(n_thr, c["x_in"])) or [c["x_in"] - 1]
        conns += [(x_in, left_out, ln, R - 1 - k, "X", "l") for k, ln in enumerate(reversed(left_lanes))]
        # (with a pocket, lane R is left-only: it gets no through link above)
        links[cid] = conns
        for idx, (f, t, fl, tl_, *_r) in enumerate(conns):
            c_xml = f'    <connection from="{f}" to="{t}" fromLane="{fl}" toLane="{tl_}"'
            con.append(c_xml + "/>")
            tll.append(c_xml + f' tl="{cid}" linkIndex="{idx}"/>')

    out.mkdir(parents=True, exist_ok=True)
    (out / "reforma.nod.xml").write_text("<nodes>\n" + "\n".join(nod) + "\n</nodes>\n")
    (out / "reforma.edg.xml").write_text("<edges>\n" + "\n".join(edg) + "\n</edges>\n")
    (out / "reforma.con.xml").write_text("<connections>\n" + "\n".join(con) + "\n</connections>\n")
    progs = [tl_logic(cid, "0", "static", phase_list(spec[cid], links[cid], default_greens(spec[cid])))
             for cid in links]
    (out / "reforma.tll.xml").write_text("<tlLogics>\n" + "\n".join(progs) + "\n" + "\n".join(tll) + "\n</tlLogics>\n")
    return links


# ------------------------------------------------------------------ signal programs
def green_phases(c) -> list[dict]:
    """Green phases as {(approach, dir): 'G'|'g'}; unlisted movements are red.
    'g' = permissive (yields to opposing traffic)."""
    turn_nb = "r" if c["cross_dir"] == "EB" else "l"
    turn_sb = "l" if c["cross_dir"] == "EB" else "r"
    perm = lambda d: "G" if d == "r" else "g"  # noqa: E731  right turns onto a one-way street don't yield
    reforma = {("NB", "s"): "G", ("SB", "s"): "G", ("NB", turn_nb): perm(turn_nb), ("SB", turn_sb): perm(turn_sb)}
    cross = {("X", "s"): "G", ("X", "l"): "G", ("X", "r"): "G"}
    if not c["protected"]:
        return [reforma, cross]
    d = c["protected"]
    lead = {(d, "s"): "G", (d, "l"): "G"}
    return [reforma, lead, cross]


def phase_list(c, conns, greens) -> list[tuple[int, str]]:
    """[(duration, state)] alternating green / yellow (sumo-rl expects that order)."""
    gp = green_phases(c)
    states = ["".join(g.get((a, d), "r") for (*_x, a, d) in conns) for g in gp]
    out = []
    for i, st in enumerate(states):
        nxt = states[(i + 1) % len(states)]
        out.append((greens[i], st))
        out.append((YELLOW, "".join("y" if ch in "Gg" and nch == "r" else ch for ch, nch in zip(st, nxt))))
    return out


def default_greens(c) -> list[int]:
    return [40, 25] if not c["protected"] else [35, 12, 25]


def tl_logic(cid, pid, typ, phases, offset=0, actuated=False, c=None) -> str:
    rows = []
    for k, (dur, st) in enumerate(phases):
        if actuated and k % 2 == 0:
            gi = k // 2
            is_cross = gi == len(phases) // 2 - 1
            is_lead = c["protected"] and gi == 1
            mn, mx = (8, 25) if is_lead else ((10, 50) if is_cross else (15, 70))
            rows.append(f'        <phase duration="{min(max(dur, mn), mx)}" minDur="{mn}" maxDur="{mx}" state="{st}"/>')
        else:
            rows.append(f'        <phase duration="{dur}" state="{st}"/>')
    params = ('\n        <param key="max-gap" value="3.0"/>\n        <param key="detector-gap" value="2.0"/>'
              if actuated else "")
    return (f'    <tlLogic id="{cid}" type="{typ}" programID="{pid}" offset="{offset}">{params}\n'
            + "\n".join(rows) + "\n    </tlLogic>")


def read_counts(profile="pico") -> dict:
    f = COUNTS_DIR / f"{profile}.csv"
    if not f.exists():
        return {}
    out = {}
    with f.open() as fh:
        for r in csv.DictReader(line for line in fh if not line.startswith("#")):
            out.setdefault((r["interseccion"], r["aproximacion"]), {})[r["movimiento"]] = 4 * float(r["vehiculos_15min"])
    return out


APPROACH_NAME = {"NB": "sur", "SB": "norte"}


def webster_greens(c, counts) -> list[int]:
    """Green split proportional to the critical flow ratio y_i = q_i / (lanes * s) (Webster)."""
    cid = c["id"]
    if not counts:
        return default_greens(c)
    xa = "oeste" if c["cross_dir"] == "EB" else "este"
    q = lambda a: counts.get((cid, a), {})  # noqa: E731
    nb, sb, x = q("sur"), q("norte"), q(xa)
    y_x = sum(x.values()) / (c["x_in"] * SAT_FLOW)
    if not c["protected"]:
        y = [max(sum(nb.values()), sum(sb.values())) / (REFORMA_LANES * SAT_FLOW), y_x]
        mins = [30, 15]
    else:
        d = q(APPROACH_NAME[c["protected"]])
        o = sb if c["protected"] == "NB" else nb
        y_left = d.get("izquierda", 0) / (SAT_FLOW * (1.0 if c["pocket"] else 0.8))
        y = [max(o.get("recto", 0) + o.get("derecha", 0), d.get("recto", 0)) / (REFORMA_LANES * SAT_FLOW), y_left, y_x]
        mins = [30, 8, 15]
    avail = CYCLE - YELLOW * len(y)
    g = [max(m, round(avail * yi / sum(y))) for yi, m in zip(y, mins)]
    g[0] += avail - sum(g)  # Reforma absorbs the rounding so the cycle is exact
    return g


def write_programs(net_stem: str, links: dict, tls_ids: list[str], offsets: dict) -> None:
    spec = {c["id"]: c for c in CORRIDOR}
    counts = read_counts("pico")
    fixed, act = [], []
    for cid in tls_ids:
        c, conns = spec[cid], links[cid]
        g = webster_greens(c, counts)
        fixed.append(tl_logic(cid, "fixed", "static", phase_list(c, conns, g), offsets.get(cid, 0)))
        act.append(tl_logic(cid, "actuated", "actuated", phase_list(c, conns, g), 0, actuated=True, c=c))
    hdr = ("<!-- PROVISIONAL: ciclo comun de {C} s 'medido en campo' SINTETICO. Reparto de verde\n"
           "     proporcional a la demanda (Webster, conteos env/conteos/pico.csv) y offsets de onda verde\n"
           "     hacia el norte a 40 km/h. Reemplazar por los tiempos cronometrados (PLAN 6.1). -->\n").format(C=CYCLE)
    (NET_DIR / f"{net_stem}_fixed.add.xml").write_text(
        "<additional>\n" + hdr + "\n".join(fixed) + "\n</additional>\n")
    hdr_a = "<!-- Programa actuado de SUMO (extiende el verde con detectores automaticos), mismas fases. -->\n"
    (NET_DIR / f"{net_stem}_actuated.add.xml").write_text("<additional>\n" + hdr_a + "\n".join(act) + "\n</additional>\n")


# ----------------------------------------------------------------------- netconvert
def netconvert(out: Path, *args) -> None:
    cmd = ["netconvert", "--no-warnings", "--no-turnarounds", *map(str, args), "-o", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"netconvert failed:\n{' '.join(cmd)}\n{r.stderr}")
    # drop netconvert's header (timestamp + absolute paths) so rebuilds are byte-identical
    txt = Path(out).read_text()
    txt = re.sub(r"<!-- generated on .*?-->", "<!-- generated by env/build_network.py (SUMO netconvert) -->", txt,
                 count=1, flags=re.S)
    Path(out).write_text(txt)


def build_corridor(osm=OSM_FILE) -> dict:
    nodes, ways = read_osm(osm)
    lay = geo_layout(nodes, ways)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        links = build_plain(lay, td)
        netconvert(NET_DIR / "reforma.net.xml", "--node-files", td / "reforma.nod.xml", "--edge-files", td / "reforma.edg.xml",
                   "--connection-files", td / "reforma.con.xml", "--tllogic-files", td / "reforma.tll.xml", "--proj.plain-geo", "--proj.utm", "--junctions.corner-detail", 5,
                   "--default.junctions.radius", 8, "--tls.ignore-internal-junction-jam",
                   "--output.street-names")
    # Green-wave offsets for the northbound direction (distance from C15 / progression speed)
    xy = {c["id"]: to_xy(lay[c["id"]]) for c in CORRIDOR}
    p0 = xy[CORRIDOR[0]["id"]]
    offsets = {cid: int(round(math.dist(p0, p) / 11.1)) % CYCLE for cid, p in xy.items()}
    ids = [c["id"] for c in CORRIDOR]
    write_programs("reforma", links, ids, offsets)
    (NET_DIR / "tls_names.json").write_text(
        json.dumps({c["id"]: c["name"] for c in CORRIDOR}, ensure_ascii=False, indent=2) + "\n")
    spacing = {f"{a}-{b}": round(math.dist(xy[a], xy[b])) for a, b in zip(ids, ids[1:])}
    return {"links": links, "spacing_m": spacing, "layout": lay}


def build_cruce(links: dict, tls: str = BUSIEST) -> None:
    keep = sorted({f for (f, *_r) in links[tls]} | {t for (_f, t, *_r) in links[tls]})
    # the neighbouring TLS nodes become plain fringe nodes of the cut
    others = [c["id"] for c in CORRIDOR if c["id"] != tls and any(c["id"] in e.split("_")[1:] for e in keep)]
    netconvert(NET_DIR / "cruce.net.xml", "--sumo-net-file", NET_DIR / "reforma.net.xml",
               "--keep-edges.explicit", ",".join(keep), "--tls.unset", ",".join(others))
    # same link indices as in the corridor (checked in tests/test_env_reforma.py)
    write_programs("cruce", links, [tls], {})


def build_osm_raw(out: Path) -> None:
    """Direct OSM import with the PLAN §6.1 options (diagnostic; not used by the scenarios)."""
    s, w, n, e = 14.5960, -90.5195, 14.6095, -90.5130
    netconvert(out, "--osm-files", OSM_FILE, "--keep-edges.by-vclass", "passenger",
               "--remove-edges.by-type", "highway.service,highway.footway,highway.pedestrian,highway.steps,"
               "highway.path,highway.cycleway,highway.track,highway.living_street",
               "--keep-edges.in-geo-boundary", f"{w},{s},{e},{n}", "--remove-edges.isolated",
               "--tls.guess-signals", "--tls.join", "--tls.join-dist", 60, "--junctions.join",
               "--geometry.remove", "--ramps.guess", "--tls.discard-simple", "--edges.join", "--osm.turn-lanes")
    import sumolib

    net = sumolib.net.readNet(str(out), withPrograms=True)
    print(f"[osm-raw] {out}: {len(net.getEdges())} edges, {len(net.getTrafficLights())} TLS")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--osm-raw", metavar="OUT", nargs="?", const=str(Path(tempfile.gettempdir()) / "reforma_osm_raw.net.xml"),
                    help="also run the direct OSM import (diagnostic)")
    args = ap.parse_args(argv)
    if not (COUNTS_DIR / "pico.csv").exists():
        from env.synthetic_counts import main as gen_counts

        gen_counts([])
    info = build_corridor()
    build_cruce(info["links"])
    print("[build_network] wrote", ", ".join(p.name for p in sorted(NET_DIR.glob("*.xml"))))
    print("[build_network] spacing (m):", info["spacing_m"])
    if args.osm_raw:
        build_osm_raw(Path(args.osm_raw))


if __name__ == "__main__":
    main()
