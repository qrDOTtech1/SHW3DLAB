"""ATELIER-3D : generateurs d'objets personnalises pour la Creality K2 SE.

Chaque generateur renvoie un dict {couleur: solide CadQuery}. Les couleurs sont des CORPS separes :
- avec le module CFS (multicolore) : on importe le 3MF, un objet = une couleur ;
- sans CFS : meme fichier, impression monochrome + changement de filament a la hauteur indiquee
  (le relief commence toujours a une hauteur unique, donnee dans le rapport).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq
import numpy as np


@dataclass(frozen=True)
class Machine:
    nom: str = "Creality K2 SE"
    x: float = 220.0
    y: float = 215.0
    z: float = 245.0
    marge: float = 5.0


K2SE = Machine()
POLICE = "Arial"
POLICE_GRAS = "Arial Black"


# ---------------------------------------------------------------- briques
def texte(chaine, hauteur_lettre, epaisseur, police=POLICE, largeur_max=None, z0=0.0):
    """Texte en relief, centre en (0, 0). Reduit la taille si la largeur depasse largeur_max."""
    h = hauteur_lettre
    for _ in range(8):
        t = cq.Workplane("XY").text(chaine, h, epaisseur, font=police, halign="center", valign="center",
                                    combine=False)
        bb = t.val().BoundingBox()
        if largeur_max is None or bb.xlen <= largeur_max:
            break
        h *= largeur_max / bb.xlen * 0.98
    return t.translate((0, 0, z0)), h


def plaque_arrondie(L, l, e, r):
    r = min(r, L / 2 - 0.01, l / 2 - 0.01)
    return cq.Workplane("XY").box(L, l, e, centered=(True, True, False)).edges("|Z").fillet(r)


def qr_matrice(url, bordure=1):
    import qrcode
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=bordure)
    q.add_data(url)
    q.make(fit=True)
    return np.array(q.get_matrix(), dtype=bool)


def qr_relief(url, cote_mm, epaisseur, z0=0.0):
    """QR en relief (modules noirs), carre de cote_mm centre en (0, 0). Renvoie (solide, module_mm, fond)."""
    M = qr_matrice(url, bordure=0)
    n = M.shape[0]
    mod = cote_mm / n
    boites = []
    for i in range(n):                                   # fusion des modules par lignes (runs)
        j = 0
        while j < n:
            if M[i, j]:
                k = j
                while k < n and M[i, k]:
                    k += 1
                x0 = -cote_mm / 2 + j * mod
                y0 = cote_mm / 2 - (i + 1) * mod
                boites.append(cq.Solid.makeBox((k - j) * mod, mod, epaisseur, cq.Vector(x0, y0, z0)))
                j = k
            else:
                j += 1
    sol = cq.Workplane("XY").add(cq.Compound.makeCompound(boites)).combine(clean=True)
    return sol, mod, n


# ---------------------------------------------------------------- porte-cle
def porte_cle(prenom="STEVEN", forme="capsule", L=60.0, l=22.0, e=3.0, relief=1.0, anneau_d=5.0):
    """Porte-cle prenom : plaque + texte en relief (2e couleur) + trou d'anneau renforce."""
    base = plaque_arrondie(L, l, e, l / 2 if forme == "capsule" else 4.0)
    xa = -L / 2 + l / 2 if forme == "capsule" else -L / 2 + 6.0
    base = base.cut(cq.Workplane("XY").circle(anneau_d / 2).extrude(e + 1).translate((xa, 0, -0.5)))
    zone = L - (xa + L / 2) - anneau_d - 4.0              # largeur utile a droite de l'anneau
    t, h = texte(prenom.upper(), l * 0.5, relief, POLICE_GRAS, largeur_max=zone - 3.0, z0=e)
    cx = xa + anneau_d / 2 + 2.5 + zone / 2
    t = t.translate((cx, 0, 0))
    return {"base": base, "relief": t}, {"hauteur_changement_couleur_mm": e, "taille_lettres_mm": round(h, 1)}


