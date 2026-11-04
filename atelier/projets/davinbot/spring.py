"""Compensation de gravite de l'epaule (J2) par ressort de traction.

Montage « longueur libre nulle » : un cable part de la console du bras (B), passe sur une poulie
en tete d'un mat fixe sur la tourelle (A) et descend vers un ressort de traction loge dans le mat
via un palan 2:1 (course divisee par 2). Couple de rappel = k.|AB| x bras de levier : il suit la
loi en sinus de la gravite -> compensation quasi parfaite sur toute la plage. La raideur et la longueur libre sont
dimensionnees sur le couple de gravite REEL (masses et centres de gravite du build) pour
minimiser le couple residuel que J2 doit fournir sur toute sa plage de rotation.
"""
from __future__ import annotations

import math

import numpy as np

from .cad.util import SCREW, box, cyl, cut_all, fuse_all
from .parts.model import Part

G = 9.81


def layout(cfg, tur, arm, T2, z2):
    """Points d'ancrage (monde, pose zero) + consoles imprimees."""
    o2 = T2[:3, 3]
    xa = min(tur.x0, arm.x0) - 14.0 - 9.0            # plan du ressort, hors des segments et des brides
    y_pl = (tur.y0 + tur.y1) / 2
    h_a = cfg["j2_spring_h"]                         # ancrage tourelle au-dessus de l'axe
    r_b = cfg["j2_spring_r"]                         # ancrage bras le long du bras
    A = np.array([xa, y_pl, z2 + h_a])
    B = np.array([xa, arm.y0 + 12.0, z2 + r_b])       # cable legerement incline (y) : degage le mat
    parts = []
    # console tourelle : patte sur la face -X, jusqu'au plan du ressort
    za = z2 + h_a
    A[2] = za
    zb0 = tur.z1 - 40                                  # pied du mat, visse sur la tourelle
    mast = fuse_all([box(xa - 10, tur.x0, y_pl - 13, y_pl + 13, zb0, za + 12),
                     cyl(26.0, 16.0, -8).rotate((0, 0, 0), (1, 0, 0), -90).translate((xa, y_pl, za))])
    mast = cut_all(mast, [
        box(xa - 6, tur.x0 - 4, y_pl - 9, y_pl + 9, zb0 + 4, za - 14),              # logement du ressort
        box(xa - 2.5, xa + 2.5, y_pl - 7, y_pl + 7, za - 12, za + 14),                # gorge de la poulie
        cyl(5.2, 40, -20).rotate((0, 0, 0), (1, 0, 0), -90).translate((xa, y_pl, za)),  # axe de poulie d5
        cyl(SCREW["M4"]["clear"], 30, -15).rotate((0, 0, 0), (0, 1, 0), 90).translate((tur.x0 - 2, y_pl - 7, zb0 + 12)),
        cyl(SCREW["M4"]["clear"], 30, -15).rotate((0, 0, 0), (0, 1, 0), 90).translate((tur.x0 - 2, y_pl + 7, zb0 + 12)),
        cyl(SCREW["M4"]["clear"], 30, -15).rotate((0, 0, 0), (0, 1, 0), 90).translate((tur.x0 - 2, y_pl - 7, zb0 + 30)),
        cyl(SCREW["M4"]["clear"], 30, -15).rotate((0, 0, 0), (0, 1, 0), 90).translate((tur.x0 - 2, y_pl + 7, zb0 + 30))])
    parts.append(Part(id="RESSORT_mat", name="Compensation J2 - mat + poulie (tourelle)", group="RESSORT",
                      body=1, shape=mast, category="structure",
                      notes="PETG 60 %. Loge le ressort de traction et son palan 2:1 ; poulie d20 sur axe d5."))
    parts.append(Part(id="RESSORT_poulie", name="Compensation J2 - poulie d20 (roulement 625)", group="RESSORT",
                      body=1, shape=cut_all(cyl(20.0, 4.5, -2.25).rotate((0, 0, 0), (1, 0, 0), -90).translate((xa, y_pl, za)),
                                            [cyl(16.0, 5.0, -2.5).rotate((0, 0, 0), (1, 0, 0), -90).translate((xa, y_pl, za))]),
                      kind="vitamin", category="bearing"))
    # console bras : equerre qui revient dans le plan du ressort (passe a cote du carter J2)
    yb0 = min(y_pl - 10, arm.y0 + 4)
    c2 = box(xa - 6, arm.x0, arm.y0 + 2, arm.y0 + 22, B[2] - 12, B[2] + 12)
    c2 = cut_all(c2, [cyl(5.2, 30, -15).rotate((0, 0, 0), (0, 1, 0), 90).translate((xa - 1, B[1], B[2])),
                      cyl(SCREW["M4"]["clear"], 40, -20).rotate((0, 0, 0), (0, 1, 0), 90).translate((arm.x0 - 2, arm.y0 + 12, B[2] - 6)),
                      cyl(SCREW["M4"]["clear"], 40, -20).rotate((0, 0, 0), (0, 1, 0), 90).translate((arm.x0 - 2, arm.y0 + 12, B[2] + 6))])
    parts.append(Part(id="RESSORT_console_bras", name="Compensation J2 - console bras", group="RESSORT",
                      body=2, shape=c2, category="structure", notes="Equerre en PETG 60 %, 4 perimetres."))
    return {"A": A, "B": B, "o": o2, "axis": T2[:3, 2]}, parts


