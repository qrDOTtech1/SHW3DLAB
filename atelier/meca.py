"""SHWORK : bibliotheque de pieces MECANIQUES parametriques (fondations pour bras robotises, RC, mecanismes).

Toutes les pieces sont etanches (manifold3d) et pensees pour l'impression FDM (jeux, chanfreins d'entree,
pas de porte-a-faux inutiles). Chaque generateur a un SCHEMA (champs, bornes, aide) : l'interface se construit
toute seule et un projet peut sauver / re-generer ses pieces.

Transmission : engrenage droit / helicoidal (developpante de cercle vraie), cremaillere, paire engrenee
  (entraxe calcule), poulie GT2.
Guidage : logement de roulement standard (608, 625, 688, 6001, 6202...), roulement a billes IMPRIME en place,
  arbre (rond, meplat D, rainure de clavette), entretoise, accouplement d'arbres.
Articulation : charniere imprimee en place (axe captif).
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as mf
import trimesh
from shapely.geometry import Polygon, Point, box as sbox
from shapely.ops import unary_union

from .c3d import section, vers_trimesh, vers_manifold

# ------------------------------------------------------------------ roulements standards (d_int, d_ext, largeur)
ROULEMENTS = {"608": (8, 22, 7), "625": (5, 16, 5), "688": (8, 16, 5), "626": (6, 19, 6), "6000": (10, 26, 8),
              "6001": (12, 28, 8), "6002": (15, 32, 9), "6200": (10, 30, 9), "6202": (15, 35, 11), "MR105": (5, 10, 4),
              "MR85": (5, 8, 2.5), "623": (3, 10, 4), "6800": (10, 19, 5), "6900": (10, 22, 6)}


def _cercle(r, n=128):
    return Point(0, 0).buffer(r, max(8, n // 4))


# ------------------------------------------------------------------ ENGRENAGES (developpante de cercle)
def _developpante(rb, t):
    return rb * (np.cos(t) + t * np.sin(t)), rb * (np.sin(t) - t * np.cos(t))


def profil_engrenage(module=1.0, dents=20, angle_pression=20.0, jeu=0.08, deport=0.0, interne=False):
    """Profil 2D d'une roue a developpante (shapely). jeu = amincissement de chaque flanc (backlash)."""
    z = int(dents)
    m = float(module)
    a = math.radians(angle_pression)
    rp = m * z / 2                                      # primitif
    rb = rp * math.cos(a)                               # base
    ra = rp + m * (1 + deport)                          # tete
    rf = max(rp - m * (1.25 - deport), 0.5)             # pied
    # epaisseur angulaire de la dent au primitif (moins le jeu)
    ep = (math.pi * m / 2 + 2 * deport * m * math.tan(a) - 2 * jeu) / rp
    inv = lambda alpha: math.tan(alpha) - alpha
    t_max = math.sqrt(max((ra / rb) ** 2 - 1, 0))
    ts = np.linspace(0, t_max, 24)
    x, y = _developpante(rb, ts)
    ang0 = ep / 2 + inv(a)                              # angle du flanc a la base
    th = np.arctan2(y, x)
    r = np.hypot(x, y)
    # flanc droit (tourne de -ang0) et gauche (miroir)
    fl_d = np.c_[r * np.cos(-ang0 + th), r * np.sin(-ang0 + th)]
    fl_g = np.c_[r * np.cos(ang0 - th), r * np.sin(ang0 - th)][::-1]
    tete_a = np.linspace(-ang0 + th[-1], ang0 - th[-1], 6)
    tete = np.c_[ra * np.cos(tete_a), ra * np.sin(tete_a)]
    base_r = min(rb, rf) if rf < rb else rf
    pied_d = np.array([[rf * math.cos(-ang0) * 0.999, rf * math.sin(-ang0)]])
    pied_g = np.array([[rf * math.cos(ang0) * 0.999, rf * math.sin(ang0)]])
    dent = Polygon(np.vstack([[0, 0], pied_d, fl_d, tete, fl_g, pied_g])).buffer(0)
    roue = [_cercle(rf, 4 * z)]
    for k in range(z):
        roue.append(_rot(dent, 360.0 * k / z))
    p = unary_union(roue).buffer(m * 0.08, join_style=1).buffer(-m * 0.08, join_style=1)   # conges de pied
    p = p.simplify(m * 0.006)                           # profil leger (ecart < 1 % du module)
    return p, {"r_primitif": rp, "r_tete": ra, "r_pied": rf, "r_base": rb}


def _rot(p, deg):
    from shapely import affinity
    return affinity.rotate(p, deg, origin=(0, 0))


def engrenage(p: dict):
    g = lambda k, d: float(p.get(k, d))
    m, z, e = g("module", 1.5), int(g("dents", 20)), g("epaisseur", 8)
    prof, info = profil_engrenage(m, z, g("angle_pression", 20), g("jeu", 0.08), g("deport", 0))
    helice = g("helice", 0)
    torsion = math.degrees(e * math.tan(math.radians(helice)) / info["r_primitif"]) if helice else 0
    if g("chevrons", 0) and helice:                     # chevrons : 2 demi-roues helicoidales opposees
        # le miroir de la 1re moitie (z -> e - z) se raccorde exactement a mi-hauteur (meme angle t/2)
        dv = max(1, int(abs(torsion) / 2 / 3))
        demi = mf.Manifold.extrude(section(prof), e / 2, dv, torsion / 2)
        s = demi + demi.mirror((0, 0, 1)).translate((0, 0, e))
    else:
        s = mf.Manifold.extrude(section(prof), e, max(1, int(abs(torsion) / 4)), torsion)
    # moyeu
    mh, md = g("moyeu_h", 0), g("moyeu_d", 0)
    if mh > 0 and md > 0:
        s = s + mf.Manifold.cylinder(mh, md / 2, md / 2, 96).translate((0, 0, e - 0.01))
    # alesage (rond ou D), allegements
    al = g("alesage", 5)
    if al > 0:
        trou = _cercle(al / 2 + g("jeu_alesage", 0.15), 64)
        if g("meplat", 0):
            trou = trou.difference(sbox(al / 2 - g("meplat", 0.5), -al, al, al))
        s = s - mf.Manifold.extrude(section(trou), e + mh + 2).translate((0, 0, -1))
    n_all = int(g("allegements", 0))
    if n_all >= 3 and info["r_pied"] - (al / 2 + 2) > 6:
        r1, r2 = max(al / 2 + 2.5, md / 2 + 1 if md else 0), info["r_pied"] - 2.5
        rc, rr = (r1 + r2) / 2, (r2 - r1) / 2
        rr = min(rr, rc * math.sin(math.pi / n_all) - 1.2)
        if rr > 1.5:
            for k in range(n_all):
                a = 2 * math.pi * k / n_all
                s = s - mf.Manifold.cylinder(e + 2, rr, rr, 48).translate((rc * math.cos(a), rc * math.sin(a), -1))
    info.update({"module": m, "dents": z, "torsion_deg": round(torsion, 2)})
    return vers_trimesh(s), info


def cremaillere(p: dict):
    g = lambda k, d: float(p.get(k, d))
    m, L, e, h = g("module", 1.5), g("longueur", 80), g("epaisseur", 8), g("hauteur", 8)
    a = math.radians(g("angle_pression", 20))
    pas = math.pi * m
    n = int(L / pas) + 1
    jeu = g("jeu", 0.08)
    pts = [(0, 0)]
    for k in range(n):
        x0 = k * pas
        ha, hf = m, 1.25 * m
        w_tete = pas / 2 - 2 * ha * math.tan(a) - 2 * jeu
        w_pied = pas / 2 + 2 * hf * math.tan(a) - 2 * jeu
        c = x0 + pas / 2
        pts += [(c - w_pied / 2, h), (c - w_tete / 2, h + ha + hf), (c + w_tete / 2, h + ha + hf), (c + w_pied / 2, h)]
    pts += [(n * pas, h), (n * pas, 0)]
    prof = Polygon(pts).buffer(0).intersection(sbox(0, 0, L, h + 3 * m))
    s = mf.Manifold.extrude(section(prof), e)
    return vers_trimesh(s), {"pas_mm": round(pas, 3), "dents": n}


def paire_engrenages(p: dict):
    """Pignon + roue deja places a l'ENTRAXE exact (+ jeu de montage)."""
    z1, z2 = int(p.get("dents_pignon", 12)), int(p.get("dents_roue", 36))
    m = float(p.get("module", 1.5))
    q = {**p, "module": m}
    a, ia = engrenage({**q, "dents": z1, "alesage": p.get("alesage_pignon", 5)})
    b, ib = engrenage({**q, "dents": z2, "alesage": p.get("alesage_roue", 8), "helice": -float(p.get("helice", 0))})
    entraxe = m * (z1 + z2) / 2 + float(p.get("jeu_entraxe", 0.1))
    # demi-pas de decalage si nombre pair pour que les dents s'emboitent
    if z2 % 2 == 0:
        b.apply_transform(trimesh.transformations.rotation_matrix(math.pi / z2, [0, 0, 1]))
    b.apply_translation([entraxe, 0, 0])
    return [a, b], {"entraxe_mm": round(entraxe, 3), "rapport": round(z2 / z1, 3), "pignon": ia, "roue": ib,
                    "animation": [{"piece": 0, "axe": [0, 0], "vitesse": 1.0}, {"piece": 1, "axe": [entraxe, 0], "vitesse": -z1 / z2}]}


def poulie_gt2(p: dict):
    g = lambda k, d: float(p.get(k, d))
    z, w, al = int(g("dents", 20)), g("largeur", 7), g("alesage", 5)
    pas = 2.0
    rp = z * pas / (2 * math.pi)
    r = rp - 0.254                                    # rayon exterieur (PLD GT2)
    base = _cercle(r, 4 * z)
    for k in range(z):
        a = 2 * math.pi * k / z
        dent = Point(r * math.cos(a), r * math.sin(a)).buffer(0.555, 16)
        base = base.difference(dent)
    s = mf.Manifold.extrude(section(base), w)
    fl = g("flasques", 1)
    if fl:
        f = mf.Manifold.cylinder(1.0, r + 1.2, r + 1.2, 96)
        s = s + f.translate((0, 0, -1.0)) + f.translate((0, 0, w))
    moy = g("moyeu_h", 6)
    if moy > 0:
        s = s + mf.Manifold.cylinder(moy, max(al / 2 + 3, 6), max(al / 2 + 3, 6), 64).translate((0, 0, -1.0 - moy + 0.01))
        # trou de vis de pression M3
        s = s - mf.Manifold.cylinder(r + 10, 1.6, 1.6, 24).rotate((0, 90, 0)).translate((0, 0, -1.0 - moy / 2))
    s = s - mf.Manifold.cylinder(w + moy + 6, al / 2 + 0.12, al / 2 + 0.12, 48).translate((0, 0, -moy - 3))
    m = vers_trimesh(s)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m, {"diametre_primitif": round(2 * rp, 2), "dents": z}


