"""Actionneurs complets (moteur deporte + etage d'entree + reducteur principal creux).

Repere local de l'actionneur :
  * z = axe de l'articulation, sortie vers +z. Face arriere du carter en z = 0.
  * le NEMA 17 est deporte en (+a, 0), corps en z < 0 (dans le segment parent),
    module MKS SERVO42C et sa zone reservee derriere lui.

Empilement axial (commun) :
  [0, t_r]      flasque arriere : roulement A, platine moteur
  [t_r, z1]     chambre de l'etage d'entree (pignon moteur -> roue d'entree)
  [z1, z2]      cloison du carter principal
  [z2, z4]      reducteur principal (disques cycloidaux ou train planetaire)
  [z4, z5]      couvercle avant : roulement de sortie O
  [z5, L]       bride de sortie (face de montage du segment enfant)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq
from shapely import affinity
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

from ..cad.util import (SCREW, extrude_poly, extrude_shapely, cyl, tube, box, hex_prism,
                        union_all, cut_all, fuse_all, bolt_circle, holes, circle2d, rect2d,
                        outline_hull)
from ..config import BEARINGS
from ..gears.cycloid import disc_polygon
from ..gears.involute import external_gear, internal_gear_cutter
from .model import Part

LIP = 2.0          # epaisseur des levres de retenue des roulements
T_DIAPH = 4.0      # cloison
T_SHOULDER = 8.0   # epaulement de sortie
T_BRIDE = 10.0     # bride de sortie (inserts M4)
T_CARRIER = 4.0    # flasque arriere du porte-satellites


def best_phase(fixed: Polygon, make_moving, pitch_rad: float, steps: int = 48) -> float:
    """Phase (rad) de la piece mobile minimisant l'interference avec la piece fixe."""
    best = (1e9, 0.0)
    for i in range(steps):
        ph = pitch_rad * i / steps
        a = make_moving(ph).intersection(fixed).area
        if a < best[0]:
            best = (a, ph)
    lo, hi = best[1] - pitch_rad / steps, best[1] + pitch_rad / steps
    for _ in range(12):   # affinage
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if make_moving(m1).intersection(fixed).area < make_moving(m2).intersection(fixed).area:
            hi = m2
        else:
            lo = m1
    return (lo + hi) / 2


@dataclass
class ActuatorBuild:
    jid: str
    kind: str
    design: object
    parts: list = field(default_factory=list)
    L: float = 0.0                  # face arriere -> face de sortie
    OD: float = 0.0                 # diametre du carter
    a: float = 0.0                  # entraxe moteur
    rear_outline: Polygon | None = None     # contour de la face arriere (plan XY local)
    mount_pts: list = field(default_factory=list)     # boulons traversants M4 (face arriere)
    out_pts: list = field(default_factory=list)       # inserts M4 de la bride de sortie
    out_d: float = 0.0              # diametre de la bride de sortie
    motor_square: Polygon | None = None
    keepout: dict = field(default_factory=dict)       # cylindre reserve MKS (local)
    motors: list = field(default_factory=list)        # [{"x": a, "tag": "M1"}] moteurs (local)
    lock_servo: dict | None = None                    # servo de verrouillage (DSDM)
    vitamins: list = field(default_factory=list)
    info: dict = field(default_factory=dict)
    stack: dict = field(default_factory=dict)


