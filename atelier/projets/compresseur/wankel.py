"""COMPRESSEUR WANKEL (moteur rotatif utilise en compresseur), parametrique et imprimable.

Geometrie exacte :
  * stator = EPITROCHOIDE a 2 lobes : P(a) = e (cos 3a, sin 3a) + R (cos a, sin a) ;
  * rotor  = ENVELOPPE INTERIEURE : intersection, sur un tour, du stator vu depuis le repere du rotor
             (le rotor tourne a 1/3 de la vitesse de l'arbre excentrique), moins le jeu ;
  * phasage = engrenage INTERIEUR du rotor (Zr) sur pignon FIXE (Zs = 2/3 Zr), excentricite e = m (Zr - Zs) / 2.
Le jeu est verifie par simulation (rotor dans le stator a chaque angle).

Variantes :
  * "perceuse" : axe acier d8 qui depasse (mandrin de perceuse), 2 roulements 608 ;
  * "compact"  : petite cylindree + moteur 130 / 180 et reduction a engrenages integres (RC 1:10).
Etancheite : segments d'apex (bande TPU / caoutchouc dans une rainure), joints de flasques (cordon de joint
torique dans une gorge), clapet a lamelle sur la sortie.
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as mf
from shapely.geometry import Polygon, Point, box as sbox
from shapely import affinity
from shapely.ops import unary_union

from atelier.noyau.c3d import section, vers_trimesh
from atelier.meca import profil_engrenage, ROULEMENTS


def stator_profil(e, R, n=720):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return Polygon(np.c_[e * np.cos(3 * a) + R * np.cos(a), e * np.sin(3 * a) + R * np.sin(a)])


def rotor_profil(e, R, jeu=0.15, pas=240):
    """Enveloppe interieure exacte : intersection du stator vu depuis le rotor sur un tour d'arbre complet."""
    stator = stator_profil(e, R)
    rot = None
    for k in range(pas):
        phi = 2 * np.pi * k / pas / 3 * 3          # angle du rotor (1/3 de l'arbre) ; 3 tours d'arbre = 1 tour de rotor
        phi = 2 * np.pi * k / pas
        c = (e * math.cos(3 * phi), e * math.sin(3 * phi))
        vu = affinity.rotate(affinity.translate(stator, -c[0], -c[1]), -phi, origin=(0, 0), use_radians=True)
        rot = vu if rot is None else rot.intersection(vu)
    return rot.buffer(-jeu, join_style=1).simplify(0.01)


def verifier(e, R, rotor, n=90):
    """Surface du rotor qui sortirait du stator, au pire angle (doit etre ~0)."""
    stator = stator_profil(e, R)
    pire = 0.0
    for k in range(n):
        phi = 2 * np.pi * k / n
        c = (e * math.cos(3 * phi), e * math.sin(3 * phi))
        r_ = affinity.translate(affinity.rotate(rotor, phi, origin=(0, 0), use_radians=True), c[0], c[1])
        pire = max(pire, r_.difference(stator).area)
    return pire


def cylindree(e, R, b):
    """Volume balaye par chambre (cm3) : V = 3 sqrt(3) e R b (formule Wankel)."""
    return 3 * math.sqrt(3) * e * R * b / 1000


