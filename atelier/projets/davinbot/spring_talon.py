"""Compensation de gravite de J2 - architecture « talon » (type KUKA A2), longueur libre nulle.

* A : ancrage fixe du cable sur une POTENCE de la tourelle, SOUS l'axe J2 (profondeur h),
  dans le plan median du bras ;
* B : renvoi entre 2 galets (623ZZ) sur un TALON du bras, SOUS l'axe J2 (rayon r) ;
* le cable remonte DANS le bras creux : moufle mobile (palan 2:1) + ressort de traction ancre
  en haut du bras sur une goupille acier d5.

Couple de rappel = k.h.r.sin(theta) : exactement la loi de la gravite (A et B sous l'axe, les deux
signes s'annulent). Tout le mecanisme reste SOUS l'axe J2 ou A L'INTERIEUR du bras : rien ne monte
dans l'espace balaye par le coude et l'avant-bras (l'ancien mat de 180 mm y etait percute).

Energie : compenser ~26 N.m sur +-110 deg demande ~35 J stockes -> un VRAI ressort (fil 5-6 mm),
choisi par le calcul (raideur G.d^4/8D^3n, cisaillement de Wahl <= 0.38 Rm, tenue en fatigue).
"""
from __future__ import annotations

import math

import numpy as np

from .cad.util import SCREW, box, cyl, cut_all, fuse_all
from .parts.model import Part


def _y_axis_cyl(d, L, x, y0, z):
    """Cylindre d'axe Y (diametre d, longueur L) partant de y0."""
    return cyl(d, L, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, y0, z))


