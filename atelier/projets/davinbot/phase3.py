"""DaVinBot, phase 3 NEMA : J1 + J2 (M1) + J3 (M1) motorises, poignet oriente a la main.

Sans moteur, un axe planetaire tourne librement. Le BLOQUEUR prend la place exacte du NEMA du poignet : semelle vissee sur
les 4 trous M3 du moteur + tige + pignon d'origine. Le pignon reste engrene dans la roue d'entree, donc l'axe est tenu.
Pour reorienter : devisser, tourner l'axe, revisser. Plus tard, le NEMA reprend sa place sans changer une autre piece.
Sur J2/J3, le moteur rapide M2 et son pignon sont retires : le cliquet d'origine tient la roue M2, le differentiel
transmet alors tout le couple de M1.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import trimesh
import manifold3d as mf

from atelier.noyau.c3d import vers_trimesh, vers_manifold

PACK = Path(__file__).resolve().parents[3] / "data" / "bases" / "davinbot_a7a7f0a8e7.zip"
RETIRES = ("J2_nema17_M2", "J2_mks_M2", "J2_zone_mks_M2", "J2_pignon_M2", "J3_nema17_M2", "J3_mks_M2", "J3_zone_mks_M2", "J3_pignon_M2")
for _j in ("J4", "J5", "J6"):
    RETIRES += (f"{_j}_nema17", f"{_j}_mks", f"{_j}_zone_mks", f"{_j}_pignon_moteur")
E_SEMELLE = 5.0
R_TIGE = 4.5
TROU_M3 = 1.7
ENTRAXE = 15.5                                       # NEMA 17 : trous a 31 mm


def bloqueur(z, joints, q, j):
    """Renvoie (maillage monde, rapport de controle) pour l'axe j."""
    lire = lambda n: trimesh.load(io.BytesIO(z.read(n)), file_type="stl", force="mesh")
    T = np.asarray(next(x for x in joints if x["name"] == j)["T"], float)
    Ti = np.linalg.inv(T)
    loc = lambda n: lire(f"view/{n}.stl").apply_transform(Ti)
    moteur, pignon, flasque = loc(f"{j}_nema17"), loc(f"{j}_pignon_moteur"), loc(f"{j}_flasque_arriere")
    cx, cy = (pignon.bounds[0][:2] + pignon.bounds[1][:2]) / 2
    z_face = flasque.bounds[0][2]                    # face arriere du flasque, ou le moteur s'appuie
    z_p0, z_p1 = pignon.bounds[0][2], pignon.bounds[1][2]
    # la semelle s'oriente comme le carter moteur (l'emprise xy du NEMA donne le carre, on prend les axes locaux)
    semelle = mf.Manifold.cube((42.0, 42.0, E_SEMELLE), True).translate((cx, cy, z_face - E_SEMELLE / 2))
    for sx in (-1, 1):
        for sy in (-1, 1):
            semelle = semelle - mf.Manifold.cylinder(E_SEMELLE + 2, TROU_M3, TROU_M3, 24).translate((cx + sx * ENTRAXE, cy + sy * ENTRAXE, z_face - E_SEMELLE - 1))
    tige = mf.Manifold.cylinder(z_p0 + 2.0 - z_face + 0.01, R_TIGE, R_TIGE, 48).translate((cx, cy, z_face - 0.01))
    plein = mf.Manifold.cylinder(z_p1 - z_p0, R_TIGE, R_TIGE, 48).translate((cx, cy, z_p0))   # rebouche l'alesage du pignon
    b = mf.Manifold.batch_boolean([semelle, tige, plein, vers_manifold(pignon)], mf.OpType.Add)
    return b, T, {"axe": j, "centre": [round(float(cx), 2), round(float(cy), 2)], "z_face": round(float(z_face), 2),
                  "moteur_z": [round(float(moteur.bounds[0][2]), 2), round(float(moteur.bounds[1][2]), 2)]}
