"""SPEC-A : multiplicateur de vitesse, 100 % imprime, sans roulement (axes = vis acier M4).
Gros pignon sur le moteur -> petit pignon en sortie : la sortie tourne ~11x plus vite.
    python -m atelier.projets.spec_a sortie/spec_a
"""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import trimesh
from shapely.geometry import Polygon
from atelier.projets.davinbot.gears.involute import external_gear

M, PA, FW = 1.0, 20.0, 6.0
ZB, ZP = 40, 12                      # grand / petit -> survitesse 3,33 par etage ; 2 etages ~11:1
RATIO = (ZB / ZP) ** 2


def roue(z, z0, h=FW):
    return trimesh.creation.extrude_polygon(Polygon(external_gear(z, M, 0.25, PA)), h).apply_translation((0, 0, z0))


def perce(mesh, d, x=0, y=0):
    t = trimesh.creation.cylinder(radius=d / 2, height=60, sections=48).apply_translation((x, y, 0))
    return mesh.difference(t)


def cyl(d, h, z0, x=0, y=0):
    return trimesh.creation.cylinder(radius=d / 2, height=h, sections=48).apply_translation((x, y, z0 + h / 2))


def plaque(mount_moteur):
    b = trimesh.creation.box((108, 54, 4)).apply_translation((26, 0, 2))
    b = perce(b, 9, 0, 0)                           # passage arbre moteur / vis
    b = perce(b, 3.3, 26, 0); b = perce(b, 3.3, 52, 0)    # axes M4 intermediaire + sortie
    for sx in (-1, 1):
        for sy in (-1, 1):
            b = perce(b, 3.3, -18 + sx * 0, 0)      # (placeholder)
    for cx, cy in ((-20, -22), (-20, 22), (72, -22), (72, 22)):
        b = perce(b, 3.3, cx, cy)                   # entretoises M3
    if mount_moteur:
        b = perce(b, 22, 0, 0)                      # collerette NEMA
        for sx in (-1, 1):
            for sy in (-1, 1):
                b = perce(b, 3.3, sx * 15.5, sy * 15.5)
    return b


def exporter(dossier):
    d = Path(dossier); d.mkdir(parents=True, exist_ok=True)
    out = {}
    # grand pignon moteur (alesage 5 mm, meplat D)
    g = perce(roue(ZB, 0), 5.0)
    g = g.difference(trimesh.creation.box((6, 1.5, FW + 2)).apply_translation((2.6, 0, FW / 2)))
    out["moteur_grand_pignon"] = g
    # intermediaire compose : petit pignon (bas) + grand (haut) + moyeu, alesage M4
    inter = trimesh.boolean.union([roue(ZP, 0), roue(ZB, 8), cyl(10, 14, 0)])
    inter = perce(inter, 3.3)
    out["intermediaire_compose"] = inter
    # sortie : petit pignon + disque marque (leger, equilibre), alesage M4
    disque = cyl(44, 3, 14).difference(cyl(5, 5, 13))
    for a in range(0, 360, 45):
        disque = disque.difference(cyl(5, 5, 13, 16 * math.cos(math.radians(a)), 16 * math.sin(math.radians(a))))
    sortie = trimesh.boolean.union([roue(ZP, 8), cyl(10, 6, 14), disque])
    out["sortie_disque"] = perce(sortie, 3.3)
    # bati
    out["plaque_bas"] = plaque(True)
    out["plaque_haut"] = plaque(False).apply_translation((0, 0, 20))
    out["entretoise_x4"] = cyl(9, 24, 0).difference(cyl(3.4, 30, -3))
    bilan = {}
    for nom, m in out.items():
        m.export(d / f"{nom}.stl")
        bilan[nom] = (round(m.volume * 1.27e-3, 1), bool(m.is_watertight))
    return bilan


if __name__ == "__main__":
    b = exporter(sys.argv[1] if len(sys.argv) > 1 else "sortie/spec_a")
    for k, v in b.items():
        print(k, v[0], "g", "etanche" if v[1] else "NON ETANCHE")
    print(f"Survitesse {RATIO:.1f}:1  (grand Z{ZB} -> petit Z{ZP}, 2 etages)")
