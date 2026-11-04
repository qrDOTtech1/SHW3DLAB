"""Tete de changement d'outil ACTIVE (axe 6) + base de couplage standard des outils.

Principe (verrouillage a baionnette motorise) :
  * l'outil plonge en ligne droite : ses 3 ergots traversent les fenetres de la
    plaque de face puis celles de la bague de verrouillage ;
  * le servo MG90S tourne de 90 deg ; son pignon (Z16) entraine la denture exterieure
    de la bague (Z48) -> la bague tourne de 30 deg et passe AU-DESSUS des ergots ;
  * des rampes sous la bague tirent les ergots : la base de l'outil est plaquee sur
    les 3 cones detrompeurs asymetriques (zero jeu en torsion, un seul sens possible) ;
  * rotation inverse de 90 deg -> liberation dans le rack.
Interface electrique : bloc de 6 pogo pins AU CENTRE de la tete, sous la queue de l'outil,
encadre par 2 aimants de pre-alignement. Le verrouillage tire l'outil vers le bras : la face
inferieure de la queue (platine de 6 pastilles dorees) ecrase les pogo de `pogo_preload`.
Les 6 fils (V+, VCC, GND, SDA/TX, SCL/RX, SIG) + 3 fils servo tombent dans le tunnel central.

Repere de la tete : z = 0 sur la bride de sortie de l'axe 6, +z vers l'outil.
Repere des outils : z = 0 sur la face de couplage (= dessus de la plaque de face).
"""
from __future__ import annotations

import math

import cadquery as cq
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..cad.util import (SCREW, extrude_shapely, cyl, tube, cone, box, union_all, cut_all,
                        fuse_all, holes, circle2d, rect2d, bolt_circle)
from ..gears.involute import external_gear
from .actuator import best_phase
from .model import Part

# --- servo MG90S (cotes constructeur arrondies)
MG = dict(L=22.8, W=12.2, H=22.7, tab_z=15.9, tab_t=2.5, tab_L=32.3, dome_d=11.8,
          dome_h=4.3, spline_d=4.8, spline_h=3.2, shaft_off=5.3, screw_sp=27.8)
PINION_Z, RING_Z, GEAR_M = 16, 48, 1.0
PINOUT = ["V+ 12V/24V", "VCC 5V/3V3", "GND", "DATA1 SDA / TX", "DATA2 SCL / RX", "SIG (PWM/ADC)"]
CONE_ANGLES = (70.0, 125.0, 250.0)       # asymetriques -> detrompage
LUG_ANGLES = (0.0, 120.0, 240.0)