class _Common:
    """Pieces partagees par les deux familles de reducteurs."""

    def __init__(self, jid: str, d, cfg: dict):
        self.jid, self.d, self.cfg = jid, d, cfg
        self.tol, self.press, self.wall = cfg["tol"], cfg["press_tol"], cfg["wall"]
        self.bore = cfg["cable_bore"]
        self.fw = cfg["face_width"]
        self.pa = cfg["pressure_angle"]
        self.A = BEARINGS[d.brg_in]          # roulements d'arbre A et B
        self.O = BEARINGS[d.brg_out]         # roulement de sortie
        self.pre = d.pre
        self.a = d.pre.a
        self.t_r = self.A[2] + LIP
        self.z1 = self.t_r + self.fw + 2.0
        self.z2 = self.z1 + T_DIAPH
        self.m_body = cfg["motor_body"]
        self.double = bool(cfg.get("j2_double")) and jid == "J2"
        if self.double:
            self.motor_xs = [self.a, -self.a]
            self.motors = [{"x": self.a, "tag": ""}, {"x": -self.a, "tag": "M2"}]
        self.parts: list[Part] = []
        self.vit: list = []

    # ------------------------------------------------------------ helpers
    def P(self, name, label, body, shape, **kw) -> Part:
        p = Part(id=f"{self.jid}_{name}", name=f"{self.jid} - {label}", group=self.jid,
                 body=body, shape=shape, **kw)
        self.parts.append(p)
        return p

    def bearing_vit(self, key, label, z0, x=0.0, y=0.0, body=0, qty_name=None):
        d, D, B = BEARINGS[key]
        shp = tube(D, d, B, z0, x, y)
        self.P(f"brg_{label}_{round(z0)}_{round(x)}_{round(y)}", f"roulement {key} ({label})",
               body, shp, kind="vitamin", category="bearing")

    # ------------------------------------------------------------ etage d'entree
    def gear_polys(self):
        pre, tol = self.pre, self.tol
        g_in = Polygon(external_gear(pre.zi, pre.m, tol, self.pa, flank_pts=12, arc_pts=5))
        g_m0 = Polygon(external_gear(pre.zm, pre.m, tol, self.pa, flank_pts=12, arc_pts=5))

        def moving(ph):
            return affinity.translate(affinity.rotate(g_m0, ph, origin=(0, 0), use_radians=True),
                                      self.a, 0)
        ph = best_phase(g_in, moving, 2 * math.pi / pre.zm)
        return g_in, moving(ph), ph

    def chamber_outline(self):
        pre = self.pre
        r_in = pre.m * pre.zi / 2 + pre.m + 1.5
        r_pin = pre.m * pre.zm / 2 + pre.m + 1.5
        heads = [circle2d(SCREW["M3"]["head"] + 1.2, self.a + sx * 15.5, sy * 15.5)
                 for sx in (-1, 1) for sy in (-1, 1)]
        out = outline_hull(circle2d(2 * r_in), circle2d(2 * r_pin, self.a, 0), *heads)
        if self.double:                                 # second pignon, en miroir de l'autre cote de la roue
            out = unary_union([out, affinity.scale(out, -1, 1, origin=(0, 0))]).simplify(0.05)
        return out

    def motor_pts(self, ax=None):
        ax = self.a if ax is None else ax
        return [(ax + sx * 15.5, sy * 15.5) for sx in (-1, 1) for sy in (-1, 1)]

    def choose_mount_pts(self, Rb: float, chamber: Polygon, extra=None) -> list:
        sq = unary_union([rect2d(ax, 0, self.m_body + 6, self.m_body + 6)
                          for ax in getattr(self, "motor_xs", [self.a])] + (extra or []))
        keep = []
        for n in (8, 10, 12):
            keep = []
            for k in range(n):
                ang = 2 * math.pi * k / n + math.pi / n
                p = (Rb * math.cos(ang), Rb * math.sin(ang))
                c = circle2d(SCREW["M4"]["clear"] + 3.0, *p)
                if c.intersects(sq) or c.intersects(chamber.buffer(1.0)):
                    continue
                keep.append(p)
            if len(keep) >= 5:
                break
        return keep

    def chamber_clear_radius(self) -> float:
        """Rayon mini du cercle de boulons pour ne pas percer la chambre d'entree."""
        pre = self.pre
        r_in = pre.m * pre.zi / 2 + pre.m + 1.5
        return r_in + self.wall + SCREW["M4"]["clear"] / 2 + 0.8

    def rear_cap(self, Rb: float, OD: float) -> tuple:
        """Flasque arriere + chambre de l'etage d'entree (piece fixe, corps parent)."""
        A, t_r, z1 = self.A, self.t_r, self.z1
        chamber = self.chamber_outline()
        sq = rect2d(self.a, 0, self.m_body, self.m_body)
        sqs = [rect2d(x, 0, self.m_body, self.m_body) for x in getattr(self, "motor_xs", [self.a])]
        outline = outline_hull(circle2d(OD), sq, *sqs, chamber.buffer(self.wall + 0.8))
        body = extrude_shapely(outline, z1)
        mount = self.choose_mount_pts(Rb, chamber)
        cut = [
            extrude_shapely(chamber, z1 - t_r + 1, t_r),                        # chambre
            cyl(A[1] + self.press, A[2] + 0.01, t_r - A[2]),                    # roulement A
            cyl((A[0] + A[1]) / 2 + 1.0, t_r, -1),                              # levre A
        ]
        for ax in getattr(self, "motor_xs", [self.a]):
            cut += [cyl(22.0 + 2 * self.tol, 2.2 + 1, -1, ax, 0),               # centrage NEMA
                    cyl(9.0, t_r + 2, -1, ax, 0)]                               # passage arbre
            for x, y in self.motor_pts(ax):
                cut.append(cyl(SCREW["M3"]["clear"], t_r + 2, -1, x, y))
                cut.append(cyl(SCREW["M3"]["head"] + 0.4, 3.6, t_r - 3.5, x, y))
        cut += holes(mount, SCREW["M4"]["clear"], -1, z1 + 2)
        shape = cut_all(body, cut)
        self.P("flasque_arriere", "flasque arriere + chambre d'entree", -1, shape,
               category="housing", print_up=(0, 0, -1),
               notes="Imprimer face arriere sur le plateau. Vis M3x8 tete cylindrique "
                     "(fixation NEMA 17) posees depuis la chambre.")
        return outline, mount, chamber

    def second_pinion(self, g_in: Polygon):
        """Pignon du 2e moteur (J2) : meme roue d'entree, en face du premier, phase calculee pour engrener."""
        pre, t_r = self.pre, self.t_r
        g0 = Polygon(external_gear(pre.zm, pre.m, self.tol, self.pa, flank_pts=12, arc_pts=5))
        def moving(ph):
            return affinity.translate(affinity.rotate(g0, ph, origin=(0, 0), use_radians=True), -self.a, 0)
        g = moving(best_phase(g_in, moving, 2 * math.pi / pre.zm))
        dbore = circle2d(5.0 + self.tol, -self.a, 0).difference(rect2d(-self.a + 2.25 + self.tol / 2 + 5, 0, 10, 10))
        shape = extrude_shapely(g.difference(dbore), self.fw, t_r + 0.2)
        grub = cq.Workplane("YZ", origin=(-self.a, 0, t_r + 0.2 + self.fw / 2)).circle(1.25).extrude(20)
        self.P("pignon_moteur_2", f"pignon moteur 2 Z{pre.zm} m{pre.m}", -1, shape.cut(grub), category="gear",
               anim={"type": "spin", "center": [-self.a, 0], "k": [1.0, 0.0]},
               notes="Meme pignon que le moteur 1. Les 2 moteurs recoivent les memes ordres de pas : verifier leur sens.")

    def motor_pinion(self, g_m: Polygon):
        pre, t_r = self.pre, self.t_r
        # alesage en D (arbre 5 mm, meplat 4.5 mm)
        dbore = circle2d(5.0 + self.tol, self.a, 0).difference(
            rect2d(self.a + 2.25 + self.tol / 2 + 5, 0, 10, 10))
        prof = g_m.difference(dbore)
        shape = extrude_shapely(prof, self.fw, t_r + 0.2)
        # vis de pression M3 (percage 2.5 a tarauder) radiale cote meplat
        grub = (cq.Workplane("YZ", origin=(self.a, 0, t_r + 0.2 + self.fw / 2))
                .circle(1.25).extrude(20))
        shape = shape.cut(grub)
        self.P("pignon_moteur", f"pignon moteur Z{pre.zm} m{pre.m}", -1, shape, category="gear",
               anim={"type": "spin", "center": [self.a, 0], "k": [1.0, 0.0]},
               notes="Alesage en D 5 mm, vis sans tete M3 (tarauder 2.5 mm).")

    def input_gear(self, g_in: Polygon):
        A, t_r = self.A, self.t_r
        af = A[0] + self.tol
        hexp = Polygon([(af / math.sqrt(3) * math.cos(k * math.pi / 3),
                         af / math.sqrt(3) * math.sin(k * math.pi / 3))
                        for k in range(6)])
        prof = g_in.difference(hexp)
        self.P("roue_entree", f"roue d'entree Z{self.pre.zi} m{self.pre.m}", -1,
               extrude_shapely(prof, self.fw, t_r + 0.2), category="gear",
               anim={"type": "spin", "center": [0, 0], "k": [-1.0 / self.pre.ratio, 0.0]},
               notes="Montee sur l'hexagone de l'arbre d'entree creux.")

    def motor_and_keepout(self, ax=None, tag=""):
        ax = self.a if ax is None else ax
        mb, ml, cfg = self.m_body, self.cfg["motor_len"], self.cfg
        sfx = f"_{tag}" if tag else ""
        lab = f" {tag}" if tag else ""
        shaft = cyl(5.0, 22.0, 2.0, ax, 0).cut(box(ax + 2.0, ax + 3, -3, 3, 1, 25))
        motor = fuse_all([box(ax - mb / 2, ax + mb / 2, -mb / 2, mb / 2, -ml, 0),
                          cyl(22.0, 2.0, 0, ax, 0), shaft])
        self.P(f"nema17{sfx}", f"NEMA 17{lab}", -1, motor, kind="vitamin",
               category="motor")
        if not cfg.get("pilote_deporte"):
            mks = box(ax - 19.5, ax + 19.5, -15.75, 15.75, -ml - 9.5, -ml)
            self.P(f"mks{sfx}", f"MKS SERVO42C{lab} (carte)", -1, mks, kind="vitamin",
                   category="electronics")
        ko = cyl(cfg["mks_d"], cfg["mks_len"], -ml - cfg["mks_len"], ax, 0)
        self.P(f"zone_mks{sfx}", f"zone reservee MKS{lab} {cfg['mks_len']:.0f} mm", -1, ko,
               kind="keepout", category="keepout")
        return {"center": [ax, 0, -ml - cfg["mks_len"]], "d": cfg["mks_d"],
                "h": cfg["mks_len"], "tag": tag}

    def front_cap(self, z4: float, Rb: float, OD: float, mount, pin_holes=None) -> float:
        O = self.O
        z5 = z4 + O[2] + LIP
        body = cyl(OD, z5 - z4, z4)
        cut = [cyl(O[1] + self.press, O[2] + 0.01, z4 - 0.01),
               cyl((O[0] + O[1]) / 2 + 1.0, z5 - z4 + 2, z4 - 1)]
        s = SCREW["M4"]
        for x, y in mount:
            cut.append(cyl(s["clear"], z5 - z4 + 2, z4 - 1, x, y))
            cut.append(cyl(s["head"] + 0.4, s["head_h"] + 1, z5 - s["head_h"], x, y))
        if pin_holes:
            cut += pin_holes
        self.P("couvercle_avant", "couvercle avant (roulement de sortie)", -1,
               cut_all(body, cut), category="cap", print_up=(0, 0, 1),
               notes=f"Boulons traversants M4 : couvercle -> carter -> flasque -> segment.")
        return z5

    def output(self, z4: float, z5: float, OD: float, shoulder_d: float, shoulder_cut=None,
               k_out=(1.0, 0.0), shoulder_extra=None):
        """Epaulement + moyeu (piece 1) et bride de sortie (piece 2)."""
        O, B = self.O, self.A
        zs0 = z4 - T_SHOULDER
        hub = fuse_all([cyl(shoulder_d, T_SHOULDER, zs0),
                        cyl(O[0] - self.press * 0.5, O[2], z4)] + (shoulder_extra or []))
        r_m3 = (B[1] / 2 + O[0] / 2) / 2 + 0.5
        m3_pts = bolt_circle(4, r_m3, 45)
        cut = [cyl(B[1] + self.press, B[2] + 0.01, zs0 - 0.01),               # roulement B
               cyl((B[0] + B[1]) / 2 + 1.0, T_SHOULDER + O[2] + 2, zs0 - 1)]    # passage
        cut += holes(m3_pts, SCREW["M3"]["insert"], z4 + O[2] - 6.5, 7)
        if shoulder_cut:
            cut += shoulder_cut
        self.P("moyeu_sortie", "moyeu de sortie (epaulement)", self.body_out, cut_all(hub, cut),
               category="output", print_up=(0, 0, 1),
               anim={"type": "spin", "center": [0, 0], "k": list(k_out)},
               notes="Inserts thermiques M3 x4 sur la face superieure.")
        # bride de sortie : collet dans la levre du couvercle + plateau
        z_top_hub = z4 + O[2]
        zb0 = z5 + 0.5
        out_d = OD - 2.0
        collar_od = (O[0] + O[1]) / 2 - 0.5
        body = fuse_all([cyl(collar_od, zb0 - z_top_hub, z_top_hub), cyl(out_d, T_BRIDE, zb0)])
        r_m4 = max(r_m3 + SCREW["M3"]["head"] / 2 + SCREW["M4"]["insert"] / 2 + 2.0,
                   collar_od / 2 - 1)
        r_m4 = min(r_m4, out_d / 2 - SCREW["M4"]["insert"] / 2 - 2.0)
        out_pts = bolt_circle(6, r_m4, 0)
        L = zb0 + T_BRIDE
        cut = [cyl(self.bore + 4, L + 2, z_top_hub - 1)]
        for x, y in m3_pts:
            cut.append(cyl(SCREW["M3"]["clear"], L - z_top_hub + 2, z_top_hub - 1, x, y))
            cut.append(cyl(SCREW["M3"]["head"] + 0.4, 4.0, L - 3.4, x, y))
        cut += holes(out_pts, SCREW["M4"]["insert"], L - 8.5, 9)
        # piges de centrage (2 x d3) asymetriques
        cut += holes([(r_m4 * math.cos(math.radians(30)), r_m4 * math.sin(math.radians(30))),
                      (r_m4 * math.cos(math.radians(190)), r_m4 * math.sin(math.radians(190)))],
                     3.0 + self.tol / 2, L - 5, 6)
        self.P("bride_sortie", "bride de sortie", self.body_out, cut_all(body, cut),
               category="output", print_up=(0, 0, 1),
               anim={"type": "spin", "center": [0, 0], "k": list(k_out)},
               notes="6 inserts M4 + 2 piges d3 : interface standard du segment enfant.")
        # roulements
        self.bearing_vit(self.d.brg_out, "O", z4, body=-1)
        self.bearing_vit(self.d.brg_in, "B", zs0, body=self.body_out)
        self.bearing_vit(self.d.brg_in, "A", self.t_r - self.A[2], body=-1)
        return L, out_pts, out_d


