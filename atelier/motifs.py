"""MOTIFS de surface (meme formules que web/effets.js, vectorisees numpy) + AJOURAGE traversant.

f(u, v, p) -> hauteur 0..1 ; (u, v) en "cellules" (deja divises par la taille). Utilises :
  * effet_surface(...) : relief deplace le long des normales (keycaps, lots, serveur) ;
  * ajourer(...)       : le motif devient des TROUS qui traversent la paroi (diffuseurs RGB, lampes, grilles).
"""
from __future__ import annotations

import math

import numpy as np
import trimesh


def _fract(x):
    return x - np.floor(x)


def _lisse(a, b, x):
    t = np.clip((x - a) / (b - a + 1e-12), 0, 1)
    return t * t * (3 - 2 * t)


def _tri(x):
    return 1 - np.abs(_fract(x) * 2 - 1)


def _hash2(x, y):
    h = np.sin(x * 127.1 + y * 311.7) * 43758.5453
    return h - np.floor(h)


def _bruit(x, y):
    xi, yi = np.floor(x), np.floor(y)
    xf, yf = x - xi, y - yi
    u, v = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)
    a, b, c, d = _hash2(xi, yi), _hash2(xi + 1, yi), _hash2(xi, yi + 1), _hash2(xi + 1, yi + 1)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def _fbm(x, y, o=4):
    s, a, f = 0.0, 0.5, 1.0
    for _ in range(o):
        s = s + a * _bruit(x * f, y * f)
        f *= 2.03
        a *= 0.5
    return s / (1 - 0.5 ** o)


def _voronoi(x, y, alea):
    xi, yi = np.floor(x), np.floor(y)
    f1 = np.full(x.shape, 9.0)
    f2 = np.full(x.shape, 9.0)
    idv = np.zeros(x.shape)
    for j in (-1, 0, 1):
        for i in (-1, 0, 1):
            cx, cy = xi + i, yi + j
            px = cx + 0.5 + (_hash2(cx, cy) - 0.5) * alea
            py = cy + 0.5 + (_hash2(cy + 17.3, cx - 4.1) - 0.5) * alea
            d = np.hypot(x - px, y - py)
            plus_proche = d < f1
            f2 = np.where(plus_proche, f1, np.minimum(f2, d))
            idv = np.where(plus_proche, _hash2(cx * 1.7, cy * 3.1), idv)
            f1 = np.minimum(f1, d)
    return f1, f2, idv


def _hexa(x, y):
    sx, sy = 1.0, 1.7320508
    ax, ay = np.mod(x, sx) - sx / 2, np.mod(y, sy) - sy / 2
    bx, by = np.mod(x - sx / 2, sx) - sx / 2, np.mod(y - sy / 2, sy) - sy / 2
    pa = ax * ax + ay * ay < bx * bx + by * by
    gx, gy = np.abs(np.where(pa, ax, bx)), np.abs(np.where(pa, ay, by))
    return np.maximum(gx * 0.5 + gy * 0.8660254, gx)


def _ecailles(u, v):
    H, R = 0.5, 0.62
    r = np.floor(v / H)
    out = np.zeros(u.shape)
    fait = np.zeros(u.shape, bool)
    for dr in (2, 1, 0, -1):
        rr = r + dr
        cy = rr * H
        off = np.mod(rr, 2) * 0.5
        cx = np.floor(u + off) + 0.5 - off
        for dc in (-1, 0, 1):
            d = np.hypot(u - (cx + dc), v - cy)
            ok = (~fait) & (v <= cy) & (d < R)
            t = d / R
            out = np.where(ok, np.sqrt(np.clip(1 - t * t, 0, 1)) * 0.6 + 0.4 * (1 - (cy - v) / R), out)
            fait |= ok
    return out


