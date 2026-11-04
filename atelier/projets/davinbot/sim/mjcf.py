"""Generation de la scene MuJoCo (MJCF) a partir d'un build du generateur.

* Geometrie : maillages STL du build (pose zero), fusionnes par corps cinematique pour le
  rendu ; enveloppes convexes par piece pour les contacts.
* Inertie : masse et centre de gravite reels (volumes CAO x densite + elements du commerce),
  tenseur d'inertie de l'enveloppe convexe mis a l'echelle de la masse.
* Actionneurs : asservissement de position (boucle fermee MKS SERVO42C) dont la force est
  bornee au COUPLE DISPONIBLE calcule par le generateur (DSDM : mode Force) ; inertie
  reflechie des rotors (armature = J_rotor x rapport^2 x nb moteurs), frottement sec des
  reducteurs (rendement), amortissement visqueux.
* Scene : deux bras (A = artiste/manipulateur, B = assistant/inspecteur) face a face ;
  breadboard sur le boitier capteurs RFP602 ; composant ESP32 libre ; camera sur le poignet de B.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import trimesh

J_ROTOR = 8.2e-6        # kg.m2, NEMA 17 17HS19 (82 g.cm2)
EXCLUDE_GROUPS = ("RACK", "CAPT")   # outils du rack exclus plus bas (corps 0)
COLLIDE_CATS = ("structure", "housing", "cap", "tool", "sensor", "output")


def _load(path: Path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh")
    m.apply_scale(0.001)
    return m


def _fmt(v, n=6):
    return " ".join(f"{float(x):.{n}g}" for x in v)


def _slab_hulls(m, n=6):
    """Enveloppes convexes par tranches le long de z (axe du bras en pose d'assemblage) : une
    seule enveloppe noierait les ergots / equerres dans un volume plein et creerait des contacts
    fantomes (ex. plaque de face contre la fourche du rack)."""
    z0, z1 = m.bounds[0][2], m.bounds[1][2]
    if z1 - z0 < 1e-3 or m.volume < 1e-6:
        return [m.convex_hull]
    out = []
    edges = np.linspace(z0, z1, n + 1)
    for a, b in zip(edges[:-1], edges[1:]):
        try:
            sl = m.slice_plane([0, 0, a - 1e-5], [0, 0, 1], cap=True).slice_plane([0, 0, b + 1e-5], [0, 0, -1], cap=True)
        except Exception:
            continue
        if sl is not None and len(sl.vertices) >= 4:
            try:
                h = sl.convex_hull
                if h.volume > 1e-9:
                    out.append(h)
            except Exception:
                pass
    return out or [m.convex_hull]


def build_scene(build_dir: Path, arm_gap: float = 0.56, progress=lambda m: None, arms=("A", "B"),
                scene_name: str = "scene", extra: dict | None = None) -> dict:
    """Ecrit build_dir/sim/scene.xml + meshes ; retourne les infos utiles a l'environnement."""
    man = json.loads((build_dir / "manifest.json").read_text(encoding="utf8"))
    sim = build_dir / "sim"
    mdir = sim / "meshes"
    mdir.mkdir(parents=True, exist_ok=True)
    parts = man["parts"]
    joints = man["joints"]
    torque = man["torque"]
    designs = man["designs"]

    # ------------------------------------------------ maillages par corps (visuel) + hulls
    extra = extra or {}
    excl = EXCLUDE_GROUPS + tuple(extra.get("exclude", ()))
    arm_parts = [p for p in parts if p["kind"] != "keepout" and not p["group"].startswith(excl)
                 and not (p["group"].startswith("OUTIL") and p["body"] == 0)]
    bodies = {b: [p for p in arm_parts if p["body"] == b] for b in range(7)}
    assets, body_geoms, inertials = [], {}, {}
    for b, ps in bodies.items():
        progress(f"Maillages corps {b} ({len(ps)} pieces)")
        meshes, masses, coms = [], [], []
        geoms = []
        for p in ps:
            m = _load(build_dir / p["view"])
            meshes.append(m)
            masses.append(p["masse_g"] / 1000.0)
            c = p.get("com") or [(p["bbox"][i] + p["bbox"][i + 3]) / 2 for i in range(3)]
            coms.append(np.array(c) / 1000.0)
            if p["kind"] in ("print", "metal") and p["category"] in COLLIDE_CATS and m.volume > 2e-7:
                for k, hull in enumerate(_slab_hulls(m)):
                    name = f"h_{p['id']}_{k}"
                    hull.export(str(mdir / f"{name}.stl"))
                    assets.append(f'<mesh name="{name}" file="meshes/{name}.stl"/>')
                    geoms.append(f'<geom type="mesh" mesh="{name}" class="col"/>')
        if not meshes:
            continue
        merged = trimesh.util.concatenate(meshes)
        vname = f"v_body{b}"
        merged.export(str(mdir / f"{vname}.stl"))
        assets.append(f'<mesh name="{vname}" file="meshes/{vname}.stl"/>')
        geoms.insert(0, f'<geom type="mesh" mesh="{vname}" class="vis" rgba="{_rgba(b)}"/>')
        M = float(sum(masses))
        com = sum(m * c for m, c in zip(masses, coms)) / max(M, 1e-9)
        hull = merged.convex_hull
        I = hull.moment_inertia * (M / max(hull.volume, 1e-12)) if hull.volume > 0 else np.eye(3) * 1e-4
        # (moment_inertia de trimesh suppose densite 1 -> mise a l'echelle masse/volume)
        I = 0.5 * (I + I.T)
        inertials[b] = (M, com, I)
        body_geoms[b] = geoms

    # ------------------------------------------------ actionneurs (limites reelles)
    tm = man["cfg"]["motor_torque"] * man["cfg"]["motor_torque_derate"]
    act_xml, jinfo = [], []
    for j in joints:
        name = j["name"]
        d = designs[name]
        t = torque[name]
        if d["kind"] == "dsdm":
            tmax = t["mode_force_Nm"]
            ratio, nmot = d["i1"], 2
            eta = 0.95 * 0.80 * 0.90
            vmax = math.radians(t["vitesse_force_deg_s"])
            vmax_fast = math.radians(t["vitesse_vitesse_deg_s"])
            t_fast = t["mode_vitesse_Nm"]
        else:
            tmax = t.get("couple_dispo_Nm", tm * d["ratio"])
            ratio, nmot = d["ratio"], 1
            eta = 0.95 * (0.80 if d["kind"] == "cycloidal" else 0.88)
            vmax = math.radians(t.get("vitesse_max_deg_s", 90))
            vmax_fast, t_fast = vmax, tmax
        armature = J_ROTOR * ratio ** 2 * nmot
        friction = (1 - eta) * tmax * 0.15
        jinfo.append({"name": name, "tmax": tmax, "vmax": vmax, "vmax_fast": vmax_fast, "t_fast": t_fast,
                      "armature": armature, "friction": friction, "limit": math.radians(j["limit"]),
                      "dsdm": d["kind"] == "dsdm"})
    for arm in arms:
        for ji in jinfo:
            kp = ji["tmax"] / math.radians(3.0)          # saturation a 3 deg d'erreur
            act_xml.append(
                f'<position name="{arm}_{ji["name"]}" joint="{arm}_{ji["name"]}" kp="{kp:.4g}" '
                f'kv="{kp * 0.02:.4g}" forcerange="{-ji["tmax"]:.4g} {ji["tmax"]:.4g}" '
                f'ctrlrange="{-ji["limit"]:.4g} {ji["limit"]:.4g}"/>')

    # ------------------------------------------------ arbre des corps (bras A et B)
    def arm_xml(arm: str, pos, yaw_deg):
        q = _quat_z(yaw_deg)
        lines = [f'<body name="{arm}_base" pos="{_fmt(pos)}" quat="{_fmt(q)}">']
        depth = 0
        for b in range(7):
            M, com, I = inertials.get(b, (0.01, np.zeros(3), np.eye(3) * 1e-6))
            ind = "  " * (b + 1)
            if b > 0:
                j = joints[b - 1]
                ji = jinfo[b - 1]
                lines.append(f'{ind}<body name="{arm}_b{b}">')
                lines.append(f'{ind}  <joint name="{arm}_{j["name"]}" pos="{_fmt(np.array(j["origin"]) / 1000)}" '
                             f'axis="{_fmt(j["axis"])}" range="{-ji["limit"]:.4g} {ji["limit"]:.4g}" '
                             f'armature="{ji["armature"]:.4g}" frictionloss="{ji["friction"]:.4g}" damping="0.05"/>')
                depth += 1
            else:
                lines.append(f'{ind}<body name="{arm}_b0">')
                depth += 1
            lines.append(f'{ind}  <inertial pos="{_fmt(com)}" mass="{max(M, 1e-3):.5g}" '
                         f'fullinertia="{_fmt([I[0, 0], I[1, 1], I[2, 2], I[0, 1], I[0, 2], I[1, 2]])}"/>')
            for gx in body_geoms.get(b, []):
                lines.append(f'{ind}  {gx}')
            sp = man.get("spring")
            if sp and b == 1:
                lines.append(f'{ind}  <site name="{arm}_ressort_A" pos="{_fmt(np.array(sp["A"]) / 1000)}" size="0.004"/>')
            if sp and b == 2:
                lines.append(f'{ind}  <site name="{arm}_ressort_B" pos="{_fmt(np.array(sp["B"]) / 1000)}" size="0.004"/>')
            if b == 6:
                j6 = man["joints"][5]
                face = (np.array(j6["origin"]) + np.array(j6["axis"]) *
                        (man["actuators"]["J6"]["L_mm"] + man["head"]["coupling_face_mm"])) / 1000.0
                lines.append(f'{ind}  <site name="{arm}_face" pos="{_fmt(face)}" size="0.005" rgba="0 1 0.5 1"/>')
                tip = _tool_tip(man)
                lines.append(f'{ind}  <site name="{arm}_tip" pos="{_fmt(tip)}" size="0.004" rgba="1 0.6 0 1"/>')
                lines.append(f'{ind}  <geom name="{arm}_pointe" type="sphere" size="0.003" pos="{_fmt(tip)}" '
                             f'rgba="1 0.6 0 1" contype="1" conaffinity="1" friction="0.3 0.005 0.0001"/>')
            if b == 5 and arm == "B":
                cam = _camera_pose(man)
                lines.append(f'{ind}  <camera name="B_cam" pos="{_fmt(cam["pos"])}" '
                             f'xyaxes="{_fmt(cam["xyaxes"])}" fovy="70"/>')
                lines.append(f'{ind}  <site name="B_cam_site" pos="{_fmt(cam["pos"])}" size="0.004" rgba="0 0.8 1 1"/>')
        lines.append("  " * 7 + "</body>" * 0)
        lines += ["</body>"] * (depth + 1)
        return "\n".join(lines)

    sens = man["info"]["capteurs"]
    bx = sens["center"][0] / 1000.0
    top = 0.016 + 0.004 + 0.0038 + 0.003              # boitier + couvercle + tete de piston
    # plan de travail = boitier capteurs RFP602 (zone ou le bras tient avec marge de couple :
    # cartographie IK x couple gravitaire -> 0.6 a 0.85 du couple disponible)
    wx = bx
    bench_h = top + 0.008          # dessus de la toile (plaque sur 4 pistons)
    board = [wx + 0.045, 0.035, bench_h + 0.005]
    target = [wx + 0.06, 0.035, bench_h + 0.010 + 0.004]
    comp0 = [wx + 0.03, -0.05, bench_h + 0.004]
    B_pos = [0.75, 0.0, 0.0]
    xml = f"""<mujoco model="DaVinBot_V2_bimanuel">
  <compiler angle="radian" meshdir="." autolimits="true" inertiafromgeom="false"/>
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast" cone="elliptic"/>
  <size memory="200M"/>
  <visual><global offwidth="960" offheight="720"/><quality shadowsize="2048"/></visual>
  <default>
    <default class="vis"><geom contype="0" conaffinity="0" group="1" density="0"/></default>
    <default class="col"><geom contype="1" conaffinity="1" group="3" density="0" rgba="0.4 0.6 1 0.15"
      friction="0.6 0.005 0.0001" solref="0.004 1"/></default>
    <default class="tool"><geom contype="2" conaffinity="0" group="3" density="0" rgba="0.9 0.7 0.3 0.2"
      friction="1.0 0.01 0.0001" solref="0.004 1" condim="4"/></default>
    <default class="obj"><geom contype="1" conaffinity="3" friction="1.0 0.01 0.0001" condim="4"/></default>
  </default>
  <asset>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.13 0.15 0.18" rgb2="0.10 0.12 0.14" width="512" height="512"/>
    <material name="grid" texture="grid" texrepeat="8 8"/>
    {chr(10).join('    ' + a for a in assets + extra.get("assets", []))}
  </asset>
  <worldbody>
    <light pos="0.3 -0.6 1.8" dir="0 0.3 -1" diffuse="0.9 0.9 0.9"/>
    <camera name="vue" pos="0.38 -1.25 0.85" xyaxes="1 0 0 0 0.55 0.83" fovy="45"/>
    <camera name="zoom" pos="{bx + 0.30:.3f} -0.30 0.26" mode="targetbody" target="capteurs" fovy="40"/>
    <geom name="table" type="plane" size="1.5 1.0 0.02" material="grid" contype="1" conaffinity="3"/>
{extra.get("world", "")}
    <body name="capteurs" pos="{_fmt([bx, 0, 0])}">
      <geom name="boitier_capteurs" type="box" size="0.093 0.093 {top / 2:.4f}" pos="0 0 {top / 2:.4f}" rgba="0.26 0.65 0.78 1"/>
      <geom name="piston1" type="cylinder" size="0.006 0.002" pos="-0.075 -0.075 {top + 0.002:.4f}" rgba="0.9 0.6 0.2 1"/>
      <geom name="piston2" type="cylinder" size="0.006 0.002" pos="-0.075 0.075 {top + 0.002:.4f}" rgba="0.9 0.6 0.2 1"/>
      <geom name="piston3" type="cylinder" size="0.006 0.002" pos="0.075 -0.075 {top + 0.002:.4f}" rgba="0.9 0.6 0.2 1"/>
      <geom name="piston4" type="cylinder" size="0.006 0.002" pos="0.075 0.075 {top + 0.002:.4f}" rgba="0.9 0.6 0.2 1"/>
      <site name="rfp1" type="box" pos="-0.075 -0.075 {top + 0.004:.4f}" size="0.009 0.009 0.003" rgba="0 0 0 0"/>
      <site name="rfp2" type="box" pos="-0.075 0.075 {top + 0.004:.4f}" size="0.009 0.009 0.003" rgba="0 0 0 0"/>
      <site name="rfp3" type="box" pos="0.075 -0.075 {top + 0.004:.4f}" size="0.009 0.009 0.003" rgba="0 0 0 0"/>
      <site name="rfp4" type="box" pos="0.075 0.075 {top + 0.004:.4f}" size="0.009 0.009 0.003" rgba="0 0 0 0"/>
      <body name="toile" pos="0 0 {top + 0.006:.4f}">
        <joint name="toile_z" type="slide" axis="0 0 1" range="-0.003 0.01" damping="5"/>
        <joint name="toile_rx" type="hinge" axis="1 0 0" range="-0.05 0.05" damping="0.5"/>
        <joint name="toile_ry" type="hinge" axis="0 1 0" range="-0.05 0.05" damping="0.5"/>
        <inertial pos="0 0 0" mass="0.3" diaginertia="0.001 0.001 0.002"/>
        <geom name="toile" type="box" size="0.09 0.09 0.002" rgba="0.96 0.94 0.88 1" friction="0.8 0.005 0.0001"/>
      </body>
    </body>
    <body name="breadboard" pos="{_fmt(board)}">
      <geom type="box" size="0.041 0.028 0.005" rgba="0.95 0.95 0.92 1"/>
      <site name="cible" pos="0.015 0 0.009" size="0.003" rgba="0 1 0 1"/>
    </body>
    <body name="composant" pos="{_fmt(comp0)}">
      <freejoint name="composant"/>
      <inertial pos="0 0 0" mass="0.01" diaginertia="3e-7 5e-7 7e-7"/>
      <geom name="esp32" type="box" size="0.0125 0.009 0.003" rgba="0.1 0.1 0.12 1"
        friction="0.9 0.005 0.0001"/>
      <site name="composant_c" size="0.003" rgba="1 0 0 1"/>
    </body>
{arm_xml("A", [0, 0, 0], 0)}
{arm_xml("B", B_pos, 180) if "B" in arms else ""}
  </worldbody>
  <contact>
{chr(10).join(f'    <exclude body1="{a}_b{k}" body2="{a}_b{k + 1}"/>' for a in arms for k in range(6))}
{chr(10).join(f'    <exclude body1="world" body2="{a}_b1"/>' for a in arms)}
  </contact>
{_spring_xml(man, arms)}
  <equality>
{extra.get("equality", "")}
    <weld name="prise_A" body1="A_b6" body2="composant" active="false" solref="0.004 1"/>
  </equality>
  <actuator>
    {chr(10).join('    ' + a for a in act_xml + extra.get("actuators", []))}
  </actuator>
  <sensor>
    <framepos name="tipA" objtype="site" objname="A_tip"/>
    {'<framepos name="tipB" objtype="site" objname="B_tip"/>' if "B" in arms else ""}
    <touch name="rfp1" site="rfp1"/><touch name="rfp2" site="rfp2"/>
    <touch name="rfp3" site="rfp3"/><touch name="rfp4" site="rfp4"/>
    <framepos name="comp" objtype="site" objname="composant_c"/>
  </sensor>
</mujoco>"""
    if "B" not in arms:
        import re
        xml = re.sub(r'\s*<camera name="B_cam".*?/>', "", xml)
    (sim / f"{scene_name}.xml").write_text(xml, encoding="utf8")
    info = {"joints": jinfo, "target": target, "comp0": comp0, "board": board, "B_pos": B_pos,
            "present": [wx + 0.09, 0.0, 0.30],
            "home_deg": [-155, -25, 115, 0, -40, 0], "home_deg_B": [0, 10, 20, 0, 30, 0], "hash": man["hash"]}
    info["surface_z"] = top + 0.008
    info["canvas_center"] = [bx, 0.0]
    (sim / f"{scene_name}_info.json").write_text(json.dumps(info, indent=1), encoding="utf8")
    return info


def _spring_xml(man, arms):
    sp = man.get("spring")
    if not sp:
        return ""
    k = sp["k_N_mm"] * 1000.0
    L0 = sp["L0_mm"] / 1000.0
    body = "".join(f'''
    <spatial name="{a}_ressort_J2" stiffness="{k:.4g}" springlength="{L0:.4g}" width="0.004" rgba="0.9 0.8 0.1 1">
      <site site="{a}_ressort_A"/><site site="{a}_ressort_B"/>
    </spatial>''' for a in arms)
    return "  <tendon>" + body + "\n  </tendon>"


def _rgba(b):
    c = [(0.55, 0.6, 0.66), (0.62, 0.68, 0.75), (0.85, 0.87, 0.9), (0.62, 0.68, 0.75),
         (0.85, 0.87, 0.9), (0.62, 0.68, 0.75), (0.91, 0.64, 0.24)][b]
    return _fmt(list(c) + [1])


def _quat_z(deg):
    a = math.radians(deg) / 2
    return [math.cos(a), 0, 0, math.sin(a)]


def _tool_tip(man) -> np.ndarray:
    """Pointe de l'outil monte (repere monde pose zero, m)."""
    j6 = man["joints"][5]
    tool = [p for p in man["parts"] if p["group"] in ("OUTIL_P", "OUTIL_A") and p["body"] == 6
            and p["kind"] == "print"]
    if tool:
        z = max(p["bbox"][5] for p in tool) + 3.0      # bout reel de l'outil monte + 3 mm
    else:
        z = man["info"]["z_bride_outil"] + man["head"]["coupling_face_mm"] + 60.0
    return np.array([j6["origin"][0], j6["origin"][1], z]) / 1000.0


def _camera_pose(man) -> dict:
    cam = next((p for p in man["parts"] if p["id"] == "CAM_camera"), None)
    tip = _tool_tip(man)
    if cam is None:
        pos = tip + np.array([0, 0.06, -0.05])
    else:
        c = cam.get("com") or [(cam["bbox"][i] + cam["bbox"][i + 3]) / 2 for i in range(3)]
        pos = np.array(c) / 1000.0
    look = tip - pos
    look /= np.linalg.norm(look)
    x = np.cross(look, [0, 0, 1.0])
    if np.linalg.norm(x) < 1e-6:
        x = np.array([1.0, 0, 0])
    x /= np.linalg.norm(x)
    y = np.cross(x, look)          # camera MuJoCo : regarde selon -z, y vers le haut
    return {"pos": pos, "xyaxes": list(x) + list(y)}
