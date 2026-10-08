"""Rendus de previsualisation (matplotlib) : vue assemblee du presentoir avec porte-cles."""
from __future__ import annotations

import math

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from .objets import _mesh


def _T_rot_x(deg):
    return trimesh.transformations.rotation_matrix(math.radians(deg), [1, 0, 0])


def vue_presentoir(corps, info, porte_cles, fichier, largeur=170.0, hauteur=190.0, e=4.0, crochet_l=16.0,
                   n=3, coul_base="#f2efe8", coul_relief="#1d1d1f", coul_cles=("#e4572e", "#17bebb", "#ffc914")):
    inc = info["inclinaison_deg"]
    pan_b = _mesh(corps["panneau"]["base"])
    pan_r = _mesh(corps["panneau"]["relief"])
    pied = _mesh(corps["pied"]["base"])
    # panneau : de "a plat" (face +Z) a "debout incline", tenon dans la rainure du pied
    T = trimesh.transformations.translation_matrix([0, 6.0, 22.0 - 12.0]) @ _T_rot_x(inc) \
        @ trimesh.transformations.translation_matrix([0, hauteur / 2 + 12.0, 0])
    items = [(pied, coul_base, 1.0)]
    for m, c in ((pan_b, coul_base), (pan_r, coul_relief)):
        m = m.copy(); m.apply_transform(T); items.append((m, c, 1.0))
    # porte-cles pendus sous chaque crochet
    pas = largeur / n
    y_cr = hauteur / 2 - 62.0
    for i, (pc, col) in enumerate(zip(porte_cles, coul_cles)):
        x = -largeur / 2 + pas * (i + 0.5)
        tip = T @ np.array([x, y_cr, e + crochet_l * 0.6, 1.0])
        for part, c in ((pc["base"], col), (pc["relief"], coul_relief)):
            m = _mesh(part)
            # porte-cle vertical : anneau en haut, pendu au crochet
            R = trimesh.transformations.rotation_matrix(math.radians(90), [0, 0, 1])
            R = trimesh.transformations.rotation_matrix(math.radians(90), [1, 0, 0]) @ R
            m.apply_transform(R)
            top = m.bounds[1][2]
            m.apply_translation([tip[0] - m.centroid[0], tip[1] - m.bounds[0][1] - 1.0, tip[2] - top + 2.0])
            items.append((m, c, 1.0))
    fig = plt.figure(figsize=(9, 9))
    ax = fig.add_subplot(111, projection="3d")
    allv = []
    for m, c, a in items:
        pc = Poly3DCollection(m.vertices[m.faces], facecolor=c, edgecolor="none", alpha=a)
        pc.set_facecolor(c)
        ax.add_collection3d(pc)
        allv.append(m.vertices)
    V = np.vstack(allv)
    ctr, span = V.mean(0), (V.max(0) - V.min(0)).max() / 2
    for k, c in zip("xyz", ctr):
        getattr(ax, f"set_{k}lim")(c - span, c + span)
    ax.view_init(18, -62)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(fichier, dpi=110, facecolor="white")
    plt.close(fig)


