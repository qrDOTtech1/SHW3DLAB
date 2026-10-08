"""KEYCAPS : moteur parametrique de touches de clavier (profils, tailles libres, tiges, legendes, logos).

Profils (hauteurs par rangee R1 = rangee des chiffres ... R4 = rangee du bas, comme les fabricants) :
  oem, cherry (sculptes, creux cylindrique), dsa, xda, sa (uniformes / spheriques), plat (low-profile facon
  clavier bureautique / chiclet), perso (tout libre).
Tiges : mx (Cherry MX et clones : Gateron, Kailh BOX, Outemu...), choc (Kailh Choc v1 low-profile), choc_v2
  (croix MX basse), alps (Alps / Matias), rond (axe rond perso), aucune (cache decoratif, a coller).
Tailles : en u (1u = pas de 19.05 mm) ou dimensions libres en mm (claviers au pas different, touches
  speciales). Stabilisateurs automatiques a partir de 2u (entraxes Cherry : 2-2.75u = 23.876 mm, 6.25u = 100 mm).
Legendes : texte (17 polices) ou logo (image -> 2D) sur le DESSUS (epouse le creux) ou la FACE AVANT, en
  relief, grave, ou incruste 2 couleurs (facon double-shot : 2 pieces emboitees).
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as mf
from shapely import affinity
from shapely.geometry import box as sbox, MultiPolygon

from .c3d import section, vers_manifold, vers_trimesh, integrer

PAS = 19.05

# hauteurs (avant, arriere) par rangee R1..R4, et forme du creux
PROFILS = {
    "oem":    {"nom": "OEM (sculpte)", "rangs": {1: (11.2, 12.4), 2: (9.4, 10.6), 3: (8.6, 9.6), 4: (8.8, 9.4)}, "dish": "cylindre", "creux": 0.9, "haut": (12.5, 13.5)},
    "cherry": {"nom": "Cherry (sculpte bas)", "rangs": {1: (9.3, 10.4), 2: (7.4, 8.6), 3: (7.0, 7.9), 4: (7.6, 8.1)}, "dish": "cylindre", "creux": 0.75, "haut": (12.3, 13.4)},
    "dsa":    {"nom": "DSA (uniforme)", "rangs": {r: (7.4, 7.4) for r in (1, 2, 3, 4)}, "dish": "sphere", "creux": 1.0, "haut": (12.7, 12.7)},
    "xda":    {"nom": "XDA (large, uniforme)", "rangs": {r: (9.0, 9.0) for r in (1, 2, 3, 4)}, "dish": "sphere", "creux": 0.8, "haut": (14.6, 14.6)},
    "sa":     {"nom": "SA (haut, retro)", "rangs": {1: (13.5, 14.8), 2: (11.8, 12.6), 3: (11.4, 11.4), 4: (11.8, 12.6)}, "dish": "sphere", "creux": 1.3, "haut": (12.7, 12.7)},
    "plat":   {"nom": "Plat / low-profile (bureautique)", "rangs": {r: (4.6, 4.6) for r in (1, 2, 3, 4)}, "dish": "cylindre", "creux": 0.35, "haut": (15.4, 14.6)},
    "perso":  {"nom": "Personnalise", "rangs": {r: (8.0, 9.0) for r in (1, 2, 3, 4)}, "dish": "cylindre", "creux": 0.8, "haut": (12.5, 13.5)},
}

TIGES = {"mx": "Cherry MX (et clones)", "choc": "Kailh Choc v1 (low-profile)", "choc_v2": "Kailh Choc v2 (croix MX basse)",
         "alps": "Alps / Matias", "rond": "Axe rond", "aucune": "Aucune (cache a coller)"}


def _rect(l, w, r):
    r = max(0.0, min(r, l / 2 - 0.05, w / 2 - 0.05))
    b = sbox(-l / 2, -w / 2, l / 2, w / 2)
    return b.buffer(-r, join_style=1).buffer(r, join_style=1) if r > 0 else b


def _croix(l=4.1, e=1.25, jeu=0.05, h=10.0):
    a = mf.Manifold.cube((l + 2 * jeu, e + 2 * jeu, h)).translate((-(l + 2 * jeu) / 2, -(e + 2 * jeu) / 2, 0))
    b = mf.Manifold.cube((e + 2 * jeu, l + 2 * jeu, h)).translate((-(e + 2 * jeu) / 2, -(l + 2 * jeu) / 2, 0))
    return a + b


def _tige(type_, h, jeu, d_rond=4.0):
    """Tige dans le repere de la touche (z = 0 au bas de la jupe), pointant vers le haut jusqu'a h."""
    if type_ == "mx" or type_ == "choc_v2":
        cyl = mf.Manifold.cylinder(h, 2.75, 2.75, 48)
        return cyl - _croix(4.1, 1.25, jeu, 4.2).translate((0, 0, -0.01)), 4.2 if type_ == "mx" else 3.0
    if type_ == "choc":
        # 2 lames 1.2 x 3.0 a 5.7 mm d'entraxe (Kailh Choc v1)
        lame = mf.Manifold.cube((1.2 - 2 * jeu, 3.0 - 2 * jeu, h)).translate((-(1.2 - 2 * jeu) / 2, -(3.0 - 2 * jeu) / 2, 0))
        return lame.translate((-2.85, 0, 0)) + lame.translate((2.85, 0, 0)), 3.0
    if type_ == "alps":
        return mf.Manifold.cube((4.5 - 2 * jeu, 2.2 - 2 * jeu, h)).translate((-(4.5 - 2 * jeu) / 2, -(2.2 - 2 * jeu) / 2, 0)), 3.5
    if type_ == "rond":
        return mf.Manifold.cylinder(h, d_rond / 2 + 1.2, d_rond / 2 + 1.2, 48) - mf.Manifold.cylinder(4.0, d_rond / 2 + jeu, d_rond / 2 + jeu, 48).translate((0, 0, -0.01)), 4.0
    return None, 0