class HeadGeom:
    """Toutes les cotes de la tete, partagees avec la base des outils."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.tol = cfg["tol"]
        self.D = cfg["tool_d"]
        self.bore = cfg["cable_bore"]
        self.floor = 5.0
        self.r_sp = max(13.0, self.bore / 2 + 5.5)            # rayon de la queue d'outil
        self.lug_r = self.r_sp + 4.5
        self.lug_h = 6.0                     # ergots renforces (piges acier d3 inserees)
        self.lug_w_deg = 24.0
        self.win_deg = self.lug_w_deg + 5.0
        self.ring_rot = cfg["lock_ring_rot"]
        self.servo_rot = 90.0
        # rapport bague/pignon impose : 90 deg servo -> ring_rot deg bague
        self.zr = max(RING_Z, int(round(PINION_Z * self.servo_rot / self.ring_rot)))
        self.Rr = GEAR_M * self.zr / 2
        self.Rp = GEAR_M * PINION_Z / 2
        self.r_servo = self.Rr + self.Rp
        self.z_servo0 = self.floor
        self.z_spline_top = self.z_servo0 + MG["H"] + MG["dome_h"] + MG["spline_h"]
        self.ring_t = 6.0
        self.zr0 = self.z_spline_top - MG["spline_h"] + 0.3   # bague [zr0, zr1] au-dessus du dome
        self.zr1 = self.zr0 + self.ring_t
        self.face_t = 4.0
        self.zf0 = self.zr1 + 0.3
        self.z_face = self.zf0 + self.face_t                 # face de couplage
        self.lug_top = self.zr0 - 0.4
        self.lug_bot = self.lug_top - self.lug_h
        self.spigot_len = self.z_face - self.lug_bot
        self.r_cone = self.D / 2 - 7.5
        self.cone = dict(d0=10.0, d1=4.5, h=6.0)
        self.pogo_ang = 0.0                    # bloc pogo central, oriente selon X
        self.pogo_len = cfg["pogo_n"] * cfg["pogo_pitch"] + 3.0
        self.mag_off = cfg["pogo_w"] / 2 + cfg["pogo_mag_d"] / 2 + 1.6   # aimants de part et d'autre (Y)
        # pointe des pogo au repos : depasse la face de la queue de `pogo_preload`
        self.z_pogo_tip = None
        self.H = self.z_face

    def servo_frame(self):
        """Position de l'axe du servo et orientation (tangentielle) du corps."""
        return (self.r_servo, 0.0), 90.0        # axe servo sur +X, corps le long de Y

    def servo_footprint(self, grow=0.0) -> Polygon:
        (sx, sy), _ = self.servo_frame()
        # corps : le long de Y, l'axe est decale de shaft_off vers +Y du centre du corps
        cy = sy - MG["shaft_off"]
        return rect2d(sx, cy, MG["W"] + grow, MG["L"] + grow)

    def pogo_rect(self, grow=0.0) -> Polygon:
        """Empreinte du bloc pogo, centre sur l'axe (longueur selon X)."""
        return rect2d(0, 0, self.pogo_len + grow, self.cfg["pogo_w"] + grow)

    def mag_pts(self):
        return [(0.0, self.mag_off), (0.0, -self.mag_off)]

    def cone_pts(self):
        return [(self.r_cone * math.cos(math.radians(a)), self.r_cone * math.sin(math.radians(a)))
                for a in CONE_ANGLES]

    def lug_poly(self, grow=0.0, rot_deg=0.0) -> Polygon:
        polys = []
        half = math.radians(self.lug_w_deg / 2) + grow / self.lug_r
        for a0 in LUG_ANGLES:
            a = math.radians(a0 + rot_deg)
            pts = [(0, 0)]
            for i in range(9):
                t = a - half + 2 * half * i / 8
                pts.append(((self.lug_r + grow) * math.cos(t), (self.lug_r + grow) * math.sin(t)))
            polys.append(Polygon(pts))
        return unary_union(polys)

    def window_poly(self, r_out, rot_deg=0.0) -> Polygon:
        polys = []
        half = math.radians(self.win_deg / 2)
        for a0 in LUG_ANGLES:
            a = math.radians(a0 + rot_deg)
            pts = [(0, 0)] + [(r_out * math.cos(a - half + 2 * half * i / 8),
                               r_out * math.sin(a - half + 2 * half * i / 8)) for i in range(9)]
            polys.append(Polygon(pts))
        return unary_union(polys)

    def face_screw_pts(self):
        r = self.D / 2 - 4.0
        forbid = unary_union([self.servo_footprint(6)] +
                             [circle2d(self.cone["d0"] + 6, x, y) for x, y in self.cone_pts()])
        pts = []
        for k in range(24):
            a = math.radians(15 * k + 7.5)
            p = (r * math.cos(a), r * math.sin(a))
            if circle2d(SCREW["M3"]["insert"] + 3, *p).intersects(forbid):
                continue
            if any(math.dist(p, q) < 24 for q in pts):
                continue
            pts.append(p)
        return pts


