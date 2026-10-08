"""CLIQUET v2.5 du ServBuddy : rochet a crochet + verrou coulissant + ressort replie, dimensionne au calcul.

Pourquoi (mesures sur la v2.4, voir sim_cliquet) : la lame en V de 1.1 mm x ~7 mm devait se soulever de 1.4 mm
-> ~5 % de deformation, au-dela de la limite elastique du PLA (~2 %) et tres loin de son endurance (~0.5 %).
Son bec rond pouvait aussi chasser hors de la dent sous effort.

Nouveau principe (tout en 2D (u, v) dans le plan de la nacelle, origine = axe du pignon, v = vers l'exterieur) :
  - ROCHET 24 dents, profondeur 0.8 mm, flanc d'arret a CROCHET (8 deg) : sous effort la dent tire le verrou
    vers le fond (auto-engageant) au lieu de le chasser. Pas de reglage 15 deg au lieu de 30 : plus fin.
  - VERROU (tete) rigide, guide entre la jambe de la trappe et la paroi de la nacelle. L'effort de blocage passe
    tete -> jambe -> paroi de la nacelle, EN COMPRESSION : le ressort ne porte jamais la charge.
  - RESSORT REPLIE (bras exterieur + boucle + bras interieur, ~22 mm de fibre, 0.8 mm) : il ne fait que rappeler
    la tete. Deformation calculee < 0.5 % au clic et a la liberation -> duree de vie en fatigue.
  - LANGUETTE de liberation a fleur, cote +u, hors du ressort.
  - JAMBE a bourrelet clipse dans une vraie gorge de la paroi de la nacelle ; le carenage appuie sur son sommet.
Le tout est une extrusion pure le long de X : imprimee DEBOUT (X vertical), toutes les fibres du ressort sont dans
le plan des couches (pas de delaminage), aucun surplomb.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Polygon, Point, LineString, box as sbox
from shapely.ops import unary_union

# ------------------------------------------------------------------ parametres (mm)
P = dict(
    n_dents=30, r_tete=5.6, prof=0.6, crochet=8.0,           # rochet
    ep=0.6, ep_min=0.45, ep_max=0.8, r_ext=(10.5, 10.0), r_int=(8.3, 8.6), phi_racine=-57.0, phi_boucle=20.0, phi_tete=-30.0,   # ressort (r: racine->boucle, boucle->tete)
    u_jambe=(-7.05, -6.15), v_jambe0=2.2, bourrelet=(3.0, 0.2),                      # jambe + clip
    u_tete=(-5.80, 6.95), r_dessus=7.3, levee=0.8, precharge=0.15,                  # verrou
    u_lang=(5.1, 6.95), v_lang1=16.0,                                                # languette
    jeu=0.2, r_pignon=6.5, mur=7.2,
)


def polaire(r, phi_deg):
    """phi mesure depuis +v vers +u (0 = sommet)."""
    a = math.radians(phi_deg)
    return np.array([r * math.sin(a), r * math.cos(a)])


def arc_uv(r0, r1, p0, p1, n=60):
    ps = np.linspace(p0, p1, n)
    return Polygon([polaire(r1, p) for p in ps] + [polaire(r0, p) for p in ps[::-1]])


def rochet_uv(p=P, phase=0.0):
    """Profil du rochet (uv). Flanc d'arret du cote +theta (theta = angle polaire usuel depuis +u) :
    il bloque la rotation ANTI-HORAIRE (uv) = ouverture du bracelet, et laisse passer le serrage."""
    N, ro, h = p["n_dents"], p["r_tete"], p["prof"]
    ri = ro - h
    pas = 2 * math.pi / N
    gam = h * math.tan(math.radians(p["crochet"])) / ri
    pts = []
    for k in range(N):
        th = math.pi / 2 - math.radians(2.0) + k * pas + phase    # une pointe a theta = 88 deg (juste a droite du sommet)
        for s in np.linspace(0.0, 1.0, 7)[:-1]:                    # rampe : de la racine k-1 a la pointe k
            tt = th - pas + gam + s * (pas - gam)
            rr = ri + (ro - ri) * s
            pts.append((rr * math.cos(tt), rr * math.sin(tt)))
        pts.append((ro * math.cos(th), ro * math.sin(th)))         # pointe
        pts.append((ri * math.cos(th - gam), ri * math.sin(th - gam)))   # pied du flanc (en retrait : crochet)
    return Polygon(pts).buffer(0)


def ligne_moyenne(p=P, n=80):
    """Fibre neutre du ressort, de la racine (encastree sur la jambe) a la tete (guidee)."""
    (e0, e1), (i0, i1) = p["r_ext"], p["r_int"]
    rc, re_ = (e1 + i0) / 2, (e1 - i0) / 2
    a = [polaire(e0 + (e1 - e0) * s, p["phi_racine"] + (p["phi_boucle"] - p["phi_racine"]) * s) for s in np.linspace(0, 1, n)]
    cb = polaire(rc, p["phi_boucle"])
    e_r = polaire(1.0, p["phi_boucle"]); e_t = polaire(1.0, p["phi_boucle"] + 90)
    b = [cb + re_ * (math.cos(s) * e_r + math.sin(s) * e_t) for s in np.linspace(0, math.pi, 16)[1:-1]]
    c = [polaire(i0 + (i1 - i0) * s, p["phi_boucle"] + (p["phi_tete"] - p["phi_boucle"]) * s) for s in np.linspace(0, 1, n)]
    return np.array(a + b + c)


def dessin(p=P):
    """Formes 2D (uv) : rochet, tete, ressort, jambe, languette ; + gorge a creuser dans la nacelle."""
    j0, j1 = p["u_jambe"]
    roch = rochet_uv(p)
    # --- tete (verrou) : entre la jambe (jeu 0.35 : place pour clipser) et la paroi +u ; dessus concentrique
    t0, t1 = p["u_tete"]
    tete = sbox(t0, 1.0, t1, 9.0).intersection(Point(0, 0).buffer(p["r_dessus"], 96).union(sbox(t1 - 1.9, 0, t1, 9.0)))
    # degagements : rochet (pointes + jeu) partout, pignon dans la tranche du pignon (traite par le generateur)
    tete = tete.difference(Point(0, 0).buffer(p["r_tete"] + 0.3, 96))
    # dent du verrou : epouse le creux juste a gauche de la pointe a 88 deg, avec le crochet
    creux = arc_uv(p["r_tete"] - p["prof"] + 0.12, p["r_tete"] + 0.35, -8.0, 4.5).difference(roch.buffer(0.10, join_style=2))
    creux = max(getattr(creux, "geoms", [creux]), key=lambda g: g.area)
    tete = tete.union(creux.buffer(0.05).buffer(-0.05))
    # poteau tete -> ressort
    tete = tete.union(arc_uv(p["r_dessus"] - 0.6, p["r_int"][1] + 0.15, p["phi_tete"] - 4.0, p["phi_tete"] + 2.0, 20))
    # --- ressort
    fibre = LineString(ligne_moyenne(p))
    ep_n = epaisseurs(fibre.coords, p)
    ressort = ressort_poly(fibre.coords, ep_n)
    # --- jambe (porte la charge du verrou vers la paroi de la nacelle) + bourrelet de clip
    vb, hb = p["bourrelet"]
    e0 = p["r_ext"][0]
    sous_bras = Point(0, 0).buffer(e0 - p["ep_max"] / 2 - 0.35, 128)                  # tout l'ancrage reste sous le bras
    jambe = sbox(j0, p["v_jambe0"], j1, 12).intersection(sous_bras)
    jambe = jambe.union(arc_uv(8.95, e0 - p["ep_max"] / 2 - 0.35, p["phi_racine"] - 2.5, math.degrees(math.atan2(j1, 8.0)), 40))
    cb_ = (-p["mur"] - hb + 0.45, vb)
    if hb > 0:                                                 # hb = 0 : coque deja imprimee sans gorge
        jambe = jambe.union(Point(cb_).buffer(0.45, 24).intersection(sbox(-p["mur"] - 1, vb - 1, j0 + 0.01, vb + 1)))
    racine = arc_uv(8.95, e0 + p["ep_max"] / 2, p["phi_racine"] - 2.5, p["phi_racine"] + 0.4, 10)
    jambe = jambe.union(racine).difference(Point(0, 0).buffer(p["r_pignon"] + 0.3, 96))
    gorge = Point(cb_).buffer(0.45 + 0.12, 24)
    # --- languette (a fleur : le generateur la rogne sur la peau du carenage)
    l0, l1 = p["u_lang"]
    lang = sbox(l0, 5.0, l1, p["v_lang1"])                    # rognee a fleur + encoche d'ongle par le generateur
    mobile = unary_union([tete, lang])
    return dict(rochet=roch, tete=tete, ressort=ressort, jambe=jambe, languette=lang, mobile=mobile,
                gorge=gorge, fibre=fibre, ep=ep_n)


def epaisseurs(fibre, p=P, larg=10.1):
    """Ressort a EGALE CONTRAINTE : epaisseur ~ racine du moment (calcule), bornee [ep_min, ep_max], lissee."""
    f = np.asarray(fibre)
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(f, axis=0).T))]
    ep = np.full(len(f), p["ep"])
    for _ in range(6):
        _, _, U = fea(f, ep, larg, p["precharge"] + p["prof"])
        M = np.abs(np.gradient(U[:, 2], s)) * ep ** 3
        ep = np.clip(p["ep_max"] * np.sqrt(M / M.max()), p["ep_min"], p["ep_max"])
        ep = np.convolve(np.pad(ep, 4, mode="edge"), np.ones(9) / 9, "valid")
    return ep


def ressort_poly(fibre, ep):
    f = np.asarray(fibre)
    return unary_union([LineString(f[i:i + 2]).buffer(0.5 * (ep[i] + ep[i + 1]) / 2, 12) for i in range(len(f) - 1)])


# ------------------------------------------------------------------ calcul : poutres planes (Euler-Bernoulli)
E_PLA = 3500.0      # MPa (PLA imprime, sens des fibres)


def fea(fibre_xy, ep, larg, dv, du=0.0, rot_libre=False):
    """Ressort encastre au 1er noeud ; dernier noeud impose (du, dv), rotation bloquee (tete guidee).
    Retourne deformation max (%), effort de rappel (N), deplacements des noeuds."""
    X = np.asarray(fibre_xy, float)
    n = len(X)
    ep_n = np.broadcast_to(np.asarray(ep, float), (n,))
    K = np.zeros((3 * n, 3 * n))
    for e in range(n - 1):
        t_e = 0.5 * (ep_n[e] + ep_n[e + 1]); A, I = larg * t_e, larg * t_e ** 3 / 12
        d = X[e + 1] - X[e]
        L = float(np.hypot(*d)); c, s = d / L
        k = np.array([[E_PLA * A / L, 0, 0, -E_PLA * A / L, 0, 0],
                      [0, 12 * E_PLA * I / L ** 3, 6 * E_PLA * I / L ** 2, 0, -12 * E_PLA * I / L ** 3, 6 * E_PLA * I / L ** 2],
                      [0, 6 * E_PLA * I / L ** 2, 4 * E_PLA * I / L, 0, -6 * E_PLA * I / L ** 2, 2 * E_PLA * I / L],
                      [-E_PLA * A / L, 0, 0, E_PLA * A / L, 0, 0],
                      [0, -12 * E_PLA * I / L ** 3, -6 * E_PLA * I / L ** 2, 0, 12 * E_PLA * I / L ** 3, -6 * E_PLA * I / L ** 2],
                      [0, 6 * E_PLA * I / L ** 2, 2 * E_PLA * I / L, 0, -6 * E_PLA * I / L ** 2, 4 * E_PLA * I / L]])
        T = np.zeros((6, 6)); R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]]); T[:3, :3] = R; T[3:, 3:] = R
        idx = list(range(3 * e, 3 * e + 6))
        K[np.ix_(idx, idx)] += T.T @ k @ T
    fixes = {0: 0.0, 1: 0.0, 2: 0.0, 3 * n - 2: dv}
    if du is not None:
        fixes[3 * n - 3] = du
    if not rot_libre:
        fixes[3 * n - 1] = 0.0
    libres = [i for i in range(3 * n) if i not in fixes]
    U = np.zeros(3 * n)
    for i, v in fixes.items():
        U[i] = v
    fi = list(fixes)
    U[libres] = np.linalg.solve(K[np.ix_(libres, libres)], -K[np.ix_(libres, fi)] @ U[fi])
    F = K @ U
    eps = 0.0
    for e in range(n - 1):                        # moment aux deux bouts de chaque element
        t_e = 0.5 * (ep_n[e] + ep_n[e + 1]); A, I = larg * t_e, larg * t_e ** 3 / 12
        d = X[e + 1] - X[e]
        L = float(np.hypot(*d)); c, s = d / L
        R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        ue = np.r_[R @ U[3 * e:3 * e + 3], R @ U[3 * e + 3:3 * e + 6]]
        Ni = E_PLA * A / L * (ue[3] - ue[0])
        th = (ue[4] - ue[1]) / L
        M0 = E_PLA * I / L * (6 * th - 4 * ue[2] - 2 * ue[5])
        M1 = E_PLA * I / L * (-6 * th + 2 * ue[2] + 4 * ue[5])
        eps = max(eps, (max(abs(M0), abs(M1)) * t_e / 2 / I + abs(Ni) / A) / E_PLA)
    return 100 * eps, float(np.hypot(F[3 * n - 3], F[3 * n - 2])), U.reshape(n, 3)
