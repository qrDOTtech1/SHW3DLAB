"""Pipeline complet : assemblage -> orientation d'impression -> exports -> controles -> manifeste."""
from __future__ import annotations

import json
import math
import os
import shutil
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import cadquery as cq
import numpy as np

from .assembly import build_assembly
from .cad.util import apply_T, to_shape, bbox
from .checks import (print_orientation, part_mass, run_checks, torque_analysis, firmware_doc,
                     coupling_capacity)
from .config import normalize, cfg_hash, BEARINGS
from .parts.effector import PINOUT, CONE_ANGLES

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "sortie" / "davinbot"


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if hasattr(o, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(o)
    return str(o)


def export_stl(shape, path, tol, ang):
    cq.exporters.export(cq.Workplane("XY").add(shape), str(path), tolerance=tol, angularTolerance=ang)


def build(cfg_in: dict | None, progress=lambda m, f=None: None, full_interference=True) -> dict:
    cfg = normalize(cfg_in)
    h = cfg_hash(cfg)
    out = OUT / h
    if (out / "manifest.json").exists():
        progress("Resultat en cache.", 1.0)
        return json.loads((out / "manifest.json").read_text(encoding="utf8"))
    tmp = OUT / (h + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    for sub in ("view", "stl", "step"):
        (tmp / sub).mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = []

    def P(msg, f=None):
        log.append(f"[{time.time() - t0:6.1f}s] {msg}")
        progress(msg, f)

    P("Dimensionnement des reducteurs et assemblage...", 0.02)
    asm = build_assembly(cfg, lambda m, f=None: P(m))

    # --------------------------------------------------------- formes monde + exports
    world = {}
    parts_json = []
    masses, coms = {}, {}
    n = len(asm.parts)
    step_all = []

    def export_part(i, p):
        shp = to_shape(p.shape)
        ws = apply_T(shp, p.T)
        wb = bbox(ws)
        world[p.id] = (ws, wb)
        vol = abs(shp.Volume()) / 1000.0
        m = part_mass(p, cfg, vol)
        masses[p.id] = m
        try:
            c = ws.Center()
            coms[p.id] = np.array([c.x, c.y, c.z])
        except Exception:
            coms[p.id] = np.array([(wb[0] + wb[3]) / 2, (wb[1] + wb[4]) / 2, (wb[2] + wb[5]) / 2])
        export_stl(ws, tmp / "view" / f"{p.id}.stl", 0.08 if p.kind == "print" else 0.2, 0.3)
        entry = {
            "id": p.id, "name": p.name, "group": p.group, "body": p.body, "kind": p.kind,
            "category": p.category, "color": p.color, "notes": p.notes, "anim": p.anim,
            "T": np.asarray(p.T).round(6).tolist(), "volume_cm3": round(vol, 2),
            "masse_g": round(m * 1000, 1), "bbox": [round(v, 2) for v in wb],
            "com": [round(float(v), 2) for v in coms[p.id]],
            "view": f"view/{p.id}.stl",
        }
        if p.kind == "metal":
            sols = [so for so in ws.Solids() if so.Volume() > 1.0] if hasattr(ws, "Solids") else [ws]
            entry.update({"solides": len(sols), "fits": True, "materiau": p.material,
                          "stl": f"stl/{p.id}.stl", "step": f"step/{p.id}.step", "a_commander": True})
            export_stl(ws, tmp / "stl" / f"{p.id}.stl", cfg["stl_tol"], 0.1)
            cq.exporters.export(cq.Workplane("XY").add(ws), str(tmp / "step" / f"{p.id}.step"))
            step_all.append(ws)
        if p.kind == "print":
            # piece MONOBLOC : un seul solide (un fragment libre = piece qui tombe a l'impression
            # ou qui casse au montage). Les eclats < 1 mm3 (artefacts booleens) sont ignores.
            sols = [so for so in ws.Solids() if so.Volume() > 1.0] if hasattr(ws, "Solids") else [ws]
            entry["solides"] = len(sols)
            if len(sols) > 1:
                entry["fragments_mm3"] = sorted([round(so.Volume()) for so in sols], reverse=True)[:6]
            po = print_orientation(p, cfg)
            entry.update({"fits": po["fits"], "print_dims": po["dims"], "print_up": po["up"],
                          "print_rot_z": po["rot_z"], "support_cm2": po["support_cm2"], "stl": f"stl/{p.id}.stl", "step": f"step/{p.id}.step",
                          "filament_g": round(m * 1000, 1)})
            export_stl(po["shape"], tmp / "stl" / f"{p.id}.stl", cfg["stl_tol"], 0.1)
            cq.exporters.export(cq.Workplane("XY").add(po["shape"]), str(tmp / "step" / f"{p.id}.step"))
            step_all.append(ws)
        parts_json.append(entry)
        if i % 8 == 0:
            P(f"Export {i + 1}/{n} : {p.name}", 0.1 + 0.55 * i / n)

    for i, p in enumerate(asm.parts):
        export_part(i, p)

    torque = torque_analysis(asm, masses, coms)
    spring_res = None
    if getattr(asm, "spring", None) is not None:
        from .spring import size_spring, gravity_curve
        bodies = {p.id: p.body for p in asm.parts}
        j2 = asm.joints[1]
        j6 = asm.joints[5]
        tip = np.array([j6["origin"][0], j6["origin"][1],
                        asm.info["z_bride_outil"] + asm.head_geom.z_face + 80.0])
        pl = cfg["payload"]
        from .spring import _rot
        o, a, A, Bp = asm.spring["o"], asm.spring["axis"], asm.spring["A"], asm.spring["B"]
        spring_res = size_spring(asm.spring, j2, masses, coms, bodies, tip, pl, j2["limit"])
        if asm.spring.get("z_pin") is not None:
            # plus grande fraction de compensation pour laquelle un VRAI ressort tient dans le bras
            from .spring_talon import design_spring
            th_ = np.radians(spring_res["courbe"]["theta_deg"])
            Ls_ = [float(np.linalg.norm(A - (o + _rot(a, t) @ (Bp - o)))) for t in th_]
            room_ = asm.spring["z_pin"] - (asm.spring["z_floor"] + 6.0 + 22.0)
            for f in np.arange(1.0, 0.29, -0.05):
                r_ = size_spring(asm.spring, j2, masses, coms, bodies, tip, pl, j2["limit"], fraction=float(f))
                kk = r_["k_N_mm"]
                if design_spring(kk * max(Ls_), kk * min(Ls_), kk, room_) is not None:
                    spring_res = r_
                    spring_res["fraction_compensee"] = round(float(f), 2)
                    break
        # couple residuel reel : a vide et a pleine charge
        th = np.radians(spring_res["courbe"]["theta_deg"])
        k, L0 = spring_res["k_N_mm"], spring_res["L0_mm"]
        S = []
        for t in th:
            Bt = o + _rot(a, t) @ (Bp - o)
            dv = A - Bt
            L = np.linalg.norm(dv)
            S.append(k * (L - L0) * np.dot(np.cross((Bt - o) / 1000.0, dv / L), a))
        S = np.array(S)
        worst = 0.0
        for m_pl in (0.0, pl):
            Gc = gravity_curve(j2, masses, coms, bodies, th, [(m_pl, tip)])
            worst = max(worst, float(np.max(np.abs(Gc + S))))
        t2 = torque["J2"]
        t2["couple_requis_sans_ressort_Nm"] = t2["couple_requis_Nm"]
        t2["couple_requis_Nm"] = round(worst, 2)
        t2["ressort_compensation"] = spring_res["ressort"]
        key = "marge_mode_force" if "marge_mode_force" in t2 else "marge"
        avail = t2.get("mode_force_Nm", t2.get("couple_dispo_Nm"))
        t2[key] = round(avail / max(worst, 1e-6), 2)
        t2["ok"] = bool(t2[key] >= 1.2)
        if t2["ok"]:
            t2.pop("recommandation", None)
        # ressort REEL + moufle, places a leurs vraies cotes (architecture talon)
        if asm.spring.get("z_pin") is not None:
            from .spring_talon import design_spring, spring_parts
            Ls = []
            for t in th:
                Bt = o + _rot(a, t) @ (Bp - o)
                Ls.append(float(np.linalg.norm(A - Bt)))
            L_pose0 = float(np.linalg.norm(A - Bp))
            ratio = 2
            room = asm.spring["z_pin"] - (asm.spring["z_floor"] + 6.0 + 22.0)
            des = design_spring(k * max(Ls), k * min(Ls), k, room, ratio=ratio)
            if des is None:
                spring_res["ressort_reel"] = {"erreur": f"aucun ressort standard ne tient dans {room:.0f} mm "
                                                        "(reduire la compensation ou allonger le bras)"}
            else:
                des["allongement_pose0_mm"] = round(k * L_pose0 * ratio / des["k_N_mm"], 1)
                des["course_ressort_mm"] = round((max(Ls) - min(Ls)) / ratio, 1)
                des["place_disponible_mm"] = round(room, 1)
                spring_res["ressort_reel"] = des
                spring_res["ressort"] = (f"cable Dyneema d1.5 (tension maxi {k * max(Ls):.0f} N) + palan 2:1 ; "
                                         f"ressort de traction fil d{des['d_mm']:g} mm, D{des['D_mm']:g}, "
                                         f"{des['spires']} spires, L0 {des['L0_mm']:.0f} mm, k {des['k_N_mm']} N/mm, "
                                         f"{des['F_max_N']} N maxi (cisaillement {des['tau_MPa']} / "
                                         f"{des['tau_admissible_MPa']} MPa admissibles)")
                t2["ressort_compensation"] = spring_res["ressort"]
                arm_spec = asm.spring["arm_spec"]
                for p in spring_parts(asm.spring, des, asm.spring["z_pin"], arm_spec):
                    asm.parts.append(p)
                    export_part(len(asm.parts) - 1, p)
    P("Export STEP de l'assemblage complet...", 0.66)
    cq.exporters.export(cq.Workplane("XY").add(cq.Compound.makeCompound(step_all)),
                        str(tmp / "step" / "DAVINBOT_V2_assemblage.step"))

    # --------------------------------------------------------- controles
    checks = run_checks(asm, world, lambda m, f=None: P(m, 0.7 + 0.25 * (f or 0)), full_interference)
    fit_fail = [pj["name"] for pj in parts_json if pj["kind"] == "print" and not pj["fits"]]
    checks["pieces_metal"] = [{"piece": pj["name"], "materiau": pj.get("materiau"), "masse_g": pj["masse_g"],
                               "step": pj.get("step")} for pj in parts_json if pj["kind"] == "metal"]
    checks["monobloc"] = [{"piece": pj["name"], "solides": pj["solides"], "fragments_mm3": pj.get("fragments_mm3")}
                          for pj in parts_json if pj["kind"] in ("print", "metal") and pj.get("solides", 1) > 1]
    P("Balayage des articulations (collisions sur toute la plage)...", 0.93)
    from .checks import joint_sweep_check
    checks["balayage"] = joint_sweep_check(asm, tmp / "view", progress=lambda m, f=None: P(m))
    P("Analyse structurelle (sections x charges reelles)...", 0.96)
    from .checks import structure_check
    checks["structure"] = structure_check(asm, masses, coms, tmp / "view", cfg, spring_res)
    fw_doc = firmware_doc(asm, torque)
    asm.torque = torque
    cap = coupling_capacity(asm, masses, cfg)

    # --------------------------------------------------------- nomenclature
    bom = defaultdict(int)
    for p in asm.parts:
        if p.kind != "vitamin":
            continue
        nm = p.name.split(" - ", 1)[-1] if " - " in p.name else p.name
        if p.category == "bearing":
            key = nm.split("(")[0].strip().replace("roulement", "Roulement").strip()
            bom[f"{key}-2RS"] += 1
        elif p.category == "pin":
            continue
        else:
            bom[nm.split(" (")[0] if "MKS" in nm or "NEMA" in nm else nm] += 1
    for j, act in asm.acts.items():
        for desc, q in act.vitamins:
            bom[desc] += q
        bom[f"Vis CHC M4 x {act.info['vis_M4_longueur_min']} (boulons traversants {j}) + ecrou"] += len(act.mount_pts)
        bom["Vis CHC M4 x 12 (bride de sortie -> segment)"] += len(act.out_pts)
        bom["Insert thermique M4 x 8.1"] += len(act.out_pts)
        bom["Vis CHC M3 x 16 (bride -> moyeu)"] += 4
        bom["Insert thermique M3 x 5.7"] += 4
        bom["Vis CHC M3 x 8 (fixation NEMA 17)"] += 4 * len(act.motors)
        bom["Pige acier d3 x 8 (centrage bride)"] += 2
    nt = len(asm.tools_meta)
    bom["Platine 6 pastilles dorees (PCB 1.6 mm, cote outil)"] += nt
    bom[f"Aimant neodyme d{cfg['pogo_mag_d']:g}x{cfg['pogo_mag_h']:g} (centrage pogo)"] += 2 + 2 * nt
    bom["EEPROM I2C 24C02 (SOIC-8) sur mini-carte"] += len(asm.tools_meta)
    bom["Camera endoscopique USB d%g" % cfg["cam_d"]] += 0
    bom_list = sorted([{"ref": k, "qte": v} for k, v in bom.items() if v > 0], key=lambda x: x["ref"])

    total_print = sum(pj.get("filament_g", 0) for pj in parts_json if pj["kind"] == "print")
    manifest = {
        "hash": h, "version": "2.0.0", "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.time() - t0, 1), "cfg": cfg,
        "designs": {k: v.to_dict() for k, v in asm.designs.items()},
        "actuators": {k: {**a.info, "kind": a.kind} for k, a in asm.acts.items()},
        "joints": asm.joints, "parts": parts_json, "cable_path": asm.cable_path,
        "checks": {**checks, "fit_fail": fit_fail}, "torque": torque, "bom": bom_list,
        "info": {**asm.info, "filament_total_g": round(total_print, 0),
                 "pieces_imprimees": sum(1 for pj in parts_json if pj["kind"] == "print"),
                 "masse_bras_kg": round(sum(masses[p.id] for p in asm.parts if 1 <= p.body <= 6), 2)},
        "warnings": asm.warnings, "tools": asm.tools_meta,
        "head": {"pinout": PINOUT, "cone_angles": CONE_ANGLES, "ring_rot_deg": asm.head_geom.ring_rot,
                 "servo_rot_deg": asm.head_geom.servo_rot, "ring_teeth": asm.head_geom.zr,
                 "coupling_face_mm": round(asm.head_geom.z_face, 2)},
        "firmware_md": fw_doc, "log": log, "spring": spring_res, "changeur": cap,
        "rack_slots": getattr(asm, "rack_slots", {}),
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest, default=_json_default, indent=1), encoding="utf8")
    (tmp / "FIRMWARE_DSDM.md").write_text(fw_doc, encoding="utf8")
    (tmp / "outils_eeprom.json").write_text(json.dumps(asm.tools_meta, indent=2, ensure_ascii=False), encoding="utf8")
    P("Archive ZIP...", 0.97)
    with zipfile.ZipFile(tmp / "DAVINBOT_V2.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("stl", "step"):
            for f in sorted((tmp / sub).iterdir()):
                z.write(f, f"{sub}/{f.name}")
        z.write(tmp / "manifest.json", "manifest.json")
        z.write(tmp / "FIRMWARE_DSDM.md", "FIRMWARE_DSDM.md")
        z.write(tmp / "outils_eeprom.json", "outils_eeprom.json")
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    os.replace(tmp, out)
    P(f"Termine en {time.time() - t0:.0f} s.", 1.0)
    return manifest
