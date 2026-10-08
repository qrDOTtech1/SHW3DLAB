"""PONCAGE (lissage carrossier) : efface les facettes et cassures douces d'un maillage (grands triangles gauchis
d'un STL imparfait) SANS arrondir les nervures, rainures et aretes vives.

Filtre bilateral des normales de faces (Zheng et al. 2011) : chaque normale est moyennee avec celles de ses
voisines PROCHES EN ORIENTATION seulement (poids gaussien sur l'ecart angulaire) ; puis les sommets sont
deplaces pour suivre les normales filtrees (Sun et al. 2007). Une arete vive (ecart > ~sigma) ne se moyenne
pas : elle reste nette.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy import sparse


def poncer(m: trimesh.Trimesh, sigma_angle_deg=12.0, iter_normales=10, iter_sommets=10, masque_sommets=None, passes=3):
    """Retourne une copie poncee. masque_sommets : booleens des sommets autorises a bouger (None = tous)."""
    m = m.copy()
    V = m.vertices.astype(np.float64)
    F = m.faces
    nf = len(F)
    # voisinage des faces par SOMMET partage (plus large que par arete : facettes en eventail)
    vf = sparse.coo_matrix((np.ones(nf * 3), (np.repeat(np.arange(nf), 3), F.ravel())), shape=(nf, len(V))).tocsr()
    fa = m.face_adjacency                                   # voisines par ARETE (memoire legere)
    i = np.concatenate([fa[:, 0], fa[:, 1], np.arange(nf)])
    j = np.concatenate([fa[:, 1], fa[:, 0], np.arange(nf)])
    s_r = np.radians(sigma_angle_deg)
    for _ in range(passes):                                 # passes externes (normales -> sommets)
        tri = V[F]
        N = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        A = np.linalg.norm(N, axis=1) + 1e-12
        N = N / A[:, None]
        C = tri.mean(1)
        sig_c = 2.0 * np.median(np.linalg.norm(C[i] - C[j], axis=1)) + 1e-9
        Wc = np.exp(-np.sum((C[i] - C[j]) ** 2, 1) / (2 * sig_c ** 2)) * A[j]
        Nf = N.copy()
        for _ in range(iter_normales):
            d = np.arccos(np.clip(np.sum(Nf[i] * Nf[j], 1), -1, 1))
            w = Wc * np.exp(-(d ** 2) / (2 * s_r ** 2))
            W = sparse.csr_matrix((w, (i, j)), shape=(nf, nf))
            Nn = W @ Nf
            Nf = Nn / (np.linalg.norm(Nn, axis=1, keepdims=True) + 1e-12)
        # mise a jour des sommets : chaque sommet glisse vers les plans des faces voisines (normales filtrees)
        deg = np.asarray(vf.sum(0)).ravel() + 1e-12
        for _ in range(iter_sommets // 3 + 1):
            C = V[F].mean(1)
            acc = np.zeros_like(V)
            for k in range(3):
                vk = V[F[:, k]]
                proj = (np.sum(Nf * (C - vk), 1))[:, None] * Nf
                np.add.at(acc, F[:, k], proj)
            dV = acc / deg[:, None]
            if masque_sommets is not None:
                dV[~masque_sommets] = 0
            V = V + dV
    m.vertices = V
    return m
