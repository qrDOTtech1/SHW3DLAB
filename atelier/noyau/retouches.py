"""RETOUCHES AU PINCEAU (carrossier) sur une coque de carrosserie.

Un trait = liste de touches [x, y, z, nx, ny, nz, r, op] dans le repere du modele (n = normale de la surface).

Surface (avant decoupe) :
- "lisser"  : poncage local (Taubin, sans retrait de matiere) avec fondu au bord du pinceau ;
- "raboter" : la zone est remplacee par la surface ajustee sur son POURTOUR (quadrique locale) : bosses,
              carres, creux disparaissent, la courbure de la tole est conservee. Peau exterieure et interieure
              sont traitees separement (l'epaisseur reste constante).

Decoupe :
- "+" : ajoute la zone a une piece (la matiere est prise a la caisse ou a la piece voisine) ;
- "-" : rend la zone a la caisse.
Le volume d'une touche = cylindre de rayon r le long de la normale, qui traverse l'epaisseur de la coque.
"""
from __future__ import annotations

import numpy as np
import trimesh
import manifold3d as mf
from scipy.spatial import cKDTree


def _repere(n):
    n = n / (np.linalg.norm(n) + 1e-12)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a); u /= np.linalg.norm(u)
    return u, np.cross(n, u), n


def _voisins(m):
    e = m.edges_unique
    nb = [[] for _ in range(len(m.vertices))]
    for a, b in e:
        nb[a].append(b); nb[b].append(a)
    return nb


def raboter(V, VN, arbre, p, n, r, tol=0.12):
    """Remplace la surface dans la sphere (p, r) par la quadrique ajustee sur l'anneau 1.2r..2.2r, par peau.
    Refuse (ne touche a rien) si la tole autour n'est pas bien decrite par une quadrique (erreur > tol mm) :
    jamais de bosse inventee sur une zone tres galbee."""
    idx = np.array(arbre.query_ball_point(p, 2.2 * r), dtype=int)
    if len(idx) < 12:
        return False
    u, v, w = _repere(np.asarray(n, float))
    ok = False
    for sens in (1, -1):                                   # peau exterieure puis interieure
        sel = idx[(VN[idx] @ w) * sens > 0.35]
        if len(sel) < 12:
            continue
        d = V[sel] - p
        x, y, h = d @ u, d @ v, d @ w
        rr = np.hypot(x, y)
        anneau = rr > 1.2 * r
        if anneau.sum() < 10:
            continue
        A = np.c_[np.ones(anneau.sum()), x[anneau], y[anneau], x[anneau] ** 2, x[anneau] * y[anneau], y[anneau] ** 2]
        coef, *_ = np.linalg.lstsq(A, h[anneau], rcond=None)
        err = np.abs(A @ coef - h[anneau])
        if np.percentile(err, 90) > tol:
            continue
        dedans = rr < 1.2 * r
        if not dedans.any():
            continue
        xi, yi = x[dedans], y[dedans]
        cible = coef @ np.vstack([np.ones_like(xi), xi, yi, xi ** 2, xi * yi, yi ** 2])
        t = rr[dedans] / r
        poids = np.clip((1.18 - t) / 0.3, 0, 1)             # plein jusqu'a 0.88 r, fondu jusqu'a 1.18 r
        ids = sel[dedans]
        V[ids] += ((cible - h[dedans]) * poids)[:, None] * w
        ok = True
    return ok


def lisser(V, nb, ids, poids, iters=10):
    """Taubin local (lambda / mu) : lisse sans faire fondre la piece."""
    for k in range(iters):
        f = 0.55 if k % 2 == 0 else -0.58
        moy = np.array([V[nb[i]].mean(0) if nb[i] else V[i] for i in ids])
        V[ids] += f * poids[:, None] * (moy - V[ids])