# =====================================================================================
def build_servo(jid: str, d, cfg: dict, body_in: int, body_out: int) -> ActuatorBuild:
    """Servo MG996R (ou format standard) : l'axe de sortie sur J6, le corps decale. Pas de canal central : les cables contournent."""
    c = _Common(jid, d, cfg)
    a = 10.0
    plaque = box(a - 31, a + 31, -21, 21, 0, 6)
    mount = [(a + sx * 26, sy * 16) for sx in (-1, 1) for sy in (-1, 1)]
    trous = [box(a - 20.6, a + 20.6, -10.1, 10.1, -1, 7)]
    trous += [cyl(SCREW["M3"]["clear"], 8, -1, a + sx * 24.75, sy * 5) for sx in (-1, 1) for sy in (-1, 1)]
    trous += holes(mount, SCREW["M4"]["clear"], -1, 8)
    c.P("support_servo", "support du servo", -1, cut_all(plaque, trous), category="housing", print_up=(0, 0, 1),
        notes="4 vis M3 + ecrous pour le servo, 4 vis M4 vers le poignet.")
    corps = fuse_all([box(a - 20.35, a + 20.35, -9.85, 9.85, -21, 15.5), box(a - 27.25, a + 27.25, -9.85, 9.85, 6, 8.5), cyl(6, 4.4, 15.5)])
    c.P("servo", "servo MG996R", -1, corps, kind="vitamin", category="motor", notes="Pignons metal, rotation ~180 deg.")
    z0, L, od = 20.0, 25.0, 42.0
    out_pts = bolt_circle(4, 15.0, 45)
    disque = cut_all(cyl(od, L - z0, z0), holes(out_pts, SCREW["M3"]["clear"], z0 - 1, L - z0 + 2) + [cyl(3.4, L - z0 + 2, z0 - 1)])
    c.P("disque_sortie", "disque de sortie (sur palonnier)", body_out, disque, category="flange", print_up=(0, 0, 1),
        anim={"type": "spin", "center": [0, 0], "k": [1.0, 0.0]}, notes="Vis sur le palonnier rond du servo.")
    outline = rect2d(a, 0, 62, 42)
    b = ActuatorBuild(jid=jid, kind="servo", design=d, parts=c.parts, L=L, OD=od, a=a, rear_outline=outline, mount_pts=mount,
                      out_pts=out_pts, out_d=od, motor_square=rect2d(a, 0, 41, 20), keepout={}, vitamins=[], stack=dict(z5=L, L=L),
                      motors=[{"x": a, "tag": ""}])
    for p in b.parts:
        if p.body == -1:
            p.body = body_in
    b.info = {"L_mm": L, "OD_mm": od, "entraxe_moteur_mm": a, "rapport_total": 1, "boulons_traversants_M4": 4, "vis_M4_longueur_min": 16}
    return b


