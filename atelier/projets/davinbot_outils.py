"""Outils du DaVinBot : bride a pogo pins, bracelet de capteurs, supports et tete de peinture fine.

Tout se monte sur le disque de J6 (4 vis M3 sur cercle d30). Cotes non encore mesurees sur les vraies pieces :
pogo pins, capteur de force (carre 38 x 38 suppose), module laser (25 x 11, trous a 20 mm).
  python -m atelier.projets.davinbot_outils sortie/davinbot_tubes/outils
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import manifold3d as mf
import numpy as np
import trimesh


def bo(x, y, z, cx=0.0, cy=0.0, z0=0.0):
    return mf.Manifold.cube((x, y, z), True).translate((cx, cy, z0 + z / 2))


def cy(d, h, cx=0.0, cy_=0.0, z0=0.0, n=64):
    return mf.Manifold.cylinder(h, d / 2, d / 2, n).translate((cx, cy_, z0))


def somme(L):
    return mf.Manifold.batch_boolean(L, mf.OpType.Add)


CERCLE_J6 = [(15 * math.cos(math.radians(45 + 90 * k)), 15 * math.sin(math.radians(45 + 90 * k))) for k in range(4)]
CERCLE_OUTIL = [(24 * math.cos(math.radians(90 * k)), 24 * math.sin(math.radians(90 * k))) for k in range(4)]
POGO_D = 2.0                      # a ajuster sur les vraies pogo pins


def bride_pogo():
    """Se visse sur J6 ; chaque outil vient dessus : 4 vis M3, 2 aimants d6x3 pour le centrage, 8 pogo pins."""
    b = cy(62, 8)
    trous = [cy(3.4, 10, x, y, -1) for x, y in CERCLE_J6] + [cy(6.2, 3.4, x, y, 4.8) for x, y in CERCLE_J6]
    trous += [cy(4.1, 6, x, y, 2.5) for x, y in CERCLE_OUTIL]                 # inserts M3 des outils
    trous += [cy(6.2, 3.2, s * 24 * .707, s * 24 * .707, 5) for s in (-1, 1)]  # aimants
    trous += [cy(POGO_D, 10, -10.5 + 3 * k, -22, -1) for k in range(8)] + [bo(26, 6, 3, 0, -22, -0.01)]
    trous += [bo(26, 6, 4, 0, -22, 0)]                                         # sortie des fils
    # place du GY-521 (21 x 16) cote fixe
    trous += [bo(21.6, 16.6, 3, 0, 15, -0.01)]
    return b - somme(trous)


def platine_outil(ep=5.0):
    """Face commune de tous les outils : contacts, aimants et vis imperdables."""
    b = cy(62, ep)
    trous = [cy(3.4, ep + 2, x, y, -1) for x, y in CERCLE_OUTIL]
    trous += [cy(6.2, 3.2, s * 24 * .707, s * 24 * .707, -0.01) for s in (-1, 1)]
    trous += [cy(POGO_D, ep + 2, -10.5 + 3 * k, -22, -1) for k in range(8)]
    trous += [bo(14, 8, 2.2, 0, 16, ep - 2.2)]                                 # EEPROM 24C02
    return b - somme(trous)


def support_laser():
    """Module VL53L0X V2 : 25 x 11 mm, 2 vis M2 a 20 mm. Rien devant la lentille."""
    b = bo(31, 17, 4) + bo(31, 3, 12, 0, -7, 0)
    trous = [bo(26, 11.8, 3, 0, 0, 2), bo(11, 8, 6, 0, 0, -1)]                 # logement + fenetre de lentille
    trous += [cy(2.2, 7, s * 10, 0, -1) for s in (-1, 1)]
    return b - somme(trous)


def bracelet(d_int=70.0, ep=8.0, h=20.0):
    """Collier en 2 moities serrees par 2 vis M3 : 3 paires laser + ultrason a 120 deg. Poser au poignet, avant J6."""
    r = d_int / 2
    bague = cy(d_int + 2 * ep, h, n=128) - cy(d_int, h + 2, z0=-1, n=128)
    ajout, trous = [bague], []
    for k in range(3):
        a = 120 * k + 90
        def place(m):
            return m.rotate((0, 0, a)).translate((0, 0, 0))
        R = r + ep + 8
        # plaque tangentielle : ultrason (53 x 28) dessus, laser en dessous
        plaque = bo(16, 60, h, R - 3, 0, 0)
        ajout.append(place(plaque))
        for s in (-1, 1):
            trous.append(place(cy(3.4, 18, 0, 0, 0).rotate((0, 90, 0)).translate((R - 12, s * 22, 5))))     # vis du support
            trous.append(place(cy(3.4, 18, 0, 0, 0).rotate((0, 90, 0)).translate((R - 12, s * 22, 15))))
    # 2 oreilles de serrage + coupe en 2
    for s in (-1, 1):
        ajout.append(bo(12, 14, h, s * (r + ep + 3), 0, 0).rotate((0, 0, 30)))
        trous.append(cy(3.4, 16, 0, 0, 0).rotate((90, 0, 0)).translate((s * (r + ep + 3), 8, h / 2)).rotate((0, 0, 30)))
    m = somme(ajout) - somme(trous)
    coupe = bo(300, 1.0, h + 4, 0, 0, -2).rotate((0, 0, 30))
    return m - coupe


def platine_xy(lame=0.8, L=45.0):
    """Table XY monobloc a lames flexibles, sans jeu ni frottement : ~ +/-4 mm par axe (lames de 45 mm x 0,8 mm en PETG).
    Imprimer a plat, 2 lignes de buse 0,4 par lame, 100 % de remplissage."""
    H = 10.0
    ext, ix, cx = 110.0, 74.0, 40.0
    cadre = bo(ext, ext, H) - bo(ext - 12, ext - 12, H + 2, z0=-1)
    inter = bo(ix, ix, H) - bo(ix - 10, ix - 10, H + 2, z0=-1)
    cent = bo(cx, cx, H)
    Ri, Re = (ext - 12) / 2, ix / 2
    mi = (Ri + Re) / 2
    P = []
    for sx in (-1, 1):                    # etage 1 : lames le long de Y, le cadre tient un bout, l'intermediaire l'autre -> mouvement X
        for sy in (-1, 1):
            P.append(bo(lame, L + 1, H, sx * mi, sy * (Ri - L / 2)))
            P.append(bo(mi - Re + 1, 4, H, sx * (Re + mi) / 2, sy * (Ri - L)))
    ri, rc = (ix - 10) / 2, cx / 2
    mc = (ri + rc) / 2
    for sy in (-1, 1):                    # etage 2 : lames le long de X, l'intermediaire tient un bout, le centre l'autre -> mouvement Y
        for sx in (-1, 1):
            P.append(bo(L + 1, lame, H, sx * (ri - L / 2), sy * mc))
    for sy in (-1, 1):
        for sx in (-1, 1):
            P.append(bo(4, mc - rc + 1, H, sx * (ri - L), sy * (rc + mc) / 2))
    m = somme([cadre, inter, cent] + P)
    trous = [cy(3.4, H + 2, x, y, -1) for x, y in ((6, 6), (-6, 6), (6, -6), (-6, -6))]
    trous += [cy(3.4, H + 2, sx * (ext / 2 - 3), sy * (ext / 2 - 3), -1) for sx in (-1, 1) for sy in (-1, 1)]
    return m - somme(trous)


def support_servo_xy():
    """2 SG90 ou servos numeriques : chacun pousse la table par une biellette. Se fixe sur le cadre XY."""
    b = bo(40, 30, 3) + bo(40, 3, 26, 0, -13.5, 0)
    trous = [bo(23.2, 12.6, 5, 0, 0, -1)] + [cy(2.2, 5, s * 14, 0, -1) for s in (-1, 1)] + [cy(3.4, 5, s * 16, -13.5, 10).rotate((0, 0, 0)) for s in ()]
    trous += [cy(3.4, 6, 0, 0, 0).rotate((90, 0, 0)).translate((s * 14, -11, 18)) for s in (-1, 1)]
    return b - somme(trous)


def biellette(L=30.0):
    b = bo(L, 6, 3) + cy(6, 3, -L / 2) + cy(6, 3, L / 2)
    return b - somme([cy(2.2, 5, -L / 2, 0, -1), cy(2.2, 5, L / 2, 0, -1)])


def porte_capteur_force():
    """Capteur alu 38 x 38 : le cadre repose, le carre central recoit l'effort du pinceau."""
    b = bo(50, 50, 10)
    trous = [bo(38.5, 38.5, 5, 0, 0, 6), bo(30, 30, 8, 0, 0, 3.5), bo(8, 60, 3, 0, 0, 7.5)]
    trous += [cy(3.4, 12, x, y, -1) for x, y in ((6, 6), (-6, 6), (6, -6), (-6, -6))]
    return b - somme(trous)


