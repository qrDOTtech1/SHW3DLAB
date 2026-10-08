"""LIGNES DE CARROSSERIE : lit les lignes de jeu GRAVEES dans le modele (portes, ailes, capot, coffre, pare-chocs)
et trace le contour exact de chaque piece.

1. carte de profondeur d'une face (lancer de rayons sur une grille fine) ;
2. relief local (profondeur - moyenne locale) : les rainures de jeu ressortent en negatif ;
3. pour chaque piece, quelques POINTS DE REPERE (forme connue de la piece) sont relies par le CHEMIN DE COUT
   MINIMAL sur la carte : le contour colle exactement aux rainures du modele, pas a une forme inventee.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def carte(m, axe, signe, res=0.25):
    """Carte de profondeur vue depuis +/- axe. Retourne (P, u0, v0, res, a, b) : P[ligne, colonne] avec
    colonne -> coordonnee a, ligne -> coordonnee b."""
    lo, hi = m.bounds
    a, b = [i for i in range(3) if i != axe]
    us = np.arange(lo[a], hi[a], res)
    vs = np.arange(lo[b], hi[b], res)
    U, V = np.meshgrid(us, vs)
    o = np.zeros((U.size, 3)); o[:, a] = U.ravel(); o[:, b] = V.ravel()
    o[:, axe] = (hi[axe] + 50) if signe > 0 else (lo[axe] - 50)
    d = np.zeros((U.size, 3)); d[:, axe] = -signe
    P = np.full(U.size, np.nan)
    for k in range(0, U.size, 150_000):                  # par paquets : memoire maitrisee
        loc, idx, _ = m.ray.intersects_location(o[k:k + 150_000], d[k:k + 150_000], multiple_hits=False)
        P[idx + k] = loc[:, axe] * signe
    return P.reshape(U.shape), us[0], vs[0], res, a, b


def relief(P, sigma=3.0):
    sil = ~np.isnan(P)
    Pf = np.where(sil, P, np.nanmin(P))
    return Pf - ndimage.gaussian_filter(Pf, sigma), sil


def cout(P, sigma=3.0, prof=0.04):
    """Cout de passage : faible dans les rainures et sur le bord de la silhouette, fort ailleurs, interdit dans le vide."""
    rel, sil = relief(P, sigma)
    c = 1.0 + 200.0 * np.exp(np.minimum(rel, 0.0) / prof)
    bord = sil & ~ndimage.binary_erosion(sil, iterations=1)
    c[bord] = 40.0                                       # le bord de silhouette n est PAS une ligne de jeu (sauf faute de mieux)
    c[~sil] = 1e4
    return c


def tracer(c, reperes, rayon_accroche=6):
    """Contour ferme passant par les reperes (indices ligne, colonne), chaque troncon suivant les rainures."""
    from skimage.graph import route_through_array
    pts = []
    H, W = c.shape
    # accroche chaque repere au pixel de rainure le plus proche
    acc = []
    for r, q in reperes:
        r0, r1 = max(0, r - rayon_accroche), min(H, r + rayon_accroche + 1)
        q0, q1 = max(0, q - rayon_accroche), min(W, q + rayon_accroche + 1)
        sub = c[r0:r1, q0:q1]
        i, j = np.unravel_index(np.argmin(sub), sub.shape)
        acc.append((r0 + i, q0 + j))
    for k in range(len(acc)):
        a, b = acc[k], acc[(k + 1) % len(acc)]
        chemin, _ = route_through_array(c, a, b, fully_connected=True, geometric=True)
        pts += chemin[:-1]
    return np.array(pts)


def vers_modele(pts, u0, v0, res):
    """indices (ligne, colonne) -> coordonnees (a, b) du modele."""
    return np.c_[u0 + pts[:, 1] * res, v0 + pts[:, 0] * res]
