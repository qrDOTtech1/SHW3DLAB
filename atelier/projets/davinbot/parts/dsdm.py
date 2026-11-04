"""Actionneur DSDM (Dual-Speed Dual-Motor) - axes 2 et 3.

Differentiel planetaire a deux entrees, entierement imprimable :
  M1 (muscle couple, +X)  -> pignon a moyeu long -> roue Z_i1 (chambre B)
                          -> arbre excentrique creux -> 2 disques cycloidaux
                          -> PORTE-COURONNE (couronne interieure tournante)
  M2 (muscle vitesse, -X) -> pignon -> roue Z_i2 (chambre A) -> TUBE SOLAIRE creux
                             (passe au centre de l'arbre excentrique)
  Sortie = PORTE-SATELLITES -> bride standard -> segment suivant.
  w_sortie = (Zs.w_solaire + Zr.w_couronne) / (Zs + Zr)

Verrou mecanique de M2 : cliquet a pivot tangentiel (effort passant par le pivot =
auto-bloquant) pilote par un MG90S loge dans le segment parent ; ses dents sont le
conjugue exact de la roue Z_i2. Indispensable : sans lui, en "mode force", le couple
de sortie serait limite au couple de maintien de M2 x son faible rapport.

Empilement axial (z local) :
  [0, t_r] paroi arriere (roulement A du tube solaire, 2 platines NEMA)
  [t_r, zA1] chambre A (etage M2 + cliquet)      |  piece : flasque arriere
  [zA1, zB0] cloison AB (roulement C de l'arbre excentrique)  | piece : cloison
  [zB0, zB1] chambre B (etage M1)                 |
  [zB1, zsh1] carter cycloidal (cloison, pions, disques, epaulement porte-couronne)
  [zsh1, z4] carter differentiel (roulement du porte-couronne, satellites)
  [z4, z5] couvercle avant (roulement de sortie) ; [z5, L] bride de sortie
"""
from __future__ import annotations

import math

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..cad.util import (SCREW, extrude_shapely, cyl, tube, box, hex_prism, union_all, cut_all,
                        fuse_all, bolt_circle, holes, circle2d, rect2d, outline_hull)
from ..config import BEARINGS
from ..gears.cycloid import disc_polygon
from ..gears.involute import external_gear, internal_gear_cutter
from .actuator import (_Common, ActuatorBuild, best_phase, LIP, T_DIAPH, T_SHOULDER, T_CARRIER,
                       _finish)
from .effector import MG

LOCK_LIFT_DEG = 30.0       # rotation du servo pour degager le cliquet


def _double_d(d: float, flat: float) -> Polygon:
    """Section double-D : cercle d avec deux meplats a +/- flat."""
    return circle2d(d).intersection(rect2d(0, 0, 2 * flat, d + 2))


