"""Synthetic (PROVISIONAL) turning-movement counts for the Reforma corridor.

    python -m env.synthetic_counts      # writes env/conteos/{pico,mediodia}.csv

Flows are propagated along the corridor so the counts are mutually consistent: the
northbound volume reaching 14 calle is what left 15 calle straight plus what turned
into Reforma from 15 calle, etc. Replace these files by the real video counts
(PLAN §6.2, see env/conteos/README.md) — nothing else has to change.
"""
from __future__ import annotations

import csv
from pathlib import Path

from env.build_network import CORRIDOR

OUT = Path(__file__).resolve().parent / "conteos"

# Reforma entry volumes (veh/h), cross-street entry volumes (veh/h), share of Reforma
# traffic that turns into the cross street (NB, SB) and cross-street movement split
# (recto, turns into Reforma NB, turns into Reforma SB).
#
# CALIBRATION (PLAN 6.2 "Validar", env/conteos/README.md): v1 (Reforma 1800/1600, cross
# 450-700, 68/16/16) gave a fixed-time corridor travel time of ~160 s per direction vs the
# reference of 330 s NB / 300 s SB (env/validate.py), i.e. a peak far below capacity. v2
# multiplies the Reforma entries by 1.37 (NB x1.22, SB x1.53), keeps the cross streets
# (x0.95 overall: 10a calle 650 -> 500, it was at capacity with its 18 s of green), biases
# the cross-street turns towards the north (morning peak) and lowers the two shared-lane
# permissive lefts that block a through lane of an entry approach (NB left at 15 calle,
# SB left at 6a calle). Together with the vType of env/demand.py this puts fixed-time
# travel time within +-15 % of the reference without gridlock (see the README table).
PROFILES = {
    "pico": dict(
        nb_in=2200, sb_in=2450,
        cross={"C15": 450, "C14": 500, "C12": 700, "C10": 500, "C06": 550},
        turn={"C15": (0.02, 0.13), "C14": (0.13, 0.12), "C12": (0.08, 0.18), "C10": (0.10, 0.14), "C06": (0.12, 0.08)},
        cross_split=(0.58, 0.30, 0.12),  # recto, gira hacia Reforma NB, gira hacia Reforma SB
    ),
    "mediodia": dict(  # ~65 % of the peak, NB-heavier (peak is SB-heavier), more turning, balanced cross turns
        nb_in=1650, sb_in=1350,
        cross={"C15": 300, "C14": 330, "C12": 470, "C10": 330, "C06": 370},
        turn={"C15": (0.04, 0.16), "C14": (0.17, 0.16), "C12": (0.14, 0.21), "C10": (0.16, 0.18), "C06": (0.16, 0.12)},
        cross_split=(0.56, 0.22, 0.22),
    ),
}


def movements(profile: str) -> list[tuple[str, str, str, float]]:
    """[(interseccion, aproximacion, movimiento, veh/h)] consistent along the corridor."""
    P = PROFILES[profile]
    rows, into_nb, into_sb = [], {}, {}
    rs, to_n, to_s = P["cross_split"]  # recto, gira hacia Reforma NB, gira hacia Reforma SB
    for c in CORRIDOR:  # cross streets first: what they inject into Reforma
        cid, q = c["id"], P["cross"][c["id"]]
        xa = "oeste" if c["cross_dir"] == "EB" else "este"
        # EB (from the west): left -> northbound, right -> southbound; WB the other way round
        left, right = (q * to_n, q * to_s) if c["cross_dir"] == "EB" else (q * to_s, q * to_n)
        rows += [(cid, xa, "recto", q * rs), (cid, xa, "izquierda", left), (cid, xa, "derecha", right)]
        into_nb[cid], into_sb[cid] = q * to_n, q * to_s
    f = P["nb_in"]
    for c in CORRIDOR:  # northbound, south -> north
        t = P["turn"][c["id"]][0]
        mov = "derecha" if c["cross_dir"] == "EB" else "izquierda"
        rows += [(c["id"], "sur", "recto", f * (1 - t)), (c["id"], "sur", mov, f * t)]
        f = f * (1 - t) + into_nb[c["id"]]
    f = P["sb_in"]
    for c in reversed(CORRIDOR):  # southbound, north -> south
        t = P["turn"][c["id"]][1]
        mov = "izquierda" if c["cross_dir"] == "EB" else "derecha"
        rows += [(c["id"], "norte", "recto", f * (1 - t)), (c["id"], "norte", mov, f * t)]
        f = f * (1 - t) + into_sb[c["id"]]
    order = {c["id"]: i for i, c in enumerate(CORRIDOR)}
    return sorted(rows, key=lambda r: (order[r[0]], r[1], r[2]))


def main(argv=None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for profile in PROFILES:
        path = OUT / f"{profile}.csv"
        with path.open("w", newline="") as fh:
            fh.write("# SINTETICO - PROVISIONAL (env/synthetic_counts.py). Reemplazar por conteos en video, ver README.md\n")
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["interseccion", "aproximacion", "movimiento", "vehiculos_15min"])
            for inter, ap, mov, vph in movements(profile):
                w.writerow([inter, ap, mov, int(round(vph / 4))])
        print(f"[synthetic_counts] wrote {path}")


if __name__ == "__main__":
    main()
