"""RANGEMENT DES PIECES SUR LE PLATEAU par EMPREINTES REELLES (pas des rectangles).

Chaque piece est projetee sur le plateau (silhouette exacte, trous compris), rasterisee a 0.5 mm. On place les
pieces de la plus grande a la plus petite ; pour chacune, 4 rotations sont essayees et la correlation (FFT)
avec l'occupation du plateau donne d'un coup TOUTES les positions libres : on garde la plus en bas a gauche.
Resultat : les petites pieces se glissent dans les creux et dans les trous des grandes (anneau, cadre...).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.signal import fftconvolve

RES = 0.5          # mm par pixel


def empreinte(m, rot_deg=0.0, res=RES):
    """Masque booleen de la silhouette (projection XY de tous les triangles), origine = coin bas-gauche."""
    v = m.vertices[:, :2].copy()
    if rot_deg:
        a = math.radians(rot_deg)
        v = v @ np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
    lo = v.min(0)
    v = (v - lo) / res
    w, h = int(math.ceil(v[:, 0].max())) + 2, int(math.ceil(v[:, 1].max())) + 2
    im = Image.new("1", (w, h), 0)
    d = ImageDraw.Draw(im)
    tri = v[m.faces]
    # seulement les triangles non verticaux (les verticaux ne changent pas la silhouette)
    u, w_ = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    aire = np.abs(u[:, 0] * w_[:, 1] - u[:, 1] * w_[:, 0])
    for t in tri[aire > 1e-6]:
        d.polygon([tuple(p) for p in t], fill=1)
    return np.array(im, dtype=bool), lo


def ranger(meshes, W=195.0, H=195.0, ecart=3.0, rotations=(0, 90, 180, 270), res=RES, max_plateaux=20):
    """-> [(plateau, rot_deg, dx, dy)] par piece : appliquer rotation Z (autour de l'origine) puis translation."""
    nx, ny = int(W / res), int(H / res)
    dil = max(1, int(round(ecart / 2 / res)))
    plateaux = []                                     # grilles d'occupation (deja dilatees de ecart/2)
    ordre = sorted(range(len(meshes)), key=lambda i: -float(np.prod(meshes[i].extents[:2])))
    poses = [None] * len(meshes)
    cache = {}
    for i in ordre:
        m = meshes[i]
        # une seule rasterisation par piece (cache pour les pieces identiques) ; rotations de 90 deg = rot90 exact
        cle = (len(m.vertices), round(float(m.volume), 2))
        if cle not in cache:
            msk0, lo0 = empreinte(m, 0, res)
            cache[cle] = (msk0, lo0, ndimage.binary_dilation(msk0, iterations=dil))
        msk0, lo0, mskd0 = cache[cle]
        essais = []
        for r in rotations:
            q = int(round(r / 90)) % 4
            mskd = np.rot90(mskd0, k=q)                    # rot90 tourne de +90 deg (repere image : y vers le bas) -> on gere l'origine ci-dessous
            msk = np.rot90(msk0, k=q)
            # coin bas-gauche de la piece tournee (dans le repere de la piece) pour retrouver la translation
            v = m.vertices[:, :2]
            a = math.radians(-90 * q)
            vr = v @ np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
            essais.append((-90 * q, msk, mskd, vr.min(0)))
        place = False
        for k in range(len(plateaux) + 1):
            if k == len(plateaux):
                if len(plateaux) >= max_plateaux:
                    break
                plateaux.append(np.zeros((ny, nx), dtype=bool))
            occ = plateaux[k]
            meilleur = None
            for r, msk, mskd, lo in essais:
                h, w = mskd.shape
                if h > ny or w > nx:
                    continue
                if not occ.any():
                    cand = (0, 0)
                else:
                    coll = fftconvolve(occ.astype(np.float32), mskd[::-1, ::-1].astype(np.float32), mode="valid")
                    libres = np.argwhere(coll < 0.5)
                    if not len(libres):
                        continue
                    # en bas a gauche (y puis x), avec preference pour les positions compactes
                    j = np.lexsort((libres[:, 1], libres[:, 0]))[0]
                    cand = tuple(libres[j])
                score = (cand[0] + h) * 10000 + cand[1] + w
                if meilleur is None or score < meilleur[0]:
                    meilleur = (score, r, cand, mskd, lo)
            if meilleur:
                _, r, (py, px), mskd, lo = meilleur
                h, w = mskd.shape
                occ[py:py + h, px:px + w] |= mskd
                # position de l'origine de la piece : coin du masque (px, py) correspond a lo apres rotation
                poses[i] = (k, r, px * res - lo[0] + dil * 0, py * res - lo[1])
                place = True
                break
        if not place:
            raise ValueError(f"piece {i} trop grande pour le plateau {W:g} x {H:g}")
    return poses, len(plateaux)


def appliquer(m, rot, dx, dy):
    import trimesh
    m = m.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(rot), [0, 0, 1]))
    m.apply_translation([dx, dy, -m.bounds[0][2]])
    return m
