"""Profils d'engrenages en developpante de cercle (exterieurs et interieurs).

Toutes les cotes en mm. Les profils sont des polygones 2D fermes (liste de (x, y))
orientes CCW, centres sur l'origine, dent n°0 centree sur l'axe +X.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def inv(alpha: float) -> float:
    """Fonction developpante : inv(a) = tan(a) - a."""
    return math.tan(alpha) - alpha


@dataclass
class GearGeom:
    z: int
    m: float
    pressure_angle_deg: float = 20.0

    @property
    def r(self) -> float:          # rayon primitif
        return self.m * self.z / 2

    @property
    def rb(self) -> float:         # rayon de base
        return self.r * math.cos(math.radians(self.pressure_angle_deg))

    def tip_radius_ext(self, ha: float = 1.0) -> float:
        return self.r + ha * self.m

    def root_radius_ext(self, hf: float = 1.25) -> float:
        return self.r - hf * self.m


def _flank_angle(rb: float, rho: float, half_thick_angle: float, pa: float) -> float:
    """Demi-angle (par rapport a l'axe de la dent) du flanc a un rayon rho >= rb."""
    alpha = math.acos(min(1.0, rb / rho))
    return half_thick_angle + inv(pa) - inv(alpha)


def tooth_polygon(z: int, m: float, *, pa_deg: float = 20.0, ha: float = 1.0,
                  hf: float = 1.25, thickness_delta: float = 0.0,
                  flank_pts: int = 10, arc_pts: int = 4) -> list[tuple[float, float]]:
    """Polygone d'une roue a denture droite en developpante.

    ha / hf : coefficients de saillie / creux (x m).
    thickness_delta : variation d'epaisseur de dent sur le primitif (mm).
        < 0 -> dent amincie (jeu fonctionnel), > 0 -> dent epaissie.
    Pour une couronne interieure on appelle cette fonction avec ha=1.25, hf=1.0 et
    thickness_delta = +jeu : on obtient la forme du *vide* a soustraire.
    """
    pa = math.radians(pa_deg)
    r = m * z / 2
    rb = r * math.cos(pa)
    ra = r + ha * m
    rf = max(0.3 * r, r - hf * m)
    half_t = (math.pi * m / 2 + thickness_delta) / (2 * r)   # demi-angle d'epaisseur au primitif
    pitch = 2 * math.pi / z

    r_start = max(rb, rf)
    # rayons echantillonnes sur le flanc (plus denses pres de la base)
    rhos = [r_start + (ra - r_start) * (i / flank_pts) ** 1.3 for i in range(flank_pts + 1)]
    phis = [_flank_angle(rb, rho, half_t, pa) for rho in rhos]

    # pointe de dent : si les flancs se croisent avant ra, on tronque
    tip_idx = len(rhos) - 1
    for i, ph in enumerate(phis):
        if ph <= 0.002:
            tip_idx = max(1, i - 1)
            break
    rhos, phis = rhos[:tip_idx + 1], phis[:tip_idx + 1]
    phi_base = phis[0]
    # demi-largeur angulaire du creux ne doit pas etre negative
    root_half = pitch / 2 - phi_base

    pts: list[tuple[float, float]] = []
    for k in range(z):
        c = k * pitch
        # descente radiale sous le cercle de base (si pied < base)
        if rf < rb:
            pts.append((rf * math.cos(c - phi_base), rf * math.sin(c - phi_base)))
        # flanc gauche (angle croissant avec k -> CCW) : de la base vers la tete
        for rho, ph in zip(rhos, phis):
            pts.append((rho * math.cos(c - ph), rho * math.sin(c - ph)))
        # arc de tete
        ph_t = phis[-1]
        rt = rhos[-1]
        for j in range(1, arc_pts):
            a = c - ph_t + 2 * ph_t * j / arc_pts
            pts.append((rt * math.cos(a), rt * math.sin(a)))
        # flanc droit : de la tete vers la base
        for rho, ph in zip(reversed(rhos), reversed(phis)):
            pts.append((rho * math.cos(c + ph), rho * math.sin(c + ph)))
        if rf < rb:
            pts.append((rf * math.cos(c + phi_base), rf * math.sin(c + phi_base)))
        # arc de pied jusqu'a la dent suivante
        if root_half > 0:
            a0 = c + phi_base
            a1 = c + pitch - phi_base
            for j in range(1, arc_pts):
                a = a0 + (a1 - a0) * j / arc_pts
                pts.append((rf * math.cos(a), rf * math.sin(a)))
    return pts


def external_gear(z: int, m: float, backlash: float = 0.0, pa_deg: float = 20.0,
                  **kw) -> list[tuple[float, float]]:
    """Pignon exterieur ; `backlash` = jeu total a repartir (la moitie par roue)."""
    return tooth_polygon(z, m, pa_deg=pa_deg, ha=1.0, hf=1.25,
                         thickness_delta=-backlash / 2, **kw)


def internal_gear_cutter(z: int, m: float, backlash: float = 0.0, pa_deg: float = 20.0,
                         **kw) -> list[tuple[float, float]]:
    """Forme du vide d'une couronne interieure (a soustraire d'un disque)."""
    return tooth_polygon(z, m, pa_deg=pa_deg, ha=1.25, hf=1.0,
                         thickness_delta=+backlash / 2, **kw)


def contact_ratio_external(z1: int, z2: int, m: float, pa_deg: float = 20.0) -> float:
    pa = math.radians(pa_deg)
    r1, r2 = m * z1 / 2, m * z2 / 2
    ra1, ra2 = r1 + m, r2 + m
    rb1, rb2 = r1 * math.cos(pa), r2 * math.cos(pa)
    a = r1 + r2
    L = math.sqrt(ra1**2 - rb1**2) + math.sqrt(ra2**2 - rb2**2) - a * math.sin(pa)
    return L / (math.pi * m * math.cos(pa))


def contact_ratio_internal(zp: int, zr: int, m: float, pa_deg: float = 20.0) -> float:
    pa = math.radians(pa_deg)
    rp, rr = m * zp / 2, m * zr / 2
    rap, rar = rp + m, rr - m
    rbp, rbr = rp * math.cos(pa), rr * math.cos(pa)
    a = rr - rp
    L = math.sqrt(rap**2 - rbp**2) - math.sqrt(max(0.0, rar**2 - rbr**2)) + a * math.sin(pa)
    return L / (math.pi * m * math.cos(pa))


def min_teeth_no_undercut(pa_deg: float = 20.0) -> int:
    return math.ceil(2 / math.sin(math.radians(pa_deg)) ** 2)
