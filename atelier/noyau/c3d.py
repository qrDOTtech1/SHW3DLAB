"""CREATION 3D : moteur geometrique de l'onglet facon Tinkercad (et au-dela).

Booleens et extrusions par manifold3d (maillages TOUJOURS etanches -> toujours imprimables) ; trimesh
pour les entrees / sorties et les analyses. Toutes les dimensions en mm, plateau K2 SE 220 x 215 x 245.

Formes : boite, cylindre, sphere, cone, tube, pyramide, prisme, tore, etoile, coeur, demi-sphere, texte,
vis / ecrou (filetage helicoidal), boite a couvercle, crochet...
Image -> 3D : relief de logo, tampon (miroir), emporte-piece, lithophanie, relief photo.
Outils : grouper (solides - percages, comme Tinkercad), couper au plan + tenons d'alignement, decouper
pour tenir sur le plateau, orientation auto (moins de surplombs), reparer, simplifier, creuser (coque),
analyse (volume, poids, cout, surplombs, etancheite).
"""
from __future__ import annotations

import io
import math
import uuid
from pathlib import Path

import numpy as np
import trimesh
import manifold3d as mf
from shapely.geometry import MultiPolygon, Polygon, Point, box as sbox
from shapely import affinity
from shapely.ops import unary_union

PLATEAU = (220.0, 215.0, 245.0)
DENSITE = {"PLA": 1.24, "PLA+": 1.24, "PETG": 1.27, "ABS": 1.04, "TPU": 1.21}


# ------------------------------------------------------------------ conversions
def vers_manifold(m: trimesh.Trimesh) -> mf.Manifold:
    mesh = mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32))
    r = mf.Manifold(mesh)
    if r.status() != mf.Error.NoError or r.is_empty():
        # maillage non etanche (import) : on le repare d'abord
        m = reparer(m)
        r = mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))
    return r


def vers_trimesh(s: mf.Manifold) -> trimesh.Trimesh:
    me = s.to_mesh()
    return trimesh.Trimesh(np.asarray(me.vert_properties)[:, :3], np.asarray(me.tri_verts), process=False)


def section(poly) -> mf.CrossSection:
    """shapely (Multi)Polygon -> CrossSection (trous compris)."""
    anneaux = []
    for g in (poly.geoms if isinstance(poly, MultiPolygon) else [poly]):
        if g.is_empty:
            continue
        g = Polygon(g.exterior, g.interiors).buffer(0)
        for gg in (g.geoms if isinstance(g, MultiPolygon) else [g]):
            anneaux.append(np.asarray(gg.exterior.coords)[:-1])
            anneaux += [np.asarray(h.coords)[:-1] for h in gg.interiors]
    return mf.CrossSection(anneaux, mf.FillRule.EvenOdd)


def extruder(poly, h, z0=0.0, torsion=0.0, echelle_haut=(1.0, 1.0), divisions=0):
    s = mf.Manifold.extrude(section(poly), h, divisions, torsion, echelle_haut)
    return vers_trimesh(s.translate((0, 0, z0)))


