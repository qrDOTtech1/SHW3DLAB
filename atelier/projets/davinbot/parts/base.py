"""Socle (axe 1), plateau, boitier des 4 capteurs RFP602, rack d'outils."""
from __future__ import annotations

import math

import numpy as np

from ..cad.util import (SCREW, box, cyl, tube, apply_T, union_all, cut_all, fuse_all, holes,
                        bolt_circle, cone)
from .links import rear_cutters
from .model import Part


def build_socle(cfg: dict, zb: float, wlb: float, T1, act1) -> tuple[list[Part], dict]:
    """Socle cylindrique (moteur J1 suspendu dedans) + plateau porteur de J1."""
    D = cfg["base_d"]
    w = max(4.0, cfg["wall"])
    floor = 5.0
    z_top = zb - wlb
    r_boss = D / 2 - 7.0
    a = act1.a
    parts = []
    # ---------------- socle
    shell = tube(D, D - 2 * w, z_top, 0)
    body = fuse_all([shell, cyl(D, floor, 0)])
    bosses = bolt_circle(8, r_boss, 22.5)
    adds = [cyl(11.0, z_top - floor, floor, x, y) for x, y in bosses]
    # patte de fixation du boitier capteurs (+X)
    adds.append(box(D / 2 - 6, D / 2 + 10, -26, 26, 0, 34))
    body = fuse_all([body] + adds)
    cut = [cyl(SCREW["M4"]["insert"], 9, z_top - 8.99, x, y) for x, y in bosses]
    # MKS du moteur J1 : fenetre laterale (-X, cote moteur) + fenetre au sol
    z_mks0 = zb - cfg["motor_len"] - cfg["mks_len"]
    z_mks1 = zb - cfg["motor_len"] + 4
    cut.append(box(-D / 2 - 1, -D / 2 + w + 20, -32, 32, max(floor + 3, z_mks0), z_mks1))
    cut.append(cyl(cfg["mks_d"] + 2, floor + 2, -1, -a, 0))
    # passage de cables (+Y) et fixation table (4 x M5)
    cut.append(cyl(24.0, w + 30, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((0, D / 2 - w - 12, 26)))
    for x, y in bolt_circle(4, D / 2 - 14, 45):
        cut += [cyl(SCREW["M5"]["clear"], floor + 2, -1, x, y),
                cyl(SCREW["M5"]["head"] + 0.6, z_top, floor, x, y)]
    for yy in (-14, 14):
        for zz in (10, 24):
            h = cyl(SCREW["M4"]["insert"], 9, 0).rotate((0, 0, 0), (0, 1, 0), 90)
            cut.append(h.translate((D / 2 + 10 - 8.99, yy, zz)))
    parts.append(Part(id="BASE_socle", name="Socle - fut (moteur J1 loge)", group="BASE", body=0,
                      shape=cut_all(body, cut), category="structure", print_up=(0, 0, 1),
                      notes="Fenetres d'acces au MKS SERVO42C (ecran OLED/boutons) cote -X et au sol."))
    # ---------------- plateau + nervures
    plate = cyl(D, wlb, z_top)
    ribs = []
    for k in range(8):
        ang = 22.5 + 45 * k + 22.5
        rib = box(act1.OD / 2 - 2, D / 2 - w - 0.5, -2.5, 2.5, z_top - 16, z_top)
        rib = rib.rotate((0, 0, 0), (0, 0, 1), ang)
        ribs.append((ang, rib))
    keep = []
    for ang, rib in ribs:
        ca = math.cos(math.radians(ang))
        sa = math.sin(math.radians(ang))
        # ecarte les nervures qui croisent le moteur / sa zone MKS (moteur en -X)
        if ca < -0.35 and abs(sa) < 0.94:
            continue
        keep.append(rib)
    plate = fuse_all([plate] + keep)
    cut = [apply_T(c, T1) for c in rear_cutters(act1, wlb, cfg)]
    for x, y in bosses:
        cut += [cyl(SCREW["M4"]["clear"], wlb + 2, z_top - 1, x, y),
                cyl(SCREW["M4"]["head"] + 0.6, 3.0, zb - 2.99, x, y)]
    parts.append(Part(id="BASE_plateau", name="Socle - plateau porteur J1 (nervure)", group="BASE",
                      body=0, shape=cut_all(plate, cut), category="housing", print_up=(0, 0, -1),
                      notes="Imprimer face superieure sur le plateau (nervures vers le haut)."))
    info = {"z_top": z_top, "lug_x": D / 2 + 10}
    return parts, info


def build_sensor_box(cfg: dict, x_base: float) -> tuple[list[Part], dict]:
    """Boitier des 4 capteurs RFP602 en matrice carree (sous le chassis de la toile)."""
    S0 = cfg["rfp_spacing"]
    margin = 18.0
    bed = min(cfg["bed_x"], cfg["bed_y"]) - 2 * cfg["bed_margin"]
    S = min(S0 + 2 * margin, bed)
    spacing = S - 2 * margin
    H, lid_t = 16.0, 4.0
    pad = cfg["rfp_pad_d"]
    tol = cfg["tol"]
    cx = x_base + 25.0 + S / 2
    pts = [(cx + sx * spacing / 2, sy * spacing / 2) for sx in (-1, 1) for sy in (-1, 1)]
    parts = []
    body = box(cx - S / 2, cx + S / 2, -S / 2, S / 2, 0, H)
    cut = [box(cx - 25, cx + 25, -20, 20, 3, H + 1)]                      # baie electronique
    for x, y in pts:
        cut.append(cyl(pad + 6, H - 3 + 1, 3, x, y))                       # puits du piston
        cut.append(cyl(pad + 1.0, 0.8, 3 - 0.8, x, y))                     # lamage pastille
        # queue du capteur -> baie centrale
        L = math.hypot(x - cx, y)
        ang = math.degrees(math.atan2(-y, cx - x))
        ch = box(0, L - 20, -4.0, 4.0, 1.5, 3.2).rotate((0, 0, 0), (0, 0, 1), ang).translate((x, y, 0))
        cut.append(ch)
    cut.append(box(cx - S / 2 - 1, cx - 24, -5, 5, 3, 10))                 # sortie cable vers le socle
    screw_pts = [(cx + sx * (S / 2 - 7), sy * (S / 2 - 7)) for sx in (-1, 1) for sy in (-1, 1)]
    screw_pts += [(cx, S / 2 - 7), (cx, -S / 2 + 7)]
    cut += holes(screw_pts, SCREW["M3"]["insert"], H - 6, 6.01)
    cut += [cyl(SCREW["M4"]["insert"], 9, 0).rotate((0, 0, 0), (0, 1, 0), 90)
            .translate((cx - S / 2 - 0.01, yy, 8)) for yy in (-30, 30)]
    parts.append(Part(id="CAPT_boitier", name="Capteurs - boitier matrice 4 x RFP602", group="CAPTEURS",
                      body=0, shape=cut_all(body, cut), category="sensor", print_up=(0, 0, 1),
                      notes=f"Matrice {spacing:.0f} x {spacing:.0f} mm : triangulation du point d'appui "
                            "(barycentre des 4 forces)."))
    lid = box(cx - S / 2, cx + S / 2, -S / 2, S / 2, H, H + lid_t)
    lcut = [cyl(pad + 2 + 2 * tol, lid_t + 2, H - 1, x, y) for x, y in pts]
    for x, y in screw_pts:
        lcut += [cyl(SCREW["M3"]["clear"], lid_t + 2, H - 1, x, y),
                 cyl(SCREW["M3"]["head"] + 0.4, 2.0, H + lid_t - 1.99, x, y)]
    parts.append(Part(id="CAPT_couvercle", name="Capteurs - couvercle guides de pistons", group="CAPTEURS",
                      body=0, shape=cut_all(lid, lcut), category="sensor", print_up=(0, 0, 1)))
    for i, (x, y) in enumerate(pts):
        z0 = 3.0 + 0.3
        pis = fuse_all([cyl(pad - 1.0, 1.5, z0, x, y),
                        cyl(pad + 2, H + lid_t - z0 - 1.5 + 0.8, z0 + 1.5, x, y),
                        cyl(pad + 10, 3.0, H + lid_t + 0.8, x, y)])
        parts.append(Part(id=f"CAPT_piston_{i + 1}", name=f"Capteurs - piston {i + 1}", group="CAPTEURS",
                          body=0, shape=pis, category="sensor", print_up=(0, 0, 1),
                          notes="Teton central = diametre sensible - 1 mm : concentre l'effort sur la zone active."))
        parts.append(Part(id=f"CAPT_rfp602_{i + 1}", name=f"RFP602 n{i + 1}", group="CAPTEURS", body=0,
                          shape=cyl(pad, 0.3, 3 - 0.3, x, y), kind="vitamin", category="electronics"))
    # liaison socle -> boitier
    br = box(x_base, cx - S / 2, -40, 40, 0, 16)
    bcut = []
    for yy in (-14, 14):
        for zz in (10,):
            bcut.append(cyl(SCREW["M4"]["clear"], 20, 0).rotate((0, 0, 0), (0, 1, 0), 90)
                        .translate((x_base - 1, yy, zz)))
    for yy in (-30, 30):
        bcut.append(cyl(SCREW["M4"]["clear"], 30, 0).rotate((0, 0, 0), (0, 1, 0), 90)
                    .translate((cx - S / 2 - 26, yy, 8)))
    bcut.append(box(x_base - 1, cx - S / 2 + 1, -5, 5, 3, 10))
    parts.append(Part(id="CAPT_liaison", name="Capteurs - liaison rigide socle/boitier", group="CAPTEURS",
                      body=0, shape=cut_all(br, bcut), category="structure", print_up=(0, 0, 1),
                      notes="Reference mecanique commune robot / toile (calibration des forces)."))
    return parts, {"spacing": spacing, "S": S, "center": [cx, 0], "pts": pts,
                   "spacing_clamped": spacing != S0}


def build_rack(cfg: dict, g, origin=None, n_slots: int = 5) -> tuple[list[Part], list]:
    """Rack de stockage « face en haut » : chaque outil est suspendu par sa gorge dans une
    fourche, face de couplage vers le haut. Le robot arrive tete en bas (posture naturelle),
    verrouille, puis ressort l'outil par l'ouverture de la fourche (+Y) avant de remonter.
    Montants en 2 troncons (volume d'impression) emboites et boulonnes.

    Rack en ARC centre sur l'axe J1 : chaque fourche est a la meme portee (rayon rack_r) et
    s'ouvre radialement VERS le robot -> meme geste pour tous les outils, jamais de sortie au
    droit de l'axe J1 (singularite), angles J1 loin des butees."""
    R = cfg["rack_r"]
    Dt = g.D - 4.0
    slot_w = Dt - 5 + 2 * cfg["tol"] + 1.0
    fork_L = Dt + 30
    pitch = Dt + cfg["rack_jeu"]                         # arc serre : J1 reste loin de ses butees
    zf = cfg["rack_h"]                                   # dessus des fourches
    parts, slots = [], []
    zsplit = min(cfg["bed_z"] - 20, zf * 0.62)
    dth = math.degrees(pitch / R)
    for i in range(n_slots):
        th = (i - (n_slots - 1) / 2) * dth                # rotation de la fourche autour de J1
        ox, oy = 0.0, -R - 15 - fork_L / 2                # repere local : fourche centree sur -Y
        yc = oy + 15 + fork_L / 2
        xc = ox

        def rz(shape, th=th):
            return shape.rotate((0, 0, 0), (0, 0, 1), th)
        z = zf - 2.6
        f = box(xc - pitch / 2 + 4, xc + pitch / 2 - 4, oy + 15, oy + 15 + fork_L, z, z + 2.6)
        f = f.cut(box(xc - slot_w / 2, xc + slot_w / 2, yc, oy + 15 + fork_L + 1, z - 1, z + 4))
        f = f.cut(cyl(slot_w, 6, z - 1, xc, yc))
        f = fuse_all([f, box(xc - pitch / 2 + 4, xc + pitch / 2 - 4, oy + 15, oy + 25, z - 12, z + 2.6),
                      # chanfreins d'entree (guidage de l'outil quand le robot le re-engage)
                      box(xc - slot_w / 2 - 6, xc - slot_w / 2, oy + 15 + fork_L - 12, oy + 15 + fork_L, z, z + 2.6),
                      box(xc + slot_w / 2, xc + slot_w / 2 + 6, oy + 15 + fork_L - 12, oy + 15 + fork_L, z, z + 2.6)])
        f = cut_all(f, [cyl(SCREW["M4"]["clear"], 14, 0).rotate((0, 0, 0), (1, 0, 0), -90)
                        .translate((xc + sx * 8, oy + 14, z - 6)) for sx in (-1, 1)])
        # fourche en COIN : taillee selon les 2 bissectrices radiales (jeu 1.5 mm par cote), sinon
        # les plaques rectangulaires se chevauchent cote robot, la ou l'arc se resserre
        half = math.radians(dth / 2)
        for sgn in (-1, 1):
            n = np.array([sgn * math.cos(half), math.sin(half)])                  # normale sortante
            ang = math.degrees(math.atan2(n[1], n[0]))
            cutter = box(-1.5, 400, -400, 400, -50, zf + 50).rotate((0, 0, 0), (0, 0, 1), ang)   # 1.5 mm en deca
            f = f.cut(cutter)
        parts.append(Part(id=f"RACK_fourche_{i + 1}", name=f"Rack - fourche {i + 1}", group="RACK", body=0,
                          shape=rz(f), category="structure", print_up=(0, 0, 1),
                          notes="L'outil pend par sa gorge, face de couplage vers le haut."))
        low = box(xc - 15, xc + 15, oy - 15, oy + 15, 0, zsplit).cut(box(xc - 11, xc + 11, oy - 11, oy + 11, 3, zsplit + 1))
        low = fuse_all([low, box(xc - 40, xc + 40, oy - 45, oy + 15, 0, 6)])
        low = cut_all(low, [cyl(SCREW["M5"]["clear"], 8, -1, xc + sx * 30, oy - 30) for sx in (-1, 1)] +
                      [cyl(SCREW["M4"]["clear"], 40, -20).rotate((0, 0, 0), (0, 1, 0), 90)
                       .translate((xc, oy, zsplit - 10))])
        up = fuse_all([box(xc - 15, xc + 15, oy - 15, oy + 15, zsplit, zf + 10)
                       .cut(box(xc - 11, xc + 11, oy - 11, oy + 11, zsplit + 4, zf + 6)),   # plancher 4 mm :
                       # relie le tenon au fut (sinon tenon et fut ne se touchent que par une arete)
                       box(xc - 10.8, xc + 10.8, oy - 10.8, oy + 10.8, zsplit - 30, zsplit)
                       .cut(box(xc - 7, xc + 7, oy - 7, oy + 7, zsplit - 31, zsplit + 1))])
        up = cut_all(up, [cyl(SCREW["M4"]["clear"], 40, -20).rotate((0, 0, 0), (0, 1, 0), 90)
                          .translate((xc, oy, zsplit - 10))] +
                     [cyl(SCREW["M4"]["insert"], 9, 0).rotate((0, 0, 0), (1, 0, 0), -90)
                      .translate((xc + sx * 8, oy + 15 - 8.99, z - 6)) for sx in (-1, 1)])
        parts.append(Part(id=f"RACK_montant_{i + 1}", name=f"Rack - montant {i + 1} (bas)", group="RACK", body=0,
                          shape=rz(low), category="structure", print_up=(0, 0, 1),
                          notes="Visse sur l'etabli (2 x M5)."))
        parts.append(Part(id=f"RACK_mat_{i + 1}", name=f"Rack - montant {i + 1} (haut, emboite)", group="RACK",
                          body=0, shape=rz(up), category="structure", print_up=(0, 0, 1),
                          notes="Emboite de 30 mm dans le troncon bas + vis M4 traversante."))
        c, sn = math.cos(math.radians(th)), math.sin(math.radians(th))
        slots.append({"c": (c * xc - sn * yc, sn * xc + c * yc, zf), "yaw": th,
                      "sortie": (-sn, c, 0.0), "x": (c, sn, 0.0),
                      "fourche": {"slot_w": slot_w, "fork_L": fork_L, "pitch": pitch, "R": R}})
    return parts, slots