def _motif(nom, u, v, p):
    tr, nt, al = p["trait"], p["nettete"], p["alea"]
    fl = max(0.01, 0.06 / max(nt, 0.2))
    if nom == "alveoles":
        return _lisse(0.5 - tr - fl, 0.5 - tr + fl, _hexa(u, v))
    if nom == "hexa_bombe":
        return np.clip(1 - _hexa(u, v) * 2, 0, 1) ** 0.6
    if nom == "gaufre":
        g = np.maximum(np.abs(_fract(u) - 0.5), np.abs(_fract(v) - 0.5))
        return _lisse(0.5 - tr - fl, 0.5 - tr + fl, g)
    if nom == "triangles":
        d = np.maximum.reduce([np.abs(_fract(t) - 0.5) for t in (u, u * 0.5 + v * 0.8660254, -u * 0.5 + v * 0.8660254)])
        return 1 - _lisse(tr - fl, tr + fl, 0.5 - d)
    if nom == "voronoi":
        a, b, _ = _voronoi(u, v, al)
        return 1 - _lisse(tr * 0.6 - fl, tr * 0.6 + fl, b - a)
    if nom == "pierre":
        a, b, _ = _voronoi(u, v, al)
        return np.clip((b - a) * 2.2, 0, 1) ** 0.55
    if nom == "mosaique":
        a, b, i = _voronoi(u, v, al)
        return (0.35 + 0.65 * i) * _lisse(0, tr + fl, b - a)
    if nom == "ecailles":
        return _ecailles(u, v)
    if nom == "briques":
        r = np.floor(v * 2)
        x, y = _fract(u + np.mod(r, 2) * 0.5), _fract(v * 2)
        g = np.minimum(np.minimum(x, 1 - x) * 2, np.minimum(y, 1 - y))
        return _lisse(tr * 0.5 - fl, tr * 0.5 + fl, g)
    if nom == "diamant":
        return (1 - np.maximum(np.abs(_fract(u + v) - 0.5), np.abs(_fract(u - v) - 0.5)) * 2) ** nt
    if nom == "rainures":
        return _tri(u) ** nt
    if nom == "cannelures":
        x = _fract(u) * 2 - 1
        return np.sqrt(np.clip(1 - x * x, 0, 1))
    if nom == "vagues":
        return 0.5 + 0.5 * np.sin(2 * np.pi * (u + 0.35 * np.sin(2 * np.pi * v * 0.5)))
    if nom == "chevrons":
        return _tri(u + np.abs(_fract(v) - 0.5) * 1.5) ** nt
    if nom == "tressage":
        cu, cv = np.floor(u * 2), np.floor(v * 2)
        sens = np.mod(cu + cv, 2) == 1
        t = np.where(sens, _fract(v * 2), _fract(u * 2))
        b = np.where(sens, _fract(u * 2), _fract(v * 2))
        return np.sin(np.pi * t) * (0.55 + 0.45 * np.sin(np.pi * b))
    if nom == "picots":
        r = np.hypot(_fract(u) - 0.5, _fract(v) - 0.5) / (0.5 - tr * 0.5)
        return np.sqrt(np.clip(1 - r * r, 0, 1))
    if nom == "damier":
        return _lisse(-fl * 4, fl * 4, np.sin(np.pi * 2 * u) * np.sin(np.pi * 2 * v))
    if nom == "bois":
        return 0.5 + 0.5 * np.sin(2 * np.pi * (u + 1.2 * _fbm(u * 0.15, v * 0.6, 3)))
    if nom == "cuir":
        a, b, _ = _voronoi(u * 3, v * 3, 1.0)
        return 0.65 * np.clip((b - a) * 3, 0, 1) + 0.35 * _fbm(u * 4, v * 4)
    if nom == "bruit":
        return np.clip((_fbm(u * 2, v * 2, 5) - 0.5) * 2.4 + 0.5, 0, 1)
    # motifs reserves a l'AJOURAGE (formes de trous nettes)
    if nom == "cercles":
        r = np.hypot(_fract(u) - 0.5, _fract(v) - 0.5)
        return (r > 0.5 - tr).astype(float)
    if nom == "fentes":
        return (np.abs(_fract(u) - 0.5) > 0.5 - tr).astype(float)
    raise ValueError(f"motif inconnu : {nom}")


MOTIFS = ["alveoles", "hexa_bombe", "gaufre", "triangles", "voronoi", "pierre", "mosaique", "ecailles", "briques",
          "diamant", "rainures", "cannelures", "vagues", "chevrons", "tressage", "picots", "damier", "bois", "cuir", "bruit"]
MOTIFS_AJOURAGE = ["alveoles", "cercles", "gaufre", "triangles", "voronoi", "briques", "fentes", "diamant", "ecailles"]


def champ(nom, a, b, q):
    """Hauteur 0..1 du motif aux coordonnees surface (a, b) en mm, avec rotation / taille / etirement / decalage."""
    ang = math.radians(q.get("rotation", 0))
    ca, sa = math.cos(ang), math.sin(ang)
    t = q.get("taille", 6.0)
    et = q.get("etirement", 1.0)
    sx, sy = t * math.sqrt(et), t / math.sqrt(et)
    x, y = a * ca - b * sa, a * sa + b * ca
    p = {"trait": q.get("trait", 0.08), "nettete": q.get("nettete", 1.0), "alea": q.get("alea", 0.85)}
    h = _motif(nom, x / q.get("sx_force", sx) + q.get("du", 0), y / sy + q.get("dv", 0), p)
    return 1 - h if q.get("inverser") else h


