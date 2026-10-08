"""Porte-cle PRENOM avec distributeur de jeton integre (version "deco" du porte-jeton).

Silhouette organique d'un seul tenant : patte d'anneau -> prenom (incruste, couleur 2) -> col qui loge le
poussoir -> MEDAILLON rond qui contient le jeton. Le jeton sort par le bout du medaillon quand on pousse le
bouton du dessus ; meme mecanique validee que le porte-jeton classique (clipsage a 2 niveaux, cran de repos,
course bornee par la lumiere). Bord superieur adouci (arrondi en 3 marches de 0.3 mm), pas de ponçage.
"""
from __future__ import annotations

import math

import cadquery as cq
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon, box as sbox
from shapely.ops import unary_union

from atelier.produits.porte_cles import Style, prenom_polygone, extrude
from atelier.produits.porte_jeton import Jeton, Params, _box, _cyl


def _plein(p):
    return unary_union([Polygon(g.exterior) for g in (p.geoms if isinstance(p, MultiPolygon) else [p])])


def porte_cle_jeton(texte="Steven", police="pacifico", jeton: Jeton | None = None, p: Params | None = None,
                    h_txt: float = 13.0, contour: float = 3.0):
    j = jeton or Jeton()
    p = p or Params()
    D = j.d + p.jeu_d
    R = D / 2
    H = j.e + p.jeu_e
    z0, z1 = p.plancher, p.plancher + H
    E = z1 + p.toit
    Rm = R + p.paroi                                   # rayon du medaillon
    x_bec = R
    x_dos = -R - p.course - p.coul_l - 1.0             # fond du canal du poussoir
    W_col = p.coul_w + 2 * p.jeu_coul + 2 * p.paroi    # largeur du col
    # ------------------------------------------------------------------ prenom
    nom, n_gl = prenom_polygone(texte.strip(), Style(police=police, hauteur=h_txt))
    bx0, by0, bx1, by1 = nom.bounds
    # le prenom finit juste avant le col (marge = contour) ; centre vertical sur l'axe du jeton
    x_fin = x_dos - p.paroi - 1.0
    nom = affinity.translate(nom, x_fin - bx1, -(by0 + by1) / 2)
    bx0, by0, bx1, by1 = nom.bounds
    sil = _plein(nom.buffer(contour, join_style=1))
    # ------------------------------------------------------------------ silhouette d'un seul tenant
    medaillon = Point(0, 0).buffer(Rm, 128)
    # bec : les parois du medaillon se prolongent jusqu'a l'embouchure (elles portent les bosses de clipsage)
    bec = sbox(0, -Rm, x_bec + 1.2, Rm).buffer(-2.0, join_style=1).buffer(2.0, join_style=1)
    col = sbox(min(bx1 - 2, x_dos - p.paroi), -W_col / 2, 0, W_col / 2)
    # patte d'anneau a gauche du prenom
    first = min((g for g in (nom.geoms if isinstance(nom, MultiPolygon) else [nom])), key=lambda q: q.bounds[0])
    ya = (first.bounds[1] + first.bounds[3]) / 2
    xa = bx0 - contour - p.patte_d / 2 + 2.5
    patte = unary_union([Point(xa, ya).buffer(p.patte_d / 2, 64),
                         sbox(xa, ya - p.patte_d * 0.35, bx0 + 2, ya + p.patte_d * 0.35)])
    plan = unary_union([sil, col, medaillon, bec, patte])
    plan = plan.buffer(4.0, join_style=1).buffer(-4.0, join_style=1)       # raccords organiques (congés 4 mm)
    plan = _plein(plan)
    # ------------------------------------------------------------------ volume : bord sup arrondi en marches
    marches = [(0.0, 0.0), (E - 0.9, 0.0), (E - 0.6, 0.15), (E - 0.3, 0.45)]
    corps = None
    for k, (za, retrait) in enumerate(marches):
        zb = marches[k + 1][0] if k + 1 < len(marches) else E
        if k == 0:
            couche = extrude(plan.buffer(-0.25, join_style=1), 0.3, 0.0).union(extrude(plan, zb - 0.3, 0.3))
        else:
            couche = extrude(plan.buffer(-retrait, join_style=1), zb - za, za)
        corps = couche if corps is None else corps.union(couche)
    corps = corps.cut(_cyl(p.anneau_d, E + 2, xa, ya, -1))
    # ------------------------------------------------------------------ mecanique (identique au porte-jeton)
    cav = _cyl(D, H, 0, 0, z0).union(_box(0, x_bec + p.paroi + 2, -R, R, z0, z1))
    canal = _box(x_dos, 0, -(p.coul_w / 2 + p.jeu_coul), p.coul_w / 2 + p.jeu_coul, z0, z1)
    corps = corps.cut(cav).cut(canal)
    Rt = j.d / 2

    def x_contact(i):
        return math.sqrt(max(Rt ** 2 - (Rt - i) ** 2, 0.0))
    crans = [(p.cran, x_contact(p.cran) + 0.2), (p.bosse, p.course - 0.3 + x_contact(p.bosse))]
    for inter, xb in crans:
        tip = Rt - inter
        for s_ in (-1, 1):
            b_ = _cyl(2.4, H, xb, s_ * (tip + 1.2), z0)
            corps = corps.union(b_.intersect(_box(xb - 2, xb + 2, -R - p.paroi, R + p.paroi, z0, z1)))
    corps = corps.cut(_cyl(D - 6.0, p.toit + 1, 0, 0, z1 - 0.5))           # fenetre : on voit le jeton
    x_c0 = -R - p.coul_l / 2
    lum = (cq.Workplane("XY").center(x_c0 + p.course / 2, 0).slot2D(p.course + p.bouton_d + 0.6, p.bouton_d + 0.6)
           .extrude(p.toit + 1).translate((0, 0, z1 - 0.5)))
    corps = corps.cut(lum)
    xc_av = -R
    coul = _box(xc_av - p.coul_l, xc_av, -p.coul_w / 2, p.coul_w / 2, 0, H - 2 * 0.15)
    coul = coul.cut(_cyl(D, H + 2, 0, 0, -1)).cut(_cyl(2.6, H + 1, x_c0, 0, -0.5)).translate((0, 0, z0 + 0.15))
    bouton = _cyl(2.5, H + p.toit - 0.3, 0, 0, 0).union(_cyl(p.bouton_d + 2.0, 1.6, 0, 0, H + p.toit - 0.3))
    bouton = bouton.edges(">Z").fillet(0.6).translate((x_c0, 0, z0 + 0.3))
    # ------------------------------------------------------------------ incrustation du prenom
    corps = corps.cut(extrude(nom.buffer(p.jeu_txt, join_style=1), p.empreinte + 1, E - p.empreinte))
    corps = corps.cut(extrude(nom.buffer(p.jeu_txt + 0.25, join_style=1), 1.0, E - 0.3))
    h_n = p.empreinte + p.relief
    prenom = extrude(nom.buffer(-0.2, join_style=1), 0.3, 0.0).union(extrude(nom, h_n - 0.3, 0.3))
    # ------------------------------------------------------------------ controles
    bb = corps.val().BoundingBox()
    # le prenom ne doit pas mordre le canal (sinon toit trop fin)
    marge_canal = round(x_dos - bx1, 2)
    rep = {
        "texte": texte, "police": police, "jeton_mm": [j.d, j.e], "alesage_mm": round(D, 2),
        "cavite_h_mm": round(H, 2), "course_ejecteur_mm": p.course,
        "sortie_jeton_mm": round(p.course + Rt - x_bec, 1), "doigts_flexibles_mm": p.doigt,
        "dimensions_mm": [round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)],
        "corps_monobloc": len([s_ for s_ in corps.val().Solids() if s_.Volume() > 1]) == 1,
        "prenom_hors_canal_mm": marge_canal, "glyphes": n_gl,
    }
    rep["ok"] = rep["corps_monobloc"] and bb.xlen < 200 and marge_canal > 0.5
    g = {"E": E, "empreinte": p.empreinte, "jeton": j, "params": p, "R": R, "z0": z0, "x_c0": x_c0, "Rt": Rt, "H": H}
    return {"corps": corps, "coulisseau": coul, "bouton": bouton, "prenom": prenom}, g, rep
