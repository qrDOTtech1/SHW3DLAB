"""Scene « atelier » : un bras avec sa tete active nue, le rack d'outils (outils suspendus face en
haut), l'outil P (porte-pinceau) et la DaVinHand ARTICULEE (phalanges, ecartement, 5e
metacarpe, opposition), la toile sur les 4 RFP602 et un gobelet a saisir.

Les outils sont des corps libres ; quand le robot verrouille, une contrainte de soudure relie
l'outil a la tete (equivalent du verrou baionnette + cones).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import trimesh

from .mjcf import build_scene, _fmt

HAND_TORQUE = 0.30          # N.m maxi par articulation (tension tendon x bras de levier)


def _load_tool_frame(build_dir, p):
    m = trimesh.load(str(build_dir / p["view"]), force="mesh")
    Ti = np.linalg.inv(np.array(p["T"]))
    m.apply_transform(Ti)
    m.apply_scale(0.001)
    return m


def _inertial(ms):
    M = sum(m for m, _ in ms)
    if M <= 0:
        return 0.01, np.zeros(3)
    c = sum(m * c for m, c in ms) / M
    return M, c


def build_atelier(build_dir: Path, progress=lambda m: None) -> dict:
    man = json.loads((build_dir / "manifest.json").read_text(encoding="utf8"))
    sim = build_dir / "sim"
    mdir = sim / "meshes"
    mdir.mkdir(parents=True, exist_ok=True)
    parts = man["parts"]
    assets, world, acts, eq = [], [], [], []

    # ------------------------------------------------------------ rack (statique)
    for p in parts:
        if p["group"] == "RACK" and p["kind"] == "print":
            m = trimesh.load(str(build_dir / p["view"]), force="mesh")
            m.apply_scale(0.001)
            n = f"r_{p['id']}"
            m.export(str(mdir / f"{n}.stl"))
            assets.append(f'<mesh name="{n}" file="meshes/{n}.stl"/>')
            hn = f"rh_{p['id']}"
            # les fourches sont des plaques percees : on garde le maillage (enveloppe convexe
            # des 2 bras de fourche via decomposition simple : un hull par moitie)
            if "fourche" in p["id"]:
                # fourche = plaque en U : 3 boites orientees (2 bras + traverse) dans le repere
                # de la fourche (tourne de yaw autour de J1), sinon l'enveloppe boucherait le U
                k_slot = int(p["id"].rsplit("_", 1)[1]) - 1
                sl = list(man["rack_slots"].values())[k_slot]
                fk = sl["fourche"]
                yaw = math.radians(sl["yaw_deg"])
                q = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
                Rz = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
                c = np.array(sl["face"]) / 1000.0
                zc = (m.bounds[0][2] + m.bounds[1][2]) / 2
                hz = (m.bounds[1][2] - m.bounds[0][2]) / 2
                sw, L, pitch = fk["slot_w"] / 1000, fk["fork_L"] / 1000, fk["pitch"] / 1000
                arm_w = (pitch - 8e-3 - sw) / 2
                yb0, yb1 = -L / 2, -sw / 2                 # plein entre les bras, cote montant
                boxes = [((-(sw / 2 + arm_w / 2), 0.0), (arm_w / 2, L / 2)),
                         ((sw / 2 + arm_w / 2, 0.0), (arm_w / 2, L / 2)),
                         ((0.0, (yb0 + yb1) / 2), (sw / 2, (yb1 - yb0) / 2))]
                for (lx, ly), (sx, sy) in boxes:
                    pc = np.array([c[0], c[1], zc]) + Rz @ np.array([lx, ly, 0.0])
                    world.append(f'    <geom type="box" pos="{_fmt(pc)}" quat="{_fmt(q)}" size="{_fmt([sx, sy, hz])}" '
                                 f'rgba="0 0 0 0" contype="1" conaffinity="1"/>')
            else:
                hull = m.convex_hull
                hull.export(str(mdir / f"{hn}.stl"))
                assets.append(f'<mesh name="{hn}" file="meshes/{hn}.stl"/>')
                world.append(f'    <geom type="mesh" mesh="{hn}" rgba="0 0 0 0" contype="1" conaffinity="1"/>')
            world.append(f'    <geom type="mesh" mesh="{n}" contype="0" conaffinity="0" rgba="0.55 0.6 0.66 1"/>')

    # ------------------------------------------------------------ outils libres
    slots = {k: np.array(v["face"]) / 1000.0 for k, v in man["rack_slots"].items()}
    tools_info = {}

    def tool_xml(tid, root_pos):
        ps = [p for p in parts if p["group"] == f"OUTIL_{tid}" and p["kind"] != "keepout"
              and not ("douille" in p["id"])]
        # arbre articule (main) a partir des chaines d'animation (repere outil)
        keyof = lambda j: (tuple(np.round(j["o"], 2)), tuple(np.round(j["a"], 4)))  # noqa: E731
        joints, parent, jdata = {}, {}, {}
        body_of = {}
        for p in ps:
            ch = (p.get("anim") or {}).get("joints") if (p.get("anim") or {}).get("type") == "chain" else None
            if not ch:
                body_of[p["id"]] = None
                continue
            prev = None
            for j in ch:
                k = keyof(j)
                if k not in joints:
                    joints[k] = f"{tid}_j{len(joints)}"
                    parent[k] = prev
                    jdata[k] = j
                prev = k
            body_of[p["id"]] = prev
        # geometrie par corps
        groups = {}
        for p in ps:
            groups.setdefault(body_of[p["id"]], []).append(p)
        children = {}
        for k, pk in parent.items():
            children.setdefault(pk, []).append(k)

        def body_block(k, ind):
            ps_b = groups.get(k, [])
            lines = []
            ms = []
            for p in ps_b:
                mesh = _load_tool_frame(build_dir, p)
                n = f"t_{p['id']}"
                mesh.export(str(mdir / f"{n}.stl"))
                assets.append(f'<mesh name="{n}" file="meshes/{n}.stl"/>')
                col = "0.91 0.64 0.24 1" if p["kind"] == "print" else "0.25 0.27 0.3 1"
                if "pulpe" in p["id"]:
                    col = "0.26 0.65 0.78 1"
                lines.append(f'{ind}<geom type="mesh" mesh="{n}" contype="0" conaffinity="0" group="1" rgba="{col}"/>')
                if p["kind"] == "print" and mesh.volume > 2e-8:
                    hn = f"th_{p['id']}"
                    mesh.convex_hull.export(str(mdir / f"{hn}.stl"))
                    assets.append(f'<mesh name="{hn}" file="meshes/{hn}.stl"/>')
                    lines.append(f'{ind}<geom type="mesh" mesh="{hn}" class="tool"/>')
                Ti = np.linalg.inv(np.array(p["T"]))
                c = (Ti @ np.r_[np.array(p.get("com") or [0, 0, 0]), 1.0])[:3] / 1000.0
                ms.append((p["masse_g"] / 1000.0, c))
            M, c = _inertial(ms)
            I = max(M, 1e-3) * 2e-4
            lines.insert(0, f'{ind}<inertial pos="{_fmt(c)}" mass="{max(M, 0.002):.4g}" diaginertia="{I:.3g} {I:.3g} {I:.3g}"/>')
            for ck in children.get(k, []):
                j = jdata[ck]
                lo, hi = sorted((0.0, math.radians(j["max"])))
                jn = joints[ck]
                lines.append(f'{ind}<body name="{jn}_b">')
                lines.append(f'{ind}  <joint name="{jn}" pos="{_fmt(np.array(j["o"]) / 1000)}" axis="{_fmt(j["a"])}" '
                             f'range="{lo - 0.01:.4f} {hi + 0.01:.4f}" damping="0.02" armature="0.0005"/>')
                lines += body_block(ck, ind + "  ")
                lines.append(f'{ind}</body>')
                kp = HAND_TORQUE / 0.25
                acts.append(f'<position name="{jn}" joint="{jn}" kp="{kp:.4g}" kv="{kp * 0.03:.4g}" '
                            f'forcerange="{-HAND_TORQUE} {HAND_TORQUE}" ctrlrange="{lo - 0.01:.4f} {hi + 0.01:.4f}"/>')
                tools_info.setdefault(tid, {}).setdefault("ctrl", {}).setdefault(j.get("ctrl", "x"), []).append(
                    [jn, math.radians(j["max"])])
            return lines

        yaw = math.radians(man["rack_slots"][tid].get("yaw_deg", 0.0))
        qt = [0.0, math.cos(yaw / 2), math.sin(yaw / 2), 0.0]           # Rz(yaw) * Rx(180)
        body = [f'    <body name="outil_{tid}" pos="{_fmt(root_pos)}" quat="{_fmt(qt)}">',
                '      <freejoint name="outil_{}_libre"/>'.format(tid)]
        body += body_block(None, "      ")
        if tid == "P":                               # poils du pinceau : touffe souple (pas une tige)
            ee = next(t for t in man["tools"] if t["id"] == "P")
            tip, Lp = ee["z_offset_pointe_mm"] / 1000.0, ee["longueur_poils_mm"] / 1000.0
            body.append(f'      <geom name="poils" type="capsule" fromto="0 0 {tip - Lp + 0.003:.4f} 0 0 {tip - 0.0025:.4f}" '
                        f'size="0.0025" rgba="0.35 0.22 0.1 1" class="tool" solref="0.03 0.6" solimp="0.5 0.9 0.004"/>')
        body.append("    </body>")
        world.append("\n".join(body))
        eq.append(f'    <weld name="verrou_{tid}" body1="A_b6" body2="outil_{tid}" active="false" solref="0.003 1"/>')
        # point de travail (repere outil)
        zmax = max(np.array(p["bbox"]).reshape(2, 3)[1][2] for p in ps)  # indicatif
        rs = man["rack_slots"][tid]
        tools_info.setdefault(tid, {}).update({"slot": slots[tid].tolist(), "sortie": rs.get("sortie", [0, 1, 0]),
                                               "x": rs.get("x", [1, 0, 0]),
                                               "course_sortie": rs.get("course_sortie", 110.0) / 1000.0})

    progress("Scene atelier : outil P + DaVinHand articulee...")
    tool_xml("P", slots["P"])
    tool_xml("H", slots["H"])

    # TCP en repere outil : pointe du pinceau (P) ; centre de prise devant la paume (H)
    def tool_frame_bbox(tid, pred):
        pts = []
        for p in parts:
            if p["group"] == f"OUTIL_{tid}" and pred(p):
                Ti = np.linalg.inv(np.array(p["T"]))
                b = np.array(p["bbox"]).reshape(2, 3)
                for x in (b[0][0], b[1][0]):
                    for y in (b[0][1], b[1][1]):
                        for z in (b[0][2], b[1][2]):
                            pts.append((Ti @ np.r_[x, y, z, 1.0])[:3])
        pts = np.array(pts)
        return pts.min(0), pts.max(0)
    for tid in ("P", "H"):                          # longueur de l'outil sous la face (degagement du rack)
        lo_t, hi_t = tool_frame_bbox(tid, lambda p: p["kind"] != "keepout")
        tools_info[tid]["longueur"] = float(hi_t[2]) / 1000.0
    lo, hi = tool_frame_bbox("P", lambda p: p["kind"] == "print" and "douille" not in p["id"])
    # pointe du pinceau : valeur de l'EEPROM de l'outil (comme le robot reel), poils compris
    eeP = next(t for t in man["tools"] if t["id"] == "P")
    tools_info["P"]["tcp"] = [0.0, 0.0, eeP["z_offset_pointe_mm"] / 1000.0]
    tools_info["P"]["longueur"] = max(tools_info["P"]["longueur"], eeP["z_offset_pointe_mm"] / 1000.0)
    lo, hi = tool_frame_bbox("H", lambda p: p["id"] == "OUTILH_paume")
    tools_info["H"]["tcp"] = [0.0, float(lo[1]) / 1000.0 - 0.028, float(lo[2] + 0.62 * (hi[2] - lo[2])) / 1000.0]

    # ------------------------------------------------------------ objets
    world.append('''    <body name="gobelet" pos="0.30 0.24 0.066">
      <freejoint name="gobelet_libre"/>
      <inertial pos="0 0 0" mass="0.12" diaginertia="8e-5 8e-5 5e-5"/>
      <geom type="cylinder" size="0.03 0.065" class="obj" rgba="0.85 0.25 0.3 1"/>
      <site name="gobelet_c" size="0.004"/>
    </body>''')
    extra = {"exclude": ("OUTIL",), "assets": assets, "world": "\n".join(world),
             "equality": "\n".join(eq), "actuators": acts}
    info = build_scene(build_dir, progress=progress, arms=("A",), scene_name="atelier", extra=extra)
    info["outils"] = tools_info
    info["eeprom"] = {t["id"]: t for t in man["tools"]}
    (sim / "atelier_info.json").write_text(json.dumps(info, indent=1), encoding="utf8")
    return info
