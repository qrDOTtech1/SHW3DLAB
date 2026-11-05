"""Controles automatiques : volume d'impression, collisions, zones MKS, canal de cables,
bilan de couple (statique) et documentation de commande DSDM."""
from __future__ import annotations

import math

import cadquery as cq
import numpy as np

from .cad.util import apply_T, to_shape, cyl, fuse_all, union_all, bbox

G = 9.81
VIT_MASS = {"motor": None, "electronics": 1.6, "bearing": 7.85 * 0.55, "pin": 7.85, "screw": 7.85}
NEMA_KG = 0.40
MG90S_KG = 0.0134


# ------------------------------------------------------------------ orientation d'impression
AXES = [(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]


def _rot_to_z(u):
    u = np.asarray(u, float)
    u = u / np.linalg.norm(u)
    z = np.array([0, 0, 1.0])
    if np.allclose(u, z):
        return np.eye(3)
    if np.allclose(u, -z):
        return np.diag([1.0, -1.0, -1.0])
    v = np.cross(u, z)
    s = np.linalg.norm(v)
    c = np.dot(u, z)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / s ** 2)


def _bottom_area(shape: cq.Shape) -> float:
    bb = shape.BoundingBox()
    area = 0.0
    for f in shape.Faces():
        if f.geomType() != "PLANE":
            continue
        n = f.normalAt()
        if n.z < -0.999 and abs(f.Center().z - bb.zmin) < 0.05:
            area += f.Area()
    return area


def support_area(shape, angle_deg: float = 45.0) -> float:
    """Surface (cm2) des facettes en surplomb au-dela de `angle_deg` (hors appui plateau)."""
    try:
        verts, tris = shape.tessellate(0.4, 0.5)
    except Exception:
        return 0.0
    V = np.array([(v.x, v.y, v.z) for v in verts])
    T = np.array(tris)
    if len(T) == 0:
        return 0.0
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    n = np.cross(b - a, c - a)
    area = np.linalg.norm(n, axis=1) / 2
    nz = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    zc = (a[:, 2] + b[:, 2] + c[:, 2]) / 3
    zmin = V[:, 2].min()
    over = (nz < -math.cos(math.radians(90 - angle_deg))) & (zc > zmin + 0.3)
    return float(area[over].sum() / 100.0)


def print_orientation(part, cfg) -> dict:
    """Choisit l'orientation d'impression (face plane maxi au plateau) et verifie le volume."""
    shape = to_shape(part.shape)
    bx = cfg["bed_x"] - 2 * cfg["bed_margin"]
    by = cfg["bed_y"] - 2 * cfg["bed_margin"]
    bz = cfg["bed_z"]
    cands = [part.print_up] if part.print_up else []
    cands += [a for a in AXES if a not in cands]
    best = None
    for idx, up in enumerate(cands):
        R = _rot_to_z(up)
        M = np.eye(4)
        M[:3, :3] = R
        s = apply_T(shape, M)
        b = s.BoundingBox()
        dz = b.zlen
        fit_rot = None
        for zr in (0, 90, 45, 30, 60, 15, 75):
            Rz = np.eye(4)
            a = math.radians(zr)
            Rz[:2, :2] = [[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]]
            s2 = apply_T(s, Rz) if zr else s
            b2 = s2.BoundingBox()
            if b2.xlen <= bx and b2.ylen <= by and dz <= bz:
                fit_rot = (zr, s2, b2)
                break
        if fit_rot:
            sup = support_area(fit_rot[1])
            bot = _bottom_area(fit_rot[1]) / 100.0
            cost = sup - 0.3 * bot
            if part.print_up and idx == 0:
                cost -= 1.0                              # leger bonus a l'orientation du concepteur
            if best is None or cost < best[2]:
                best = (up, fit_rot, cost, sup)
    if best is None:
        s = apply_T(shape, np.eye(4))
        b = s.BoundingBox()
        return {"fits": False, "shape": s, "dims": [round(b.xlen, 1), round(b.ylen, 1), round(b.zlen, 1)],
                "up": None, "rot_z": 0, "support_cm2": None}
    up, (zr, s2, b2), _, sup = best
    s3 = s2.translate(cq.Vector(cfg["bed_x"] / 2 - b2.center.x, cfg["bed_y"] / 2 - b2.center.y, -b2.zmin))
    return {"fits": True, "shape": s3, "dims": [round(b2.xlen, 1), round(b2.ylen, 1), round(b2.zlen, 1)],
            "up": list(up), "rot_z": zr, "support_cm2": round(sup, 1)}