def build_head(cfg: dict, act6, body: int) -> tuple[list[Part], HeadGeom]:
    """Tete montee sur la bride de l'axe 6 (repere actionneur J6, decale de L)."""
    g = HeadGeom(cfg)
    tol = g.tol
    L = act6.L
    parts = []

    def P(pid, label, shape, **kw):
        sh = shape.translate((0, 0, L))
        if kw.get("anim"):
            kw["anim"] = dict(kw["anim"])
        parts.append(Part(id=f"TETE_{pid}", name=f"Tete axe 6 - {label}", group="TETE",
                          body=body, shape=sh, **kw))

    # ---------------- corps de tete
    D, H = g.D, g.zf0
    body_s = cyl(D, H, 0)
    cut = [cyl(g.bore + 4, H + 2, -1)]                                  # tunnel central
    # fixation sur la bride J6 : vis M4 tete dans la tete (lamage)
    for x, y in act6.out_pts:
        cut += [cyl(SCREW["M4"]["clear"], g.floor + 2, -1, x, y),
                cyl(SCREW["M4"]["head"] + 0.6, H, g.floor, x, y)]
    r = math.hypot(*act6.out_pts[0])
    for ang in (30, 190):
        cut.append(cyl(3.0 + tol, 4.0, -0.01, r * math.cos(math.radians(ang)),
                       r * math.sin(math.radians(ang))))
    # gorge de la bague (dents exterieures) + zone des ergots + alesage de la queue
    ring_od = 2 * (g.Rr + GEAR_M) + 1.2
    cut.append(cyl(ring_od, g.zf0 - g.zr0 + 0.4, g.zr0 - 0.4))
    cut.append(cyl(2 * (g.lug_r + 0.8), g.zr0 - g.lug_bot + 0.4, g.lug_bot - 0.4))
    # logement servo : corps + pattes + dome/pignon
    (sx, sy), _ = g.servo_frame()
    fp = g.servo_footprint(2 * tol + 0.2)
    cut.append(extrude_shapely(fp, H - g.z_servo0 + 1, g.z_servo0))
    tabs = rect2d(sx, sy - MG["shaft_off"], MG["W"] + 0.6, MG["tab_L"] + 0.6)
    cut.append(extrude_shapely(tabs, H - (g.z_servo0 + MG["tab_z"]) + 1, g.z_servo0 + MG["tab_z"]))
    cut.append(cyl(2 * (g.Rp + GEAR_M) + 1.5, g.zf0 - g.zr0 + 1, g.zr0 - 0.5, sx, sy))
    for dy in (-MG["screw_sp"] / 2, MG["screw_sp"] / 2):                  # vis M2 des pattes
        cut.append(cyl(1.8, 8, g.z_servo0 + MG["tab_z"] - 7.9, sx, sy - MG["shaft_off"] + dy))
    # logement du porte-pogo central (sous la queue d'outil) ; fils -> tunnel central
    hold_h = cfg["pogo_depth"] + 2.0
    z_h1 = g.lug_bot - 0.4
    z_h0 = z_h1 - hold_h
    cut.append(cyl(2 * g.r_sp, hold_h + 0.01, z_h0))
    # canal des 3 fils du servo -> tunnel
    cut.append(_radial_channel(sx, 0.0, 5.0, g.z_servo0 + 1.0, 4.0))
    # inserts de la plaque de face
    fsp = g.face_screw_pts()
    cut += holes(fsp, SCREW["M3"]["insert"], g.zf0 - 6, 6.01)
    # allegements (poches entre les elements)
    P("corps", "corps de tete (servo integre)", cut_all(body_s, cut), category="tool",
      print_up=(0, 0, 1), notes="Imprimer bride en bas. Servo MG90S insere par le haut, "
                                "2 vis M2x8 dans les pattes.")

    # ---------------- bague de verrouillage
    ring2d = Polygon(external_gear(g.zr, GEAR_M, tol, 20, flank_pts=10, arc_pts=4))
    pin2d0 = Polygon(external_gear(PINION_Z, GEAR_M, tol, 20, flank_pts=10, arc_pts=4))

    def mv(ph):
        return affinity.translate(affinity.rotate(pin2d0, ph, origin=(0, 0), use_radians=True), sx, sy)
    ph = best_phase(ring2d, mv, 2 * math.pi / PINION_Z)
    ring2d = ring2d.difference(circle2d(2 * (g.r_sp + 0.6)))
    ring2d = ring2d.difference(g.window_poly(g.lug_r + 0.7))
    ring = extrude_shapely(ring2d, g.ring_t, g.zr0)
    # rampes de serrage sous la bague : 6 marches de 0.1 mm sur la course de verrouillage
    ramps = []
    steps = 6
    for a0 in LUG_ANGLES:
        for i in range(steps):
            t0 = a0 - g.win_deg / 2 - (g.ring_rot) * (i + 1) / steps
            t1 = a0 - g.win_deg / 2 - (g.ring_rot) * i / steps
            seg = _sector(g.r_sp + 0.8, g.lug_r + 0.3, t0 - g.lug_w_deg, t1)
            ramps.append(extrude_shapely(seg, 0.1 * (i + 1) + 0.01, g.zr0 - 0.1 * (i + 1)))
    ring = fuse_all([ring] + ramps)
    P("bague", f"bague de verrouillage Z{g.zr} (baionnette)", ring, category="output",
      print_up=(0, 0, -1),
      anim={"type": "lock", "center": [0, 0], "deg": -g.ring_rot},
      notes=f"Rotation {g.ring_rot:g} deg pour 90 deg servo. Rampes 0.6 mm = pre-serrage.")

    # ---------------- pignon servo
    pin2d = mv(ph).difference(circle2d(MG["spline_d"] - 0.2, sx, sy))
    pin = extrude_shapely(mv(ph), g.ring_t, g.zr0)
    pin = cut_all(pin, [cyl(MG["spline_d"] - 0.2, MG["spline_h"] - 0.3 + 0.01, g.zr0 - 0.01, sx, sy),
                        cyl(2.2, 10, g.zr0 - 1, sx, sy), cyl(4.2, 2.0, g.zr1 - 1.99, sx, sy)])
    P("pignon_servo", f"pignon servo Z{PINION_Z} (cannelure MG90S)", pin, category="gear",
      print_up=(0, 0, 1), anim={"type": "lock_pinion", "center": [sx, sy], "deg": g.servo_rot},
      notes="Emmanche sur la cannelure 4.8 mm + vis M2 de palonnier.")

    # ---------------- plaque de face (fenetres, cones, pogo)
    face = cyl(D, g.face_t, g.zf0)
    fcut = [extrude_shapely(circle2d(2 * (g.r_sp + tol)).union(g.window_poly(g.lug_r + 0.7)),
                            g.face_t + 2, g.zf0 - 1)]
    for x, y in fsp:
        fcut += [cyl(SCREW["M3"]["clear"], g.face_t + 2, g.zf0 - 1, x, y),
                 cyl(SCREW["M3"]["head"] + 0.4, 2.0, g.z_face - 1.99, x, y)]
    cones = [cone(g.cone["d0"], g.cone["d1"], g.cone["h"], g.z_face, x, y) for x, y in g.cone_pts()]
    face = cut_all(fuse_all([face] + cones), fcut)
    P("plaque_face", "plaque de couplage (3 cones detrompeurs)", face, category="tool",
      print_up=(0, 0, -1), notes="Cones asymetriques a " + ", ".join(f"{a:g}" for a in CONE_ANGLES)
      + " deg : un seul sens d'emboitement.")

    # ---------------- elements du commerce
    servo = fuse_all([
        extrude_shapely(g.servo_footprint(), MG["H"], g.z_servo0),
        extrude_shapely(rect2d(sx, sy - MG["shaft_off"], MG["W"], MG["tab_L"]), MG["tab_t"],
                        g.z_servo0 + MG["tab_z"]),
        cyl(MG["dome_d"], MG["dome_h"], g.z_servo0 + MG["H"], sx, sy),
        cyl(MG["spline_d"] - 0.2, MG["spline_h"], g.z_servo0 + MG["H"] + MG["dome_h"], sx, sy)])
    P("servo", "servo MG90S (verrouillage)", servo, kind="vitamin", category="motor")
    # ---------------- porte-pogo central + aimants
    z_tip = g.lug_bot + cfg["pogo_preload"]              # pointes au repos (au-dessus de la face)
    g.z_pogo_tip = z_tip
    zb_pogo = z_tip - cfg["pogo_depth"]                 # base du corps de connecteur
    holder = cyl(2 * g.r_sp - 2 * tol, hold_h, z_h0)
    hcut = [extrude_shapely(g.pogo_rect(2 * tol), z_h1 - zb_pogo + 1, zb_pogo)]
    for x, y in g.mag_pts():
        hcut.append(cyl(cfg["pogo_mag_d"] + tol, cfg["pogo_mag_h"] + 0.2, z_h1 - cfg["pogo_mag_h"] - 0.19, x, y))
    # fentes : les 6 fils plongent dans le tunnel central
    hcut.append(box(-g.pogo_len / 2, g.pogo_len / 2, -2.0, 2.0, z_h0 - 1, zb_pogo + 0.01))
    hcut += [cyl(2.2, hold_h + 2, z_h0 - 1, sx_, 0) for sx_ in (-g.pogo_len / 2 - 3.0, g.pogo_len / 2 + 3.0)]
    P("porte_pogo", "porte-pogo central + 2 aimants de centrage", cut_all(holder, hcut), category="tool",
      print_up=(0, 0, 1),
      notes=f"Pointes des pogo {cfg['pogo_preload']:g} mm au-dessus de la face de la queue : "
            f"ecrasement garanti par le verrouillage (course ressort {cfg['pogo_travel']:g} mm). "
            "Fils directement dans le tunnel central.")
    pogo = extrude_shapely(g.pogo_rect(), cfg["pogo_depth"], zb_pogo)
    P("pogo", "bloc 6 pogo pins (ressorts) - cote robot", pogo, kind="vitamin",
      category="electronics", notes=" | ".join(f"{i + 1}:{n}" for i, n in enumerate(PINOUT)))
    mags = union_all([cyl(cfg["pogo_mag_d"], cfg["pogo_mag_h"], z_h1 - cfg["pogo_mag_h"] - 0.19, x, y)
                      for x, y in g.mag_pts()])
    P("aimants", f"aimants de centrage d{cfg['pogo_mag_d']:g}x{cfg['pogo_mag_h']:g} (x2)", mags,
      kind="vitamin", category="pin")
    return parts, g


