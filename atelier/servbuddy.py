"""LE ServBuddy (by SHWork) : bracelet porte-assiette pour le service.

Repere : X = axe de l'avant-bras (+X vers la main), Y = largeur du poignet, Z = haut (dos du poignet). Poignet = ellipse.

Architecture (inspiree des attelles de poignet : coque rigide en gouttiere, bords evases, appui large) :
- COQUE DORSALE (gouttiere ~200 deg) : evasee aux deux bouts, legerement conique (plus large cote coude) ; interieur
  avec LOGEMENT D'ALCANTARA (creux 0.8 mm) + RAINURES DE BORDURE ou l'on enfonce le film.
- PLATEAU porte-assiette rectangulaire a bords arrondis, sur PILIERS : lame d'air isolante entre plateau et poignet
  (chaleur de l'assiette) ; dessus a PISTES CREUSES concentriques a remplir de silicone (anti-derapant, isolant,
  bonne prise) ; levre peripherique ; 2 LOGEMENTS D'AIMANTS (10 x 3) sur les flancs pour clipser un ustensile.
- PLAQUE PALMAIRE (petit rectangle cote paume) clipsable / declipsable : crochet a lamelle + VERROU COULISSANT qui
  bloque la lamelle (rien ne s'ouvre en service) ; interieur alcantara aussi ; "SHWORK" grave dessous.
- REGLAGE MECANIQUE : SANGLE CRANTEE (TPU) entre la coque et la plaque palmaire, tiree par une ROULETTE moletee a
  pignon (module 1) ; un CLIQUET a lamelle s'engage dans le moletage (crans de 15 deg) : tour de poignet reglable
  au millimetre, sans outil, d'une main.
- PINCE PORTE-SERVIETTE a ressort integre (flexure) cote coude.
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as mf
from shapely.geometry import Polygon, Point, box as sbox
from shapely import affinity

from .c3d import section, vers_trimesh

M3 = 1.65


def _ell(a, b, t):
    return np.c_[a * np.cos(t), b * np.sin(t)]


def anneau(a, b, e, t0, t1, n=160, arrondi=0.7):
    """Section 2D (u = Y, v = Z) d'un arc d'anneau elliptique entre les angles t0 et t1 (rad), epaisseur e."""
    t = np.linspace(t0, t1, n)
    ext = _ell(a + e, b + e, t)
    inn = _ell(a, b, t)[::-1]
    p = Polygon(np.vstack([ext, inn])).buffer(0)
    if arrondi:
        p = p.buffer(-arrondi, join_style=1).buffer(arrondi, join_style=1)
    return p


def extrude_x(poly, x0, x1):
    """Polygone (u = Y, v = Z) extrude le long de X entre x0 et x1."""
    s = mf.Manifold.extrude(section(poly), x1 - x0)
    return s.transform(np.array([[0, 0, 1, x0], [1, 0, 0, 0], [0, 1, 0, 0]], float))


def ergonomie(s, L, b, evasement=0.08):
    """Attelle : bords EVASES aux deux bouts sur la moitie haute (dos du poignet) : la coque ne marque pas la peau.
    La moitie basse (recepteur de verrou, boitier de roulette, plaque palmaire) reste cylindrique : les pieces
    mobiles y coulissent sans deformation."""
    s = s.refine_to_length(2.0)

    def w(P):
        P = np.asarray(P).copy()
        u = np.abs(P[:, 0]) / (L / 2)
        haut = np.clip((P[:, 2] - 0.15 * b) / (0.35 * b), 0, 1) ** 2          # 0 en bas, 1 sur le dessus
        f = 1 + evasement * np.clip((u - 0.55) / 0.45, 0, 1.3) ** 3 * haut
        P[:, 1] *= f
        P[:, 2] = np.where(P[:, 2] > 0, P[:, 2] * f, P[:, 2])
        return P
    return s.warp_batch(w)


def tube(a, b, r, n=32):
    a, b = np.asarray(a, float), np.asarray(b, float)
    v = b - a
    L = float(np.linalg.norm(v))
    c = mf.Manifold.cylinder(L, r, r, n)
    z = np.array([0, 0, 1.0]); u = v / L
    ax = np.cross(z, u); s = np.linalg.norm(ax); co = float(z @ u)
    if s < 1e-9:
        R = np.eye(3) if co > 0 else np.diag([1, -1, -1.0])
    else:
        k = ax / s
        K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        g = math.atan2(s, co)
        R = np.eye(3) + math.sin(g) * K + (1 - math.cos(g)) * K @ K
    return c.transform(np.c_[R, a])


def rrect(lx, ly, r):
    return sbox(-lx / 2, -ly / 2, lx / 2, ly / 2).buffer(-r, join_style=1).buffer(r, join_style=1)


def union(l):
    l = [x for x in l if x is not None]
    return mf.Manifold.batch_boolean(l, mf.OpType.Add)


# ------------------------------------------------------------------ generateur
def servbuddy(p: dict):
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    tour = g("tour_poignet", 165.0)                 # tour de poignet mesure (mm)
    L = g("longueur", 62.0)                          # longueur de la gouttiere
    e = g("epaisseur", 2.6)
    film = g("film", 0.8)                            # alcantara adhesif
    PX, PY = g("plateau_l", 92.0), g("plateau_w", 68.0)
    air = max(g("lame_air", 9.0), 9.0)               # l'arbre de reglage passe dans la lame d'air
    # poignet : ellipse de rapport 0.72 (largeur / hauteur) dont le perimetre = tour
    k = 0.72
    a = tour / (math.pi * (3 * (1 + k) - math.sqrt((3 + k) * (1 + 3 * k))))   # Ramanujan : demi-largeur
    b = k * a
    ai, bi = a + film, b + film                      # interieur de la coque (film compris)
    out, info = {}, {}
    # angles : dorsal du cote haut, gaps lateraux, palmaire en bas
    td0, td1 = math.radians(-22), math.radians(202)         # coque dorsale (224 deg)
    tp0, tp1 = math.radians(-128), math.radians(-52)        # plaque palmaire (76 deg)

    # ---------------- COQUE DORSALE
    dor = extrude_x(anneau(ai, bi, e, td0, td1), -L / 2, L / 2)
    # logement d'alcantara + rainures de bordure (le film s'y enfonce)
    marge = 3.0
    poche = extrude_x(anneau(ai - 0.01, bi - 0.01, film, td0 + 0.07, td1 - 0.07, arrondi=0), -L / 2 + marge, L / 2 - marge)
    dor = dor - poche.translate((0, 0, 0))
    for xr in (-L / 2 + marge, L / 2 - marge):
        dor = dor - extrude_x(anneau(ai - 0.01, bi - 0.01, 1.8, td0 + 0.07, td1 - 0.07, arrondi=0), xr - 0.6, xr + 0.6)
    # ---------------- PLATEAU sur piliers (lame d'air) + pistes a silicone
    z_top_coque = bi + e
    z_pl = z_top_coque + air
    ep = 4.0
    def dalle(lx, ly, r, z, h=0.01):
        return mf.Manifold.extrude(section(rrect(lx, ly, r)), h).translate((0, 0, z))
    # dalle FLOTTANTE : sous-face fortement chanfreinee (on la voit "planer"), arete superieure adoucie
    pl = mf.Manifold.hull(union([dalle(PX - 14, PY - 14, 6, z_pl), dalle(PX, PY, 9, z_pl + ep * 0.55),
                                 dalle(PX, PY, 9, z_pl + ep - 0.8), dalle(PX - 1.6, PY - 1.6, 8.2, z_pl + ep - 0.01)]))
    # pistes creuses concentriques (silicone) + croix centrale
    pistes = []
    for d in range(5, int(min(PX, PY) / 2) - 4, 6):
        ring = rrect(PX - 2 * d, PY - 2 * d, max(1.5, 9 - d)).difference(rrect(PX - 2 * d - 4, PY - 2 * d - 4, max(1, 7 - d)))
        if not ring.is_empty:
            pistes.append(ring)
    from shapely.ops import unary_union
    pz = unary_union(pistes)
    pl = pl - mf.Manifold.extrude(section(pz), 1.4).translate((0, 0, z_pl + ep - 1.4))
    # levre peripherique (l'assiette ne glisse pas) : bourrelet 1.2 mm
    pl = pl + mf.Manifold.extrude(section(rrect(PX, PY, 9).difference(rrect(PX - 3, PY - 3, 7.5))), 1.2).translate((0, 0, z_pl + ep))
    # logements d'aimants (ustensile) sur les flancs Y
    for sy in (-1, 1):
        pl = pl - tube((PX * 0.18, sy * (PY / 2 + 0.5), z_pl + ep / 2), (PX * 0.18, sy * (PY / 2 - 3.2), z_pl + ep / 2), 5.1)
        pl = pl - tube((-PX * 0.18, sy * (PY / 2 + 0.5), z_pl + ep / 2), (-PX * 0.18, sy * (PY / 2 - 3.2), z_pl + ep / 2), 5.1)
    # MONTANTS SCULPTES (font partie de la coque) : pied large et ovale qui se fond dans la coque, tete fine
    xs_m, ys_m = L / 2 - 9, a * 0.42
    montants = []
    for x in (-xs_m, xs_m):
        for y in (-ys_m, ys_m):
            zs_ = bi * math.sqrt(max(0.05, 1 - (y / ai) ** 2))
            pied = mf.Manifold.extrude(section(affinity.scale(Point(0, 0).buffer(1, 48), 7.5, 5.5)), 0.01).translate((x, y * 0.92, zs_ - 1.0))
            tete = mf.Manifold.cylinder(0.01, 3.4, 3.4, 48).translate((x, y, z_pl - 0.01))
            montants.append(mf.Manifold.hull(pied + tete))
    out["plateau"] = pl
    # ================= REGLAGE 100 % MECANIQUE ET RIGIDE (PLA) : 2 CREMAILLERES + ARBRE + ROULETTE + VERROU
    # La plaque palmaire porte 2 cremailleres VERTICALES (une de chaque cote du poignet). Elles coulissent dans 2
    # guides de la coque dorsale. Un ARBRE transversal (dans la lame d'air, sous le plateau) porte 2 pignons qui
    # engrenent les 2 cremailleres : tourner la ROULETTE monte / descend la plaque bien parallele (serrage).
    # Un VERROU (pion coulissant parallele a l'arbre) entre dans les trous de la roulette : position bloquee, rigide.
    # Deverrouille + roulette tournee a fond vers le bas : les cremailleres sortent des guides -> plaque retiree.
    from .meca import profil_engrenage
    rp, mod = 6.5, 1.0                                           # pignons 13 dents module 1
    Yp = ai + e + 4.6                                            # plan des pignons / cremailleres (hors de la coque)
    wp = 5.0                                                     # largeur des pignons et cremailleres
    z_s = bi + e + 3.6                                           # axe de l'arbre, dans la lame d'air
    xr0 = rp - 1.0                                               # pied des dents de cremaillere (cote pignon)
    xr1 = rp + 5.5                                               # dos de la cremaillere
    z_bas = -(bi + e) + 1.0                                      # bas des cremailleres (au niveau de la plaque)
    z_haut = z_s + 7.0                                           # haut des cremailleres en position nominale
    j = 0.3
    # ---------------- PLAQUE PALMAIRE
    pal = extrude_x(anneau(ai, bi, e, tp0, tp1), -L / 2 + 6, L / 2 - 6)
    pal = pal - extrude_x(anneau(ai - 0.01, bi - 0.01, film, tp0 + 0.06, tp1 - 0.06, arrondi=0), -L / 2 + 9, L / 2 - 9)
    zb = -(bi + e)
    boss = mf.Manifold.extrude(section(rrect(L - 16, 2 * ai * 0.5, 5)), 4.0).translate((0, 0, zb - 1.6))
    boss = boss - extrude_x(Polygon(_ell(ai + 0.2, bi + 0.2, np.linspace(-math.pi, math.pi, 200))), -L, L)
    pal = pal + boss
    try:
        from .porte_cles import Style, prenom_polygone
        txt, _ = prenom_polygone("SHWORK", Style(police="bebas", hauteur=6.0, serrage=0.0))
        bt = txt.bounds
        txt = affinity.translate(txt, -(bt[0] + bt[2]) / 2, -(bt[1] + bt[3]) / 2)
        txt = affinity.scale(txt, -1, 1, origin=(0, 0))
        pal = pal - mf.Manifold.extrude(section(txt), 0.7).translate((0, 0, zb - 1.6 - 0.01))
    except Exception:
        pass
    # 2 bras + 2 cremailleres (dents vers -X, cote pignon)
    for s in (-1, 1):
        y0 = s * (Yp - wp / 2) if s > 0 else s * (Yp + wp / 2)
        bras_y0, bras_y1 = sorted((s * (ai + e) * math.cos(tp1 if s > 0 else tp0) * (1 if s > 0 else 1), s * (Yp + wp / 2)))
        bras_y0, bras_y1 = sorted((s * 18.0, s * (Yp + wp / 2)))
        pal = pal + mf.Manifold.cube((xr1 - xr0 + 4, bras_y1 - bras_y0, 5.0)).translate((xr0 - 2, bras_y0, zb - 1.0))
        cr = mf.Manifold.cube((xr1 - (rp + 1.25), wp, z_haut - zb)).translate((rp + 1.25, s * Yp - wp / 2, zb))
        for zt in z_s + math.pi * mod * np.arange(-int((z_s - zb - 6) / (math.pi * mod)), int((z_haut - 1.0 - z_s) / (math.pi * mod)) + 1):   # une dent pile a la hauteur de l'arbre
            # dent de cremaillere normalisee m1, 20 deg : ligne primitive x = rp, saillie 1, creux 1.25, jeu 0.1 / flanc
            dent = Polygon([(rp + 1.3, zt - 1.14), (rp + 1.3, zt + 1.14), (rp - 1.0, zt + 0.32), (rp - 1.0, zt - 0.32)])
            cr = cr + mf.Manifold.extrude(section(dent), wp).transform(np.array([[1, 0, 0, 0], [0, 0, 1, s * Yp - wp / 2], [0, 1, 0, 0]], float))
        pal = pal + cr
    pal = pal - extrude_x(Polygon(_ell(ai, bi, np.linspace(-math.pi, math.pi, 240))), -L, L)          # jamais dans le poignet
    out["plaque_palmaire"] = pal
    # ---------------- NACELLES (guide de cremaillere + paliers de l'arbre + logement du pignon) : une seule forme
    # profilee en goutte, qui nait de la coque et remonte jusqu'a l'arbre ; fenetre sur le pignon (cote horloger).
    cav = extrude_x(Polygon(_ell(ai, bi, np.linspace(-math.pi, math.pi, 240))), -L, L)
    gz0 = -(bi + e) * 0.25
    for s_ in (-1, 1):
        yi_, ye_ = s_ * (Yp - wp / 2 - 4.2), s_ * (Yp + wp / 2 + 4.2)
        tete = tube((0, yi_, z_s), (0, ye_, z_s), rp + 4.0, 64)
        dos = tube((xr1 + 1.0, yi_, z_s - 2), (xr1 + 1.0, ye_, z_s - 2), 3.2, 32)
        pied = tube(((xr0 + xr1) / 2, yi_, gz0 + 4), ((xr0 + xr1) / 2, ye_, gz0 + 4), 4.6, 32)
        racine = tube((-2, s_ * 20, 4), (12, s_ * 20, 4), 4.0, 32)          # se fond dans la coque
        nac = mf.Manifold.hull(union([tete, dos, pied, racine]))
        nac = nac - cav
        nac = nac - mf.Manifold.cube((PX + 20, PY + 1.2, 40)).translate((-PX / 2 - 10, -PY / 2 - 0.6, z_pl - 0.6))   # affleure sous le plateau
        dor = dor + nac
        dor = dor - mf.Manifold.cube((xr1 - xr0 + 2 * j + 1.2, wp + 2 * j, 200)).translate((xr0 - 1.2 - j, s_ * Yp - wp / 2 - j, -100))
        dor = dor - tube((0, s_ * (Yp - wp / 2 - 0.65), z_s), (0, s_ * (Yp + wp / 2 + 0.65), z_s), rp + 1.6)
        # fenetre sur le pignon (montage + look) : ouverte vers le haut et l'arriere
        dor = dor - mf.Manifold.cube((2 * rp + 3.2, wp + 1.3, 30)).translate((-rp - 1.6, s_ * Yp - wp / 2 - 0.65, z_s))
    dor = dor - tube((0, -(Yp + 20), z_s), (0, Yp + 20, z_s), 3.15)              # alesage de l'arbre (traverse tout)
    # ---------------- ARBRE (hexagonal 5 mm sur plats) + ROULETTE integree (cote -Y) + 2 PIGNONS a moyeu hexagonal
    hexa = Polygon([(2.89 * math.cos(math.pi / 3 * i), 2.89 * math.sin(math.pi / 3 * i)) for i in range(6)])
    y_k0 = -(Yp + wp / 2 + 5.4)
    arbre = mf.Manifold.extrude(section(hexa), (Yp + wp / 2 + 5.0) - y_k0 + 0.01).translate((0, 0, y_k0))
    R_k = 11.0
    rou = mf.Manifold.cylinder(6.0, R_k, R_k, 96).translate((0, 0, y_k0 - 6.0))
    for i in range(30):                                           # moletage de prise
        ang = i * math.pi / 15
        rou = rou - mf.Manifold.cylinder(8, 0.9, 0.9, 10).translate((R_k * math.cos(ang), R_k * math.sin(ang), y_k0 - 7))
    R_tr = 7.6                                                    # 12 trous de verrouillage (crans de 30 deg)
    for i in range(12):
        ang = i * math.pi / 6
        rou = rou - mf.Manifold.cylinder(4.0, 1.35, 1.35, 16).translate((R_tr * math.cos(ang), R_tr * math.sin(ang), y_k0 - 3.99))
    arbre = arbre + rou
    arbre = arbre - mf.Manifold.cylinder(10, 1.25, 1.25, 16).translate((0, 0, Yp + wp / 2 + 5.0 - 9.9))   # vis M3 de bout
    # repere : axe Z local -> axe Y, centre (0, z_s)
    Tz = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, z_s]], float)     # local Z -> Y, local Y -> -Z
    out["arbre_roulette"] = arbre.transform(Tz)
    pg, _ = profil_engrenage(mod, 13, 20, 0.12)
    for s, nom in ((-1, "pignon_g"), (1, "pignon_d")):
        pn = mf.Manifold.extrude(section(affinity.rotate(pg, 180 / 13, origin=(0, 0)).difference(hexa.buffer(0.15, join_style=2))), wp).translate((0, 0, s * Yp - wp / 2))   # un creux face a la dent
        out[nom] = pn.transform(Tz)
    out["rondelle_bout"] = mf.Manifold.cylinder(1.8, 4.5, 4.5, 32).translate((0, 0, Yp + wp / 2 + 5.0)) \
        .__sub__(mf.Manifold.cylinder(4, M3, M3, 16).translate((0, 0, Yp + wp / 2 + 4))).transform(Tz)
    # ---------------- VERROU : pion coulissant (parallele a l'arbre) dans le palier exterieur gauche -> trous de la roulette
    ang_v = math.radians(90)                                       # trou de verrou au-dessus de l'arbre
    vx, vz = R_tr * math.cos(ang_v), z_s + R_tr * math.sin(ang_v)
    vx, vz = 0.0, z_s + R_tr
    yv0, yv1 = -(Yp + wp / 2 + 0.6), -(Yp + wp / 2 + 4.6)
    dor = dor + (mf.Manifold.cube((8, 4.0, vz + 4.5 - (z_s + 2))).translate((-4, yv1, z_s + 2)) - cav)   # bossage du verrou
    dor = dor - tube((vx, yv0 + 0.5, vz), (vx, yv1 - 0.5, vz), 1.5)              # canon du pion
    dor = dor - mf.Manifold.cube((2.2, 4.2, 6.0)).translate((vx - 1.1, yv1 - 0.1, vz + 0.4))     # lumiere du doigt
    dor = dor - tube((0, -(Yp + 20), z_s), (0, Yp + 20, z_s), 3.15)              # alesage (re-perce apres le bossage)
    pion = tube((vx, yv0 + 0.3, vz), (vx, y_k0 - 3.0, vz), 1.2)                  # engage : traverse le palier + 3 mm dans la roulette
    pion = pion + mf.Manifold.cube((1.8, 2.0, 5.0)).translate((vx - 0.9, yv1 + 0.6, vz))         # doigt de manoeuvre
    out["verrou"] = pion
    # ---------------- PINCE PORTE-SERVIETTE (cote coude) : machoire sur lame souple
    pince = union([mf.Manifold.cube((3, 26, 8)).translate((-PX / 2 - 3, -13, z_pl - 2)),
                   mf.Manifold.cube((20, 26, 2.2)).translate((-PX / 2 - 21, -13, z_pl - 2)),
                   mf.Manifold.cube((3, 26, 5)).translate((-PX / 2 - 21, -13, z_pl + 0.2))])
    for i in range(5):
        pince = pince + mf.Manifold.cube((1.2, 26, 1.2)).translate((-PX / 2 - 18 + i * 3.2, -13, z_pl + 0.2))
    out["plateau"] = out["plateau"] + pince
    # ---------------- ergonomie (attelle) appliquee aux coques
    # OUIES d'aeration : fentes allongees inclinees sur les flancs hauts (sous le plateau : la chaleur s'evacue)
    for ang in (38, 52, 128, 142):
        t_ = math.radians(ang)
        for xc in (-14, 0, 14):
            r_in = np.array([0, ai * math.cos(t_), bi * math.sin(t_)]) * 0.95
            r_out = np.array([0, (ai + e) * math.cos(t_), (bi + e) * math.sin(t_)]) * 1.08
            fente = mf.Manifold.hull(union([tube(r_in + [xc - 4.5, 0, 0], r_out + [xc - 4.5, 0, 0], 1.3, 16),
                                            tube(r_in + [xc + 4.5, 0, 0], r_out + [xc + 4.5, 0, 0], 1.3, 16)]))
            dor = dor - fente
    dor = dor + (union(montants) - cav)
    out["coque_dorsale"] = ergonomie(dor, L, bi)
    for x in (-xs_m, xs_m):                                          # 4 vis M3 : plateau -> tetes des montants
        for y in (-ys_m, ys_m):
            out["plateau"] = out["plateau"] - tube((x, y, z_pl + ep + 1), (x, y, z_pl - 1), M3) - tube((x, y, z_pl + ep + 1), (x, y, z_pl + ep - 2.0), 3.0)
            out["coque_dorsale"] = out["coque_dorsale"] - tube((x, y, z_pl + 0.1), (x, y, z_pl - 9), 1.25)
    out["coque_dorsale"] = out["coque_dorsale"] - out["plateau"]      # le plateau se pose, rien ne s'interpenetre
    # zero copeau : chaque piece = ses morceaux significatifs seulement
    for k_, v_ in list(out.items()):
        parts = sorted(v_.decompose(), key=lambda q: -q.volume())
        out[k_] = union([q for q in parts if q.volume() > 0.02 * parts[0].volume()])
    info.update({"poignet_mm": [round(2 * a, 1), round(2 * b, 1)], "tour_poignet": tour,
                 "plateau_mm": [PX, PY], "lame_air_mm": air,
                 "quincaillerie": ["5 vis M3 x 10 (4 plateau + bout d'arbre)", "4 aimants neodyme 10 x 3 (ustensiles)",
                                   "Silicone alimentaire bi-composant (pistes du plateau)",
                                   f"Film alcantara adhesif {film} mm : 2 bandes (coque {round(L - 6)} mm de large, plaque {round(L - 18)} mm)",
                                   "Tout en PLA (remplissage 40 %+, 4 perimetres pour arbre, pignons et cremailleres)"]})
    return out, info