# ------------------------------------------------------------------ masses
def part_mass(p, cfg, vol_cm3: float) -> float:
    """Masse en kg."""
    if p.kind == "keepout":
        return 0.0
    if p.kind == "print":
        return vol_cm3 * cfg["pla_density"] / 1000.0
    if p.kind == "metal":
        m_ = (p.material or "").lower()
        dens = 2.7 if "alu" in m_ else 8.5 if "laiton" in m_ else 4.4 if "titane" in m_ else 7.9
        return vol_cm3 * dens / 1000.0
    if p.category == "motor":
        if "MG90S" in p.name:
            return MG90S_KG
        if "micro" in p.name.lower():
            return 0.015                    # micro pas-a-pas d15 (main)
        return NEMA_KG
    dens = VIT_MASS.get(p.category, 1.2) or 1.2
    return vol_cm3 * dens / 1000.0


# ------------------------------------------------------------------ interferences
def _bb_overlap(a, b, pad=-0.05):
    return not (a[3] + pad < b[0] or b[3] + pad < a[0] or a[4] + pad < b[1] or
                b[4] + pad < a[1] or a[5] + pad < b[2] or b[5] + pad < a[2])


def inter_volume(s1: cq.Shape, s2: cq.Shape) -> float:
    try:
        r = s1.intersect(s2)
        return abs(r.Volume())
    except Exception:
        return -1.0


def cable_sweep(path, d: float) -> cq.Shape:
    solids = []
    for p0, p1 in zip(path[:-1], path[1:]):
        v = np.array(p1) - np.array(p0)
        L = float(np.linalg.norm(v))
        if L < 1e-6:
            continue
        solids.append(cq.Solid.makeCylinder(d / 2, L, cq.Vector(*p0), cq.Vector(*(v / L))))
        solids.append(cq.Solid.makeSphere(d / 2, cq.Vector(*p1), angleDegrees1=-90, angleDegrees2=90))
    s = solids[0]
    for o in solids[1:]:
        s = s.fuse(o)
    return s.clean()


def run_checks(asm, world: dict, progress, full_interference=True) -> dict:
    cfg = asm.cfg
    out = {"keepout": [], "cable": {}, "collisions": [], "motor_collisions": []}
    printed = [p for p in asm.parts if p.kind in ("print", "metal")]     # pieces fabriquees
    solids = [p for p in asm.parts if p.kind in ("print", "vitamin", "metal")]
    # --- zones MKS : rien ne doit y penetrer
    progress("Controle des zones reservees MKS SERVO42C...")
    for k in [p for p in asm.parts if p.kind == "keepout"]:
        ks, kb = world[k.id]
        hits = []
        grp_tag = k.id.replace("zone_mks", "")
        for p in solids:
            if p.group == k.group and ("mks" in p.id or "nema17" in p.id):
                continue
            ps, pb = world[p.id]
            if not _bb_overlap(kb, pb):
                continue
            v = inter_volume(ks, ps)
            if v > 1.0:
                hits.append({"part": p.name, "mm3": round(v, 1)})
        out["keepout"].append({"zone": k.name, "ok": not hits, "hits": hits})
    # --- canal de cables
    progress("Controle du canal de cables (diametre 12 mm, axe 6 -> socle)...")
    sweep = cable_sweep(asm.cable_path, 12.0)
    sb = bbox(sweep)
    hits = []
    for p in solids:
        ps, pb = world[p.id]
        if not _bb_overlap(sb, pb):
            continue
        v = inter_volume(sweep, ps)
        if v > 2.0:
            hits.append({"part": p.name, "mm3": round(v, 1)})
    L = sum(float(np.linalg.norm(np.array(b) - np.array(a))) for a, b in zip(asm.cable_path[:-1], asm.cable_path[1:]))
    out["cable"] = {"ok": not hits, "hits": hits, "longueur_mm": round(L, 0), "diametre_teste_mm": 12.0,
                    "path": asm.cable_path}
    # --- moteurs / servos vs pieces imprimees
    progress("Controle moteurs / structure...")
    motors = [p for p in asm.parts if p.kind == "vitamin" and p.category == "motor"]
    for mt in motors:
        ms, mb = world[mt.id]
        for p in printed:
            ps, pb = world[p.id]
            if not _bb_overlap(mb, pb):
                continue
            v = inter_volume(ms, ps)
            if v > 3.0:
                out["motor_collisions"].append({"a": mt.name, "b": p.name, "mm3": round(v, 1)})
    # --- interferences entre pieces imprimees
    if full_interference:
        pairs = []
        for i, a in enumerate(printed):
            for b in printed[i + 1:]:
                if _bb_overlap(world[a.id][1], world[b.id][1]):
                    pairs.append((a, b))
        progress(f"Interferences entre pieces imprimees ({len(pairs)} paires candidates)...")
        for n, (a, b) in enumerate(pairs):
            v = inter_volume(world[a.id][0], world[b.id][0])
            if v > 2.0:
                out["collisions"].append({"a": a.name, "b": b.name, "mm3": round(v, 1)})
            if n % 60 == 0:
                progress(f"  interferences {n}/{len(pairs)}", n / max(1, len(pairs)))
        out["pairs_tested"] = len(pairs)
    return out


