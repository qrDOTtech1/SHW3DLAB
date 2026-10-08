"""CHASSIS SHWORK 190 (RC 1:10) : chassis tubulaire custom imprime, modules vissés, suspension ACTIVE a culbuteurs.

Repere = celui de la carrosserie preparee (sol z = 0, avant = -X, axe de symetrie y = 0, mm).

Architecture (demande Steven, 2026-10-07) :
- PLANCHER bas (plaque) + FAUX PLANCHER : tunnel a glissieres en queue d'aronde sous la cabine, ou l'on glisse des
  TIROIRS (batterie, electronique, reservoir d'air...) ;
- CAGE TUBULAIRE de cabine : 2 flancs plans (arceau avant / arceau principal / arceau arriere, longerons de toit,
  croix de porte) + traverses a pattes vissees M3 (comme une vraie cage boulonnee) ;
- MODULE AVANT vissé (4 x M3) : supports de suspension AV ; il porte ailes, capot, calandre (pattes de fixation) ;
- MODULE ARRIERE vissé : suspension AR, porte pare-chocs AR ;
- SUSPENSION a doubles triangles + PUSHROD + CULBUTEUR ; chaque culbuteur pousse un VERIN PNEUMATIQUE CUSTOM monte a
  l'HORIZONTALE (le long de X) : ressort pneumatique. Facon "Activa 2026" : un DISTRIBUTEUR A TIROIR pilote par
  SERVO par essieu transfere l'air entre verin gauche et droit (anti-roulis actif), plus tard en hydraulique (huile
  vegetale) poussee par le compresseur Wankel.
Toutes les pieces sortent en coordonnees d'assemblage ; l'orientation d'impression est faite par l'appelant.
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as mf
from shapely.geometry import Polygon, box as sbox

from .c3d import section, vers_trimesh

M3_PASSAGE, M3_TARAUD = 1.65, 1.25


# ------------------------------------------------------------------ briques
def tube(a, b, r, n=24):
    """Cylindre plein de a a b (rayon r)."""
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
        ang = math.atan2(s, co)
        R = np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K
    return c.transform(np.c_[R, a])


def trou(a, b, r=M3_PASSAGE):
    return tube(a, b, r, 20)


def boule(p, r):
    return mf.Manifold.sphere(r, 24).translate(tuple(p))


def plaque(poly, z0, e):
    return mf.Manifold.extrude(section(poly), e).translate((0, 0, z0))


def union(lst):
    lst = [x for x in lst if x is not None]
    return mf.Manifold.batch_boolean(lst, mf.OpType.Add) if lst else None


# ------------------------------------------------------------------ geometrie de reference
def reperes(p):
    g = lambda k, d: float(p.get(k, d))
    return {
        "xa": g("x_essieu_av", -142.4), "xr": g("x_essieu_ar", 118.2),
        "zr": g("z_roue", 31.3), "voie": g("voie", 140.0), "rr": g("r_roue", 31.0), "lr": g("l_roue", 24.0),
        "z_plancher": g("z_plancher", 6.0), "e_plancher": g("e_plancher", 2.5),
        "demi_int": g("demi_largeur_int", 68.0),
        "x_cab_av": g("x_cabine_av", -88.0), "x_cab_ar": g("x_cabine_ar", 78.0),
        "z_toit": g("z_toit", 110.0), "r_tube": g("r_tube", 2.6),
    }


# ------------------------------------------------------------------ plancher + faux plancher a tiroirs
def plancher(R):
    zp, e = R["z_plancher"], R["e_plancher"]
    xa, xr = R["xa"], R["xr"]
    # plaque : etroite entre les roues AV (braquage), large sous la cabine, moyenne a l'arriere
    poly = Polygon([(xa - 50, -34), (xa + 38, -34), (xa + 52, -66), (xr - 40, -66), (xr - 28, -50), (xr + 62, -50),
                    (xr + 62, 50), (xr - 28, 50), (xr - 40, 66), (xa + 52, 66), (xa + 38, 34), (xa - 50, 34)]).buffer(4, join_style=1).buffer(-4, join_style=1)
    s = plaque(poly, zp, e)
    # nervures longitudinales (rigidite) + bossages de fixation des modules et de la cage
    for y in (-47.0, 47.0):                                     # nervures SOUS le plancher (rigidite ; le tunnel se visse dedans)
        x0n, x1n = R["x_cab_av"] - 4, R["x_cab_ar"] + 4
        s = s + mf.Manifold.cube((x1n - x0n, 3, 3)).translate((x0n, y - 1.5, zp - 3))
    fix = []
    for x in (xa + 30, xa + 46, xr - 30, xr - 16):              # modules AV / AR : 4 vis chacun
        for y in (-24, 24):
            fix.append((x, y))
    for x in (R["x_cab_av"], R["x_cab_ar"], 18.0):              # pieds de cage (a, c, montant B)
        for y in (-(R["demi_int"] - 8), R["demi_int"] - 8):
            fix.append((x, y))
    for x, y in fix:
        s = s - trou((x, y, zp - 1), (x, y, zp + e + 6), M3_TARAUD)
    return s, fix


def faux_plancher(R, l_tunnel=None):
    """Tunnel sous la cabine : parois + couvercle (le vrai 'plancher' de l'habitacle), glissieres en queue d'aronde
    sur le fond : on y glisse des tiroirs par l'avant ou l'arriere."""
    zp, e = R["z_plancher"], R["e_plancher"]
    x0, x1 = R["x_cab_av"] + 0.5, R["x_cab_ar"] - 6
    L = x1 - x0
    larg, h = 92.0, 16.0                                       # interieur du tunnel
    z0 = zp + e
    paroi = 2.0
    ext = mf.Manifold.cube((L, larg + 2 * paroi, h + paroi)).translate((x0, -(larg / 2 + paroi), z0))
    vide = mf.Manifold.cube((L + 2, larg, h)).translate((x0 - 1, -larg / 2, z0))
    tun = ext - vide
    # glissieres en queue d'aronde (2) sur le fond
    q = Polygon([(-3.0, 0), (3.0, 0), (4.5, 2.4), (-4.5, 2.4)])
    rails = []
    for y in (-26, 26):
        rails.append(rail_x(q, L, x0, y, z0))
    # fixation : 4 vis M3 verticales dans les parois du tunnel (taraudees dans les nervures du plancher)
    for x in (x0 + 8, x1 - 8):
        for y in (-(larg / 2 + paroi / 2), larg / 2 + paroi / 2):
            tun = tun - trou((x, y, z0 - 1), (x, y, z0 + h + paroi + 1))
    return tun, union(rails), {"x0": x0, "x1": x1, "larg": larg, "h": h, "z0": z0}


def rail_x(q, L, x0, y, z):
    """Profil 2D q (u = largeur selon Y, v = hauteur selon Z) extrude le long de +X sur L, pose en (x0, y, z)."""
    e = mf.Manifold.extrude(section(q), L)                      # (u, v, w) -> (x = w, y = u, z = v)
    return e.transform(np.array([[0, 0, 1, x0], [1, 0, 0, y], [0, 1, 0, z]], float))


def tiroir(T, longueur=70.0, hauteur=12.0, nom="tiroir"):
    """Tiroir qui glisse sur les queues d'aronde du faux plancher (jeu 0.25), poignee a l'avant."""
    j = 0.25
    larg = T["larg"] - 2 * j
    z0 = T["z0"] + 2.4 + j
    s = mf.Manifold.cube((longueur, larg, hauteur)).translate((0, -larg / 2, z0))
    s = s - mf.Manifold.cube((longueur - 4, larg - 4, hauteur)).translate((2, -larg / 2 + 2, z0 + 2))
    q = Polygon([(-3.0 - j, -0.01), (3.0 + j, -0.01), (4.5 + j, 2.4 + j), (-4.5 - j, 2.4 + j)])
    for y in (-26, 26):                                          # rainures femelles sous le tiroir
        s = s - rail_x(q, longueur + 2, -1, y, T["z0"])
    s = s + tube((-3, -10, z0 + hauteur / 2), (-3, 10, z0 + hauteur / 2), 2.0)       # poignee
    return s.translate((T["x0"] + 4, 0, 0))


# ------------------------------------------------------------------ cage tubulaire (2 flancs plans + traverses)
def cage(R):
    rt = R["r_tube"]
    ya = R["demi_int"] - 8                                       # plan des flancs (|y|)
    xA, xB, xC = R["x_cab_av"], 18.0, R["x_cab_ar"]              # pied avant, montant B, pied arriere
    zb = R["z_plancher"] + R["e_plancher"] + R["r_tube"] * 1.35 + 0.05   # les boules des pieds posent SUR le plancher
    zt = R["z_toit"]
    zc = 84.0                                                    # ligne de ceinture (sous la vitre)
    # noeuds d'un flanc (x, z)
    N = {"a0": (xA, zb), "a1": (xA + 4, zc), "a2": (-28.0, zt - 4), "b0": (xB, zb), "b1": (xB, zc), "b2": (xB, zt),
         "c0": (xC, zb), "c1": (xC - 6, zc), "c2": (66.0, zt - 3)}
    barres = [("a0", "a1"), ("a1", "a2"), ("a2", "b2"), ("b2", "c2"), ("c2", "c1"), ("c1", "c0"), ("a0", "b0"), ("b0", "c0"),
              ("b0", "b1"), ("b1", "b2"), ("a1", "b1"), ("b1", "c1"), ("a0", "b1"), ("a1", "b0"), ("b1", "c0")]
    flancs = {}
    for s in (1, -1):
        P = {k: (x, s * ya, z) for k, (x, z) in N.items()}
        parts = [tube(P[a], P[b], rt) for a, b in barres] + [boule(p, rt * 1.35) for p in P.values()]
        f = union(parts)
        for k in ("a0", "b0", "c0"):                            # pieds : trou vertical M3 vers le plancher
            x, y, z = P[k]
            f = f + mf.Manifold.cylinder(z - (R["z_plancher"] + R["e_plancher"]) - 0.02, 4.2, 4.2, 24).translate((x, y, R["z_plancher"] + R["e_plancher"] + 0.02))
            f = f - trou((x, y, z - 10), (x, y, z + 6))
        for k in ("a1", "b1", "c1", "a2", "b2", "c2"):          # noeuds : trou transversal M3 pour les traverses
            x, y, z = P[k]
            f = f - trou((x, y - 6, z), (x, y + 6, z))
        flancs[s] = f
    # traverses a pattes : entre les flancs, aux noeuds hauts et a la ceinture
    trav = []
    for k in ("a2", "b2", "c2", "b1", "c1", "a1"):
        x, z = N[k]
        y0, y1 = -ya + 3.2, ya - 3.2
        t = tube((x, y0, z), (x, y1, z), rt)
        for yy in (y0, y1):                                     # pattes (oreilles) percees M3
            t = t + mf.Manifold.cube((8, 3.0, 8), True).translate((x, yy + (1.5 if yy < 0 else -1.5), z))
            t = t - trou((x, yy - 6, z), (x, yy + 6, z))
        trav.append(t)
    # croix de toit (rigidite) vissee aux traverses a2 / c2
    xs, zs = N["a2"], N["c2"]
    trav.append(union([tube((xs[0] + 6, -ya + 6, xs[1] - 1), (zs[0] - 6, ya - 6, zs[1] - 1), rt * 0.85),
                       tube((xs[0] + 6, ya - 6, xs[1] - 1), (zs[0] - 6, -ya + 6, zs[1] - 1), rt * 0.85)]))      # croix de toit (1 piece)
    return flancs, trav, N, ya


# ------------------------------------------------------------------ suspension a culbuteur + verin horizontal
Y_CLOISON = 22.0          # plan interieur des cloisons de suspension (|y|), epaisseur 4 mm vers l'exterieur
E_CLOISON = 4.0


def coin(R, xa, s, avant=True):
    """Un coin de suspension (cote s = +1 / -1) monte sur la CLOISON du module.
    - triangles : bagues de pivot (axe X) collees a la face exterieure de la cloison (|y| = Yc + 4 + 2.6) ;
    - pushrod du triangle inferieur au culbuteur ;
    - culbuteur : pivote (axe Y) sur la face exterieure de la cloison, AU-DESSUS du triangle superieur ;
    - verin horizontal (axe X) entre le bras haut du culbuteur et une console de la cloison."""
    zr = R["zr"]
    yr = s * R["voie"] / 2
    yi = s * (R["voie"] / 2 - R["lr"] / 2 - 4)                  # face interieure du pneu - 4
    yb = s * (Y_CLOISON + E_CLOISON + 3.7)                       # axe des bagues contre la cloison
    Lo_in = [(xa - 13, yb, 16.5), (xa + 13, yb, 16.5)]
    Lo_out = (xa, yi - s * 4, 18.0)
    Up_in = [(xa - 11, yb, 46.0), (xa + 11, yb, 46.0)]
    Up_out = (xa, yi - s * 6, 46.0)
    dx = 6 if avant else -6
    piv = (xa + dx, s * (Y_CLOISON + E_CLOISON + 10.5), 62.0)   # culbuteur deporte : le verin passe a cote de la cloison   # culbuteur contre la cloison, au-dessus des triangles
    pr_bas = (xa, yi - s * 9, 20.0)                              # pushrod : du triangle inferieur...
    pr_haut = (piv[0] + (-8 if avant else 8), piv[1], piv[2] - 4)   # ...au bras bas du culbuteur
    cyl_a = (piv[0] + (2 if avant else -2), piv[1], piv[2] + 10)    # bras haut du culbuteur -> tige du verin
    sens = 1 if avant else -1                                    # verin vers l'interieur du chassis (AV vers l'arriere, AR vers l'avant)
    Lv = 46.0
    cyl_b = (cyl_a[0] + sens * Lv, cyl_a[1], cyl_a[2])
    rt = 2.2
    def bague(a, r):
        return tube((a[0] - 2.5, a[1], a[2]), (a[0] + 2.5, a[1], a[2]), r)
    tri_inf = union([tube(Lo_in[0], Lo_out, rt), tube(Lo_in[1], Lo_out, rt), boule(Lo_out, 3.6),
                     bague(Lo_in[0], 3.6), bague(Lo_in[1], 3.6), boule(pr_bas, 3.2)])
    for a in Lo_in:
        tri_inf = tri_inf - trou((a[0] - 6, a[1], a[2]), (a[0] + 6, a[1], a[2]))
    tri_sup = union([tube(Up_in[0], Up_out, rt * 0.9), tube(Up_in[1], Up_out, rt * 0.9), boule(Up_out, 3.4),
                     bague(Up_in[0], 3.4), bague(Up_in[1], 3.4)])
    for a in Up_in:
        tri_sup = tri_sup - trou((a[0] - 6, a[1], a[2]), (a[0] + 6, a[1], a[2]))
    # porte-moyeu : montant entre les rotules + fusee vers la roue (axe Y) + bras de direction a l'avant
    pm = union([tube(Lo_out, Up_out, 3.4), tube((xa, yi - s * 5, zr), (xa, yr, zr), 2.5),
                tube((xa, yi - s * 5, zr), (xa, yi + s * 2, zr), 5.0)])
    if avant:
        pm = pm + tube((xa, yi - s * 5, zr - 6), (xa + 14, yi - s * 9, zr - 6), 2.0)
    pm = pm - trou((xa, yr - s * 6, zr), (xa, yr + s * 2, zr), 1.0)
    # pushrod (tige a rotules) ; culbuteur : moyeu sur l'axe Y + 2 bras (pushrod, verin)
    push = union([tube(pr_bas, pr_haut, 1.6), boule(pr_bas, 2.6), boule(pr_haut, 2.6)])
    cul = union([tube((piv[0], piv[1] - s * 2.6, piv[2]), (piv[0], piv[1] + s * 2.6, piv[2]), 4.2),
                 tube(piv, pr_haut, 2.8), tube(piv, cyl_a, 2.8), tube(pr_haut, cyl_a, 2.0)])
    cul = cul - trou((piv[0], piv[1] - 6, piv[2]), (piv[0], piv[1] + 6, piv[2]))
    # ---- ARTICULATIONS montables : chaque liaison = un axe M3 commun aux 2 pieces ; la piece qui recoit est
    # evidee au contact (jeu 0.3 mm) : rien n'est soude, tout se visse.
    def axe(p_, d_, L=14):
        d_ = np.asarray(d_, float); d_ = d_ / np.linalg.norm(d_); p_ = np.asarray(p_, float)
        return trou(p_ - d_ * L / 2, p_ + d_ * L / 2)

    def logement(p_, d_, demi, r_):
        d_ = np.asarray(d_, float); p_ = np.asarray(p_, float)
        return tube(p_ - d_ * demi, p_ + d_ * demi, r_)
    ex, ey = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    # rotules exterieures : la boule du triangle s'insere entre 2 oreilles du porte-moyeu (chape), axe X
    for P_, cle in ((Lo_out, "inf"), (Up_out, "sup")):
        oreilles = union([tube(np.array(P_) - ex * 5.8, np.array(P_) - ex * 2.3, 3.8),
                          tube(np.array(P_) + ex * 2.3, np.array(P_) + ex * 5.8, 3.8)])
        pm = (pm + oreilles) - logement(P_, ex, 2.2, 4.3) - axe(P_, ex)
        if cle == "inf":
            tri_inf = tri_inf - logement(P_, ex, 6.0, 9.0) + (boule(P_, 3.6) ^ logement(P_, ex, 1.9, 9.0))
            tri_inf = tri_inf - axe(P_, ex)
        else:
            tri_sup = tri_sup - logement(P_, ex, 6.0, 9.0) + (boule(P_, 3.4) ^ logement(P_, ex, 1.9, 9.0))
            tri_sup = tri_sup - axe(P_, ex)
    # pushrod : extremites en oeillet (axe X) ; boule d'accroche du triangle inf. et bras du culbuteur en chape
    push = push - axe(pr_bas, ex) - axe(pr_haut, ex)
    tri_inf = tri_inf - logement(pr_bas, ex, 1.9, 3.6) - axe(pr_bas, ex)
    cul = cul - logement(pr_haut, ex, 1.9, 3.3) - axe(pr_haut, ex)
    pm = pm - logement(pr_bas, ex, 1.9, 3.6)
    # bras haut du culbuteur : chape pour l'oeillet de tige du verin (axe Y)
    cul = cul - logement(cyl_a, ey, 3.3, 3.9) - axe(cyl_a, ey)
    return {"triangle_inf": tri_inf, "triangle_sup": tri_sup, "porte_moyeu": pm, "pushrod": push, "culbuteur": cul}, \
        {"Lo_in": Lo_in, "Up_in": Up_in, "piv": piv, "cyl_a": cyl_a, "cyl_b": cyl_b, "yi": yi}


def verin_suspension_env(a, b):
    """Enveloppe du verin custom (alesage 12, tige 4) : corps cote ancrage, tige, oeillets (axe Y)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    u = (b - a) / np.linalg.norm(b - a)
    corps = tube(b - u * 5, b - u * 30, 8.5)
    tige = tube(a + u * 3, b - u * 30, 2.0)
    oy = np.array([0, 3.0, 0])
    oeil_a = tube(a - oy, a + oy, 3.5) - trou(a - 2 * oy, a + 2 * oy)
    oeil_b = tube(b - oy, b + oy, 3.5) - trou(b - 2 * oy, b + 2 * oy)
    return union([corps, tige, oeil_a, oeil_b, tube(b - u * 5, b, 3.0)])


def module(R, avant=True):
    """Module AV / AR : semelle vissée sur le plancher (4 x M3) + 2 CLOISONS de suspension (plan XZ) + traverse
    haute. Chaque cloison porte les 4 pivots des triangles, le pivot du culbuteur et la console du verin."""
    xa = R["xa"] if avant else R["xr"]
    zp, e = R["z_plancher"], R["e_plancher"]
    z0 = zp + e
    sens = 1 if avant else -1
    yc, ec = Y_CLOISON, E_CLOISON
    # semelle : entre le nez (pare-chocs) et la cabine
    xb0, xb1 = (xa - 46, R["x_cab_av"] - 4) if avant else (R["x_cab_ar"] + 4, xa + 52)
    elems = [mf.Manifold.cube((xb1 - xb0, 2 * (yc + ec), 3)).translate((xb0, -(yc + ec), z0))]
    coins, pts = {}, {}
    xc0, xc1 = xa - 22, xa + 22                                  # longueur des cloisons
    for s in (1, -1):
        c, k = coin(R, xa, s, avant)
        coins[s], pts[s] = c, k
        y0 = yc if s > 0 else -(yc + ec)
        # cloison : profil trapeze (large en bas, monte jusqu'au culbuteur)
        prof = Polygon([(xc0, z0), (xc1, z0), (xc1, 52), (k["piv"][0] + 9 * sens, k["piv"][2] + 7),
                        (k["piv"][0] - 9 * sens, k["piv"][2] + 7), (xc0, 52)]).buffer(0)
        cl = mf.Manifold.extrude(section(prof), ec).transform(np.array([[1, 0, 0, 0], [0, 0, 1, y0], [0, 1, 0, 0]], float))
        cl = cl - mf.Manifold.extrude(section(Polygon([(xa - 12, 24), (xa + 12, 24), (xa + 8, 40), (xa - 8, 40)])), ec + 2) \
            .transform(np.array([[1, 0, 0, 0], [0, 0, 1, y0 - 1], [0, 1, 0, 0]], float))           # allegement
        elems.append(cl)
        # console du verin : bras horizontal depuis la cloison jusqu'a l'ancrage (chape 2 joues)
        cb = k["cyl_b"]
        xcons = np.sign(cb[0] - k["piv"][0])
        pv = k["piv"]                                        # bossage d'axe du culbuteur (de la cloison au culbuteur)
        elems.append(tube((pv[0], s * (yc + ec), pv[2]), (pv[0], pv[1] - s * 3.0, pv[2]), 4.0))
        elems.append(tube((k["piv"][0] + 8 * xcons, s * (yc + ec / 2), cb[2] - 13), (cb[0], s * (yc + ec / 2), cb[2] - 13), 2.6))
        ya_, yb_ = sorted((s * (yc + ec / 2), cb[1] + s * 6.1))
        elems.append(mf.Manifold.cube((9, yb_ - ya_, 3)).translate((cb[0] - 4.5, ya_, cb[2] - 15)))      # semelle de chape
        for dy in (-4.6, 4.6):
            elems.append(mf.Manifold.cube((9, 3, 18)).translate((cb[0] - 4.5, cb[1] + dy - 1.5, cb[2] - 13)))
        # chapes des bagues de triangle (axe X) : 2 joues collees a la cloison, bague de 5 mm entre elles
        for a in k["Lo_in"] + k["Up_in"]:
            for dxj in (-4.1, 4.1):
                ya2, yb2 = sorted((s * (yc + ec), a[1] + s * 0.6))
                elems.append(mf.Manifold.cube((3, yb2 - ya2, 9)).translate((a[0] + dxj - 1.5, ya2, a[2] - 4.5)))
    # traverse haute + pattes de carrosserie (ailes / pare-chocs) a l'avant du nez
    elems.append(tube((xa - sens * 16, -(yc + ec), 56), (xa - sens * 16, yc + ec, 56), 2.6))
    bx = (xa - 44) if avant else (xa + 50)
    for y in (-40, 40):
        elems.append(tube((bx, np.sign(y) * (yc + 2), z0 + 1.5), (bx, y, 50.0), 2.4))
        elems.append(mf.Manifold.cube((8, 8, 3), True).translate((bx, y, 51.5)))
    m = union(elems)
    for s in (1, -1):                                          # percages des axes
        k = pts[s]
        for a in k["Lo_in"] + k["Up_in"]:
            m = m - trou((a[0] - 7, a[1], a[2]), (a[0] + 7, a[1], a[2]))             # axe M3 des triangles (axe X)
        pv, cb = k["piv"], k["cyl_b"]
        m = m - trou((pv[0], s * (yc - 1), pv[2]), (pv[0], pv[1] + s * 1, pv[2]))
        m = m - trou((cb[0], cb[1] - 8, cb[2]), (cb[0], cb[1] + 8, cb[2]))
    for x in ((xa + 30, xa + 46) if avant else (xa - 30, xa - 16)):          # 4 vis sur le plancher
        for y in (-14, 14):
            m = m - trou((x, y, z0 - 2), (x, y, z0 + 6))
    for y in (-40, 40):
        m = m - trou((bx, y, 48), (bx, y, 56))
    verins = {s: verin_suspension_env(pts[s]["cyl_a"], pts[s]["cyl_b"]) for s in (1, -1)}
    return m, coins, verins, pts


# ------------------------------------------------------------------ distributeur actif pilote par servo
def distributeur_servo(R, x, y=0.0, z=None, nom="AV"):
    """Distributeur a TIROIR (alesage 10, 2 joints 8x1) entraine par un servo SG90 via une biellette : position
    centrale = verins G et D isoles ; tiroir d'un cote = air vers G (et D a l'echappement), de l'autre = vers D.
    C'est le coeur de l'anti-roulis actif (Activa 2026)."""
    z = z if z is not None else R["z_plancher"] + R["e_plancher"] + 22
    L, d_al = 46.0, 10.0
    corps = mf.Manifold.cube((L, 22, 20)).translate((x - L / 2, y - 11, z))
    corps = corps - tube((x - L / 2 + 3, y, z + 10), (x + L / 2 + 1, y, z + 10), d_al / 2 + 0.05)
    for k, dx in enumerate((-12, 0, 12)):                       # G, P (pression), D sur le dessus ; E dessous
        corps = corps + tube((x + dx, y, z + 19), (x + dx, y, z + 26), 2.6)
        corps = corps - tube((x + dx, y, z + 9), (x + dx, y, z + 27), 0.9)
    corps = corps - tube((x - 18, y, z - 1), (x - 18, y, z + 11), 0.9) - tube((x + 18, y, z - 1), (x + 18, y, z + 11), 0.9)
    # support SG90 (23 x 12.5) en bout + pattes
    sup = mf.Manifold.cube((14, 32, 18)).translate((x + L / 2, y - 16, z))
    sup = sup - mf.Manifold.cube((12.8, 23.2, 20)).translate((x + L / 2 + 0.6, y - 11.6, z - 1))
    corps = corps + sup
    corps = corps - tube((x + L / 2 - 1, y, z + 10), (x + L / 2 + 15, y, z + 10), d_al / 2 + 0.6)     # passage tiroir -> servo
    tiroir = tube((x - L / 2 + 4, y, z + 10), (x + L / 2 + 8, y, z + 10), d_al / 2 - 0.25)
    # 2 gorges de joint torique 8 x 1 (fond d8.4, largeur 1.35) + gorge de passage centrale (relie G<->P ou P<->D)
    for zz in (-6, 6):
        tiroir = tiroir - (tube((x + zz - 0.68, y, z + 10), (x + zz + 0.68, y, z + 10), 6) - tube((x + zz - 0.7, y, z + 10), (x + zz + 0.7, y, z + 10), 4.2))
    tiroir = tiroir - (tube((x - 4, y, z + 10), (x + 4, y, z + 10), 6) - tube((x - 4.1, y, z + 10), (x + 4.1, y, z + 10), 3.4))
    tiroir = tiroir - trou((x + L / 2 + 5, y - 6, z + 10), (x + L / 2 + 5, y + 6, z + 10), 0.9)     # trou de biellette
    return corps, tiroir


# ------------------------------------------------------------------ assemblage complet
def chassis(p: dict):
    R = reperes(p)
    out = {}
    pl, fix = plancher(R)
    out["plancher"] = pl
    tun, rails, T = faux_plancher(R)
    out["faux_plancher"] = tun + rails
    out["tiroir_batterie"] = tiroir(T, 78, 12)
    out["tiroir_electronique"] = tiroir(T, T["x1"] - T["x0"] - 92, 12).translate((84, 0, 0))
    flancs, trav, N, ya = cage(R)
    out["cage_flanc_g"], out["cage_flanc_d"] = flancs[1], flancs[-1]
    for i, t in enumerate(trav):
        out[f"cage_traverse_{i + 1}"] = t
    for av, nom in ((True, "av"), (False, "ar")):
        m, coins, verins, pts = module(R, av)
        out[f"module_{nom}"] = m
        for s, cote in ((1, "g"), (-1, "d")):
            for k, v in coins[s].items():
                out[f"{k}_{nom}{cote}"] = v
            out[f"verin_{nom}{cote}"] = verins[s]
        corps, tir = distributeur_servo(R, (R["xa"] + 60) if av else (R["xr"] - 62), 0.0, nom=nom)
        out[f"distributeur_{nom}"] = corps
        out[f"tiroir_distrib_{nom}"] = tir
    info = {"empattement": round(R["xr"] - R["xa"], 1), "voie": R["voie"], "z_roue": R["zr"],
            "faux_plancher": {"longueur": round(T["x1"] - T["x0"], 1), "largeur": T["larg"], "hauteur": T["h"]},
            "quincaillerie": ["Vis M3 x 8 a 20 (cage, modules, triangles, culbuteurs) ~60 pieces",
                              "4 verins custom alesage 12 / tige 4 (joints 10x1 piston, 4x1.5 tige)",
                              "2 distributeurs a tiroir (joints 8x1) + 2 servos SG90",
                              "Tube LEGO / tube 4 mm, reservoir d'air (compresseur Wankel)"]}
    return out, info
