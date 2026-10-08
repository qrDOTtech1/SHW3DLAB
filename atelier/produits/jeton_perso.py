"""Jeton de caddie IMPRIME et personnalise : initiale en grand, QR code ou logo (image -> 2D).

Le jeton garde les cotes d'une piece (d du porte-jeton, epaisseur 2.33 mm = piece de 1 EUR) pour
fonctionner dans les caddies ET dans le porte-cle. Deux fabrications :

* "incruste" (2 impressions, comme les prenoms) : disque couleur 1 avec empreinte de 1 mm, motif couleur 2
  emboite + colle, AFFLEURANT (le jeton reste plat des deux cotes). Reserve aux motifs en peu de morceaux
  (initiale, logo simple) ;
* "pause" (1 impression + changement de filament) : disque couleur 1 jusqu'a 1.73 mm, puis PAUSE dans le
  G-code -> on change de filament -> le motif et le jonc du bord (0.6 mm) sortent en couleur 2. Obligatoire
  pour un QR code (des centaines de modules), conseille pour les logos detailles.
"""
from __future__ import annotations

import math

import cadquery as cq
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, box as sbox
from shapely.ops import unary_union

from atelier.produits.porte_cles import Style, glyphes, extrude


E_JETON = 2.33          # epaisseur d'une piece de 1 EUR / jeton de caddie
H_MOTIF = 0.6           # epaisseur de la couche couleur 2 (mode pause)
JONC = 1.1              # largeur du jonc du bord
EMPREINTE = 1.0         # profondeur d'incrustation (mode incruste)
JEU = 0.1


def _ajuster(poly, r_max):
    """Centre le motif et le met a l'echelle pour tenir dans un cercle de rayon r_max."""
    b = poly.bounds
    poly = affinity.translate(poly, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
    pts = [c for g in (poly.geoms if isinstance(poly, MultiPolygon) else [poly]) for c in g.exterior.coords]
    dmax = max(math.hypot(x, y) for x, y in pts)
    k = r_max / dmax
    return affinity.scale(poly, k, k, origin=(0, 0))


def motif_initiale(lettre, police, r_max):
    gs = glyphes(lettre[:1], Style(police=police, hauteur=20.0))
    return _ajuster(unary_union(gs), r_max)


def motif_qr(texte, r_max):
    import numpy as np
    import qrcode
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=0)   # L : moins de modules
    q.add_data(texte)                                                                  # -> modules plus gros
    q.make(fit=True)
    M = np.array(q.get_matrix(), dtype=bool)
    n = M.shape[0]
    cote = 2 * r_max / math.sqrt(2)
    mod = cote / n
    bx = [sbox(-cote / 2 + j * mod, cote / 2 - (i + 1) * mod, -cote / 2 + (j + 1) * mod, cote / 2 - i * mod)
          for i in range(n) for j in range(n) if M[i, j]]
    return unary_union(bx).buffer(0.01, join_style=2).buffer(-0.01, join_style=2), mod, n


def _disque(d, e, chanfrein=0.3):
    return (cq.Workplane("XY").circle(d / 2).extrude(e).edges().chamfer(chanfrein))


def jeton_perso(d=23.25, motif="initiale", texte="S", police="pacifico", mode="incruste", image=None,
                seuil=None, inverser=None):
    """-> (pieces, rep). pieces : {"jeton"} (+ "jeton_motif" en mode incruste)."""
    r_int = d / 2 - JONC - 0.3
    rep = {"motif": motif, "diametre_mm": d, "epaisseur_mm": E_JETON}
    if motif == "initiale":
        poly = motif_initiale(texte.strip()[:1] or "?", police, r_int)
        rep["lettre"] = texte.strip()[:1]
    elif motif == "qr":
        poly, mod, n = motif_qr(texte or "https://monsite.fr", r_int)
        rep.update({"qr_modules": n, "qr_module_mm": round(mod, 2), "qr_lisible": mod >= 0.55, "qr_conseil": "URL de 17 caracteres max -> 21 modules (0.7 mm), plus net" if n > 21 else ""})
        if mode != "pause":
            rep["mode_force"] = "QR = des centaines de modules : 1 impression avec pause (changement de filament)"
        mode = "pause"
    elif motif == "logo":
        from atelier.noyau.image2d import image_vers_polygone
        poly, info = image_vers_polygone(image, 2 * r_int, seuil, inverser, detail_min_mm=0.45)
        poly = _ajuster(poly, r_int)
        rep["logo"] = info
    else:
        raise ValueError(f"motif inconnu : {motif}")
    n_parts = len(poly.geoms) if isinstance(poly, MultiPolygon) else 1
    rep["morceaux_motif"] = n_parts
    if mode == "incruste" and n_parts > 6:
        rep["mode_force"] = f"motif en {n_parts} morceaux : trop a coller -> 1 impression avec pause"
        mode = "pause"
    rep["mode"] = mode
    if mode == "incruste":
        j = _disque(d, E_JETON)
        j = j.cut(extrude(poly.buffer(JEU, join_style=1), EMPREINTE + 1, E_JETON - EMPREINTE))
        j = j.cut(extrude(poly.buffer(JEU + 0.2, join_style=1), 1.0, E_JETON - 0.25))
        m = extrude(poly.buffer(-0.15, join_style=1), 0.25, 0.0).union(extrude(poly, EMPREINTE - 0.25, 0.25))
        pieces = {"jeton": j, "jeton_motif": m}
        rep["pause_z"] = None
    else:
        zp = E_JETON - H_MOTIF
        base = _disque(d, E_JETON).cut(cq.Workplane("XY").circle(d / 2 - JONC).extrude(H_MOTIF + 1).translate((0, 0, zp)))
        haut = extrude(poly.intersection(Point(0, 0).buffer(d / 2 - JONC + 0.05, 128)), H_MOTIF, zp)
        pieces = {"jeton": base.union(haut)}
        rep["pause_z"] = round(zp, 2)
    rep["ok"] = True
    return pieces, poly, rep
