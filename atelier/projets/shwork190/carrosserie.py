"""CARROSSERIE RC a partir d'un STL de voiture (modele plein, imparfait) : base du projet SHWork 190 SE.

1. preparer : garde la caisse (retire roues et debris), met a l'echelle (longueur cible), oriente (avant = +X),
   pose sur z = 0, centre.
2. coque    : modele PLEIN -> champ de distance signe (voxels + transformee de distance) -> COQUE d'epaisseur
              constante par marching cubes (surface fermee meme si le STL d'origine a des trous), dessous ouvert.
              Les petits trous / defauts du modele d'origine sont refermes au passage.
3. panneaux : detache capot, coffre et portes (prismes de decoupe reglables, avec jeu) -> pieces separees.
4. troncons : decoupe la coque en troncons qui tiennent sur le plateau, avec assemblage (tenons / queue d'aronde / clips).
"""
from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
import manifold3d as mf

from atelier.noyau.c3d import vers_manifold, vers_trimesh

ICI = Path(__file__).resolve().parents[3]
CACHE = ICI / "sortie" / "carrosserie_cache"
CACHE.mkdir(parents=True, exist_ok=True)


def _marching_cubes():
    try:
        from skimage.measure import marching_cubes
        return marching_cubes
    except ImportError:
        p = r"C:\Users\Super\AppData\Local\Programs\Python\Python312\Lib\site-packages"
        if p not in sys.path:
            sys.path.append(p)
        from skimage.measure import marching_cubes        # installe dans le Python principal du PC
        return marching_cubes


# ------------------------------------------------------------------ 1. preparation
def _roues(m, res=0.25):
    """Centres (x, z) et rayon des roues, detectes comme cercles sur la carte de relief du flanc (Hough)."""
    import cv2
    from atelier.noyau import lignes
    P, u0, v0, r, a, b = lignes.carte(m, 1, 1, res)
    rel, sil = lignes.relief(P, 3)
    g = np.clip(128 + rel * 300, 0, 255).astype(np.uint8)
    g[~sil] = 0
    g = cv2.GaussianBlur(g, (5, 5), 1.5)
    H = m.extents[2]
    cs = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.5, minDist=int(0.35 * m.extents[0] / res),
                          param1=80, param2=40, minRadius=int(0.13 * H / res), maxRadius=int(0.25 * H / res))
    out = []
    if cs is not None:
        for cx, cy, rr in cs[0]:
            z = v0 + cy * r
            if z < 0.4 * H:                                   # roues : en bas de la caisse
                out.append((u0 + cx * r, z, rr * r))
    out = sorted(out, key=lambda t: t[0])
    if len(out) > 2:                                          # garde l'avant et l'arriere
        out = [out[0], out[-1]]
    return out