def build_dsdm(jid: str, d, cfg: dict, body_in: int, body_out: int) -> ActuatorBuild:
    c = _Common(jid, d, cfg)
    c.body_out = body_out
    cy_d = d.cyc
    tol, press, fw = c.tol, c.press, c.fw
    wall = max(cfg["dsdm_wall"], c.wall)
    A = BEARINGS[d.brg_sun]
    C = BEARINGS[d.brg_ecc_shaft]
    E = BEARINGS[cy_d.brg_ecc]
    RG = BEARINGS[d.brg_ring]
    pre1, pre2 = d.pre, d.pre2
    a1, a2 = pre1.a, pre2.a
    c.motor_xs = [a1, -a2]
    c.motors = [{"x": a1, "tag": "M1"}, {"x": -a2, "tag": "M2"}]
    mb = c.m_body

    t_r = c.t_r
    zA1 = t_r + fw + 2.0
    zB0 = zA1 + C[2] + LIP
    zB1 = zB0 + fw + 2.0
    z2 = zB1 + T_DIAPH
    dt = cy_d.disc_t
    zd0 = z2 + 0.5
    zd1 = zd0 + dt + 0.6
    zd_end = zd1 + dt
    zsh0 = zd_end + 0.5
    zsh1 = zsh0 + T_SHOULDER
    zc0 = zsh1 + 0.5
    zp0 = zc0 + T_CARRIER + 0.5
    zp1 = zp0 + fw
    zrc_top = max(zp1 + 0.5, zp0 + RG[2])
    z4 = zrc_top + 0.5 + T_SHOULDER
    zs0_out = z4 - T_SHOULDER

    # ---------------------------------------------------------------- dentures d'entree
    def stage_polys(pre, ax):
        g_in = Polygon(external_gear(pre.zi, pre.m, tol, c.pa, flank_pts=12, arc_pts=5))
        g_m0 = Polygon(external_gear(pre.zm, pre.m, tol, c.pa, flank_pts=12, arc_pts=5))

        def mv(ph):
            return affinity.translate(affinity.rotate(g_m0, ph, origin=(0, 0), use_radians=True), ax, 0)
        ph = best_phase(g_in, mv, 2 * math.pi / pre.zm)
        return g_in, mv(ph)
    g_i1, g_m1 = stage_polys(pre1, a1)
    g_i2, g_m2 = stage_polys(pre2, -a2)
    r_i2 = pre2.m * pre2.zi / 2 + pre2.m
    r_i1 = pre1.m * pre1.zi / 2 + pre1.m

    # ---------------------------------------------------------------- cliquet de verrouillage
    lock = cfg.get("dsdm_lock", True)
    r_root2 = pre2.m * pre2.zi / 2 - 1.25 * pre2.m
    phi = math.radians(120.0)
    L_arm = 16.0
    r_t = r_i2 - 0.6
    Tp = (r_t * math.cos(phi), r_t * math.sin(phi))
    tang = (-math.sin(phi), math.cos(phi))
    Pp = (Tp[0] - L_arm * tang[0], Tp[1] - L_arm * tang[1])
    tip = affinity.rotate(rect2d(0, 0, 8.0, r_i2 + 1.5 - (r_root2 + 0.4)), math.degrees(phi) - 90,
                          origin=(0, 0))
    tip = affinity.translate(tip, ((r_i2 + 1.5 + r_root2 + 0.4) / 2) * math.cos(phi),
                             ((r_i2 + 1.5 + r_root2 + 0.4) / 2) * math.sin(phi))
    arm = outline_hull(circle2d(10.0, *Pp), circle2d(6.0, *Tp))
    lever2d = unary_union([arm, tip]).difference(g_i2.buffer(tol / 2))
    lever_open = affinity.rotate(lever2d, LOCK_LIFT_DEG, origin=Pp)
    servo_fp = rect2d(Pp[0], Pp[1] + MG["shaft_off"], MG["W"] + 1.0, MG["L"] + 1.0)

    # ---------------------------------------------------------------- contours & boulons
    heads = [circle2d(SCREW["M3"]["head"] + 1.2, ax + sx * 15.5, sy * 15.5)
             for ax in (a1, -a2) for sx in (-1, 1) for sy in (-1, 1)]
    chamberA = outline_hull(circle2d(2 * (r_i2 + 1.5)), circle2d(2 * (pre2.m * pre2.zm / 2 + pre2.m + 1.5), -a2, 0),
                            circle2d(16.0, a1, 0), *heads)
    if lock:
        chamberA = unary_union([chamberA, lever2d.buffer(1.0), lever_open.buffer(1.0),
                                circle2d(12.0, *Pp)]).convex_hull
    chamberB = outline_hull(circle2d(2 * (r_i1 + 1.5)), circle2d(2 * (pre1.m * pre1.zm / 2 + pre1.m + 1.5), a1, 0))
    cyc_R = cy_d.R
    Rb = max(cyc_R + cy_d.rp + 1.5 + SCREW["M4"]["clear"] / 2 + 0.3,
             RG[1] / 2 + 2.5 + SCREW["M4"]["clear"] / 2,
             c.O[1] / 2 + 2.5 + SCREW["M4"]["clear"] / 2,
             r_i1 + 1.5 + wall + SCREW["M4"]["clear"] / 2)
    OD = 2 * (Rb + SCREW["M4"]["clear"] / 2 + wall)
    sqs = [rect2d(a1, 0, mb, mb), rect2d(-a2, 0, mb, mb)]
    outline = outline_hull(circle2d(OD), *sqs, chamberA.buffer(wall))
    extra_forbid = [chamberA.buffer(1.0), chamberB.buffer(1.0)] + ([servo_fp.buffer(2)] if lock else [])
    mount = c.choose_mount_pts(Rb, chamberA.union(chamberB), extra=extra_forbid)

    # ---------------------------------------------------------------- flasque arriere (chambre A)
    body = extrude_shapely(outline, zA1)
    cut = [extrude_shapely(chamberA, zA1 - t_r + 1, t_r),
           cyl(A[1] + press, A[2] + 0.01, t_r - A[2]),
           cyl((A[0] + A[1]) / 2 + 1.0, t_r, -1)]
    for ax, hole in ((a1, 14.5), (-a2, 9.0)):
        cut += [cyl(22.0 + 2 * tol, 3.2, -1, ax, 0), cyl(hole, t_r + 2, -1, ax, 0)]
        for x, y in c.motor_pts(ax):
            cut += [cyl(SCREW["M3"]["clear"], t_r + 2, -1, x, y),
                    cyl(SCREW["M3"]["head"] + 0.4, 3.6, t_r - 3.5, x, y)]
    if lock:
        cut.append(cyl(10.0, t_r + 2, -1, *Pp))
    cut += holes(mount, SCREW["M4"]["clear"], -1, zA1 + 2)
    c.P("flasque_arriere", "flasque arriere DSDM (2 NEMA + chambre A)", -1, cut_all(body, cut),
        category="housing", print_up=(0, 0, -1),
        notes=f"Paroi mini {wall:g} mm. Vis M3 des 2 moteurs posees depuis la chambre A.")

    # ---------------------------------------------------------------- cloison AB + chambre B
    outline2 = outline_hull(circle2d(OD), chamberB.buffer(wall))
    body = extrude_shapely(outline2, zB1 - zA1, zA1)
    cut = [extrude_shapely(chamberB, zB1 - zB0 + 1, zB0),
           cyl(C[1] + press, C[2] + 0.01, zB0 - C[2]),
           cyl((C[0] + C[1]) / 2 + 1.0, zB0 - C[2] - zA1 + 1, zA1 - 1),
           cyl(14.5, zB0 - zA1 + 1, zA1 - 1, a1, 0),
           cyl(8.0, 4.0, zA1 - 0.01, -a2, 0)]
    cut += holes(mount, SCREW["M4"]["clear"], zA1 - 1, zB1 - zA1 + 2)
    c.P("cloison_AB", "cloison AB + chambre B (roulement C)", -1, cut_all(body, cut),
        category="housing", print_up=(0, 0, 1))

    # ---------------------------------------------------------------- pignons & roues d'entree
    # M2 : pignon standard
    dbore2 = circle2d(5.0 + tol, -a2, 0).difference(rect2d(-a2 + 2.25 + tol / 2 + 5, 0, 10, 10))
    c.P("pignon_M2", f"pignon M2 Z{pre2.zm}", -1, extrude_shapely(g_m2.difference(dbore2), fw, t_r + 0.2),
        category="gear", anim={"type": "spin", "center": [-a2, 0], "k": [0.0, 1.0]})
    # M1 : pignon a moyeu long (traverse la chambre A et la cloison)
    dbore1 = circle2d(5.0 + tol, a1, 0).difference(rect2d(a1 + 2.25 + tol / 2 + 5, 0, 10, 10))
    hub1 = extrude_shapely(circle2d(13.0, a1, 0).difference(dbore1), zB0 + 0.2 - 2.4, 2.4)
    teeth1 = extrude_shapely(g_m1, fw, zB0 + 0.2)
    pin1 = fuse_all([hub1, teeth1])
    c.P("pignon_M1", f"pignon M1 Z{pre1.zm} a moyeu long", -1, pin1, category="gear",
        print_up=(0, 0, 1), anim={"type": "spin", "center": [a1, 0], "k": [1.0, 0.0]},
        notes="Moyeu 13 mm sur l'arbre 5 mm (D), dents en bout apres la cloison AB.")
    k_ecc = -1.0 / pre1.ratio
    k_sun = -1.0 / pre2.ratio
    hexp = Polygon([(A[0] + tol) / math.sqrt(3) * np.array([math.cos(k * math.pi / 3),
                                                             math.sin(k * math.pi / 3)])
                    for k in range(6)])
    c.P("roue_M2", f"roue solaire d'entree Z{pre2.zi}", -1,
        extrude_shapely(g_i2.difference(hexp), fw, t_r + 0.2), category="gear",
        anim={"type": "spin", "center": [0, 0], "k": [0.0, k_sun]},
        notes="Ses dents servent aussi de denture de verrouillage (cliquet).")
    flat = C[0] / 2 - 1.5
    dd = _double_d(C[0] + tol, flat + tol / 2)
    c.P("roue_M1", f"roue excentrique d'entree Z{pre1.zi}", -1,
        extrude_shapely(g_i1.difference(dd), fw, zB0 + 0.2), category="gear",
        anim={"type": "spin", "center": [0, 0], "k": [k_ecc, 0.0]})

    # ---------------------------------------------------------------- tube solaire (M2)
    diff = d
    zs_teeth0, zs_teeth1 = zp0 - 0.5, zp1 + 0.3
    sun2d = Polygon(external_gear(diff.zs, diff.m, tol, c.pa, flank_pts=12, arc_pts=5))
    tube_s = fuse_all([
        cyl(A[0] - press * 0.5, A[2], t_r - A[2]),
        hex_prism(A[0], fw + 0.5, t_r),
        cyl(A[0] - 0.2, zs_teeth0 - (t_r + fw + 0.5), t_r + fw + 0.5),
        extrude_shapely(sun2d, zs_teeth1 - zs_teeth0, zs_teeth0),
        cyl(A[0] - press * 0.5, zs0_out + A[2] - zs_teeth1, zs_teeth1),
    ]).cut(cyl(c.bore + tol, 500, -100))
    c.P("tube_solaire", f"tube solaire creux Z{diff.zs} (entree M2)", -1, tube_s, category="shaft",
        print_up=(0, 0, 1), anim={"type": "spin", "center": [0, 0], "k": [0.0, k_sun]},
        notes=f"Canal cables {c.bore} mm sur toute la longueur.")

    # ---------------------------------------------------------------- arbre excentrique (M1)
    ecc_id = A[0] + 1.0
    mid_d = E[0] - 2 * cy_d.e - 0.5
    ecc = fuse_all([
        cyl(C[0] - press * 0.5, C[2], zB0 - C[2]),
        extrude_shapely(dd.buffer(-tol / 2 - 0.01), fw + 0.4, zB0),
        cyl(E[0] - 0.5, zd0 - (zB0 + fw + 0.4), zB0 + fw + 0.4),
        cyl(E[0] - press * 0.5, dt, zd0, cy_d.e, 0),
        cyl(mid_d, 0.6, zd0 + dt),
        cyl(E[0] - press * 0.5, dt, zd1, -cy_d.e, 0),
        cyl(C[0] - press * 0.5, zsh0 + C[2] - zd_end, zd_end),
    ]).cut(cyl(ecc_id, 500, -100))
    c.P("arbre_excentrique", "arbre excentrique creux (entree M1)", -1, ecc, category="shaft",
        print_up=(0, 0, 1), anim={"type": "spin", "center": [0, 0], "k": [k_ecc, 0.0]},
        notes=f"Tourne autour du tube solaire (jeu diametral {ecc_id - A[0]:.1f} mm).")
    for nm, zz, x in (("E1", zd0, cy_d.e), ("E2", zd1, -cy_d.e)):
        c.bearing_vit(cy_d.brg_ecc, nm, zz, x, 0, body=-1)
    c.bearing_vit(d.brg_ecc_shaft, "C", zB0 - C[2], body=-1)
    c.bearing_vit(d.brg_ecc_shaft, "D", zsh0, body=-1)

    # ---------------------------------------------------------------- carter cycloidal
    diaph_hole = 2 * (E[0] / 2 + cy_d.e) + 1.5
    pin_pts = bolt_circle(cy_d.N, cyc_R, 0)
    body = cyl(OD, zsh1 - zB1, zB1)
    r_bore = max(cyc_R, cyc_R - cy_d.rp + 2 * cy_d.e + 0.6)   # lobes excentres > R si 2e > rp
    cut = [cyl(2 * r_bore, zsh1 - z2 + 1, z2), cyl(diaph_hole, T_DIAPH + 2, zB1 - 1)]
    cut += holes(pin_pts, 2 * cy_d.rp - 0.05, z2 - 3.5, zsh1 - z2 + 4.5)
    cut += holes(mount, SCREW["M4"]["clear"], zB1 - 1, zsh1 - zB1 + 2)
    c.P("carter_cyclo", f"carter cycloidal M1 ({cy_d.N} pions)", -1, cut_all(body, cut),
        category="housing", print_up=(0, 0, 1))
    pin_len = (zsh1 + 3.5) - (z2 - 3.5)
    c.P("piges_couronne", f"piges couronne d{2 * cy_d.rp:g} x{cy_d.N}", -1,
        union_all([cyl(2 * cy_d.rp, pin_len, z2 - 3.5, x, y) for x, y in pin_pts]),
        kind="vitamin", category="pin")
    c.vit.append((f"Pige cylindrique acier d{2 * cy_d.rp:g} x {math.ceil(pin_len)} mm", cy_d.N))

    k_ring = -k_ecc / cy_d.lobes
    base = disc_polygon(cyc_R, cy_d.rp, cy_d.N, cy_d.e, tol)
    hole_pts = bolt_circle(cy_d.out_pins, cy_d.Rh, 0)
    disc2d = base.difference(unary_union([circle2d(E[1] + press)] +
                                         [circle2d(cy_d.hole_d, x, y) for x, y in hole_pts]))
    for k, (zz, sign, rot0) in enumerate(((zd0, 1, 0.0), (zd1, -1, math.pi / cy_d.lobes))):
        g = affinity.translate(affinity.rotate(disc2d, rot0, origin=(0, 0), use_radians=True), sign * cy_d.e, 0)
        c.P(f"disque_{k + 1}", f"disque cycloidal {k + 1} ({cy_d.lobes} lobes)", -1,
            extrude_shapely(g, dt, zz), category="disc", print_up=(0, 0, 1),
            anim={"type": "cycloid", "e": cy_d.e, "sign": sign, "ecc": [k_ecc, 0.0],
                  "rot": [k_ring, 0.0], "rot0": rot0})
    opl = (zsh0 + 6.0) - (z2 + 0.8)
    c.P("pions_sortie", f"pions de sortie cycloidal d{cy_d.out_pin_d:g} x{cy_d.out_pins}", -1,
        union_all([cyl(cy_d.out_pin_d, opl, z2 + 0.8, x, y) for x, y in hole_pts]),
        kind="vitamin", category="pin", anim={"type": "spin", "center": [0, 0], "k": [k_ring, 0.0]})
    c.vit.append((f"Pige cylindrique acier d{cy_d.out_pin_d:g} x {math.ceil(opl)} mm", cy_d.out_pins))

    # ---------------------------------------------------------------- differentiel
    m = diff.m
    pl0 = Polygon(external_gear(diff.zp, m, tol, c.pa, flank_pts=12, arc_pts=5))
    ac = diff.carrier_r
    planet_polys, planet_phases = [], []
    for k in range(diff.n):
        psi = 2 * math.pi * k / diff.n
        cx, cy = ac * math.cos(psi), ac * math.sin(psi)

        def mv(ph, cx=cx, cy=cy):
            return affinity.translate(affinity.rotate(pl0, ph, origin=(0, 0), use_radians=True), cx, cy)
        ph = best_phase(sun2d, mv, 2 * math.pi / diff.zp)
        planet_polys.append(mv(ph))
        planet_phases.append(ph)
    rr = m * (diff.zr / 2 + 1.25)
    r_tip_ring = m * (diff.zr / 2 - 1.0)
    ring_cut0 = Polygon(internal_gear_cutter(diff.zr, m, tol, c.pa, flank_pts=12, arc_pts=5))
    ring_solid0 = circle2d(2 * rr + 6).difference(ring_cut0)
    ring_ph = best_phase(planet_polys[0], lambda ph: affinity.rotate(ring_solid0, ph, origin=(0, 0),
                                                                     use_radians=True),
                         2 * math.pi / diff.zr)
    ring_cut = affinity.rotate(ring_cut0, ring_ph, origin=(0, 0), use_radians=True)

    # porte-couronne : epaulement (pions de sortie cycloidal + roulement D) + couronne tournante
    sh_d = RG[0] + 4.0
    rc = fuse_all([cyl(sh_d, zp0 - zsh0, zsh0), cyl(RG[0] - press * 0.5, zrc_top - zp0, zp0)])
    rcut = [extrude_shapely(ring_cut, zrc_top - zsh1 + 1, zsh1),
            cyl(C[1] + press, C[2] + 0.01, zsh0 - 0.01),
            cyl((C[0] + C[1]) / 2 + 1.0, zsh1 - zsh0 + 2, zsh0 - 1)]
    rcut += holes(hole_pts, cy_d.out_pin_d - 0.05, zsh0 - 0.01, 6.0)
    c.P("porte_couronne", f"porte-couronne tournant Z{diff.zr} (sortie M1)", -1, cut_all(rc, rcut),
        category="output", print_up=(0, 0, 1),
        anim={"type": "spin", "center": [0, 0], "k": [k_ring, 0.0]},
        notes=f"Tourne dans un roulement {d.brg_ring} (section fine).")
    c.bearing_vit(d.brg_ring, "R", zp0, body=-1)

    # carter differentiel
    body = cyl(OD, z4 - zsh1, zsh1)
    cut = [cyl(sh_d + 1.0, zp0 - zsh1 + 0.01, zsh1 - 0.01),
           cyl(RG[1] + press, RG[2] + 0.01, zp0),
           cyl((RG[0] + RG[1]) / 2 + 1.0, z4 - zp0 + 1, zp0)]
    cut += holes(pin_pts, 2 * cy_d.rp + 0.05, zsh1 - 0.01, 3.5)
    cut += holes(mount, SCREW["M4"]["clear"], zsh1 - 1, z4 - zsh1 + 2)
    c.P("carter_diff", f"carter differentiel (roulement {d.brg_ring})", -1, cut_all(body, cut),
        category="housing", print_up=(0, 0, 1), notes=f"Paroi {wall:g} mm (bloc DSDM).")

    # satellites
    kc = [diff.zr * k_ring / (diff.zs + diff.zr), diff.zs * k_sun / (diff.zs + diff.zr)]
    ks = [0.0, k_sun]
    kp = [kc[i] - (ks[i] - kc[i]) * diff.zs / diff.zp for i in range(2)]
    if diff.planet_brg == "bague":
        pb_d, pin_d, nb = 3.0 + tol, 3.0, 0
    else:
        PB = BEARINGS[diff.planet_brg]
        pb_d, pin_d, nb = PB[1] + press, PB[0], max(1, int(fw // PB[2]))
    for k, poly in enumerate(planet_polys):
        psi = 2 * math.pi * k / diff.n
        cx, cy = ac * math.cos(psi), ac * math.sin(psi)
        c.P(f"satellite_{k + 1}", f"satellite differentiel {k + 1} Z{diff.zp}", body_out,
            extrude_shapely(poly.difference(circle2d(pb_d, cx, cy)), fw, zp0), category="gear",
            print_up=(0, 0, 1),
            anim={"type": "planet", "psi0": psi, "ac": ac, "carrier": kc, "spin": kp,
                  "phase0": planet_phases[k]})
        for j in range(nb):
            c.bearing_vit(diff.planet_brg, f"P{k + 1}", zp0 + j * BEARINGS[diff.planet_brg][2], cx, cy, body=body_out)
    c.vit.append((f"Axe acier d{pin_d:g} x {math.ceil(zs0_out + 5 - zc0)} mm (satellites DSDM)", diff.n))

    plate_d = 2 * (r_tip_ring - 1.2)
    sun_tip = m * (diff.zs + 2)
    ppts = bolt_circle(diff.n, ac, 0)
    so_pts = bolt_circle(diff.n, ac, 180 / diff.n) if diff.standoffs else []
    rear = tube(plate_d, sun_tip + 1.5, T_CARRIER, zc0)
    rcut = holes(ppts, pin_d - 0.05, zc0 - 1, T_CARRIER + 2)
    for x, y in so_pts:
        rcut += [cyl(SCREW["M3"]["clear"], T_CARRIER + 2, zc0 - 1, x, y),
                 cyl(SCREW["M3"]["head"] + 0.4, 2.2, zc0 - 0.01, x, y)]
    c.P("porte_sat_arriere", "porte-satellites (flasque arriere)", body_out, cut_all(rear, rcut),
        category="output", print_up=(0, 0, 1), anim={"type": "spin", "center": [0, 0], "k": kc})
    extra = [cyl(7.0, zs0_out - (zc0 + T_CARRIER), zc0 + T_CARRIER, x, y) for x, y in so_pts]
    scut = holes(ppts, pin_d - 0.05, zs0_out - 0.01, 5.0)
    scut += holes(so_pts, SCREW["M3"]["insert"], zc0 + T_CARRIER - 0.01, 6.0)

    z5 = c.front_cap(z4, Rb, OD, mount)
    L, out_pts, out_d = c.output(z4, z5, OD, plate_d, scut, k_out=tuple(kc), shoulder_extra=extra)

    # ---------------------------------------------------------------- moteurs, verrou
    kos = [c.motor_and_keepout(a1, "M1"), c.motor_and_keepout(-a2, "M2")]
    lock_info = None
    if lock:
        wl = max(cfg["dsdm_wall"], cfg["wall"])
        z_spl = -wl - 1.0                     # sommet de cannelure sous la paroi du segment
        lever = extrude_shapely(lever2d, fw, t_r + 0.2)
        z_hub0 = z_spl - MG["spline_h"] + 0.4          # au-dessus du dome du servo
        hubL = cyl(9.0, t_r + 0.2 - z_hub0, z_hub0, *Pp)
        lever = fuse_all([lever, hubL]).cut(cyl(MG["spline_d"] - 0.2, MG["spline_h"], z_hub0 - 0.01, *Pp))
        c.P("cliquet_M2", "cliquet de verrouillage M2 (conjugue de la roue)", -1, lever,
            category="output", print_up=(0, 0, 1),
            anim={"type": "lock_lever", "center": list(Pp), "deg": LOCK_LIFT_DEG},
            notes=f"Servo 0 deg = M2 verrouille ; {LOCK_LIFT_DEG:g} deg = libre. Pivot tangentiel : "
                  "l'effort des dents passe par le pivot (auto-bloquant).")
        z_top = z_spl - MG["spline_h"]
        zb = z_top - MG["dome_h"] - MG["H"]
        sv = fuse_all([
            extrude_shapely(rect2d(Pp[0], Pp[1] + MG["shaft_off"], MG["W"], MG["L"]), MG["H"], zb),
            extrude_shapely(rect2d(Pp[0], Pp[1] + MG["shaft_off"], MG["W"], MG["tab_L"]), MG["tab_t"],
                            zb + MG["tab_z"]),
            cyl(MG["dome_d"], MG["dome_h"], zb + MG["H"], *Pp),
            cyl(MG["spline_d"] - 0.2, MG["spline_h"], z_top, *Pp)])
        c.P("servo_verrou", "servo MG90S (verrou M2)", -1, sv, kind="vitamin", category="motor")
        lock_info = {"pivot": list(Pp), "z_spline": z_spl, "tab_z": zb + MG["tab_z"] + MG["tab_t"],
                     "screw_pts": [(Pp[0], Pp[1] + MG["shaft_off"] + s * MG["screw_sp"] / 2) for s in (-1, 1)],
                     "footprint": servo_fp}

    b = _finish(c, "dsdm", d, L, OD, outline, mount, out_pts, out_d, kos[0],
                dict(z1=zA1, zB0=zB0, zB1=zB1, z2=z2, zsh0=zsh0, z4=z4, z5=z5, L=L), body_in)
    b.motors = c.motors
    b.keepouts = kos
    b.lock_servo = lock_info
    b.a = a1
    b.info.update({"rapport_M1_couple": d.i1, "rapport_M2_vitesse": d.i2,
                   "k_couronne": d.k_ring, "differentiel": f"Zs{diff.zs}/Zp{diff.zp}/Zr{diff.zr}",
                   "verrou_M2": bool(lock), "paroi_mm": wall})
    return b