def mandrin_pinceau(d_max=12.0):
    """Coulisseau Z a ressort leger ; le manche est serre par 2 vis M3 contre un V. Pousse sur le capteur de force."""
    corps = cy(24, 46)
    v = cy(d_max + 0.5, 48, 0, 0, -1)
    fente = bo(14, 2, 48, 7, 0, -1)
    pousse = cy(16, 9, 0, 0, 45) - cy(4.1, 6, 0, 0, 48.5)
    vis = [cy(2.8, 26, 0, 0, 0).rotate((90, 0, 0)).translate((9.2, 13, z)) for z in (12, 34)]   # serrent la fente
    return (corps - somme([v, fente] + vis)) + pousse


def guide_z():
    """Guide du coulisseau : 2 bagues, ressort de rappel autour du mandrin. Le jeu de 0,3 mm evite le blocage."""
    b = cy(36, 40) + bo(50, 50, 4, z0=36)
    trous = [cy(24.3, 42, z0=-1)] + [cy(3.4, 6, x, y, 35) for x, y in ((18, 18), (-18, 18), (18, -18), (-18, -18))]
    return b - somme(trous)


def colonne(L=30.0):
    return cy(10, L) - cy(3.4, L + 2, z0=-1)


def support_as5600():
    """Carte AS5600 (23 x 23, 2 trous a 14 mm) a 1,5 mm de l'aimant."""
    b = bo(30, 30, 3) + bo(30, 3, 16, 0, -13.5, 0)
    trous = [cy(2.2, 5, s * 7, 0, -1) for s in (-1, 1)]
    return b - somme(trous)


