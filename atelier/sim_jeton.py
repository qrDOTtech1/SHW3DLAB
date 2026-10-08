"""Simulation de la course du jeton : interference jeton / corps tous les 0.25 mm."""
import numpy as np
import cadquery as cq
from .porte_jeton import porte_jeton


def simuler(pcs=None, g=None):
    if pcs is None:
        pcs, g, _ = porte_jeton()
    corps = pcs["corps"].val()
    Rt, z0, H = g["Rt"], g["z0"], g["H"]
    course = g["params"].course
    prof = []
    for c in np.arange(0.0, course + 6.0, 0.25):
        jet = cq.Workplane("XY").circle(Rt).extrude(H - 0.3).translate((c, 0, z0 + 0.15)).val()
        v = corps.intersect(jet).Volume()
        prof.append((round(float(c), 2), round(v, 3)))
    return prof
