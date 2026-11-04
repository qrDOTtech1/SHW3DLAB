"""Profil de disque cycloidal (reducteur a rouleaux / pions fixes).

Convention : couronne de N pions de rayon rp sur un cercle de rayon R, centree a
l'origine. Le disque possede N-1 lobes. Pour un angle d'entree 0, le centre du disque
est en (+e, 0) et son orientation est 0. Rapport de reduction (couronne fixe,
sortie par les pions de sortie) : N-1, sens inverse de l'entree.

Le second disque (dephase de 180 deg) : centre en (-e, 0) et rotation de
pi/(N-1) (un demi-lobe) -> verifie numeriquement par `check_mesh`.
"""
from __future__ import annotations

import math

from shapely.geometry import Point, Polygon


def cycloid_profile(R: float, rp: float, N: int, e: float, samples: int | None = None,
                    ) -> list[tuple[float, float]]:
    """Profil exact (sans jeu) du disque dans son repere propre."""
    samples = samples or max(600, 40 * N)
    pts = []
    for i in range(samples):
        t = 2 * math.pi * i / samples
        psi = math.atan2(math.sin((1 - N) * t), R / (e * N) - math.cos((1 - N) * t))
        x = R * math.cos(t) - rp * math.cos(t + psi) - e * math.cos(N * t)
        y = -R * math.sin(t) + rp * math.sin(t + psi) + e * math.sin(N * t)
        pts.append((x, y))
    poly = Polygon(pts)
    if not poly.exterior.is_ccw:
        pts.reverse()
    return pts


def disc_polygon(R: float, rp: float, N: int, e: float, clearance: float) -> Polygon:
    """Disque avec jeu fonctionnel : profil decale vers l'interieur de clearance/2."""
    poly = Polygon(cycloid_profile(R, rp, N, e))
    if not poly.is_valid:
        poly = poly.buffer(0)
    if clearance > 0:
        poly = poly.buffer(-clearance / 2, join_style=1, quad_segs=4)
    return poly


def validity(R: float, rp: float, N: int, e: float) -> dict:
    """Controles de validite geometrique du profil."""
    k1 = e * N / R                      # coefficient d'excentricite (< 1 obligatoire)
    ok_k1 = k1 < 1.0
    poly = Polygon(cycloid_profile(R, rp, N, e))
    simple = poly.is_valid
    # rayon de courbure minimal de l'epicycloide raccourcie ~ approx : on verifie que
    # le decalage de rp ne cree pas de boucle -> equivalent a un polygone valide
    # espacement entre pions
    pin_gap = 2 * R * math.sin(math.pi / N) - 2 * rp
    return {"k1": round(k1, 3), "k1_ok": ok_k1, "profil_simple": simple,
            "ecart_pions_mm": round(pin_gap, 2), "ecart_ok": pin_gap > 1.0,
            "ok": ok_k1 and simple and pin_gap > 1.0}


def check_mesh(R: float, rp: float, N: int, e: float, second_disc: bool = False,
               input_angle: float = 0.0) -> dict:
    """Distance min disque/pions pour un angle d'entree donne (verification numerique).

    Retourne la penetration max (<0 = interference) et l'ecart min.
    """
    from shapely import affinity
    poly = Polygon(cycloid_profile(R, rp, N, e))
    sign = -1 if second_disc else 1
    rot0 = math.pi / (N - 1) if second_disc else 0.0
    # cinematique : centre du disque tourne avec l'entree, le disque tourne de -in/(N-1)
    cx = sign * e * math.cos(input_angle)
    cy = sign * e * math.sin(input_angle)
    rot = rot0 - input_angle / (N - 1)
    d = affinity.rotate(poly, rot, origin=(0, 0), use_radians=True)
    d = affinity.translate(d, cx, cy)
    dists = []
    for k in range(N):
        a = 2 * math.pi * k / N
        p = Point(R * math.cos(a), R * math.sin(a))
        dist = d.exterior.distance(p) * (1 if not d.contains(p) else -1)
        dists.append(dist - rp)
    return {"ecart_min": min(dists), "ecart_max": max(dists)}