def retoucher_surface(m: trimesh.Trimesh, touches) -> trimesh.Trimesh:
    if not touches:
        return m
    m = m.copy()
    V = m.vertices.astype(np.float64).copy()
    VN = m.vertex_normals.copy()
    arbre = cKDTree(V)
    nb = None
    for t in touches:
        x, y, z, nx, ny, nz, r, op = t
        p, n = np.array([x, y, z], float), np.array([nx, ny, nz], float)
        if op == "raboter":
            raboter(V, VN, arbre, p, n, float(r))
        elif op == "lisser":
            if nb is None:
                nb = _voisins(m)
            ids = np.array(arbre.query_ball_point(p, float(r)), dtype=int)
            if len(ids):
                d = np.linalg.norm(V[ids] - p, axis=1) / float(r)
                lisser(V, nb, ids, np.clip(1.2 - d, 0, 1))
    m.vertices = V
    return m


def volume_touches(touches, epaisseur=1.8, jeu=0.0):
    """Union des cylindres de pinceau (traversent l'epaisseur de la coque)."""
    cyl = []
    for t in touches:
        x, y, z, nx, ny, nz, r, op = t
        n = np.array([nx, ny, nz], float)
        n /= np.linalg.norm(n) + 1e-12
        h = epaisseur + 7.0
        c = mf.Manifold.cylinder(h, float(r) + jeu, float(r) + jeu, 24).translate((0, 0, -h + 3.0))
        # oriente l'axe Z du cylindre sur la normale
        zax = np.array([0, 0, 1.0])
        v = np.cross(zax, n); s = np.linalg.norm(v); cth = zax @ n
        if s < 1e-9:
            R = np.eye(3) if cth > 0 else np.diag([1, -1, -1.0])
        else:
            vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
            R = np.eye(3) + vx + vx @ vx * ((1 - cth) / s ** 2)
        M = np.c_[R, [x, y, z]]
        cyl.append(c.transform(M))
    if not cyl:
        return None
    return mf.Manifold.batch_boolean(cyl, mf.OpType.Add)


def taches_flancs(m: trimesh.Trimesh, k=1.0, res=0.25):
    """Detecte les CARRES parasites des flancs (contours fins de baguettes mal modelisees, pavés, petits
    creux) et renvoie des touches 'raboter' pour les effacer. Garde poignees, arches, lignes de caisse."""
    from scipy import ndimage
    from atelier.noyau import lignes
    touches = []
    for sg in (1, -1):
        P, u0, v0, r, a, b = lignes.carte(m, 1, sg, res)
        vide = np.isnan(P)
        Pf = np.where(vide, np.nanmin(P), P)
        e = Pf - ndimage.median_filter(Pf, size=(1, int(30 / res) | 1))
        z = v0 + np.arange(P.shape[0])[:, None] * r
        # loin du vide (arches, bas de caisse, vitres decoupees) et des courbures fortes
        loin = ndimage.distance_transform_edt(~vide) * r > 5.0
        gy, gx = np.gradient(ndimage.gaussian_filter(Pf, 3), r)
        plat = np.hypot(gx, gy) < 0.9                        # flanc quasi vertical (pas de bord d'arche)
        zone = (z > 6 * k) & (z < 85 * k) & loin & plat
        trait = (np.abs(e) > 0.12 * k) & (np.abs(e) < 1.0 * k) & zone
        ferme = ndimage.binary_closing(trait, iterations=2)
        interieur = ndimage.binary_fill_holes(ferme) & ~ferme      # l'INTERIEUR des cadres fermes seulement
        # + pavés EN RELIEF plein (agrafes / baguettes fantomes) : bosse compacte de 0.2 a 2 mm
        bosse = ndimage.binary_opening((e > 0.2 * k) & (e < 2.0 * k) & zone, iterations=1)
        bosse = ndimage.binary_dilation(bosse, iterations=2) & zone
        lab, n = ndimage.label(interieur | bosse)
        for i, sl in enumerate(ndimage.find_objects(lab), 1):
            reg = lab[sl] == i
            h_, w_ = (sl[0].stop - sl[0].start) * r, (sl[1].stop - sl[1].start) * r
            if not (1.0 < w_ < 34 and 0.8 < h_ < 16) or reg.mean() < 0.45:
                continue
            em = e[sl][reg]
            if not (np.abs(em).mean() < 0.15 * k or em.mean() > 0.15 * k):   # cadre a fleur OU bosse en relief
                continue
            if em.min() < -1.0 * k:                           # creux profond = vraie forme (poignee)
                continue
            h_, w_ = h_ + 1.5, w_ + 1.5                         # + le cadre lui-meme
            rr = 0.5 * np.hypot(h_, w_) + 1.2
            n_t = max(1, int(np.ceil(w_ / max(h_ * 1.2, 4.0))))      # baguette allongee : plusieurs touches
            cy = (sl[0].start + sl[0].stop) / 2
            for xs in np.linspace(sl[1].start, sl[1].stop, n_t + 2)[1:-1]:
                rt = min(rr, 0.5 * np.hypot(h_, w_ / n_t) + 1.5)
                gyi, gxi = int(cy), int(xs)
                touches.append([float(u0 + gxi * r), float(sg * Pf[gyi, gxi]), float(v0 + gyi * r),
                                0.0, float(sg), 0.0, float(rt), "raboter"])
    return touches