def compresseur(p: dict):
    """Compresseur Wankel 100 % IMPRIME (seuls des joints toriques caoutchouc sont ajoutes) :
    paliers lisses graissables, arbre excentrique d'une piece (hexagone de 10 pour le mandrin), tirants M8 et
    ecrous imprimes, segments d'apex et joints de flasques decoupes dans des joints toriques, 4 lumieres aux angles
    optimises par simulation, embouts pour tube LEGO / tube d8 / cannele / taraudage."""
    from atelier.meca import orifice as _orif, _place
    from atelier.noyau.c3d import filetage
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    version = p.get("version", "perceuse")
    compact = version == "compact"
    m = g("module", 1.0 if not compact else 0.8)
    Zr = int(g("dents_rotor", 30 if not compact else 24))
    Zr -= Zr % 3
    Zs = Zr * 2 // 3
    e = m * (Zr - Zs) / 2
    K = g("rapport_K", 7.0)
    R = K * e
    b = g("largeur", 16 if not compact else 10)
    jeu, jeu_flanc = g("jeu", 0.15), g("jeu_flanc", 0.2)
    paroi = g("paroi", 6.0)
    cord = g("cordon", 2.0)                              # tore des joints toriques disponibles
    j_pal = g("jeu_palier", 0.25)                         # jeu diametral des paliers lisses imprimes
    port = p.get("orifice", "lego")
    # ---------------------------------------------------------------- arbre : tourillon, excentrique, hexagone
    d_tour = g("tourillon", 12.0 if not compact else 8.0)
    d_exc = d_tour + 2 * e + 4.0                          # l'excentrique englobe le tourillon (arbre d'une piece)
    hexa = g("hexagone", 10.0 if not compact else 6.0)
    # ---------------------------------------------------------------- profils
    stator = stator_profil(e, R)
    rotor2d = rotor_profil(e, R, jeu)
    fuite = verifier(e, R, rotor2d)
    r_ext = R + e + paroi
    a_vis = [math.pi / 4 + k * math.pi / 2 for k in range(4)]
    r_vis = r_ext - 5.0
    visserie = p.get("visserie", "placo")              # placo | imprimee | m3
    imprimer_vis = int(g("imprimer_visserie", 1))
    r_passage = {"placo": 2.0, "imprimee": 4.3, "m3": 1.7}.get(visserie, 2.0)
    r_avant_trou = {"placo": 1.4, "imprimee": 4.3, "m3": 1.7}.get(visserie, 2.0)   # placo : la vis taraude le flasque arriere
    trous_vis = [Point(r_vis * math.cos(a), r_vis * math.sin(a)).buffer(r_passage, 32) for a in a_vis]
    trous_ar = [Point(r_vis * math.cos(a), r_vis * math.sin(a)).buffer(r_avant_trou, 32) for a in a_vis]
    exterieur = Point(0, 0).buffer(r_ext, 96)
    for a in a_vis:                                      # oreilles des tirants
        exterieur = exterieur.union(Point(r_vis * math.cos(a), r_vis * math.sin(a)).buffer(8.0, 32))
    h_st = b + 2 * jeu_flanc
    # ---------------------------------------------------------------- STATOR + 4 lumieres (2 admissions, 2 refoulements)
    stator_s = mf.Manifold.extrude(section(exterieur.difference(stator).difference(unary_union(trous_vis))), h_st)
    a_adm, a_ref = g("angle_admission", 205), g("angle_refoulement", 86)
    lumieres = [(a_adm, "admission"), (a_adm + 180, "admission"), (a_ref, "refoulement"), (a_ref + 180, "refoulement")]
    d_lum = min(5.0, b * 0.45)
    for ang, nom in lumieres:
        a = math.radians(ang)
        dirv = np.array([math.cos(a), math.sin(a), 0.0])
        # rayon du stator dans cette direction (point de l'epitrochoide le plus proche en angle)
        pts = np.asarray(stator.exterior.coords)
        k = np.argmin(np.abs(((np.arctan2(pts[:, 1], pts[:, 0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        r_s = float(np.hypot(*pts[k]))
        canal = mf.Manifold.cylinder(r_ext - r_s + 2, d_lum / 2, d_lum / 2, 32).translate((0, 0, -1))
        stator_s = stator_s - _place(canal, np.array([r_s * math.cos(a), r_s * math.sin(a), h_st / 2]), dirv)
        b_, v_ = _orif(port, g("tube", 4.0 if port != "tube8" else 8.0), min(d_lum, 3.0 if port != "tube8" else 5.0))
        pos = np.array([(r_ext - 1.0) * math.cos(a), (r_ext - 1.0) * math.sin(a), h_st / 2])
        if h_st / 2 > 0:
            stator_s = (stator_s + _place(b_, pos, dirv)) - _place(v_, pos, dirv)
    # ---------------------------------------------------------------- ROTOR
    rot = mf.Manifold.extrude(section(rotor2d), b)
    pts = np.asarray(rotor2d.exterior.coords)
    d = np.hypot(pts[:, 0], pts[:, 1])
    ang = np.arctan2(pts[:, 1], pts[:, 0])
    for k in range(3):                                   # rainures d'apex pour segment en cordon de joint torique
        a0 = 2 * math.pi * k / 3
        msk = np.abs(((ang - a0 + math.pi) % (2 * math.pi)) - math.pi) < 0.6
        i = np.argmax(np.where(msk, d, -1))
        sx, sy = pts[i]
        prof_r = cord * 0.78
        rainure = mf.Manifold.cylinder(b + 2, cord * 0.525, cord * 0.525, 24).translate((math.hypot(sx, sy) - prof_r + cord * 0.5, 0, -1))
        rainure = rainure + mf.Manifold.cube((cord * 1.05, cord * 0.6, b + 2), True).translate((math.hypot(sx, sy) - prof_r + cord * 0.5 + cord * 0.3, 0, b / 2))
        rot = rot - rainure.rotate((0, 0, math.degrees(math.atan2(sy, sx))))
    cour_prof, _ = profil_engrenage(m, Zr, 20, -0.12)
    prof_eng = g("prof_engrenage", 5.0 if not compact else 3.5)
    rot = rot - mf.Manifold.extrude(section(cour_prof), prof_eng + 0.01).translate((0, 0, -0.01))
    # palier lisse du rotor sur l'excentrique + rainure de graissage en helice (2 tours) + reserve de graisse
    alesage = d_exc + j_pal
    rot = rot - mf.Manifold.cylinder(b + 2, alesage / 2, alesage / 2, 128).translate((0, 0, prof_eng - 0.01))
    sill = mf.Manifold.extrude(section(Point(alesage / 2, 0).buffer(0.9, 16)), b - prof_eng - 1, 64, 720).translate((0, 0, prof_eng + 0.5))
    rot = rot - sill
    # ---------------------------------------------------------------- FLASQUES : paliers lisses graissables, pignon fixe, joint de face
    e_fl = g("epaisseur_flasque", 8.0)
    fl = mf.Manifold.extrude(section(exterieur.difference(unary_union(trous_vis))), e_fl)
    fl_ar_brut = mf.Manifold.extrude(section(exterieur.difference(unary_union(trous_ar))), e_fl)
    r_g = R + e + 1.6 + cord * 0.6
    gorge = mf.Manifold.extrude(section(Point(0, 0).buffer(r_g + cord * 0.55, 128).difference(Point(0, 0).buffer(r_g - cord * 0.55, 128))), cord * 0.75).translate((0, 0, e_fl - cord * 0.75))
    def palier(sol, z_ext_sign):
        sol = sol - mf.Manifold.cylinder(e_fl + 2, (d_tour + j_pal) / 2, (d_tour + j_pal) / 2, 96).translate((0, 0, -1))
        # rainure annulaire de graisse au milieu du palier + canal radial vers un graisseur (bossage avec bouchon)
        sol = sol - (mf.Manifold.cylinder(2.0, d_tour / 2 + 1.0, d_tour / 2 + 1.0, 64) - mf.Manifold.cylinder(2.0, d_tour / 2 - 1, d_tour / 2 - 1, 64)).translate((0, 0, e_fl / 2 - 1.0))
        canal = mf.Manifold.cylinder(r_ext + 2, 1.0, 1.0, 16).rotate((0, 90, 0)).rotate((0, 0, 180)).translate((0, 0, e_fl / 2))
        sol = sol - canal
        bos = mf.Manifold.cylinder(6, 4.0, 4.0, 32).rotate((0, 90, 0)).translate((-(r_ext + 4.0), 0, e_fl / 2))
        sol = sol + bos - mf.Manifold.cylinder(9, 1.0, 1.0, 16).rotate((0, 90, 0)).translate((-(r_ext + 6), 0, e_fl / 2)) \
                  - mf.Manifold.cylinder(4, 2.1, 2.1, 24).rotate((0, 90, 0)).translate((-(r_ext + 6.5), 0, e_fl / 2))
        return sol
    fl_av = palier(fl - gorge, 1)
    for a in a_vis:                                       # tetes noyees cote exterieur (face z = 0)
        x, y = r_vis * math.cos(a), r_vis * math.sin(a)
        if visserie == "placo":
            fl_av = fl_av - mf.Manifold.cylinder(2.4, 4.4, 2.0, 32).translate((x, y, -0.01))          # tete trompette ~8.5
        elif visserie == "m3":
            fl_av = fl_av - mf.Manifold.cylinder(3.2, 3.1, 3.1, 32).translate((x, y, -0.01))          # tete cylindrique M3
    pig, _ = profil_engrenage(m, Zs, 20, 0.0)
    fl_av = fl_av + mf.Manifold.extrude(section(pig.difference(Point(0, 0).buffer((d_tour + j_pal) / 2, 64))), prof_eng - 0.4).translate((0, 0, e_fl))
    fl_ar = palier(fl_ar_brut - gorge, -1)
    if visserie == "m3":                                  # ecrous M3 noyes (6 pans) sur la face exterieure du flasque arriere
        for a in a_vis:
            x, y = r_vis * math.cos(a), r_vis * math.sin(a)
            fl_ar = fl_ar - mf.Manifold.extrude(section(Polygon([(x + 3.25 * math.cos(math.pi / 3 * k), y + 3.25 * math.sin(math.pi / 3 * k)) for k in range(6)])), 2.6).translate((0, 0, -0.01))
    bouchon = mf.Manifold.cylinder(3.5, 2.0, 2.0, 24) + mf.Manifold.cylinder(1.5, 3.2, 3.2, 24).translate((0, 0, 3.5))   # graisseur (bouchon serre)
    # ---------------------------------------------------------------- ARBRE EXCENTRIQUE d'une piece
    # arbre DROIT imprime debout : tourillon arriere | hexagone (porte l'excentrique) | tourillon avant | hexagone mandrin
    # (l'hexagone, plus petit que le tourillon, passe dans les paliers : aucun porte-a-faux a l'impression)
    hex_pts = lambda s_: Polygon([(s_ / math.sqrt(3) * math.cos(math.pi / 3 * k), s_ / math.sqrt(3) * math.sin(math.pi / 3 * k)) for k in range(6)])
    h_mil = min(hexa, d_tour * 0.85)                      # sur plats ; sur angles = 1.155 x < tourillon
    L_ar, L_av = e_fl + 1.0, e_fl + 1.0
    L_hex = g("longueur_hexagone", 30.0 if not compact else 0.0)
    arbre = mf.Manifold.cylinder(L_ar, d_tour / 2, d_tour / 2, 96)
    arbre = arbre + mf.Manifold.extrude(section(hex_pts(h_mil)), h_st).translate((0, 0, L_ar))       # exactement entre les flasques
    arbre = arbre + mf.Manifold.cylinder(L_av, d_tour / 2, d_tour / 2, 96).translate((0, 0, L_ar + h_st))
    if L_hex > 0:
        arbre = arbre + mf.Manifold.extrude(section(hex_pts(hexa)), L_hex).translate((0, 0, L_ar + h_st + L_av))
    # EXCENTRIQUE separe, imprime a plat : disque d_exc, trou hexagonal decale de e, rainure de graisse
    e_exc = b - prof_eng - 0.8                           # l'excentrique est A COTE du pignon fixe (au niveau du palier du rotor)
    exc = mf.Manifold.cylinder(e_exc, d_exc / 2, d_exc / 2, 128) - mf.Manifold.extrude(section(hex_pts(h_mil + 0.25)), b + 2).translate((-e, 0, -1))
    exc = exc - mf.Manifold.extrude(section(Point(d_exc / 2, 0).buffer(0.8, 12)), b + 2).translate((0, 0, -1))   # reserve de graisse axiale
    # ---------------------------------------------------------------- TIRANTS M8 + ECROUS (imprimes)
    L_tir = 2 * e_fl + h_st + 14
    tirant = filetage(8.0, L_tir, 1.25).translate((0, 0, 4)) + mf.Manifold.extrude(section(Polygon([(13 / math.sqrt(3) * math.cos(math.pi / 3 * k + math.pi / 6), 13 / math.sqrt(3) * math.sin(math.pi / 3 * k + math.pi / 6)) for k in range(6)])), 4)
    ecrou = mf.Manifold.extrude(section(Polygon([(13 / math.sqrt(3) * math.cos(math.pi / 3 * k + math.pi / 6), 13 / math.sqrt(3) * math.sin(math.pi / 3 * k + math.pi / 6)) for k in range(6)])), 6.5) \
        - filetage(8.0, 8.5, 1.25, jeu=0.3, interne=True).translate((0, 0, -1))
    # ---------------------------------------------------------------- CLAPETS a lamelle (2 refoulements) : siege + lamelle + goujon
    siege = mf.Manifold.cylinder(4, 9, 9, 64) - mf.Manifold.cylinder(6, 2.0, 2.0, 32).translate((0, 0, -1))
    siege = siege + mf.Manifold.cylinder(3.0, 1.0, 1.0, 16).translate((7.0, 0, 3.99))                     # goujon de la lamelle (pas de vis)
    lamelle = mf.Manifold.cube((15, 7, 0.5), True).translate((1.5, 0, 0.25)) - mf.Manifold.cylinder(2, 1.1, 1.1, 16).translate((7.0, 0, -0.5))
    pieces = {"stator": stator_s, "rotor": rot, "flasque_avant": fl_av, "flasque_arriere": fl_ar, "arbre": arbre,
              "excentrique": exc,
              "bouchon_graisseur_1": bouchon, "bouchon_graisseur_2": bouchon,
              "clapet_siege": siege, "clapet_lamelle": lamelle}
    if visserie == "imprimee" and imprimer_vis:
        for k in range(4):
            pieces[f"tirant_{k + 1}"] = tirant
            pieces[f"ecrou_{k + 1}"] = ecrou
    pile = 2 * e_fl + h_st
    q_vis = {"placo": f"4 vis placo d3.5 x 45 (pile {pile:.0f} mm : la pointe depasse de ~{45 - pile:.0f} mm a l'arriere, a couper a la meuleuse ou a laisser)",
             "imprimee": "4 tirants M8 + 4 ecrous IMPRIMES" + ("" if imprimer_vis else " (non inclus dans ce plateau)"),
             "m3": f"4 vis M3 x {int(math.ceil((pile + 2) / 5) * 5)} + 4 ecrous M3 (noyes au dos)"}[visserie]
    q = [q_vis, f"Joints toriques : cordon de tore {cord:g} mm -> 3 segments d'apex de {b:g} mm + 2 joints de flasque d ~{2 * r_g:.0f} mm (cordon colle bout a bout)",
         "Graisse (silicone ou lithium) : paliers, excentrique, engrenage", "Tube : " + {"lego": "tube pneumatique LEGO (4 x 2 mm)", "tube8": "tube d8 interieur",
         "cannele": "tube souple", "g18": "raccords G1/8 (taraud G1/8)", "m5": "raccords M5"}.get(port, port)]
    infos = {"excentricite_mm": round(e, 3), "R_mm": round(R, 2), "K": K, "cylindree_chambre_cm3": round(cylindree(e, R, b), 2),
             "taux_compression_geometrique": round(_taux(e, R), 1), "fuite_rotor_mm2": round(fuite, 4), "rotor_ok": fuite < 0.01,
             "a_imprimer_en_plus": "tout est imprime : arbre, paliers, tirants, ecrous, clapets", "quincaillerie": q,
             "geometrie_sim": {"e": e, "R": R, "b": b, "jeu": jeu, "jeu_flanc": jeu_flanc, "angle_admission": a_adm, "angle_refoulement": a_ref},
             "conseil": "Arbre et tirants : imprimer DEBOUT, 100 % remplissage, 0.12 mm (qualite Art). Rotor et stator : 5 perimetres. "
                        "Poncer la piste du stator et l'alesage du rotor, graisser ; perceuse 500-1200 tr/min (paliers PLA : chauffe au-dela)."}
    if compact:
        mot = _moteur_reduction(p, r_ext, e_fl, d_tour)
        pieces.update(mot["pieces"]); q += mot["quincaillerie"]; infos.update(mot["infos"])
    noms = list(pieces)
    out = [vers_trimesh(pieces[n]) for n in noms]
    poses = []
    zr = e_fl + jeu_flanc
    for n in noms:
        T = np.eye(4)
        if n == "stator":
            T[2, 3] = e_fl
        elif n == "rotor":
            T[0, 3], T[2, 3] = e, zr                         # arbre a 0 deg : centre du rotor sur l'excentrique
        elif n == "flasque_avant":
            pass                                          # pignon fixe tourne vers le rotor (vers +z)
        elif n == "flasque_arriere":
            T = np.diag([1.0, -1, -1, 1]); T[2, 3] = 2 * e_fl + h_st      # retourne : sa gorge de joint face au stator
        elif n == "excentrique":
            T[0, 3], T[2, 3] = e, zr + prof_eng + 0.5
        elif n == "arbre":
            T = np.diag([1.0, -1, -1, 1]); T[2, 3] = 2 * e_fl + h_st + 1.0   # hexagone mandrin cote flasque avant ; tourillons dans les paliers                                # tourillon "arriere" dans le flasque avant
        elif n.startswith("tirant"):
            k = int(n[-1]) - 1
            T[0, 3], T[1, 3], T[2, 3] = r_vis * math.cos(a_vis[k]), r_vis * math.sin(a_vis[k]), -4.0
        elif n.startswith("ecrou"):
            k = int(n[-1]) - 1
            T[0, 3], T[1, 3], T[2, 3] = r_vis * math.cos(a_vis[k]), r_vis * math.sin(a_vis[k]), 2 * e_fl + h_st
        else:
            T[0, 3] = r_ext + 30 + 20 * noms.index(n) % 60
        poses.append(T.tolist())
    infos.update({"noms": noms, "assemblage": poses})
    return out, infos


def _taux(e, R):
    """Taux de compression geometrique Vmax / Vmin (volumes des chambres calcules sur les profils reels)."""
    from atelier.projets.compresseur.sim_wankel import geometrie
    _, V, _ = geometrie(e, R, 10.0, 0.0, 120)
    return float(V.max() / V.min())


def _d_plat(d):
    return Point(0, 0).buffer(d / 2 + 0.1, 32).difference(sbox(d / 2 - 0.5, -d, d, d))


def _moteur_reduction(p, r_ext, e_fl, d_axe):
    """Version compacte : moteur 130 (ou 180) + reduction a 2 engrenages dans un carter fixe sur le flasque avant."""
    import trimesh
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    moteur = p.get("moteur", "130")
    M = {"130": (20.0, 15.0, 25.0, 2.0, 12.5), "180": (20.4, 15.4, 32.5, 2.0, 15.0)}[moteur]   # l, e, L, axe, entraxe vis
    z1, z2 = int(g("dents_pignon_moteur", 10)), int(g("dents_roue", 40))
    mm = 0.8
    entraxe = mm * (z1 + z2) / 2 + 0.1
    pig, _ = profil_engrenage(mm, z1, 20, 0.06)
    roue, _ = profil_engrenage(mm, z2, 20, 0.06)
    pignon = mf.Manifold.extrude(section(pig), 6) - mf.Manifold.cylinder(8, 1.0 - 0.02, 1.0 - 0.02, 24).translate((0, 0, -1))
    roue_s = mf.Manifold.extrude(section(roue), 6) - mf.Manifold.extrude(section(_d_plat(d_axe)), 10).translate((0, 0, -1))
    # carter : plaque support moteur (le moteur se fixe dessous par 2 vis M2 a l'entraxe M[4])
    carter = mf.Manifold.extrude(section(Point(0, 0).buffer(r_ext, 64).union(Point(entraxe, 0).buffer(M[0] / 2 + 3, 48))), 3)
    carter = carter - mf.Manifold.cylinder(5, 4.5, 4.5, 48).translate((entraxe, 0, -1))      # palier du moteur
    for s in (-1, 1):
        carter = carter - mf.Manifold.cylinder(5, 1.1, 1.1, 16).translate((entraxe, s * M[4] / 2, -1))
    carter = carter - mf.Manifold.cylinder(5, d_axe / 2 + 0.3, d_axe / 2 + 0.3, 32).translate((0, 0, -1))
    # capot de protection des engrenages (couvercle arrondi)
    capot = mf.Manifold.extrude(section(Point(0, 0).buffer(r_ext, 64).union(Point(entraxe, 0).buffer(M[0] / 2 + 3, 48))
                                        .difference(Point(0, 0).buffer(r_ext - 1.6, 64).union(Point(entraxe, 0).buffer(M[0] / 2 + 1.4, 48)))), 8)
    capot = capot + mf.Manifold.extrude(section(Point(0, 0).buffer(r_ext, 64).union(Point(entraxe, 0).buffer(M[0] / 2 + 3, 48))), 1.6).translate((0, 0, 8))
    return {"pieces": {"pignon_moteur": pignon, "roue_reduction": roue_s, "carter_moteur": carter, "capot_engrenages": capot},
            "quincaillerie": [f"Moteur {moteur} (5-7.4 V) + 2 vis M2x4", f"Reduction {z2}/{z1} = {z2 / z1:.1f}:1"],
            "infos": {"reduction": round(z2 / z1, 2), "entraxe_reduction_mm": round(entraxe, 2)}}
