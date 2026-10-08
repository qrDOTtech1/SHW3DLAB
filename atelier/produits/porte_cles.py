"""Moteur de porte-cles prenom, style « le prenom EST le porte-cle » (tendance Etsy) :

* le prenom en relief, lettres resserrees jusqu'a se toucher -> UNE seule piece ;
* une base « contour » qui suit la silhouette du prenom (offset), avec une patte d'anneau ;
* deux modes de fabrication :
  - "2impressions" (sans CFS) : base couleur 1 avec une EMPREINTE du prenom (jeu + chanfrein d'entree),
    prenom couleur 2 imprime a part, puis emboite (+ 1 goutte de cyanoacrylate) ;
  - "changement" : une seule impression, pause / changement de filament a la hauteur indiquee.
* production en serie : N prenoms -> 1 plateau de bases + 1 plateau de prenoms.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq
import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

FONTS = Path("C:/Windows/Fonts")
LOCALES = Path(__file__).resolve().parents[2] / "polices"
# cle -> (fichier, libelle, licence, vente de prenoms personnalises autorisee ?)
POLICES_INFO = {
    "arial_black": (FONTS / "ariblk.ttf", "Arial Black", "Microsoft (Windows)", True),
    "impact": (FONTS / "impact.ttf", "Impact", "Microsoft (Windows)", True),
    "comic_gras": (FONTS / "comicbd.ttf", "Comic Sans gras", "Microsoft (Windows)", True),
    "script": (FONTS / "segoescb.ttf", "Segoe Script", "Microsoft (Windows)", True),
    "gabriola": (FONTS / "Gabriola.ttf", "Gabriola (calligraphie ancienne)", "Microsoft (Windows)", True),
    "manuscrite": (FONTS / "segoeprb.ttf", "Segoe Print", "Microsoft (Windows)", True),
    "verdana_gras": (FONTS / "verdanab.ttf", "Verdana gras", "Microsoft (Windows)", True),
    "pacifico": (LOCALES / "Pacifico-Regular.ttf", "Pacifico", "OFL (Google Fonts)", True),
    "lobster": (LOCALES / "Lobster-Regular.ttf", "Lobster", "OFL (Google Fonts)", True),
    "titan": (LOCALES / "TitanOne-Regular.ttf", "Titan One", "OFL (Google Fonts)", True),
    "luckiest": (LOCALES / "LuckiestGuy-Regular.ttf", "Luckiest Guy", "Apache 2.0 (Google Fonts)", True),
    "bangers": (LOCALES / "Bangers-Regular.ttf", "Bangers", "OFL (Google Fonts)", True),
    "righteous": (LOCALES / "Righteous-Regular.ttf", "Righteous", "OFL (Google Fonts)", True),
    "bebas": (LOCALES / "BebasNeue-Regular.ttf", "Bebas Neue", "OFL (Google Fonts)", True),
    "marker": (LOCALES / "PermanentMarker-Regular.ttf", "Permanent Marker", "Apache 2.0 (Google Fonts)", True),
    "chewy": (LOCALES / "Chewy-Regular.ttf", "Chewy", "Apache 2.0 (Google Fonts)", True),
    "bungee": (LOCALES / "Bungee-Regular.ttf", "Bungee", "OFL (Google Fonts)", True),
    "pricedown": (LOCALES / "PricedownBl.otf", "Pricedown (style GTA)",
                  "Typodermic gratuite : usage commercial statique OK, PERSONNALISATION = licence a acheter", False),
}
POLICES = {k: str(v[0]) for k, v in POLICES_INFO.items() if Path(v[0]).exists()}


@dataclass
class Style:
    police: str = "arial_black"
    hauteur: float = 16.0          # hauteur des majuscules (mm)
    serrage: float = 0.10          # resserrage des lettres (fraction de la hauteur) : > 0 = lettres qui se touchent
    contour: float = 3.2           # marge de la base autour du prenom (mm)
    e_base: float = 3.0            # epaisseur de la base (mm)
    relief: float = 2.0            # depassement du prenom au-dessus de la base (mm)
    empreinte: float = 1.2         # profondeur de l'empreinte (mode 2 impressions)
    jeu: float = 0.12              # jeu lateral prenom / empreinte (mm)
    anneau_d: float = 5.0          # trou d'anneau
    patte_d: float = 13.0          # diametre de la patte d'anneau
    majuscules: bool = False
    mode: str = "2impressions"     # "2impressions" | "changement"


# ---------------------------------------------------------------- texte -> polygones 2D
def _face_poly(face, tol=0.05):
    vs, tris = face.tessellate(tol)
    P = np.array([[v.x, v.y] for v in vs])
    return unary_union([Polygon(P[list(t)]) for t in tris if Polygon(P[list(t)]).area > 1e-9]).buffer(0)


_CMAPS = {}


def caracteres_absents(texte, police):
    """Caracteres que la police ne sait pas dessiner (emoji, alphabets non couverts...)."""
    from fontTools.ttLib import TTFont
    f = POLICES[police]
    if f not in _CMAPS:
        _CMAPS[f] = set(TTFont(f, fontNumber=0, lazy=True).getBestCmap().keys())
    return sorted({c for c in texte if not c.isspace() and ord(c) not in _CMAPS[f]})


def glyphes(texte, style: Style):
    """Polygones de chaque glyphe (accents / points rattaches a leur lettre), ordonnes gauche -> droite."""
    t = texte.upper() if style.majuscules else texte
    font = POLICES[style.police]
    w = cq.Workplane("XY").text(t, style.hauteur, 1.0, fontPath=font, halign="left", valign="bottom",
                                combine=False)
    comps = []
    for sol in w.vals():
        for f in sol.Faces():
            if abs(f.normalAt().z + 1) < 1e-3 and f.Center().z < 0.01:      # face du dessous
                comps.append(_face_poly(f))
    comps = [c for c in comps if not c.is_empty]
    comps.sort(key=lambda p: p.bounds[0])
    # regroupement : un composant dont l'etendue X recouvre largement un autre = meme glyphe (accent, point)
    groups = []
    for c in comps:
        x0, _, x1, _ = c.bounds
        placed = False
        for g in groups:
            gx0, _, gx1, _ = g.bounds
            ov = min(x1, gx1) - max(x0, gx0)
            if ov > 0.5 * min(x1 - x0, gx1 - gx0):
                groups[groups.index(g)] = unary_union([g, c])
                placed = True
                break
        if not placed:
            groups.append(c)
    groups.sort(key=lambda p: p.bounds[0])
    return groups


def prenom_polygone(texte, style: Style):
    """Plusieurs mots : chacun est une piece (soudee), separes par un vrai espace (0.32 h)."""
    mots = texte.split()
    if len(mots) > 1:
        x, polys, n = 0.0, [], 0
        for m in mots:
            u, k = _mot_polygone(m, style)
            u = affinity.translate(u, x - u.bounds[0], 0)
            polys.append(u)
            n += k
            x = u.bounds[2] + 0.32 * style.hauteur
        return unary_union(polys), n
    return _mot_polygone(texte.strip(), style)


def _mot_polygone(texte, style: Style):
    """Prenom resserre ADAPTATIF : chaque glyphe glisse vers le precedent jusqu'a former une vraie
    jonction (aire de recouvrement >= 0.02 h^2, ~5 mm2 a 16 mm) -> une seule piece solide, quelle
    que soit la police. `serrage` = recouvrement maxi autorise (fraction de la largeur du glyphe)."""
    gs = glyphes(texte, style)
    a_min = 0.006 * style.hauteur ** 2              # ~1.5 mm2 a 16 mm : tient a la manipulation, reste lisible
    placed = [gs[0]]
    shift_acc = 0.0
    def corps(p):                                                     # corps principal (sans point / accent)
        return max(p.geoms, key=lambda q: q.area) if isinstance(p, MultiPolygon) else p
    for g in gs[1:]:
        g0 = affinity.translate(g, -shift_acc, 0)
        prev = unary_union([corps(q) for q in placed])     # tout ce qui est deja place (et non le seul glyphe precedent)
        gb = corps(g0)
        last = corps(placed[-1])
        w = min(gb.bounds[2] - gb.bounds[0], last.bounds[2] - last.bounds[0])
        lo, hi = 0.0, max(gb.bounds[0] - prev.bounds[2], 0.0) + 0.6 * w + 1.0     # fenetre = vrai ecart + recouvrement
        g0_full = g0
        g0 = gb
        if g0.intersection(prev).area >= a_min:
            s_ = 0.0
        else:
            for _ in range(22):                                       # recherche dichotomique du decalage
                mid = (lo + hi) / 2
                if affinity.translate(g0, -mid, 0).intersection(prev).area >= a_min:
                    hi = mid
                else:
                    lo = mid
            s_ = hi
        shift_acc += s_
        placed.append(affinity.translate(g0_full, -s_, 0))
    u = unary_union(placed).buffer(0.05).buffer(-0.05)               # soude les contacts tangents
    # soudure de secours : s'il reste plusieurs GROS morceaux dans le mot, pont de 1.6 mm entre les
    # deux points les plus proches (generique : formes de lettres que le resserrage ne joint pas)
    from shapely.ops import nearest_points
    for _ in range(12):
        if not isinstance(u, MultiPolygon):
            break
        gros = [q for q in u.geoms if q.area >= 0.15 * style.hauteur ** 2
                and q.bounds[1] <= u.bounds[1] + 0.35 * (u.bounds[3] - u.bounds[1])]
        if len(gros) < 2:
            break
        gros.sort(key=lambda q: q.bounds[0])
        a_, b_ = gros[0], gros[1]
        pa, pb = nearest_points(a_, b_)
        from shapely.geometry import LineString
        pont = LineString([pa, pb]).buffer(0.8, cap_style=1)
        u = unary_union([u, pont]).buffer(0.05).buffer(-0.05)
    # petits details detaches (points des i, accents) : grossis jusqu'a >= 2 mm -> manipulables
    if isinstance(u, MultiPolygon):
        parts = sorted(u.geoms, key=lambda q: -q.area)
        fixes = [parts[0]]
        for q in parts[1:]:
            dmin = min(q.bounds[2] - q.bounds[0], q.bounds[3] - q.bounds[1])
            if q.area < 0.08 * style.hauteur ** 2 and dmin < 2.0:
                q = q.buffer((2.0 - dmin) / 2 + 0.05, join_style=1)
            fixes.append(q)
        u = unary_union(fixes)
    return u, len(gs)


# ---------------------------------------------------------------- base contour + patte d'anneau
def base_polygone(nom, style: Style):
    c = nom.buffer(style.contour, join_style=1)
    c = unary_union([Polygon(p.exterior) for p in (c.geoms if isinstance(c, MultiPolygon) else [c])])
    x0, y0, x1, y1 = nom.bounds
    # patte : a gauche, a mi-hauteur de la premiere lettre
    first = min((g for g in (nom.geoms if isinstance(nom, MultiPolygon) else [nom])), key=lambda p: p.bounds[0])
    yc = (first.bounds[1] + first.bounds[3]) / 2
    xc = x0 - style.contour - style.patte_d / 2 + 2.5
    patte = Point(xc, yc).buffer(style.patte_d / 2, 64)
    pont = Polygon([(xc, yc - style.patte_d * 0.35), (x0 + 2, yc - style.patte_d * 0.35),
                    (x0 + 2, yc + style.patte_d * 0.35), (xc, yc + style.patte_d * 0.35)])
    b = unary_union([c, patte, pont]).buffer(1.2, join_style=1).buffer(-1.2, join_style=1)   # congés
    trou = Point(xc, yc).buffer(style.anneau_d / 2, 64)
    return b, trou, (xc, yc)


# ---------------------------------------------------------------- 2D -> 3D
def extrude(poly, h, z0=0.0):
    polys = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    sols = []
    for p in polys:
        if p.is_empty or p.area < 0.01:
            continue
        p = p.simplify(0.01)
        w = cq.Workplane("XY").polyline(list(p.exterior.coords)[:-1]).close()
        for h_ in p.interiors:
            w = w.polyline(list(h_.coords)[:-1]).close()
        sols.append(w.extrude(h).translate((0, 0, z0)))
    r = sols[0]
    for s_ in sols[1:]:
        r = r.union(s_)
    return r


def porte_cle(texte, style: Style | None = None):
    """Renvoie {"base": solide, "prenom": solide}, rapport."""
    st = style or Style()
    absents_geo = set(caracteres_absents(texte, st.police))
    texte_geo = " ".join("".join(c for c in m if c not in absents_geo) for m in texte.split())
    texte_geo = " ".join(texte_geo.split())
    if not texte_geo:
        raise ValueError(f"aucun caractere dessinable dans {texte!r} avec la police {st.police}")
    nom, n_gl = prenom_polygone(texte_geo, st)
    base2d, trou, ring = base_polygone(nom, st)
    base = extrude(base2d.difference(trou), st.e_base)
    rep = {"texte": texte, "police": st.police, "mode": st.mode}
    if st.mode == "2impressions":
        z_emp = st.e_base - st.empreinte
        emp = extrude(nom.buffer(st.jeu, join_style=1), st.empreinte + 1.0, z_emp)
        bouche = extrude(nom.buffer(st.jeu + 0.25, join_style=1), 1.0, st.e_base - 0.3)    # chanfrein d'entree
        base = base.cut(emp).cut(bouche)
        h_nom = st.empreinte + st.relief
        pied = extrude(nom.buffer(-0.2, join_style=1), 0.3, 0.0)                          # anti « patte d'elephant »
        corps = extrude(nom, h_nom - 0.3, 0.3)
        prenom = pied.union(corps) if pied is not None else corps
        rep["assemblage"] = (f"emboiter le prenom dans l'empreinte (jeu {st.jeu} mm, profondeur {st.empreinte} mm) "
                             "+ 1 goutte de cyanoacrylate")
        rep["hauteur_prenom_mm"] = round(h_nom, 2)
    else:
        prenom = extrude(nom, st.relief, st.e_base)
        rep["changement_couleur_mm"] = st.e_base
    # ---- controles
    n_mots = max(1, len(texte_geo.split()))
    absents = sorted(absents_geo)
    parts_nom = sorted(nom.geoms, key=lambda q: -q.area) if isinstance(nom, MultiPolygon) else [nom]
    seuil_detail = 0.15 * st.hauteur ** 2                    # accents, points, apostrophes : petites pieces a part
    h_ref = nom.bounds[3] - nom.bounds[1]
    details = [q for q in parts_nom[n_mots:]
               if q.area < seuil_detail or q.bounds[1] > nom.bounds[1] + 0.35 * h_ref]
    pieces_nom = len(parts_nom) - len(details)
    min_detail = min((min(q.bounds[2] - q.bounds[0], q.bounds[3] - q.bounds[1]) for q in details), default=None)
    epais = nom.buffer(-0.4)                      # trait < 0.8 mm (2 lignes de buse 0.4) -> disparait
    perte = 1 - (epais.buffer(0.4).area / nom.area) if nom.area else 1
    anneau_mur = st.patte_d / 2 - st.anneau_d / 2
    x0, y0, x1, y1 = base2d.bounds
    rep["controles"] = {
        "dimensions_mm": [round(x1 - x0, 1), round(y1 - y0, 1), round(st.e_base + st.relief, 1)],
        "prenom_monobloc": pieces_nom == n_mots, "pieces_prenom": pieces_nom, "glyphes": n_gl,
        "details_a_placer": len(details),
        "plus_petit_detail_mm": round(min_detail, 1) if min_detail else None,
        "base_monobloc": not isinstance(base2d, MultiPolygon),
        "traits_trop_fins_pct": round(100 * perte, 1), "mur_anneau_mm": anneau_mur,
        "mots": n_mots, "caracteres_absents": absents,
        "longueur_alerte": (x1 - x0) > 110,
        "ok": (pieces_nom == n_mots and not isinstance(base2d, MultiPolygon) and perte < 0.03 and anneau_mur >= 3.0
               and (min_detail is None or min_detail >= 1.6) and not absents),
    }
    return {"base": base, "prenom": prenom}, rep


def serie(noms, style: Style | None = None, plateau=(210.0, 205.0), ecart=4.0):
    """Production : place N porte-cles sur 1 plateau de bases + 1 plateau de prenoms (rangees)."""
    st = style or Style()
    items, reps = [], []
    for n in noms:
        c, r = porte_cle(n, st)
        bb = c["base"].val().BoundingBox()
        items.append((c, bb))
        reps.append(r)
    x, y, row_h = 0.0, 0.0, 0.0
    poses = []
    for c, bb in items:
        w, h = bb.xlen, bb.ylen
        if x + w > plateau[0]:
            x, y, row_h = 0.0, y + row_h + ecart, 0.0
        poses.append((x - bb.xmin, y - bb.ymin))
        x += w + ecart
        row_h = max(row_h, h)
    hauteur_utilisee = y + row_h
    plateaux = {"bases": None, "prenoms": None}
    for (c, bb), (dx, dy) in zip(items, poses):
        for k, key in (("base", "bases"), ("prenom", "prenoms")):
            s_ = c[k].translate((dx, dy, 0))
            plateaux[key] = s_ if plateaux[key] is None else plateaux[key].union(s_)
    return plateaux, {"porte_cles": reps, "plateau_mm": plateau, "occupation_y_mm": round(hauteur_utilisee, 1),
                      "tient": hauteur_utilisee <= plateau[1]}
