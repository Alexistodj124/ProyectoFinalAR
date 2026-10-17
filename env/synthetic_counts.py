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
# traffic that turns into the cross street, and cross-street movement split.
PROFILES = {
    "pico": dict(
        nb_in=1800, sb_in=1600,
        cross={"C15": 450, "C14": 500, "C12": 700, "C10": 650, "C06": 550},
        turn={"C15": (0.12, 0.13), "C14": (0.13, 0.12), "C12": (0.14, 0.18), "C10": (0.18, 0.14), "C06": (0.12, 0.15)},
        cross_split=(0.68, 0.16, 0.16),  # recto, izquierda, derecha
    ),
    "mediodia": dict(  # ~65 % of the peak, more balanced directions and more turning
        nb_in=1170, sb_in=1120,
        cross={"C15": 310, "C14": 330, "C12": 470, "C10": 440, "C06": 370},
        turn={"C15": (0.16, 0.16), "C14": (0.17, 0.16), "C12": (0.18, 0.21), "C10": (0.21, 0.18), "C06": (0.16, 0.18)},
        cross_split=(0.56, 0.22, 0.22),
    ),
}


def movements(profile: str) -> list[tuple[str, str, str, float]]:
    """[(interseccion, aproximacion, movimiento, veh/h)] consistent along the corridor."""
    P = PROFILES[profile]
    rows, into_nb, into_sb = [], {}, {}
    rs, ri, rd = P["cross_split"]
    for c in CORRIDOR:  # cross streets first: what they inject into Reforma
        cid, q = c["id"], P["cross"][c["id"]]
        xa = "oeste" if c["cross_dir"] == "EB" else "este"
        rows += [(cid, xa, "recto", q * rs), (cid, xa, "izquierda", q * ri), (cid, xa, "derecha", q * rd)]
        # EB (from the west): right -> southbound, left -> northbound; WB the other way round
        into_nb[cid], into_sb[cid] = (q * ri, q * rd) if c["cross_dir"] == "EB" else (q * rd, q * ri)
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
            w = csv.writer(fh)
            w.writerow(["interseccion", "aproximacion", "movimiento", "vehiculos_15min"])
            for inter, ap, mov, vph in movements(profile):
                w.writerow([inter, ap, mov, int(round(vph / 4))])
        print(f"[synthetic_counts] wrote {path}")


if __name__ == "__main__":
    main()