def _rot(axis, t):
    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def gravity_curve(joint, masses, coms, bodies, thetas, extra=None):
    """Couple de gravite sur l'axe (N.m) pour chaque angle (bras aval rigide)."""
    o = np.array(joint["origin"], float)
    a = np.array(joint["axis"], float)
    pts = [(masses[pid], coms[pid]) for pid in masses if bodies[pid] >= joint["body"] and masses[pid] > 0]
    if extra:
        pts += extra
    out = []
    for t in thetas:
        R = _rot(a, t)
        tau = 0.0
        for m, c in pts:
            r = R @ (np.asarray(c) - o) / 1000.0
            tau += np.dot(np.cross(r, [0, 0, -m * G]), a)
        out.append(tau)
    return np.array(out)


def size_spring(sp, joint, masses, coms, bodies, payload_pt, payload, limit_deg, fraction=1.0):
    """Choisit k (N/mm) et L0 (mm) minimisant le couple residuel max sur la plage."""
    th = np.radians(np.linspace(-limit_deg, limit_deg, 73))
    extra = [(payload * 0.5, payload_pt)]            # compense le bras + la moitie de la charge
    Gc = gravity_curve(joint, masses, coms, bodies, th, extra)
    o, a = sp["o"], sp["axis"]
    A, B = sp["A"], sp["B"]
    Ls, arms = [], []
    for t in th:
        Bt = o + _rot(a, t) @ (B - o)
        dvec = A - Bt
        L = np.linalg.norm(dvec)
        u = dvec / L
        # couple d'une force unitaire (tension) appliquee en B, dirigee vers A
        arms.append(np.dot(np.cross((Bt - o) / 1000.0, u), a))
        Ls.append(L)
    Ls, arms = np.array(Ls), np.array(arms)
    best = None
    for L0 in (0.0,):                                  # cable + poulie : longueur libre nulle
        ext = Ls - L0                                  # mm (toujours > 0 : ressort tendu)
        S_unit = ext * arms                            # couple par N/mm de raideur
        # moindres carres : tau_res = -Gc - k S_unit (le ressort s'oppose a la gravite)
        k = -np.dot(Gc, S_unit) / np.dot(S_unit, S_unit)
        if k <= 0:
            continue
        k *= fraction
        res = Gc + k * S_unit
        m = np.max(np.abs(res))
        if best is None or m < best[0]:
            best = (m, k, L0, res)
    m, k, L0, res = best
    Fmax = k * (Ls.max() - L0)
    return {"k_N_mm": round(float(k), 3), "L0_mm": round(float(L0), 1), "course_mm": round(float(Ls.max() - Ls.min()), 1),
            "effort_max_N": round(float(Fmax), 1), "couple_gravite_max_Nm": round(float(np.max(np.abs(Gc))), 2),
            "couple_residuel_max_Nm": round(float(m), 2),
            "reduction_pct": round(100 * (1 - m / np.max(np.abs(Gc))), 1),
            "courbe": {"theta_deg": np.degrees(th).round(1).tolist(), "gravite": Gc.round(2).tolist(),
                       "residuel": res.round(2).tolist()},
            "A": sp["A"].round(2).tolist(), "B": sp["B"].round(2).tolist(),
            "ressort": (f"cable Dyneema d1.5 + poulie : raideur equivalente {k:.2f} N/mm ; ressort de traction "
                        f"{4 * k:.2f} N/mm via palan 2:1 (course {(Ls.max() - Ls.min()) / 2:.0f} mm), "
                        f"tension cable maxi {Fmax:.0f} N")}