def build_cycloid(jid: str, d, cfg: dict, body_in: int, body_out: int) -> ActuatorBuild:
    c = _Common(jid, d, cfg)
    c.body_out = body_out
    E = BEARINGS[d.brg_ecc]
    tol, press = c.tol, c.press
    dt = d.disc_t
    z2 = c.z2
    zd0 = z2 + 0.5
    zd1 = zd0 + dt + 0.6
    zd_end = zd1 + dt
    z4 = zd_end + 0.5 + T_SHOULDER
    Rb = d.R + d.rp + 1.5 + SCREW["M4"]["clear"] / 2 + 0.3
    Rb = max(Rb, c.O[1] / 2 + 2.5 + SCREW["M4"]["clear"] / 2, c.chamber_clear_radius())
    OD = 2 * (Rb + SCREW["M4"]["clear"] / 2 + 3.0)

    g_in, g_m, _ = c.gear_polys()
    outline, mount, chamber = c.rear_cap(Rb, OD)
    c.motor_pinion(g_m)
    c.input_gear(g_in)
    keepout = c.motor_and_keepout()
    if c.double:
        c.second_pinion(g_in)
        c.motor_and_keepout(-c.a, "M2")

    # ---- carter : cloison + couronne de pions
    diaph_hole = max(2 * (E[0] / 2 + d.e) + 1.5, E[0] - 0.5 + 1.5)
    body = cyl(OD, z4 - c.z1, c.z1)
    pin_pts = bolt_circle(d.N, d.R, 0)
    r_bore = max(d.R, d.R - d.rp + 2 * d.e + 0.6)     # pions tenus aux 2 bouts si > R
    cut = [cyl(2 * r_bore, z4 - z2 + 1, z2), cyl(diaph_hole, T_DIAPH + 2, c.z1 - 1),
           cyl(8.0, T_DIAPH + 2, c.z1 - 1, c.a, 0)]
    if c.double:
        cut.append(cyl(8.0, T_DIAPH + 2, c.z1 - 1, -c.a, 0))
    cut += holes(pin_pts, 2 * d.rp - 0.05, z2 - 3.5, z4 - z2 + 4.5)
    cut += holes(mount, SCREW["M4"]["clear"], c.z1 - 1, z4 - c.z1 + 2)
    c.P("carter", f"carter cycloidal ({d.N} pions)", -1, cut_all(body, cut), category="housing",
        print_up=(0, 0, 1), notes=f"{d.N} piges acier d{2 * d.rp:.0f} inserees a force.")
    pin_len = (z4 + 3.5) - (z2 - 3.5)
    pins = union_all([cyl(2 * d.rp, pin_len, z2 - 3.5, x, y) for x, y in pin_pts])
    c.P("piges_couronne", f"piges couronne d{2 * d.rp:.0f}x{pin_len:.0f} (x{d.N})", -1, pins,
        kind="vitamin", category="pin")
    c.vit.append((f"Pige cylindrique acier d{2 * d.rp:.0f} x {math.ceil(pin_len)} mm", d.N))

    # ---- couvercle avant (maintient le haut des piges)
    z5 = c.front_cap(z4, Rb, OD, mount,
                     pin_holes=holes(pin_pts, 2 * d.rp + 0.05, z4 - 0.01, 3.5))

    # ---- arbre d'entree creux a double excentrique
    k_in = -1.0 / d.pre.ratio
    A = c.A
    t_r = c.t_r
    hex_top = t_r + 0.2 + c.fw + 0.3
    collar_d = min(E[0] - 0.5, diaph_hole - 1.5)
    mid_d = E[0] - 2 * d.e - 0.5
    zs0 = z4 - T_SHOULDER
    shaft = fuse_all([
        cyl(A[0] - press * 0.5, A[2], t_r - A[2]),
        hex_prism(A[0], hex_top - t_r, t_r),
        cyl(collar_d, zd0 - hex_top, hex_top),
        cyl(E[0] - press * 0.5, dt, zd0, d.e, 0),
        cyl(mid_d, 0.6, zd0 + dt),
        cyl(E[0] - press * 0.5, dt, zd1, -d.e, 0),
        cyl(A[0] - press * 0.5, zs0 + A[2] - zd_end, zd_end),
    ])
    shaft = shaft.cut(cyl(c.bore + tol, 400, -100))
    c.P("arbre_entree", "arbre d'entree creux a double excentrique", -1, shaft, category="shaft",
        print_up=(0, 0, 1), anim={"type": "spin", "center": [0, 0], "k": [k_in, 0.0]},
        notes=f"Excentricite {d.e} mm, cames a 180 deg. Canal {c.bore} mm.")
    c.bearing_vit(d.brg_ecc, "E1", zd0, d.e, 0, body=-1)
    c.bearing_vit(d.brg_ecc, "E2", zd1, -d.e, 0, body=-1)

    # ---- disques cycloidaux
    k_disc = -k_in / d.lobes
    base = disc_polygon(d.R, d.rp, d.N, d.e, tol)
    hole_pts = bolt_circle(d.out_pins, d.Rh, 0)
    cut2d = unary_union([circle2d(E[1] + press)] + [circle2d(d.hole_d, x, y) for x, y in hole_pts])
    # allegements entre les trous de sortie
    disc2d = base.difference(cut2d)
    for k, (zz, sign, rot0) in enumerate(((zd0, 1, 0.0), (zd1, -1, math.pi / d.lobes))):
        g = affinity.rotate(disc2d, rot0, origin=(0, 0), use_radians=True)
        g = affinity.translate(g, sign * d.e, 0)
        c.P(f"disque_{k + 1}", f"disque cycloidal {k + 1} ({d.lobes} lobes)", -1,
            extrude_shapely(g, dt, zz), category="disc", print_up=(0, 0, 1),
            anim={"type": "cycloid", "e": d.e, "sign": sign, "ecc": [k_in, 0.0],
                  "rot": [k_disc, 0.0], "rot0": rot0},
            notes="Profil epicycloidal decale de tol/2 (jeu fonctionnel).")

    # ---- sortie : pions de sortie sur l'epaulement
    shoulder_d = 2 * (d.Rh + d.out_pin_d / 2 + 2.0)
    pin_cut = holes(hole_pts, d.out_pin_d - 0.05, zs0 - 0.01, 6.0)
    L, out_pts, out_d = c.output(z4, z5, OD, shoulder_d, pin_cut, k_out=(k_disc, 0.0))
    opl = (zs0 + 6.0) - (z2 + 0.8)
    c.P("pions_sortie", f"pions de sortie d{d.out_pin_d:g}x{opl:.0f} (x{d.out_pins})", body_out,
        union_all([cyl(d.out_pin_d, opl, z2 + 0.8, x, y) for x, y in hole_pts]),
        kind="vitamin", category="pin",
        anim={"type": "spin", "center": [0, 0], "k": [k_disc, 0.0]})
    c.vit.append((f"Pige cylindrique acier d{d.out_pin_d:g} x {math.ceil(opl)} mm", d.out_pins))

    return _finish(c, "cycloidal", d, L, OD, outline, mount, out_pts, out_d, keepout,
                   dict(z1=c.z1, z2=z2, z4=z4, z5=z5, L=L), body_in)


