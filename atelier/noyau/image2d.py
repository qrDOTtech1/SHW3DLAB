"""IMAGE -> 3D, etape 1 : vectorisation d'un logo / dessin en polygones 2D imprimables.

image (PNG/JPG, transparence geree) -> niveaux de gris -> seuil (Otsu auto ou manuel) -> contours avec
TROUS (hierarchie OpenCV) -> polygones shapely lisses, mis a l'echelle en mm. Les details plus fins que la
buse sont elimines (ouverture morphologique a l'echelle d'impression) : ce qui reste s'imprime vraiment.
Le resultat est un polygone comme celui d'un prenom : il passe dans tous les produits (incrustation,
relief, changement de filament).
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


def _charger(data: bytes):
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        a = np.array(im)[:, :, 3].astype(np.float32) / 255.0
        g = np.array(im.convert("L")).astype(np.float32)
        g = g * a + 255.0 * (1 - a)                 # transparent = fond blanc
        return g.astype(np.uint8), True
    return np.array(im.convert("L")), False


def masque(data: bytes, seuil: int | None = None, inverser: bool | None = None, px_max: int = 900):
    """Masque binaire (True = matiere du motif). Inversion auto : le fond est la couleur majoritaire du bord."""
    g, _ = _charger(data)
    h, w = g.shape
    k = px_max / max(h, w)
    if k < 1:
        g = cv2.resize(g, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    if seuil is None:
        seuil, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = g < seuil                                   # sombre = motif
    if inverser is None:
        bord = np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]])
        inverser = bord.mean() > 0.5                # bord majoritairement "motif" -> c'est le fond
    if inverser:
        m = ~m
    return m, int(seuil), bool(inverser)


def polygones(m: np.ndarray, taille_mm: float, detail_min_mm: float = 0.5, lissage_mm: float = 0.12):
    """Masque -> MultiPolygon en mm (plus grande dimension = taille_mm), centre sur (0, 0)."""
    ys, xs = np.nonzero(m)
    if not len(xs):
        raise ValueError("image vide : aucun motif detecte (essaie d'inverser ou de changer le seuil)")
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    m = m[y0:y1, x0:x1]
    mm_px = taille_mm / max(m.shape)
    # ouverture morphologique : supprime ce qui est plus fin que detail_min_mm (non imprimable)
    r = max(1, int(round(detail_min_mm / mm_px / 2)))
    u8 = (m * 255).astype(np.uint8)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    u8 = cv2.morphologyEx(u8, cv2.MORPH_OPEN, ker)
    u8 = cv2.copyMakeBorder(u8, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    cs, hier = cv2.findContours(u8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        raise ValueError("aucun contour exploitable apres nettoyage (motif trop fin pour cette taille)")
    hier = hier[0]
    polys = []
    for i, c in enumerate(cs):
        if hier[i][3] != -1 or len(c) < 3:          # on part des contours exterieurs
            continue
        ext = c[:, 0, :].astype(float)
        trous = []
        k = hier[i][2]
        while k != -1:
            if len(cs[k]) >= 3:
                trous.append(cs[k][:, 0, :].astype(float))
            k = hier[k][0]
        p = Polygon(ext, trous).buffer(0)
        if p.area > 4:
            polys.append(p)
    u = unary_union(polys)
    # pixels -> mm (Y vers le haut), centre
    u = affinity.scale(u, mm_px, -mm_px, origin=(0, 0))
    b = u.bounds
    u = affinity.translate(u, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
    u = u.simplify(lissage_mm / 2).buffer(lissage_mm, join_style=1).buffer(-lissage_mm, join_style=1)
    u = u.buffer(0)
    parts = [g for g in (u.geoms if isinstance(u, MultiPolygon) else [u]) if g.area > (detail_min_mm ** 2)]
    return MultiPolygon(parts) if len(parts) > 1 else parts[0]


def image_vers_polygone(data: bytes, taille_mm: float, seuil=None, inverser=None, detail_min_mm=0.5):
    m, s, inv = masque(data, seuil, inverser)
    p = polygones(m, taille_mm, detail_min_mm)
    n = len(p.geoms) if isinstance(p, MultiPolygon) else 1
    return p, {"seuil": s, "inverse": inv, "morceaux": n, "dimensions_mm": [round(p.bounds[2] - p.bounds[0], 1),
                                                                            round(p.bounds[3] - p.bounds[1], 1)]}


def apercu_png(poly, px=360, fond=(30, 33, 40), coul=(240, 240, 244), cercle_mm: float | None = None):
    """Image PNG du polygone (pour l'apercu dans l'interface)."""
    b = poly.bounds
    ext = max(b[2] - b[0], b[3] - b[1], cercle_mm or 0) * 1.1
    k = px / ext
    img = np.zeros((px, px, 3), np.uint8)
    img[:] = fond

    def pts(coords):
        return np.array([[(x * k + px / 2), (px / 2 - y * k)] for x, y in coords], np.int32)
    if cercle_mm:
        cv2.circle(img, (px // 2, px // 2), int(cercle_mm / 2 * k), (90, 96, 110), 2, cv2.LINE_AA)
    for g in (poly.geoms if isinstance(poly, MultiPolygon) else [poly]):
        cv2.fillPoly(img, [pts(g.exterior.coords)], coul, cv2.LINE_AA)
        for h in g.interiors:
            cv2.fillPoly(img, [pts(h.coords)], fond, cv2.LINE_AA)
    ok, buf = cv2.imencode(".png", img[:, :, ::-1])
    return buf.tobytes()