def _preparer_propre(m, longueur, inverser):
    """Modele PROPRE (un seul solide etanche, roues soudees) : oriente, met a l'echelle, retire les roues par
    soustraction (cylindre juste a l'interieur de la levre d'aile : pneu, frein, suspension partent)."""
    if m.extents[1] > m.extents[0]:
        m.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 0, 1]))
    if inverser:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [0, 0, 1]))
    k = longueur / m.extents[0]
    m.apply_scale(k)
    m.apply_translation([-m.bounds.mean(0)[0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
    roues = _roues(m)
    s = vers_manifold(m)
    W = m.extents[1]
    for x, z, rr in roues:
        c = mf.Manifold.cylinder(W + 40, rr + 1.6, rr + 1.6, 96).rotate((90, 0, 0)).translate((x, W / 2 + 20, z))
        bas = mf.Manifold.cube((2 * rr + 3.2, W + 40, z + 2)).translate((x - rr - 1.6, -W / 2 - 20, -2))
        s = s - (c + bas)                                     # + le dessous de la roue jusqu'au sol
        # passage de roue VIDE (debattement de la RC) : on ne garde que la levre d'aile exterieure (7 mm)
        Vv = m.vertices
        pres = (np.abs(Vv[:, 0] - x) < rr + 12) & (Vv[:, 2] > z) & (Vv[:, 2] < z + rr + 12)
        demi = float(np.abs(Vv[pres, 1]).max()) if pres.any() else W / 2      # demi-largeur de la caisse a la roue
        li = 2 * (demi - 7.0)
        vide = mf.Manifold.cylinder(li, rr + 7.0, rr + 7.0, 96).rotate((90, 0, 0)).translate((x, li / 2, z))
        s = s - (vide + mf.Manifold.cube((2 * rr + 14, li, z + 2)).translate((x - rr - 7, -li / 2, -2)))
    out = vers_trimesh(s)
    parts = sorted(out.split(only_watertight=False), key=lambda c: -abs(c.volume))
    out = parts[0]
    return out, {"echelle": round(k, 4), "roues": [[round(a, 1) for a in t] for t in roues], "modele": "propre",
                 "dimensions_mm": [round(float(x), 1) for x in out.extents]}


def preparer(chemin, longueur=445.0, inverser=False, garder_petits=True):
    m = trimesh.load(str(chemin), force="mesh")
    m.merge_vertices()
    comps = sorted(m.split(only_watertight=False), key=lambda c: -len(c.faces))
    if comps[0].is_watertight and len(comps[0].faces) > 0.95 * len(m.faces):
        return _preparer_propre(comps[0], longueur, inverser)
    caisse = comps[0]
    bb = caisse.bounds
    garde = [caisse]
    retire = []
    for c in comps[1:]:
        roue = len(c.faces) > 2000 and c.bounds[0][2] <= bb[0][2] + 1.0            # gros morceau qui touche le sol = roue
        if roue:
            retire.append("roue")
            continue
        if garder_petits:
            garde.append(c)
    m = trimesh.util.concatenate(garde)
    # longueur selon le plus grand axe horizontal
    ext = m.extents
    if ext[1] > ext[0]:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 0, 1]))
    k = longueur / m.extents[0]
    m.apply_scale(k)
    if inverser:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [0, 0, 1]))
    m.apply_translation([-m.bounds.mean(0)[0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
    m = nettoyer(m, longueur)
    return m, {"echelle": round(k, 4), "roues_retirees": len(retire), "morceaux_gardes": len(garde),
               "dimensions_mm": [round(float(x), 1) for x in m.extents]}


def nettoyer(m, longueur=445.0):
    """Retire ce qu'un carrossier ne garde pas : mecanique dans les passages de roue (etriers, suspension, debris),
    antenne (fil inimprimable), fragments ouverts minuscules. Reperes de la Mercedes 190 (modele a 445 mm)."""
    k = longueur / 445.0
    c = m.triangles_center
    garde = np.ones(len(m.faces), bool)
    for xc in (-144.0, 118.0):                            # centres des roues (x, z = 31) : cylindre de 27 mm
        garde &= np.hypot(c[:, 0] - xc * k, c[:, 2] - 31.0 * k) > 27.0 * k
    vh = m.vertices[m.faces]                                                           # antenne : tout triangle qui y touche
    garde &= ~(((vh[:, :, 0] > 150 * k) & (vh[:, :, 0] < 178 * k) & (vh[:, :, 2] > 99.5 * k)).any(1))
    m = m.submesh([np.nonzero(garde)[0]], append=True)
    parts = m.split(only_watertight=False)
    m = trimesh.util.concatenate([p for p in parts if len(p.faces) >= 8])
    m = debosseler(m, k)
    return debosseler(m, k)


def debosseler(m, k=1.0, res=0.25, seuil=0.18):
    """Pavés / creux parasites des flancs (baguettes mal modelisees du STL) : sur chaque flanc, la tole de
    reference = mediane HORIZONTALE (garde les lignes de caisse, efface les pavés courts) ; les sommets des
    zones compactes qui s'en ecartent sont ramenes sur la tole. Bande 10-62 mm, loin des passages de roue."""
    from scipy import ndimage
    from scipy.ndimage import map_coordinates
    from atelier.noyau import lignes
    # les pavés sont souvent portes par de GRANDS triangles : on subdivise les flancs de la bande (aretes <= 1.5 mm)
    c, n = m.triangles_center, m.face_normals
    flanc = (np.abs(c[:, 1]) > 55 * k) & (c[:, 2] > 5 * k) & (c[:, 2] < 67 * k)
    if flanc.any():
        a_ = m.submesh([np.nonzero(flanc)[0]], append=True)
        b_ = m.submesh([np.nonzero(~flanc)[0]], append=True)
        v2, f2 = trimesh.remesh.subdivide_to_size(a_.vertices, a_.faces, max_edge=1.5 * k, max_iter=12)
        m = trimesh.util.concatenate([trimesh.Trimesh(v2, f2, process=False), b_])
    V = m.vertices.copy()
    for sg in (1, -1):
        P, u0, v0, r, a, b = lignes.carte(m, 1, sg, res)
        vide = np.isnan(P)
        Pf = np.where(vide, np.nanmin(P), P)
        med = ndimage.median_filter(Pf, size=(1, int(30 / res) | 1))
        e = Pf - med
        z = v0 + np.arange(P.shape[0])[:, None] * r
        loin = ndimage.distance_transform_edt(~vide) * r > 4.0          # loin des bords / passages de roue
        zone = (z > 10 * k) & (z < 62 * k) & loin
        mask = (np.abs(e) > seuil * k) & zone
        mask = ndimage.binary_opening(mask, iterations=2)                 # compact : pas les traits fins
        mask = ndimage.binary_dilation(mask, iterations=3) & zone
        corr = np.where(mask, -e, 0.0)
        corr = ndimage.gaussian_filter(corr, 1.0)
        # sommets du flanc : proches de la surface vue de ce cote
        cu, cv = (V[:, 0] - u0) / r, (V[:, 2] - v0) / r
        Pv = map_coordinates(Pf, [cv, cu], order=1, mode="nearest")
        cv_ = map_coordinates(corr, [cv, cu], order=1, mode="nearest")
        sur = (np.abs(V[:, 1] * sg - Pv) < 1.6 * k) & (np.abs(cv_) > 0.02)
        V[sur, 1] += sg * cv_[sur]
    m.vertices = V
    return m


# ------------------------------------------------------------------ 2. coque
def coque(m, paroi=1.8, pas=0.6, ouvrir_dessous=True, lissage=2, simplifier=0.04):
    """Coque d'epaisseur `paroi` (interieur du modele plein), dessous ouvert. Robuste aux trous du STL."""
    from scipy import ndimage
    mc = _marching_cubes()
    # voxelisation maison (memoire maitrisee) : echantillonnage dense de la surface -> voxels de peau,
    # dilatation d'1 voxel (referme les petits trous du STL), remplissage de l'interieur, erosion de compensation
    lo = m.bounds[0] - 3 * pas
    dims = np.ceil((m.bounds[1] - m.bounds[0]) / pas).astype(int) + 7
    n_pts = int(min(12e6, m.area / (pas * 0.35) ** 2))
    pts, _ = trimesh.sample.sample_surface(m, n_pts)
    idx = np.floor((pts - lo) / pas).astype(int)
    idx = np.clip(idx, 0, dims - 1)
    peau = np.zeros(dims, dtype=bool)
    peau[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    peau = ndimage.binary_dilation(peau, iterations=1)
    plein = ndimage.binary_fill_holes(peau)
    plein = ndimage.binary_erosion(plein, iterations=1)
    d_in = ndimage.distance_transform_edt(plein) * pas
    d_out = ndimage.distance_transform_edt(~plein) * pas
    s = np.where(plein, d_in - pas / 2, -(d_out - pas / 2))       # distance signee (positive dedans)
    s = ndimage.gaussian_filter(s.astype(np.float32), sigma=0.8)      # surface lisse (pas de marches de voxels)
    champ = np.minimum(s, paroi - s)                    # > 0 dans la coque (0 < s < paroi)
    if ouvrir_dessous:
        # dessous OUVERT comme une vraie carrosserie de RC : dans chaque colonne verticale, la peau inferieure
        # (premier passage dans la matiere en montant) est retiree -> plancher supprime, on voit l'interieur par dessous
        dedans = s > 0
        a_matiere = dedans.any(axis=2)
        z_bas = np.argmax(dedans, axis=2)                 # premier voxel plein en partant du bas
        n_peau = int(math.ceil((paroi + 0.6) / pas)) + 1
        zz = np.arange(champ.shape[2])[None, None, :]
        retire = a_matiere[:, :, None] & (zz >= z_bas[:, :, None] - 1) & (zz <= z_bas[:, :, None] + n_peau)
        champ[retire] = -1.0
    e_dbl = 1.6
    champ2 = np.minimum(s - (paroi + 0.15), (paroi + 0.15 + e_dbl) - s)      # doublure : 0.15 mm sous la peau interieure
    if ouvrir_dessous:
        champ2[retire] = -1.0
    v2, f2, _, _ = mc(champ2.astype(np.float32), 0.0, spacing=(pas, pas, pas))
    doublure = trimesh.Trimesh(v2 + lo, f2[:, ::-1], process=True)
    if doublure.volume < 0:
        doublure.invert()
    verts, faces, _, _ = mc(champ.astype(np.float32), 0.0, spacing=(pas, pas, pas))
    # repere : la grille commence a origine du voxel grid - 3 voxels de marge
    verts = verts + lo
    sh = trimesh.Trimesh(verts, faces[:, ::-1], process=True)
    if sh.volume < 0:
        sh.invert()
    if lissage:
        trimesh.smoothing.filter_taubin(sh, iterations=lissage)
    s_m = vers_manifold(sh)
    if simplifier:
        s_m = s_m.simplify(simplifier)
    out = vers_trimesh(s_m)
    # garde la plus grosse piece (+ les morceaux importants) : supprime les copeaux
    parts = sorted(out.split(only_watertight=False), key=lambda c: -abs(c.volume))
    out = trimesh.util.concatenate([c for c in parts if abs(c.volume) > 20])
    out.metadata["doublure"] = doublure
    return out


# ------------------------------------------------------------------ 2b. coque PRECISE (distance signee exacte, libigl)
def _sdf(V, F, P, lo_b=-np.inf, hi_b=np.inf):
    import igl
    out = np.empty(len(P))
    for k in range(0, len(P), 1_000_000):
        out[k:k + 1_000_000] = igl.signed_distance(np.ascontiguousarray(P[k:k + 1_000_000]), V, F, sign_type=igl.SIGNED_DISTANCE_TYPE_FAST_WINDING_NUMBER,
                                                  lower_bound=lo_b, upper_bound=hi_b)[0]
    return out


def coque_precise(m, paroi=1.8, pas=0.35, ouvrir_dessous=True, e_doublure=1.6, tranche=24, journal=None, poncage=True):
    """Coque fidele au 1/10 mm : distance SIGNEE EXACTE au maillage d'origine (nombre d'enroulement generalise :
    juste meme sur un STL troue / non-manifold), grille fine seulement pres de la peau, marching cubes par tranches.
    s > 0 DEDANS. Coque = 0 < s < paroi ; doublure = paroi+0.15 < s < paroi+0.15+e_doublure."""
    from scipy.ndimage import map_coordinates
    mc = _marching_cubes()
    V = np.ascontiguousarray(m.vertices, dtype=np.float64)
    F = np.ascontiguousarray(m.faces, dtype=np.int64)
    lo = m.bounds[0] - 3 * pas
    dims = np.ceil((m.bounds[1] - m.bounds[0]) / pas).astype(int) + 7
    # 1. grille grossiere (signe + distance approchee partout)
    pg = 1.2
    dg = np.ceil((dims * pas) / pg).astype(int) + 2
    G = np.stack(np.meshgrid(*[lo[i] + np.arange(dg[i]) * pg for i in range(3)], indexing="ij"), -1).reshape(-1, 3)
    sg = (-_sdf(V, F, G)).reshape(dg).astype(np.float32)
    del G
    band_lo, band_hi = -1.0 - 1.5 * pg, paroi + 0.15 + e_doublure + 1.0 + 1.5 * pg
    n_peau = int(math.ceil((paroi + 0.6) / pas)) + 1
    # PLANCHER a ouvrir : colonnes ou la face inferieure est quasi horizontale (pente < 40 deg), decide sur la
    # grille grossiere (meme decision pour toutes les tranches : pas de couture). Les faces inclinees (bas de
    # pare-chocs, bas de caisse arrondi) restent intactes.
    ded_g = sg > 0
    a_g = ded_g.any(axis=2)
    zb_g = np.where(a_g, np.argmax(ded_g, axis=2), 0).astype(np.float32) * pg
    gx, gy = np.gradient(zb_g, pg)
    plancher_g = a_g & (np.hypot(gx, gy) < 0.84) & (zb_g < 0.24 * (m.bounds[1][2] - m.bounds[0][2]))   # le plancher est EN BAS (pas sous les arches)
    from scipy import ndimage as _nd
    plancher_g = _nd.binary_opening(plancher_g, iterations=1)
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="coque_"))
    morceaux, morceaux2 = [], []      # morceaux2 (doublure) : sur disque, traite apres la coque (memoire)
    zz = np.arange(dims[2])[None, None, :]
    ys, zs = np.arange(dims[1]), np.arange(dims[2])
    for x0 in range(0, dims[0] - 1, tranche):
        x1 = min(dims[0], x0 + tranche + 1)
        nx = x1 - x0
        gx_, gy_, gz_ = np.meshgrid(np.arange(x0, x1, dtype=np.float32) * pas, ys.astype(np.float32) * pas,
                                    zs.astype(np.float32) * pas, indexing="ij")
        s = map_coordinates(sg, [gx_ / pg, gy_ / pg, gz_ / pg], order=1, mode="nearest").astype(np.float32)
        q = (s > band_lo) & (s < band_hi)
        if q.any():
            X = np.c_[gx_[q], gy_[q], gz_[q]].astype(np.float64) + lo
            s[q] = -_sdf(V, F, X)
            del X
        del gx_, gy_, gz_, q
        retire = None
        if ouvrir_dessous:
            dedans = s > 0
            a_mat = dedans.any(axis=2)
            z_bas = np.argmax(dedans, axis=2)
            gi = np.clip(np.round((lo[0] + np.arange(x0, x1) * pas - lo[0]) / pg).astype(int), 0, dg[0] - 1)
            gj = np.clip(np.round(ys * pas / pg).astype(int), 0, dg[1] - 1)
            pl = plancher_g[gi][:, gj] & a_mat
            retire = pl[:, :, None] & (zz >= z_bas[:, :, None] - 1) & (zz <= z_bas[:, :, None] + n_peau)
        for cible, (a_, b_) in ((morceaux, (0.0, paroi)), (morceaux2, (paroi + 0.15, paroi + 0.15 + e_doublure))):
            ch = np.minimum(s - a_, b_ - s)
            if retire is not None:
                ch[retire] = -1.0
            if ch.max() <= 0:
                continue
            v, f, _, _ = mc(ch, 0.0, spacing=(pas, pas, pas))
            vv = (v + lo + np.array([x0 * pas, 0, 0])).astype(np.float32)
            if cible is morceaux2:
                fn = tmp / f"d{x0}.npz"
                np.savez(fn, v=vv, f=f.astype(np.int32))
                cible.append(fn)
            else:
                cible.append((vv, f.astype(np.int32)))
        if journal:
            journal(f"coque : tranche {x0 // tranche + 1}/{(dims[0] - 2) // tranche + 1}")

    def souder(liste):
        # soudure + simplification, sans calcul lourd sur le maillage brut (memoire)
        vs, fs, n = [], [], 0
        for v, f in liste:
            vs.append(v.astype(np.float32)); fs.append((f + n).astype(np.int32)); n += len(v)
        liste.clear()
        t = trimesh.Trimesh(np.vstack(vs), np.vstack(fs)[:, ::-1], process=False)
        del vs, fs
        t.merge_vertices(digits_vertex=5)
        t.update_faces(t.nondegenerate_faces()); t.remove_unreferenced_vertices()
        m_ = vers_manifold(t).simplify(0.005)
        del t
        out_ = vers_trimesh(m_)
        if out_.volume < 0:
            out_.invert()
        return out_
    del sg
    sh = souder(morceaux)
    from atelier.noyau.poncage import poncer                       # ponçage carrossier : efface les plis / facettes du STL
    if poncage:
        sh = vers_trimesh(vers_manifold(poncer(sh, sigma_angle_deg=18, passes=7, iter_normales=12)))
    sh_m = sh
    import gc
    gc.collect()
    l2 = []
    for fn in morceaux2:
        with np.load(fn) as z:
            l2.append((np.array(z["v"]), np.array(z["f"])))
        fn.unlink()
    doublure = souder(l2)
    try:
        tmp.rmdir()
    except OSError:
        pass
    out = sh
    parts = sorted(out.split(only_watertight=False), key=lambda c: -abs(c.volume))
    out = trimesh.util.concatenate([c for c in parts if abs(c.volume) > 20])
    out.metadata["doublure"] = doublure
    return out


def coque_cache(chemin, longueur, paroi, pas, inverser):
    h = hashlib.sha1(f"{Path(chemin).stat().st_size}|{Path(chemin).stat().st_mtime}|{longueur}|{paroi}|{pas}|{inverser}".encode()).hexdigest()[:16]
    f = CACHE / f"coque_{h}.ply"
    fi = CACHE / f"coque_{h}.json"
    if f.exists():
        import json
        return trimesh.load(f, force="mesh", process=False), json.loads(fi.read_text())
    base, info = preparer(chemin, longueur, inverser)
    c = coque(base, paroi, pas)
    c.export(f)
    import json
    info.update({"triangles": len(c.faces), "paroi": paroi, "pas": pas})
    fi.write_text(json.dumps(info))
    return c, info


# ------------------------------------------------------------------ 3. panneaux (decoupes reglables)
# fractions de la longueur (x : 0 = AVANT = -X, 1 = ARRIERE) et de la hauteur (z) - Mercedes 190 (W201), a ajuster
PANNEAUX_190E = {
    "capot":     {"vue": "dessus", "x": (0.035, 0.285), "y_marge": 0.10, "z_min": 0.56},
    "coffre":    {"vue": "dessus", "x": (0.835, 0.985), "y_marge": 0.11, "z_min": 0.58},
    # portes : contour en vue de cote (x, z) en fractions ; montant de pare-brise incline, arriere suivant l'arche
    "porte_avg": {"vue": "cote", "cote": 1, "contour": [(0.367, 0.16), (0.563, 0.16), (0.563, 0.90), (0.445, 0.90), (0.367, 0.66)]},
    "porte_avd": {"vue": "cote", "cote": -1, "contour": [(0.367, 0.16), (0.563, 0.16), (0.563, 0.90), (0.445, 0.90), (0.367, 0.66)]},
    "porte_arg": {"vue": "cote", "cote": 1, "contour": [(0.567, 0.16), (0.695, 0.16), (0.735, 0.30), (0.735, 0.60), (0.690, 0.88), (0.567, 0.90)]},
    "porte_ard": {"vue": "cote", "cote": -1, "contour": [(0.567, 0.16), (0.695, 0.16), (0.735, 0.30), (0.735, 0.60), (0.690, 0.88), (0.567, 0.90)]},
}


def boite_panneau(nom, cfg, bounds, jeu=0.0, profondeur=32.0):
    """Prisme de decoupe d'un panneau (repere de la coque). jeu > 0 : prisme agrandi (logement du panneau)."""
    from shapely.geometry import Polygon
    from atelier.noyau.c3d import section
    (x0, y0, z0), (x1, y1, z1) = bounds
    L, Wd, H = x1 - x0, y1 - y0, z1 - z0
    if cfg["vue"] == "dessus":
        xa, xb = x0 + cfg["x"][0] * L, x0 + cfg["x"][1] * L
        ym = cfg["y_marge"] * Wd
        za = z0 + cfg["z_min"] * H
        return mf.Manifold.cube((xb - xa + 2 * jeu, Wd - 2 * ym + 2 * jeu, z1 - za + 20)).translate((xa - jeu, y0 + ym - jeu, za - jeu))
    pts = [(x0 + fx * L, z0 + fz * H) for fx, fz in cfg["contour"]]
    poly = Polygon(pts).buffer(jeu, join_style=2) if jeu else Polygon(pts)
    s = cfg.get("cote", 1)
    ya = (y1 - profondeur) if s > 0 else (y0 - 20)
    yb = (y1 + 20) if s > 0 else (y0 + profondeur)
    # extrusion du contour (plan XZ) le long de Y
    pr = mf.Manifold.extrude(section(poly), yb - ya)                 # contour dans XY, extrude selon Z
    M = np.array([[1, 0, 0, 0], [0, 0, 1, ya], [0, 1, 0, 0]], float)  # (x, y, z) -> (x, z + ya, y)
    return pr.transform(M)


def detacher(coque_m, panneaux: dict, jeu=0.35, profondeur=32.0, ref_bounds=None):
    """-> (caisse, {nom: panneau}). Le panneau = coque dans le prisme ; la caisse = coque moins le prisme agrandi du jeu."""
    b = ref_bounds if ref_bounds is not None else coque_m.bounds
    S = vers_manifold(coque_m)
    out = {}
    caisse = S
    for nom, cfg in panneaux.items():
        P = boite_panneau(nom, cfg, b, 0.0, profondeur)
        piece = S ^ P
        if piece.is_empty() or piece.volume() < 50:
            continue
        out[nom] = vers_trimesh(piece)
        caisse = caisse - boite_panneau(nom, cfg, b, jeu, profondeur)
    return vers_trimesh(caisse), out


# ------------------------------------------------------------------ 4. troncons
def troncons(caisse, doublure, longueur_max=180.0, recouvrement=10.0):
    """Coupe la caisse en N troncons egaux le long de X (chacun imprime DEBOUT sur une face de coupe) + une ECLISSE
    par coupe : bague qui epouse l'interieur de la coque sur +/- recouvrement, a coller a cheval (jeu 0.15)."""
    x0, x1 = caisse.bounds[0][0], caisse.bounds[1][0]
    n = max(1, int(math.ceil((x1 - x0) / longueur_max)))
    coupes = [x0 + (x1 - x0) * k / n for k in range(1, n)]
    S, D = vers_manifold(caisse), vers_manifold(doublure)
    bornes = [x0 - 1] + coupes + [x1 + 1]
    morceaux = []
    for a, b in zip(bornes[:-1], bornes[1:]):
        morceaux.append(vers_trimesh(S ^ mf.Manifold.cube((b - a, 1e4, 1e4)).translate((a, -5e3, -5e3))))
    eclisses = []
    for c in coupes:
        e = D ^ mf.Manifold.cube((2 * recouvrement, 1e4, 1e4)).translate((c - recouvrement, -5e3, -5e3))
        if not e.is_empty():
            m = vers_trimesh(e)
            # retire les copeaux (petits morceaux de doublure isoles)
            parts = [q for q in m.split(only_watertight=False) if abs(q.volume) > 30]
            if parts:
                eclisses.append(trimesh.util.concatenate(parts))
    return morceaux, eclisses, coupes


# ================================================================== DECOUPE SUR LES LIGNES DE JEU DU MODELE (pas de formes inventees)
# Reperes de chaque piece, en FRACTIONS de la carte (x : 0 = avant, y : 0 = haut de l'image), lus sur le modele
# Mercedes 190 (W201). Le contour final suit les rainures du modele entre ces reperes (chemin de cout minimal).
_F, _D = (983.0, 316.0), (983.0, 376.0)          # tailles des cartes de reference (flanc, dessus) a 0.25 mm
_fl = lambda pts: [(x / _F[0], y / _F[1]) for x, y in pts]
_ds = lambda pts: [(x / _D[0], y / _D[1]) for x, y in pts]
LIGNES_190E = {
    "capot":        {"vue": "dessus", "reperes": _ds([(50, 48), (90, 47), (130, 46), (170, 45), (210, 45), (250, 44), (285, 44),
                                                       (285, 330), (250, 329), (210, 329), (170, 328), (130, 328), (90, 327), (50, 327)]), "accroche": 3},
    "coffre":       {"vue": "dessus", "reperes": _ds([(832, 70), (890, 68), (940, 66), (940, 310), (890, 308), (832, 306)]), "accroche": 4},
    "pare_choc_av": {"vue": "flanc", "toute_largeur": True, "reperes": _fl([(2, 190), (105, 188), (108, 262), (2, 262)]), "accroche": 4},
    "pare_choc_ar": {"vue": "flanc", "toute_largeur": True, "reperes": _fl([(905, 190), (965, 195), (965, 245), (905, 248)]), "accroche": 4},
    "aile_avg":     {"vue": "flanc", "cote": 1, "reperes": _fl([(30, 128), (296, 113), (300, 245), (248, 248), (170, 165), (105, 188), (40, 170)]), "accroche": 4},
    "aile_avd":     {"vue": "flanc", "cote": -1, "symetrique_de": "aile_avg"},
    "porte_avg":    {"vue": "flanc", "cote": 1, "reperes": _fl([(301, 245), (300, 120), (395, 22), (521, 16), (523, 245)]), "accroche": 4},
    "porte_avd":    {"vue": "flanc", "cote": -1, "symetrique_de": "porte_avg"},
    "porte_arg":    {"vue": "flanc", "cote": 1, "reperes": _fl([(531, 245), (530, 16), (650, 22), (712, 98), (735, 104), (705, 170), (660, 245), (600, 245)]), "accroche": 4},
    "porte_ard":    {"vue": "flanc", "cote": -1, "symetrique_de": "porte_arg"},
}
ORDRE_DECOUPE = ["capot", "coffre", "pare_choc_av", "pare_choc_ar", "aile_avg", "aile_avd", "porte_avg", "porte_avd", "porte_arg", "porte_ard"]


# Contours releves sur les lignes de jeu visibles du modele (cartes de relief 1978x596 flanc / 1978x758 dessus,
# x = 0 avant, y = 0 haut ; dessus : y = 0 cote +Y). Verifies superposes a la carte (sortie/chk_*.png).
_IMG = {"flanc": (1978.0, 596.0), "dessus": (1978.0, 758.0)}
POLY_190E = {
    "capot": [(88, 98), (330, 96), (572, 92), (560, 240), (548, 380), (560, 520), (572, 665), (330, 662), (88, 660), (62, 520), (55, 380), (62, 240)],
    "coffre": [(1640, 122), (1700, 125), (1910, 140), (1912, 380), (1910, 620), (1700, 630), (1640, 635), (1668, 500), (1678, 380), (1668, 260)],
    "pare_choc_av": [(4, 372), (205, 378), (198, 440), (188, 528), (40, 528), (10, 470)],
    "pare_choc_ar": [(1812, 388), (1930, 386), (1976, 400), (1976, 520), (1880, 524), (1825, 525)],
    "aile_avg": [(80, 288), (300, 262), (560, 234), (600, 240), (598, 285), (606, 400), (612, 496), (500, 496), (488, 420), (455, 360),
                 (400, 322), (330, 312), (265, 328), (220, 362), (205, 378), (65, 372), (75, 330)],
    "porte_avg": [(600, 285), (628, 232), (700, 165), (800, 55), (930, 38), (1056, 30), (1056, 260), (1056, 500), (830, 500), (614, 497), (606, 400)],
    "porte_arg": [(1064, 30), (1200, 36), (1300, 45), (1400, 145), (1478, 212), (1474, 280), (1420, 320), (1360, 380), (1330, 440), (1308, 500), (1064, 502), (1062, 260)],
}
POLY_190E["porte_avg"] = POLY_190E["porte_avg"]


def contours_lignes(base, res=0.25, cache=None):
    """Contours (repere du modele) : flanc -> (x, z), dessus -> (x, y), d'apres les bornes du modele prepare."""
    import json
    if cache is not None and cache.exists():
        d = json.loads(cache.read_text())
        if d.get("v") == 2:
            return {k: np.array(v) for k, v in d["c"].items()}
    lo, hi = base.bounds
    out = {}
    for nom, pts in POLY_190E.items():
        vue = LIGNES_190E[nom]["vue"]
        W, H = _IMG[vue]
        q = np.array(pts, float)
        x = lo[0] + q[:, 0] / W * (hi[0] - lo[0])
        if vue == "flanc":
            v = hi[2] - q[:, 1] / H * (hi[2] - lo[2])
        else:
            v = hi[1] - q[:, 1] / H * (hi[1] - lo[1])
        out[nom] = np.c_[x, v]
    if cache is not None:
        cache.write_text(json.dumps({"v": 2, "c": {k: v.tolist() for k, v in out.items()}}))
    return out


def prisme_contour(nom, contours, bounds, jeu=0.0, profondeur=32.0):
    """Prisme de decoupe a partir du contour lu sur le modele (repere de la coque)."""
    from shapely.geometry import Polygon
    from atelier.noyau.c3d import section
    cfg = LIGNES_190E[nom]
    src = cfg.get("symetrique_de", nom)
    pts = contours[src]
    poly = Polygon(pts).buffer(0)
    if jeu:
        poly = poly.buffer(jeu, join_style=2)
    poly = poly.simplify(0.05)
    (x0, y0, z0), (x1, y1, z1) = bounds
    if cfg["vue"] == "dessus":
        # le capot / coffre : la peau du dessus seulement (de 22 mm sous le point le plus bas du contour au-dessus du toit)
        return mf.Manifold.extrude(section(poly), z1 - z0 + 40).translate((0, 0, z0 + 0.42 * (z1 - z0)))
    if cfg.get("toute_largeur"):
        ya, yb = y0 - 20, y1 + 20
    else:
        s = cfg.get("cote", 1)
        ya = (y1 - profondeur) if s > 0 else (y0 - 20)
        yb = (y1 + 20) if s > 0 else (y0 + profondeur)
    pr = mf.Manifold.extrude(section(poly), yb - ya)
    return pr.transform(np.array([[1, 0, 0, 0], [0, 0, 1, ya], [0, 1, 0, 0]], float))


def detacher_lignes(coque_m, contours, choix, jeu=0.35, profondeur=32.0):
    """Detache les pieces choisies dans l'ORDRE_DECOUPE ; chaque piece = coque restante dans son prisme."""
    S = vers_manifold(coque_m)
    b = coque_m.bounds
    out = {}
    for nom in ORDRE_DECOUPE:
        if nom not in choix:
            continue
        P = prisme_contour(nom, contours, b, 0.0, profondeur)
        piece = S ^ P
        if piece.is_empty() or piece.volume() < 50:
            continue
        # garde le gros morceau (pas les copeaux du bord)
        pm = vers_trimesh(piece)
        parts = sorted(pm.split(only_watertight=False), key=lambda q: -abs(q.volume))
        out[nom] = trimesh.util.concatenate([q for q in parts if abs(q.volume) > 0.05 * abs(parts[0].volume)])
        S = S - prisme_contour(nom, contours, b, jeu, profondeur)
    return vers_trimesh(S), out


# ================================================================== DECOUPE PRECISE (carrossier) : contours aimantes sur les rainures
# Petites pieces vues de FACE / de DOS (cartes 0.2 mm, 852 x 669 px, colonne -> y = -85.16 + c*0.2, ligne
# affichee -> z = (668 - l)*0.2), modele a 445 mm. Chaque piece : polygone + tranche en X (debut, fin) en mm.
_FACE = {
    "calandre": {"vue": "avant", "x": (-235, -196), "poly": [(268, 314), (279, 300), (404, 300), (404, 244), (448, 244), (448, 300), (571, 300), (583, 314), (583, 433), (268, 433)]},
    "phare_g": {"vue": "avant", "x": (-235, -194), "poly": [(70, 333), (264, 329), (264, 430), (76, 431)]},
    "phare_d": {"vue": "avant", "x": (-235, -194), "poly": [(588, 329), (782, 333), (776, 431), (588, 430)]},
    "plaque_av": {"vue": "avant", "x": (-235, -200), "poly": [(306, 456), (546, 456), (546, 518), (306, 518)]},
    "feu_g": {"vue": "arriere", "x": (196, 235), "poly": [(97, 324), (294, 322), (294, 395), (97, 394)]},
    "feu_d": {"vue": "arriere", "x": (196, 235), "poly": [(558, 322), (755, 324), (755, 394), (558, 395)]},
    "retro_g": {"vue": "avant", "x": (-82, -45), "poly": [(0, 193), (40, 193), (40, 254), (0, 254)]},
    "retro_d": {"vue": "avant", "x": (-82, -45), "poly": [(812, 193), (852, 193), (852, 254), (812, 254)]},
    # partie VERTICALE du coffre (entre les feux, jusqu'au pare-chocs) : reunie au dessus du coffre
    "coffre_dos": {"vue": "arriere", "x": (190, 235), "poly": [(158, 214), (696, 214), (696, 321), (556, 321), (556, 430), (297, 430), (297, 321), (158, 321)]},
}


def _face_mm(poly, k=1.0):
    return [((-85.1588 + c * 0.2) * k, (668 - l) * 0.2 * k) for c, l in poly]


def aimanter(pts, P, u0, v0, res, rayon=2.5, seuil=-0.03, lissage=9):
    """Deplace chaque point du contour (coords modele 2D) le long de la normale du contour jusqu'au fond de la
    rainure la plus proche (relief < seuil) a moins de `rayon` mm ; decalages lisses le long du contour."""
    from shapely.geometry import Polygon as _P
    from scipy.ndimage import map_coordinates, median_filter
    from atelier.noyau import lignes
    rel, sil = lignes.relief(P, 3.0)
    poly = _P(pts).buffer(0)
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    L = poly.exterior.length
    n = max(64, int(L / 0.4))
    q = np.array([poly.exterior.interpolate(i / n, normalized=True).coords[0] for i in range(n)])
    t = np.roll(q, -1, 0) - np.roll(q, 1, 0)
    nr = np.c_[t[:, 1], -t[:, 0]] / (np.linalg.norm(t, axis=1)[:, None] + 1e-9)
    offs = np.arange(-rayon, rayon + 1e-6, res / 2)
    best = np.zeros(n)
    for i in range(n):
        c = q[i] + offs[:, None] * nr[i]
        r = map_coordinates(rel, [(c[:, 1] - v0) / res, (c[:, 0] - u0) / res], order=1, mode="nearest")
        cost = r + 0.004 * np.abs(offs)               # a profondeur egale : la rainure la plus proche
        j = np.argmin(cost)
        best[i] = offs[j] if r[j] < seuil else np.nan
    ok = ~np.isnan(best)
    if ok.sum() < n * 0.2:
        return q
    idx = np.arange(n)
    best = np.interp(idx, idx[ok], best[ok], period=n)
    best = median_filter(best, size=lissage, mode="wrap")
    from scipy.ndimage import uniform_filter1d
    best = uniform_filter1d(best, size=max(5, lissage), mode="wrap")      # plus de crans : tracé continu
    out = q + best[:, None] * nr
    # Chaikin x2 : arrondit les petites cassures restantes sans s'ecarter de la rainure
    for _ in range(2):
        a_, b_ = out, np.roll(out, -1, 0)
        out = np.empty((2 * len(a_), 2))
        out[0::2] = 0.75 * a_ + 0.25 * b_
        out[1::2] = 0.25 * a_ + 0.75 * b_
    return out


def contours_precis(base, cache=None, journal=None):
    """Tous les contours de decoupe (repere du modele prepare), aimantes sur les rainures. Cache JSON."""
    import json
    from atelier.noyau import lignes
    if cache is not None and cache.exists():
        d = json.loads(cache.read_text())
        if d.get("v") == 3:
            return d["c"]
    k = (base.bounds[1][0] - base.bounds[0][0]) / 445.0
    vues = {"flanc": (1, 1), "dessus": (2, 1), "avant": (0, -1), "arriere": (0, 1)}
    cartes = {}
    for v, (ax, sg) in vues.items():
        cartes[v] = lignes.carte(base, ax, sg, 0.2)
        if journal:
            journal(f"carte {v}")
    out = {}
    grossiers = contours_lignes(base)
    for nom, pts in grossiers.items():
        vue = LIGNES_190E[nom]["vue"]
        P, u0, v0, r, a, b = cartes[vue]
        out[nom] = {"vue": vue, "pts": aimanter(np.asarray(pts), P, u0, v0, r).tolist()}
    for nom, cfg in _FACE.items():
        P, u0, v0, r, a, b = cartes[cfg["vue"]]
        pts = np.array(_face_mm(cfg["poly"], k))
        out[nom] = {"vue": cfg["vue"], "x": [cfg["x"][0] * k, cfg["x"][1] * k],
                    "pts": (pts if nom == "coffre_dos" else aimanter(pts, P, u0, v0, r, rayon=1.6)).tolist()}
    if cache is not None:
        cache.write_text(json.dumps({"v": 3, "c": out}))
    return out


ORDRE_PRECIS = ["retro_g", "retro_d", "calandre", "phare_g", "phare_d", "plaque_av", "feu_g", "feu_d", "capot", "coffre",
                "pare_choc_av", "pare_choc_ar", "aile_avg", "aile_avd", "porte_avg", "porte_avd", "porte_arg", "porte_ard"]
PETITES = {"retro_g", "retro_d", "calandre", "phare_g", "phare_d", "plaque_av", "feu_g", "feu_d"}


def _prisme(cfg, bounds, jeu, profondeur, cote=1, miroir=False):
    from shapely.geometry import Polygon as _P
    from atelier.noyau.c3d import section
    pts = np.array(cfg["pts"], float)
    if miroir:
        pts = pts.copy()
    poly = _P(pts).buffer(0)
    if jeu:
        poly = poly.buffer(jeu, join_style=2)
    poly = poly.simplify(0.03)
    (x0, y0, z0), (x1, y1, z1) = bounds
    vue = cfg["vue"]
    if vue == "dessus":
        return mf.Manifold.extrude(section(poly), z1 - z0 + 40).translate((0, 0, z0 + 0.42 * (z1 - z0)))
    if vue in ("avant", "arriere"):                       # polygone (y, z) extrude le long de X
        xa, xb = cfg["x"]
        pr = mf.Manifold.extrude(section(poly), xb - xa)
        return pr.transform(np.array([[0, 0, 1, xa], [1, 0, 0, 0], [0, 1, 0, 0]], float))
    if cfg.get("toute_largeur"):
        ya, yb = y0 - 20, y1 + 20
    elif cote > 0:
        ya, yb = y1 - profondeur, y1 + 20
    else:
        ya, yb = y0 - 20, y0 + profondeur
    pr = mf.Manifold.extrude(section(poly), yb - ya)
    return pr.transform(np.array([[1, 0, 0, 0], [0, 0, 1, ya], [0, 1, 0, 0]], float))


def detacher_precis(coque_m, contours, choix, jeu=0.35, jeu_petites=0.2, profondeur=32.0, retouches=None, paroi=1.8):
    """Detache (dans l'ordre : petites pieces d'abord) ; chaque piece = coque restante dans son volume de decoupe.
    retouches = {piece: [[x,y,z,nx,ny,nz,r,'+'|'-'], ...]} : coups de PINCEAU qui ajoutent ('+') une zone a la piece
    (prise a la caisse ou a la voisine) ou la rendent ('-') a la caisse."""
    from atelier.noyau.retouches import volume_touches
    S = vers_manifold(coque_m)
    b = coque_m.bounds
    out = {}
    retouches = retouches or {}
    plus = {k: [t for t in v if t[7] == "+"] for k, v in retouches.items()}
    moins = {k: [t for t in v if t[7] == "-"] for k, v in retouches.items()}

    def avec_pinceau(P, nom, j):
        a = volume_touches(plus.get(nom, []), paroi, j)
        if a is not None:
            P = P + a
        for autre, t in plus.items():                       # zone donnee a une AUTRE piece : on la retire de celle-ci
            if autre != nom and t:
                P = P - volume_touches(t, paroi, -j if j else 0.0)
        r_ = volume_touches(moins.get(nom, []), paroi, -j if j else 0.0)
        if r_ is not None:
            P = P - r_
        return P
    for nom in ORDRE_PRECIS:
        if nom not in choix:
            continue
        cfgL = LIGNES_190E.get(nom, {})
        src = cfgL.get("symetrique_de", nom)
        cfg = dict(contours[src])
        cfg["toute_largeur"] = cfgL.get("toute_largeur", False)
        cote = cfgL.get("cote", 1)
        P = _prisme(cfg, b, 0.0, profondeur, cote)
        if nom == "coffre" and "coffre_dos" in contours:
            P = P + _prisme(contours["coffre_dos"], b, 0.0, profondeur)
        P = avec_pinceau(P, nom, 0.0)
        piece = S ^ P
        if piece.is_empty() or piece.volume() < 20:
            continue
        pm = vers_trimesh(piece)
        parts = sorted(pm.split(only_watertight=False), key=lambda q: -abs(q.volume))
        out[nom] = trimesh.util.concatenate([q for q in parts if abs(q.volume) > 0.05 * abs(parts[0].volume)])
        j = jeu_petites if nom in PETITES else jeu
        Pj = _prisme(cfg, b, j, profondeur, cote)
        if nom == "coffre" and "coffre_dos" in contours:
            Pj = Pj + _prisme(contours["coffre_dos"], b, j, profondeur)
        S = S - avec_pinceau(Pj, nom, j)
    return vers_trimesh(S), out


# ================================================================== MODELE PROPRE 190 E 2.3-16 : contours releves a la loupe
# Pixels des cartes 0.2 mm du modele a 445 mm (colonne, ligne depuis le HAUT de l'image). Releves sur les rainures
# reelles (zoom quadrille), puis aimantes au fond de la rainure. Voir sortie/v2_*.png.
V2_PX = {
    "flanc": {
        "porte_avg": [(713, 547), (703, 526), (696, 421), (700, 342), (718, 263), (721, 258), (808, 179), (887, 105), (945, 63),
                      (987, 42), (1100, 38), (1226, 37), (1218, 79), (1208, 158), (1200, 253), (1197, 368), (1200, 500), (1199, 547)],
        "porte_arg": [(1199, 547), (1200, 500), (1197, 368), (1200, 253), (1208, 158), (1218, 79), (1226, 37), (1487, 43), (1516, 51),
                      (1600, 140), (1687, 231), (1676, 286), (1667, 314), (1641, 337), (1596, 360), (1570, 389), (1553, 423),
                      (1540, 480), (1536, 547)],
        "aile_avg": [(170, 296), (400, 276), (600, 258), (700, 258), (718, 263), (700, 342), (696, 421), (703, 526), (713, 547),
                     (737, 590), (575, 598), (570, 580), (560, 505), (545, 440), (520, 400), (475, 370), (400, 357), (325, 365),
                     (280, 395), (250, 460), (242, 433), (175, 433), (172, 370)],
        "pare_choc_av": [(0, 433), (242, 433), (250, 460), (240, 520), (232, 560), (225, 605), (0, 605)],
        "pare_choc_ar": [(1853, 426), (2225, 426), (2225, 610), (1881, 600), (1876, 540), (1865, 470)],
    },
    "dessus": {
        "capot": [(108, 128), (350, 120), (600, 108), (640, 110), (618, 306), (612, 476), (618, 646), (640, 842), (600, 844),
                  (350, 832), (108, 824), (100, 662), (88, 652), (88, 300), (100, 290)],
        "coffre": [(1850, 112), (1890, 300), (1905, 476), (1890, 652), (1850, 840), (2172, 845), (2172, 107)],
    },
    "avant": {
        "calandre": ([(282, 300), (295, 291), (465, 291), (465, 268), (490, 268), (490, 291), (653, 291), (665, 300), (665, 432), (282, 432)], (-240, -200)),
        "phare_g": ([(76, 309), (276, 309), (276, 432), (80, 432)], (-240, -185)),
        "phare_d": ([(676, 309), (876, 309), (872, 432), (676, 432)], (-240, -185)),
        "retro_g": ([(-6, 185), (68, 185), (68, 258), (-6, 258)], (-72, -45)),      # y < -81.5 : la porte (y~79) reste intacte
        "retro_d": ([(884, 185), (958, 185), (958, 258), (884, 258)], (-72, -45)),
    },
    "arriere": {
        "feu_g": ([(47, 297), (335, 297), (335, 426), (47, 426)], (180, 240)),       # feux nervures : du coin au logement de plaque
        "feu_d": ([(617, 297), (905, 297), (905, 426), (617, 426)], (180, 240)),
        "coffre_dos": ([(112, 205), (840, 205), (840, 297), (617, 297), (617, 423), (335, 423), (335, 297), (112, 297)], (200, 240)),
    },
}
V2_CARTES = {"flanc": (-222.5, 12.684, 629), "dessus": (-222.5, -95.177, 952), "avant": (-95.177, 12.684, 629), "arriere": (-95.177, 12.684, 629)}


def contours_v2(base, cache=None):
    """Contours du modele propre (repere du modele prepare a 445 mm), aimantes sur les rainures. Cache JSON."""
    import json
    from atelier.noyau import lignes
    if cache is not None and cache.exists():
        d = json.loads(cache.read_text())
        if d.get("v") == "v2":
            return d["c"]
    k = (base.bounds[1][0] - base.bounds[0][0]) / 445.0
    ax = {"flanc": (1, 1), "dessus": (2, 1), "avant": (0, -1), "arriere": (0, 1)}
    out = {}
    for vue, pieces in V2_PX.items():
        P, u0, v0, r, a, b = lignes.carte(base, ax[vue][0], ax[vue][1], 0.2)
        U0, V0, Hh = V2_CARTES[vue]
        for nom, val in pieces.items():
            px, xr = (val, None) if isinstance(val, list) else val
            q = np.array(px, float)
            pts = np.c_[(U0 + q[:, 0] * 0.2) * k, (V0 + (Hh - 1 - q[:, 1]) * 0.2) * k]
            if nom != "coffre_dos":
                pts = aimanter(pts, P, u0, v0, r, rayon=1.2 if xr is None else 1.0, seuil=-0.02)
            d = {"vue": vue, "pts": np.asarray(pts).tolist()}
            if xr is not None:
                d["x"] = [xr[0] * k, xr[1] * k]
            out[nom] = d
    if cache is not None:
        cache.write_text(json.dumps({"v": "v2", "c": out}))
    return out


def evider_interieur(coque_m, marge=6.0, demi=66.0, x0=-185.0, x1=175.0, res=1.0, z_bas=-1.0):
    """Carrosserie RC = PEAU seulement : retire tout ce qui est sous la peau du dessus (moins `marge`) dans la zone
    |y| < demi, x0 < x < x1 : dessous de caisse, tunnel, echappement, structures internes du modele. Garde flancs,
    bas de caisse, arches, faces avant / arriere (pare-chocs, calandre, feux)."""
    import cv2
    from shapely.geometry import Polygon as _P
    from shapely.ops import unary_union as _uu
    from atelier.noyau.c3d import section
    from atelier.noyau import lignes
    P, u0, v0, r, a, b = lignes.carte(coque_m, 2, 1, res)          # z de la peau du dessus (vue de dessus)
    ztop = np.where(np.isnan(P), -1e9, P)
    X = u0 + np.arange(P.shape[1]) * r
    Y = v0 + np.arange(P.shape[0]) * r
    zone = (np.abs(Y)[:, None] < demi) & (X[None, :] > x0) & (X[None, :] < x1)
    lim = np.where(zone, ztop - marge, -1e9)                         # on vide jusqu'a cette hauteur
    pas = 3.0
    niveaux = np.arange(z_bas, float(np.nanmax(lim[zone])) if zone.any() else 0, pas)
    blocs = []
    for z in niveaux:
        msk = (lim >= z + pas).astype(np.uint8) * 255
        cs, _ = cv2.findContours(msk, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        polys = [_P(c[:, 0, :] * r + [u0, v0]).buffer(0) for c in cs if len(c) >= 3]
        polys = [p_ for p_ in polys if p_.area > 4]
        if not polys:
            continue
        reg = _uu(polys).simplify(0.5)
        blocs.append(mf.Manifold.extrude(section(reg), pas + 0.01).translate((0, 0, z)))
    if not blocs:
        return coque_m
    vide = mf.Manifold.batch_boolean(blocs, mf.OpType.Add)
    out = vers_trimesh(vers_manifold(coque_m) - vide)
    parts = sorted(out.split(only_watertight=False), key=lambda c: -abs(c.volume))
    return trimesh.util.concatenate([c for c in parts if abs(c.volume) > 30])