def entraxes_stab(lx_u):
    if lx_u >= 6:
        return [-50.0, 50.0]
    if lx_u >= 2:
        return [-11.938, 11.938]
    return []


def keycap(p: dict):
    """-> (trimesh, info). p : profil, rang, u_x, u_y, (l_mm, w_mm), pas, tige, jeu, + surcharges."""
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    prof = PROFILS.get(p.get("profil", "oem"), PROFILS["oem"])
    rang = int(p.get("rang", 3))
    pas = g("pas", PAS)
    ux, uy = g("u_x", 1.0), g("u_y", 1.0)
    jeu_bord = g("ecart", 1.05)                                   # espace entre touches (19.05 -> 18.0)
    L = g("l_mm", ux * pas - jeu_bord)
    W = g("w_mm", uy * pas - jeu_bord)
    h_av, h_ar = prof["rangs"].get(rang, list(prof["rangs"].values())[2])
    h_av, h_ar = g("h_avant", h_av), g("h_arriere", h_ar)
    tw, td = prof["haut"]
    marge_l, marge_w = (18.0 - tw), (18.0 - td)
    lt, wt = g("haut_l", max(4.0, L - marge_l)), g("haut_w", max(4.0, W - marge_w))
    r_bas, r_haut = g("rayon_bas", 1.2 if p.get("profil") != "plat" else 1.8), g("rayon_haut", 2.0)
    paroi = g("paroi", 1.3)
    dish_type = p.get("dish") or prof["dish"]
    creux = g("creux", prof["creux"])
    h = max(h_av, h_ar)
    decal_haut = g("decal_haut", 0.0)                             # le haut recule (profils sculptes)

    # ---------------------------------------------------------- coque exterieure (loft rectangle arrondi)
    # loft bas -> haut avec rayon qui change : couches empilees (hull de deux tranches) = flancs propres
    bas = mf.Manifold.extrude(section(_rect(L, W, r_bas)), 0.01)
    haut = mf.Manifold.extrude(section(_rect(lt, wt, r_haut)), 0.01).translate((0, decal_haut, h + 4))
    corps = mf.Manifold.batch_hull([bas, haut])
    # dessus incline (arriere plus haut) : plan de coupe
    pente = math.degrees(math.atan2(h_ar - h_av, W))
    plan = mf.Manifold.cube((L * 4, W * 4, 60), True).rotate((-pente, 0, 0)).translate((0, 0, 30 + (h_av + h_ar) / 2))
    corps = corps - plan
    z_haut = (h_av + h_ar) / 2
    # creux du dessus (dish)
    if creux > 0 and dish_type != "plat":
        if dish_type == "sphere":
            Rd = (max(lt, wt) ** 2 / 4 + creux ** 2) / (2 * creux)
            outil = mf.Manifold.sphere(Rd, 192).translate((0, 0, Rd - creux))
        else:
            Rd = (wt ** 2 / 4 + creux ** 2) / (2 * creux)
            outil = mf.Manifold.cylinder(L * 3, Rd, Rd, 192, True).rotate((0, 90, 0)).translate((0, 0, Rd - creux))
        # le creux suit l'inclinaison du dessus (profils sculptes)
        corps = corps - outil.rotate((-pente, 0, 0)).translate((0, decal_haut, z_haut))
    # ---------------------------------------------------------- interieur creux
    hi = h - paroi - 0.8
    ib = mf.Manifold.extrude(section(_rect(L - 2 * paroi, W - 2 * paroi, max(0.3, r_bas - paroi))), 0.01).translate((0, 0, -0.01))
    ih = mf.Manifold.extrude(section(_rect(max(2, lt - 2 * paroi), max(2, wt - 2 * paroi), 0.5)), 0.01).translate((0, decal_haut, max(1.0, min(h_av, h_ar) - paroi - creux - 0.6)))
    interieur = mf.Manifold.batch_hull([ib, ih])
    corps = corps - interieur
    # ---------------------------------------------------------- tige(s) + stabilisateurs
    tige_t = p.get("tige", "mx")
    jeu = g("jeu", 0.05)
    h_tige = max(1.0, min(h_av, h_ar) - paroi - creux - 0.4)
    t, prof_tige = _tige(tige_t, h_tige + 0.5, jeu, g("d_axe", 4.0))
    infos = {"dimensions_mm": [round(L, 2), round(W, 2), round(h, 2)], "profil": prof["nom"], "rang": rang,
             "tige": TIGES.get(tige_t, tige_t), "stabilisateurs": []}
    z_tige = 0.6 if tige_t in ("mx", "alps", "rond") else 0.3
    if t is not None:
        corps = corps + t.translate((0, 0, z_tige))
        for x in entraxes_stab(ux if ux >= uy else 0):
            if tige_t in ("mx", "choc_v2"):
                corps = corps + _tige("mx", h_tige + 0.5, jeu)[0].translate((x, 0, z_tige))
            infos["stabilisateurs"].append(x)
        # nervures de renfort tige -> parois (la tige ne casse pas)
        if p.get("nervures", True):
            for ang in (0, 90):
                lg = (L if ang == 0 else W) - 2 * paroi
                n_ = mf.Manifold.cube((lg, 1.0, 1.6), True).translate((0, 0, h_tige - 0.2))
                corps = corps + (n_.rotate((0, 0, ang)) ^ interieur.translate((0, 0, 0)))
    # ---------------------------------------------------------- reperes de doigts (F / J)
    rep = p.get("repere", "aucun")
    if rep in ("barre", "point"):
        if rep == "barre":
            b = mf.Manifold.cube((4.0, 0.9, 0.6), True)
        else:
            b = mf.Manifold.sphere(0.8, 24)
        corps = corps + b.translate((0, -wt / 2 + 2.6, z_haut - creux + 0.25))
    m = vers_trimesh(corps)
    infos["haut_mm"] = [round(lt, 2), round(wt, 2)]
    infos["z_dessus"] = round(z_haut, 2)
    infos["creux"] = creux
    infos["pente_deg"] = round(pente, 2)
    return m, infos