# ------------------------------------------------------------------ relief de surface
def effet_surface(m: trimesh.Trimesh, q: dict):
    """q : motif, profondeur, taille, etirement, rotation, trait, nettete, alea, du, dv, zones, bas, haut,
    projection (auto/cylindre/triplanaire/x/y/z), inverser, fondu."""
    from .c3d import _densifier
    t = q.get("taille", 6.0)
    m = _densifier(m, max(0.2, min(0.4, t / 12)), int(q.get("max_faces", 900_000)))
    v, nrm, F = m.vertices, m.vertex_normals, m.faces
    zmin, zmax = v[:, 2].min(), v[:, 2].max()
    H = zmax - zmin
    z0, z1 = zmin + H * q.get("bas", 0) / 100, zmin + H * q.get("haut", 100) / 100
    fn = m.face_normals
    fz = m.triangles_center[:, 2]
    zones = q.get("zones", "cotes")
    ok_f = (fz > zmin + 0.25) & (fz >= z0 - 1e-6) & (fz <= z1 + 1e-6)
    ok_f &= (np.abs(fn[:, 2]) < 0.7) if zones == "cotes" else (fn[:, 2] > 0.7) if zones == "dessus" else (fn[:, 2] > -0.7)
    vf = m.vertex_faces
    ok_v = np.where(vf >= 0, ok_f[np.clip(vf, 0, None)], True).all(1)
    nom = q.get("motif", "alveoles")
    c = v[:, :2].mean(0)
    cote = np.abs(nrm[:, 2]) < 0.5
    rr = np.hypot(*(v[:, :2] - c).T)
    rond = cote.sum() > 50 and rr[cote].std() / max(rr[cote].mean(), 1e-6) < 0.1
    proj = q.get("projection", "auto")
    proj = ("cylindre" if rond else "triplanaire") if proj == "auto" else proj
    h = np.zeros(len(v))
    if proj == "cylindre":
        R = rr[cote].mean() if cote.any() else 1
        tour = 2 * math.pi * R
        sx = t * math.sqrt(q.get("etirement", 1.0))
        n_rep = max(1, round(tour / sx))
        ang = np.arctan2(v[:, 1] - c[1], v[:, 0] - c[0]) / (2 * math.pi) * tour
        lat = np.abs(nrm[:, 2]) < 0.7
        h[lat] = champ(nom, ang[lat], v[lat, 2], {**q, "sx_force": tour / n_rep})
        rest = ~lat
        h[rest] = champ(nom, v[rest, 0], v[rest, 1], q)
    elif proj in ("x", "y", "z"):
        a, b = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}[proj]
        h = champ(nom, v[:, a], v[:, b], q)
    else:
        w = nrm ** 4
        ws = w.sum(1) + 1e-9
        h = (w[:, 0] * champ(nom, v[:, 1], v[:, 2], q) + w[:, 1] * champ(nom, v[:, 0], v[:, 2], q)
             + w[:, 2] * champ(nom, v[:, 0], v[:, 1], q)) / ws
    fondu = q.get("fondu", 1.5)
    poids = np.ones(len(v))
    if fondu > 0 and zones != "dessus":
        poids = np.minimum.reduce([_lisse(z0, z0 + fondu, v[:, 2]), 1 - _lisse(z1 - fondu, z1, v[:, 2]), _lisse(zmin, zmin + fondu, v[:, 2])])
    d = h * q.get("profondeur", 0.8) * poids * ok_v
    return trimesh.Trimesh(v + nrm * d[:, None], F, process=False)