# ------------------------------------------------------------------ bilan de couple
def _reco(T_req, T_av, ratio, what) -> str:
    need = ratio * T_req * 1.2 / max(T_av, 1e-6)
    return (f"Couple insuffisant ({T_av:.1f} < {T_req:.1f} N.m x1.2). Options : rapport {what} "
            f"~{need:.0f}:1, compensation de gravite (ressort), charge ou portee reduite, "
            f"NEMA 17 plus coupleux (17HS24 / 17HS8401).")
def torque_analysis(asm, masses: dict, coms: dict) -> dict:
    cfg = asm.cfg
    tm = cfg["motor_torque"] * cfg["motor_torque_derate"]
    rpm = cfg["motor_rpm"]
    eta = {"cycloidal": 0.95 * 0.80, "planetary": 0.95 * 0.88}
    # point de charge : bout d'outil A (sur l'axe J6)
    j6 = asm.joints[5]
    tipz = asm.info["z_bride_outil"] + asm.head_geom.z_face + 80.0
    tip = np.array([j6["origin"][0], j6["origin"][1], tipz])
    payload = cfg["payload"]
    res = {}
    for jd in asm.joints:
        j = jd["name"]
        body = jd["body"]
        a = np.array(jd["axis"], float)
        o = np.array(jd["origin"], float)
        M = np.zeros(3)
        m_tot = 0.0
        for p in asm.parts:
            if p.body >= body and p.body <= 6 and masses.get(p.id, 0) > 0:
                r = coms[p.id] - o
                rp = r - np.dot(r, a) * a
                M += masses[p.id] * rp
                m_tot += masses[p.id]
        rp_tip = (tip - o) - np.dot(tip - o, a) * a
        # couple gravitaire maxi sur la plage de rotation (bras aval tendu)
        # pire cas : tout axe en aval de l'epaule peut devenir horizontal (bras tendu) ;
        # seul J1 (base fixe, axe toujours vertical) echappe a la gravite
        gravity_axis = jd["body"] > 1 or abs(np.dot(a, [0, 0, 1])) < 0.5
        T_arm = G * np.linalg.norm(M) / 1000.0 if gravity_axis else 0.0
        T_pay = G * payload * np.linalg.norm(rp_tip) / 1000.0 if gravity_axis else 0.0
        T_req = T_arm + T_pay
        d = asm.designs[j]
        entry = {"masse_aval_kg": round(m_tot + payload, 3), "couple_bras_Nm": round(T_arm, 2),
                 "couple_charge_Nm": round(T_pay, 2), "couple_requis_Nm": round(T_req, 2),
                 "axe_gravitaire": gravity_axis}
        if d.kind == "dsdm":
            e1 = 0.95 * 0.80 * 0.90
            e2 = 0.95 * 0.90
            T1 = tm * d.i1 * e1
            T2 = tm * d.i2 * e2
            lock = cfg.get("dsdm_lock", True)
            T_force = T1 if lock else min(T1, T2)
            entry.update({
                "type": "DSDM",
                "rapport_M1": d.i1, "rapport_M2": d.i2,
                "mode_force_Nm": round(T_force if lock else min(T1, T2), 2),
                "mode_force_limite_par": "M1 (cycloidal)" if lock else "M2 (maintien electronique)",
                "mode_vitesse_Nm": round(min(T2, T1), 2),
                "mode_hybride_Nm": round(min(T1, T2), 2),
                "vitesse_force_deg_s": round(rpm / d.i1 * 6, 1),
                "vitesse_vitesse_deg_s": round(rpm / d.i2 * 6, 1),
                "vitesse_hybride_deg_s": round(rpm / d.i1 * 6 + rpm / d.i2 * 6, 1),
                "gain_vitesse_x": round(d.i1 / d.i2, 1),
                "marge_mode_force": round((T_force if lock else min(T1, T2)) / T_req, 2) if T_req > 0 else None,
            })
            if T_req > 0:
                ratio = min(1.0, T2 / T_req)
                entry["mode_vitesse_angle_max_deg"] = round(math.degrees(math.asin(ratio)), 1)
                entry["mode_vitesse_valide_partout"] = T2 >= T_req
            entry["ok"] = bool((entry["marge_mode_force"] or 99) >= 1.2)
            if not entry["ok"]:
                entry["recommandation"] = _reco(T_req, T_force if lock else min(T1, T2), d.i1, "M1")
        else:
            act = asm.acts[j]
            tmj = cfg["motor_torque_leger"] * cfg["motor_torque_derate"] if j in ("J1", "J4", "J5") and cfg.get("motor_torque_leger") else tm
            T_av = tmj * d.ratio * eta[d.kind] * len(act.motors)
            if act.kind == "servo":
                T_av = 0.9                              # MG996R : couple continu prudent
            entry.update({"type": d.kind, "rapport": d.ratio, "couple_dispo_Nm": round(T_av, 2),
                          "vitesse_max_deg_s": round(rpm / d.ratio * 6, 1),
                          "marge": round(T_av / T_req, 2) if T_req > 0 else None})
            entry["ok"] = bool(entry["marge"] is None or entry["marge"] >= 1.2)
            if not entry["ok"]:
                entry["recommandation"] = _reco(T_req, T_av, d.ratio, "reducteur")
        res[j] = entry
    return res


