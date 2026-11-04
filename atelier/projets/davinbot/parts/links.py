"""Segments (corps structurels) : coque en U ouverte cote +X + capot visse.

Chaque segment est une boite alignee sur les axes monde (pose zero, bras vertical).
Les actionneurs se fixent :
  * par leur face arriere (flasque) sur une paroi du segment PARENT : le moteur
    traverse la paroi et loge dans la cavite, le MKS sort par une fenetre en face ;
  * par leur bride de sortie sur une paroi du segment ENFANT.
Toutes les decoupes sont definies dans le repere local de l'actionneur puis
transformees -> coherence garantie entre carter, moteur et segment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..cad.util import (SCREW, box, cyl, apply_T, union_all, cut_all, fuse_all, bbox)
from .model import Part

LIP_W = 9.0       # debord des brides d'eclissage
LIP_T = 6.0       # epaisseur de chaque demi-bride


@dataclass
class Mount:
    T: np.ndarray            # repere actionneur -> monde
    act: object              # ActuatorBuild
    kind: str                # "rear" | "flange"


@dataclass
class LinkSpec:
    key: str
    label: str
    body: int
    x0: float
    x1: float
    y0: float
    y1: float
    z0: float
    z1: float
    wall: float
    mounts: list = field(default_factory=list)
    extra_cut: list = field(default_factory=list)      # solides monde a soustraire
    extra_add: list = field(default_factory=list)      # solides monde a ajouter
    avoid: list = field(default_factory=list)          # bbox (x0,y0,z0,x1,y1,z1) interdites aux bossages
    split_zs: list = field(default_factory=list)
    notes: str = ""
    locked: set = field(default_factory=set)


def rear_cutters(act, wall: float, cfg: dict) -> list:
    """Decoupes (repere actionneur) dans la paroi qui recoit la face arriere."""
    mb = cfg["motor_body"] + 1.0
    zz = -(wall + 1.0)
    out = [cyl(cfg["cable_bore"] + 4, wall + 2, zz)]
    for mt in (act.motors or [{"x": act.a}]):
        out.append(box(mt["x"] - mb / 2, mt["x"] + mb / 2, -mb / 2, mb / 2, zz, 0.5))
    out += [cyl(SCREW["M4"]["clear"], wall + 2, zz, x, y) for x, y in act.mount_pts]
    return out


def mks_window(act, wall_z: float, wall: float, cfg: dict) -> list:
    """Fenetre d'acces MKS dans la paroi opposee (repere actionneur, paroi en z=wall_z)."""
    return [cyl(cfg["mks_d"] + 1.0, wall + 2, wall_z - wall - 1, act.a, 0)]


def flange_cutters(act, wall: float, cfg: dict) -> list:
    L = act.L
    out = [cyl(cfg["cable_bore"] + 4, wall + 2, L - 1)]
    out += [cyl(SCREW["M4"]["clear"], wall + 2, L - 1, x, y) for x, y in act.out_pts]
    r = math.hypot(*act.out_pts[0])
    for ang in (30, 190):
        out.append(cyl(3.0 + cfg["tol"], 4.0, L - 0.01, r * math.cos(math.radians(ang)),
                       r * math.sin(math.radians(ang))))
    return out


def _bbox_hit(b1, b2, pad=0.0) -> bool:
    return not (b1[3] + pad < b2[0] or b2[3] + pad < b1[0] or b1[4] + pad < b2[1] or
                b2[4] + pad < b1[1] or b1[5] + pad < b2[2] or b2[5] + pad < b1[2])