def legende_polygone(p: dict, l_dispo: float, w_dispo: float, image: bytes | None = None):
    """Texte (police) ou logo -> polygone 2D centre, a l'echelle de la place disponible."""
    if p.get("type_legende") == "logo" and image:
        from .image2d import image_vers_polygone
        poly, _ = image_vers_polygone(image, 30.0, p.get("seuil"), p.get("inverser"), detail_min_mm=0.35)
    else:
        from .porte_cles import Style, prenom_polygone
        txt = str(p.get("texte", "A"))
        poly, _ = prenom_polygone(txt, Style(police=p.get("police", "arial_black"), hauteur=10.0))
    b = poly.bounds
    poly = affinity.translate(poly, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
    pw, ph = b[2] - b[0], b[3] - b[1]
    taille = float(p.get("taille_legende", 0.55))              # fraction de la place
    k = min(l_dispo * taille / max(pw, 1e-6), w_dispo * taille / max(ph, 1e-6))
    poly = affinity.scale(poly, k, k, origin=(0, 0))
    poly = affinity.rotate(poly, float(p.get("rotation", 0)), origin=(0, 0))
    return affinity.translate(poly, float(p.get("dx", 0)), float(p.get("dy", 0)))


def keycap_complet(p: dict, image: bytes | None = None):
    """Touche + legende. -> (liste de (maillage, role)), infos. role : 'touche' | 'legende'."""
    from .c3d import extruder
    m, info = keycap(p)
    lt0, wt0 = info["haut_mm"]
    dech = float(p.get("decal_haut", 0) or 0)
    # tiges a ne jamais percer (et stabilisateurs)
    proteger = [(0.0, 0.0, 2.95)] + [(x, 0.0, 2.95) for x in info["stabilisateurs"]]   # tige MX d5.5 + 0.2
    z_int = info["z_dessus"] - info["creux"] - float(p.get("paroi", 1.3) or 1.3) - 1.2
    # ---- texture du dessus (meme moteur que Creation 3D)
    if p.get("texture"):
        from .motifs import effet_surface
        m = effet_surface(m, {"motif": p["texture"], "profondeur": float(p.get("texture_prof", 0.35)),
                              "taille": float(p.get("texture_taille", 2.5)), "rotation": float(p.get("texture_rot", 0)),
                              "trait": float(p.get("texture_trait", 0.08)), "zones": "dessus", "projection": "z",
                              "fondu": 0, "max_faces": 400_000})
    # ---- ajourage du dessus (motif traversant : diffuseur RGB)
    if p.get("ajour"):
        from .motifs import ajourer
        m = ajourer(m, {"motif": p["ajour"], "axe": "z", "taille": float(p.get("ajour_taille", 3.0)),
                        "trait": float(p.get("ajour_trait", 0.15)), "rotation": float(p.get("ajour_rot", 0)),
                        "zone_xy": (-lt0 / 2 + 1.2, lt0 / 2 - 1.2, dech - wt0 / 2 + 1.2, dech + wt0 / 2 - 1.2),
                        "zone_z": (z_int, info["z_dessus"] + 5), "proteger": proteger, "paroi_min": 0.6})
        info["ajour"] = p["ajour"]
    leg = p.get("type_legende", "aucune")
    if leg in ("texte", "logo") and (p.get("texte") or image):
        lt, wt = info["haut_mm"]
        poly = legende_polygone(p, lt - 1.5, wt - 1.5, image)
        mode = p.get("mode_legende", "graver")
        prof = float(p.get("profondeur_legende", 0.6))
        face = p.get("face", "dessus")
        if mode in ("percer", "translucide") and face == "dessus":
            # legende TRAVERSANTE (shine-through RGB) : le trou traverse le dessus ; la tige reste intacte
            import manifold3d as mf
            from .c3d import vers_manifold as vm, vers_trimesh as vt, section as sec
            from shapely.geometry import Point
            from shapely.ops import unary_union
            pp = poly
            for (x, y, r) in proteger:
                pp = pp.difference(Point(x, y).buffer(r + 0.3))
            pp = affinity.translate(pp, 0, dech)
            haut = info["z_dessus"] + 6
            jeu = float(p.get("jeu_legende", 0.08)) if mode == "translucide" else 0
            trou = mf.Manifold.extrude(sec(pp.buffer(jeu, join_style=1) if jeu else pp), haut - z_int).translate((0, 0, z_int))
            B = vm(m)
            touche = vt(B - trou)
            if mode == "percer":
                return [(touche, "touche")], info
            insert = mf.Manifold.extrude(sec(pp), haut - z_int).translate((0, 0, z_int)) ^ B
            return [(touche, "touche"), (vt(insert), "legende")], info
        if face == "dessus":
            z = info["z_dessus"] + 3
            motif = extruder(poly, 1.2 if mode != "relief" else prof + 0.3, 0)
            motif.apply_translation([0, float(p.get("decal_haut", 0)), z])
            point, n = [float(p.get("dx", 0)), float(p.get("decal_haut", 0)) + float(p.get("dy", 0)), info["z_dessus"]], [0, 0, 1]
        else:   # face avant (texte lisible de face, "side-printed")
            motif = extruder(poly, 1.2, 0)
            import trimesh as _t
            R = _t.geometry.align_vectors([0, 0, 1], [0, -1, 0])
            motif.apply_transform(R)
            W = info["dimensions_mm"][1]
            zc = info["z_dessus"] * 0.45
            motif.apply_translation([0, -W / 2 - 3, zc])
            point, n = [0, -W / 2, zc], [0, -1, 0]
        if mode == "incruster":
            # jeu fait en 2D (rapide et exact) : logement = legende elargie de `jeu`, piece = legende exacte
            from .c3d import epouser, vers_manifold as vm, vers_trimesh as vt
            jeu = float(p.get("jeu_legende", 0.08))
            def pose(pl):
                mm_ = extruder(pl, 1.2, 0)
                if face != "dessus":
                    import trimesh as _t
                    mm_.apply_transform(_t.geometry.align_vectors([0, 0, 1], [0, -1, 0]))
                    mm_.apply_translation([0, -info["dimensions_mm"][1] / 2 - 3, info["z_dessus"] * 0.45])
                else:
                    mm_.apply_translation([0, float(p.get("decal_haut", 0)), info["z_dessus"] + 3])
                return epouser(mm_, m, point, n, enfoncement=prof)
            A, L_, B = vm(pose(poly)), vm(pose(poly.buffer(jeu, join_style=1))), vm(m)
            res = [vt(B - L_), vt(A ^ B)]
        else:
            res = integrer(motif, m, mode, prof, point, n, True)
        roles = {"relief": ["touche"], "graver": ["touche"], "incruster": ["touche", "legende"], "coller": ["touche", "legende"]}[mode]
        return list(zip(res, roles)), info
    return [(m, "touche")], info
