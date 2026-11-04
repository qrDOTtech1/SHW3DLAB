"""FIGURINE PHOTO : une photo de visage -> une petite figurine imprimable a l'effigie de la personne, sans intervention.

1. Le visage (478 points 3D) vient de MediaPipe. MediaPipe exige numpy < 2 : il tourne dans un petit environnement
   a part, cree tout seul a la premiere utilisation (sortie/venv_visage), resultat garde en cache par image.
2. Le corps entier est un champ volumique (crane, visage, barbe, cheveux, oreilles, cou, buste en veste), lisse puis
   converti en maillage ferme d'un seul tenant : pas de trou, pas d'assemblage.
3. Barbe et cheveux sont lus dans la photo (zones sombres autour des points du visage), reglables a la main.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from skimage import measure

ICI = Path(__file__).resolve().parents[2]
VENV = ICI / "sortie" / "venv_visage"
CACHE = ICI / "sortie" / "figurines"
NOWIN = 0x08000000 if sys.platform == "win32" else 0

SCRIPT = r'''
import json, sys, numpy as np, mediapipe as mp
from PIL import Image
im = np.array(Image.open(sys.argv[1]).convert("RGB"))
with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=True, max_num_faces=1, min_detection_confidence=0.3) as fm:
    r = fm.process(im)
if not r.multi_face_landmarks:
    print(json.dumps({"erreur": "aucun visage"})); sys.exit(0)
h, w = im.shape[:2]
L = [[p.x * w, p.y * h, p.z * w] for p in r.multi_face_landmarks[0].landmark]
print(json.dumps({"points": L}))
'''


def _python_visage() -> str:
    exe = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not exe.exists():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True, creationflags=NOWIN)
    if subprocess.run([str(exe), "-c", "import mediapipe"], capture_output=True, creationflags=NOWIN).returncode:
        subprocess.run([str(exe), "-m", "pip", "install", "-q", "mediapipe==0.10.14"], check=True, creationflags=NOWIN)
    return str(exe)


def points_visage(image: Path) -> np.ndarray:
    CACHE.mkdir(parents=True, exist_ok=True)
    cle = hashlib.sha1(Path(image).read_bytes()).hexdigest()[:16]
    f = CACHE / f"{cle}.json"
    if not f.exists():
        r = subprocess.run([_python_visage(), "-c", SCRIPT, str(image)], capture_output=True, text=True, creationflags=NOWIN)
        d = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"erreur": r.stderr[-300:]}
        if "erreur" in d:
            raise ValueError("Pas de visage detecte : prends une photo nette, visage bien visible. " + d["erreur"])
        f.write_text(json.dumps(d))
    return np.array(json.loads(f.read_text())["points"])


def _repere(L):
    """Repere de la tete : x = vers sa gauche, y = haut, z = vers l'avant ; hauteur du visage (front-menton) = 1."""
    ex = L[263] - L[33]; ex /= np.linalg.norm(ex)
    ey = L[10] - L[152]; ey -= ey.dot(ex) * ex; ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    if ez.dot(L[1] - (L[33] + L[263]) / 2) < 0:
        ez = -ez
    o = (L[33] + L[263]) / 2
    ech = np.linalg.norm(L[10] - L[152])
    return (L - o) @ np.c_[ex, ey, ez] / ech


def _taux_sombre(image, L, Q):
    """Barbe : un point du bas du visage est-il nettement plus sombre que le front ?"""
    from PIL import Image
    im = np.asarray(Image.open(image).convert("L"), float)
    im = ndimage.gaussian_filter(im, im.shape[1] / 400)
    lum = im[np.clip(L[:, 1].astype(int), 0, im.shape[0] - 1), np.clip(L[:, 0].astype(int), 0, im.shape[1] - 1)]
    peau = np.percentile(lum[Q[:, 1] > 0.05], 70)
    return lum < 0.62 * peau


def _lisse_max(a, b, k=0.03):
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0, 1)
    return b + (a - b) * h + k * h * (1 - h)