def build_link(s: LinkSpec, cfg: dict) -> list[Part]:
    w = s.wall
    outer = box(s.x0, s.x1, s.y0, s.y1, s.z0, s.z1)
    inner = box(s.x0 + w, s.x1 + 1, s.y0 + w, s.y1 - w, s.z0 + w, s.z1 - w)
    shell = outer.cut(inner)

    # bossages du capot (cote +X), inserts M3
    boss_d, boss_l = 8.0, 12.0
    ys = (s.y0 + w + 2.6, s.y1 - w - 2.6)
    length = s.z1 - s.z0 - 2 * w - 8
    n_z = max(2, int(length // 70) + 2)
    zs = [s.z0 + w + 4 + length * i / (n_z - 1) for i in range(n_z)]
    zs_split = [z for z in s.split_zs]
    boss_pts = []
    for y in ys:
        for z in zs:
            if any(abs(z - zc) < 12 for zc in zs_split):
                continue
            bb = (s.x1 - boss_l, y - boss_d / 2, z - boss_d / 2, s.x1, y + boss_d / 2, z + boss_d / 2)
            if any(_bbox_hit(bb, a, 1.0) for a in s.avoid):
                continue
            boss_pts.append((y, z))
    add = []
    for y, z in boss_pts:
        b = cyl(boss_d, boss_l, 0, 0, 0).rotate((0, 0, 0), (0, 1, 0), 90)
        b = b.translate((s.x1 - boss_l, y, z))
        # nervure de liaison boss -> paroi Y la plus proche
        yw = s.y0 + w if y < (s.y0 + s.y1) / 2 else s.y1 - w
        rib = box(s.x1 - boss_l, s.x1, min(y, yw) - 0.01, max(y, yw) + 0.01, z - 2, z + 2)
        add += [b, rib]
    body = fuse_all([shell] + add + s.extra_add)

    cut = []
    for m in s.mounts:
        if m.kind == "rear":
            cs = rear_cutters(m.act, w, cfg)
        else:
            cs = flange_cutters(m.act, w, cfg)
        cut += [apply_T(c, m.T) for c in cs]
    cut += s.extra_cut
    ins = SCREW["M3"]["insert"]
    for y, z in boss_pts:
        h = cyl(ins, 7, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((s.x1 - 6.5, y, z))
        cut.append(h)
    body = cut_all(body, cut)

    # capot
    cover = box(s.x1, s.x1 + w, s.y0, s.y1, s.z0, s.z1)
    ccut = []
    for y, z in boss_pts:
        ccut.append(cyl(SCREW["M3"]["clear"], w + 2, 0).rotate((0, 0, 0), (0, 1, 0), 90)
                    .translate((s.x1 - 1, y, z)))
        ccut.append(cyl(SCREW["M3"]["head"] + 0.4, 2.0, 0).rotate((0, 0, 0), (0, 1, 0), 90)
                    .translate((s.x1 + w - 1.99, y, z)))
    # le capot recoit les memes decoupes s'il croise une interface (rare)
    cover = cut_all(cover, ccut + [c for c in cut if _bbox_hit(bbox(c), bbox(cover))])

    parts = []
    shells = _split(body, s, cfg) if s.split_zs else [(body, "")]
    covers = _split_plain(cover, s) if s.split_zs else [(cover, "")]
    for shp, suf in shells:
        parts.append(Part(id=f"{s.key}_coque{suf}", name=f"{s.label} - coque{suf.replace('_', ' ')}",
                          group=s.key, body=s.body, shape=shp, category="structure",
                          print_up=(1, 0, 0), notes=s.notes or "Imprimer ouverture vers le haut."))
    for shp, suf in covers:
        parts.append(Part(id=f"{s.key}_capot{suf}", name=f"{s.label} - capot{suf.replace('_', ' ')}",
                          group=s.key, body=s.body, shape=shp, category="cap",
                          print_up=(-1, 0, 0), notes=f"{len(boss_pts)} vis M3x10 + inserts."))
    return parts


def _lip_frame(s: LinkSpec, z0: float, z1: float):
    ring = box(s.x0 - LIP_W, s.x1, s.y0 - LIP_W, s.y1 + LIP_W, z0, z1)
    return ring.cut(box(s.x0 + 0.01, s.x1 + 1, s.y0 + 0.01, s.y1 - 0.01, z0 - 1, z1 + 1))


def _lip_bolts(s: LinkSpec):
    pts = []
    c = LIP_W / 2
    ny = max(2, int((s.y1 - s.y0) // 45) + 1)
    for i in range(ny):
        y = s.y0 + 8 + (s.y1 - s.y0 - 16) * i / (ny - 1)
        pts.append((s.x0 - c, y))
    nx = max(2, int((s.x1 - s.x0) // 45) + 1)
    for i in range(nx):
        x = s.x0 + 8 + (s.x1 - s.x0 - 16) * i / (nx - 1)
        pts += [(x, s.y0 - c), (x, s.y1 + c)]
    return pts


def _split(body, s: LinkSpec, cfg: dict):
    """Decoupe en modules assembles par brides boulonnees M4 (volume d'impression)."""
    planes = [s.z0 - 1] + sorted(s.split_zs) + [s.z1 + 1]
    bolts = _lip_bolts(s)
    out = []
    for i in range(len(planes) - 1):
        za, zb = planes[i], planes[i + 1]
        seg = body.intersect(box(s.x0 - 50, s.x1 + 50, s.y0 - 50, s.y1 + 50, za, zb))
        adds, cuts = [], []
        if i > 0:
            adds.append(_lip_frame(s, za, za + LIP_T))
            cuts += [cyl(SCREW["M4"]["clear"], LIP_T + 2, za - 1, x, y) for x, y in bolts]
        if i < len(planes) - 2:
            adds.append(_lip_frame(s, zb - LIP_T, zb))
            cuts += [cyl(SCREW["M4"]["clear"], LIP_T + 2, zb - LIP_T - 1, x, y) for x, y in bolts]
        seg = cut_all(fuse_all([seg] + adds), cuts)
        out.append((seg, f"_{i + 1}"))
    return out


def _split_plain(shape, s: LinkSpec):
    planes = [s.z0 - 1] + sorted(s.split_zs) + [s.z1 + 1]
    return [(shape.intersect(box(s.x0 - 50, s.x1 + 50, s.y0 - 50, s.y1 + 50, planes[i],
                                 planes[i + 1])), f"_{i + 1}") for i in range(len(planes) - 1)]


def auto_split(z0: float, z1: float, free: tuple, max_len: float) -> list:
    """Plans de coupe regulierement repartis dans la zone libre (sans interface)."""
    L = z1 - z0
    n = math.ceil(L / max_len)
    if n <= 1:
        return []
    fa, fb = free
    zs = []
    for k in range(1, n):
        target = z0 + L * k / n
        zs.append(min(max(target, fa + LIP_T + 2), fb - LIP_T - 2))
    return zs