def payload_capacity(asm, cfg, tools) -> dict:
    """Charge utile maxi a bout de bras (pire cas horizontal, marge 1.2 sur chaque axe),
    avec l'outil P (monte au calcul) et avec la DaVinHand a la place."""
    tq = getattr(asm, "torque", None)
    if not tq:
        return {}
    pl = cfg["payload"]
    res, lim = {}, None
    for j, t in tq.items():
        if not t.get("axe_gravitaire") or t.get("couple_charge_Nm", 0) <= 0:
            continue
        per_kg = t["couple_charge_Nm"] / pl
        avail = t.get("mode_force_Nm", t.get("couple_dispo_Nm"))
        arm_part = t["couple_requis_Nm"] - t["couple_charge_Nm"]
        mx = (avail / 1.2 - arm_part) / per_kg
        res[j] = round(mx, 2)
        lim = mx if lim is None else min(lim, mx)
    hand_extra = tools.get("H", 0) - tools.get("P", 0)
    return {"par_axe_kg": res, "avec_outil_P_kg": round(lim, 2),
            "avec_DaVinHand_kg": round(lim - hand_extra, 2), "masse_DaVinHand_kg": tools.get("H")}


def coupling_capacity(asm, masses, cfg) -> dict:
    """Capacite du changeur d'outil (verrou baionnette + cones) face a l'outil le plus lourd
    tenu a bout de bras, bras horizontal (moment maximal a l'interface)."""
    g = asm.head_geom
    lugs = 3
    # ergot : cisaillement a la racine (PETG ~ 25 MPa) + pige acier d3 (cisaillement ~ 300 MPa)
    arc = math.radians(g.lug_w_deg) * g.r_sp
    A_lug = arc * g.lug_h
    F_petg = A_lug * 25.0
    F_pin = math.pi * 1.5 ** 2 * 300.0
    F_lug = F_petg + F_pin                           # N par ergot (rupture)
    sf = 3.0
    F_axial = lugs * F_lug / sf
    # moment : un ergot tire, appui sur les cones opposes (bras de levier ~ rayon des cones)
    M_bend = (F_lug / sf) * (g.r_cone + g.lug_r) / 1000.0
    tools = {}
    for t in asm.tools_meta:
        tid = t["id"]
        ms = [(masses[p.id], p) for p in asm.parts if p.group == f"OUTIL_{tid}" and p.kind != "keepout"]
        m = sum(x for x, _ in ms)
        tools[tid] = round(m, 3)
    payload = cfg["payload"]
    worst_tool = max(tools, key=tools.get)
    m_tot = tools[worst_tool] + payload
    lever = 0.12                                     # centre de gravite outil + charge (m)
    M_req = m_tot * G * lever
    F_req = m_tot * G * 3.0                          # choc / acceleration 3 g
    return {"ergots": lugs, "effort_rupture_par_ergot_N": round(F_lug), "coef_securite": sf,
            "effort_axial_admissible_N": round(F_axial), "moment_admissible_Nm": round(M_bend, 2),
            "masses_outils_kg": tools, "outil_le_plus_lourd": worst_tool,
            "charge_testee_kg": round(m_tot, 2), "moment_requis_Nm": round(M_req, 2),
            "effort_requis_3g_N": round(F_req),
            "marge_moment": round(M_bend / M_req, 2), "marge_effort": round(F_axial / F_req, 2),
            "charge_utile_max": payload_capacity(asm, cfg, tools),
            "ok": bool(M_bend >= M_req and F_axial >= F_req)}


