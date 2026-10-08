"""LOGO SHWork (SHW 3DLAB) : vectorisation de l'image de reference -> polygones 2D (shapely), pour graver /
mettre en relief le logo sur n'importe quelle surface, et images pour l'interface.

partie = "mot" (SHWork orange) | "slogan" (SUPER HIGH WORK) | "tout"
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parents[2]
SRC = ICI / "data" / "logo_shwork_src.png"


@lru_cache(maxsize=8)
def _poly(partie="mot", sur=6):
    import cv2
    from PIL import Image
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    im = np.array(Image.open(SRC).convert("RGB")).astype(np.float32)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    orange = np.clip(((r - g) - 60) / 60, 0, 1) * (r > 150)                       # couverture douce (anti-crenelage)
    gris = np.clip((150 - (r + g + b) / 3) / 60, 0, 1) * (np.abs(r - b) < 40)
    a = {"mot": orange, "slogan": gris, "tout": np.maximum(orange, gris)}[partie]
    a = cv2.resize(a, None, fx=sur, fy=sur, interpolation=cv2.INTER_CUBIC)      # sur-echantillonnage
    a = cv2.GaussianBlur(a, (0, 0), sur * 0.45)
    m = (a > 0.5).astype(np.uint8) * 255
    cs, hi = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    polys = []
    for i, c in enumerate(cs):
        if hi[0][i][3] != -1 or len(c) < 8:
            continue
        ext = c[:, 0, :].astype(float)
        trous = []
        j = hi[0][i][2]
        while j != -1:
            if len(cs[j]) >= 8:
                trous.append(cs[j][:, 0, :].astype(float))
            j = hi[0][j][0]
        p = Polygon(ext, trous).buffer(0)
        if p.area > (sur * 3) ** 2:
            polys.append(p)
    u = unary_union(polys).simplify(sur * 0.25)
    from shapely import affinity
    u = affinity.scale(u, 1, -1, origin=(0, 0))                                  # image (y vers le bas) -> y vers le haut
    bx = u.bounds
    return affinity.translate(u, -(bx[0] + bx[2]) / 2, -(bx[1] + bx[3]) / 2)


def logo_polygone(largeur=40.0, partie="mot"):
    """Logo vectorise, centre en (0, 0), a la largeur demandee (mm)."""
    from shapely import affinity
    u = _poly(partie)
    bx = u.bounds
    k = largeur / (bx[2] - bx[0])
    return affinity.scale(u, k, k, origin=(0, 0))


def logo_3d(largeur=40.0, epaisseur=1.2, partie="mot", socle=0.0):
    """Logo en relief (extrusion), pose sur z = 0 ; socle optionnel (plaque arrondie dessous)."""
    import manifold3d as mf
    from atelier.noyau.c3d import section, vers_trimesh
    p = logo_polygone(largeur, partie)
    s = mf.Manifold.extrude(section(p), epaisseur)
    if socle > 0:
        bx = p.buffer(2.5, join_style=1).envelope.buffer(2.0, join_style=1)
        s = s.translate((0, 0, socle)) + mf.Manifold.extrude(section(bx), socle)
    return vers_trimesh(s)


def monogramme_polygone(largeur=20.0):
    """Monogramme SHW (le logo coupe apres le W, sans 'ork') : pour l'icone et les petites gravures."""
    from shapely import affinity
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    q = logo_polygone(1000.0, "mot")
    x0, y0, x1, y1 = q.bounds
    xc, d = x0 + 0.628 * 1000, (y1 - y0) * 0.42
    m = q.intersection(Polygon([(x0 - 50, y0 - 5), (xc - d, y0 - 5), (xc, y1 + 5), (x0 - 50, y1 + 5)]))
    parts = sorted(getattr(m, "geoms", [m]), key=lambda p: -p.area)
    m = unary_union([p for p in parts if p.area > 0.08 * parts[0].area])
    b = m.bounds
    m = affinity.translate(m, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
    k = largeur / (b[2] - b[0])
    return affinity.scale(m, k, k, origin=(0, 0))