def _sector(r0, r1, a0_deg, a1_deg, n=10) -> Polygon:
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    pts = [(r1 * math.cos(a0 + (a1 - a0) * i / n), r1 * math.sin(a0 + (a1 - a0) * i / n))
           for i in range(n + 1)]
    pts += [(r0 * math.cos(a1 - (a1 - a0) * i / n), r0 * math.sin(a1 - (a1 - a0) * i / n))
            for i in range(n + 1)]
    return Polygon(pts)


def _radial_channel(r_end, ang_deg, w, z0, h):
    a = math.radians(ang_deg)
    ch = box(0, r_end, -w / 2, w / 2, z0, z0 + h)
    return ch.rotate((0, 0, 0), (0, 0, 1), ang_deg)


# =====================================================================================
def tool_base(g: HeadGeom, cfg: dict, eeprom: bool = False, t: float = 8.0):
    """Base de couplage standard heritee par TOUS les outils (repere outil).

    Retourne (solide, cutters) : les cutters doivent etre appliques APRES la fusion du
    corps specifique de l'outil (canaux de fils, pogo...).
    """
    tol = g.tol
    Dt = g.D - 4.0
    base = cyl(Dt, t, 0)
    # queue de verrouillage + ergots (vers -z, dans la tete)
    spig = cyl(2 * g.r_sp - 2 * tol, g.spigot_len, -g.spigot_len)
    lugs = extrude_shapely(g.lug_poly(-tol).difference(circle2d(2 * g.r_sp - 1)), g.lug_h - tol,
                           -g.spigot_len)
    base = fuse_all([base, spig, lugs])
    # pige acier d3 x 12 radiale dans chaque ergot : l'effort de verrouillage passe dans l'acier
    zl = -g.spigot_len + (g.lug_h - tol) / 2
    for a0 in LUG_ANGLES:
        pin = cyl(3.0 - 0.05, 12.0, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((g.lug_r - 11.5, 0, zl))
        base = base.cut(pin.rotate((0, 0, 0), (0, 0, 1), a0))
    # gorge de rack (prise par la fourche du support)
    groove = tube(Dt + 2, Dt - 5, 3.0, t - 5.0)
    # alesage central (fils vers l'outil) arrete 5 mm au-dessus de la platine pogo
    cutters = [groove, cyl(g.bore, g.spigot_len + t - 5 + 1, -g.spigot_len + 5)]
    cutters += [cyl(2.6, 7.0, -g.spigot_len - 0.5, sx_, 0) for sx_ in (-g.pogo_len / 2 + 2, g.pogo_len / 2 - 2)]
    # cones femelles (detrompeurs) + jeu
    for x, y in g.cone_pts():
        cutters.append(cone(g.cone["d0"] + 2 * tol, g.cone["d1"] + 2 * tol, g.cone["h"] + 0.3, -0.01, x, y))
    # platine 6 pastilles dorees (PCB 1.6 mm) sur la face inferieure de la queue + aimants
    zq = -g.spigot_len
    cutters.append(extrude_shapely(g.pogo_rect(2 * tol + 1.0), 1.7, zq - 0.01))
    for x, y in g.mag_pts():
        cutters.append(cyl(cfg["pogo_mag_d"] + tol, cfg["pogo_mag_h"] + 0.2, zq - 0.01, x, y))
    if eeprom:   # poche PCB EEPROM I2C 24C02 (SOIC-8 sur carte 10x8), fils vers l'alesage
        e2d = rect2d(g.bore / 2 + 7.0, 0, 8.6, 10.6)
        cutters.append(extrude_shapely(e2d, 3.0, 1.5))
        cutters.append(box(g.bore / 2 - 1, g.bore / 2 + 3, -1.5, 1.5, 2.0, 4.5))
    return base, cutters, Dt, t
