"""Porte-serviette / porte-cles MURAL personnalise, fixation INVISIBLE (comme un cadre).

* plaque : silhouette du prenom (meme moteur que les porte-cles) + bandeau qui porte les crochets ;
  prenom INCRUSTE (2 impressions : plaque couleur 1, prenom couleur 2, emboite + colle) ;
* fixation : 2 TROUS DE SERRURE au dos (col 4.6 mm, chambre de tete 9.4 mm). On visse 2 vis au mur, on
  presente la plaque et on la fait descendre : les tetes de vis disparaissent derriere. Impression dos au
  plateau -> la chambre est un simple pont de 9.4 mm, sans support ;
* crochets : pieces SEPAREES imprimees A PLAT (la flexion travaille dans le plan des couches, la ou le
  PETG/PLA est solide - un crochet imprime debout casse entre les couches). Ils traversent la plaque par
  une mortaise depuis le DOS ; leur semelle est encastree dans le dos (affleurante) : la traction de la
  serviette s'appuie sur la plaque, rien n'est visible devant.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq
from shapely.geometry import MultiPolygon, Polygon, box as sbox
from shapely.ops import unary_union

from .porte_cles import Style, prenom_polygone, extrude


@dataclass
class ParamsPS:
    hauteur_txt: float = 30.0       # hauteur des lettres (mm)
    contour: float = 6.0            # marge de la plaque autour du prenom
    bandeau: float = 24.0           # hauteur du bandeau qui porte les crochets
    epaisseur: float = 9.0
    empreinte: float = 1.6          # profondeur d'incrustation du prenom
    relief: float = 2.0             # depassement du prenom
    jeu: float = 0.15
    n_crochets: int = 3
    crochet_b: float = 10.0         # largeur du crochet (= epaisseur d'impression a plat)
    crochet_h: float = 9.0          # hauteur de la section du bras
    crochet_l: float = 32.0         # avancee du bras depuis la facade
    crochet_bec: float = 14.0       # hauteur du bec anti-glisse
    semelle: float = 2.5            # epaisseur de la semelle encastree au dos
    jeu_mortaise: float = 0.2
    vis_tete: float = 9.4           # chambre des trous de serrure (tete de vis <= 8.5)
    vis_col: float = 4.6            # col (vis d3.5 - 4)
    serrure_course: float = 10.0
    serrure_col_ep: float = 1.8
    serrure_chambre_ep: float = 3.5
    charge_kg: float = 1.5          # serviette de bain mouillee
    dyn: float = 2.0
    mode: str = "2impressions"


def _rect(x0, x1, y0, y1):
    return sbox(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _prisme(poly, z0, z1):
    return extrude(poly, z1 - z0, z0)


def porte_serviette(texte="Steven", police="pacifico", p: ParamsPS | None = None):
    p = p or ParamsPS()
    st = Style(police=police, hauteur=p.hauteur_txt, contour=p.contour, jeu=p.jeu)
    nom, n_gl = prenom_polygone(texte, st)
    x0, y0, x1, y1 = nom.bounds
    # ---------------------------------------------------------- plaque 2D
    sil = nom.buffer(p.contour, join_style=1)
    sil = unary_union([Polygon(g.exterior) for g in (sil.geoms if isinstance(sil, MultiPolygon) else [sil])])
    L = (x1 - x0) + 2 * p.contour
    yb1 = y0 + 0.30 * (y1 - y0)                      # le bandeau remonte sous le bas des lettres
    yb0 = y0 - p.contour - p.bandeau
    bandeau = _rect(x0 - p.contour, x1 + p.contour, yb0, yb1).buffer(-4).buffer(4)
    plaque2d = unary_union([sil, bandeau]).buffer(2, join_style=1).buffer(-2, join_style=1)
    E = p.epaisseur
    # ---------------------------------------------------------- crochets : positions sur le bandeau
    n = max(1, p.n_crochets)
    y_cr = (yb0 + (y0 - p.contour)) / 2 + 1.0       # milieu du bandeau
    xs = [x0 + (i + 0.5) * (x1 - x0) / n for i in range(n)]
    # ---------------------------------------------------------- volume de la plaque (dos = z 0, face = z E)
    plaque = _prisme(plaque2d, 0.0, E)
    coupes = []
    for xc in xs:
        bm, hm = p.crochet_b + p.jeu_mortaise, p.crochet_h + p.jeu_mortaise
        coupes.append(_prisme(_rect(xc - bm / 2, xc + bm / 2, y_cr - hm / 2, y_cr + hm / 2), -1, E + 1))
        # logement de la semelle dans le dos (affleurante)
        bs, hs = bm + 8, hm + 8
        coupes.append(_prisme(_rect(xc - bs / 2, xc + bs / 2, y_cr - hs / 2, y_cr + hs / 2), -1, p.semelle + 0.1))
        # degagement du conge semelle / tenon (R 1.2) au fond du logement
        coupes.append(_prisme(_rect(xc - bm / 2 - 1.4, xc + bm / 2 + 1.4, y_cr - hm / 2 - 1.4, y_cr + hm / 2 + 1.4),
                              -1, p.semelle + 1.4))
    # ---------------------------------------------------------- trous de serrure (dos)
    y_k = (y0 + y1) / 2 - p.serrure_course / 2      # cercle d'entree ; la fente monte de `course`
    xk = [x0 + 0.18 * (x1 - x0), x0 + 0.82 * (x1 - x0)]
    for xc in xk:
        col = unary_union([Polygon([(xc + p.vis_col / 2 * math.cos(a), y_k + p.vis_col / 2 * math.sin(a))
                                    for a in [i * 2 * math.pi / 48 for i in range(48)]]).buffer(0),
                           _rect(xc - p.vis_col / 2, xc + p.vis_col / 2, y_k, y_k + p.serrure_course)])
        entree = Polygon([(xc + p.vis_tete / 2 * math.cos(a), y_k + p.vis_tete / 2 * math.sin(a))
                          for a in [i * 2 * math.pi / 64 for i in range(64)]])
        chambre = unary_union([entree, _rect(xc - p.vis_tete / 2, xc + p.vis_tete / 2, y_k, y_k + p.serrure_course),
                               Polygon([(xc + p.vis_tete / 2 * math.cos(a), y_k + p.serrure_course + p.vis_tete / 2 * math.sin(a))
                                        for a in [i * 2 * math.pi / 64 for i in range(64)]])])
        coupes.append(_prisme(unary_union([col, entree]), -1, p.serrure_col_ep))          # col + entree de la tete
        coupes.append(_prisme(chambre, p.serrure_col_ep - 0.01, p.serrure_col_ep + p.serrure_chambre_ep))
    # ---------------------------------------------------------- incrustation du prenom
    if p.mode == "2impressions":
        coupes.append(_prisme(nom.buffer(p.jeu, join_style=1), E - p.empreinte, E + 1))
        coupes.append(_prisme(nom.buffer(p.jeu + 0.25, join_style=1), E - 0.3, E + 1))
        h_nom = p.empreinte + p.relief
        prenom = _prisme(nom.buffer(-0.2, join_style=1), 0, 0.3).union(_prisme(nom, 0.3, h_nom))
    else:
        h_nom = p.relief
        prenom = _prisme(nom, E, E + p.relief)
    for c_ in coupes:
        plaque = plaque.cut(c_)
    # ---------------------------------------------------------- crochet (profil u = hors du mur, v = vertical)
    E_t = E                                          # le tenon traverse toute la plaque
    b, h = p.crochet_b, p.crochet_h
    u_bras = E_t + p.crochet_l
    prof = unary_union([
        _rect(0, p.semelle, -(h / 2 + 4), h / 2 + 4),                      # semelle (dans le dos)
        _rect(p.semelle - 0.01, E_t + 0.01, -h / 2, h / 2),                # tenon (dans la mortaise)
        _rect(E_t, u_bras, -h / 2, h / 2),                                  # bras
        _rect(u_bras - 7.0, u_bras, -h / 2, h / 2 + p.crochet_bec),        # bec
    ]).buffer(1.2, join_style=1).buffer(-1.2, join_style=1)         # conges interieurs (raccords)
    # arrondis EXTERIEURS du bras et du bec (crochet galbe, doux pour le linge) ; la semelle et le tenon
    # restent a angles vifs (ajustement dans la mortaise)
    galbe = _rect(E_t + 2.0, u_bras + 5, -h / 2 - 5, h / 2 + p.crochet_bec + 5)
    prof = unary_union([prof.difference(galbe), prof.intersection(galbe).buffer(-3.0, join_style=1).buffer(3.0, join_style=1)])
    # conge de raccordement bras / facade (le bas reste droit pour sortir de la mortaise)
    crochet_2d = prof
    crochet = extrude(crochet_2d, b, 0.0)                                   # imprime A PLAT, profil dans XY
    # ---------------------------------------------------------- controles mecaniques
    g = 9.81
    F = p.charge_kg * g * p.dyn / n * 1.5            # repartition + 50 % si la serviette est sur un seul crochet
    F = max(F, p.charge_kg * g * p.dyn)              # cas le plus defavorable : tout sur un crochet
    M = F * (p.crochet_l - 3.5)                       # N.mm, charge au fond du crochet
    W_ = b * h ** 2 / 6
    sig = M / W_
    adm_plan = 20.0                                   # PETG/PLA, flexion DANS le plan des couches (a plat)
    ledge = (p.vis_tete - p.vis_col) / 2
    perim = math.pi * p.vis_tete / 2 + 2 * p.serrure_course
    tau_cap = perim * p.serrure_col_ep * 8.0          # N, cisaillement du rebord du col (8 MPa)
    # arrachement en haut de plaque : moment de la charge repris par les serrures (bras de levier ~ distance
    # serrures -> bas de plaque)
    lev = max(y_k - yb0, 10.0)
    T_serrure = F * (E + p.crochet_l) / lev / 2
    pb = plaque2d.bounds
    rep = {
        "texte": texte, "police": police,
        "dimensions_mm": [round(pb[2] - pb[0], 1), round(pb[3] - pb[1], 1), E],
        "crochets": n, "entraxe_vis_mm": round(xk[1] - xk[0], 1),
        "vis_conseillees": f"vis tete cylindrique ou ronde d3.5-4 (tete <= {p.vis_tete - 0.9:.1f} mm) + chevilles, "
                           f"depassant de {p.serrure_col_ep + 2.0:.1f}-{p.serrure_col_ep + p.serrure_chambre_ep - 0.5:.1f} mm",
        "crochet_contrainte_MPa": round(sig, 1), "crochet_coef": round(adm_plan / sig, 2),
        "serrure_capacite_N": round(tau_cap), "serrure_effort_N": round(T_serrure, 1),
        "serrure_coef": round(tau_cap / max(T_serrure, 1e-6), 1),
        "plaque_monobloc": len([s_ for s_ in plaque.val().Solids() if s_.Volume() > 1]) == 1,
        "tient_plateau": (pb[2] - pb[0]) <= 205 and (pb[3] - pb[1]) <= 200,
    }
    rep["ok"] = rep["plaque_monobloc"] and rep["tient_plateau"] and rep["crochet_coef"] >= 2 and rep["serrure_coef"] >= 3
    return {"plaque": plaque, "prenom": prenom, "crochet": crochet}, rep, {"xs": xs, "y_cr": y_cr, "E": E,
                                                                          "b": p.crochet_b}
