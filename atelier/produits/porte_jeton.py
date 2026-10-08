"""Porte-cle PORTE-JETON (jeton de caddie / piece de 1 EUR) avec ejecteur integre.

* fourreau : le jeton entre par le cote (+X), deux BOSSES de clipsage le retiennent ; des fentes de
  decharge transforment les parois de l'embouchure en DOIGTS FLEXIBLES (clic a l'insertion) ;
* poussoir : coulisseau dans un canal derriere le jeton, face concave epousant le jeton ; son BOUTON
  traverse une lumiere du dessus ; la course est bornee par la lumiere -> le jeton depasse juste assez
  pour etre saisi, sans tomber ;
* fenetre sur le dessus (on voit le jeton) + patte d'anneau.

Montage : coulisseau glisse par l'embouchure -> bouton enfonce a travers la lumiere (+ goutte de colle)
-> jeton clipse.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq


@dataclass
class Jeton:
    d: float = 23.25           # jeton de caddie standard / piece de 1 EUR
    e: float = 2.4             # epaisseur maxi admise


@dataclass
class Params:
    jeu_d: float = 0.55        # jeu diametral jeton / fourreau
    jeu_e: float = 0.25        # jeu en epaisseur
    plancher: float = 1.2
    toit: float = 1.4
    paroi: float = 2.2
    bosse: float = 0.6         # interference des bosses principales (par cote)
    cran: float = 0.3          # interference du cran de repos (par cote)
    doigt: float = 1.6         # epaisseur des doigts flexibles
    fente: float = 0.9         # largeur des fentes de decharge
    course: float = 6.5        # sortie du jeton quand on pousse (mm)
    coul_l: float = 8.0        # longueur du coulisseau (X)
    coul_w: float = 12.0       # largeur du coulisseau (Y)
    jeu_coul: float = 0.3
    bouton_d: float = 4.0
    anneau_d: float = 5.0
    patte_d: float = 13.0
    texte: str = ""            # prenom incruste (vide = porte-jeton simple)
    police: str = "arial_black"
    h_txt: float = 11.0        # hauteur des lettres
    marge_txt: float = 4.0
    empreinte: float = 1.0     # profondeur d'incrustation du prenom
    relief: float = 1.2
    jeu_txt: float = 0.12


def _cyl(d, h, x=0.0, y=0.0, z=0.0):
    return cq.Workplane("XY").circle(d / 2).extrude(h).translate((x, y, z))


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def porte_jeton(jeton: Jeton | None = None, p: Params | None = None):
    j, p = jeton or Jeton(), p or Params()
    D = j.d + p.jeu_d                      # alesage du fourreau
    R = D / 2
    H = j.e + p.jeu_e                      # hauteur de la cavite
    z0, z1 = p.plancher, p.plancher + H
    E = z1 + p.toit                        # epaisseur totale
    W = D + 2 * p.paroi
    # centre du jeton au repos = origine ; embouchure a +X (x = R) ; canal du coulisseau a -X
    x_bec = R
    x_dos = -R - p.course - p.coul_l - 1.0 # fond du canal
    # ---- zone prenom (entre l'anneau et le coulisseau) : le corps s'allonge de la longueur du prenom
    nom = None
    L_nom = 0.0
    if p.texte.strip():
        from shapely import affinity
        from atelier.produits.porte_cles import Style, prenom_polygone
        nom, _ = prenom_polygone(p.texte.strip(), Style(police=p.police, hauteur=p.h_txt))
        bx0, by0, bx1, by1 = nom.bounds
        h_max = W - 2 * 3.5                      # le prenom tient dans la largeur du corps
        if by1 - by0 > h_max:
            k = h_max / (by1 - by0)
            nom = affinity.scale(nom, k, k, origin=(0, 0))
            bx0, by0, bx1, by1 = nom.bounds
        L_nom = (bx1 - bx0) + 2 * p.marge_txt
        x_nom = x_dos - p.paroi - L_nom / 2      # centre de la zone prenom
        nom = affinity.translate(nom, x_nom - (bx0 + bx1) / 2, -(by0 + by1) / 2)
    # ---- corps exterieur : stade + patte d'anneau
    L = x_bec - x_dos + p.paroi + L_nom
    corps = cq.Workplane("XY").center((x_bec + x_dos - p.paroi - L_nom) / 2, 0).rect(L, W).extrude(E)
    # arrondi genereux cote anneau, petit cote embouchure (la paroi y porte les bosses de clipsage)
    corps = corps.edges("|Z and <X").fillet(min(W / 2 - 0.5, 9.0)).edges("|Z and >X").fillet(2.0)
    xa = x_dos - p.paroi - L_nom - p.patte_d / 2 + 3.0
    patte = _cyl(p.patte_d, E * 0.75, xa, 0, 0).union(_box(xa, x_dos - p.paroi - L_nom + 2, -p.patte_d * 0.35, p.patte_d * 0.35, 0, E * 0.75))
    corps = corps.union(patte).cut(_cyl(p.anneau_d, E + 2, xa, 0, -1))
    # ---- cavite : fourreau du jeton (cercle + passage jusqu'a l'embouchure) + canal du coulisseau
    cav = _cyl(D, H, 0, 0, z0).union(_box(0, x_bec + p.paroi + 2, -R, R, z0, z1))
    canal = _box(x_dos, 0, -(p.coul_w / 2 + p.jeu_coul), p.coul_w / 2 + p.jeu_coul, z0, z1)
    corps = corps.cut(cav).cut(canal)
    # ---- clipsage a DEUX niveaux (positions calculees par les cordes du jeton, rayon Rt) :
    #  * cran de repos (0.3 mm) juste devant le jeton au repos : il ne ballotte pas ;
    #  * bosses principales (0.6 mm) placees pour qu'en FIN de course le jeton vienne s'y appuyer de
    #    0.3 mm : il depasse (~course) et reste tenu jusqu'a ce qu'on le tire.
    Rt = j.d / 2
    def x_contact(i):                       # recul du centre ou la corde atteint (Rt - i)
        return math.sqrt(max(Rt ** 2 - (Rt - i) ** 2, 0.0))
    crans = [(p.cran, x_contact(p.cran) + 0.2), (p.bosse, p.course - 0.3 + x_contact(p.bosse))]
    for inter, xb in crans:
        tip = Rt - inter                     # sommet de la bosse (depuis l'axe du jeton)
        for s_ in (-1, 1):
            b_ = _cyl(2.4, H, xb, s_ * (tip + 1.2), z0)
            corps = corps.union(b_.intersect(_box(xb - 2, xb + 2, -R - p.paroi, R + p.paroi, z0, z1)))
    # doigts flexibles : fentes de decharge derriere les parois, de la 1re bosse a l'embouchure
    for s_ in (-1, 1):
        y_f = s_ * (R + p.doigt + p.fente / 2)
        if abs(y_f) + p.fente / 2 < W / 2 - 0.4:
            corps = corps.cut(_box(crans[0][1] - 3.0, x_bec + p.paroi + 1, y_f - p.fente / 2, y_f + p.fente / 2, -1, E + 1))
    # ---- fenetre (voir le jeton) + lumiere du bouton
    corps = corps.cut(_cyl(D - 6.0, p.toit + 1, 0, 0, z1 - 0.5))
    x_c0 = -R - p.coul_l / 2                                     # centre du bouton au repos
    lum = (cq.Workplane("XY").center(x_c0 + p.course / 2, 0).slot2D(p.course + p.bouton_d + 0.6, p.bouton_d + 0.6)
           .extrude(p.toit + 1).translate((0, 0, z1 - 0.5)))
    corps = corps.cut(lum)
    # ---- coulisseau (face concave = jeton) et bouton
    xc_av = -R + 0.0                                             # face avant au contact du jeton
    coul = _box(xc_av - p.coul_l, xc_av, -p.coul_w / 2, p.coul_w / 2, 0, H - 2 * 0.15)
    coul = coul.cut(_cyl(D, H + 2, 0, 0, -1))                    # face concave (rayon du jeton)
    coul = coul.cut(_cyl(2.6, H + 1, x_c0, 0, -0.5))             # trou du bouton
    coul = coul.translate((0, 0, z0 + 0.15))
    bouton = _cyl(2.5, H + p.toit - 0.3, 0, 0, 0).union(_cyl(p.bouton_d + 2.0, 1.6, 0, 0, H + p.toit - 0.3))
    bouton = bouton.edges(">Z").fillet(0.6).translate((x_c0, 0, z0 + 0.3))
    # ---- incrustation du prenom (2 impressions : corps couleur 1, prenom couleur 2)
    prenom = None
    if nom is not None:
        from atelier.produits.porte_cles import extrude
        corps = corps.cut(extrude(nom.buffer(p.jeu_txt, join_style=1), p.empreinte + 1, E - p.empreinte))
        corps = corps.cut(extrude(nom.buffer(p.jeu_txt + 0.25, join_style=1), 1.0, E - 0.3))
        h_n = p.empreinte + p.relief
        prenom = extrude(nom.buffer(-0.2, join_style=1), 0.3, 0.0).union(extrude(nom, h_n - 0.3, 0.3))
    # ---- controles
    bb = corps.val().BoundingBox()
    depasse = p.course + Rt - x_bec                               # partie du jeton au-dela de l'embouchure
    rep = {
        "jeton_mm": [j.d, j.e], "alesage_mm": round(D, 2), "cavite_h_mm": round(H, 2),
        "clipsage_par_cote_mm": p.bosse, "doigts_flexibles_mm": p.doigt,
        "course_ejecteur_mm": p.course, "sortie_jeton_mm": round(depasse, 1),
        "crans_x_mm": [round(c[1], 2) for c in crans],
        "dimensions_mm": [round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)],
        "corps_monobloc": len([s_ for s_ in corps.val().Solids() if s_.Volume() > 1]) == 1,
        "ok": True,
    }
    rep["ok"] = rep["corps_monobloc"] and bb.xlen < 200 and p.doigt >= 1.2
    pieces = {"corps": corps, "coulisseau": coul, "bouton": bouton}
    if prenom is not None:
        pieces["prenom"] = prenom
    rep["texte"] = p.texte
    rep["police"] = p.police if p.texte else None
    return pieces, {"E": E, "empreinte": p.empreinte, "jeton": j, "params": p, "R": R, "z0": z0,
                                                                   "x_c0": x_c0, "Rt": Rt, "H": H}, rep