def figurine(image: Path, p: dict):
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    L = points_visage(image)
    Q = _repere(L)
    relief, tete_x = g("relief", 1.35), g("grosse_tete", 1.6)
    Q = Q * [1, 1, relief]
    bouche_y = Q[13, 1]

    # ---- grille commune (unites : hauteur du visage = 1)
    pas = 1.0 / g("detail", 62)
    xs = np.arange(-1.75, 1.75 + pas, pas)
    ys = np.arange(-3.05, 1.10 + pas, pas)
    zs = np.arange(-1.15, 1.05 + pas, pas)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij", sparse=False)

    # ---- visage : surface issue de la photo, symetrisee (le cote cache est deduit du cote visible)
    pts2 = Q[:, :2]
    f_lin = LinearNDInterpolator(pts2, Q[:, 2]); f_nn = NearestNDInterpolator(pts2, Q[:, 2])
    def z_face(x, y):
        v = f_lin(x, y); return np.where(np.isnan(v), f_nn(x, y), v)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    sym = g("symetrie", 1)
    zf = z_face(gx, gy)
    if sym:
        zf = 0.5 * (zf + z_face(-gx, gy))
    dedans = ~np.isnan(f_lin(gx, gy))
    if sym:
        dedans = dedans | ~np.isnan(f_lin(-gx, gy))
    zf = ndimage.gaussian_filter(zf, 0.8)
    # le bord du visage rejoint la surface du crane en douceur (pas de sillon)
    cy = float(Q[10, 1]) - 0.42
    larg = max(0.52, float(np.percentile(np.abs(Q[:, 0]), 99)))
    hc = -0.32 + 0.74 * np.sqrt(np.clip(1 - (gx / larg) ** 2 - ((gy - cy) / 0.70) ** 2, 0, 1))
    w_ = np.clip(ndimage.distance_transform_edt(dedans) * pas / 0.16, 0, 1)
    w_ = w_ * w_ * (3 - 2 * w_)
    zf = w_ * zf + (1 - w_) * hc
    # a petite echelle les traits disparaissent : orbites, yeux, sourcils et levres sont sculptes (position lue sur la photo)
    gau = lambda cx, cy, sx, sy: np.exp(-((gx - cx) / sx) ** 2 - ((gy - cy) / sy) ** 2)
    ax_oeil = 0.5 * (abs(Q[468, 0]) + abs(Q[473, 0])); y_oeil = 0.5 * (Q[468, 1] + Q[473, 1])
    ax_sou = 0.5 * (abs(Q[105, 0]) + abs(Q[334, 0])); y_sou = 0.5 * (Q[105, 1] + Q[334, 1])
    l_bou = 0.5 * (abs(Q[61, 0]) + abs(Q[291, 0]))
    for s_ in (-1, 1):
        zf = zf - 0.10 * gau(s_ * ax_oeil, y_oeil, 0.115, 0.055) + 0.065 * gau(s_ * ax_oeil, y_oeil, 0.05, 0.038)
        zf = zf + 0.06 * gau(s_ * ax_sou, y_sou + 0.015, 0.13, 0.024)
    zf = zf - 0.03 * gau(0, Q[13, 1], l_bou, 0.013) + 0.018 * gau(0, Q[13, 1] + 0.035, l_bou * 0.8, 0.02) + 0.022 * gau(0, Q[14, 1] - 0.035, l_bou * 0.75, 0.024)
    masque = ndimage.gaussian_filter(dedans.astype(float), 1.5)
    face = (zf[:, :, None] - Z)
    face = np.where(masque[:, :, None] > 0.5, np.minimum(face, Z + 0.25), -1.0)

    # ---- crane + machoire
    cy = float(Q[10, 1]) - 0.42
    larg = max(0.52, float(np.percentile(np.abs(Q[:, 0]), 99)) * 1.0)
    def ell(c, r):
        return 1 - np.sqrt(((X - c[0]) / r[0]) ** 2 + ((Y - c[1]) / r[1]) ** 2 + ((Z - c[2]) / r[2]) ** 2)
    crane = ell((0, cy, -0.32), (larg, 0.70, 0.74)) * 0.65
    machoire = ell((0, float(Q[152, 1]) + 0.32, -0.18), (larg * 0.86, 0.42, 0.52)) * 0.45
    # le crane s'arrete derriere la surface du visage : les traits de la photo restent a l'air libre
    derriere = np.where(masque[:, :, None] > 0.5, zf[:, :, None] - Z, 9.0)
    crane, machoire = np.minimum(crane, derriere), np.minimum(machoire, derriere)
    tete = _lisse_max(_lisse_max(crane, machoire), face, 0.03)

    # ---- oreilles
    for s in (-1, 1):
        tete = _lisse_max(tete, ell((s * (larg + 0.01), float(Q[1, 1]) + 0.02, -0.35), (0.07, 0.17, 0.11)) * 0.12, 0.03)

    # ---- texture frisee commune (bruit lisse fixe : le meme maillage a chaque calcul)
    rng = np.random.default_rng(7)
    bruit = ndimage.gaussian_filter(rng.standard_normal(X.shape), 1.15)
    bruit /= bruit.std()

    # ---- cheveux : coque epaisse au-dessus de la ligne du front, degrade sur les cotes
    if g("cheveux", 1):
        ligne = float(Q[10, 1]) - 0.06
        recul = np.clip((0.15 - Z) / 0.85, 0, 1)            # la ligne descend vers l'arriere et sur les tempes
        zone = np.clip((Y - (ligne - 0.62 * recul - 0.10 * np.clip(np.abs(X) / larg, 0, 1) ** 2)) / 0.13, 0, 1)
        zone = np.minimum(zone, np.clip((np.abs(X) < larg * 2) * 1.0, 0, 1))
        ep = g("volume_cheveux", 0.11) * zone * (1 + 0.2 * bruit)
        tete = tete + ep                                   # epaisseur posee sur la vraie surface : pas de casque

    # ---- barbe : lue dans la photo, epaissit le bas du visage
    bas = Q[:, 1] < bouche_y + 0.14
    sombres = _taux_sombre(image, L, Q) & bas
    if g("barbe", 1) and sombres.sum() > 12:
        B = np.zeros(gx.shape)
        for q in Q[sombres]:
            for sg in ((1, -1) if sym else (1,)):
                i, j = int((sg * q[0] - xs[0]) / pas), int((q[1] - ys[0]) / pas)
                if 0 <= i < B.shape[0] and 0 <= j < B.shape[1]:
                    B[i, j] = 1
        B = np.clip(ndimage.gaussian_filter(B, 0.075 / pas) * 40, 0, 1)
        lb = np.abs(gy - (Q[13, 1] - 0.01)) < 0.035                # les levres restent libres
        lb &= np.abs(gx) < 0.17
        B[lb] = 0
        B = ndimage.gaussian_filter(B, 1.0)
        tete = tete + g("volume_barbe", 0.075) * B[:, :, None] * (1 + 0.22 * bruit)

    # ---- corps a l'echelle reduite : plus la tete est grosse, plus le buste est petit (style figurine)
    e = 1.6 / tete_x
    menton = float(Q[152, 1])
    y_ep = menton - 0.42 * e
    H_b = 0.95 * e
    cou = 0.29 - np.hypot(X, (Z + 0.2) / 0.95)
    cou = np.minimum(cou, menton + 0.3 - Y)
    cou = np.minimum(cou, Y - (y_ep - 0.3))
    t = np.clip((y_ep - Y) / H_b, 0, 1)                      # 0 = epaules, 1 = bas du buste
    epaule = np.clip((y_ep + 0.16 * e - Y) / (0.30 * e), 0, 1) ** 0.5
    lx = (0.98 * e - 0.10 * t) * (0.32 + 0.68 * epaule)
    lz = (0.44 * e) * (0.55 + 0.45 * epaule)
    Zb = Z + 0.2
    buste = (1 - np.sqrt((X / lx) ** 2 + (Zb / lz) ** 2)) * 0.5
    socle_y = y_ep - H_b
    buste = np.minimum(np.minimum(buste, Y - socle_y), y_ep + 0.16 * e - Y)
    # devant du buste : chemise en retrait dans le V, revers de veste en relief, col, boutons (seulement sur l'avant)
    devant = np.clip(Zb / 0.08, 0, 1)
    v = np.abs(X) - np.clip((y_ep + 0.10 * e - Y) * 0.36, 0, 0.30 * e)
    dans_v = np.clip(-v / 0.02, 0, 1) * (Y < y_ep + 0.12 * e) * (Y > y_ep - 0.62 * e)
    buste = buste - 0.018 * dans_v * devant
    revers = np.clip(1 - np.abs(v - 0.055 * e) / (0.055 * e), 0, 1) * (Y > y_ep - 0.66 * e) * (Y < y_ep + 0.14 * e)
    buste = buste + 0.014 * revers * devant
    croisement = np.clip(1 - np.abs(X) / 0.012, 0, 1) * (Y <= y_ep - 0.62 * e)            # fermeture de la veste
    buste = buste - 0.006 * croisement * devant
    col = np.clip(1 - np.abs(np.abs(X) - 0.16) / 0.12, 0, 1) * np.clip(1 - np.abs(Y - (y_ep + 0.09 * e)) / 0.10, 0, 1)
    corps = _lisse_max(cou, buste, 0.05)
    corps = np.maximum(corps, np.where(Zb > -0.02, 0.05 * col - 0.02 + np.minimum(cou + 0.09, 0), -1))

    champ = _lisse_max(tete, corps, 0.04)
    champ = ndimage.gaussian_filter(champ, 0.55)
    champ[0], champ[-1] = -1, -1
    champ[:, 0], champ[:, -1] = -1, -1
    champ[:, :, 0], champ[:, :, -1] = -1, -1
    v, fa, *_ = measure.marching_cubes(champ, 0.0, spacing=(pas, pas, pas))
    v += [xs[0], ys[0], zs[0]]
    m = trimesh.Trimesh(np.c_[v[:, 0], -v[:, 2], v[:, 1]], fa[:, ::-1], process=True)   # Z = haut, la figurine regarde vers -Y
    if m.volume < 0:
        m.invert()
    morceaux = m.split(only_watertight=False)
    m = max(morceaux, key=lambda x: abs(x.volume)) if len(morceaux) > 1 else m

    # ---- echelle + socle grave
    H = g("hauteur", 90.0)
    socle_h = g("socle", 6.0)
    ech = (H - socle_h) / m.extents[2]
    m.apply_scale(ech)
    m.apply_translation([-m.bounding_box.centroid[0], -m.bounding_box.centroid[1], socle_h - 0.6 - m.bounds[0][2]])

    import manifold3d as mf
    from atelier.noyau.c3d import vers_manifold, vers_trimesh, section
    Rs = max(m.extents[0], m.extents[1]) * 0.56 + 2
    socle = mf.Manifold.cylinder(socle_h, Rs, Rs - 0.8, 128)
    corps_m = vers_manifold(m)
    if corps_m.status() != mf.Error.NoError or corps_m.volume() <= 0:
        corps_m = vers_manifold(trimesh.convex.convex_hull(m)) if False else corps_m
    final = corps_m + socle
    nom = str(p.get("nom_socle") or "").strip()
    if nom:
        from atelier.produits.porte_cles import Style, glyphes
        from shapely.ops import unary_union
        from shapely import affinity
        t_ = unary_union(glyphes(nom, Style(police="gabriola", hauteur=10.0)))
        b = t_.bounds
        k_ = min((socle_h - 2) / (b[3] - b[1]), Rs * 1.1 / (b[2] - b[0]))
        t_ = affinity.scale(affinity.translate(t_, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2), k_, k_, origin=(0, 0))
        t_ = affinity.scale(t_, -1, 1, origin=(0, 0))
        pr = mf.Manifold.extrude(section(t_), 3.0).transform(np.array([[-1, 0, 0, 0], [0, 0, 1, -Rs - 1.0 + 0.5], [0, 1, 0, socle_h / 2]], float))
        final = final - pr
    res = vers_trimesh(final)
    return [res], {"noms": ["figurine"], "hauteur_mm": round(float(res.extents[2]), 1), "points_visage": len(L),
                   "barbe_detectee": int(sombres.sum()), "etanche": bool(res.is_watertight),
                   "volume_cm3": round(float(res.volume) / 1000, 1)}
