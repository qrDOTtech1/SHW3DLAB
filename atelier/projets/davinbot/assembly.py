"""Assemblage complet du DaVinBot V2 (pose zero : bras vertical).

Corps cinematiques : 0 socle | 1 tourelle | 2 bras | 3 bloc coude | 4 avant-bras |
5 poignet | 6 tete outil. Chaque articulation k relie le corps k-1 au corps k.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from .cad.util import (SCREW, box, cyl, tube, apply_T, fuse_all, cut_all, frame_z_to, T as Tm,
                       rot_matrix, bbox, union_all)
from .gears.solver import design_all
from .parts.actuator import build_cycloid, build_planetary
from .parts.dsdm import build_dsdm
from .parts.base import build_socle, build_sensor_box, build_rack
from .parts.effector import build_head
from .parts.links import LinkSpec, Mount, build_link, auto_split, mks_window
from .parts.model import Part
from .parts.tools import build_tools


@dataclass
class Assembly:
    cfg: dict
    designs: dict
    acts: dict = field(default_factory=dict)
    frames: dict = field(default_factory=dict)
    parts: list = field(default_factory=list)
    joints: list = field(default_factory=list)
    cable_path: list = field(default_factory=list)
    info: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    tools_meta: list = field(default_factory=list)
    head_geom: object = None


def _clone_act(act, jid, body_in, body_out, src_in, src_out):
    new = copy.copy(act)
    new.jid = jid
    parts = []
    for p in act.parts:
        q = copy.copy(p)
        q.id = jid + p.id[len(act.jid):]
        q.name = jid + p.name[len(act.jid):]
        q.group = jid
        q.body = body_in if p.body == src_in else body_out
        parts.append(q)
    new.parts = parts
    return new


def _world_pts(T, pts2d, z=0.0):
    return [(T @ np.array([x, y, z, 1.0]))[:3] for x, y in pts2d]


def _outline_world_bbox(T, act, z_local=0.0):
    pts = list(act.rear_outline.exterior.coords)
    w = np.array(_world_pts(T, pts, z_local))
    return w.min(axis=0), w.max(axis=0)


def _circle_world_bbox(T, d, z_local):
    pts = [(d / 2 * math.cos(a), d / 2 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 33)]
    w = np.array(_world_pts(T, pts, z_local))
    return w.min(axis=0), w.max(axis=0)


def _shape_bbox_world(shape, T):
    return bbox(apply_T(shape, T))


def build_assembly(cfg: dict, progress=lambda msg, f=None: None) -> Assembly:
    D = design_all(cfg)
    asm = Assembly(cfg=cfg, designs=D)
    tol = cfg["tol"]
    ml = cfg["motor_len"]
    bore = cfg["cable_bore"]
    w_std = max(4.0, cfg["wall"])
    w_ds = max(cfg["dsdm_wall"], w_std)

    # ------------------------------------------------------------ actionneurs
    def build(j, bi, bo):
        d = D[j]
        if d.kind == "dsdm":
            return build_dsdm(j, d, cfg, bi, bo)
        if d.kind == "cycloidal":
            return build_cycloid(j, d, cfg, bi, bo)
        return build_planetary(j, d, cfg, bi, bo)

    cache = {}
    for j, (bi, bo) in zip(["J1", "J2", "J3", "J4", "J5", "J6"],
                           [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]):
        key = id(D[j])
        if key in cache:
            src_j, src_bi, src_bo = cache[key]
            asm.acts[j] = _clone_act(asm.acts[src_j], j, bi, bo, src_bi, src_bo)
            progress(f"Actionneur {j} : reutilise la geometrie de {src_j}")
        else:
            progress(f"Generation actionneur {j} ({D[j].kind})...")
            asm.acts[j] = build(j, bi, bo)
            cache[key] = (j, bi, bo)
    A = asm.acts
    wall_of = {"J1": 6.0, "J2": w_ds if D["J2"].kind == "dsdm" else w_std,
               "J3": w_ds if D["J3"].kind == "dsdm" else w_std}

    def t_link(w):
        return ml + 0.5 + 2 * w

    def motor_reach(act):
        """extensions locales (x+ , x-) : contour arriere, moteurs ET zones MKS (d = mks_d)."""
        xs = [p[0] for p in act.rear_outline.exterior.coords]
        for mt in act.motors:
            xs += [mt["x"] + cfg["mks_d"] / 2, mt["x"] - cfg["mks_d"] / 2]
        return max(xs), -min(xs)

    # ------------------------------------------------------------ socle + J1
    wlb = 6.0
    zb = ml + cfg["mks_len"] + 10.0 + wlb
    T1 = frame_z_to((0, 0, 1), (-1, 0, 0), (0, 0, zb))
    asm.frames["J1"] = T1
    z_o1 = zb + A["J1"].L
    progress("Socle et plateau...")
    sp, sinfo = build_socle(cfg, zb, wlb, T1, A["J1"])
    asm.parts += sp

    # ------------------------------------------------------------ tourelle + J2
    w2 = wall_of["J2"]
    T2 = t_link(w2)
    a2_dn, a2_up = motor_reach(A["J2"])
    y_t1 = T2 / 2
    shoulder_h = max(cfg["shoulder_h"], a2_dn + w2 + 2)
    if shoulder_h > cfg["shoulder_h"]:
        asm.warnings.append(f"Hauteur d'epaule portee a {shoulder_h:.0f} mm (moteur J2 sous l'axe).")
    z2 = z_o1 + shoulder_h
    TJ2 = frame_z_to((0, 1, 0), (0, 0, -1), (0, y_t1, z2))
    asm.frames["J2"] = TJ2
    y_o2 = y_t1 + A["J2"].L
    lo, hi = _outline_world_bbox(TJ2, A["J2"])
    x_c = cfg["motor_body"] / 2 + bore / 2 + 3.0
    W2 = max(cfg["link_w"], A["J1"].out_d + 4, hi[0] - lo[0] + 2, 2 * (x_c + bore / 2 + w2 + 1))
    tur = LinkSpec("TOURELLE", "Tourelle (epaule)", 1, -W2 / 2, W2 / 2, y_t1 - T2, y_t1,
                   z_o1, max(hi[2], z2 + A["J2"].OD / 2) + 2, w2,
                   notes=f"Paroi {w2:g} mm autour du bloc {'DSDM' if D['J2'].kind == 'dsdm' else 'J2'}.")
    tur.mounts = [Mount(T1, A["J1"], "flange"), Mount(TJ2, A["J2"], "rear")]

    # ------------------------------------------------------------ bras + J3
    w3 = max(wall_of["J2"], wall_of["J3"])
    T3 = t_link(w3)
    a3_dn, a3_up = motor_reach(A["J3"])
    min_upper = A["J2"].out_d / 2 + a3_dn + w3 + 12
    upper = max(cfg["upper_len"], min_upper)
    if upper > cfg["upper_len"]:
        asm.warnings.append(f"Longueur de bras portee a {upper:.0f} mm (encombrement).")
    z3 = z2 + upper
    TJ3 = frame_z_to((0, -1, 0), (0, 0, -1), (0, y_o2, z3))
    asm.frames["J3"] = TJ3
    y_o3 = y_o2 - A["J3"].L
    lo3, hi3 = _outline_world_bbox(TJ3, A["J3"])
    W3 = max(cfg["link_w"], A["J2"].out_d + 4, hi3[0] - lo3[0] + 2, 2 * (x_c + bore / 2 + w3 + 1))
    arm_z0 = z2 - A["J2"].out_d / 2 - w3 - 2
    arm_z1 = max(hi3[2], z3 + A["J3"].OD / 2) + 2
    arm = LinkSpec("BRAS", "Bras superieur", 2, -W3 / 2, W3 / 2, y_o2, y_o2 + T3, arm_z0, arm_z1, w3)
    arm.mounts = [Mount(TJ2, A["J2"], "flange"), Mount(TJ3, A["J3"], "rear")]
    if cfg.get("tube_segments"):
        arm.tube_zone = (z2 + A["J2"].out_d / 2 + w3 + 3, z3 - a3_dn - w3 - 3)
        arm.cable_haut = (-x_c, y_o2 + T3 - (w3 + cfg["tube_d"] / 2 + 1) - 3.35)

    # ------------------------------------------------------------ bloc coude + J4
    wb = wall_of["J3"]
    a4, _ = motor_reach(A["J4"])
    Tb = max(cfg["motor_body"] + 2 * wb + 6, 2 * (bore / 2 + wb + 4), cfg["mks_d"] + 2 * (wb + 1))
    y_c3 = y_o3 - Tb / 2
    eb_z0 = z3 - A["J3"].out_d / 2 - wb - 2
    z4r = max(z3 + A["J3"].out_d / 2 + wb + 2, eb_z0 + ml + 0.5 + 2 * wb)
    TJ4 = frame_z_to((0, 0, 1), (-1, 0, 0), (0, y_c3, z4r))
    asm.frames["J4"] = TJ4
    lo4, hi4 = _outline_world_bbox(TJ4, A["J4"])
    eb = LinkSpec("COUDE", "Bloc coude (roulis avant-bras)", 3,
                  min(lo4[0], -A["J3"].out_d / 2) - 2, max(hi4[0], A["J3"].out_d / 2) + 2,
                  min(lo4[1], y_o3 - Tb) - 1, y_o3, eb_z0, z4r, wb)
    eb.y0 = min(eb.y0, y_o3 - Tb)
    eb.mounts = [Mount(TJ3, A["J3"], "flange"), Mount(TJ4, A["J4"], "rear")]
    z4o = z4r + A["J4"].L

    # ------------------------------------------------------------ avant-bras + J5
    w4 = w_std
    T4 = t_link(w4)
    a5_dn, a5_up = motor_reach(A["J5"])
    min_fore = (z4o - z3) + w4 + a5_dn + 10
    fore = max(cfg["fore_len"], min_fore)
    if fore > cfg["fore_len"]:
        asm.warnings.append(f"Longueur d'avant-bras portee a {fore:.0f} mm (encombrement).")
    z5 = z3 + fore
    y_f1 = y_c3 + T4 / 2
    TJ5 = frame_z_to((0, 1, 0), (0, 0, -1), (0, y_f1, z5))
    asm.frames["J5"] = TJ5
    lo5, hi5 = _outline_world_bbox(TJ5, A["J5"])
    W4 = max(cfg["link_w"], A["J4"].out_d + 4, hi5[0] - lo5[0] + 2, 2 * (x_c + bore / 2 + w4 + 1))
    fa = LinkSpec("AVANT_BRAS", "Avant-bras", 4, -W4 / 2, W4 / 2, y_c3 - T4 / 2, y_f1, z4o,
                  max(hi5[2], z5 + A["J5"].OD / 2) + 2, w4)
    fa.mounts = [Mount(TJ4, A["J4"], "flange"), Mount(TJ5, A["J5"], "rear")]
    if cfg.get("tube_segments"):
        fa.tube_zone = (z4o + w4 + 3, z5 - a5_dn - w4 - 3)
    y_o5 = y_f1 + A["J5"].L

    # ------------------------------------------------------------ poignet + J6
    ww = w_std
    Tw = max(cfg["motor_body"] + 2 * ww + 6, 2 * (bore / 2 + ww + 4), cfg["mks_d"] + 2 * (ww + 1))
    y_c5 = y_o5 + Tw / 2
    wr_z0 = z5 - A["J5"].out_d / 2 - ww - 2
    z6r = max(z5 + A["J5"].out_d / 2 + ww + 2, wr_z0 + ml + 0.5 + 2 * ww)
    TJ6 = frame_z_to((0, 0, 1), (-1, 0, 0), (0, y_c5, z6r))
    asm.frames["J6"] = TJ6
    lo6, hi6 = _outline_world_bbox(TJ6, A["J6"])
    wr = LinkSpec("POIGNET", "Poignet (tangage)", 5, min(lo6[0], -A["J5"].out_d / 2) - 2,
                  max(hi6[0], A["J5"].out_d / 2) + 2, y_o5, max(hi6[1], y_o5 + Tw) + 1, wr_z0, z6r, ww)
    wr.mounts = [Mount(TJ5, A["J5"], "flange"), Mount(TJ6, A["J6"], "rear")]
    z6o = z6r + A["J6"].L
    wrist_eff = z6o - z5
    if abs(wrist_eff - cfg["wrist_len"]) > 1:
        asm.warnings.append(f"Poignet effectif (axe 5 -> bride outil) : {wrist_eff:.0f} mm "
                            f"(demande {cfg['wrist_len']:.0f} mm, impose par l'encombrement).")

    # ------------------------------------------------------------ fenetres MKS & zones interdites
    links = [tur, arm, eb, fa, wr]
    frames = {"J1": T1, "J2": TJ2, "J3": TJ3, "J4": TJ4, "J5": TJ5, "J6": TJ6}
    parent = {"J2": tur, "J3": arm, "J4": eb, "J5": fa, "J6": wr}
    # le segment parent doit contenir moteurs, servo et zones MKS (hors axe moteur) + paroi.
    # Les faces portant une interface (flasque / bride) ne bougent jamais.
    names = (("x0", "x1"), ("y0", "y1"), ("z0", "z1"))
    for L in links:
        L.locked = set()
        for m in L.mounts:
            ax = m.T[:3, 2]
            k = int(np.argmax(np.abs(ax)))
            pt = m.T[:3, 3] + (ax * m.act.L if m.kind == "flange" else 0)
            lo_, hi_ = getattr(L, names[k][0]), getattr(L, names[k][1])
            L.locked.add(names[k][0] if abs(pt[k] - lo_) < abs(pt[k] - hi_) else names[k][1])
    for j, L in parent.items():
        act, T = A[j], frames[j]
        k_ax = int(np.argmax(np.abs(T[:3, 2])))
        for p in act.parts:
            if p.body != L.body or p.kind not in ("vitamin", "keepout"):
                continue
            if not any(t in p.id for t in ("nema17", "zone_mks", "mks", "servo")):
                continue
            bb = bbox(apply_T(p.shape, T))
            mg = L.wall + 1.0
            for k, (a0, a1) in enumerate((("x0", "x1"), ("y0", "y1"), ("z0", "z1"))):
                if k == k_ax:
                    continue
                for attr, val, fn in ((a0, bb[k] - mg, min), (a1, bb[k + 3] + mg, max)):
                    cur = getattr(L, attr)
                    new = fn(cur, val)
                    if new == cur:
                        continue
                    if attr in L.locked:
                        asm.warnings.append(f"{L.label} : {p.name} deborde la face d'interface "
                                            f"{attr} de {abs(new - cur):.1f} mm")
                        continue
                    setattr(L, attr, new)
    for j, L in parent.items():
        act, T = A[j], frames[j]
        # epaisseur du segment le long de l'axe moteur -> paroi opposee
        axis = T[:3, 2]
        for mt in act.motors:
            # position de la paroi opposee en z local
            p0 = T[:3, 3]
            k = int(np.argmax(np.abs(axis)))
            lim = [(L.x0, L.x1), (L.y0, L.y1), (L.z0, L.z1)][k]
            far = lim[0] if axis[k] > 0 else lim[1]
            z_far = (far - p0[k]) / axis[k]            # < 0
            z_wall_in = z_far + L.wall
            ko_top = -ml                                # sommet de la zone MKS (local)
            if z_wall_in > -ml - cfg["mks_len"]:
                # la zone MKS traverse la paroi opposee -> fenetre
                win = cyl(cfg["mks_d"] + 1.0, L.wall + 2, z_far - 1, mt["x"], 0)
                L.extra_cut.append(apply_T(win, T))
        # zones a eviter pour les bossages du capot
        for p in act.parts:
            if p.body == L.body and (p.kind in ("vitamin", "keepout")):
                L.avoid.append(bbox(apply_T(p.shape, T)))
        # entretoises du servo de verrou (DSDM)
        if act.lock_servo:
            ls = act.lock_servo
            posts, pc = [], []
            for x, y in ls["screw_pts"]:
                h = -L.wall - ls["tab_z"]
                posts.append(cyl(6.5, h + 0.5, ls["tab_z"], x, y))
                pc.append(cyl(1.8, h, ls["tab_z"] - 0.01, x, y))
            from .cad.util import extrude_shapely as _ex
            body_fp = _ex(ls["footprint"].buffer(0.3), -L.wall - ls["tab_z"] + 2, ls["tab_z"] - 1)
            posts = [cut_all(s, [body_fp]) for s in posts]
            L.extra_add += [apply_T(s, T) for s in posts]
            L.extra_cut += [apply_T(s, T) for s in pc]
            L.extra_cut.append(apply_T(cyl(10.0, L.wall + 2, -L.wall - 1, *ls["pivot"]), T))
    # socle : bossages evites (non applicable), bloc coude / poignet : fenetres dessous gerees ci-dessus

    # ------------------------------------------------------------ decoupe en modules imprimables
    bed_diag = math.hypot(cfg["bed_x"], cfg["bed_y"]) - 2 * cfg["bed_margin"]
    for L in links:
        depth = L.y1 - L.y0
        max_len = min(bed_diag - depth - 16, cfg["bed_z"] - 2 * cfg["bed_margin"] + 60)
        max_len = bed_diag / 1.0 - depth * 1.0 - 12
        length = L.z1 - L.z0
        if length > max_len:
            # zone libre : entre les interfaces
            free = _free_zone(L, A, frames, parent, cfg)
            L.split_zs = auto_split(L.z0, L.z1, free, max_len)
            if L.split_zs:
                asm.warnings.append(f"{L.label} ({length:.0f} mm) decoupe en {len(L.split_zs) + 1} "
                                    f"modules boulonnes (plateau {cfg['bed_x']:.0f}x{cfg['bed_y']:.0f}).")

    # ------------------------------------------------------------ compensation de gravite J2
    asm.spring = None
    if cfg.get("j2_spring", True):
        from .spring_talon import layout as spring_layout
        asm.spring, sparts = spring_layout(cfg, tur, arm, TJ2, z2)
        asm.parts += sparts
        # goupille haute du ressort : sous les moteurs de J3 (zone MKS), a travers le bras
        z_pin = frames["J3"][2, 3] - 75.0
        asm.spring["z_pin"] = z_pin
        asm.spring["arm_spec"] = arm
        # goupille d8 + bossages d20 le long de la goupille (matage ~7 MPa au lieu de 29 dans 4 mm de paroi)
        xs_, ypl_ = asm.spring["x_s"], asm.spring["y_pl"]
        boss_l = (ypl_ - 6.0) - arm.y0
        arm.extra_add += [cyl(20.0, boss_l, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((xs_, arm.y0, z_pin)),
                          cyl(20.0, boss_l, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((xs_, ypl_ + 6.0, z_pin))]
        arm.extra_cut.append(cyl(8.0 + cfg["tol"], arm.y1 - arm.y0 + 10, 0).rotate((0, 0, 0), (1, 0, 0), -90)
                             .translate((xs_, arm.y0 - 5, z_pin)))
        asm.spring.update(pin_d=8.0, boss_l=round(boss_l - arm.wall, 1))

    # ------------------------------------------------------------ pieces des actionneurs
    for j in ["J1", "J2", "J3", "J4", "J5", "J6"]:
        for p in A[j].parts:
            p.T = frames[j]
            asm.parts.append(p)
    for L in links:
        progress(f"Segment {L.label}...")
        asm.parts += build_link(L, cfg)

    # ------------------------------------------------------------ tete + outils
    progress("Tete de changement d'outil active...")
    hparts, g = build_head(cfg, A["J6"], 6)
    for p in hparts:
        p.T = TJ6
    asm.parts += hparts
    asm.head_geom = g
    tool_origin = TJ6 @ Tm(None, (0, 0, A["J6"].L + g.z_face))
    progress("Capteurs RFP602, rack, outils...")
    sb, sinfo2 = build_sensor_box(cfg, sinfo["lug_x"])
    asm.parts += sb
    if sinfo2["spacing_clamped"]:
        asm.warnings.append(f"Entraxe RFP602 limite a {sinfo2['spacing']:.0f} mm (volume d'impression).")
    rack_origin = (0.0, -(cfg["rack_r"] + 60))
    rparts, slots = build_rack(cfg, g, None, 5)
    asm.parts += rparts
    place = {"P": (tool_origin, 6),
             "P_spares": (Tm(None, (rack_origin[0] - 420, rack_origin[1] + 40, 0)), 0)}
    # outils suspendus face en haut : repere outil retourne (rotation 180 deg autour de X),
    # la gorge [3, 6] mm (repere outil) encadre la fourche (dessus a zf)
    flip = rot_matrix((1, 0, 0), 180.0)
    asm.rack_slots = {}
    for tl, sl in zip(("P", "A", "B", "C", "H"), slots):
        xc, yc, zf = sl["c"]
        asm.rack_slots[tl] = {"face": [xc, yc, zf + 5.8 - 2.6 + 0.2], "sortie": list(sl["sortie"]),
                              "x": list(sl["x"]), "yaw_deg": sl["yaw"], "course_sortie": 110.0,
                              "fourche": sl["fourche"]}
        if tl != "P":
            place[tl] = (Tm(rot_matrix((0, 0, 1), sl["yaw"]) @ flip, (xc, yc, zf + 5.8 - 2.6 + 0.2)), 0)
    tparts, tmeta = build_tools(cfg, g, place)
    asm.parts += tparts
    asm.tools_meta = tmeta

    # ------------------------------------------------------------ support camera
    progress("Support camera endoscopique...")
    asm.parts += _camera_mount(cfg, wr, TJ6, A["J6"], g, y_c5)

    # ------------------------------------------------------------ articulations
    lim = {"J1": 170, "J2": 110, "J3": 140, "J4": 180, "J5": 115, "J6": 270}
    for j, body in zip(["J1", "J2", "J3", "J4", "J5", "J6"], range(1, 7)):
        T = frames[j]
        d = D[j]
        asm.joints.append({
            "name": j, "body": body, "origin": T[:3, 3].round(3).tolist(),
            "axis": T[:3, 2].round(6).tolist(), "limit": lim[j], "kind": d.kind,
            "ratio": d.ratio if d.kind != "dsdm" else d.i1,
            "ratio_m2": d.i2 if d.kind == "dsdm" else None,
            "T": T.round(5).tolist()})

    # ------------------------------------------------------------ chemin de cables (pose zero)
    xc = x_c
    asm.cable_path = [
        (0, sinfo["lug_x"] * 0 + cfg["base_d"] / 2 - 4.0 - 20, 26.0), (0, 0, 26.0), (0, 0, zb - 1),
        (0, 0, z_o1 + w2 + 10), (xc, 0, z_o1 + w2 + 10), (xc, 0, z2), (0, 0, z2),
        (0, y_t1 - 12, z2), (0, y_o2 + 12, z2), (0, y_o2 + T3 / 2, z2 + 8),
        (-xc, y_o2 + T3 / 2, z2 + 20), (-xc, y_o2 + T3 / 2, z3), (0, y_o2 + T3 / 2, z3),
        (0, y_o2 + 12, z3), (0, y_c3, z3), (0, y_c3, z4o + w4 + 10),
        (-xc, y_c3, z4o + w4 + 20), (-xc, y_c3, z5), (0, y_c3, z5), (0, y_f1 - 12, z5),
        (0, y_o5 + 12, z5), (0, y_c5, z5),
        (0, y_c5, z6o + g.lug_bot - cfg["pogo_depth"] - 2.4 - 7.0)]   # entree des fentes du porte-pogo
    if cfg.get("tube_segments") and arm.tube_zone:      # les cables passent dans le triangle de tubes
        yh = y_o2 + T3 - (w3 + cfg["tube_d"] / 2 + 1)
        ycab = yh - (cfg["tube_d"] + 8) / 2 - cfg["cable_bore"] / 2 - 0.5
        i = asm.cable_path.index((-xc, y_o2 + T3 / 2, z2 + 20))
        asm.cable_path[i - 1:i + 3] = [(0, ycab, z2 + 8), (0, ycab, arm.tube_zone[1] - cfg["tube_prise"] - 10), (*arm.cable_haut, arm.tube_zone[1] - cfg["tube_prise"] - 8),
                                        (*arm.cable_haut, z3), (-xc, y_o2 + T3 / 2, z3), (0, y_o2 + T3 / 2, z3)]   # sort du triangle a cote du moteur J3
    asm.cable_path = [tuple(float(v) for v in p) for p in asm.cable_path]

    asm.info = {
        "z_base_plateau": zb, "hauteur_epaule": z2, "z_coude": z3, "z_poignet": z5,
        "z_bride_outil": z6o, "portee_verticale_mm": round(z6o + g.z_face, 1),
        "longueur_bras_mm": round(upper, 1), "longueur_avant_bras_mm": round(fore, 1),
        "poignet_effectif_mm": round(wrist_eff, 1),
        "portee_horizontale_mm": round(upper + fore + wrist_eff + g.z_face, 1),
        "capteurs": {k: v for k, v in sinfo2.items() if k != "pts"},
        "offsets_y_mm": {"tourelle": round(y_t1, 1), "bras": round(y_o2, 1), "coude": round(y_c3, 1),
                         "poignet": round(y_c5, 1)},
    }
    return asm


def _free_zone(L: LinkSpec, A, frames, parent, cfg):
    """Zone en z du segment sans interface (entre bride basse et moteurs du haut)."""
    lo, hi = L.z0, L.z1
    zs_lo, zs_hi = [], []
    for m in L.mounts:
        act = m.act
        T = m.T
        if m.kind == "flange":
            b = _circle_world_bbox(T, act.out_d + 4, act.L)
        else:
            b = _outline_world_bbox(T, act)
            for p in act.parts:
                if p.kind in ("vitamin", "keepout") and p.body == L.body:
                    bb = bbox(apply_T(p.shape, T))
                    b = (np.minimum(b[0], bb[:3]), np.maximum(b[1], bb[3:]))
        mid = (b[0][2] + b[1][2]) / 2
        if mid < (lo + hi) / 2:
            zs_lo.append(b[1][2])
        else:
            zs_hi.append(b[0][2])
    fa = max(zs_lo) if zs_lo else lo
    fb = min(zs_hi) if zs_hi else hi
    return (fa, fb)


def _camera_mount(cfg, wr: LinkSpec, TJ6, act6, g, y_c5) -> list[Part]:
    """Support de camera endoscopique fixe sur la face +Y du poignet."""
    tol = cfg["tol"]
    cd = cfg["cam_d"]
    yw = wr.y1
    z6o = TJ6[2, 3] + act6.L
    z_face = z6o + g.z_face
    R_h = g.D / 2
    plate_z0, plate_z1 = wr.z0 + 6, wr.z1 - 4
    plate = box(-22, 22, yw, yw + 6, plate_z0, plate_z1)
    pcut = []
    bolt_pts = [(sx * 14, plate_z0 + 10) for sx in (-1, 1)] + [(sx * 14, plate_z1 - 10) for sx in (-1, 1)]
    for x, z in bolt_pts:
        pcut.append(cyl(SCREW["M3"]["clear"], 30, -15).rotate((0, 0, 0), (1, 0, 0), 90).translate((x, yw + 3, z)))
    pcut.append(cyl(10.0, 30, -15).rotate((0, 0, 0), (1, 0, 0), 90).translate((0, yw + 3, plate_z0 + 25)))
    parts = []
    if cfg["variant"] == "artiste":
        y_cam = max(y_c5 + R_h + cd / 2 + 6.0, yw + cd / 2 + 10.0)
        zc0, zc1 = z_face - 26, z_face - 4           # camera entierement en retrait de la face (+z = vers l outil) : libre au rack
        x_air = cd / 2 + cfg["air_d"] / 2 + 4.0          # tubes camera / air FUSIONNES (1.5 mm de recouvrement)
        holder = fuse_all([tube(cd + 6, cd + 2 * tol, zc1 - zc0, zc0, 0, y_cam),
                           tube(cfg["air_d"] + 5, cfg["air_d"] + 2 * tol, zc1 - zc0, zc0, x_air, y_cam)])
        # bras vertical : recouvre la platine ET la nervure du porte-camera (jamais un simple contact de face)
        za, zb = min(zc0, plate_z1 - 12), max(zc0 + 6, plate_z1 - 4)
        armb = box(-5, 5, yw, y_cam - cd / 2 - 1, za, zb)
        rib = box(-5, 5, yw + 6, y_cam, zc0, zc0 + 6)
        post = box(-5, 5, yw, yw + 10, za, zb)
        bracket = cut_all(fuse_all([plate, armb, rib, post, holder]),
                          pcut + [cyl(cd + 2 * tol, 100, zc0 - 50, 0, y_cam),
                                  cyl(cfg["air_d"] + 2 * tol, 100, zc0 - 50, x_air, y_cam)])
        parts.append(Part(id="CAM_support_artiste", name="Poignet - support camera axiale + canal air (bras artiste)",
                          group="CAMERA", body=5, shape=bracket, category="sensor", print_up=(0, 1, 0),
                          notes=f"Camera d{cd:g} parallele a l'axe outil (suivi macro) ; canal d{cfg['air_d']:g} "
                                "pour le tuyau de la micro-pompe 12 V."))
        parts.append(Part(id="CAM_camera", name="Camera endoscopique USB (macro)", group="CAMERA", body=5,
                          shape=cyl(cd, 30, zc0 - 8, 0, y_cam), kind="vitamin", category="electronics"))
    else:
        ang = cfg["cam_angle"]
        tip = np.array([0.0, y_c5, z_face + 60.0])
        dist = 72.0
        dirv = np.array([0.0, -math.sin(math.radians(ang)), math.cos(math.radians(ang))])
        pos = tip - dist * dirv
        L = 22.0

        def along(shape):
            return shape.rotate((0, 0, 0), (1, 0, 0), ang).translate(tuple(pos))
        led_dx = cd / 2 + cfg["led_d"] / 2 + 3.0
        holder = along(fuse_all([tube(cd + 6, cd + 2 * tol, L, -L / 2),
                                 tube(cfg["led_d"] + 5, cfg["led_d"] + 2 * tol, L, -L / 2, led_dx, 0)]))
        armb = box(-6, 6, yw, pos[1] + 2, plate_z1 - 12, pos[2] - 4)
        post = box(-6, 6, yw, yw + 12, plate_z1 - 12, pos[2] - 4)
        bracket = fuse_all([plate, armb, post, holder])
        bracket = cut_all(bracket, pcut + [along(cyl(cd + 2 * tol, 60, -30)),
                                           along(cyl(cfg["led_d"] + 2 * tol, 60, -30, led_dx, 0))])
        parts.append(Part(id="CAM_support_assistant", name=f"Poignet - support camera rasante {ang:g} deg + flash LED",
                          group="CAMERA", body=5, shape=bracket, category="sensor",
                          notes=f"Vise la pointe de l'outil ({dist:.0f} mm) : calibration rasante."))
        parts.append(Part(id="CAM_camera", name="Camera endoscopique USB (rasante)", group="CAMERA", body=5,
                          shape=along(cyl(cd, 30, -20)), kind="vitamin", category="electronics"))
    return parts