# ------------------------------------------------------------------ GUIDAGE
def logement_roulement(p: dict):
    """Palier a semelle (2 trous de fixation) ou bride ronde, avec logement serre du roulement standard."""
    ref = p.get("reference", "608")
    di, de, b = ROULEMENTS.get(ref, ROULEMENTS["608"])
    serrage = float(p.get("serrage", -0.05))            # negatif = serre (FDM : -0.05 a +0.1)
    paroi = float(p.get("paroi", 4))
    forme = p.get("forme", "semelle")
    re = de / 2 + paroi
    h = b + 2.0                                          # 2 mm d'epaulement sous le roulement
    if forme == "bride":
        corps = _cercle(re + 7, 128).difference(unary_union(
            [Point((re + 3.5) * math.cos(a), (re + 3.5) * math.sin(a)).buffer(1.7, 16) for a in np.linspace(0, 2 * math.pi, 4, endpoint=False)]))
        s = mf.Manifold.extrude(section(corps), h)
    else:
        # palier a semelle, imprime A PLAT : corps rond + jambe + semelle percee de 2 trous verticaux (axe Y)
        L = 2 * re + 22
        corps = unary_union([_cercle(re, 128), sbox(-re, -re - 6, re, 0),
                             sbox(-L / 2, -re - 6, L / 2, -re).buffer(1.5, join_style=1).buffer(-1.5, join_style=1)])
        s = mf.Manifold.extrude(section(corps), h)
        for x in (-L / 2 + 5.5, L / 2 - 5.5):
            s = s - mf.Manifold.cylinder(10, 1.7, 1.7, 24).rotate((90, 0, 0)).translate((x, -re + 2, h / 2))
    log = mf.Manifold.cylinder(b + 0.05, de / 2 + serrage, de / 2 + serrage, 128).translate((0, 0, 2.0))
    chanf = mf.Manifold.cylinder(0.6, de / 2 + serrage, de / 2 + serrage + 0.6, 128).translate((0, 0, h - 0.6 + 0.001))
    epaul = mf.Manifold.cylinder(h + 2, de / 2 - 1.2, de / 2 - 1.2, 96).translate((0, 0, -1))
    s = s - log - chanf - epaul
    m = vers_trimesh(s)
    m.apply_translation([-m.bounds.mean(0)[0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
    return m, {"roulement": ref, "d_int": di, "d_ext": de, "largeur": b, "quincaillerie": [f"Roulement {ref} ({di}x{de}x{b})"]}


def roulement_imprime(p: dict):
    """Roulement a billes imprime EN PLACE (bagues + billes captives, une seule impression, aucun montage)."""
    g = lambda k, d: float(p.get(k, d))
    di, de, b = g("d_int", 8), g("d_ext", 30), g("largeur", 10)
    jeu = g("jeu", 0.35)
    rm = (di / 2 + de / 2) / 2                           # rayon moyen des billes
    db = min(b - 2.4, (de - di) / 2 - 3.2)               # diametre des billes
    n = max(6, int(2 * math.pi * rm / (db + 1.2)))
    bague_int = mf.Manifold.cylinder(b, rm - db * 0.18, rm - db * 0.18, 128) - mf.Manifold.cylinder(b + 2, di / 2, di / 2, 96).translate((0, 0, -1))
    bague_ext = mf.Manifold.cylinder(b, de / 2, de / 2, 128) - mf.Manifold.cylinder(b + 2, rm + db * 0.18, rm + db * 0.18, 128).translate((0, 0, -1))
    gorge = mf.Manifold.revolve(mf.CrossSection.circle(db / 2 + jeu, 48).translate((rm, b / 2)), 128)
    s = (bague_int - gorge) + (bague_ext - gorge)
    for k in range(n):
        a = 2 * math.pi * k / n
        s = s + mf.Manifold.sphere(db / 2, 32).translate((rm * math.cos(a), rm * math.sin(a), b / 2))
    return vers_trimesh(s), {"billes": n, "d_bille": round(db, 2), "jeu": jeu,
                             "conseil": "Imprimer a plat, sans support, couche <= 0.2 ; casser les billes a la main apres impression"}


def arbre(p: dict):
    g = lambda k, d: float(p.get(k, d))
    d, L = g("d", 8), g("longueur", 60)
    prof = _cercle(d / 2, 96)
    if g("meplat", 0) > 0:
        prof = prof.difference(sbox(d / 2 - g("meplat", 0.5), -d, d, d))
    s = mf.Manifold.extrude(section(prof), L)
    if g("clavette", 0) > 0:
        w = g("clavette", 2)
        s = s - mf.Manifold.cube((w, d, L * 0.6)).translate((-w / 2, d / 2 - w / 2, L * 0.2))
    ch = min(0.6, d * 0.08)
    s = s - (mf.Manifold.cylinder(ch, d / 2 + 1, d / 2 + 1, 64) - mf.Manifold.cylinder(ch, d / 2 - ch, d / 2, 64)).translate((0, 0, -0.001))
    m = vers_trimesh(s)
    return m, {"conseil": "Imprimer COUCHE (axe horizontal) pour la solidite en flexion"}


def entretoise(p: dict):
    g = lambda k, d: float(p.get(k, d))
    return vers_trimesh(mf.Manifold.cylinder(g("longueur", 5), g("d_ext", 12) / 2, g("d_ext", 12) / 2, 96)
                        - mf.Manifold.cylinder(g("longueur", 5) + 2, g("d_int", 8.2) / 2, g("d_int", 8.2) / 2, 64).translate((0, 0, -1))), {}


def accouplement(p: dict):
    g = lambda k, d: float(p.get(k, d))
    d1, d2, L, D = g("d1", 5), g("d2", 8), g("longueur", 25), g("d_ext", 20)
    s = mf.Manifold.cylinder(L, D / 2, D / 2, 96)
    s = s - mf.Manifold.cylinder(L / 2 + 0.5, d1 / 2 + 0.1, d1 / 2 + 0.1, 64).translate((0, 0, -0.5))
    s = s - mf.Manifold.cylinder(L / 2 + 0.5, d2 / 2 + 0.1, d2 / 2 + 0.1, 64).translate((0, 0, L / 2))
    for z in (L / 4, 3 * L / 4):                        # vis de pression M3 + logement d'ecrou
        s = s - mf.Manifold.cylinder(D, 1.6, 1.6, 24).rotate((0, 90, 0)).translate((0, 0, z))
        s = s - mf.Manifold.cube((2.6, 5.8, 6.4), True).translate((D / 2 - 4, 0, z))
    return vers_trimesh(s), {"quincaillerie": ["2 vis M3x8 + 2 ecrous M3"]}


# ------------------------------------------------------------------ ARTICULATION
def charniere(p: dict):
    """Charniere imprimee EN PLACE : noeuds alternes, axe solidaire des noeuds pairs, jeu radial + cones
    (le noeud imprime au-dessus d'un autre ne se soude pas)."""
    g = lambda k, d: float(p.get(k, d))
    L, D, n = g("longueur", 60), g("diametre", 8), int(g("noeuds", 5))
    jeu, ail, e = g("jeu", 0.4), g("aile", 25), g("epaisseur", 3)
    n = max(3, n | 1)
    lk = (L - (n - 1) * jeu) / n
    s_a, s_b = None, None
    axe_r = D / 2 - 1.6
    for k in range(n):
        y0 = k * (lk + jeu)
        tube = mf.Manifold.cylinder(lk, D / 2, D / 2, 64).rotate((-90, 0, 0)).translate((0, y0, D / 2))
        if k % 2 == 0:
            s_a = tube if s_a is None else s_a + tube
        else:
            trou = mf.Manifold.cylinder(lk + 2, axe_r + jeu, axe_r + jeu, 48).rotate((-90, 0, 0)).translate((0, y0 - 1, D / 2))
            t = tube - trou
            s_b = t if s_b is None else s_b + t
    axe = mf.Manifold.cylinder(L, axe_r, axe_r, 48).rotate((-90, 0, 0)).translate((0, 0, D / 2))
    s_a = s_a + axe
    aile_a = mf.Manifold.cube((ail, L, e)).translate((-ail - D / 2 + 1.5, 0, 0))
    aile_b = mf.Manifold.cube((ail, L, e)).translate((D / 2 - 1.5, 0, 0))
    # les ailes ne touchent que leurs propres noeuds
    vide_a = vide_b = None
    for k in range(n):
        y0 = k * (lk + jeu)
        bloc = mf.Manifold.cube((D + 2 * jeu + 0.01, lk + 2 * jeu, D + 2)).translate((-(D + 2 * jeu) / 2, y0 - jeu, -1))
        if k % 2 == 0:
            vide_b = bloc if vide_b is None else vide_b + bloc
        else:
            vide_a = bloc if vide_a is None else vide_a + bloc
    s_a = s_a + (aile_a - vide_a)
    s_b = s_b + (aile_b - vide_b)
    # trous de vis fraises dans les ailes
    for x in (-ail / 2 - D / 2, ail / 2 + D / 2):
        for y in (L * 0.2, L * 0.8):
            v = mf.Manifold.cylinder(e + 2, 1.75, 1.75, 24).translate((x, y, -1)) + mf.Manifold.cylinder(1.6, 1.75, 3.5, 24).translate((x, y, e - 1.6))
            s_a, s_b = s_a - v, s_b - v
    return vers_trimesh(s_a + s_b), {"noeuds": n, "jeu": jeu, "conseil": "Imprimer a plat, ailes sur le plateau ; faire jouer a la main apres impression"}


# ------------------------------------------------------------------ CATALOGUE (schemas -> interface automatique)
def _c(k, label, val, mini=None, maxi=None, pas=None, type_="nombre", options=None, aide=""):
    return {"k": k, "label": label, "val": val, "min": mini, "max": maxi, "pas": pas, "type": type_, "options": options, "aide": aide}


CATALOGUE = {
    "engrenage": {"nom": "Engrenage droit / helicoidal", "cat": "Transmission", "fn": engrenage, "champs": [
        _c("module", "Module", 1.5, 0.5, 5, 0.25, aide="taille des dents (1 = petit, 2 = robuste)"), _c("dents", "Nombre de dents", 20, 6, 200, 1),
        _c("epaisseur", "Epaisseur", 8, 2, 60, 0.5), _c("helice", "Angle d'helice (0 = droit)", 0, -45, 45, 1),
        _c("chevrons", "Chevrons (helices opposees)", 0, type_="bool"), _c("angle_pression", "Angle de pression", 20, 14.5, 25, 0.5),
        _c("alesage", "Alesage", 5, 0, 60, 0.1), _c("meplat", "Meplat (D)", 0, 0, 3, 0.1),
        _c("moyeu_d", "Moyeu diametre", 0, 0, 80, 0.5), _c("moyeu_h", "Moyeu hauteur", 0, 0, 40, 0.5),
        _c("allegements", "Allegements (trous)", 0, 0, 12, 1), _c("jeu", "Jeu par flanc (backlash)", 0.08, 0, 0.3, 0.01)]},
    "paire": {"nom": "Paire d'engrenages (entraxe auto)", "cat": "Transmission", "fn": paire_engrenages, "champs": [
        _c("module", "Module", 1.5, 0.5, 5, 0.25), _c("dents_pignon", "Dents du pignon", 12, 6, 100, 1), _c("dents_roue", "Dents de la roue", 36, 6, 200, 1),
        _c("epaisseur", "Epaisseur", 8, 2, 60, 0.5), _c("helice", "Helice", 0, -45, 45, 1),
        _c("alesage_pignon", "Alesage pignon", 5, 0, 30, 0.1), _c("alesage_roue", "Alesage roue", 8, 0, 60, 0.1),
        _c("jeu_entraxe", "Jeu d'entraxe", 0.1, 0, 0.5, 0.01), _c("allegements", "Allegements", 0, 0, 12, 1)]},
    "cremaillere": {"nom": "Cremaillere", "cat": "Transmission", "fn": cremaillere, "champs": [
        _c("module", "Module", 1.5, 0.5, 5, 0.25), _c("longueur", "Longueur", 80, 10, 210, 1), _c("epaisseur", "Epaisseur", 8, 2, 40, 0.5),
        _c("hauteur", "Hauteur sous dents", 8, 2, 40, 0.5), _c("jeu", "Jeu", 0.08, 0, 0.3, 0.01)]},
    "poulie_gt2": {"nom": "Poulie GT2", "cat": "Transmission", "fn": poulie_gt2, "champs": [
        _c("dents", "Dents", 20, 10, 80, 1), _c("largeur", "Largeur courroie", 7, 6, 12, 0.5), _c("alesage", "Alesage", 5, 2, 12, 0.1),
        _c("flasques", "Flasques", 1, type_="bool"), _c("moyeu_h", "Moyeu (vis de pression)", 6, 0, 15, 0.5)]},
    "logement_roulement": {"nom": "Palier / logement de roulement", "cat": "Guidage", "fn": logement_roulement, "champs": [
        _c("reference", "Roulement", "608", type_="choix", options=list(ROULEMENTS)), _c("forme", "Forme", "semelle", type_="choix", options=["semelle", "bride"]),
        _c("paroi", "Paroi", 4, 2, 10, 0.5), _c("serrage", "Serrage (negatif = serre)", -0.05, -0.2, 0.2, 0.01)]},
    "roulement_imprime": {"nom": "Roulement a billes imprime", "cat": "Guidage", "fn": roulement_imprime, "champs": [
        _c("d_int", "Diametre interieur", 8, 3, 60, 0.5), _c("d_ext", "Diametre exterieur", 30, 15, 150, 0.5),
        _c("largeur", "Largeur", 10, 6, 30, 0.5), _c("jeu", "Jeu des billes", 0.35, 0.2, 0.6, 0.05)]},
    "arbre": {"nom": "Arbre / axe", "cat": "Guidage", "fn": arbre, "champs": [
        _c("d", "Diametre", 8, 2, 40, 0.1), _c("longueur", "Longueur", 60, 5, 210, 1), _c("meplat", "Meplat (D)", 0, 0, 3, 0.1),
        _c("clavette", "Rainure de clavette (largeur)", 0, 0, 8, 0.5)]},
    "entretoise": {"nom": "Entretoise", "cat": "Guidage", "fn": entretoise, "champs": [
        _c("d_int", "Diametre interieur", 8.2, 1, 40, 0.1), _c("d_ext", "Diametre exterieur", 12, 3, 60, 0.5), _c("longueur", "Longueur", 5, 0.5, 100, 0.5)]},
    "accouplement": {"nom": "Accouplement d'arbres", "cat": "Guidage", "fn": accouplement, "champs": [
        _c("d1", "Arbre 1", 5, 2, 20, 0.1), _c("d2", "Arbre 2", 8, 2, 20, 0.1), _c("longueur", "Longueur", 25, 10, 60, 1), _c("d_ext", "Diametre ext.", 20, 10, 40, 0.5)]},
    "charniere": {"nom": "Charniere imprimee en place", "cat": "Articulation", "fn": charniere, "champs": [
        _c("longueur", "Longueur", 60, 20, 200, 1), _c("diametre", "Diametre des noeuds", 8, 5, 20, 0.5), _c("noeuds", "Noeuds (impair)", 5, 3, 15, 2),
        _c("aile", "Largeur des ailes", 25, 8, 80, 1), _c("epaisseur", "Epaisseur des ailes", 3, 1.5, 8, 0.5), _c("jeu", "Jeu", 0.4, 0.2, 0.8, 0.05)]},
}


def generer_piece(nom: str, params: dict):
    c = CATALOGUE.get(nom)
    if not c:
        raise ValueError(f"piece inconnue : {nom}")
    p = {f["k"]: f["val"] for f in c["champs"]}
    p.update({k: v for k, v in params.items() if v not in (None, "")})
    r, info = c["fn"](p)
    ms = r if isinstance(r, list) else [r]
    return ms, info


# ================================================================== PNEUMATIQUE (joints toriques du commerce)
# joints toriques metriques NBR courants : (diametre interieur, tore)
JOINTS = [(d, 1.0) for d in (2, 3, 4, 5, 6, 7, 8, 9, 10)] + [(d, 1.5) for d in range(3, 17)] + \
         [(d, 2.0) for d in (6, 8, 10, 12, 14, 15, 16, 18, 20, 22, 24, 25, 26, 28, 30, 32)] + \
         [(d, 2.5) for d in (15, 18, 20, 22, 25, 28, 30, 32, 35, 38, 40)] + \
         [(d, 3.0) for d in (20, 25, 28, 30, 32, 35, 38, 40, 45, 50, 55, 60)]


def gorge(diam, cote="piston", dynamique=True, tore=None):
    """Choisit un joint du commerce et dimensionne la gorge.
    cote = "piston" : gorge EXTERIEURE sur une piece qui glisse dans un alesage de diametre `diam` ;
    cote = "tige"   : gorge INTERIEURE dans un alesage, autour d'une tige de diametre `diam`."""
    taux = 0.80 if dynamique else 0.72                      # profondeur / tore (ecrasement 20-28 %)
    cands = []
    for di, c in JOINTS:
        if tore and abs(c - tore) > 1e-6:
            continue
        prof = c * taux
        if cote == "piston":
            fond = diam - 2 * prof                          # diametre a fond de gorge
            etir = fond / di - 1                            # le joint est etire de 0-6 % sur le fond
            if 0 <= etir <= 0.06:
                cands.append((abs(etir - 0.02) + abs(c - max(1.5, diam * 0.09)) * 0.1, di, c, prof, fond))
        else:
            fond = diam + 2 * prof
            comp = di / diam - 1                            # joint de tige : serre la tige (0-5 % plus petit)
            if -0.05 <= comp <= 0.0:
                cands.append((abs(comp + 0.02) + abs(c - max(1.5, diam * 0.15)) * 0.1, di, c, prof, fond))
    if not cands:
        raise ValueError(f"aucun joint standard pour {cote} d{diam:g} : essaie un diametre voisin (pair de preference)")
    _, di, c, prof, fond = min(cands)
    return {"joint": f"Joint torique {di:g} x {c:g} NBR", "di": di, "tore": c, "profondeur": round(prof, 2),
            "largeur": round(c * 1.35, 2), "fond": round(fond, 2)}


def _gorge_ext(fond, ext, larg, z):
    """Anneau a retirer (gorge exterieure) entre les diametres fond et ext, de largeur larg, centre en z."""
    return (mf.Manifold.cylinder(larg, ext / 2 + 1, ext / 2 + 1, 96) - mf.Manifold.cylinder(larg, fond / 2, fond / 2, 96)).translate((0, 0, z - larg / 2))


def _cannele(d_tube=4.0, L=12.0, perce=2.0):
    """Embout cannele (tube souple de diametre interieur d_tube) : 3 cones anti-retour, canal central."""
    s = mf.Manifold.cylinder(L, d_tube / 2 * 0.95, d_tube / 2 * 0.95, 48)
    for k in range(3):
        z = 1.5 + k * (L - 3) / 3
        s = s + mf.Manifold.cylinder((L - 3) / 3 * 0.9, d_tube / 2 * 1.18, d_tube / 2 * 0.9, 48).translate((0, 0, z))
    return s - mf.Manifold.cylinder(L + 2, perce / 2, perce / 2, 32).translate((0, 0, -1))


def _carre_arrondi(c, r):
    return sbox(-c / 2, -c / 2, c / 2, c / 2).buffer(-r, join_style=1).buffer(r, join_style=1)


def verin(p: dict):
    """Verin pneumatique imprime : corps (fond + orifice), tete vissee (4 vis M3) avec joint de tige et joint
    statique, piston a joint, tige. Simple effet (ressort de rappel) ou double effet. Pieces eclatees en X."""
    g = lambda k, d: float(p.get(k, d))
    D, course, d = g("alesage", 20), g("course", 40), g("tige", 6)
    paroi, double = g("paroi", 3.0), int(g("double_effet", 1))
    d_tube = g("tube", 4)
    jp = gorge(D, "piston")
    jt = gorge(d, "tige")
    e_pis = max(8.0, jp["largeur"] + 5)
    L_int = course + e_pis + 2
    De = D + 2 * paroi
    fond = 4.0
    # ---------------- corps : tube + fond + bride de tete (4 vis M3) + orifice arriere
    corps = mf.Manifold.cylinder(fond + L_int, De / 2, De / 2, 128) - mf.Manifold.cylinder(L_int + 1, D / 2, D / 2, 128).translate((0, 0, fond))
    bride_r = De / 2 + 5
    bride = mf.Manifold.extrude(section(_carre_arrondi(2 * bride_r, 3)), 5).translate((0, 0, fond + L_int - 5))
    corps = corps + (bride - mf.Manifold.cylinder(40, D / 2, D / 2, 128).translate((0, 0, fond)))
    vis = [(sx * (bride_r - 3.2), sy * (bride_r - 3.2)) for sx in (-1, 1) for sy in (-1, 1)]
    for x, y in vis:
        corps = corps - mf.Manifold.cylinder(12, 1.25, 1.25, 24).translate((x, y, fond + L_int - 11.99))   # avant-trou M3
    po = p.get("orifice", "cannele")
    corps = _ajouter_orifice(corps, po, np.array([De / 2 - 1.0, 0, fond + 3.5]), (1, 0, 0), d_tube, 2.0)
    corps = corps - mf.Manifold.cylinder(De, 1.0, 1.0, 24).rotate((0, 90, 0)).translate((0, 0, fond + 3.5))
    # ---------------- tete : bride + emboitement (joint statique) + gorge de tige (+ orifice avant)
    h_tete = 12.0
    tete = mf.Manifold.extrude(section(_carre_arrondi(2 * bride_r, 3)), 5)
    tete = tete + mf.Manifold.cylinder(h_tete - 5, D / 2 - 0.15, D / 2 - 0.15, 128).translate((0, 0, -(h_tete - 5)))
    js = gorge(D - 0.3, "piston", dynamique=False)
    tete = tete - _gorge_ext(js["fond"], D, js["largeur"], -(h_tete - 5) / 2)
    tete = tete - mf.Manifold.cylinder(40, d / 2 + 0.25, d / 2 + 0.25, 64).translate((0, 0, -20))
    tete = tete - mf.Manifold.cylinder(jt["largeur"], jt["fond"] / 2, jt["fond"] / 2, 64).translate((0, 0, 1.0))
    for x, y in vis:
        tete = tete - mf.Manifold.cylinder(20, 1.7, 1.7, 24).translate((x, y, -10)) - mf.Manifold.cylinder(3, 3.1, 3.1, 24).translate((x, y, 2.5))
    if double:
        tete = _ajouter_orifice(tete, po, np.array([bride_r - 1.0, 0, 2.5]), (1, 0, 0), d_tube, 2.0)
        tete = tete - mf.Manifold.cylinder(bride_r + 1, 1.0, 1.0, 24).rotate((0, 90, 0)).translate((0, 0, 2.5))
        tete = tete - mf.Manifold.cylinder(14, 1.0, 1.0, 24).translate((D / 2 - 2.5, 0, -(h_tete - 5) - 1))
    # ---------------- piston (gorge exterieure, alesage borgne pour la tige)
    piston = mf.Manifold.cylinder(e_pis, D / 2 - 0.25, D / 2 - 0.25, 128)
    piston = piston - _gorge_ext(jp["fond"], D, jp["largeur"], e_pis / 2)
    piston = piston - mf.Manifold.cylinder(e_pis - 2, d / 2 + 0.1, d / 2 + 0.1, 64).translate((0, 0, 2.01))
    # ---------------- tige (tige acier rectifiee recommandee ; version imprimee pour essais)
    L_tige = course + h_tete + 15
    tige = mf.Manifold.cylinder(L_tige, d / 2, d / 2, 64) + mf.Manifold.cylinder(8, d / 2 + 2, d / 2 + 2, 6).translate((0, 0, L_tige - 8))
    if int(g("oeillets", 0)):                               # montage a OEILLETS (suspension) : axe M3 aux deux bouts
        oe = mf.Manifold.cylinder(7, 3.6, 3.6, 32).rotate((90, 0, 0)).translate((0, 3.5, 0))
        tige = mf.Manifold.cylinder(L_tige, d / 2, d / 2, 64) + oe.translate((0, 0, L_tige + 2.5))             + mf.Manifold.cylinder(3, d / 2 + 0.8, 3.0, 32).translate((0, 0, L_tige - 0.5))
        tige = tige - mf.Manifold.cylinder(10, 1.65, 1.65, 24).rotate((90, 0, 0)).translate((0, 5, L_tige + 2.5))
        chape = (mf.Manifold.cube((De, 7, 9)).translate((-De / 2, -3.5, -9)) - mf.Manifold.cylinder(10, 1.65, 1.65, 24).rotate((90, 0, 0)).translate((0, 5, -4.5)))
        corps = corps + chape
    out, x = [], 0.0
    for s_ in (corps, tete, piston, tige):
        m = vers_trimesh(s_)
        m.apply_translation([x - m.bounds[0][0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
        out.append(m)
        x = m.bounds[1][0] + 8
    S = math.pi * (D / 2) ** 2
    q = ["4 vis M3x12", jp["joint"] + " (piston)", jt["joint"] + " (tige)", js["joint"] + " (tete, statique)",
         f"Tube pneumatique d{d_tube:g} mm interieur", "Graisse silicone"]
    if not double:
        q.append(f"Ressort de rappel d < {D - 2:g} mm, longueur libre > {course + 5:g} mm")
    return out, {"alesage": D, "course": course,
                 "force_sortie_6bar_N": round(S * 0.6, 1), "force_rentree_6bar_N": round((S - math.pi * (d / 2) ** 2) * 0.6, 1),
                 "joint_piston": jp["joint"], "joint_tige": jt["joint"], "quincaillerie": q,
                 "conseil": "PETG ou PLA+ ; poncer l'alesage (grain 600 puis 1000) et graisser ; tige acier rectifiee recommandee"}


def raccord(p: dict):
    """Raccord cannele pour tube souple : droit (ou reduction), coude, T, Y, croix."""
    g = lambda k, d: float(p.get(k, d))
    d1, d2, forme = g("tube", 4), g("tube2", 4), p.get("forme", "T")
    c = max(d1, d2) * 1.25 + 2
    s = mf.Manifold.sphere(c / 2, 48)
    canal = mf.Manifold.sphere(1.0, 16)
    bras = {"droit": [(0, 0, 1), (0, 0, -1)], "coude": [(0, 0, 1), (1, 0, 0)], "T": [(0, 0, 1), (0, 0, -1), (1, 0, 0)],
            "Y": [(0, 0, -1), (math.sin(0.6), 0, math.cos(0.6)), (-math.sin(0.6), 0, math.cos(0.6))],
            "croix": [(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0)]}[forme]
    for k, vec in enumerate(bras):
        d = d2 if (forme == "droit" and k == 1) else d1
        rot = trimesh.geometry.align_vectors([0, 0, 1], vec)
        s = s + _cannele(d, 12, min(2.0, d * 0.5)).translate((0, 0, c / 2 - 1)).transform(rot[:3, :])
        canal = canal + mf.Manifold.cylinder(c / 2 + 1, 1.0, 1.0, 24).transform(rot[:3, :])
    m = vers_trimesh(s - canal)
    m.apply_translation([-m.bounds.mean(0)[0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
    return m, {"quincaillerie": [f"Tube souple d{d1:g} mm interieur"], "conseil": "Imprimer en PETG, 100 % remplissage, 4 perimetres (etancheite)"}


def gorge_seule(p: dict):
    """Bague d'essai avec la gorge calculee : valide l'ajustement du joint avant le vrai montage."""
    g = lambda k, d: float(p.get(k, d))
    D, cote = g("diametre", 20), p.get("cote", "piston")
    j = gorge(D, cote, bool(int(g("dynamique", 1))))
    if cote == "piston":
        s = mf.Manifold.cylinder(10, D / 2 - 0.25, D / 2 - 0.25, 128) - _gorge_ext(j["fond"], D, j["largeur"], 5)
        s = s - mf.Manifold.cylinder(12, D / 2 - 3, D / 2 - 3, 96).translate((0, 0, -1))
    else:
        s = mf.Manifold.cylinder(10, D / 2 + 5 + j["profondeur"], D / 2 + 5 + j["profondeur"], 128) - mf.Manifold.cylinder(12, D / 2 + 0.25, D / 2 + 0.25, 96).translate((0, 0, -1))
        s = s - mf.Manifold.cylinder(j["largeur"], j["fond"] / 2, j["fond"] / 2, 96).translate((0, 0, 5 - j["largeur"] / 2))
    return vers_trimesh(s), {**{k: v for k, v in j.items()}, "quincaillerie": [j["joint"]]}


CATALOGUE.update({
    "verin": {"nom": "Verin pneumatique", "cat": "Pneumatique", "fn": verin, "champs": [
        _c("alesage", "Alesage (diametre du piston)", 20, 10, 60, 1), _c("course", "Course", 40, 5, 150, 1),
        _c("tige", "Diametre de tige", 6, 3, 16, 0.5), _c("double_effet", "Double effet (2 orifices)", 1, type_="bool"),
        _c("paroi", "Paroi", 3, 2, 6, 0.5), _c("tube", "Tube souple (d interieur)", 4, 2, 8, 0.5),
        _c("orifice", "Orifices", "cannele", type_="choix", options=["cannele", "g18", "m5"])]},
    "raccord": {"nom": "Raccord cannele", "cat": "Pneumatique", "fn": raccord, "champs": [
        _c("forme", "Forme", "T", type_="choix", options=["droit", "coude", "T", "Y", "croix"]),
        _c("tube", "Tube (d interieur)", 4, 2, 10, 0.5), _c("tube2", "Reduction : 2e tube (droit)", 4, 2, 10, 0.5)]},
    "gorge": {"nom": "Gorge de joint torique (essai)", "cat": "Pneumatique", "fn": gorge_seule, "champs": [
        _c("diametre", "Diametre (alesage ou tige)", 20, 3, 60, 0.5), _c("cote", "Type", "piston", type_="choix", options=["piston", "tige"]),
        _c("dynamique", "Joint mobile (dynamique)", 1, type_="bool")]},
})


def _vibe_deck(p):
    from .vibedeck import vibe_deck
    return vibe_deck(p)


def _g(groupe, *champs):
    for c in champs:
        c["groupe"] = groupe
    return list(champs)


CATALOGUE["vibedeck"] = {"nom": "Vibe Deck", "cat": "Projets", "fn": _vibe_deck,
    "description": "Macropad a touches MX + ecran Guition 4.3\" (ou OLED), design epure, pivot a crans ou motorise.",
    "couleurs": {"socle": "#d9dde3", "plaque": "#2b2d42", "cadre": "#1c1f26", "dos": "#d9dde3"},
    "champs":
    _g("Touches", _c("colonnes", "Colonnes", 4, 1, 10, 1), _c("rangees", "Rangees", 3, 1, 6, 1),
       _c("encodeur", "Molette (encodeur EC11)", 1, type_="bool")) +
    _g("Ecran", _c("ecran", "Ecran", "guition_43", type_="choix", options=["guition_43", "oled_096", "oled_13", "aucun"]),
       _c("angle_ecran", "Angle de l'ecran", 72, 45, 100, 1), _c("bordure", "Bordure autour de l'ecran", 3, 1.5, 8, 0.5),
       _c("rayon_ecran", "Rayon des coins de l'ecran", 7, 2, 15, 0.5)) +
    _g("Pivot", _c("pivot", "Mecanisme", "crans", type_="choix", options=["crans", "servo", "fixe"]),
       _c("servo", "Servo", "sg90", type_="choix", options=["sg90", "mg90s"]), _c("largeur_charniere", "Largeur de la charniere", 34, 24, 80, 1)) +
    _g("Design", _c("inclinaison", "Inclinaison du dessus", 7, 0, 15, 0.5), _c("hauteur_avant", "Hauteur a l'avant", 16, 12, 30, 0.5),
       _c("rayon", "Rayon des coins", 10, 3, 20, 0.5), _c("arrondi", "Arrondi des aretes", 2.5, 0.8, 5, 0.1),
       _c("bord", "Bordure autour de la plaque", 6, 3, 15, 0.5), _c("joint_ombre", "Joint d'ombre", 0.35, 0.1, 1, 0.05)) +
    _g("Electronique", _c("usb_x", "Position de l'USB-C", 0, -50, 50, 1), _c("fond", "Epaisseur du fond", 2.2, 1.6, 4, 0.2)) +
    _g("Carte ecran (a verifier)", _c("ecran_l", "Largeur carte (officiel 120)", 120, 60, 160, 0.1), _c("ecran_h", "Hauteur carte (officiel 70.2)", 70.2, 40, 120, 0.1),
       _c("actif_l", "Zone active L (officiel 95.04)", 95.04, 40, 150, 0.01), _c("actif_h", "Zone active H (officiel 53.86)", 53.86, 20, 110, 0.01),
       _c("actif_x", "Decalage zone active X", 0, -15, 15, 0.1), _c("actif_y", "Decalage zone active Y", 0, -10, 10, 0.1),
       _c("ecran_e", "Epaisseur carte + dalle (A MESURER)", 9, 4, 25, 0.1),
       _c("trou_x", "Trous : axe depuis le bord X (A MESURER)", 3.5, 1.5, 10, 0.1), _c("trou_y", "Trous : axe depuis le bord Y (A MESURER)", 3.5, 1.5, 10, 0.1))}


# ================================================================== PNEUMATIQUE v2 : orifices standard + circuit complet
# Orifices : "cannele" (tube souple), "g18" (avant-trou 8.6 -> taraud G1/8 : raccords rapides du commerce),
#            "m5" (avant-trou 4.2 -> taraud M5). Un bossage plein entoure toujours l'orifice.
ORIFICES = {"lego": "Embout tube LEGO (4 x 2)", "tube8": "Embout tube d8 interieur", "cannele": "Embout cannele (tube souple)",
            "g18": "Taraudage G1/8 (raccord rapide)", "m5": "Taraudage M5 (mini raccord)"}


def orifice(type_, d_tube=4.0, canal=2.5):
    """-> (bossage, vide) le long de +Z, base a z = 0 (a placer avec transform)."""
    if type_ == "g18":
        boss = mf.Manifold.cylinder(11, 7.0, 7.0, 48)
        vide = mf.Manifold.cylinder(11.5, 4.3, 4.3, 48).translate((0, 0, 0.5)) + mf.Manifold.cylinder(1.2, 4.3, 5.3, 48).translate((0, 0, 10.0)) \
            + mf.Manifold.cylinder(12, canal / 2, canal / 2, 24).translate((0, 0, -1))
        return boss, vide
    if type_ == "m5":
        boss = mf.Manifold.cylinder(7, 5.0, 5.0, 48)
        vide = mf.Manifold.cylinder(6.5, 2.1, 2.1, 32).translate((0, 0, 1.0)) + mf.Manifold.cylinder(9, min(canal, 2.0) / 2, min(canal, 2.0) / 2, 24).translate((0, 0, -1))
        return boss, vide
    if type_ == "lego":                                  # tube LEGO : 4 ext / ~2 int -> embout lisse d2.6 a bourrelet (A AJUSTER)
        boss = mf.Manifold.cylinder(3, 3.0, 3.0, 32) + mf.Manifold.cylinder(7, 1.3, 1.3, 24).translate((0, 0, 2.9))             + mf.Manifold.cylinder(1.2, 1.3, 1.45, 24).translate((0, 0, 6.0))
        vide = mf.Manifold.cylinder(12, 0.6, 0.6, 16).translate((0, 0, -1))
        return boss, vide
    if type_ == "tube8":
        d_tube = 8.0
    boss = mf.Manifold.cylinder(3, d_tube / 2 + 2.0, d_tube / 2 + 2.0, 48) + _cannele(d_tube, 12, min(canal, d_tube * 0.55)).translate((0, 0, 2.9))
    vide = mf.Manifold.cylinder(17, min(canal, d_tube * 0.55) / 2, min(canal, d_tube * 0.55) / 2, 24).translate((0, 0, -1))
    return boss, vide


def _place(sol, pos, direction):
    rot = trimesh.geometry.align_vectors([0, 0, 1], direction)
    rot[:3, 3] = pos
    return sol.transform(rot[:3, :])


def _ajouter_orifice(corps, type_, pos, direction, d_tube=4.0, canal=2.5):
    b, v = orifice(type_, d_tube, canal)
    return (corps + _place(b, pos, direction)) - _place(v, pos, direction)


def reservoir(p: dict):
    """Reservoir cylindrique a fonds bombes, 2 a 4 orifices, pieds. Paroi epaisse (pression)."""
    g = lambda k, d: float(p.get(k, d))
    D, L, e = g("diametre", 60), g("longueur", 120), g("paroi", 4)
    po = p.get("orifice", "g18")
    ext = mf.Manifold.cylinder(L - D * 0.5, D / 2, D / 2, 96).translate((0, 0, D * 0.25)) + \
          mf.Manifold.sphere(D / 2, 96).scale((1, 1, 0.5)).translate((0, 0, D * 0.25)) + mf.Manifold.sphere(D / 2, 96).scale((1, 1, 0.5)).translate((0, 0, L - D * 0.25))
    inn = mf.Manifold.cylinder(L - D * 0.5, D / 2 - e, D / 2 - e, 96).translate((0, 0, D * 0.25)) + \
          mf.Manifold.sphere(D / 2 - e, 96).scale((1, 1, 0.5)).translate((0, 0, D * 0.25)) + mf.Manifold.sphere(D / 2 - e, 96).scale((1, 1, 0.5)).translate((0, 0, L - D * 0.25))
    s = ext - inn
    n = int(g("orifices", 3))
    pts = [((0, 0, L), (0, 0, 1)), ((0, 0, 0), (0, 0, -1)), ((D / 2, 0, L / 2), (1, 0, 0)), ((-D / 2, 0, L / 2), (-1, 0, 0))][:n]
    for pos, dirv in pts:
        s = _ajouter_orifice(s, po, np.array(pos, float) - np.array(dirv) * 1.0, dirv, g("tube", 4), 3.0)
    # pieds (couche sur le cote : imprime debout = fonds bombes autoportants)
    vol = math.pi * (D / 2 - e) ** 2 * (L - D * 0.5) + 4 / 3 * math.pi * (D / 2 - e) ** 3 * 0.5
    m = vers_trimesh(s)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m, {"volume_L": round(vol / 1e6, 3), "quincaillerie": [f"{n} raccords {ORIFICES[po]}"] if po != "cannele" else [],
               "conseil": "PETG, 100 % remplissage, 5 perimetres. TESTER A L'EAU avant l'air (une piece imprimee qui cede sous pression d'air projette des eclats) ; ne pas depasser 3 bar"}


def collecteur(p: dict):
    """Bloc collecteur (manifold) : 1 entree, N sorties sur une galerie interne."""
    g = lambda k, d: float(p.get(k, d))
    n, pas, po = int(g("sorties", 4)), g("pas", 18), p.get("orifice", "g18")
    L = n * pas + 10
    s = galet_simple(L, 18, 18)
    s = s - mf.Manifold.cylinder(L - 6, 2.5, 2.5, 32).rotate((0, 90, 0)).translate((-L / 2 + 3, 0, 9))      # galerie
    s = _ajouter_orifice(s, po, np.array([-L / 2 + 0.5, 0, 9]), (-1, 0, 0), g("tube", 4), 3.0)
    for k in range(n):
        x = -L / 2 + 5 + pas * (k + 0.5)
        s = _ajouter_orifice(s, po, np.array([x, 0, 17.5]), (0, 0, 1), g("tube", 4), 3.0)
    for x in (-L / 2 + 4, L / 2 - 4):                    # trous de fixation
        s = s - mf.Manifold.cylinder(20, 1.7, 1.7, 16).rotate((90, 0, 0)).translate((x, 10, 4))
    return vers_trimesh(s), {"quincaillerie": [f"{n + 1} raccords {ORIFICES[po]}"] if po != "cannele" else []}


def galet_simple(l, w, h, r=3.0):
    sb = sbox(-l / 2, -w / 2, l / 2, w / 2).buffer(-r, join_style=1).buffer(r, join_style=1)
    return mf.Manifold.extrude(section(sb), h)


def clapet_antiretour(p: dict):
    """Clapet anti-retour a joint torique : un joint pousse par un ressort ferme le siege (l'air ne passe que dans un sens).
    2 pieces vissees (corps + bouchon) + 1 joint + 1 ressort du commerce."""
    g = lambda k, d: float(p.get(k, d))
    po = p.get("orifice", "cannele")
    D = 16.0
    corps = mf.Manifold.cylinder(22, D / 2, D / 2, 64)
    corps = corps - mf.Manifold.cylinder(18, 5.0, 5.0, 48).translate((0, 0, 4))           # chambre du clapet
    corps = corps - mf.Manifold.cylinder(5, 1.5, 1.5, 24).translate((0, 0, -0.5))         # siege (passage d3)
    corps = corps - mf.Manifold.cylinder(1.0, 1.5, 3.0, 24).translate((0, 0, 3.0))        # chanfrein d'appui du joint
    corps = _ajouter_orifice(corps, po, np.array([0, 0, 0.5]), (0, 0, -1), g("tube", 4), 2.5)
    # bouchon visse (filetage M14x1.5 imprime simplifie : emboitement + 2 vis M2 radiales) -> simple : emmanche + colle
    bouchon = mf.Manifold.cylinder(4, D / 2, D / 2, 64) + mf.Manifold.cylinder(6, 4.9, 4.9, 48).translate((0, 0, -6))
    bouchon = bouchon - mf.Manifold.cylinder(12, 1.25, 1.25, 24).translate((0, 0, -7))
    bouchon = _ajouter_orifice(bouchon, po, np.array([0, 0, 3.5]), (0, 0, 1), g("tube", 4), 2.5)
    bouchon = bouchon - mf.Manifold.cylinder(1.2, 3.2, 3.2, 24).translate((0, 0, -6.01))  # appui du ressort
    for x in (-3.4, 3.4):                                                                   # rainures de passage d'air
        bouchon = bouchon - mf.Manifold.cube((1.2, 1.2, 7), True).translate((x, 0, -2.5))
    m1, m2 = vers_trimesh(corps), vers_trimesh(bouchon)
    m2.apply_translation([D + 8 - m2.bounds.mean(0)[0], 0, -m2.bounds[0][2]])
    return [m1, m2], {"quincaillerie": ["1 joint torique 3 x 1.5 NBR (obturateur)", "1 ressort d4-5 x 8 mm (faible)", "Colle cyano ou epoxy (bouchon)"],
                      "conseil": "Le joint torique doit appuyer sur le chanfrein ; tester au souffle : passe dans le sens de la fleche, bloque dans l'autre"}


def soupape(p: dict):
    """Soupape de securite REGLABLE : bille / joint sur siege, ressort, vis de reglage M6 (tarage a la pression voulue)."""
    g = lambda k, d: float(p.get(k, d))
    po = p.get("orifice", "g18")
    corps = mf.Manifold.cylinder(30, 8, 8, 64)
    corps = corps - mf.Manifold.cylinder(24, 3.5, 3.5, 48).translate((0, 0, 4))
    corps = corps - mf.Manifold.cylinder(5, 1.25, 1.25, 24).translate((0, 0, -0.5))
    corps = corps - mf.Manifold.cylinder(8, 2.5, 2.5, 32).translate((0, 0, 23))           # avant-trou M6 (vis de reglage)
    for a in range(4):                                                                     # echappements lateraux
        corps = corps - mf.Manifold.cylinder(10, 1.2, 1.2, 16).rotate((0, 90, 0)).rotate((0, 0, 90 * a)).translate((0, 0, 8))
    corps = _ajouter_orifice(corps, po, np.array([0, 0, 0.5]), (0, 0, -1), g("tube", 4), 2.5)
    d_s = 2.4
    F_par_bar = math.pi * (d_s / 2) ** 2 * 0.1                                             # N par bar sur le siege
    pr = g("pression_ouverture", 2.5)
    return vers_trimesh(corps), {"quincaillerie": ["1 bille acier d4 (ou joint 3 x 1.5)", "1 ressort d6 x 15 mm", "1 vis M6 x 10 (reglage) + contre-ecrou"],
                                 "force_ressort_N": round(F_par_bar * pr, 2),
                                 "conseil": f"Tarage : serrer la vis jusqu'a ouverture a {pr:g} bar (manometre). Force ressort ~ {F_par_bar * pr:.2f} N"}


def vanne_3_2(p: dict):
    """Distributeur 3/2 manuel a TIROIR : P -> A (bouton enfonce), A -> echappement (relache). Tiroir a 2 joints toriques."""
    g = lambda k, d: float(p.get(k, d))
    po = p.get("orifice", "cannele")
    d_al, L = 10.0, 46.0
    jt = gorge(d_al, "piston")
    corps = galet_simple(24, 22, L)
    corps = corps - mf.Manifold.cylinder(L - 4, d_al / 2 + 0.05, d_al / 2 + 0.05, 64).translate((0, 0, 4))   # alesage du tiroir
    zP, zA, zE = 14.0, 24.0, 34.0
    for z, dirv in ((zP, (1, 0, 0)), (zA, (-1, 0, 0)), (zE, (1, 0, 0))):
        x = 12 if dirv[0] > 0 else -12
        corps = _ajouter_orifice(corps, po, np.array([x - dirv[0] * 0.5, 0, z]), dirv, g("tube", 4), 2.5)
        corps = corps - mf.Manifold.cylinder(12, 1.25, 1.25, 16).rotate((0, 90, 0)).translate((-6 if dirv[0] > 0 else -6, 0, z))
    # tiroir : 2 portees a joint (gorges calculees) separees par une gorge de passage
    tir = mf.Manifold.cylinder(L + 6, d_al / 2 - 0.25, d_al / 2 - 0.25, 64)
    for z in (19.0, 29.0):
        tir = tir - _gorge_ext(jt["fond"], d_al, jt["largeur"], z)
    tir = tir - _gorge_ext(d_al - 3.0, d_al, 6.0, 24.0)                                    # passage P->A ou A->E
    tir = tir + mf.Manifold.cylinder(4, 7, 7, 64).translate((0, 0, L + 6))                  # bouton
    m1, m2 = vers_trimesh(corps), vers_trimesh(tir)
    m2.apply_translation([30, 0, 0])
    return [m1, m2], {"quincaillerie": [f"2 x {jt['joint']} (tiroir)", "1 ressort de rappel d7 x 15", "Graisse silicone"],
                      "conseil": "Poncer l'alesage ; le tiroir doit coulisser gras sans jeu"}


def silencieux(p: dict):
    """Silencieux d'echappement : chicanes + maille fine (imprime en remplissage gyroide 15 % = filtre poreux)."""
    g = lambda k, d: float(p.get(k, d))
    po = p.get("orifice", "m5")
    s = mf.Manifold.cylinder(26, 7, 7, 64) - mf.Manifold.cylinder(22, 5.5, 5.5, 48).translate((0, 0, 2))
    for k in range(10):
        s = s - mf.Manifold.cylinder(5, 0.6, 0.6, 12).rotate((0, 90, 0)).rotate((0, 0, 36 * k)).translate((0, 0, 8 + (k % 3) * 5))
    s = _ajouter_orifice(s, po, np.array([0, 0, 0.5]), (0, 0, -1), g("tube", 4), 2.5)
    return vers_trimesh(s), {"conseil": "Remplir de laine d'acier fine ou de mousse"}


CATALOGUE.update({
    "reservoir": {"nom": "Reservoir d'air", "cat": "Pneumatique", "fn": reservoir, "champs": [
        _c("diametre", "Diametre", 60, 30, 150, 1), _c("longueur", "Longueur", 120, 50, 230, 1), _c("paroi", "Paroi", 4, 2.4, 8, 0.2),
        _c("orifices", "Nombre d'orifices", 3, 2, 4, 1), _c("orifice", "Orifices", "g18", type_="choix", options=list(ORIFICES)), _c("tube", "Tube (cannele)", 4, 2, 8, 0.5)]},
    "collecteur": {"nom": "Bloc collecteur", "cat": "Pneumatique", "fn": collecteur, "champs": [
        _c("sorties", "Sorties", 4, 1, 10, 1), _c("pas", "Pas", 18, 12, 30, 1), _c("orifice", "Orifices", "g18", type_="choix", options=list(ORIFICES)), _c("tube", "Tube (cannele)", 4, 2, 8, 0.5)]},
    "clapet": {"nom": "Clapet anti-retour", "cat": "Pneumatique", "fn": clapet_antiretour, "champs": [
        _c("orifice", "Orifices", "cannele", type_="choix", options=list(ORIFICES)), _c("tube", "Tube (cannele)", 4, 2, 8, 0.5)]},
    "soupape": {"nom": "Soupape de securite reglable", "cat": "Pneumatique", "fn": soupape, "champs": [
        _c("pression_ouverture", "Pression d'ouverture (bar)", 2.5, 0.5, 6, 0.1), _c("orifice", "Orifice", "g18", type_="choix", options=list(ORIFICES)), _c("tube", "Tube (cannele)", 4, 2, 8, 0.5)]},
    "vanne": {"nom": "Distributeur 3/2 manuel", "cat": "Pneumatique", "fn": vanne_3_2, "champs": [
        _c("orifice", "Orifices", "cannele", type_="choix", options=list(ORIFICES)), _c("tube", "Tube (cannele)", 4, 2, 8, 0.5)]},
    "silencieux": {"nom": "Silencieux d'echappement", "cat": "Pneumatique", "fn": silencieux, "champs": [
        _c("orifice", "Orifice", "m5", type_="choix", options=list(ORIFICES)), _c("tube", "Tube (cannele)", 4, 2, 8, 0.5)]},
})


def _compresseur(p):
    from .wankel import compresseur
    return compresseur(p)


CATALOGUE["compresseur"] = {"nom": "Compresseur Wankel", "cat": "Projets", "fn": _compresseur, "simulation": "pneumatique",
    "description": "Compresseur a piston rotatif Wankel : entraine a la perceuse (axe d8) ou version compacte moteur + reduction (RC 1:10).",
    "couleurs": {"stator": "#7fb8a4", "rotor": "#e07a3a", "flasque_avant": "#d9dde3", "flasque_arriere": "#d9dde3", "excentrique": "#2b2d42",
                 "clapet_siege": "#c9a227", "clapet_lamelle": "#555555", "pignon_moteur": "#2b2d42", "roue_reduction": "#2b2d42",
                 "carter_moteur": "#d9dde3", "capot_engrenages": "#d9dde3"},
    "champs": [
        dict(_c("version", "Version", "perceuse", type_="choix", options=["perceuse", "compact"]), groupe="Version"),
        dict(_c("moteur", "Moteur (compact)", "130", type_="choix", options=["130", "180"]), groupe="Version"),
        dict(_c("rapport_K", "Rapport K = R / e (forme)", 7.0, 6.0, 8.5, 0.1), groupe="Geometrie"),
        dict(_c("module", "Module de l'engrenage de phase", 1.0, 0.6, 1.5, 0.1), groupe="Geometrie"),
        dict(_c("dents_rotor", "Dents de la couronne du rotor (multiple de 3)", 30, 18, 45, 3), groupe="Geometrie"),
        dict(_c("largeur", "Largeur du rotor", 16, 6, 30, 0.5), groupe="Geometrie"),
        dict(_c("visserie", "Visserie", "placo", type_="choix", options=["placo", "imprimee", "m3"]), groupe="Visserie"),
        dict(_c("imprimer_visserie", "Imprimer la visserie sur le plateau (tirants imprimes)", 1, type_="bool"), groupe="Visserie"),
        dict(_c("orifice", "Raccords", "lego", type_="choix", options=["lego", "tube8", "cannele", "g18", "m5"]), groupe="Raccords et joints"),
        dict(_c("cordon", "Tore de tes joints toriques (mm)", 2.0, 1.0, 4.0, 0.1), groupe="Raccords et joints"),
        dict(_c("tourillon", "Diametre des tourillons (paliers)", 12, 6, 20, 0.5), groupe="Arbre et paliers"),
        dict(_c("jeu_palier", "Jeu des paliers lisses", 0.25, 0.1, 0.6, 0.05), groupe="Arbre et paliers"),
        dict(_c("hexagone", "Hexagone pour le mandrin (sur plats)", 10, 6, 13, 0.5), groupe="Arbre et paliers"),
        dict(_c("longueur_hexagone", "Longueur de l'hexagone", 30, 0, 60, 1), groupe="Arbre et paliers"),
        dict(_c("jeu", "Jeu rotor / stator", 0.15, 0.05, 0.4, 0.01), groupe="Ajustements"),
        dict(_c("jeu_flanc", "Jeu lateral (par flasque)", 0.2, 0.05, 0.5, 0.01), groupe="Ajustements"),
        dict(_c("paroi", "Paroi du stator", 6, 4, 12, 0.5), groupe="Ajustements"),
        dict(_c("angle_admission", "Angle de l'admission (optimise)", 205, 130, 215, 1), groupe="Lumieres"),
        dict(_c("angle_refoulement", "Angle du refoulement (optimise)", 86, 50, 89, 1), groupe="Lumieres"),
    ]}


# ================================================================== PALIERS IMPRIMES (aucun roulement du commerce)
def palier_lisse(p: dict):
    """Palier lisse imprime : bague (a emmancher ou a bride) avec rainure annulaire de graisse, rainures
    axiales, canal radial et graisseur (bouchon imprime). Jeu diametral reglable."""
    g = lambda k, d: float(p.get(k, d))
    d, L, ep = g("d_arbre", 8), g("longueur", 12), g("paroi", 3)
    jeu = g("jeu", 0.25)
    bride = int(g("bride", 1))
    di, de = d + jeu, d + jeu + 2 * ep
    s = mf.Manifold.cylinder(L, de / 2, de / 2, 96)
    if bride:
        s = s + mf.Manifold.cylinder(2.5, de / 2 + 4, de / 2 + 4, 96)
    s = s - mf.Manifold.cylinder(L + 2, di / 2, di / 2, 96).translate((0, 0, -1))
    s = s - (mf.Manifold.cylinder(2.0, di / 2 + 0.9, di / 2 + 0.9, 64) - mf.Manifold.cylinder(2.0, di / 2 - 1, di / 2 - 1, 64)).translate((0, 0, L / 2 - 1))
    for a in range(3):                                   # rainures axiales (la graisse se repartit)
        s = s - mf.Manifold.cylinder(L - 2, 0.6, 0.6, 12).translate((di / 2, 0, 1)).rotate((0, 0, 120 * a))
    if int(g("graisseur", 1)):
        s = s - mf.Manifold.cylinder(de, 0.9, 0.9, 16).rotate((0, 90, 0)).translate((0, 0, L / 2))
        s = s + (mf.Manifold.cylinder(4, 2.8, 2.8, 24).rotate((0, 90, 0)).translate((de / 2 - 1, 0, L / 2))
                 - mf.Manifold.cylinder(6, 0.9, 0.9, 16).rotate((0, 90, 0)).translate((de / 2 - 2, 0, L / 2))
                 - mf.Manifold.cylinder(3, 1.6, 1.6, 16).rotate((0, 90, 0)).translate((de / 2 + 1.2, 0, L / 2)))
    bouchon = mf.Manifold.cylinder(2.8, 1.55, 1.55, 16) + mf.Manifold.cylinder(1.2, 2.6, 2.6, 16).translate((0, 0, 2.8))
    m1, m2 = vers_trimesh(s), vers_trimesh(bouchon)
    m2.apply_translation([de + 10, 0, 0])
    return [m1, m2], {"conseil": "PLA ou PETG, 100 % remplissage ; graisser a la seringue par le graisseur ; ideal < 1500 tr/min",
                      "d_ext_mm": round(de, 2), "jeu_mm": jeu}


CATALOGUE.update({
    "palier_lisse": {"nom": "Palier lisse graissable", "cat": "Guidage", "fn": palier_lisse, "champs": [
        _c("d_arbre", "Diametre de l'arbre", 8, 3, 40, 0.5), _c("longueur", "Longueur", 12, 4, 60, 0.5), _c("paroi", "Paroi", 3, 1.5, 10, 0.5),
        _c("jeu", "Jeu diametral", 0.25, 0.1, 0.6, 0.05), _c("bride", "Bride", 1, type_="bool"), _c("graisseur", "Entree de graissage", 1, type_="bool")]},
})


def _roulement_imprime_graisse(p):
    ms, info = roulement_imprime(p)
    if not int(float(p.get("graisseur", 1))):
        return ms, info
    s = vers_manifold(ms if not isinstance(ms, list) else ms[0])
    de, b = float(p.get("d_ext", 30)), float(p.get("largeur", 10))
    s = s - mf.Manifold.cylinder(de, 0.9, 0.9, 16).rotate((0, 90, 0)).translate((0, 0, b / 2))     # entree de graissage dans la bague exterieure
    info["graisseur"] = "trou d0.9 vers la piste des billes : graisser a la seringue"
    return vers_trimesh(s), info


CATALOGUE["roulement_imprime"]["fn"] = _roulement_imprime_graisse
CATALOGUE["roulement_imprime"]["champs"].append(_c("graisseur", "Entree de graissage", 1, type_="bool"))


# ================================================================== PROJET : RC 1:10 "SHWork 190 SE" (carrosserie depuis le STL de base)
def _swork190(p: dict):
    import hashlib
    import trimesh as _tm
    from pathlib import Path
    from . import carrosserie as ca
    from .c3d import orienter
    ici = Path(__file__).resolve().parent.parent
    fid = str(p.get("base") or "")
    src = ici / "sortie" / "c3d" / f"{fid}.stl"
    if not fid or not src.exists():
        raise ValueError("Ce projet a besoin du STL de la carrosserie : cree le projet avec 'Partir d'un fichier STL'")
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    L, paroi, inv = g("longueur", 445.0), g("paroi", 1.8), int(g("inverser", 0))
    # ---- coque + doublure (cache disque : le calcul ne se fait qu'une fois par base / echelle / paroi)
    cle = hashlib.sha1(f"v5|{fid}|{L}|{paroi}|{inv}".encode()).hexdigest()[:16]
    cache = ca.CACHE / cle
    cache.mkdir(parents=True, exist_ok=True)
    import json as _json
    fi = cache / "info.json"
    if (cache / "coque.ply").exists() and (cache / "doublure.ply").exists() and fi.exists():
        coque = _tm.load(cache / "coque.ply", force="mesh", process=False)
        doublure = _tm.load(cache / "doublure.ply", force="mesh", process=False)
        propre = _json.loads(fi.read_text()).get("modele") == "propre"
    else:
        base, inf = ca.preparer(src, L, inverser=bool(inv))
        propre = inf.get("modele") == "propre"
        coque = ca.coque_precise(base, paroi, poncage=not propre)      # modele propre : aucun poncage (details intacts)
        doublure = coque.metadata["doublure"]
        coque.export(cache / "coque.ply"); doublure.export(cache / "doublure.ply")
        fi.write_text(_json.dumps({"modele": "propre" if propre else "ancien", "roues": inf.get("roues")}, default=float))
    # ---- pieces a detacher : contours releves sur les rainures du modele (cache disque)
    fc = cache / ("contours_v2.json" if propre else "contours3.json")
    if not fc.exists():
        base, _ = ca.preparer(src, L, inverser=bool(inv))
        (ca.contours_v2 if propre else ca.contours_precis)(base, fc)
    contours = (ca.contours_v2 if propre else ca.contours_precis)(None, cache=fc)
    choix = {k for k in ca.ORDRE_PRECIS if k != "plaque_av" and k in contours | {"aile_avd": 1, "porte_avd": 1, "porte_ard": 1} and int(g("detacher_" + k, 1))}
    if propre and int(g("chassis", 1)):                      # carrosserie RC = peau seule (place au chassis)
        fv = cache / "coque_videe.ply"
        if not fv.exists():
            ca.evider_interieur(coque).export(fv)
        coque = _tm.load(fv, force="mesh", process=False)
    ret = p.get("retouches") or {}
    if ret.get("surface"):                                  # pinceau : lisser / raboter la tole avant decoupe
        from .retouches import retoucher_surface
        coque = retoucher_surface(coque, ret["surface"])
    caisse, panneaux = ca.detacher_precis(coque, contours, choix, g("jeu_panneaux", 0.35), g("jeu_petites", 0.2),
                                          g("profondeur_portes", 32), retouches=ret.get("decoupe"), paroi=paroi)
    morceaux, eclisses, coupes = ca.troncons(caisse, doublure, g("troncon_max", 180), g("recouvrement", 10))
    # ---- orientation d'impression + pose d'assemblage (inverse)
    out, noms, poses = [], [], []

    def ajouter(nom, m, R):
        m = m.copy()
        m.apply_transform(R)
        t = -m.bounds[0]
        m.apply_translation(t)
        T = np.eye(4); T[:3, 3] = t
        poses.append(np.linalg.inv(T @ R).tolist())
        out.append(m); noms.append(nom)

    voir_caisse = int(g("voir_carrosserie", 1))
    for k, m in enumerate(morceaux if voir_caisse else []):
        # debout sur sa face de coupe : avant -> face arriere en bas ; arriere -> face avant en bas
        if k < len(morceaux) - 1:
            R = _tm.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
        else:
            R = _tm.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0])
        ajouter(f"troncon_{k + 1}", m, R)
    for nom, m in (panneaux.items() if voir_caisse else []):
        R, _ = orienter(m)
        ajouter(nom, m, R)
    for k, m in enumerate(eclisses if voir_caisse else []):
        R, _ = orienter(m)
        ajouter(f"eclisse_{k + 1}", m, R)
    q = [f"{len(eclisses)} eclisses a coller (cyano ou epoxy) a cheval sur les coupes",
         "Charnieres imprimees des ouvrants : prochaine etape (clips)"]
    info_ch = None
    if int(g("chassis", 1)):                               # chassis tubulaire custom + suspension active
        from .chassis import chassis as _chassis
        from .c3d import vers_trimesh as _vt
        roues = (_json.loads(fi.read_text()).get("roues") if fi.exists() else None) or []
        pc = {k: p[k] for k in ("voie", "z_plancher", "e_plancher", "r_tube") if p.get(k) not in (None, "")}
        if len(roues) == 2:
            pc.update(x_essieu_av=roues[0][0], x_essieu_ar=roues[1][0], z_roue=roues[0][1])
        pieces_ch, info_ch = _chassis(pc)
        for nom, sol in pieces_ch.items():
            m = _vt(sol)
            R, _ = orienter(m)
            ajouter("ch_" + nom, m, R)
        q += info_ch["quincaillerie"]
        # le VERIN CUSTOM imprimable (a imprimer 4 fois) : pose a cote de la voiture
        vs, iv = verin({"alesage": 12, "course": 12, "tige": 4, "paroi": 2.4, "oeillets": 1, "orifice": "lego", "double_effet": 1})
        for nom_v, mv in zip(("corps", "tete", "piston", "tige"), vs):
            mv = mv.copy(); mv.apply_translation([300, 0, 0])
            ajouter(f"ch_verin_x4_{nom_v}", mv, np.eye(4))
        q += [f"Verin x4 : {iv['joint_piston']} (piston), {iv['joint_tige']} (tige) - {iv['force_sortie_6bar_N']} N a 6 bar"]
    return out, {"noms": noms, "assemblage": poses, "quincaillerie": q, "pinceau": True,
                 "dimensions_mm": [round(float(x), 1) for x in coque.extents], "echelle": f"1:{4448 / L:.1f} (Mercedes 190 : 4448 mm)",
                 "troncons": len(morceaux), "coupes_x": [round(c, 1) for c in coupes], "panneaux": list(panneaux), "chassis": info_ch}


CATALOGUE["swork190"] = {"nom": "SHWork 190 SE (RC 1:10)", "cat": "Projets", "fn": _swork190, "base_requise": True,
    "description": "RC 1:10 sur base Mercedes 190 E : carrosserie creusee, ouvrants detaches, troncons imprimables.",
    "couleurs": {"troncon_1": "#d9dde3", "troncon_2": "#d9dde3", "troncon_3": "#d9dde3", "troncon_4": "#d9dde3", "capot": "#e07a3a", "coffre": "#7fb8a4",
                 "porte_avg": "#6c8ebf", "porte_avd": "#6c8ebf", "porte_arg": "#c9a227", "porte_ard": "#c9a227", "aile_avg": "#b5607a", "aile_avd": "#b5607a", "pare_choc_av": "#2b2d42", "pare_choc_ar": "#2b2d42",
                 "calandre": "#9aa0a8", "phare_g": "#eef3f8", "phare_d": "#eef3f8", "feu_g": "#c0392b", "feu_d": "#c0392b", "retro_g": "#2b2d42", "retro_d": "#2b2d42", "plaque_av": "#f4f4f0", "eclisse_1": "#2b2d42", "eclisse_2": "#2b2d42", "eclisse_3": "#2b2d42"},
    "champs": [
        dict(_c("longueur", "Longueur de la carrosserie (1:10 = 445)", 445, 200, 600, 1), groupe="Echelle"),
        dict(_c("chassis", "Chassis tubulaire + suspension active", 1, type_="bool"), groupe="Chassis"),
        dict(_c("voir_carrosserie", "Afficher la carrosserie", 1, type_="bool"), groupe="Chassis"),
        dict(_c("voie", "Voie (entraxe des roues)", 140, 110, 170, 1), groupe="Chassis"),
        dict(_c("z_plancher", "Hauteur du plancher (garde au sol)", 6, 3, 15, 0.5), groupe="Chassis"),
        dict(_c("r_tube", "Rayon des tubes de cage", 2.6, 1.8, 4, 0.1), groupe="Chassis"),
        dict(_c("inverser", "Inverser l'avant et l'arriere", 0, type_="bool"), groupe="Echelle"),
        dict(_c("paroi", "Epaisseur de la coque", 1.8, 1.2, 3.0, 0.1), groupe="Coque"),
        dict(_c("detacher_capot", "Capot", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_coffre", "Coffre", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_porte_avg", "Porte avant gauche", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_porte_avd", "Porte avant droite", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_porte_arg", "Porte arriere gauche", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_porte_ard", "Porte arriere droite", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_aile_avg", "Aile avant gauche", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_aile_avd", "Aile avant droite", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_pare_choc_av", "Pare-chocs avant", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("detacher_pare_choc_ar", "Pare-chocs arriere", 1, type_="bool"), groupe="Ouvrants a detacher"),
        dict(_c("jeu_panneaux", "Jeu autour des ouvrants", 0.35, 0.15, 1.0, 0.05), groupe="Ouvrants a detacher"),
        dict(_c("detacher_calandre", "Calandre + etoile", 1, type_="bool"), groupe="Petites pieces"),
        dict(_c("detacher_phare_g", "Phare gauche", 1, type_="bool"), groupe="Petites pieces"),
        dict(_c("detacher_phare_d", "Phare droit", 1, type_="bool"), groupe="Petites pieces"),
        dict(_c("detacher_feu_g", "Feu arriere gauche", 1, type_="bool"), groupe="Petites pieces"),
        dict(_c("detacher_feu_d", "Feu arriere droit", 1, type_="bool"), groupe="Petites pieces"),
        dict(_c("detacher_retro_g", "Retroviseur gauche", 1, type_="bool"), groupe="Petites pieces"),
        dict(_c("detacher_retro_d", "Retroviseur droit", 1, type_="bool"), groupe="Petites pieces"),
        dict(_c("jeu_petites", "Jeu autour des petites pieces", 0.2, 0.1, 0.6, 0.05), groupe="Petites pieces"),
        dict(_c("troncon_max", "Longueur max d'un troncon", 180, 100, 230, 5), groupe="Impression"),
        dict(_c("recouvrement", "Recouvrement des eclisses", 10, 5, 20, 1), groupe="Impression"),
    ]}


# ================================================================== PROJET : LE ServBuddy (by SHWork) - bracelet porte-assiette
def _servbuddy_v1(p: dict):
    from .servbuddy_v1 import servbuddy
    from .c3d import vers_trimesh, orienter
    pieces, info = servbuddy(p)
    out, noms, poses = [], [], []
    for nom, sol in pieces.items():
        m = vers_trimesh(sol)
        R, _ = orienter(m)
        mm = m.copy(); mm.apply_transform(R)
        t = -mm.bounds[0]; mm.apply_translation(t)
        T = np.eye(4); T[:3, 3] = t
        poses.append(np.linalg.inv(T @ R).tolist()); out.append(mm); noms.append(nom)
    info.update({"noms": noms, "assemblage": poses})
    return out, info


CATALOGUE["servbuddy_v1"] = {"nom": "ServBuddy v1 (archive)", "cat": "Projets", "fn": _servbuddy_v1,
    "description": "Bracelet porte-assiette ergonomique facon attelle : plateau isole a pistes silicone, reglage rigide par roulette + 2 cremailleres, plaque palmaire a verrou. 100 % PLA.",
    "couleurs": {"coque_dorsale": "#2b2d42", "plateau": "#ff6a13", "plaque_palmaire": "#2b2d42", "roulette": "#ff6a13",
                 "verrou": "#ff6a13", "arbre_roulette": "#ff6a13", "pignon_g": "#8d99ae", "pignon_d": "#8d99ae", "rondelle_bout": "#8d99ae"},
    "champs": [
        dict(_c("tour_poignet", "Tour de poignet (mesure)", 165, 130, 220, 1), groupe="Taille"),
        dict(_c("longueur", "Longueur de la gouttiere", 62, 45, 80, 1), groupe="Taille"),
        dict(_c("epaisseur", "Epaisseur de la coque", 2.6, 2.0, 4.0, 0.1), groupe="Taille"),
        dict(_c("plateau_l", "Plateau : longueur", 92, 60, 130, 1), groupe="Plateau"),
        dict(_c("plateau_w", "Plateau : largeur", 68, 50, 68, 1), groupe="Plateau"),
        dict(_c("lame_air", "Lame d'air isolante", 9, 9, 14, 0.5), groupe="Plateau"),
        dict(_c("film", "Epaisseur du film alcantara", 0.8, 0.4, 1.5, 0.1), groupe="Confort"),
    ]}


# ================================================================== PROJET : ServBuddy v2 (monocoque + carenages)
def _servbuddy(p: dict):
    from .servbuddy2 import servbuddy2
    from .c3d import vers_trimesh, orienter
    pieces, info = servbuddy2(p)
    out, noms, poses = [], [], []
    for nom, sol in pieces.items():
        m = vers_trimesh(sol)
        R, _ = orienter(m)
        mm = m.copy(); mm.apply_transform(R)
        t = -mm.bounds[0]; mm.apply_translation(t)
        T = np.eye(4); T[:3, 3] = t
        poses.append(np.linalg.inv(T @ R).tolist()); out.append(mm); noms.append(nom)
    info.update({"noms": noms, "assemblage": poses})
    return out, info


CATALOGUE["servbuddy"] = {"nom": "ServBuddy (by SHWork)", "cat": "Projets", "fn": _servbuddy,
    "description": "v2 : monocoque en coquille + carenages facon armure. On ouvre, on pose, on ferme (cliquet), on regle a la molette. Port a modules (plateau, pince). 100 % PLA.",
    "couleurs": {"coque_dorsale": "#3a3f4b", "coque_palmaire": "#3a3f4b", "carenage_dorsal": "#e9ebef", "carenage_palmaire": "#e9ebef",
                 "molette": "#ff6a13", "bouton_liberation": "#ff6a13", "module_plateau": "#ff6a13", "module_pince": "#ff6a13"},
    "champs": [
        dict(_c("tour_poignet", "Tour de poignet (mesure)", 165, 130, 220, 1), groupe="Taille"),
        dict(_c("longueur", "Longueur", 58, 45, 75, 1), groupe="Taille"),
        dict(_c("plateau_l", "Plateau : longueur", 96, 60, 130, 1), groupe="Module plateau"),
        dict(_c("plateau_w", "Plateau : largeur", 74, 50, 100, 1), groupe="Module plateau"),
        dict(_c("film", "Epaisseur du film alcantara", 0.8, 0.4, 1.5, 0.1), groupe="Confort"),
    ]}