def rendu_mujoco(items, fichier, largeur=1100, hauteur=900, azimut=-115, elevation=-18, distance=None,
                 fond=(0.93, 0.93, 0.95), cible=None, lignes=None):
    """Rendu eclaire (ombres) PLEINE RESOLUTION : items = [(trimesh, '#rrggbb')] en mm. Les gros maillages
    sont decoupes en morceaux (limite du lecteur STL de MuJoCo) au lieu d'etre simplifies.
    cible = point vise (mm) pour une LOUPE (avec distance en mm) ; lignes = [(pts Nx3 mm, '#rrggbb', rayon_mm)]
    tracees en tubes sur la piece (controle des decoupes)."""
    import shutil
    import tempfile
    from pathlib import Path
    import mujoco
    from PIL import Image
    tmp = Path(tempfile.mkdtemp())
    assets, geoms = [], []
    allv = []
    n = 0
    for m, col in items:
        rgb = [int(col[k:k + 2], 16) / 255 for k in (1, 3, 5)]
        for d in range(0, len(m.faces), 180_000):
            mm = m.submesh([np.arange(d, min(len(m.faces), d + 180_000))], append=True)
            mm.apply_scale(0.001)
            f = tmp / f"m{n}.stl"
            mm.export(f)
            allv.append(mm.vertices)
            assets.append(f'<mesh name="m{n}" file="{f.as_posix()}"/>')
            geoms.append(f'<geom type="mesh" mesh="m{n}" rgba="{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} 1" '
                         f'contype="0" conaffinity="0"/>')
            n += 1
    for pts, col, ray in (lignes or []):
        rgb = [int(col[k:k + 2], 16) / 255 for k in (1, 3, 5)]
        P = np.asarray(pts, float) * 0.001
        for a, b in zip(P[:-1], P[1:]):
            if np.linalg.norm(b - a) < 1e-7:
                continue
            geoms.append(f'<geom type="capsule" fromto="{a[0]} {a[1]} {a[2]} {b[0]} {b[1]} {b[2]}" size="{ray * 0.001}" '
                         f'rgba="{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} 1" contype="0" conaffinity="0"/>')
    V = np.vstack(allv)
    c = V.mean(0) if cible is None else np.asarray(cible, float) * 0.001
    span = float((V.max(0) - V.min(0)).max())
    if distance is not None and cible is not None:
        distance = distance * 0.001
    zmin = float(V[:, 2].min())
    xml = f"""<mujoco><visual><global offwidth="{largeur}" offheight="{hauteur}"/>
      <quality shadowsize="4096"/><map znear="0.002" zfar="40"/><headlight ambient="0.35 0.35 0.35" diffuse="0.5 0.5 0.5"/></visual>
      <asset>{''.join(assets)}
        <texture name="sol" type="2d" builtin="flat" rgb1="{fond[0]} {fond[1]} {fond[2]}" width="8" height="8"/>
        <material name="sol" texture="sol"/></asset>
      <worldbody>
        <light pos="{c[0] + span} {c[1] - span} {c[2] + 2 * span}" dir="-1 1 -2" castshadow="true" diffuse="0.7 0.7 0.7"/>
        <geom type="plane" size="2 2 0.01" pos="0 0 {zmin - 0.0005}" material="sol" contype="0" conaffinity="0"/>
        {''.join(geoms)}
      </worldbody></mujoco>"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    r = mujoco.Renderer(model, hauteur, largeur)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = c
    cam.distance = distance or span * 1.9
    cam.azimuth, cam.elevation = azimut, elevation
    r.update_scene(data, camera=cam)
    Image.fromarray(r.render()).save(fichier)
    r.close()
    shutil.rmtree(tmp, ignore_errors=True)


def scene_presentoir(corps, info, porte_cles, largeur=170.0, hauteur=190.0, e=4.0, crochet_l=16.0, n=3,
                     coul_base="#f2efe8", coul_relief="#1d1d1f", coul_cles=("#e4572e", "#17bebb", "#ffc914")):
    """Items du presentoir assemble (panneau incline dans le pied, porte-cles pendus)."""
    inc = info["inclinaison_deg"]
    T = trimesh.transformations.translation_matrix([0, 6.0, 22.0 - 12.0]) @ _T_rot_x(inc) \
        @ trimesh.transformations.translation_matrix([0, hauteur / 2 + 12.0, 0])
    items = [(_mesh(corps["pied"]["base"]), coul_base)]
    for part, c in ((corps["panneau"]["base"], coul_base), (corps["panneau"]["relief"], coul_relief)):
        m = _mesh(part); m.apply_transform(T); items.append((m, c))
    pas = largeur / n
    y_cr = hauteur / 2 - 62.0
    for i, (pc, col) in enumerate(zip(porte_cles, coul_cles)):
        x = -largeur / 2 + pas * (i + 0.5)
        tip = T @ np.array([x, y_cr, e + crochet_l * 0.55, 1.0])
        normal = T[:3, :3] @ np.array([0, 0, 1.0])
        for part, c in ((pc["base"], col), (pc["relief"], coul_relief)):
            m = _mesh(part)
            # pendu : axe long vertical, anneau en haut, face texte vers l'avant (normale du panneau)
            R = trimesh.transformations.rotation_matrix(math.radians(-90), [0, 0, 1])    # anneau vers le haut une fois pendu
            R = trimesh.transformations.rotation_matrix(math.radians(90 + 0), [1, 0, 0]) @ R
            m.apply_transform(R)
            items.append((m, c))
        # place le groupe (base + relief) : anneau sous la pointe du crochet, legerement devant le panneau
        grp = items[-2:]
        top = max(g[0].bounds[1][2] for g in grp)
        cx = np.mean([g[0].centroid[0] for g in grp])
        ymin = min(g[0].bounds[0][1] for g in grp)
        for g in grp:
            ymid = np.mean([(g_[0].bounds[0][1] + g_[0].bounds[1][1]) / 2 for g_ in grp])
            g[0].apply_translation([tip[0] - cx, tip[1] - ymid, tip[2] - top + 3.0])
        # le porte-cle repose a plat contre le panneau incline : rotation autour du crochet
        piv = np.array([tip[0], tip[1], tip[2]])
        for sgn in (1.0, -1.0):
            Rk = trimesh.transformations.rotation_matrix(sgn * math.radians(90.0 - inc), [1, 0, 0], piv)
            test = grp[0][0].copy(); test.apply_transform(Rk)
            # garde le sens qui ramene le bas du porte-cle vers la face (et non dans le panneau)
            low = test.vertices[test.vertices[:, 2].argmin()]
            face_pt = T @ np.array([0, 0, e, 1.0])
            if np.dot(low - face_pt[:3], normal) > 0:
                for g in grp:
                    g[0].apply_transform(Rk)
                break
    return items