# ------------------------------------------------------------------ formes
def _cercle(r, n=96):
    return Point(0, 0).buffer(r, n // 4)


def _poly_reg(n, r, rot=0.0):
    return Polygon([(r * math.cos(rot + 2 * math.pi * k / n), r * math.sin(rot + 2 * math.pi * k / n)) for k in range(n)])


def _etoile(n, r1, r2):
    return Polygon([((r1 if k % 2 == 0 else r2) * math.cos(math.pi / 2 + math.pi * k / n),
                     (r1 if k % 2 == 0 else r2) * math.sin(math.pi / 2 + math.pi * k / n)) for k in range(2 * n)])


def _coeur(l):
    t = np.linspace(0, 2 * math.pi, 200)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    p = Polygon(np.c_[x, y]).buffer(0)
    k = l / (p.bounds[2] - p.bounds[0])
    return affinity.scale(p, k, k, origin=(0, 0))


def filetage(d, longueur, pas, jeu=0.0, interne=False):
    """Tige filetee helicoidale (profil ~ISO 60 deg approche par un lobe excentre tordu)."""
    h = 0.54 * pas                                    # profondeur de filet
    r_maj = d / 2 + (jeu if interne else 0.0)
    r_min = r_maj - h
    rc = (r_maj + r_min) / 2
    ex = (r_maj - r_min) / 2
    cs = mf.CrossSection.circle(rc, 96).translate((ex, 0))
    tours = longueur / pas
    s = mf.Manifold.extrude(cs, longueur, int(tours * 24) + 1, 360.0 * tours)
    # chanfreins d'entree (le filet ne commence pas par une arete vive)
    if not interne:
        ch = mf.Manifold.cylinder(h * 1.2, r_min, r_maj + 0.5, 96)
        s = s ^ (ch + mf.Manifold.cylinder(longueur - 2 * h * 1.2, r_maj + 1, r_maj + 1, 96).translate((0, 0, h * 1.2))
                 + mf.Manifold.cylinder(h * 1.2, r_maj + 0.5, r_min, 96).translate((0, 0, longueur - h * 1.2)))
    return s


def forme(type_: str, p: dict) -> trimesh.Trimesh:
    g = lambda k, d: float(p.get(k, d))
    if type_ == "boite":
        lx, ly, lz, r = g("x", 20), g("y", 20), g("z", 20), g("arrondi", 0)
        base = sbox(-lx / 2, -ly / 2, lx / 2, ly / 2)
        if r > 0:
            r = min(r, lx / 2 - 0.01, ly / 2 - 0.01)
            base = base.buffer(-r, join_style=1).buffer(r, join_style=1)
        return extruder(base, lz)
    if type_ == "cylindre":
        return extruder(_cercle(g("d", 20) / 2, int(g("cotes", 96))), g("z", 20))
    if type_ == "prisme":
        return extruder(_poly_reg(int(g("cotes", 6)), g("d", 20) / 2), g("z", 20))
    if type_ == "tube":
        return extruder(_cercle(g("d", 20) / 2).difference(_cercle(g("d", 20) / 2 - g("paroi", 2))), g("z", 20))
    if type_ == "cone":
        r1, r2 = g("d", 20) / 2, g("d_haut", 0) / 2
        return vers_trimesh(mf.Manifold.cylinder(g("z", 20), r1, r2, 96))
    if type_ == "pyramide":
        c = g("x", 20)
        return extruder(_poly_reg(int(g("cotes", 4)), c / math.sqrt(2), math.pi / 4), g("z", 20), echelle_haut=(0.0, 0.0))
    if type_ == "sphere":
        return vers_trimesh(mf.Manifold.sphere(g("d", 20) / 2, 96).translate((0, 0, g("d", 20) / 2)))
    if type_ == "demi_sphere":
        r = g("d", 20) / 2
        return vers_trimesh(mf.Manifold.sphere(r, 96) ^ mf.Manifold.cube((2 * r + 2, 2 * r + 2, r + 1)).translate((-r - 1, -r - 1, 0)))
    if type_ == "tore":
        R, r = g("d", 30) / 2 - g("e", 6) / 2, g("e", 6) / 2
        cs = mf.CrossSection.circle(r, 48).translate((R, 0))
        return vers_trimesh(mf.Manifold.revolve(cs, 96).translate((0, 0, r)))
    if type_ == "etoile":
        return extruder(_etoile(int(g("branches", 5)), g("d", 30) / 2, g("d", 30) / 2 * g("creux", 0.45)), g("z", 5))
    if type_ == "coeur":
        return extruder(_coeur(g("x", 30)), g("z", 5))
    if type_ == "texte":
        from atelier.produits.porte_cles import Style, prenom_polygone
        poly, _ = prenom_polygone(str(p.get("texte", "Texte")), Style(police=p.get("police", "arial_black"), hauteur=g("h", 15)))
        b = poly.bounds
        poly = affinity.translate(poly, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
        return extruder(poly, g("z", 3))
    if type_ == "vis":
        d, L, pas, tete = g("d", 8), g("z", 20), g("pas", 1.25), g("tete", 13)
        tige = filetage(d, L, pas).translate((0, 0, 5))
        t = mf.Manifold.extrude(section(_poly_reg(6, tete / math.sqrt(3))), 5)
        return vers_trimesh(t + tige)
    if type_ == "ecrou":
        d, pas, cle, e = g("d", 8), g("pas", 1.25), g("tete", 13), g("z", 6.5)
        corps = mf.Manifold.extrude(section(_poly_reg(6, cle / math.sqrt(3))), e)
        trou = filetage(d, e + 2, pas, jeu=g("jeu", 0.25), interne=True).translate((0, 0, -1))
        return vers_trimesh(corps - trou)
    if type_ == "boite_couvercle":
        # boite + couvercle emboitant (levre), cote a cote
        lx, ly, lz, ep, jeu = g("x", 60), g("y", 40), g("z", 30), g("paroi", 2), g("jeu", 0.2)
        r = min(g("arrondi", 4), lx / 2 - ep - 1, ly / 2 - ep - 1)
        ext = sbox(-lx / 2, -ly / 2, lx / 2, ly / 2).buffer(-r, join_style=1).buffer(r, join_style=1)
        intr = ext.buffer(-ep, join_style=1)
        b = vers_manifold(extruder(ext, lz)) - vers_manifold(extruder(intr, lz + 1, ep))
        levre = intr.buffer(-jeu, join_style=1).difference(intr.buffer(-jeu - 1.2, join_style=1))
        c = vers_manifold(extruder(ext, ep)) + vers_manifold(extruder(levre, 4, ep - 0.01))
        c = c.translate((0, ly + 8, 0))
        return vers_trimesh(b + c)
    if type_ == "anneau_cle":
        return extruder(_cercle(g("d", 12) / 2).difference(_cercle(g("d", 12) / 2 - g("paroi", 3))), g("z", 4))
    raise ValueError(f"forme inconnue : {type_}")


# ------------------------------------------------------------------ image -> 3D
def image_3d(data: bytes, mode: str, p: dict) -> trimesh.Trimesh:
    g = lambda k, d: float(p.get(k, d))
    if mode in ("lithophanie", "relief_photo"):
        return _hauteurs(data, g("largeur", 80), g("e_min", 0.8), g("e_max", 3.2), inverse=(mode == "lithophanie"),
                         cadre=g("cadre", 3))
    from atelier.noyau.image2d import image_vers_polygone
    seuil = p.get("seuil")
    poly, info = image_vers_polygone(data, g("largeur", 50), int(seuil) if seuil else None, p.get("inverser"),
                                     detail_min_mm=g("detail", 0.5))
    if mode == "relief":                       # logo en relief sur un socle (forme du socle au choix)
        socle = p.get("socle", "contour")
        e, h = g("e_socle", 2), g("h_relief", 1.5)
        if socle == "aucun":
            return extruder(poly, h)
        if socle == "rond":
            b = poly.bounds
            sp = _cercle(max(math.hypot(x, y) for gg in (poly.geoms if isinstance(poly, MultiPolygon) else [poly])
                             for x, y in gg.exterior.coords) + g("marge", 3))
        elif socle == "rectangle":
            b = poly.bounds
            m_ = g("marge", 3)
            sp = sbox(b[0] - m_, b[1] - m_, b[2] + m_, b[3] + m_).buffer(-2, join_style=1).buffer(2, join_style=1)
        else:
            sp = unary_union([Polygon(gg.exterior) for gg in (poly.buffer(g("marge", 3), join_style=1).geoms
                              if isinstance(poly.buffer(g("marge", 3)), MultiPolygon) else [poly.buffer(g("marge", 3), join_style=1)])])
        return vers_trimesh(vers_manifold(extruder(sp, e)) + vers_manifold(extruder(poly, h, e - 0.01)))
    if mode == "tampon":                       # miroir + poignee
        pm = affinity.scale(poly, -1, 1, origin=(0, 0))
        e, h = g("e_socle", 4), g("h_relief", 2)
        b = pm.bounds
        sp = sbox(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2)
        poignee = vers_manifold(extruder(_cercle(min(b[2] - b[0], b[3] - b[1]) / 4), 25, e + h - 0.01))
        return vers_trimesh(vers_manifold(extruder(pm, h)) + vers_manifold(extruder(sp, e, h - 0.01)) + poignee)
    if mode == "emporte_piece":                # paroi fine biseautee + collerette
        exter = unary_union([Polygon(gg.exterior) for gg in (poly.geoms if isinstance(poly, MultiPolygon) else [poly])])
        paroi = exter.buffer(g("paroi", 0.9), join_style=1).difference(exter)
        coll = exter.buffer(g("collerette", 5), join_style=1).difference(exter)
        H = g("hauteur", 14)
        s = vers_manifold(extruder(paroi, H)) + vers_manifold(extruder(coll, 1.6))
        if p.get("marqueur", True):            # les traits interieurs du dessin marquent la pate (moins hauts)
            traits = poly.boundary.buffer(0.5).intersection(exter.buffer(-1.5))
            if not traits.is_empty and traits.area > 2:
                s = s + vers_manifold(extruder(traits, H - 3))
        return vers_trimesh(s)
    raise ValueError(f"mode image inconnu : {mode}")


def _hauteurs(data, largeur, e_min, e_max, inverse=True, cadre=3.0, px_mm=0.25):
    """Lithophanie : sombre = epais (la lumiere passe moins). Relief photo : clair = haut."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    w_px = int(largeur / px_mm)
    h_px = int(im.height * w_px / im.width)
    if h_px * px_mm > 200:
        h_px = int(200 / px_mm)
        w_px = int(im.width * h_px / im.height)
    a = np.asarray(im.resize((w_px, h_px), Image.LANCZOS), np.float32) / 255.0
    z = e_min + (1 - a if inverse else a) * (e_max - e_min)
    if cadre > 0:
        c = int(cadre / px_mm)
        z = np.pad(z, c, constant_values=e_max)
    z = z[::-1]                                       # ligne 0 de l'image = haut (Y max)
    ny, nx = z.shape
    xs, ys = np.meshgrid(np.arange(nx) * px_mm, np.arange(ny) * px_mm)
    top = np.c_[xs.ravel(), ys.ravel(), z.ravel()]
    bot = np.c_[xs.ravel(), ys.ravel(), np.zeros(nx * ny)]
    V = np.vstack([top, bot])
    idx = np.arange(nx * ny).reshape(ny, nx)
    a_, b_, c_, d_ = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    F = [np.c_[a_, b_, c_], np.c_[a_, c_, d_]]                       # dessus
    o = nx * ny
    F += [np.c_[a_ + o, c_ + o, b_ + o], np.c_[a_ + o, d_ + o, c_ + o]]  # dessous
    for bord in (idx[0, :], idx[:, -1], idx[-1, ::-1], idx[::-1, 0]):  # parois (tour dans le sens direct)
        u, v = bord[:-1], bord[1:]
        F += [np.c_[u, u + o, v], np.c_[v, u + o, v + o]]
    m = trimesh.Trimesh(V, np.vstack(F), process=True)
    m.fix_normals()
    return m


# ------------------------------------------------------------------ outils
def transformer(m: trimesh.Trimesh, matrice) -> trimesh.Trimesh:
    m = m.copy()
    if matrice is not None:
        T = np.asarray(matrice, float).reshape(4, 4).T                   # three.js : colonne-majeur
        m.apply_transform(T)                                             # (miroir : trimesh retourne les faces)
    return m


def grouper(objets):
    """[(maillage, trou)] -> solides unis MOINS les percages (semantique Tinkercad)."""
    sol = [vers_manifold(m) for m, t in objets if not t]
    tro = [vers_manifold(m) for m, t in objets if t]
    if not sol:
        raise ValueError("il faut au moins un SOLIDE dans le groupe")
    s = mf.Manifold.batch_boolean(sol, mf.OpType.Add) if len(sol) > 1 else sol[0]
    if tro:
        s = s - (mf.Manifold.batch_boolean(tro, mf.OpType.Add) if len(tro) > 1 else tro[0])
    if s.is_empty():
        raise ValueError("le resultat est vide (les percages ont tout enleve)")
    return vers_trimesh(s)


def intersection(objets):
    ms = [vers_manifold(m) for m in objets]
    s = mf.Manifold.batch_boolean(ms, mf.OpType.Intersect)
    if s.is_empty():
        raise ValueError("intersection vide")
    return vers_trimesh(s)


def couper(m: trimesh.Trimesh, normale=(0, 0, 1), point=None, tenons=True, d_tenon=4.0, l_tenon=10.0, jeu=0.15,
           connecteur=None):
    """Coupe au plan + connecteurs : "tenons" (chevilles a imprimer), "queue_aronde" (les 2 moities glissent
    l'une dans l'autre), "clips" (tige fendue a bourrelet : s'enclipse, sans colle), "aucun"."""
    n = np.asarray(normale, float)
    n /= np.linalg.norm(n)
    point = np.asarray(point if point is not None else m.bounds.mean(axis=0), float)
    s = vers_manifold(m)
    a, b = s.split_by_plane(tuple(n), float(n @ point))   # a : cote +n ; b : cote -n
    if a.is_empty() or b.is_empty():
        raise ValueError("le plan ne coupe pas l'objet")
    typ = connecteur or ("tenons" if tenons else "aucun")
    libres = []
    if typ != "aucun":
        # connecteurs(a=-n, b=+n) : le male part du cote +n et plonge cote -n
        bas, haut, libres = connecteurs(b, a, m, point, n, typ, d_tenon, l_tenon, jeu)
        a, b = haut, bas
    return {"morceaux": [vers_trimesh(a), vers_trimesh(b)], "chevilles": libres}


def decouper_plateau(m: trimesh.Trimesh, marge=6.0):
    """Coupe automatiquement un objet trop grand en morceaux qui tiennent sur la K2 SE (+ tenons)."""
    lim = np.array(PLATEAU) - marge
    a_faire, ok, chev = [m], [], []
    garde = 0
    while a_faire and garde < 32:
        garde += 1
        x = a_faire.pop()
        ext = x.extents
        trop = ext / lim
        if (trop <= 1).all():
            ok.append(x)
            continue
        ax = int(np.argmax(trop))
        n = np.zeros(3)
        n[ax] = 1
        r = couper(x, n, x.bounds.mean(axis=0))
        a_faire += r["morceaux"]
        chev += r["chevilles"]
    return ok, chev


def orienter(m: trimesh.Trimesh, angle_max=45.0):
    """Orientation d'impression qui minimise les surplombs (supports) puis la hauteur."""
    h = m.convex_hull
    cand = []
    for f in np.argsort(-h.area_faces)[:40]:
        nrm = h.face_normals[f]
        if any(np.allclose(nrm, c, atol=1e-3) for c, _ in cand):
            continue
        cand.append((nrm, h.area_faces[f]))
    cand += [(np.array(v, float), 0) for v in ([0, 0, -1], [0, 0, 1], [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0])]
    best = None
    cz = -math.cos(math.radians(90 - angle_max))
    for nrm, _ in cand:
        R = trimesh.geometry.align_vectors(nrm, [0, 0, -1])
        nz = (R[:3, :3] @ m.face_normals.T)[2]
        v = (R[:3, :3] @ m.vertices.T).T
        zmin = v[:, 2].min()
        fz = v[m.faces].mean(axis=1)[:, 2] - zmin
        sur = ((nz < cz) & (fz > 0.3)) * m.area_faces
        score = sur.sum() + 0.05 * (v[:, 2].max() - zmin)
        if best is None or score < best[0]:
            best = (score, R, float(sur.sum()))
    return best[1], best[2]


def reparer(m: trimesh.Trimesh):
    m = m.copy()
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(m)
    trimesh.repair.fill_holes(m)
    if not m.is_watertight:
        # dernier recours : on garde l'enveloppe des composantes non fermees
        parts = [p if p.is_watertight else p.convex_hull for p in m.split(only_watertight=False)]
        m = trimesh.util.concatenate(parts)
    return m


def simplifier(m: trimesh.Trimesh, ratio=0.5):
    s = vers_manifold(m)
    tol = float(np.linalg.norm(m.extents)) * 0.0015 / max(ratio, 0.05)
    return vers_trimesh(s.simplify(tol))


def coque(m: trimesh.Trimesh, paroi=2.0, ouverture=False):
    """Creuse l'objet a paroi CONSTANTE (decalage exact de Minkowski) : moins de matiere, moins de temps."""
    s = vers_manifold(m)
    inner = s.minkowski_difference(mf.Manifold.sphere(paroi, 12))
    if inner.is_empty() or inner.volume() < 1:
        raise ValueError("objet trop fin pour etre creuse avec cette paroi")
    s = s - inner
    if ouverture:                                     # trou d'evacuation au fond
        c = m.bounds.mean(axis=0)
        s = s - mf.Manifold.cylinder(paroi + 2, 2.5, 2.5, 32).translate((c[0], c[1], m.bounds[0][2] - 1))
    return vers_trimesh(s)


def arrondir(m: trimesh.Trimesh, r=1.5):
    """Arrondit TOUTES les aretes saillantes d'un coup (ouverture morphologique : erosion puis dilatation
    par une sphere de rayon r). Les details plus fins que 2r disparaissent."""
    s = vers_manifold(m)
    i = s.minkowski_difference(mf.Manifold.sphere(r, 12))
    if i.is_empty():
        raise ValueError(f"objet trop fin pour un arrondi de {r} mm")
    return vers_trimesh(i.minkowski_sum(mf.Manifold.sphere(r, 24)))


def epaissir(m: trimesh.Trimesh, e=1.0):
    """Gonfle l'objet de e mm dans toutes les directions (aretes arrondies)."""
    return vers_trimesh(vers_manifold(m).minkowski_sum(mf.Manifold.sphere(e, 16)))


def lisser(m: trimesh.Trimesh, angle=120.0, niveaux=2):
    """Lissage organique (subdivision lissee) : facettes -> surfaces douces."""
    s = vers_manifold(m).smooth_out(angle, 0.0).refine(2 ** niveaux)
    return vers_trimesh(s)


def analyser(m: trimesh.Trimesh, matiere="PLA", remplissage=0.15, perimetres_mm=1.2, prix_kg=20.0):
    v_cm3 = abs(m.volume) / 1000
    surf_cm2 = m.area / 100
    # approximation slicer : coque (perimetres + dessus/dessous) pleine + remplissage
    v_coque = min(v_cm3, surf_cm2 * perimetres_mm / 10)
    v_imp = v_coque + (v_cm3 - v_coque) * remplissage
    g = v_imp * DENSITE.get(matiere, 1.24)
    zmin = m.bounds[0][2]
    nz = m.face_normals[:, 2]
    fz = m.triangles_center[:, 2] - zmin
    sur = ((nz < -math.cos(math.radians(45))) & (fz > 0.3)) * m.area_faces
    ext = m.extents
    return {"dimensions_mm": [round(float(x), 2) for x in ext], "volume_cm3": round(v_cm3, 2),
            "poids_g": round(g, 1), "cout_matiere_eur": round(g / 1000 * prix_kg, 2),
            "surplombs_cm2": round(float(sur.sum()) / 100, 2),
            "surplombs_pct": round(100 * float(sur.sum()) / max(m.area, 1e-6), 1),
            "etanche": bool(m.is_watertight), "triangles": int(len(m.faces)),
            "tient_plateau": bool(ext[0] <= PLATEAU[0] - 6 and ext[1] <= PLATEAU[1] - 6 and ext[2] <= PLATEAU[2])}


def charger(data: bytes, nom: str) -> trimesh.Trimesh:
    ext = Path(nom).suffix.lower().lstrip(".") or "stl"
    m = trimesh.load(io.BytesIO(data), file_type=ext, force="mesh")
    if not isinstance(m, trimesh.Trimesh) or not len(m.faces):
        raise ValueError("fichier 3D illisible ou vide")
    return m


# ------------------------------------------------------------------ INTEGRER un objet sur la surface d'un autre
def _densifier(m: trimesh.Trimesh, taille=0.8, max_faces=400_000):
    """Maillage fin (aretes <= taille) au plus ~max_faces faces : decoupage natif de manifold3d (C++, rapide,
    triangles bien proportionnes meme sur les facettes allongees d'un cylindre ; reste etanche)."""
    taille = max(taille, math.sqrt(2.6 * float(m.area) / max_faces))
    s = vers_manifold(m)
    for _ in range(4):
        r = s.refine_to_length(taille)
        if r.num_tri() <= max_faces * 1.3:
            return vers_trimesh(r)
        taille *= 1.2 * math.sqrt(r.num_tri() / max_faces)
    return vers_trimesh(r)


def epouser(a: trimesh.Trimesh, cible: trimesh.Trimesh, point, normale, enfoncement=0.3):
    """Plaque le dessous de `a` sur la surface (meme courbe) de `cible` : chaque point de `a` est decale le long
    de la normale de la hauteur de la surface sous lui. Le motif suit un cylindre, une sphere, un galbe..."""
    n = np.asarray(normale, float)
    n /= np.linalg.norm(n)
    p0 = np.asarray(point, float)
    a = _densifier(a, max(0.5, min(float(a.extents.min()) * 2, float(np.sort(a.extents)[1]) / 40, 1.5)))
    v = a.vertices.copy()
    h = (v - p0) @ n                                   # hauteur de chaque sommet au-dessus du plan tangent
    pied = v - np.outer(h, n)                          # projection sur le plan tangent
    origines = pied + n * 200.0
    loc, idx_ray, _ = cible.ray.intersects_location(origines, np.repeat(-n[None], len(v), axis=0), multiple_hits=False)
    d = np.zeros(len(v))
    trouve = np.zeros(len(v), bool)
    d[idx_ray] = (loc - p0) @ n                        # hauteur de la surface sous ce point
    trouve[idx_ray] = True
    if not trouve.any():
        raise ValueError("la surface cible n'est pas sous l'objet")
    d[~trouve] = d[trouve].min()                       # debord : le motif ne flotte pas
    # chaque point garde sa hauteur DANS le motif (h - bas du motif), posee sur la surface sous lui
    v = pied + np.outer(d - enfoncement + (h - h.min()), n)
    return trimesh.Trimesh(v, a.faces, process=True)


def integrer(a: trimesh.Trimesh, cible: trimesh.Trimesh, mode="relief", profondeur=1.0, point=None, normale=None,
             epouse=True, jeu=0.12):
    """mode : relief (fusion), graver (creuse la cible), incruster (2 couleurs : logement dans la cible + piece
    separee avec jeu), coller (pose seulement, 2 objets). Renvoie la liste des maillages resultants."""
    n = np.asarray(normale if normale is not None else (0, 0, 1), float)
    n /= np.linalg.norm(n)
    p = np.asarray(point if point is not None else cible.bounds.mean(axis=0), float)
    plonge = mode in ("graver", "incruster")
    if epouse:
        a = epouser(a, cible, p, n, enfoncement=(profondeur if plonge else 0.3))
    elif plonge:
        a = a.copy()
        a.apply_translation(-n * profondeur)
    A, B = vers_manifold(a), vers_manifold(cible)
    if mode == "relief":
        return [vers_trimesh(B + A)]
    if mode == "coller":
        return [vers_trimesh(B), vers_trimesh(A)]
    if mode == "graver":
        return [vers_trimesh(B - A)]
    if mode == "incruster":
        piece = A ^ B                                  # la partie dans la matiere = la piece a incruster
        logement = A
        try:                                           # logement un peu plus large que la piece (jeu)
            logement = A.minkowski_sum(mf.Manifold.cube((2 * jeu, 2 * jeu, 2 * jeu), True))
        except Exception:
            pass
        return [vers_trimesh(B - logement), vers_trimesh(piece + (A - B))]
    raise ValueError(f"mode inconnu : {mode}")


# ------------------------------------------------------------------ EFFETS DE SURFACE (textures en relief)
EFFETS = {"moletage": "Moletage (diamants)", "hexagones": "Nid d'abeille", "pierre": "Pierre / ecailles",
          "vagues": "Vagues", "cannelures": "Cannelures", "picots": "Picots", "bois": "Veines de bois",
          "bruit": "Peau granuleuse"}


def _motif(nom, u, v, w, echelle):
    k = 2 * np.pi / echelle
    if nom == "moletage":
        return np.abs(np.sin(k * (u + v) / 1.414)) * np.abs(np.sin(k * (u - v) / 1.414))
    if nom == "vagues":
        return 0.5 + 0.5 * np.sin(k * u + 1.5 * np.sin(k * v * 0.5))
    if nom == "cannelures":
        return 0.5 + 0.5 * np.cos(k * u)
    if nom == "picots":
        return np.clip(np.cos(k * u) * np.cos(k * v), 0, 1) ** 3
    if nom == "hexagones":
        x, y = u / echelle, v / echelle
        q0, q1 = x * 2 / 3, -x / 3 + np.sqrt(3) / 3 * y
        q = np.stack([q0, q1, -q0 - q1], 1)
        r = np.round(q)
        dif = np.abs(r - q)
        # arrondi cubique correct
        i = dif.argmax(1)
        r[np.arange(len(r)), i] = -(r.sum(1) - r[np.arange(len(r)), i])
        d = np.abs(r - q).max(1)
        return np.clip(1 - d * 2.4, 0, 1) ** 0.5
    if nom == "pierre":
        P = np.stack([u, v, w], 1) / echelle
        cell = np.floor(P)
        best = np.full(len(P), 9.0)
        second = np.full(len(P), 9.0)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    c = cell + (dx, dy, dz)
                    h = (np.sin(c @ np.array([12.9898, 78.233, 37.719])) * 43758.5453) % 1.0
                    pt = c + np.stack([h, (h * 7.13) % 1, (h * 3.71) % 1], 1)
                    d = np.linalg.norm(P - pt, axis=1)
                    second = np.where(d < best, best, np.minimum(second, d))
                    best = np.minimum(best, d)
        return np.clip((second - best) * 3, 0, 1)
    if nom == "bruit":
        h = (np.sin(np.stack([u, v, w], 1) @ np.array([12.9898, 78.233, 37.719]) * 3.1) * 43758.5453) % 1.0
        return h
    if nom == "bois":
        return 0.5 + 0.5 * np.sin(k * (np.hypot(u, w) + 0.6 * np.sin(v / echelle)))
    raise ValueError(f"effet inconnu : {nom}")


def effet_surface(m: trimesh.Trimesh, nom="moletage", amplitude=0.6, echelle=3.0, zones="cotes"):
    """Relief de surface procedural en coordonnees triplanaires (pas de couture visible). Le dessous reste
    PLAT (adherence au plateau). zones : tout | cotes | dessus. amplitude < 0 = en creux."""
    m = _densifier(m, max(0.3, echelle / 5), max_faces=180_000)
    v, nrm = m.vertices, m.vertex_normals
    zmin = v[:, 2].min()
    dom = np.abs(nrm).argmax(1)
    u = np.where(dom == 0, v[:, 1], v[:, 0])
    w2 = np.where(dom == 2, v[:, 1], v[:, 2])
    w3 = v[np.arange(len(v)), dom]
    # objet ROND autour de Z (cylindre, vase, tasse) : projection CYLINDRIQUE sans aucune couture de motif
    cote = np.abs(nrm[:, 2]) < 0.7
    c = v[:, :2].mean(0)
    rr = np.hypot(*(v[:, :2] - c).T)
    rond = cote.sum() > 50 and rr[cote].std() / max(rr[cote].mean(), 1e-6) < 0.12
    if rond and zones != "dessus":
        R = rr[cote].mean()
        tour = 2 * np.pi * R
        n_motifs = max(1, round(tour / echelle))                  # un nombre ENTIER de motifs sur le tour
        ang = np.arctan2(v[:, 1] - c[1], v[:, 0] - c[0])
        u = np.where(cote, ang / (2 * np.pi) * n_motifs * echelle, u)
        w2 = np.where(cote, v[:, 2], w2)
        w3 = np.where(cote, rr, w3)
    f = _motif(nom, u, w2, w3, echelle)
    # masque PAR FACE puis par sommet : un sommet n'est deplace que si TOUTES ses faces sont dans la zone
    # (les aretes vives - bord du dessus, angles - restent nettes, sans pointes)
    fn = m.face_normals
    ok_f = m.triangles_center[:, 2] > zmin + 0.25
    if zones == "cotes":
        ok_f &= np.abs(fn[:, 2]) < 0.7
    elif zones == "dessus":
        ok_f &= fn[:, 2] > 0.7
    vf = m.vertex_faces
    masque = np.where(vf >= 0, ok_f[np.clip(vf, 0, None)], True).all(1) & (v[:, 2] > zmin + 0.25)
    d = f * amplitude * masque
    return trimesh.Trimesh(v + nrm * d[:, None], m.faces, process=True)


# ================================================================== DESSIN 2D -> 3D
def _lisser_pts(pts, iterations=3, ferme=True):
    """Courbe de Chaikin : une polyligne cliquee devient une courbe douce."""
    p = np.asarray(pts, float)
    for _ in range(iterations):
        q = np.roll(p, -1, axis=0) if ferme else p[1:]
        a = p if ferme else p[:-1]
        nouv = np.empty((len(a) * 2, 2))
        nouv[0::2] = 0.75 * a + 0.25 * q
        nouv[1::2] = 0.25 * a + 0.75 * q
        p = nouv if ferme else np.vstack([p[:1], nouv, p[-1:]])
    return p


def dessin_extrusion(pts, h=10.0, lisse=False, torsion=0.0, echelle_haut=1.0, epaisseur=0.0):
    """Polygone dessine -> extrusion (avec torsion / depouille). epaisseur > 0 : seulement le contour (paroi)."""
    p = _lisser_pts(pts) if lisse else np.asarray(pts, float)
    poly = Polygon(p).buffer(0)
    if poly.is_empty or poly.area < 0.5:
        raise ValueError("dessin trop petit ou croise")
    if epaisseur > 0:
        poly = poly.difference(poly.buffer(-epaisseur, join_style=1))
    c = poly.centroid
    poly = affinity.translate(poly, -c.x, -c.y)
    div = int(max(abs(torsion) / 3, 0))
    return extruder(poly, h, torsion=torsion, echelle_haut=(echelle_haut, echelle_haut), divisions=div)


def dessin_revolution(pts, angle=360.0, lisse=False, segments=128):
    """Profil dessine (x = rayon >= 0, y = hauteur) -> solide de revolution autour de l'axe Z."""
    p = _lisser_pts(pts) if lisse else np.asarray(pts, float)
    p[:, 0] = np.clip(p[:, 0], 0, None)
    poly = Polygon(p).buffer(0)
    if poly.is_empty or poly.area < 0.5:
        raise ValueError("profil trop petit ou croise")
    s = mf.Manifold.revolve(section(poly), segments, float(angle))
    m = vers_trimesh(s)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m


# ================================================================== GENERATEURS D'OBJETS
def _loft(anneaux, ferme_bas=True, ferme_haut=True):
    """Anneaux [(N,3)] de meme taille -> maillage ferme (coque laterale + couvercles en eventail)."""
    A = np.asarray(anneaux, float)
    k, n = A.shape[:2]
    V = A.reshape(-1, 3)
    F = []
    for i in range(k - 1):
        a = i * n + np.arange(n)
        b = i * n + (np.arange(n) + 1) % n
        F += [np.c_[a, b, b + n], np.c_[a, b + n, a + n]]
    V = np.vstack([V, A[0].mean(0), A[-1].mean(0)])
    cb, ch = len(V) - 2, len(V) - 1
    j = np.arange(n)
    if ferme_bas:
        F.append(np.c_[np.full(n, cb), (j + 1) % n, j])
    if ferme_haut:
        F.append(np.c_[np.full(n, ch), (k - 1) * n + j, (k - 1) * n + (j + 1) % n])
    m = trimesh.Trimesh(V, np.vstack(F), process=True)
    if m.volume < 0:
        m.invert()
    return m


def _profil_vase(p, z):
    """Rayon du vase en fonction de la hauteur. `profil` = [[t (0..1 de la hauteur), rayon], ...] (editeur a la
    souris) ; sinon 4 rayons de controle (pied, ventre, col, ouverture). Spline monotone : jamais d'ondulation parasite."""
    H = float(p.get("h", 120))
    from scipy.interpolate import PchipInterpolator
    pr = p.get("profil")
    if pr and len(pr) >= 2:
        pr = sorted(([float(t), max(3.0, float(r))] for t, r in pr), key=lambda a: a[0])
        ts, rs = [], []
        for t, r in pr:                                   # t strictement croissants
            t = min(1.0, max(0.0, t))
            if ts and t <= ts[-1] + 1e-4:
                t = ts[-1] + 1e-4
            ts.append(t); rs.append(r)
        ts = np.array(ts); ts = (ts - ts[0]) / max(ts[-1] - ts[0], 1e-6)
        return PchipInterpolator(ts * H, rs)(np.clip(z, 0, H))
    rs = [float(p.get(k, d)) for k, d in (("r_bas", 30), ("r_ventre", 45), ("r_col", 22), ("r_haut", 32))]
    zs = [0, H * float(p.get("pos_ventre", 0.35)), H * 0.8, H]
    return PchipInterpolator(zs, rs)(np.clip(z, 0, H))


def _rayon_vase(p, t, z, dr=0.0):
    """Rayon exterieur (moins dr) a l'angle t et a la hauteur z : section, torsion, ondulations."""
    H = float(p.get("h", 120))
    cotes = int(float(p.get("cotes", 0)))
    tor = np.radians(float(p.get("torsion", 0))) * z / H
    ond, ond_n = float(p.get("ondulation", 0)), int(float(p.get("ondes", 8)))
    tt = t - tor
    rr = (_profil_vase(p, z) - dr) * (1 + ond * 0.01 * np.cos(ond_n * tt))
    if cotes >= 3:
        rr = rr * np.cos(np.pi / cotes) / np.cos((tt % (2 * np.pi / cotes)) - np.pi / cotes)
    return rr


def _perso_motif(p, lw, hw):
    """Texte et/ou logo de personnalisation -> polygone 2D centre, case dans lw x hw (logo au-dessus du texte)."""
    typ = p.get("perso", "aucun")
    contenu = []
    if typ in ("texte", "texte_logo") and str(p.get("perso_texte", "")).strip():
        from atelier.produits.porte_cles import Style, prenom_polygone
        t, _ = prenom_polygone(str(p["perso_texte"]).strip()[:40], Style(police=p.get("perso_police", "bebas"), hauteur=10.0, serrage=0.0))
        contenu.append(("texte", t))
    if typ in ("logo", "texte_logo") and p.get("perso_image"):
        f = Path(__file__).resolve().parents[2] / "data" / "images" / f"{p['perso_image']}.img"
        if f.exists():
            from atelier.noyau.image2d import image_vers_polygone
            lg, _ = image_vers_polygone(f.read_bytes(), 30.0, None, bool(p.get("perso_inverser")) or None, detail_min_mm=0.4)
            contenu.insert(0, ("logo", lg))

    def caser(poly, w, h, cy):
        b = poly.bounds
        poly = affinity.translate(poly, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
        k = min(w / max(b[2] - b[0], 1e-6), h / max(b[3] - b[1], 1e-6))
        return affinity.translate(affinity.scale(poly, k, k, origin=(0, 0)), 0, cy)
    polys = []
    if len(contenu) == 2:
        polys.append(caser(contenu[0][1], lw * 0.6, hw * 0.52, hw * 0.22))
        polys.append(caser(contenu[1][1], lw, hw * 0.3, -hw * 0.3))
    elif contenu:
        polys.append(caser(contenu[0][1], lw * (0.92 if contenu[0][0] == "texte" else 0.75), hw * (0.5 if contenu[0][0] == "texte" else 0.85), 0))
    return unary_union(polys).buffer(0) if polys else None


def _forme_cadre(forme, lc, hc):
    from shapely.geometry import box as _b
    if forme == "ovale":
        return affinity.scale(Point(0, 0).buffer(1, 96), lc / 2, hc / 2)
    if forme == "pastille":
        return Point(0, 0).buffer(min(lc, hc) / 2, 96)
    if forme == "bandeau":
        rr = min(3, hc / 4)
        return _b(-lc / 2, -hc / 2, lc / 2, hc / 2).buffer(-rr, join_style=1).buffer(rr, join_style=1)
    return None


def _enrouleur(p, a0, zc, Rc, base=None):
    """Fabrique enroule(poly, y0, y1) : poly (x = arc mm, y = hauteur mm) extrude radialement de y0 a y1 mm
    au-dessus de la surface REELLE du vase (ou de `base(a, z)`) : epouse section, torsion et ondulations."""
    surf = base or (lambda a, z: _rayon_vase(p, a, z))

    def enroule(poly, y0, y1, base_haut=None):
        if poly is None or poly.is_empty:
            return None
        s = mf.Manifold.extrude(section(poly), 1.0)
        s = s.refine_to_length(3.0 if p.get("apercu") else 1.2)

        def w(P):
            P = np.asarray(P)
            a = a0 + P[:, 0] / Rc
            z = zc + P[:, 1]
            t = P[:, 2]
            r0 = surf(a, z) + y0
            r1 = (base_haut(a, z) if base_haut else surf(a, z)) + y1
            r = r0 + (r1 - r0) * t
            return np.stack([r * np.cos(a), r * np.sin(a), z], 1)
        return s.warp_batch(w)
    return enroule


def _cartouche_vase(p, paroi):
    """Personnalisation DIRECTE sur le vase : cartouche + texte / logo enroules sur la surface. Sur une forme
    irreguliere (ondulations, facettes, torsion) le cartouche devient un SOCLE LISSE qui comble les creux : le
    texte reste net et lisible quelle que soit la forme. Renvoie (a_ajouter, a_retirer) ou None."""
    if p.get("perso", "aucun") in (None, "", "aucun") or p.get("perso_support") == "plaque":
        return None
    H = float(p.get("h", 120))
    zc = H * float(p.get("perso_hauteur", 0.5))
    a0 = np.radians(float(p.get("perso_angle", 0)))
    Rc = float(_rayon_vase(p, np.array([a0]), np.array([zc]))[0])
    hc = float(p.get("perso_taille", 34))
    lc = min(float(p.get("perso_largeur", 52)), Rc * np.pi * 1.2)
    cad = _forme_cadre(p.get("perso_cadre", "ovale"), lc, hc)
    if cad is not None:
        b = cad.bounds
        lc, hc = b[2] - b[0], b[3] - b[1]
    marge = 0.78 if cad is not None else 1.0
    motif = _perso_motif(p, lc * marge, hc * marge)
    mode = p.get("perso_mode", "relief")
    prof = float(p.get("perso_relief", 0.8))
    irregulier = float(p.get("ondulation", 0)) > 0 or int(float(p.get("cotes", 0))) >= 3 or abs(float(p.get("torsion", 0))) > 0
    ajout, retrait = [], []
    if irregulier and cad is not None:
        da = (lc / 2 + 2) / Rc
        ang = np.linspace(-da, da, 25)

        def env(a, z):                                   # enveloppe lisse : rayon MAX sur la largeur du cartouche
            z = np.asarray(z)
            return np.max(np.stack([_rayon_vase(p, a0 + d, z) for d in ang]), 0) + 0.5
        enr = _enrouleur(p, a0, zc, Rc)
        ajout.append(enr(cad, -1.2, 0.0, base_haut=env))  # socle : de la paroi jusqu'a l'enveloppe lisse
        enr_s = _enrouleur(p, a0, zc, Rc, base=env)
        if motif is not None:
            if mode == "grave":
                retrait.append(enr_s(motif, -0.9, 1.0))
            else:
                ajout.append(enr_s(motif, -0.5, prof))
        if p.get("perso_filet", True):
            ajout.append(enr_s(cad.buffer(0.9).difference(cad), -1.5, 0.4))
    else:
        enr = _enrouleur(p, a0, zc, Rc)
        if paroi > 0 and mode == "grave":
            prof = min(prof, max(0.4, paroi - 0.8))
        creux = 0.6 if cad is not None else 0.0
        if cad is not None and paroi > 0:
            creux = min(creux, paroi - 0.8)
        if cad is not None:
            retrait.append(enr(cad, -creux, 3.0))
        if motif is not None:
            if mode == "grave":
                retrait.append(enr(motif, -creux - prof, 3.0))
            else:
                ajout.append(enr(motif, -creux - 1.0, -creux + prof))
        if cad is not None and p.get("perso_filet", True):
            ajout.append(enr(cad.buffer(0.9).difference(cad), -1.0, 0.5))
    A = [x for x in ajout if x is not None]
    R = [x for x in retrait if x is not None]
    return (mf.Manifold.batch_boolean(A, mf.OpType.Add) if A else None,
            mf.Manifold.batch_boolean(R, mf.OpType.Add) if R else None)


def plaque_clip(p):
    """PLAQUE AMOVIBLE qui se CLIPSE sur le bord du vase (cadeau, etiquette) : languette interieure avec bossage
    d'accroche, pont au-dessus du col, plaque exterieure qui suit EXACTEMENT la paroi (section, torsion, ondes)
    avec texte / logo. Renvoie le maillage dans le repere du vase (pose sur le col)."""
    from shapely.geometry import box as _b
    H = float(p.get("h", 120))
    paroi = float(p.get("paroi", 2.0)) or 0.9             # mode vase : 1 paroi spiralee ~0.9 mm
    j = float(p.get("plaque_jeu", 0.25))
    e = 1.8
    a0 = np.radians(float(p.get("perso_angle", 0)))
    Rc = float(_rayon_vase(p, np.array([a0]), np.array([H]))[0])
    lp = min(float(p.get("perso_largeur", 40)), Rc * np.pi * 0.9)
    hp = float(p.get("perso_taille", 26))
    pont = min(14.0, lp * 0.4)
    descente = float(p.get("plaque_descente", 4.0))
    enr = _enrouleur(p, a0, 0.0, Rc)
    forme = p.get("perso_cadre", "bandeau")
    cad = _forme_cadre(forme if forme != "aucun" else "bandeau", lp, hp)
    zc_p = H - descente - hp / 2
    cad = affinity.translate(cad, 0, zc_p)
    cou = _b(-pont / 2, zc_p, pont / 2, H + j + e)
    ext = unary_union([cad, cou]).buffer(0)
    morceaux = [enr(ext, j, j + e)]                                              # plaque exterieure
    morceaux.append(enr(_b(-pont / 2, H + j, pont / 2, H + j + e), -(paroi + j + 1.6), j + e))   # pont
    morceaux.append(enr(_b(-pont / 2, H - 9.0, pont / 2, H + j + e), -(paroi + j + 1.6), -(paroi + j)))   # languette
    morceaux.append(enr(_b(-pont / 2 + 1, H - 6.5, pont / 2 - 1, H - 5.0), -(paroi + j), -(paroi + j) + 0.35))  # clic
    b = cad.bounds
    motif = _perso_motif(p, (b[2] - b[0]) * 0.8, (b[3] - b[1]) * 0.75)
    corps = mf.Manifold.batch_boolean([x for x in morceaux if x is not None], mf.OpType.Add)
    if motif is not None:
        motif = affinity.translate(motif, 0, zc_p)
        prof = float(p.get("perso_relief", 0.8))
        if p.get("perso_mode") == "grave":
            corps = corps - enr(motif, j + e - min(prof, 1.0), j + e + 1)
        else:
            corps = corps + enr(motif, j + e - 0.3, j + e + prof)
    return vers_trimesh(corps)


def vase(p: dict) -> trimesh.Trimesh:
    """Vase / pot : profil libre (editeur souris) ou 4 rayons, section ronde ou polygonale, torsion, ondulations,
    paroi reglable (0 = plein pour le MODE VASE du slicer), fond, zone de personnalisation (texte / logo)."""
    H = float(p.get("h", 120))
    cotes = int(float(p.get("cotes", 0)))
    n = cotes * 24 if cotes >= 3 else 160
    nz = max(40, int(H / 1.2))
    zs = np.linspace(0, H, nz)
    paroi, fond = float(p.get("paroi", 2.0)), float(p.get("fond", 2.4))
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)

    def anneaux(dr=0.0, z0=0.0):
        out = []
        for z in zs:
            if z < z0:
                continue
            zz = np.full(n, z)
            rr = _rayon_vase(p, t, zz, dr)
            out.append(np.c_[rr * np.cos(t), rr * np.sin(t), zz])
        return out
    s = vers_manifold(_loft(anneaux()))
    if paroi > 0:
        a2 = anneaux(paroi, fond)
        a2.insert(0, a2[0] * np.array([1, 1, 0]) + np.array([0, 0, fond]))
        a2.append(a2[-1] + np.array([0, 0, 2.0]))         # le creux depasse en haut : vase ouvert
        s = s - vers_manifold(_loft(a2))
    c = _cartouche_vase(p, paroi)
    if c:
        aj, re = c
        if re is not None:
            s = s - re
        if aj is not None:
            s = s + aj
    if p.get("drainage"):
        s = s - mf.Manifold.cylinder(fond + 2, 4, 4, 48).translate((0, 0, -1))
    return vers_trimesh(s)


def soucoupe(d=120.0, h=12.0, paroi=2.0):
    ext = mf.Manifold.cylinder(h, d / 2 - 2, d / 2, 160)
    inn = mf.Manifold.cylinder(h, d / 2 - 2 - paroi, d / 2 - paroi, 160).translate((0, 0, paroi))
    return vers_trimesh(ext - inn)


def keycap(p: dict) -> trimesh.Trimesh:
    """Touche de clavier compatible Cherry MX : corps creux, dessus creuse (dish), croix MX avec jeu."""
    u = float(p.get("u", 1))
    L, W = 18.0 * u + 0.05 * (u - 1) * 19, 18.0
    h_av, h_ar = float(p.get("h_avant", 8.0)), float(p.get("h_arriere", 9.5))
    lt, wt = L - 6.0, W - 6.5
    e = float(p.get("paroi", 1.4))
    r = 1.5

    def rect(l, w, rr):
        return sbox(-l / 2, -w / 2, l / 2, w / 2).buffer(-rr, join_style=1).buffer(rr, join_style=1)
    h = max(h_av, h_ar)
    corps = mf.Manifold.extrude(section(rect(L, W, r)), h, 0, 0, (lt / L, wt / W))
    # dessus incline (profil OEM/Cherry : arriere plus haut)
    pente = math.atan2(h_ar - h_av, W)
    plan = mf.Manifold.cube((L * 3, W * 3, 40), True).rotate((math.degrees(-pente), 0, 0)).translate((0, 0, 20 + (h_av + h_ar) / 2))
    corps = corps - plan
    # dish cylindrique (creux du dessus)
    dish = float(p.get("dish", 0.8))
    if dish > 0:
        Rd = (wt ** 2 / 4 + dish ** 2) / (2 * dish)
        cyl = mf.Manifold.cylinder(L * 3, Rd, Rd, 160, True).rotate((0, 90, 0)).translate((0, 0, (h_av + h_ar) / 2 + Rd - dish))
        corps = corps - cyl.rotate((math.degrees(-pente), 0, 0))
    inn = mf.Manifold.extrude(section(rect(L - 2 * e, W - 2 * e, 0.5)), h - e - 1.2, 0, 0, ((lt - 2 * e) / (L - 2 * e), (wt - 2 * e) / (W - 2 * e)))
    corps = corps - inn.translate((0, 0, -0.01))
    # tige MX : cylindre d5.5 + croix 4.1 x 1.25 (+ jeu)
    j = float(p.get("jeu", 0.05))
    tige = mf.Manifold.cylinder(h - e - 1.0, 2.75, 2.75, 48)
    croix = (mf.Manifold.cube((4.1 + 2 * j, 1.25 + 2 * j, 10)).translate((-(4.1 + 2 * j) / 2, -(1.25 + 2 * j) / 2, -1))
             + mf.Manifold.cube((1.25 + 2 * j, 4.1 + 2 * j, 10)).translate((-(1.25 + 2 * j) / 2, -(4.1 + 2 * j) / 2, -1)))
    xs = [0.0] if u < 2 else [0.0, -11.94, 11.94] if u < 6 else [0.0, -50.0, 50.0]
    for x in xs:
        t = (tige - croix.translate((0, 0, 0))) if x == 0 else mf.Manifold.cylinder(h - e - 1.0, 2.0, 2.0, 32)
        corps = corps + t.translate((x, 0, 0.6))
    m = vers_trimesh(corps)
    # impression : tete en bas = dish propre ; on laisse a l'endroit pour l'apercu (Orienter auto la retourne)
    return m


def bouton_couture(d=20.0, e=3.0, trous=4, d_trou=2.0, rebord=1.0):
    disque = mf.Manifold.cylinder(e, d / 2, d / 2, 96)
    creux = mf.Manifold.cylinder(e, d / 2 - rebord - 0.6, d / 2 - rebord - 0.6, 96).translate((0, 0, e - 0.8))
    s = disque - creux
    ecart = d * 0.14 if trous == 2 else d * 0.12
    pos = [(-ecart, 0), (ecart, 0)] if trous == 2 else [(-ecart, -ecart), (ecart, -ecart), (-ecart, ecart), (ecart, ecart)]
    for x, y in pos:
        s = s - mf.Manifold.cylinder(e + 2, d_trou / 2, d_trou / 2, 32).translate((x, y, -1))
    return vers_trimesh(s)


def support_telephone(largeur=70.0, angle=65.0, epaisseur=4.0, levre=10.0, appareil=12.0):
    """Support de telephone / tablette : profil en Z extrude, angle reglable, levre anti-glisse, passe-cable."""
    a = math.radians(angle)
    dos_l = 90.0
    pied = dos_l * math.cos(a) + 20
    pts = [(0, 0), (pied, 0), (pied, epaisseur), (epaisseur * 1.5, epaisseur)]
    # dossier incline
    bx, by = epaisseur * 1.5 + appareil, epaisseur
    p_dos = [(bx, by), (bx + dos_l * math.cos(a), by + dos_l * math.sin(a))]
    prof = unary_union([
        Polygon(pts),
        sbox(0, 0, epaisseur, levre + epaisseur),                                   # levre avant
        Polygon([(0, 0), (bx + epaisseur, 0), (bx + epaisseur, epaisseur), (0, epaisseur)]),
        LineString_buffer(p_dos, epaisseur / 2),
        LineString_buffer([(p_dos[1][0], p_dos[1][1]), (pied, epaisseur)], epaisseur / 2),   # jambe arriere
    ]).buffer(1.0, join_style=1).buffer(-1.0, join_style=1)
    s = vers_manifold(extruder(prof, largeur)).rotate((90, 0, 0)).translate((0, largeur / 2, 0))
    # passe-cable
    s = s - mf.Manifold.cube((30, 14, 30)).translate((-5, -7, -1))
    m = vers_trimesh(s)
    m.apply_translation([-m.bounds.mean(0)[0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
    return m


def LineString_buffer(pts, r):
    from shapely.geometry import LineString
    return LineString(pts).buffer(r, cap_style=1)


def _masque_mm(msk, mm_px, detail):
    """Masque binaire -> polygones en mm, a l'ECHELLE FIXE de l'image (centre image = origine)."""
    import cv2
    h, w = msk.shape
    r = max(1, int(round(detail / mm_px / 2)))
    u8 = cv2.morphologyEx((msk * 255).astype(np.uint8), cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    cs, hier = cv2.findContours(u8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return None
    hier = hier[0]
    polys = []
    for i, c in enumerate(cs):
        if hier[i][3] != -1 or len(c) < 3:
            continue
        trous, k = [], hier[i][2]
        while k != -1:
            if len(cs[k]) >= 3:
                trous.append(cs[k][:, 0, :].astype(float))
            k = hier[k][0]
        p = Polygon(c[:, 0, :].astype(float), trous).buffer(0)
        if p.area > 2:
            polys.append(p)
    if not polys:
        return None
    u = unary_union(polys)
    u = affinity.translate(u, -w / 2, -h / 2)
    u = affinity.scale(u, mm_px, -mm_px, origin=(0, 0))
    return u.simplify(mm_px * 0.6).buffer(0)


def shadowbox(data: bytes, couches=5, largeur=100.0, e_couche=1.2, cadre=6.0, detail=0.8, inverser=False):
    """Shadowbox / tableau en couches : l'image est decoupee en N niveaux ; chaque couche est une plaque
    ajouree (la plus sombre au fond), empilees avec un cadre. -> liste de maillages (1 par couche + cadre),
    a imprimer chacun dans sa couleur."""
    from PIL import Image, ImageOps
    from atelier.noyau.image2d import polygones
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    k = 600 / max(im.size)
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    g = np.asarray(im, np.float32) / 255.0
    if inverser:
        g = 1 - g
    h_mm = largeur * g.shape[0] / g.shape[1]
    # seuils par quantiles : chaque couche a autant de "matiere" visible
    qs = np.quantile(g, np.linspace(0, 1, couches + 1)[1:-1])
    rect = sbox(-largeur / 2, -h_mm / 2, largeur / 2, h_mm / 2)
    out = []
    for i in range(couches):
        if i == 0:
            poly = rect                                            # fond plein
        else:
            msk = g <= qs[i - 1]                                  # ce qui reste sombre a ce niveau = matiere
            poly = _masque_mm(msk, largeur / g.shape[1], detail)
            if poly is None:
                continue
            poly = poly.intersection(rect)
            # chaque couche reste attachee au cadre (sinon les ilots tombent)
            poly = unary_union([poly, rect.difference(rect.buffer(-1.0))])
        out.append(extruder(poly, e_couche, i * e_couche))
    # cadre
    ht = couches * e_couche + 3
    cad = rect.buffer(cadre, join_style=2).difference(rect.buffer(0.15, join_style=2))
    out.append(vers_trimesh(vers_manifold(extruder(cad, ht)) + vers_manifold(extruder(rect.buffer(cadre, join_style=2), 1.0)).translate((0, 0, -1.0))))
    return out


GENERATEURS = {"vase": "Vase", "pot": "Pot + soucoupe", "keycap": "Touche de clavier (MX)", "bouton": "Bouton de couture",
               "support_tel": "Support telephone"}


def generer(nom: str, p: dict):
    g = lambda k, d: float(p.get(k, d))
    if nom == "vase":
        out = [vase(p)]
        if p.get("perso_support") == "plaque" and p.get("perso", "aucun") not in (None, "", "aucun"):
            out.append(plaque_clip(p))
        return out
    if nom == "pot":
        q = {**p, "paroi": g("paroi", 2.4), "fond": g("fond", 3), "drainage": True}
        q.setdefault("r_bas", 35); q.setdefault("r_ventre", 42); q.setdefault("r_col", 46); q.setdefault("r_haut", 48)
        q.setdefault("h", 90)
        pot = vase(q)
        d = 2 * float(q["r_bas"]) + 24
        s = soucoupe(d, 12, 2)
        s.apply_translation([pot.extents[0] / 2 + d / 2 + 8, 0, 0])
        return [pot, s]
    if nom == "keycap":
        return [keycap(p)]
    if nom == "bouton":
        return [bouton_couture(g("d", 20), g("e", 3), int(g("trous", 4)), g("d_trou", 2), g("rebord", 1))]
    if nom == "support_tel":
        return [support_telephone(g("largeur", 70), g("angle", 65), g("epaisseur", 4), g("levre", 10), g("appareil", 12))]
    raise ValueError(f"generateur inconnu : {nom}")


# ================================================================== CONNECTEURS de coupe : queue d'aronde, clips
def _repere_plan(n):
    n = np.asarray(n, float); n /= np.linalg.norm(n)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a); u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v, n


def _vers_repere(sol: mf.Manifold, origine, u, v, n):
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = u, v, n, origine
    return sol.transform(M[:3, :])


def connecteurs(a: mf.Manifold, b: mf.Manifold, m: trimesh.Trimesh, point, n, type_="tenons", d=4.0, L=10.0, jeu=0.15):
    """a = cote -n, b = cote +n. Ajoute les connecteurs ; renvoie (a, b, pieces_libres)."""
    u, v, n = _repere_plan(n)
    sec = m.section(plane_origin=point, plane_normal=n)
    if sec is None:
        return a, b, []
    p2, T = sec.to_2D()
    polys = sorted(p2.polygons_full, key=lambda q: -q.area)
    libres = []
    # passage du repere 2D de la section au repere (u, v) du plan
    def vers3d(x, y):
        return (T @ np.array([x, y, 0, 1]))[:3]
    for poly in polys[:3]:
        if type_ == "queue_aronde":
            # queue d'aronde : glisse dans le plan selon le grand axe de la section, s'evase en profondeur
            rr = poly.minimum_rotated_rectangle
            c = np.asarray(rr.exterior.coords)[:4]
            e1, e2 = c[1] - c[0], c[2] - c[1]
            ax2 = e1 if np.linalg.norm(e1) > np.linalg.norm(e2) else e2
            l_ax = np.linalg.norm(ax2); ax2 = ax2 / l_ax
            larg = min(np.linalg.norm(e1), np.linalg.norm(e2))
            w0 = min(d * 2.0, larg * 0.45)                         # largeur au plan de coupe
            w1 = w0 * 1.45                                          # largeur au fond (evasement 1:4.5)
            prof = min(L * 0.6, 8.0)
            cen = np.asarray(poly.centroid.coords[0])
            o3 = vers3d(*cen)
            s_dir = vers3d(*(cen + ax2)) - o3; s_dir /= np.linalg.norm(s_dir)
            t_dir = np.cross(n, s_dir)
            def trapeze(gonfle):
                cs = mf.CrossSection([np.array([[-(w0 / 2 + gonfle), 0.05], [-(w1 / 2 + gonfle), -prof - gonfle],
                                                [w1 / 2 + gonfle, -prof - gonfle], [w0 / 2 + gonfle, 0.05]])], mf.FillRule.EvenOdd)
                s = mf.Manifold.extrude(cs, l_ax * 2 + 20).translate((0, 0, -(l_ax + 10)))
                M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = t_dir, n, s_dir, o3
                return s.transform(M[:3, :])
            zone = vers_manifold(extruder(poly, 200, -100))              # limite a la section (repere 2D)
            Mz = np.eye(4); Mz[:3, :] = T[:3, :]
            zone = zone.transform(Mz[:3, :])
            male = trapeze(0) ^ zone
            femelle = trapeze(jeu) ^ zone
            b = b + male            # le male part de b et plonge dans a
            a = a - femelle
        elif type_ == "clips":
            zone = poly.buffer(-(d / 2 + 2.5))
            if zone.is_empty:
                continue
            q = np.asarray(zone.representative_point().coords[0])
            o3 = vers3d(*q)
            uu, vv, nn = _repere_plan(n)
            # tige fendue avec bourrelet, sur b, plongeant dans a ; trou + gorge dans a
            tige = mf.Manifold.cylinder(L, d / 2, d / 2, 48)
            bour = mf.Manifold.cylinder(1.6, d / 2, d / 2 + 0.45, 48).translate((0, 0, L - 3.0)) + \
                   mf.Manifold.cylinder(1.4, d / 2 + 0.45, d / 2 - 0.2, 48).translate((0, 0, L - 1.4))
            fente = mf.Manifold.cube((d + 2, 1.0, L * 0.7)).translate((-(d + 2) / 2, -0.5, L * 0.3 + 0.01))
            clip = (tige + bour) - fente
            trou = mf.Manifold.cylinder(L + 0.6, d / 2 + jeu, d / 2 + jeu, 48) + \
                   mf.Manifold.cylinder(2.4, d / 2 + 0.45 + jeu, d / 2 + 0.45 + jeu, 48).translate((0, 0, L - 3.2))
            # oriente le long de -n (vers a)
            M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = uu, -vv, -nn, o3
            b = b + clip.transform(M[:3, :])
            a = a - trou.transform(M[:3, :])
        else:   # tenons (chevilles separees)
            zone = poly.buffer(-(d / 2 + 2.0))
            if zone.is_empty:
                continue
            rr = zone.minimum_rotated_rectangle
            c = np.asarray(rr.exterior.coords)[:4]
            e1, e2 = c[1] - c[0], c[2] - c[1]
            ax = e1 if np.linalg.norm(e1) > np.linalg.norm(e2) else e2
            cen = np.asarray(zone.centroid.coords[0])
            cand = [cen + ax * 0.3, cen - ax * 0.3] if np.linalg.norm(ax) > 3 * d else [cen]
            pts = [q for q in cand if zone.contains(Point(q))] or [np.asarray(zone.representative_point().coords[0])]
            for q in pts:
                p3 = vers3d(*q)
                cyl = trimesh.creation.cylinder(radius=d / 2 + jeu, height=L + 1.0, sections=48)
                cyl.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], n))
                cyl.apply_translation(p3)
                c_ = vers_manifold(cyl)
                a, b = a - c_, b - c_
                libres.append(trimesh.creation.cylinder(radius=d / 2, height=L - 0.4, sections=48))
    return a, b, libres


# ================================================================== ARRONDI / CHANFREIN sur l'ARETE CLIQUEE
def _aretes_vives(m: trimesh.Trimesh, angle_min=20.0):
    ang = m.face_adjacency_angles
    k = ang > np.radians(angle_min)
    return m.face_adjacency_edges[k], m.face_adjacency[k], m.face_adjacency_convex[k]


def chaine_arete(m: trimesh.Trimesh, point, angle_min=20.0):
    """Trouve l'arete vive la plus proche du clic puis la CHAINE complete (droite ou cercle)."""
    E, F, cvx = _aretes_vives(m, angle_min)
    if not len(E):
        raise ValueError("aucune arete vive sur cet objet")
    V = m.vertices
    a, b = V[E[:, 0]], V[E[:, 1]]
    p = np.asarray(point, float)
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    d = np.linalg.norm(a + ab * t[:, None] - p, axis=1)
    i0 = int(d.argmin())
    if d[i0] > 3.0:
        raise ValueError("clique plus pres d'une arete (a moins de 3 mm)")
    n1, n2 = m.face_normals[F[i0, 0]], m.face_normals[F[i0, 1]]
    # chaine : aretes vives connexes, de meme convexite, dont l'une des faces garde la normale n1 ou n2
    from collections import defaultdict
    adj = defaultdict(list)
    for i, (x, y) in enumerate(E):
        adj[x].append(i); adj[y].append(i)
    def compatible(i):
        if cvx[i] != cvx[i0]:
            return False
        fn = m.face_normals[F[i]]
        return any(np.dot(f, n1) > 0.995 or np.dot(f, n2) > 0.995 for f in fn)
    vu, pile = {i0}, [i0]
    while pile:
        i = pile.pop()
        for s in E[i]:
            for j in adj[s]:
                if j not in vu and compatible(j):
                    # pas de virage brutal (on ne suit pas l'angle d'une boite)
                    dj, di = V[E[j, 1]] - V[E[j, 0]], V[E[i, 1]] - V[E[i, 0]]
                    c = abs(np.dot(dj, di)) / (np.linalg.norm(dj) * np.linalg.norm(di) + 1e-12)
                    if c > 0.85:
                        vu.add(j); pile.append(j)
    ids = np.array(sorted(vu))
    return {"aretes": E[ids], "faces": F[ids], "convexe": bool(cvx[i0]), "n1": n1, "n2": n2,
            "milieu": ((V[E[i0, 0]] + V[E[i0, 1]]) / 2).tolist(),
            "segments": [[V[x].tolist(), V[y].tolist()] for x, y in E[ids]]}


def _profil_coin(n1, n2, r, chanfrein, conv, x2, y2, pas=24):
    """Profil 2D (dans le repere x2, y2 perpendiculaire a l'arete, coin a l'origine) de la matiere a
    enlever (convexe) ou a ajouter (concave)."""
    a1 = np.array([np.dot(n1, x2), np.dot(n1, y2)]); a1 /= np.linalg.norm(a1)
    a2 = np.array([np.dot(n2, x2), np.dot(n2, y2)]); a2 /= np.linalg.norm(a2)
    s = 1.0 if conv else -1.0
    bis = -(a1 + a2) * s
    nb = np.linalg.norm(bis)
    if nb < 1e-6:
        raise ValueError("aretes paralleles")
    bis /= nb
    cos_half = np.clip(np.dot(-a1 * s, bis), 1e-3, 1)
    c = bis * r / cos_half                                  # centre du cercle tangent aux 2 faces
    t1, t2 = c + a1 * s * r, c + a2 * s * r                 # points de tangence
    if chanfrein:
        pts = [np.zeros(2), t1, t2]
    else:
        ang1, ang2 = np.arctan2(*(t1 - c)[::-1]), np.arctan2(*(t2 - c)[::-1])
        dA = (ang2 - ang1 + np.pi) % (2 * np.pi) - np.pi
        arc = [c + r * np.array([np.cos(ang1 + dA * k / pas), np.sin(ang1 + dA * k / pas)]) for k in range(pas + 1)]
        pts = [np.zeros(2) - (t1 + t2) * 0.02] + arc            # le coin, legerement au-dela
    poly = Polygon(pts).buffer(0)
    return poly


def arrondir_arete(m: trimesh.Trimesh, point, r=2.0, chanfrein=False):
    ch = chaine_arete(m, point)
    V = m.vertices
    segs = np.array(ch["segments"])
    n1, n2, conv = ch["n1"], ch["n2"], ch["convexe"]
    P = segs.reshape(-1, 3)
    centre = P.mean(0)
    # droite ou cercle ?
    dirs = segs[:, 1] - segs[:, 0]
    dirs /= np.linalg.norm(dirs, axis=1)[:, None]
    droite = (np.abs(dirs @ dirs[0]) > 0.999).all()
    s = vers_manifold(m)
    if droite:
        e = dirs[0]
        tt = (P - centre) @ e
        L = tt.max() - tt.min()
        o = centre + e * (tt.max() + tt.min()) / 2
        x2 = np.cross(e, n1); x2 /= np.linalg.norm(x2); y2 = np.cross(e, x2)
        prof = _profil_coin(n1, n2, r, chanfrein, conv, x2, y2)
        outil = mf.Manifold.extrude(section(prof), L + (0.02 if not conv else 2 * r + 0.5)).translate((0, 0, -(L + (0.02 if not conv else 2 * r + 0.5)) / 2))
        M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x2, y2, e, o
        outil = outil.transform(M[:3, :])
    else:
        # cercle : plan du cercle = normale constante (face plane) parmi n1 / n2
        fn = m.face_normals
        def constante(nn):           # pour CHAQUE arete, l'une des 2 faces porte cette normale (face plane du cercle)
            return np.maximum(np.abs(fn[ch["faces"][:, 0]] @ nn), np.abs(fn[ch["faces"][:, 1]] @ nn)).min() > 0.995
        if constante(n1):
            ax = n1
        elif constante(n2):
            ax = n2
        else:
            raise ValueError("arete courbe non circulaire : arrondi possible seulement sur arete droite ou cercle")
        ax = ax / np.linalg.norm(ax)
        u, v, _ = _repere_plan(ax)
        q = np.c_[(P - centre) @ u, (P - centre) @ v]
        A = np.c_[2 * q, np.ones(len(q))]
        sol = np.linalg.lstsq(A, (q ** 2).sum(1), rcond=None)[0]
        c2 = sol[:2]; R = math.sqrt(sol[2] + c2 @ c2)
        C = centre + u * c2[0] + v * c2[1]
        hgt = ((P - C) @ ax).mean()
        C = C + ax * hgt
        # point de reference sur le cercle : profil dans le demi-plan (radial, axial)
        pm = np.asarray(ch["milieu"])                       # profil pris A L'ARETE CLIQUEE (normales n1, n2)
        p0 = pm - C - ax * ((pm - C) @ ax)
        rad = p0 / np.linalg.norm(p0)
        prof = _profil_coin(n1, n2, r, chanfrein, conv, rad, ax)
        prof = affinity.translate(prof, R, 0)
        if prof.bounds[0] < 0:
            prof = prof.intersection(sbox(0, -1e3, 1e4, 1e3))
        outil = mf.Manifold.revolve(section(prof), 160)
        M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = u, v, ax, C
        # revolve : profil (x = rayon, y = axe Z local)
        outil = outil.transform(M[:3, :])
    res = s - outil if conv else s + outil
    return vers_trimesh(res), ch