def _x_axis_cyl(d, L, x0, y, z):
    return cyl(d, L, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((x0, y, z))


def layout(cfg, tur, arm, T2, z2):
    o2 = T2[:3, 3]
    ax = T2[:3, 2]
    if abs(abs(ax[1]) - 1) > 1e-6:
        raise ValueError("architecture talon : axe J2 attendu selon Y")
    tol = cfg["tol"]
    h, r = cfg["j2_spring_h"], cfg["j2_spring_r"]
    y_pl = round((arm.y0 + arm.y1) / 2, 2)             # plan du cable = plan median du bras
    x_c = 10.0                                         # brin entrant (galets -> moufle)
    x_s = 15.0                                         # axe du ressort et de la moufle
    A = np.array([0.0, y_pl, z2 - h])
    B = np.array([x_c, y_pl, z2 - r])                  # point de renvoi (entre les 2 galets)
    z_floor = arm.z0
    parts = []

    # ------------------------------------------------------------ talon (sur le bras, corps 2)
    zt0 = B[2] - 13.0
    tal = box(x_c - 24, x_c + 24, y_pl - 14, y_pl + 14, zt0, z_floor)
    galets = [(x_c - 5.75, B[2]), (x_c + 5.75, B[2])]
    tcut = [box(x_c - 12.5, x_c + 12.5, y_pl - 2.6, y_pl + 2.6, zt0 - 1, B[2] + 6),          # gorge des galets
            box(x_c - 26, x_c + 26, y_pl - 2.6, y_pl + 2.6, zt0 - 1, B[2] - 5.5)]             # entree evasee
    for gx, gz in galets:
        tcut.append(_y_axis_cyl(3.0 + tol, 40, gx, y_pl - 20, gz))                           # axes acier d3
    tcut.append(cyl(4.0, z_floor - B[2] + 2, B[2], x_c, y_pl))                               # brin montant
    z_anc = zt0 + 22.0                                                                        # point fixe du palan
    tcut.append(cyl(4.0, z_floor - z_anc + 2, z_anc, x_s + 5, y_pl))                           # brin de retour
    tcut.append(_y_axis_cyl(3.0 + tol, 40, x_s + 5, y_pl - 20, z_anc))                        # goupille du point fixe
    bolts = [(x_c - 18, y_pl - 8), (x_c - 18, y_pl + 8), (x_c + 18, y_pl - 8), (x_c + 18, y_pl + 8)]
    tcut += [cyl(SCREW["M4"]["clear"], z_floor - zt0 + 20, zt0 - 5, x, y) for x, y in bolts]
    tcut += [cyl(SCREW["M4"]["head"] + 0.6, 10, zt0 - 4, x, y) for x, y in bolts]            # lamages dessous
    parts.append(Part(id="RESSORT_talon", name="Compensation J2 - talon du bras (2 galets de renvoi)",
                      group="RESSORT", body=2, shape=cut_all(tal, tcut), category="structure",
                      print_up=(0, 1, 0),
                      notes="PA-CF ou PETG 100 %. 4 x M4 dans ecrous noyes du fond du bras ; galets = "
                            "roulements 623ZZ sur axes acier d3 ; point fixe du palan sur goupille acier d3."))
    for i, (gx, gz) in enumerate(galets):
        parts.append(Part(id=f"RESSORT_galet_{i + 1}", name=f"Compensation J2 - galet {i + 1} (623ZZ)",
                          group="RESSORT", body=2, kind="vitamin", category="bearing",
                          shape=cut_all(_y_axis_cyl(10.0, 4.0, gx, y_pl - 2.0, gz),
                                        [_y_axis_cyl(3.0, 6.0, gx, y_pl - 3.0, gz)])))
    arm.extra_cut += [cyl(5.0, 24, z_floor - 12, x_c, y_pl), cyl(5.0, 24, z_floor - 12, x_s + 5, y_pl)]
    arm.extra_cut += [cyl(SCREW["M4"]["clear"], 24, z_floor - 12, x, y) for x, y in bolts]

    # ------------------------------------------------------------ potence en TOLE ACIER (tourelle, corps 1)
    # L'analyse structurelle donne 33 MPa dans une potence imprimee (PETG : 12 admissibles) sur TOUT
    # le chemin d'effort (poutre -> coude -> montant -> semelle). Piece metal a commander : tole S235
    # 3 mm decoupee laser + pliee en profils U (JLCCNC ou equivalent), boulonnee sur la tourelle.
    if cfg.get("j2_potence_tole", True):
        parts.append(_potence_tole(cfg, tur, A, y_pl))
        parts.append(Part(id="RESSORT_goupille_A", name="Compensation J2 - goupille acier d5 (ancrage A)",
                          group="RESSORT", body=1, kind="vitamin", category="hardware",
                          shape=_x_axis_cyl(5.0, 28.0, -14.0, y_pl, A[2])))
        return {"A": A, "B": B, "o": o2, "axis": ax, "y_pl": y_pl, "x_s": x_s, "x_c": x_c,
                "z_floor": z_floor, "z_anc": z_anc, "tol": tol, "potence": "tole"}, parts
    # ------------------------------------------------------------ (variante imprimee, pour memoire)
    zp1 = min(tur.z1, 196.0)                           # sous la flasque du reducteur J2
    y_face = tur.y1
    t = 10.0                                           # epaisseur (X) des ames
    # le montant descend a y >= 58 : hors du carter FIXE de J1 (r <= 55 jusqu'a z = 152)
    y_m = 58.0
    z_con = 156.0                                      # console horizontale au-dessus du carter J1
    pot = fuse_all([
        box(-20, 20, y_face, y_face + 8, z_con, zp1),                                        # semelle vissee
        box(-t, t, y_face, y_m + 12, z_con, zp1),                                            # console
        box(-t, t, y_m, y_m + 12, A[2] - 12, zp1),                                           # montant
        box(-t, t, y_m, y_pl + 14, A[2] - 12, A[2] + 12),                                    # poutre vers A
    ])
    # gousset : triangle plein entre montant et poutre
    import cadquery as cq
    hg = min(z_con - (A[2] + 12), 60.0)
    gus = (cq.Workplane("YZ").polyline([(y_m + 12, A[2] + 12), (y_m + 12, A[2] + 12 + hg),
                                        (y_m + 12 + hg, A[2] + 12)])
           .close().extrude(2 * t).translate((-t, 0, 0)))
    pot = fuse_all([pot, gus])
    pcut = [_y_axis_cyl(SCREW["M4"]["clear"], 30, sx * 13, y_face - 10, zz)
            for sx in (-1, 1) for zz in (zp1 - 9, zp1 - 25)]
    pcut.append(_x_axis_cyl(5.0 + tol, 40, -20, y_pl, A[2]))                                 # goupille d'ancrage A
    pcut.append(box(-t - 1, t + 1, y_pl - 2.6, y_pl + 2.6, A[2] - 4, A[2] + 13))              # gorge du cable
    parts.append(Part(id="RESSORT_potence", name="Compensation J2 - potence d'ancrage A (tourelle)",
                      group="RESSORT", body=1, shape=cut_all(pot, pcut), category="structure",
                      print_up=(1, 0, 0),
                      notes="Voir analyse structurelle : PA-CF, ou tole acier si le coefficient est insuffisant. "
                            "4 x M4 dans inserts de la tourelle ; ancrage A = goupille acier d5."))
    parts.append(Part(id="RESSORT_goupille_A", name="Compensation J2 - goupille acier d5 (ancrage A)",
                      group="RESSORT", body=1, kind="vitamin", category="hardware",
                      shape=_x_axis_cyl(5.0, 2 * t + 4, -t - 2, y_pl, A[2])))
    return {"A": A, "B": B, "o": o2, "axis": ax, "y_pl": y_pl, "x_s": x_s, "x_c": x_c,
            "z_floor": z_floor, "z_anc": z_anc, "tol": tol}, parts


def design_spring(Tmax, Tmin, k_eq, room_mm, od_max=58.0, ratio=2):
    """Ressort de traction reel (fil EN 10270-1 SH) pour un palan ratio:1 : le plus LEGER qui tient."""
    G = 79_000.0
    k_s = ratio ** 2 * k_eq
    F_max, F_min = ratio * Tmax, ratio * Tmin
    best = None
    for d in (3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0):
        Rm = 2230.0 - 620.0 * math.log10(d)             # MPa (ordre de grandeur fil SH)
        for idx in (6, 7, 8, 9, 10, 11, 12):
            D = idx * d
            Kw = (4 * idx - 1) / (4 * idx - 4) + 0.615 / idx
            tau = 8 * F_max * D * Kw / (math.pi * d ** 3)
            if tau > 0.38 * Rm:                         # fatigue (cycles repetes), pas seulement statique
                continue
            n = G * d ** 4 / (8 * D ** 3 * k_s)
            if n < 3:
                continue
            L0 = (n + 1) * d + 2 * 0.6 * D
            ext_max = F_max / k_s
            if L0 + ext_max > room_mm or D + d > od_max:
                continue
            mass = math.pi * D * (n + 3) * math.pi * d ** 2 / 4 * 7.85e-3
            if best is None or mass < best["masse_g"]:
                best = {"d_mm": d, "D_mm": round(D, 1), "spires": round(n, 1), "L0_mm": round(L0, 1),
                        "allongement_min_mm": round(F_min / k_s, 1), "allongement_max_mm": round(ext_max, 1),
                        "longueur_max_mm": round(L0 + ext_max, 1), "k_N_mm": round(k_s, 2),
                        "F_max_N": round(F_max), "tau_MPa": round(tau), "tau_admissible_MPa": round(0.38 * Rm),
                        "masse_g": round(mass)}
    return best


def spring_parts(sp, design, z_pin, arm):
    """Ressort + moufle + goupille haute, places en pose zero selon le ressort retenu."""
    x_s, y_pl, tol = sp["x_s"], sp["y_pl"], sp["tol"]
    D, d = design["D_mm"], design["d_mm"]
    L_pose0 = design["L0_mm"] + design["allongement_pose0_mm"]
    z_low = z_pin - L_pose0                           # crochet bas du ressort
    loop = 0.6 * D
    parts = []
    spring = fuse_all([cyl(D + d, L_pose0 - 2 * loop, z_low + loop, x_s, y_pl),
                       _x_axis_cyl(d + 1, loop, x_s - (d + 1) / 2, y_pl, z_low + loop / 2).translate((0, 0, 0))])
    parts.append(Part(id="RESSORT_ressort", name=f"Compensation J2 - ressort de traction fil d{d:g} D{D:g} "
                                                 f"{design['spires']} spires", group="RESSORT", body=2,
                      kind="vitamin", category="hardware", shape=spring))
    zb = z_low - 22.0
    blk = box(x_s - 9, x_s + 9, y_pl - 7, y_pl + 7, zb, zb + 22)
    blk = cut_all(blk, [box(x_s - 6.5, x_s + 6.5, y_pl - 2.6, y_pl + 2.6, zb - 1, zb + 12),
                        _y_axis_cyl(3.0 + tol, 30, x_s, y_pl - 15, zb + 6),
                        _x_axis_cyl(d + 1.5, 30, x_s - 15, y_pl, zb + 16)])
    parts.append(Part(id="RESSORT_moufle", name="Compensation J2 - moufle mobile (palan 2:1)", group="RESSORT",
                      body=2, shape=blk, category="structure", print_up=(0, 1, 0),
                      notes="PA-CF 100 % ; poulie 623ZZ sur axe acier d3 ; crochet bas du ressort dans l'oeil."))
    parts.append(Part(id="RESSORT_poulie_moufle", name="Compensation J2 - poulie de moufle (623ZZ)",
                      group="RESSORT", body=2, kind="vitamin", category="bearing",
                      shape=_y_axis_cyl(10.0, 4.0, x_s, y_pl - 2.0, zb + 6)))
    parts.append(Part(id="RESSORT_goupille_haut", name="Compensation J2 - goupille acier d8 (crochet haut)",
                      group="RESSORT", body=2, kind="vitamin", category="hardware",
                      shape=_y_axis_cyl(8.0, arm.y1 - arm.y0, x_s, arm.y0, z_pin)))
    return parts


def _potence_tole(cfg, tur, A, y_pl, e=3.0, w=24.0, hf=29.0):
    """Potence en tole acier e mm : semelle vissee sur la face +Y de la tourelle, puis profils U
    (console horizontale -> montant -> poutre) jusqu'a l'ancrage A. Axe de A = goupille d5 traversant
    les deux ailes ; le cable passe entre les ailes."""
    y_face = tur.y1
    z_con = 163.0                     # au-dessus de la bride de sortie J1 (z <= 162)
    z_top = min(tur.z1, 196.0)        # sous la flasque du reducteur J2
    y_m = 58.0                        # montant hors du carter fixe de J1 (r <= 55)
    zb0, zb1 = A[2] - hf / 2, A[2] + hf / 2
    x0, x1 = -w / 2, w / 2
    segs = [
        box(-20, 20, y_face, y_face + e, z_con, z_top),                               # semelle
        # console : U ouvert vers le bas (ame en haut)
        box(x0, x1, y_face, y_m + 12, z_top - e, z_top),
        box(x0, x0 + e, y_face, y_m + 12, z_con, z_top), box(x1 - e, x1, y_face, y_m + 12, z_con, z_top),
        # montant : U ouvert vers la tourelle (ame cote +Y)
        box(x0, x1, y_m + 12 - e, y_m + 12, zb0, z_top),
        box(x0, x0 + e, y_m, y_m + 12, zb0, z_top), box(x1 - e, x1, y_m, y_m + 12, zb0, z_top),
        # poutre : U ouvert vers le haut (ame en bas), jusqu'a A
        box(x0, x1, y_m, y_pl + 14, zb0, zb0 + e),
        box(x0, x0 + e, y_m, y_pl + 14, zb0, zb1), box(x1 - e, x1, y_m, y_pl + 14, zb0, zb1),
    ]
    sh = fuse_all(segs)
    cuts = [_y_axis_cyl(SCREW["M4"]["clear"], 20, sx * 13, y_face - 8, zz)
            for sx in (-1, 1) for zz in (z_top - 9, z_con + 8)]
    cuts.append(_x_axis_cyl(5.0 + cfg["tol"], 40, -20, y_pl, A[2]))                  # goupille de A
    return Part(id="RESSORT_potence", name="Compensation J2 - potence tole acier 3 mm (ancrage A)",
                group="RESSORT", body=1, shape=cut_all(sh, cuts), kind="metal", category="structure",
                material="Acier S235 3 mm",
                notes="PIECE METAL A COMMANDER : tole S235 (ou inox 304) 3 mm, decoupe laser + pliage en U "
                      "(JLCCNC tolerie ou equivalent) ; les 3 profils U sont soit plies d'une piece avec 2 "
                      "cordons de soudure aux angles, soit 2 pieces pliees boulonnees (M4). 4 x M4 dans "
                      "inserts de la tourelle. STEP fourni.",
                meta={"section_U": {"e": e, "w": w, "hf": hf}, "porte_a_faux_mm": round(y_pl - y_m, 1)})