# ------------------------------------------------------------------ AJOURAGE (motif traversant)
def polygones_motif(nom, q, x0, x1, y0, y1, seuil=0.5, res=None):
    """Raster du motif sur la zone -> contours (cv2) -> polygones des TROUS (la ou le motif est < seuil)."""
    import cv2
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    t = q.get("taille", 6.0)
    res = res or max(0.05, t / 60)
    nx, ny = int((x1 - x0) / res) + 2, int((y1 - y0) / res) + 2
    if nx * ny > 16_000_000:
        res = math.sqrt((x1 - x0) * (y1 - y0) / 16_000_000)
        nx, ny = int((x1 - x0) / res) + 2, int((y1 - y0) / res) + 2
    X, Y = np.meshgrid(x0 + np.arange(nx) * res, y0 + np.arange(ny) * res)
    h = champ(nom, X, Y, q)
    trou = (h < seuil).astype(np.uint8) * 255
    cs, hier = cv2.findContours(trou, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return None
    polys = []
    paroi_min = q.get("paroi_min", 0.8)
    for i, c in enumerate(cs):
        if hier[0][i][3] != -1 or len(c) < 3:
            continue
        p = Polygon(c[:, 0, :] * res + [x0, y0]).buffer(0)
        if p.area * 1.0 > (paroi_min * 1.2) ** 2:
            polys.append(p.simplify(res * 0.7).buffer(0))
    if not polys:
        return None
    return unary_union(polys)


def ajourer(m: trimesh.Trimesh, q: dict):
    """Perce le motif A TRAVERS la piece : axe z / x / y (projection plane) ou cylindre (radial : abat-jour,
    pot, diffuseur). q : motif, taille, trait, rotation, etirement, alea, axe, bas, haut (%), marge (mm)."""
    import manifold3d as mf
    from .c3d import vers_manifold, vers_trimesh, section
    from shapely.geometry import box as sbox
    s = vers_manifold(m)
    lo, hi = m.bounds
    axe = q.get("axe", "z")
    marge = q.get("marge", 2.0)
    nom = q.get("motif", "alveoles")
    if axe == "cylindre":
        c = (lo[:2] + hi[:2]) / 2
        R = max(hi[0] - lo[0], hi[1] - lo[1]) / 2 + 1
        tour = 2 * math.pi * R
        zb = lo[2] + (hi[2] - lo[2]) * q.get("bas", 10) / 100
        zh = lo[2] + (hi[2] - lo[2]) * q.get("haut", 90) / 100
        n_rep = max(1, round(tour / (q.get("taille", 6) * math.sqrt(q.get("etirement", 1)))))
        q2 = {**q, "sx_force": tour / n_rep}
        poly = polygones_motif(nom, q2, 0, tour, zb, zh)
        if poly is None:
            raise ValueError("aucun trou : augmente la taille du motif ou affine le trait")
        poly = poly.intersection(sbox(0, zb, tour, zh))
        for ang, zc, w, h in q.get("exclure") or []:      # zones protegees (cartouche texte / logo d'un vase)
            xc = (-math.radians(ang) * R) % tour
            for d in (-tour, 0, tour):
                poly = poly.difference(sbox(xc + d - w / 2, lo[2] + zc - h / 2, xc + d + w / 2, lo[2] + zc + h / 2))
        if poly.is_empty:
            raise ValueError("aucun trou : la zone protegee couvre tout")
        # dalle depliee (x = arc, y = profondeur radiale, z = hauteur) puis enroulee autour de l'axe
        dalle = mf.Manifold.extrude(section(poly), R + 2).rotate((90, 0, 0)).translate((0, R + 1, 0))
        dalle = dalle.refine_to_length(max(1.0, tour / 720))

        def enrouler(p):
            x, y, z = p[:, 0], p[:, 1], p[:, 2]
            a = -x / R                                   # sens horaire : garde l'orientation du volume
            r = y
            return np.stack([c[0] + r * np.cos(a), c[1] + r * np.sin(a), z], 1)
        outil = dalle.warp_batch(lambda P: enrouler(np.asarray(P)))
        return vers_trimesh(s - outil)
    a, b, k = {"z": (0, 1, 2), "x": (1, 2, 0), "y": (0, 2, 1)}[axe]
    x0, x1, y0, y1 = q.get("zone_xy") or (lo[a] + marge, hi[a] - marge, lo[b] + marge, hi[b] - marge)
    if b == 2 and not q.get("zone_xy") and ("bas" in q or "haut" in q):     # perçage de cote : limite en hauteur
        Hh = hi[2] - lo[2]
        y0, y1 = max(y0, lo[2] + Hh * q.get("bas", 0) / 100), min(y1, lo[2] + Hh * q.get("haut", 100) / 100)
    poly = polygones_motif(nom, q, x0, x1, y0, y1)
    if poly is not None and q.get("zone_forme") is not None:      # limite a une forme 2D (ex. dessus arrondi)
        poly = poly.intersection(q["zone_forme"])
    if poly is None:
        raise ValueError("aucun trou : augmente la taille du motif ou affine le trait")
    L = hi[k] - lo[k] + 4
    outil = mf.Manifold.extrude(section(poly), L).translate((0, 0, lo[k] - 2))
    if axe == "x":
        M = np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0]], float)
        outil = outil.transform(M)
    elif axe == "y":
        M = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0]], float)
        outil = outil.transform(M)
    if q.get("zone_z"):                                  # limite en hauteur (ex. seulement le dessus d'une touche)
        z0, z1 = q["zone_z"]
        outil = outil ^ mf.Manifold.cube((1e4, 1e4, z1 - z0)).translate((-5e3, -5e3, z0))
    if q.get("proteger"):                               # volumes a ne JAMAIS percer (tige de touche...)
        for (x, y, r) in q["proteger"]:
            outil = outil - mf.Manifold.cylinder(1e3, r, r, 32).translate((x, y, -500))
    return vers_trimesh(s - outil)