def collier_endoscopes():
    """Se serre sur le guide Z (d36) : 2 rails a 90 deg descendent vers la pointe du pinceau. Fente de 60 mm pour regler la hauteur."""
    b = cy(46, 14) - cy(36.3, 16, z0=-1)
    aj = [b, bo(14, 12, 14, 26, 0, 0)]                              # oreille de serrage
    tr = [bo(16, 1.5, 16, 26, 0, -1), cy(3.4, 16).rotate((90, 0, 0)).translate((28, 8, 7))]
    for a_ in (180, 270):
        rail = bo(14, 5, 80, 0, 0, -66).translate((0, 23.5, 0))
        fente = bo(3.6, 7, 60, 0, 0, -58).translate((0, 23.5, 0))
        aj.append(rail.rotate((0, 0, a_)))
        tr.append(fente.rotate((0, 0, a_)))
    return somme(aj) - somme(tr)


def pince_endoscope(d=8.0):
    """Vise la pointe : inclinable sur sa vis M3, l'endoscope est serre par une 2e vis M3. Bague a imprimer si son diametre est plus petit."""
    b = bo(14, 8, 10) + cy(d + 7, 22, 0, 10.0, 0).rotate((0, 0, 0))
    tr = [cy(3.4, 12, 0, 0, 0).rotate((90, 0, 0)).translate((0, 5, 5)), cy(d + 0.3, 24, 0, 10.0, -1), bo(1.6, d + 9, 24, 0, 14.0, -1)]
    tr.append(cy(3.4, d + 12, 0, 0, 0).rotate((0, 90, 0)).translate((-(d + 12) / 2, 10.0 + d / 2 + 2.2, 11)))
    return b - somme(tr)


def bague_endoscope(d=5.5, ext=8.0):
    return cy(ext - 0.1, 20) - somme([cy(d + 0.3, 22, z0=-1), bo(1.2, ext, 22, 0, ext / 2, -1)])


PIECES = {
    "endoscope_collier": (collier_endoscopes, 1), "endoscope_pince": (pince_endoscope, 2), "endoscope_bague_5_5": (bague_endoscope, 2),
    "bride_pogo": (bride_pogo, 1), "platine_outil": (platine_outil, 3), "support_laser": (support_laser, 5),
    "bracelet": (bracelet, 1), "peinture_table_xy": (platine_xy, 1), "peinture_support_servo": (support_servo_xy, 2),
    "peinture_biellette": (biellette, 2), "peinture_porte_capteur": (porte_capteur_force, 1),
    "peinture_mandrin": (mandrin_pinceau, 2), "peinture_guide_z": (guide_z, 1), "peinture_colonne": (colonne, 4),
    "support_as5600": (support_as5600, 5),
}


def vers_mesh(m):
    q = m.to_mesh()
    return trimesh.Trimesh(np.asarray(q.vert_properties)[:, :3], np.asarray(q.tri_verts), process=True)


def exporter(dossier):
    d = Path(dossier); d.mkdir(parents=True, exist_ok=True)
    bilan = {}
    for nom, (f, n) in PIECES.items():
        m = f()
        t = vers_mesh(m)
        t.export(d / f"{nom}_x{n}.stl")
        bilan[nom] = {"qte": n, "g": round(t.volume * 1.27e-3, 1), "dim": t.extents.round(1).tolist(), "etanche": bool(t.is_watertight), "corps": len(t.split(only_watertight=False))}
    return bilan


if __name__ == "__main__":
    b = exporter(sys.argv[1] if len(sys.argv) > 1 else "sortie/davinbot_tubes/outils")
    for k, v in b.items():
        print(k, v)
    print("total g", round(sum(v["g"] * v["qte"] for v in b.values())))