# =====================================================================================
def build_planetary(jid: str, d, cfg: dict, body_in: int, body_out: int) -> ActuatorBuild:
    c = _Common(jid, d, cfg)
    c.body_out = body_out
    tol, press, m = c.tol, c.press, d.m
    PB = BEARINGS[d.planet_brg]
    z2 = c.z2
    zc0 = z2 + 0.5                      # flasque arriere du porte-satellites
    zp0 = zc0 + T_CARRIER + 0.5         # satellites
    zp1 = zp0 + c.fw
    z4 = zp1 + 0.5 + T_SHOULDER
    rr = m * (d.zr / 2 + 1.25)          # rayon de pied de la couronne
    r_tip_ring = m * (d.zr / 2 - 1.0)
    Rb = max(rr + 3.0 + SCREW["M4"]["clear"] / 2, c.O[1] / 2 + 2.5 + SCREW["M4"]["clear"] / 2,
             c.chamber_clear_radius())
    OD = 2 * (Rb + SCREW["M4"]["clear"] / 2 + 3.0)

    g_in, g_m, _ = c.gear_polys()
    outline, mount, chamber = c.rear_cap(Rb, OD)
    c.motor_pinion(g_m)
    c.input_gear(g_in)
    keepout = c.motor_and_keepout()

    # ---- phases des dentures (soleil fixe a 0, satellites et couronne calcules)
    sun2d = Polygon(external_gear(d.zs, m, tol, c.pa, flank_pts=12, arc_pts=5))
    pl0 = Polygon(external_gear(d.zp, m, tol, c.pa, flank_pts=12, arc_pts=5))
    ac = d.carrier_r
    planet_polys, planet_phases = [], []
    for k in range(d.n):
        psi = 2 * math.pi * k / d.n
        cx, cy = ac * math.cos(psi), ac * math.sin(psi)

        def mv(ph, cx=cx, cy=cy):
            return affinity.translate(affinity.rotate(pl0, ph, origin=(0, 0), use_radians=True),
                                      cx, cy)
        ph = best_phase(sun2d, mv, 2 * math.pi / d.zp)
        planet_polys.append(mv(ph))
        planet_phases.append(ph)
    ring_cut0 = Polygon(internal_gear_cutter(d.zr, m, tol, c.pa, flank_pts=12, arc_pts=5))
    ring_solid0 = circle2d(2 * rr + 6).difference(ring_cut0)

    def ring_mv(ph):
        return affinity.rotate(ring_solid0, ph, origin=(0, 0), use_radians=True)
    ring_ph = best_phase(planet_polys[0], ring_mv, 2 * math.pi / d.zr)
    ring_cut = affinity.rotate(ring_cut0, ring_ph, origin=(0, 0), use_radians=True)
    interf = sum(ring_mv(ring_ph).intersection(p).area for p in planet_polys)

    # ---- carter-couronne (couronne fixe integree)
    sun_tip = m * (d.zs + 2)
    A = c.A
    hex_corner = A[0] / math.cos(math.pi / 6)
    collar_d = hex_corner + 1.5
    diaph_hole = max(collar_d, sun_tip) + 1.5
    body = cyl(OD, z4 - c.z1, c.z1)
    cut = [extrude_shapely(ring_cut, z4 - z2 + 1, z2),
           cyl(diaph_hole, T_DIAPH + 2, c.z1 - 1), cyl(8.0, T_DIAPH + 2, c.z1 - 1, c.a, 0)]
    cut += holes(mount, SCREW["M4"]["clear"], c.z1 - 1, z4 - c.z1 + 2)
    c.P("carter", f"carter-couronne Z{d.zr} m{m}", -1, cut_all(body, cut), category="housing",
        print_up=(0, 0, 1), notes="Couronne interieure fixe integree au carter.")
    z5 = c.front_cap(z4, Rb, OD, mount)

    # ---- arbre d'entree creux + soleil integre
    k_s = -1.0 / d.pre.ratio
    t_r = c.t_r
    hex_top = t_r + 0.2 + c.fw + 0.3
    zs0 = z4 - T_SHOULDER
    shaft = fuse_all([
        cyl(A[0] - press * 0.5, A[2], t_r - A[2]),
        hex_prism(A[0], hex_top - t_r, t_r),
        cyl(collar_d, zp0 - 0.5 - hex_top, hex_top),
        extrude_shapely(sun2d, zp1 + 0.3 - (zp0 - 0.5), zp0 - 0.5),
        cyl(A[0] - press * 0.5, zs0 + A[2] - (zp1 + 0.3), zp1 + 0.3),
    ]).cut(cyl(c.bore + tol, 400, -100))
    c.P("arbre_soleil", f"arbre d'entree creux + soleil Z{d.zs}", -1, shaft, category="shaft",
        print_up=(0, 0, 1), anim={"type": "spin", "center": [0, 0], "k": [k_s, 0.0]})

    # ---- satellites
    kc = 1.0 / (1 + d.zr / d.zs)                  # porte-satellites / soleil
    k_c = k_s * kc                                # porte-satellites / moteur
    k_p = k_c - (k_s - k_c) * d.zs / d.zp         # rotation absolue d'un satellite
    nb = max(1, int(c.fw // PB[2]))
    for k, poly in enumerate(planet_polys):
        psi = 2 * math.pi * k / d.n
        cx, cy = ac * math.cos(psi), ac * math.sin(psi)
        g = poly.difference(circle2d(PB[1] + press, cx, cy))
        c.P(f"satellite_{k + 1}", f"satellite {k + 1} Z{d.zp}", body_out, extrude_shapely(g, c.fw, zp0),
            category="gear", print_up=(0, 0, 1),
            anim={"type": "planet", "psi0": psi, "ac": ac, "carrier": [k_c, 0.0],
                  "spin": [k_p, 0.0], "phase0": planet_phases[k]},
            notes=f"{nb} roulement(s) {d.planet_brg} par satellite.")
        for j in range(nb):
            c.bearing_vit(d.planet_brg, f"P{k + 1}", zp0 + j * PB[2], cx, cy, body=body_out)
    c.vit.append((f"Axe acier d{PB[0]} x {math.ceil(zs0 + 5 - (zc0 - 0.01))} mm (satellites)", d.n))

    # ---- porte-satellites : flasque arriere + epaulement (sortie)
    plate_d = 2 * (r_tip_ring - 1.2)
    pin_pts = bolt_circle(d.n, ac, 0)
    so_pts = bolt_circle(d.n, ac, 180 / d.n) if d.standoffs else []
    rear = tube(plate_d, sun_tip + 1.5, T_CARRIER, zc0)
    rcut = holes(pin_pts, PB[0] - 0.05, zc0 - 1, T_CARRIER + 2)
    for x, y in so_pts:
        rcut += [cyl(SCREW["M3"]["clear"], T_CARRIER + 2, zc0 - 1, x, y),
                 cyl(SCREW["M3"]["head"] + 0.4, 2.2, zc0 - 0.01, x, y)]
    c.P("porte_sat_arriere", "porte-satellites (flasque arriere)", body_out, cut_all(rear, rcut),
        category="output", print_up=(0, 0, 1),
        anim={"type": "spin", "center": [0, 0], "k": [k_c, 0.0]})
    extra = [cyl(8.0, zs0 - (zc0 + T_CARRIER), zc0 + T_CARRIER, x, y) for x, y in so_pts]
    scut = holes(pin_pts, PB[0] - 0.05, zs0 - 0.01, 5.0)
    scut += holes(so_pts, SCREW["M3"]["insert"], zc0 + T_CARRIER - 0.01, 6.0)
    # satellites : degagement dans l'epaulement (rondelle de 0.5 mm)
    L, out_pts, out_d = c.output(z4, z5, OD, plate_d, scut, k_out=(k_c, 0.0), shoulder_extra=extra)

    info_extra = {"interference_couronne_mm2": round(interf, 3), "k_porte_satellites": k_c}
    b = _finish(c, "planetary", d, L, OD, outline, mount, out_pts, out_d, keepout,
                dict(z1=c.z1, z2=z2, z4=z4, z5=z5, L=L), body_in)
    b.info.update(info_extra)
    return b


def _finish(c: _Common, kind, d, L, OD, outline, mount, out_pts, out_d, keepout, stack,
            body_in) -> ActuatorBuild:
    # les pieces marquees body=-1 appartiennent au corps parent (fixe)
    for p in c.parts:
        if p.body == -1:
            p.body = body_in
    b = ActuatorBuild(jid=c.jid, kind=kind, design=d, parts=c.parts, L=L, OD=OD, a=c.a,
                      rear_outline=outline, mount_pts=mount, out_pts=out_pts, out_d=out_d,
                      motor_square=rect2d(c.a, 0, c.m_body, c.m_body), keepout=keepout,
                      vitamins=c.vit, stack=stack,
                      motors=getattr(c, "motors", [{"x": c.a, "tag": ""}]))
    b.info = {"L_mm": round(L, 2), "OD_mm": round(OD, 2), "entraxe_moteur_mm": c.a,
              "rapport_total": d.ratio, "boulons_traversants_M4": len(mount),
              "vis_M4_longueur_min": math.ceil(stack["z5"] + 6)}
    return b