def aplanir_flancs(m: trimesh.Trimesh, k=1.0, res=0.25, paroi=1.8):
    """Efface pavés, cadres et bosses parasites des FLANCS en ramenant la tole sur son profil horizontal
    (mediane sur 30 mm le long de la caisse : garde lignes de caisse, rainures verticales et poignees).
    Les deux peaux bougent ensemble : l'epaisseur ne change pas."""
    from scipy import ndimage
    from scipy.ndimage import map_coordinates
    from atelier.noyau import lignes
    m = m.copy()
    V = m.vertices.astype(np.float64).copy()
    for sg in (1, -1):
        P, u0, v0, r, a, b = lignes.carte(m, 1, sg, res)
        vide = np.isnan(P)
        Pf = np.where(vide, np.nanmin(P), P)
        ref = ndimage.median_filter(Pf, size=(1, int(30 / res) | 1))
        e = Pf - ref
        z = v0 + np.arange(P.shape[0])[:, None] * r
        loin = ndimage.distance_transform_edt(~vide) * r > 4.0
        gy, gx = np.gradient(ndimage.gaussian_filter(Pf, 3), r)
        zone = (z > 6 * k) & (z < 85 * k) & loin & (np.hypot(gx, gy) < 0.9)
        trait = (np.abs(e) > 0.1 * k) & (np.abs(e) < 2.0 * k) & zone
        ferme = ndimage.binary_closing(trait, iterations=3)
        plein = ndimage.binary_fill_holes(ferme) & zone
        lab, n = ndimage.label(plein)
        garde = np.zeros_like(plein)
        for i, sl in enumerate(ndimage.find_objects(lab), 1):
            reg = lab[sl] == i
            h_, w_ = (sl[0].stop - sl[0].start) * r, (sl[1].stop - sl[1].start) * r
            if not (1.0 < w_ < 40 and 0.8 < h_ < 16):
                continue
            if e[sl][reg].min() < -1.0 * k:                  # vrai creux (poignee) : on garde
                continue
            if h_ < 1.5 and w_ > 25:                         # trait fin horizontal = ligne de caisse
                continue
            garde[sl] |= reg
        garde = ndimage.binary_dilation(garde, iterations=3) & zone
        corr = ndimage.gaussian_filter(np.where(garde, -e, 0.0), 1.2)
        cu, cv = (V[:, 0] - u0) / r, (V[:, 2] - v0) / r
        Pv = map_coordinates(Pf, [cv, cu], order=1, mode="nearest")
        c_v = map_coordinates(corr, [cv, cu], order=1, mode="nearest")
        dist = Pv - V[:, 1] * sg                              # 0 = peau exterieure, ~paroi = peau interieure
        sur = (dist > -0.6) & (dist < paroi + 0.8) & (np.abs(c_v) > 0.01)
        V[sur, 1] += sg * c_v[sur]
    m.vertices = V
    return m