def firmware_doc(asm, torque: dict) -> str:
    """Documentation de la logique de commande DSDM (ESP32 + MKS SERVO42C)."""
    lines = ["# Logique de commande DSDM - DaVinBot V2", ""]
    ds = [j for j in ("J2", "J3") if asm.designs[j].kind == "dsdm"]
    if not ds:
        return "# DSDM desactive\n"
    d = asm.designs[ds[0]]
    lines += [
        "## Cinematique du differentiel",
        "",
        f"Differentiel planetaire : solaire Zs={d.zs}, satellites Zp={d.zp}, couronne Zr={d.zr} (module {d.m}).",
        "",
        "```",
        "w_sortie = (Zs * w_solaire + Zr * w_couronne) / (Zs + Zr)",
        f"w_couronne = w_M1 / i_c        avec i_c = {d.cyc.ratio:.3f}  (etage {d.pre.zi}/{d.pre.zm} x cycloidal {d.cyc.lobes}:1)",
        f"w_solaire  = -w_M2 / i_s       avec i_s = {d.pre2.ratio:.3f}  (etage {d.pre2.zi}/{d.pre2.zm})",
        f"=> w_sortie = w_M1 / {d.i1:.3f}  +  w_M2 / {d.i2:.3f}   (signes selon cablage)",
        "```",
        "",
        "## Rapports virtuels",
        "",
        "| Mode | M1 (couple) | M2 (vitesse) | Verrou M2 | Rapport | Couple sortie | Vitesse sortie |",
        "|---|---|---|---|---|---|---|",
    ]
    for j in ds:
        t = torque[j]
        lines += [
            f"| {j} Force | tourne | bloque | ENGAGE | {d.i1:.1f}:1 | {t['mode_force_Nm']} N.m | {t['vitesse_force_deg_s']} deg/s |",
            f"| {j} Vitesse | maintien | tourne | libre | {d.i2:.2f}:1 | {t['mode_vitesse_Nm']} N.m | {t['vitesse_vitesse_deg_s']} deg/s |",
            f"| {j} Hybride | tourne | tourne | libre | somme | {t['mode_hybride_Nm']} N.m | {t['vitesse_hybride_deg_s']} deg/s |",
        ]
    lines += [
        "",
        "## Point physique critique (verifie par le generateur)",
        "",
        "Dans un differentiel, le couple de sortie est TOUJOURS partage : il faut que les deux",
        "entrees le contiennent. Couple de sortie maxi = min(T_M1 x i1, T_M2 x i2) tant que M2",
        "n'est tenu qu'electroniquement. D'ou le **cliquet mecanique** sur la roue solaire :",
        "verrou engage, l'effort passe par le pivot et le mode Force delivre le couple du cycloidal.",
        "",
    ]
    for j in ds:
        t = torque[j]
        if "mode_vitesse_angle_max_deg" in t:
            lines.append(f"- {j} : mode Vitesse autorise tant que le couple gravitaire < {t['mode_vitesse_Nm']} N.m, "
                         f"soit un bras incline de moins de **{t['mode_vitesse_angle_max_deg']} deg** par rapport a la "
                         f"verticale en charge maxi (couple requis horizontal : {t['couple_requis_Nm']} N.m).")
    lines += [
        "",
        "## Sequence ESP32 (pseudo-code)",
        "",
        "```cpp",
        "enum Gear { FORCE, VITESSE, HYBRIDE };",
        "",
        "void setGear(Axis &ax, Gear g) {",
        "  if (g == FORCE) {",
        "    ax.m2.holdStrict();            // MKS SERVO42C : maintien, courant max",
        "    ax.lockServo.write(LOCK_ON);   // MG90S cliquet : 0 deg -> engage",
        "    waitMs(120);                   // temps de basculement du cliquet",
        "    ax.m2.release();               // l'effort passe dans le cliquet",
        "  } else {",
        "    float tg = gravityTorque(ax);  // modele statique (masses du generateur)",
        f"    if (g != HYBRIDE && tg > ax.T_m2_max) g = HYBRIDE; // M2 seul trop faible",
        "    ax.m2.holdStrict();",
        f"    ax.lockServo.write(LOCK_OFF);  // {30:d} deg -> cliquet degage",
        "    waitMs(120);",
        "  }",
        "  ax.gear = g;",
        "}",
        "",
        "// consigne de vitesse articulaire w (deg/s) -> vitesses moteurs",
        "void drive(Axis &ax, float w) {",
        "  switch (ax.gear) {",
        f"    case FORCE:   ax.m1.speed(w * {d.i1:.3f}); ax.m2.speed(0); break;",
        f"    case VITESSE: ax.m1.hold();              ax.m2.speed(w * {d.i2:.3f}); break;",
        "    case HYBRIDE: {",
        "      // repartition : M1 fournit la part lente (couple), M2 le complement rapide",
        f"      float w1 = constrain(w, -W1_MAX, W1_MAX);   // W1_MAX = rpm_max*6/{d.i1:.3f}",
        "      float w2 = w - w1;",
        f"      ax.m1.speed(w1 * {d.i1:.3f}); ax.m2.speed(w2 * {d.i2:.3f}); break;",
        "    }",
        "  }",
        "}",
        "```",
        "",
        "Transitions : ne changer de rapport qu'a vitesse articulaire nulle ; en mode Force, verifier",
        "l'engagement du cliquet par la derive de position de M2 (encodeur du MKS) < 1 pas.",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ balayage des articulations
def joint_sweep_check(asm, view_dir, step_deg=3.0, depth_mm=0.4, progress=lambda m, f=None: None) -> dict:
    """Chaque articulation parcourt TOUTE sa plage (les autres a 0) : toute piece en aval est testee
    contre toute piece en amont (maillages reels, profondeur de penetration). Seuls les contacts
    ABSENTS a 0 deg sont signales (ceux de la pose zero sont deja couverts par les interferences),
    avec la plage d'angles ou ils se produisent. Le decor (rack, outils du rack, capteurs) est exclu :
    c'est l'espace de travail, pas la conception du bras."""
    import trimesh
    from trimesh.collision import CollisionManager
    env = ("RACK", "CAPTEURS")
    parts = [p for p in asm.parts if p.kind in ("print", "vitamin", "metal") and p.group not in env
             and not (p.group.startswith("OUTIL") and p.body == 0)]
    meshes = {}
    for p in parts:
        f = view_dir / f"{p.id}.stl"
        if f.exists():
            meshes[p.id] = trimesh.load(str(f), force="mesh")
    body = {p.id: p.body for p in parts}
    name = {p.id: p.name for p in parts}
    grp = {p.id: p.group for p in parts}
    out = {}
    for jd in asm.joints:
        b, o, a = jd["body"], np.array(jd["origin"]), np.array(jd["axis"])
        mov = CollisionManager()
        fix = CollisionManager()
        for pid, m in meshes.items():
            (mov if body[pid] >= b else fix).add_object(pid, m)

        def contacts(theta):
            R = trimesh.transformations.rotation_matrix(math.radians(theta), a, o)
            for pid in meshes:
                if body[pid] >= b:
                    mov.set_transform(pid, R)
            hit, data = mov.in_collision_other(fix, return_data=True)
            res = {}
            for c in data:
                n1, n2 = sorted(c.names)
                if grp[n1] == grp[n2] == jd["name"]:
                    continue                                 # engrenages internes du reducteur de cet axe
                if c.depth > depth_mm:
                    res[(n1, n2)] = max(res.get((n1, n2), 0.0), c.depth)
            return res
        base = contacts(0.0)
        found = {}
        for th in np.arange(-jd["limit"], jd["limit"] + 1e-6, step_deg):
            if abs(th) < 1e-9:
                continue
            for k, dpt in contacts(th).items():
                if k in base:
                    continue
                f = found.setdefault(k, {"de": th, "a": th, "prof_mm": 0.0})
                f["de"], f["a"] = min(f["de"], th), max(f["a"], th)
                f["prof_mm"] = max(f["prof_mm"], round(float(dpt), 2))
        out[jd["name"]] = [{"a": name[k[0]], "b": name[k[1]], "angles_deg": [round(v["de"], 1), round(v["a"], 1)],
                            "penetration_mm": v["prof_mm"]} for k, v in found.items()]
        progress(f"Balayage {jd['name']} : {len(found)} contact(s) nouveau(x)")
    return out


# ------------------------------------------------------------------ analyse structurelle
MATERIAUX = {                  # contrainte admissible de CALCUL (MPa) : prudente (anisotropie, fluage,
    "PETG": 12.0,              # fatigue), pas la valeur de fiche technique. Ordre = cout croissant.
    "PA-CF (imprime maison)": 25.0,
    "MJF PA12 (JLC3DP)": 15.0,
    "FDM PA12-CF (JLC3DP)": 25.0,
    "Aluminium 6061 (CNC, JLCCNC)": 110.0,
    "Acier S235 (plat / tole du commerce)": 140.0,
    "Inox 316L fritte (BJ, JLC3DP)": 80.0,
    "Laiton CuZn39Pb3 (CNC, JLCCNC)": 100.0,
    "Titane TC4 (SLM, JLC3DP)": 300.0,
}
ORDRE_COUT = ["PETG", "PA-CF (imprime maison)", "FDM PA12-CF (JLC3DP)", "Acier S235 (plat / tole du commerce)",
              "Aluminium 6061 (CNC, JLCCNC)", "Inox 316L fritte (BJ, JLC3DP)", "Laiton CuZn39Pb3 (CNC, JLCCNC)",
              "Titane TC4 (SLM, JLC3DP)"]


def _section_props(polys):
    """I (mm^4) autour de l'axe median parallele a Y (flexion dans le plan XZ) et fibre extreme c."""
    from shapely.geometry import MultiPolygon
    A = Sx = 0.0
    items = []
    for pg in polys:
        if pg.area < 1.0:
            continue
        items.append(pg)
        A += pg.area
        Sx += pg.area * pg.centroid.x
    if A <= 0:
        return None
    xc = Sx / A
    I = 0.0
    xmin, xmax = 1e9, -1e9
    for pg in items:
        # moment d'inertie exact d'un polygone (formule des aires signees), puis Huygens
        for ring, sgn in [(pg.exterior, 1.0)] + [(h, -1.0) for h in pg.interiors]:
            xs, ys = np.array(ring.xy)
            xs = xs - xc
            cr = xs[:-1] * ys[1:] - xs[1:] * ys[:-1]
            Iy = np.sum((xs[:-1] ** 2 + xs[:-1] * xs[1:] + xs[1:] ** 2) * cr) / 12.0
            I += abs(Iy) * sgn
            xmin, xmax = min(xmin, xs.min()), max(xmax, xs.max())
    return {"A": A, "I": abs(I), "c": max(abs(xmin), abs(xmax))}


def structure_check(asm, masses, coms, view_dir, cfg, spring_res=None, dyn=2.0, step=5.0) -> dict:
    """Coefficient de securite en flexion le long du bras, bras a l'horizontale (J2 = 90 deg),
    charge utile au bout, coefficient dynamique `dyn`."""
    import trimesh
    from shapely.geometry import Polygon
    g = 9.81
    j2 = asm.joints[1]
    z2 = j2["origin"][2]
    bodies = {p.id: p.body for p in asm.parts}
    loads = [(masses[pid], coms[pid][2]) for pid in masses if bodies.get(pid, 0) >= 2
             and pid in coms]
    tip_z = asm.info["z_bride_outil"] + asm.head_geom.z_face + 80.0
    loads.append((cfg["payload"], tip_z))
    mat = "PETG"
    allow = MATERIAUX[mat]
    printed = [p for p in asm.parts if p.kind == "print" and p.body >= 2 and p.category in
               ("structure", "housing", "output", "cap", "tool") and not p.group.startswith(("OUTIL", "RESSORT"))]
    meshes = {}
    for p in printed:
        f = view_dir / f"{p.id}.stl"
        if f.exists():
            meshes[p.id] = trimesh.load(str(f), force="mesh")
    names = {p.id: p.name for p in printed}
    rows = []
    zmax = max(m.bounds[1][2] for m in meshes.values()) if meshes else z2
    for z in np.arange(z2 + step, zmax, step):
        M = dyn * g * sum(m * max(0.0, (zc - z) / 1000.0) for m, zc in loads) * 1000.0     # N.mm
        if M <= 0:
            continue
        polys, who = [], []
        for pid, m in meshes.items():
            if not (m.bounds[0][2] < z < m.bounds[1][2]):
                continue
            sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            if sec is None:
                continue
            try:
                p2, _ = sec.to_planar(to_2D=np.eye(4))
                for pg in p2.polygons_full:
                    polys.append(Polygon(pg.exterior.coords, [h.coords for h in pg.interiors]))
                who.append(pid)
            except Exception:
                continue
        sp = _section_props(polys)
        if not sp or sp["I"] <= 0:
            continue
        sigma = M * sp["c"] / sp["I"]
        rows.append({"z_mm": round(float(z)), "M_Nm": round(M / 1000.0, 1), "I_cm4": round(sp["I"] / 1e4, 2),
                     "sigma_MPa": round(float(sigma), 2), "coef": round(allow / max(sigma, 1e-9), 2),
                     "pieces": [names[w] for w in who]})
    weak = sorted(rows, key=lambda r: r["coef"])[:8]
    out = {"hypotheses": f"bras horizontal (J2 = 90 deg), charge {cfg['payload']} kg au bout, coefficient "
                         f"dynamique x{dyn}, {mat} admissible {allow} MPa (FDM : adhesion inter-couches, fluage)",
           "sections_critiques": weak, "coef_mini": weak[0]["coef"] if weak else None,
           "profil": [{"z_mm": r["z_mm"], "coef": r["coef"]} for r in rows]}
    # ---------------------------------------------- pieces speciales : compensation J2
    special = []
    if spring_res and spring_res.get("ressort_reel") and "F_max_N" in spring_res["ressort_reel"]:
        des = spring_res["ressort_reel"]
        T = des["F_max_N"] / 2.0                                   # tension du cable (palan 2:1)
        sp = asm.spring
        pot = next((p for p in asm.parts if p.id == "RESSORT_potence"), None)
        if pot is not None and pot.kind == "metal":
            U = pot.meta["section_U"]
            e, w, hf = U["e"], U["w"], U["hf"]
            L = pot.meta["porte_a_faux_mm"]
            # profil U : 2 ailes (e x hf) + ame (w x e) en bas ; axe neutre puis fibre extreme
            A_f, A_w = 2 * e * hf, w * e
            zc = (A_f * (hf / 2) + A_w * (e / 2)) / (A_f + A_w)
            I = 2 * (e * hf ** 3 / 12 + e * hf * (hf / 2 - zc) ** 2) + w * e ** 3 / 12 + A_w * (zc - e / 2) ** 2
            c = max(zc, hf - zc)
            sig = dyn * T * L * c / I
            k_ = MATERIAUX["Acier S235 (plat / tole du commerce)"] / sig
            special.append({"piece": pot.name, "contrainte_MPa": round(sig, 1), "materiau": pot.material,
                            "coef": round(k_, 2), "detail": f"profil U {w:g}x{hf:g}x{e:g} mm (I = {I:.0f} mm4), "
                            f"porte-a-faux {L:.0f} mm, tension {T:.0f} N", "ok_en_PETG": False})
        else:
            L = sp["y_pl"] - 64.0
            b, hh = 20.0, 24.0
            I = b * hh ** 3 / 12.0
            sig = dyn * T * L * (hh / 2) / I
            special.append(_reco_piece("Compensation J2 - potence d'ancrage A (tourelle)", sig,
                                       f"poutre {b:g}x{hh:g} mm en porte-a-faux {L:.0f} mm, tension {T:.0f} N"))
        # goupille haute d5 en double cisaillement (acier) : effort = ressort
        dp = sp.get("pin_d", 5.0)
        tau = dyn * des["F_max_N"] / (2 * math.pi * (dp / 2) ** 2)
        special.append({"piece": f"Compensation J2 - goupille haute d{dp:g} (acier)", "contrainte_MPa": round(tau, 1),
                        "materiau": "acier (goupille rectifiee, du commerce)", "coef": round(200.0 / tau, 2),
                        "detail": f"double cisaillement, {des['F_max_N']} N"})
        # appui de la goupille dans les parois imprimees du bras (matage)
        lb = sp.get("boss_l", 4.0)
        p_mat = dyn * des["F_max_N"] / (2 * dp * lb)               # 2 bossages x d x longueur d'appui
        special.append(_reco_piece("Bras - appui de la goupille haute (bossages)", p_mat,
                                   f"matage d{dp:g} sur 2 bossages de {lb:g} mm", matage=True))
    out["pieces_speciales"] = special
    return out


def _reco_piece(name, sigma, detail, matage=False):
    """Choisit le materiau le moins cher qui donne un coefficient >= 2."""
    order = ORDRE_COUT
    k = 1.6 if matage else 1.0                                      # pression de matage admissible ~1.6 x
    for m in order:
        c = MATERIAUX[m] * k / max(sigma, 1e-9)
        if c >= 2.0:
            return {"piece": name, "contrainte_MPa": round(sigma, 1), "materiau": m, "coef": round(c, 2),
                    "detail": detail, "ok_en_PETG": m == "PETG"}
    return {"piece": name, "contrainte_MPa": round(sigma, 1), "materiau": "a redessiner", "coef":
            round(MATERIAUX[order[-1]] * k / sigma, 2), "detail": detail, "ok_en_PETG": False}