# ---------------------------------------------------------------- presentoir
def presentoir(url="https://monsite.fr/porte-cle", titre="TON PORTE-CLÉ", sous_titre="PERSONNALISÉ",
               appel="Commande le tien :", n=3, largeur=170.0, hauteur=190.0, e=4.0, relief=1.2,
               crochet_d=6.0, crochet_l=16.0, pas=None, inclinaison=75.0):
    """Presentoir 2 pieces :
    * PANNEAU imprime a plat (face lisible vers le haut -> texte et QR nets, multicolore possible),
      avec n crochets-champignons venant de la meme impression ;
    * PIED avec rainure inclinee (75 deg) dans laquelle le panneau s'emboite.
    """
    pas = pas or largeur / n
    pan = plaque_arrondie(largeur, hauteur, e, 8.0)
    relief_parts = []
    # bandeau titre (haut du panneau = +Y)
    t1, h1 = texte(titre, 14.0, relief, POLICE_GRAS, largeur_max=largeur - 20, z0=e)
    t2, h2 = texte(sous_titre, 11.0, relief, POLICE_GRAS, largeur_max=largeur - 30, z0=e)
    y_t1, y_t2 = hauteur / 2 - 16.0, hauteur / 2 - 33.0
    relief_parts += [t1.translate((0, y_t1, 0)), t2.translate((0, y_t2, 0))]
    # ligne de crochets
    y_cr = hauteur / 2 - 62.0
    crochets = []
    for i in range(n):
        x = -largeur / 2 + pas * (i + 0.5)
        tige = cq.Workplane("XY").circle(crochet_d / 2).extrude(crochet_l).translate((x, y_cr, e))
        tete = (cq.Workplane("XY").circle(crochet_d / 2 + 2.0).extrude(2.5)
                .faces("<Z").chamfer(1.9)                  # chanfrein 45 deg : imprimable sans support
                .translate((x, y_cr, e + crochet_l)))
        crochets += [tige, tete]
    # QR + appel a commander (bas du panneau)
    qr_cote = 46.0
    y_qr = -hauteur / 2 + 14.0 + qr_cote / 2
    x_qr = largeur / 2 - 14.0 - qr_cote / 2
    qr, mod, nq = qr_relief(url, qr_cote, relief, z0=e)   # meme hauteur que le texte : 1 seul changement
    qr = qr.translate((x_qr, y_qr, 0))
    larg_txt = largeur - qr_cote - 40.0
    x_txt = -largeur / 2 + 10.0 + larg_txt / 2
    t3, h3 = texte(appel, 8.0, relief, POLICE, largeur_max=larg_txt, z0=e)
    site = url.split("//")[-1].split("/")[0]
    t4, h4 = texte(site, 9.0, relief, POLICE_GRAS, largeur_max=larg_txt, z0=e)
    relief_parts += [t3.translate((x_txt, y_qr + 7, 0)), t4.translate((x_txt, y_qr - 7, 0))]
    relief_parts.append(qr)
    panneau = pan
    for c in crochets:
        panneau = panneau.union(c)
    # tenon bas (s'emboite dans le pied)
    tenon_h = 12.0
    panneau = panneau.union(cq.Workplane("XY").box(largeur - 40, tenon_h, e, centered=(True, False, False))
                            .translate((0, -hauteur / 2 - tenon_h + 0.01, 0)))
    rel = relief_parts[0]
    for r_ in relief_parts[1:]:
        rel = rel.union(r_)
    # pied : rainure inclinee, lest creux optionnel
    jeu = 0.25
    pied_L, pied_P, pied_H = largeur, 70.0, 22.0
    pied = plaque_arrondie(pied_L, pied_P, pied_H, 10.0).edges(">Z").fillet(3.0)
    ang = math.radians(90 - inclinaison)
    fente = (cq.Workplane("XY").box(largeur - 40 + 2 * jeu, e + 2 * jeu, 60, centered=(True, True, False))
             .rotate((0, 0, 0), (1, 0, 0), -math.degrees(ang)).translate((0, 6.0, pied_H - tenon_h)))
    pied = pied.cut(fente)
    pied = pied.cut(cq.Workplane("XY").box(pied_L - 30, pied_P - 30, 10, centered=(True, True, False))
                    .translate((0, 0, -0.01)))             # poche sous le pied : lest (ecrous, sable)
    info = {"hauteur_changement_couleur_mm": e, "qr_module_mm": round(mod, 2), "qr_modules": nq,
            "qr_url": url, "inclinaison_deg": inclinaison,
            "note_qr": "module >= 1.5 mm conseille pour un scan fiable a 30-40 cm" if mod < 1.5 else "ok"}
    return {"panneau": {"base": panneau, "relief": rel}, "pied": {"base": pied}}, info


# ---------------------------------------------------------------- export + controles
def _mesh(shape, tol=0.05):
    import trimesh
    sh = shape.val() if hasattr(shape, "val") else shape
    if hasattr(shape, "vals") and len(shape.vals()) > 1:
        sh = cq.Compound.makeCompound([v for v in shape.vals()])
    vs, tris = sh.tessellate(tol, 0.2)
    return trimesh.Trimesh([[v.x, v.y, v.z] for v in vs], tris)


def exporter(nom, corps, dossier, machine=K2SE):
    """STL par couleur + 3MF multi-objets + controles (plateau, monobloc)."""
    import trimesh
    dossier.mkdir(parents=True, exist_ok=True)
    rapport = {"piece": nom, "fichiers": [], "controles": {}}
    scene = trimesh.Scene()
    meshes = []
    couleurs = {"base": [235, 235, 235, 255], "relief": [30, 30, 30, 255]}
    for coul, solide in corps.items():
        m = _mesh(solide)
        f = dossier / f"{nom}_{coul}.stl"
        m.export(f)
        rapport["fichiers"].append(f.name)
        m.visual.face_colors = couleurs.get(coul, [200, 120, 40, 255])
        scene.add_geometry(m, geom_name=f"{nom}_{coul}")
        meshes.append(m)
    allm = trimesh.util.concatenate(meshes)
    ext = allm.extents
    fits = (ext[0] <= machine.x - 2 * machine.marge and ext[1] <= machine.y - 2 * machine.marge
            and ext[2] <= machine.z) or (ext[1] <= machine.x - 2 * machine.marge and ext[0] <= machine.y - 2 * machine.marge
                                         and ext[2] <= machine.z)
    base = corps["base"].val() if hasattr(corps["base"], "val") else corps["base"]
    sols = [s for s in cq.Workplane().add(corps["base"].vals() if hasattr(corps["base"], "vals") else [base]).val().Solids()
            if s.Volume() > 1.0] if hasattr(base, "Solids") else []
    rapport["controles"] = {"dimensions_mm": [round(float(v), 1) for v in ext], "tient_sur_le_plateau": bool(fits),
                            "corps_base_monobloc": len(sols) == 1,
                            "volume_cm3": round(float(sum(abs(m.volume) for m in meshes)) / 1000, 1)}
    f3 = dossier / f"{nom}.3mf"
    scene.export(f3)
    rapport["fichiers"].append(f3.name)
    return rapport
