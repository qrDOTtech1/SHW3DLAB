"""LE ServBuddy v2.5 (by SHWork) - SANS VISSERIE : bracelet porte-assiette en MONOCOQUE + CARENAGES, facon armure (Iron Man).

Repere : X = avant-bras (+X vers la main), Y = largeur du poignet (+Y = cote cubitus / petit doigt), Z = dos du poignet.

On ne l'enfile pas : on l'OUVRE, on le POSE, on le FERME (verrouillage automatique), on REGLE a la molette.
- DEUX DEMI-COQUES structurelles (fines, ajourees) articulees par une CHARNIERE cote cubitus (+Y).
- FERMETURE = REGLAGE : la demi-coque palmaire porte un SECTEUR DENTE centre sur l'axe de charniere ; il engrene un
  PIGNON loge dans la nacelle cote radius (-Y). Le pignon est solidaire d'une MOLETTE affleurante et d'une ROUE A
  ROCHET : un CLIQUET laisse serrer mais jamais desserrer (verrouillage automatique a la fermeture).
  v2.5 : cliquet redessine AU CALCUL (voir cliquet.py) : rochet 30 dents a crochet, verrou coulissant qui renvoie
  l'effort dans la paroi de la nacelle, ressort replie a egale contrainte (0.37 % au clic contre 3.2 % en v2.4).
  La LANGUETTE de liberation, a fleur, souleve le verrou : on ouvre.
- CARENAGES facettes, decolles des coques par des entretoises (lame d'air = isolation + look "armure flottante"),
  lignes de panneaux, bords biseautes.
- PORT (rail queue d'aronde) sur le carenage dorsal : modules interchangeables (plateau porte-assiette, pince
  porte-serviette...) qui s'y glissent et s'y verrouillent par un ergot.
Tout en PLA.
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as mf
from shapely.geometry import Polygon, Point, LineString, box as sbox
from shapely import affinity
from shapely.ops import unary_union

from atelier.noyau.c3d import section, vers_trimesh
from atelier.projets.servbuddy.v1 import extrude_x, tube, rrect, union, _ell

M3 = 1.65


def _ram(a, k):
    return a * math.pi * (3 * (1 + k) - math.sqrt((3 + k) * (1 + 3 * k)))


def servbuddy2(p: dict):
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    tour = g("tour_poignet", 165.0)
    L = g("longueur", 58.0)
    film = g("film", 0.8)
    PX, PY = g("plateau_l", 96.0), g("plateau_w", 74.0)
    k = 0.72
    a = tour / (math.pi * (3 * (1 + k) - math.sqrt((3 + k) * (1 + 3 * k))))
    b = k * a
    ai, bi = a + film, b + film                       # interieur des coques (film alcantara compris)
    ec = 1.8                                          # epaisseur des coques structurelles
    gap = 2.4                                         # lame d'air coque -> carenage
    ek = 1.6                                          # epaisseur du carenage
    out = {}

    def P(off, t):
        return np.array([(ai + off) * math.cos(t), (bi + off) * math.sin(t)])

    def arc(r0, r1, t0, t1, n=120):
        t = np.linspace(t0, t1, n)
        return Polygon(np.vstack([_ell(ai + r1, bi + r1, t), _ell(ai + r0, bi + r0, t)[::-1]])).buffer(0)

    cav = extrude_x(Polygon(_ell(ai, bi, np.linspace(-math.pi, math.pi, 240))), -L, L)
    R = math.radians
    # ---- angles : charniere cote +Y (cubitus), nacelle de reglage cote -Y (radius)
    t_h = R(-28)                                      # charniere
    t_d1 = R(196)                                     # bout de la coque dorsale cote -Y
    t_p0 = R(-160)                                    # debut de la coque palmaire (sous la nacelle)
    # ================= DEMI-COQUE DORSALE (structure ajouree)
    dor = extrude_x(arc(0, ec, t_h + R(4), t_d1, 200).buffer(0.6, join_style=1).buffer(-0.6, join_style=1), -L / 2, L / 2)
    # NID D'ABEILLE (allegement + respiration) : alveoles hexagonales radiales, parois de 1.1 mm sur
    # lesquelles l'alcantara se colle ; bordures pleines aux bouts et sur les zones mecaniques.
    def alveoles(t0, t1, x0, x1, Rc=2.9, paroi=1.1):
        cells = []
        r_moy = (ai + bi) / 2 + ec / 2
        pas_x = 1.5 * Rc + paroi * 0.866
        pas_t = (math.sqrt(3) * Rc + paroi) / r_moy
        i = 0
        x = x0 + Rc
        while x <= x1 - Rc:
            t = t0 + pas_t / 2 + (pas_t / 2 if i % 2 else 0)
            while t <= t1 - pas_t / 2:
                pi_, po_ = P(-1.0, t), P(ec + 1.0, t)
                c = tube((x, pi_[0], pi_[1]), (x, po_[0], po_[1]), Rc, 6)
                cells.append(c)
                t += pas_t
            x += pas_x
            i += 1
        return union(cells) if cells else None
    dor = dor - alveoles(R(14), R(172), -L / 2 + 4.0, L / 2 - 4.0)
    # ================= DEMI-COQUE PALMAIRE
    pal = extrude_x(arc(0, ec, t_p0, t_h - R(4), 140).buffer(0.6, join_style=1).buffer(-0.6, join_style=1), -L / 2 + 4, L / 2 - 4)
    pal = pal - alveoles(R(-138), R(-44), -L / 2 + 8.0, L / 2 - 8.0)
    # ================= CHARNIERE (axe X, 5 noeuds alternes)
    H = P(ec + 1.6, t_h)                              # axe de charniere noye dans la lame d'air (sous le carenage)
    rh = 3.0                                          # noeuds renforces (choc)
    r_ax, j_ax = 1.75, 0.4                            # axe imprime d3.5, jeu radial 0.4
    noeuds = np.linspace(-L / 2, L / 2, 6)
    for i in range(5):
        x0, x1 = noeuds[i] + 0.25, noeuds[i + 1] - 0.25
        c = extrude_x(Point(H).buffer(rh, 48).union(Polygon([H + [0, 0], P(ec * 0.5, t_h + (R(8) if i % 2 == 0 else -R(8))), P(ec * 0.5, t_h)]).buffer(1.6)), x0, x1)
        if i % 2 == 0:
            dor = dor + (c - cav)
        else:
            pal = pal + (c - cav)
    for i in range(5):                                # jeu entre noeuds (0.3 mm) : on retire le noeud adverse elargi
        x0, x1 = noeuds[i] - 0.0, noeuds[i + 1]
        z_ = extrude_x(Point(H).buffer(rh + 0.35, 48), x0, x1)
        if i % 2 == 0:
            pal = pal - z_
        else:
            dor = dor - z_
    # l'AXE fait partie de la coque dorsale (imprime en place, debout) ; la coque palmaire tourne autour
    pal = pal - tube((-L / 2 - 1, H[0], H[1]), (L / 2 + 1, H[0], H[1]), r_ax + j_ax)
    dor = dor + tube((noeuds[0] + 0.25, H[0], H[1]), (noeuds[-1] - 0.25, H[0], H[1]), r_ax)
    # ================= REGLAGE : SECTEUR DENTE (palmaire) + PIGNON (nacelle dorsale)
    from atelier.meca import profil_engrenage
    m_, z_p = 1.0, 11
    rp = m_ * z_p / 2
    Rm = 7.2                                          # molette
    C0 = P(Rm + 2.2, R(186))                          # axe assez loin pour que la molette ne touche JAMAIS la peau
    Rg = np.linalg.norm(C0 - H) - rp                  # rayon primitif du secteur (centre = charniere)
    z_g = int(round(2 * Rg / m_))
    Rg = m_ * z_g / 2
    u = (C0 - H) / np.linalg.norm(C0 - H)
    C = H + u * (Rg + rp)                             # entraxe exact
    ang_c = math.atan2(u[1], u[0])
    wg = 6.0                                          # largeur d'engrenement (x de -3 a +3)
    pg_big, info_g = profil_engrenage(m_, z_g, 20, 0.12)
    sect = Polygon([(0, 0)] + [((Rg + 3) * math.cos(ang_c + d), (Rg + 3) * math.sin(ang_c + d)) for d in np.linspace(-R(16), R(16), 40)])
    secteur2d = affinity.translate(pg_big, H[0], H[1]).intersection(affinity.translate(sect, H[0], H[1])).difference(
        Point(H).buffer(Rg - 3.2, 128))
    balai = Polygon([H] + [tuple(H + (Rg + 30) * np.array([math.cos(ang_c + d), math.sin(ang_c + d)])) for d in np.linspace(-R(34), R(34), 40)])
    # bras qui relie le secteur a la coque palmaire
    bras2d = Polygon([P(ec - 0.2, t_p0 + R(2)), P(ec - 0.2, t_p0 + R(16)),
                      H + u * (Rg - 3.0) + np.array([u[1], -u[0]]) * 2.0, H + u * (Rg - 3.0) - np.array([u[1], -u[0]]) * 6.0]).buffer(0.8)
    pal = pal + (extrude_x(secteur2d.union(bras2d).buffer(0), -wg / 2, wg / 2) - cav)
    out["coque_palmaire"] = pal
    # ================= MECANIQUE MONTABLE (ordre de montage) :
    #  1. glisser le PIGNON-ROCHET par la FENETRE de la nacelle (cote exterieur) ;
    #  2. enfiler l'AXE (hexagonal 5 mm sur plats) par le cote coude : sa BASE RONDE (d12) bute contre la nacelle,
    #     sert de semelle pour l'imprimer debout et de cache ;
    #  3. glisser la MOLETTE sur le bout de l'axe (hors nacelle) + vis M3 x 8 et rondelle dans le bout de l'axe ;
    #  4. poser la TRAPPE-CLIQUET dans la fenetre (sa lame souple tombe dans le rochet) : le carenage dorsal la tient.
    #  Liberer : soulever la languette de la trappe (le bec quitte le rochet) -> on ouvre.
    hexa = Polygon([(2.89 * math.cos(math.pi / 3 * i + math.pi / 6), 2.89 * math.sin(math.pi / 3 * i + math.pi / 6)) for i in range(6)])
    pg_small, _ = profil_engrenage(m_, z_p, 20, 0.12)
    sec_loc = affinity.translate(secteur2d, -C[0], -C[1])
    best = min(np.linspace(0, 360 / z_p, 24), key=lambda d: affinity.rotate(pg_small, d, origin=(0, 0)).intersection(sec_loc).area)
    pg_small = affinity.rotate(pg_small, float(best), origin=(0, 0))
    x_r0, x_r1 = wg / 2 + 0.6, wg / 2 + 3.6                     # rochet
    pig = mf.Manifold.extrude(section(pg_small), wg).translate((0, 0, -wg / 2))
    # v2.5 : rochet dessine dans le repere (u = tg, v = n_out) de la nacelle puis ramene dans le repere du pignon
    from atelier.projets.servbuddy import cliquet as CQ
    n_out = (C - np.array([0, 0])) / np.linalg.norm(C)
    tg = np.array([-n_out[1], n_out[0]])
    uv_loc = [tg[0], n_out[0], tg[1], n_out[1], 0, 0]                    # (u, v) -> repere local du pignon
    uv_glob = [tg[0], n_out[0], tg[1], n_out[1], C[0], C[1]]             # (u, v) -> (Y, Z)
    roch = mf.Manifold.extrude(section(affinity.affine_transform(CQ.rochet_uv(), uv_loc)), x_r1 - x_r0).translate((0, 0, x_r0))
    lien = mf.Manifold.cylinder(x_r0 - wg / 2 + 0.02, 4.4, 4.4, 48).translate((0, 0, wg / 2 - 0.01))
    pr = union([pig, roch, lien]) - mf.Manifold.extrude(section(hexa.buffer(0.18, join_style=2)), 40).translate((0, 0, -20))
    T_ax = np.array([[0, 0, 1, 0], [1, 0, 0, C[0]], [0, 1, 0, C[1]]], float)        # axe local Z -> X
    out["pignon_rochet"] = pr.transform(T_ax)
    # nacelle : de x0 (paroi cote coude, 4 mm) a x_n1 (paroi cote main, 2.4 mm) ; la molette est DEHORS
    x_n0, x_c0, x_c1 = -wg / 2 - 4.5, -wg / 2 - 0.5, x_r1 + 0.5
    x_n1 = x_c1 + 2.4
    x_m0, x_m1 = x_n1 + 0.6, x_n1 + 6.6                          # molette
    mol = mf.Manifold.cylinder(x_m1 - x_m0, Rm, Rm, 96).translate((0, 0, x_m0))
    for i in range(36):
        a0 = i * 2 * math.pi / 36
        mol = mol - mf.Manifold.cylinder(10, 0.55, 0.55, 8).translate((Rm * math.cos(a0), Rm * math.sin(a0), x_m0 - 1))
    mol = mol - mf.Manifold.extrude(section(hexa.buffer(0.15, join_style=2)), 30).translate((0, 0, x_m0 - 5))
    # v2.4 : 5 rayons au lieu d'un disque plein (jante 1.4 mm, moyeu r4.0)
    for i in range(5):
        a0 = i * 2 * math.pi / 5
        sect = Polygon([(0, 0)] + [(9 * math.cos(a0 + d), 9 * math.sin(a0 + d)) for d in np.linspace(0.32, 2 * math.pi / 5 - 0.32, 8)])
        jour = sect.intersection(Point(0, 0).buffer(Rm - 1.4, 64).difference(Point(0, 0).buffer(4.0, 48))).buffer(-0.4, join_style=1).buffer(0.4, join_style=1)
        if jour.area > 0.5:
            mol = mol - mf.Manifold.extrude(section(jour), 20).translate((0, 0, x_m0 - 5))
    out["molette"] = mol.transform(T_ax)
    # AXE hexagonal + BASE RONDE (cache, semelle d'impression), percage M3 en bout (vis de la molette)
    x_a0 = x_n0 - 2.0
    axe = mf.Manifold.extrude(section(hexa), x_m1 - 1.0 - x_n0).translate((0, 0, x_n0))
    axe = axe + mf.Manifold.cylinder(2.0, 6.0, 6.0, 64).translate((0, 0, x_a0))
    axe = axe + mf.Manifold.cylinder(0.6, 6.0, 5.4, 64).translate((0, 0, x_a0 - 0.6))               # chanfrein du cache
    out["axe"] = axe.transform(T_ax)
    # NACELLE
    n_out = (C - np.array([0, 0])) / np.linalg.norm(C)
    tg = np.array([-n_out[1], n_out[0]])
    nac2d = Point(C).buffer(rp + 3.2, 64).union(arc(0, ec, t_d1 - R(18), t_d1, 30)).union(
        Polygon([P(ec, t_d1 - R(18)), P(ec, t_d1), C + np.array([0, -rp - 3.0]), C + np.array([0, rp + 3.2])]).buffer(0)).buffer(1.2, join_style=1).buffer(-1.2, join_style=1)
    nac = extrude_x(nac2d, x_n0, x_n1) - cav
    Rr = rp + 1.0 + 0.6                                          # logement unique pignon + rochet
    nac = nac - extrude_x(Point(C).buffer(Rr, 64), x_c0, x_c1)
    fen = Polygon([C - u * (rp + 0.2) + np.array([u[1], -u[0]]) * 9, C - u * (rp + 0.2) - np.array([u[1], -u[0]]) * 9,
                   C - u * (rp + 9) - np.array([u[1], -u[0]]) * 12, C - u * (rp + 9) + np.array([u[1], -u[0]]) * 12])
    nac = nac - extrude_x(fen.union(Point(H).buffer(Rg + 1.6, 160).difference(Point(H).buffer(Rg - 3.8, 160)).intersection(
        Point(C).buffer(rp + 6, 64))), -wg / 2 - 0.5, wg / 2 + 0.5)
    nac = nac - tube((-L, C[0], C[1]), (L, C[0], C[1]), 3.15)                                 # palier de l'axe (hexa tourne dedans)
    # FENETRE de montage (cote exterieur) + TRAPPE-CLIQUET qui la referme
    fen2d = Polygon([C - tg * (Rr + 0.1), C + tg * (Rr + 0.1), C + tg * (Rr + 0.1) + n_out * 30, C - tg * (Rr + 0.1) + n_out * 30])
    nac = nac - extrude_x(fen2d, x_c0, x_c1)
    # ---- v2.5 TRAPPE-CLIQUET (cliquet.py) : jambe clipsee + ressort replie + verrou coulissant + languette
    G = lambda g_: affinity.affine_transform(g_, uv_glob)
    compat24 = bool(p.get("coque_v24", 0))             # coquille deja imprimee en v2.4 : pas de gorge -> pas de bourrelet
    D_ = CQ.dessin(dict(CQ.P, bourrelet=(CQ.P["bourrelet"][0], 0.0)) if compat24 else CQ.P)
    if not compat24:
        nac = nac - extrude_x(G(D_["gorge"]), x_c0 - 0.01, x_c1 + 0.01)                # gorge du clip (vraie paroi)
    fib_ = np.array(D_["fibre"].coords)
    def trappe_pose(dv):
        """Trappe avec le verrou souleve de dv (0 = imprime). Ressort deforme au calcul (meme modele que la FEA)."""
        _, _, U_ = CQ.fea(fib_, D_["ep"], x_c1 - x_c0 - 0.5, dv)
        res_ = CQ.ressort_poly(fib_ + U_[:, :2], D_["ep"])
        mob_ = affinity.translate(D_["mobile"], 0, dv)
        return res_, mob_
    # imprime avec le verrou PLUS BAS de la precharge : une fois pose sur le rochet il appuie (0.6 N)
    res0, mob0 = trappe_pose(-CQ.P["precharge"])
    t2d = unary_union([D_["jambe"], res0, mob0])
    trappe = extrude_x(G(t2d), x_c0 + 0.25, x_c1 - 0.25)
    trappe = trappe - extrude_x(G(Point(0, 0).buffer(CQ.P["r_pignon"] + 0.35, 96)), x_c0, x_r0 - 0.3)     # tranche du pignon
    trappe = trappe - extrude_x(G(Point(0, 0).buffer(4.4 + 0.4, 64)), x_c0, x_c1)                            # moyeu
    # enveloppe de balayage (verrou souleve jusqu'a levee + 0.25) : le carenage s'en ecarte de 0.25
    balayage_cq = [D_["jambe"].buffer(0.05)]
    for dv in np.linspace(0, CQ.P["levee"] + 0.25, 6):
        r_, m_ = trappe_pose(dv)
        balayage_cq += [r_.buffer(0.25), m_.buffer(0.25)]
    balayage_cq = G(unary_union(balayage_cq))
    out["trappe_cliquet"] = trappe
    dor = dor + nac
    # ================= CARENAGES facettes sur entretoises (lame d'air)
    def carenage(t0, t1, n_fac, x0, x1, bosse=None, creux=None):
        ts = np.linspace(t0, t1, n_fac + 1)
        ext = [P(gap + ec + ek + 0.6, t) for t in ts]                                      # sommets des facettes
        inn = _ell(ai + ec + gap, bi + ec + gap, np.linspace(t1, t0, 120))
        s2 = Polygon(np.vstack([np.array(ext), inn])).buffer(0)
        if bosse is not None:                         # le carenage ENVELOPPE la nacelle (forme tendue, convexe)
            enve = unary_union([Polygon(ext[-4:] + [bosse.exterior.coords[i] for i in range(0, len(bosse.exterior.coords), 4)]).convex_hull])
            s2 = s2.union(enve.difference(creux)).difference(creux)
            s2 = s2.difference(Polygon(_ell(ai + ec + gap, bi + ec + gap, np.linspace(-math.pi, math.pi, 240))))
        s2 = s2.buffer(-0.5, join_style=1).buffer(0.5, join_style=1)
        c = extrude_x(s2, x0, x1).refine_to_length(2.5)
        Lc = (x1 - x0) / 2; xc = (x0 + x1) / 2

        def biseau(Pp):                                   # bords biseautes : la peau exterieure rentre aux extremites
            Pp = np.asarray(Pp).copy()
            rho = np.sqrt((Pp[:, 1] / (ai + ec + gap)) ** 2 + (Pp[:, 2] / (bi + ec + gap)) ** 2)
            ext_ = np.clip((rho - 1.0) / (ek / (bi + ec + gap)), 0, 1.5)
            fin = np.clip((np.abs(Pp[:, 0] - xc) - (Lc - 3.0)) / 3.0, 0, 1)
            f = 1 - 0.035 * ext_ * fin
            Pp[:, 1] *= f; Pp[:, 2] *= f
            return Pp
        c = c.warp_batch(biseau)
        for xg in (xc - Lc * 0.42, xc + Lc * 0.42):                                          # lignes de panneaux
            c = c - extrude_x(arc(ec + gap + ek - 0.45, ec + gap + ek + 3, t0 - 0.2, t1 + 0.2), xg - 0.35, xg + 0.35)
        return c

    bosse = nac2d.buffer(gap + ek, join_style=1)
    kd = carenage(t_h + R(10), t_d1 - R(24), 9, -L / 2 + 1, L / 2 - 1, bosse=bosse, creux=nac2d.buffer(gap * 0.6, join_style=1))
    # capot de charniere : prolonge le carenage dorsal par-dessus les noeuds (la charniere devient invisible)
    cap2d = Point(H).buffer(rh + 0.6 + ek, 64).union(arc(ec + gap, ec + gap + ek + 0.6, t_h - R(2), t_h + R(14), 30)).convex_hull
    cap2d = cap2d.difference(Point(H).buffer(rh + 0.6, 64)).difference(arc(-5, ec + gap, t_h - R(40), t_h + R(40), 60))
    cap2d = cap2d.difference(Polygon(_ell(ai + ec + 0.3, bi + ec + 0.3, np.linspace(-math.pi, math.pi, 240))))
    cap = extrude_x(cap2d.buffer(0.4, join_style=1).buffer(-0.4, join_style=1), -L / 2 + 1, L / 2 - 1)
    # seule la moitie haute du capot (cote dorsal) : la coque palmaire pivote dessous
    cap = cap - extrude_x(Polygon([H, H + np.array([30, -40]), H + np.array([-30, -40])]), -L, L)
    kd = kd + cap
    # rien du carenage dans le chemin du secteur dente / de la coque palmaire
    env_sect = extrude_x(Point(H).buffer(Rg + 2.2, 160).difference(Point(H).buffer(Rg - 4.6, 160)).intersection(balai).union(bras2d.buffer(0.8)), -wg / 2 - 0.8, wg / 2 + 0.8)
    kp = carenage(t_p0 + R(3), t_h - R(5), 6, -L / 2 + 5, L / 2 - 5)
    # REBORDS : les carenages se referment sur les coques aux deux extremites (lame d'air invisible)
    def rebords(car, t0, t1, x0, x1):
        for xb, sens in ((x0, 1), (x1, -1)):
            lev = extrude_x(arc(ec + 0.35, ec + gap + 0.3, t0, t1, 80), min(xb, xb + sens * 1.2), max(xb, xb + sens * 1.2))
            xa_, xb_ = sorted((xb + sens * 0.35, xb + sens * 0.85))
            perle = extrude_x(arc(ec - 0.45, ec + 0.4, t0 + R(2), t1 - R(2), 80), xa_, xb_)        # bourrelet continu
            car = car + lev + perle
            gorges.append((t0, t1, xa_ - 0.1, xb_ + 0.1))
        return car
    gorges = []
    kd = rebords(kd, t_h + R(4), t_d1 - R(4), -L / 2 + 1, L / 2 - 1)
    for t0_, t1_, xa_, xb_ in gorges:
        dor = dor - extrude_x(arc(ec - 0.6, ec + 0.6, t0_ + R(1), t1_ - R(1), 80), xa_, xb_)
    gorges = []
    kp = rebords(kp, t_p0 + R(4), t_h - R(6), -L / 2 + 5, L / 2 - 5)
    gorges_p = list(gorges)
    kd, kp = kd - env_sect, kp - env_sect
    dor = dor - extrude_x(Point(H).buffer(Rg + 1.8, 160).difference(Point(H).buffer(Rg - 4.4, 160)).intersection(balai).union(bras2d.buffer(0.6)), -wg / 2 - 0.6, wg / 2 + 0.6)
    # entretoises : plots coque -> carenage (vis M2.5 / M3 depuis l'exterieur, tetes noyees)
    def plots(coque, car, angs, xs):
        for t in angs:
            for x in xs:
                a_ = P(-0.0, t); b_ = P(ec + gap - 0.02, t)
                coque = coque + tube((x, P(0.02, t)[0], P(0.02, t)[1]), (x, P(ec, t)[0], P(ec, t)[1]), 4.2)    # ilot plein sous le plot
                pl = tube((x, a_[0], a_[1]), (x, b_[0], b_[1]), 2.6)
                coque = coque + pl
                # entretoise creuse (allegee) + poche d'accroche noyee dans la coque (0.5 mm de peau cote poignet)
                q3 = lambda off: np.array([x, P(off, t)[0], P(off, t)[1]])
                coque = coque - tube(q3(0.5), q3(ec + gap + 0.5), 1.8) - tube(q3(0.5), q3(ec - 0.2), 2.35)
                coque = coque + (tube(q3(ec - 0.2), q3(ec + 0.05), 2.6) - tube(q3(ec - 0.3), q3(ec + 0.2), 1.8))   # levre de retenue
                # pion a ailettes sous le carenage : tige fendue + bec conique qui s'enclenche sous la levre
                tige = tube(q3(ec + gap + 0.4), q3(0.75), 1.5)
                bec = mf.Manifold.hull(union([tube(q3(1.55), q3(1.6), 2.15, 24), tube(q3(0.75), q3(0.8), 1.45, 24)]))
                pion = tige + bec
                n3 = np.array([0, P(1, t)[0] - P(0, t)[0], P(1, t)[1] - P(0, t)[1]]); n3 /= np.linalg.norm(n3)
                fente = mf.Manifold.cube((0.7, 30, 30), True).translate(tuple(q3(0.75) + n3 * 0))
                fente = fente ^ mf.Manifold.hull(union([tube(q3(0.6), q3(3.9), 3.0, 24)]))
                car = car + (pion - fente)
        return coque, car
    dor, kd = plots(dor, kd, (R(20), R(90), R(160)), (-L / 2 + 6, L / 2 - 6))
    out["coque_palmaire"], kp = plots(out["coque_palmaire"], kp, (R(-110), R(-70)), (-L / 2 + 10, L / 2 - 10))
    for t0_, t1_, xa_, xb_ in gorges_p:
        out["coque_palmaire"] = out["coque_palmaire"] - extrude_x(arc(ec - 0.6, ec + 0.6, t0_ + R(1), t1_ - R(1), 80), xa_, xb_)
    # fente de la molette dans le carenage dorsal (la molette affleure, bord moletee visible)
    kd = kd - extrude_x(Point(C).buffer(Rm + 1.0, 96), x_m0 - 0.6, x_m1 + 0.6)
    # le carenage arrete la molette en bout d'axe (joue de 1.6 mm) : plus de vis

    # ENCOCHE DE POUCE : creusee vers l'exterieur, evasee -> le bord moletee de la molette affleure
    enc = Point(C + n_out * (Rm + 2.5)).buffer(Rm * 0.75, 64).union(Point(C).buffer(Rm + 1.0, 96)).convex_hull
    kd = kd - extrude_x(enc, x_m0 - 0.6, x_m1 + 0.6)
    kd = kd - mf.Manifold.hull(union([extrude_x(Point(C + n_out * (Rm + 2.5)).buffer(Rm * 0.75, 48), x_m0 - 0.6, x_m1 + 0.6),
                                      extrude_x(Point(C + n_out * (Rm + 7.0)).buffer(Rm * 1.05, 48), x_m0 - 2.4, x_m1 + 2.4)]))
    # BOUTON de liberation affleurant : trou dans le carenage au droit du cliquet
    # passage de la LANGUETTE de liberation du cliquet a travers le carenage (on la souleve du bout du doigt)
    kd = kd - extrude_x(balayage_cq, x_c0 - 0.3, x_c1 + 0.3)
    # v2.4 COMMANDES A FLEUR : rien ne depasse de la peau du carenage (0.4 mm en retrait), cuvette pour l'ongle
    peau_k = Polygon(_ell(ai + ec + gap + ek, bi + ec + gap + ek, np.linspace(-math.pi, math.pi, 240))).union(bosse).convex_hull.buffer(-0.4)
    a_fleur = extrude_x(peau_k, -L, L)
    out["trappe_cliquet"] = out["trappe_cliquet"] ^ a_fleur
    # encoche d'ongle dans la languette (1 mm sous la peau) + cuvette du carenage cote +u (hors ressort)
    l0_, l1_ = CQ.P["u_lang"]
    peau_uv = affinity.affine_transform(peau_k, [tg[0], tg[1], n_out[0], n_out[1], -tg @ C, -n_out @ C])
    v_top = max(y_ for x_, y_ in np.array(peau_uv.intersection(LineString([((l0_ + l1_) / 2, 0), ((l0_ + l1_) / 2, 30)])).coords))
    out["trappe_cliquet"] = out["trappe_cliquet"] - extrude_x(G(sbox(l0_ + 0.7, v_top - 1.9, l1_ + 0.2, v_top - 1.1)), x_c0, x_c1)
    pt_ = C + tg * (l1_ + 1.2) + n_out * (v_top + 3.0)
    kd = kd - mf.Manifold.sphere(3.6, 48).scale((1.6, 1.0, 1.0)).translate((0.5 * (x_c0 + x_c1), *pt_))
    out["molette"] = out["molette"] ^ a_fleur
    # ================= PORT (rail queue d'aronde) sur le carenage dorsal
    z_k = bi + ec + gap + ek                                                                 # dessus du carenage
    q = Polygon([(-9, 0), (9, 0), (11.5, 3.2), (-11.5, 3.2)])                                # profil du rail (y, z)
    rail = mf.Manifold.extrude(section(q), L - 8).transform(np.array([[0, 0, 1, -L / 2 + 4], [1, 0, 0, 0], [0, 1, 0, z_k - 0.4]], float))
    pied = mf.Manifold.extrude(section(rrect(L - 8, 26, 3)), 2.0).translate((0, 0, z_k - 1.6))
    port = (rail + pied) - extrude_x(Polygon(_ell(ai + ec + gap + ek - 0.6, bi + ec + gap + ek - 0.6, np.linspace(-math.pi, math.pi, 240))), -L, L)
    port = port - mf.Manifold.cylinder(5, 1.55, 1.55, 16).translate((L / 2 - 9, 0, z_k - 1))      # trou d'ergot de verrouillage
    kd = kd + port
    # PORT DU DESSOUS (meme rail, tete en bas) sur le carenage palmaire : 2e module (pince, aimants, lampe...)
    z_b = -(bi + ec + gap + ek)
    Lb = L - 14
    railb = mf.Manifold.extrude(section(affinity.scale(q, 1, -1, origin=(0, 0))), Lb).transform(
        np.array([[0, 0, 1, -Lb / 2], [1, 0, 0, 0], [0, 1, 0, z_b + 0.4]], float))
    piedb = mf.Manifold.extrude(section(rrect(Lb, 26, 3)), 2.0).translate((0, 0, z_b - 0.4))
    portb = (railb + piedb) - extrude_x(Polygon(_ell(ai + ec + gap + ek - 0.6, bi + ec + gap + ek - 0.6, np.linspace(-math.pi, math.pi, 240))), -L, L)
    portb = portb - mf.Manifold.cylinder(5, 1.55, 1.55, 16).translate((Lb / 2 - 5, 0, z_b - 4))
    kp = kp + portb
    dor = dor - extrude_x(arc(-0.6, ec + 0.7, t_p0 - R(1.5), t_p0 + R(40)), -L / 2 + 3.4, L / 2 - 3.4)   # la coque palmaire pivote librement
    def texte2d(txt, police, h):
        from atelier.produits.porte_cles import Style, glyphes
        g_ = unary_union(glyphes(txt, Style(police=police, hauteur=10.0)))
        bt = g_.bounds
        g_ = affinity.translate(g_, -(bt[0] + bt[2]) / 2, -(bt[1] + bt[3]) / 2)
        return affinity.scale(g_, h / (bt[3] - bt[1]), h / (bt[3] - bt[1]), origin=(0, 0))

    def graver(car, poly2d, t, xc, prof=0.55):
        """Grave poly2d (u = X, v = hauteur) sur la face du carenage a l'angle t (normale radiale)."""
        n_ = np.array([math.cos(t) / (ai + ec + gap + ek), math.sin(t) / (bi + ec + gap + ek)]); n_ /= np.linalg.norm(n_)
        tg_ = np.array([-n_[1], n_[0]])
        o_ = P(ec + gap + ek + 3, t)
        pr = mf.Manifold.extrude(section(affinity.scale(poly2d, -1, 1, origin=(0, 0))), 12.0)   # lu a l endroit de l exterieur
        M = np.array([[1, 0, 0, xc], [0, tg_[0], -n_[0], o_[0]], [0, tg_[1], -n_[1], o_[1]]], float)
        pr = pr.transform(M)
        peau = extrude_x(Polygon(_ell(ai + ec + gap + ek - prof, bi + ec + gap + ek - prof, np.linspace(-math.pi, math.pi, 240))), -L, L)
        return car - (pr - peau)
    try:
        from atelier.noyau.logo import logo_polygone
        kd = graver(kd, logo_polygone(26.0, "mot"), R(31), 0.0, prof=0.5)               # logo SHWork (flanc cubitus)
        kd = graver(kd, texte2d("ServBuddy 1", "gabriola", 5.6), R(16), 0.0)          # signature manuscrite dessous
        kp = graver(kp, logo_polygone(20.0, "mot"), R(-122), 0.0, prof=0.5)           # logo cote paume
    except Exception as ex_:
        print("logo:", ex_)
    out["coque_dorsale"] = dor
    out["carenage_dorsal"] = kd
    out["carenage_palmaire"] = kp
    # ================= MODULES DU PORT
    z_m = z_k + 3.2 - 0.4
    qf = Polygon([(-9.25, -0.01), (9.25, -0.01), (11.75, 3.45), (-11.75, 3.45)])
    def coulisse(Lm):                                     # glissiere femelle + ergot elastique
        return mf.Manifold.extrude(section(qf), Lm + 2).transform(np.array([[0, 0, 1, -Lm / 2 - 1], [1, 0, 0, 0], [0, 1, 0, z_k - 0.4]], float))
    # --- module PLATEAU : dalle flottante effilee, pistes a silicone, aimants
    z_pl = z_k + 3.2 + 2.5
    ep = 4.2

    def dalle(lx, ly, r, z, h=0.01):
        return mf.Manifold.extrude(section(rrect(lx, ly, r)), h).translate((0, 0, z))
    pl = mf.Manifold.hull(union([dalle(30, 30, 6, z_k + 0.2), dalle(PX - 18, PY - 18, 8, z_pl), dalle(PX, PY, 10, z_pl + ep * 0.55),
                                 dalle(PX, PY, 10, z_pl + ep - 0.8), dalle(PX - 1.6, PY - 1.6, 9.2, z_pl + ep - 0.01)]))
    pistes = [rrect(PX - 2 * d, PY - 2 * d, max(1.5, 10 - d)).difference(rrect(PX - 2 * d - 4, PY - 2 * d - 4, max(1, 8 - d)))
              for d in range(6, int(min(PX, PY) / 2) - 4, 6)]
    pl = pl - mf.Manifold.extrude(section(unary_union(pistes)), 1.4).translate((0, 0, z_pl + ep - 1.4))
    pl = pl + mf.Manifold.extrude(section(rrect(PX, PY, 10).difference(rrect(PX - 3, PY - 3, 8.5))), 1.2).translate((0, 0, z_pl + ep))
    for sy in (-1, 1):
        for sx in (-1, 1):
            pl = pl - tube((sx * PX * 0.2, sy * (PY / 2 + 0.5), z_pl + ep / 2), (sx * PX * 0.2, sy * (PY / 2 - 3.2), z_pl + ep / 2), 5.1)
    # v2.4 PLATEAU AJOURE : alveoles hexagonales ouvertes par dessous ; 1.2 mm de peau sous les pistes, cerclage,
    # bossages d'aimants et zone de la glissiere gardes pleins
    hx_ = []
    Rc_, pas_ = 3.6, 3.6 * math.sqrt(3) + 1.2
    keep = Polygon(rrect(PX - 7, PY - 7, 7)).difference(Polygon(rrect(36, 34, 5)))
    for sy in (-1, 1):
        for sx in (-1, 1):
            keep = keep.difference(Point(sx * PX * 0.2, sy * (PY / 2 - 3)).buffer(7.5))
    for i in range(-12, 13):
        for j in range(-12, 13):
            cy_ = j * pas_ + (i % 2) * pas_ / 2
            cx_ = i * pas_ * math.sqrt(3) / 2
            h_ = Polygon([(cx_ + Rc_ * math.cos(math.pi / 3 * k_), cy_ + Rc_ * math.sin(math.pi / 3 * k_)) for k_ in range(6)])
            if keep.contains(h_):
                hx_.append(h_)
    if hx_:
        pl = pl - mf.Manifold.extrude(section(unary_union(hx_)), (z_pl + ep - 1.4 - 1.2) - (z_k - 5)).translate((0, 0, z_k - 5))
    pl = pl - coulisse(L - 8) - kd
    def cran(mod, xh):
        """Languette souple taillee dans le module + bossage qui tombe dans le trou du rail : on pousse, ca clique."""
        zt = z_k - 0.4 + 3.45                                    # plafond de la glissiere femelle
        mod = mod - mf.Manifold.cube((12.0, 7.6, 0.8)).translate((xh - 9.0, -3.8, zt + 2.6))        # fente de flexion
        for y_ in (-3.8, 3.0):
            mod = mod - mf.Manifold.cube((12.0, 0.8, 3.4)).translate((xh - 9.0, y_, zt))
        return mod + mf.Manifold.cylinder(1.1, 1.3, 1.1, 24).translate((xh, 0, zt - 1.05))
    pl = cran(pl, L / 2 - 9)
    out["module_plateau"] = pl
    # --- module PINCE PORTE-SERVIETTE (meme rail : se glisse a la place, ou sur un 2e bracelet)
    Lp = 26
    pin = mf.Manifold.extrude(section(rrect(Lp, 30, 4)), 6.0).translate((0, 0, z_k - 0.4))
    pin = pin - coulisse(Lp)
    lame = mf.Manifold.cube((22, 29, 2.0)).translate((-11, 12.5, z_k + 3.6))
    machoire = mf.Manifold.cube((22, 3, 7)).translate((-11, 38.5, z_k - 1.4))
    dents = union([mf.Manifold.cube((22, 1.0, 1.0)).translate((-11, 37.6, z_k - 1.4 + 1.4 * i)) for i in range(4)])
    lame = lame - union([mf.Manifold.cylinder(4, 3.2, 3.2, 6).translate((xx, yy, z_k + 3.0)) for xx in (-6, 0, 6) for yy in (18.5, 27.5)])   # v2.4 lame ajouree
    pin = union([pin, lame, machoire, dents])
    out["module_pince"] = pin.translate((0, 0, 40))       # pose a cote (non monte sur le rail)
    # ================= priorites : la peau ne touche rien, le carenage dorsal prime, les carenages epousent les coques
    out["coque_dorsale"] = out["coque_dorsale"] - cav
    out["coque_palmaire"] = out["coque_palmaire"] - cav
    out["carenage_dorsal"] = out["carenage_dorsal"] - out["coque_dorsale"]
    from atelier.noyau.c3d import vers_manifold as _vm
    out["carenage_dorsal"] = out["carenage_dorsal"] - extrude_x(balayage_cq, x_c0 - 0.3, x_c1 + 0.3)         - out["trappe_cliquet"] - out["axe"] - out["molette"]
    out["carenage_palmaire"] = out["carenage_palmaire"] - out["coque_palmaire"] - out["carenage_dorsal"]
    # ================= OUIES EN CHEVRONS (aeration : l'air traverse le carenage puis le nid d'abeille)
    def chevrons(car, t_c, n_rang, x0, x1, pas=6.5, bras=4.2, larg=0.75, ang=38):
        # rangee de chevrons pointant vers la main (+X), sur la face d'angle t_c (et n_rang rangees autour)
        n_ = np.array([math.cos(t_c) / (ai + ec + gap + ek), math.sin(t_c) / (bi + ec + gap + ek)]); n_ /= np.linalg.norm(n_)
        cuts = []
        r_moy = (ai + bi) / 2 + ec + gap + ek
        for j_ in range(n_rang):
            t = t_c + (j_ - (n_rang - 1) / 2) * (2 * bras * math.cos(math.radians(ang)) + 3.0) / r_moy
            pi_, po_ = P(ec + gap - 0.5, t), P(ec + gap + ek + 2.0, t)
            tg_ = np.array([-math.sin(t), math.cos(t)])
            x = x0
            while x <= x1:
                for sgn in (-1, 1):
                    d_ = np.array([-math.cos(math.radians(ang)) * bras, sgn * math.sin(math.radians(ang)) * bras])   # (dx, dtangente)
                    a3 = lambda p_: np.array([x, p_[0], p_[1]])
                    b3 = lambda p_: np.array([x + d_[0], p_[0] + tg_[0] * d_[1], p_[1] + tg_[1] * d_[1]])
                    cuts.append(mf.Manifold.hull(union([tube(a3(pi_), a3(po_), larg, 12), tube(b3(pi_), b3(po_), larg, 12)])))
                x += pas
        return car - union(cuts)
    # flancs du carenage dorsal (au-dessus du nid d'abeille, entre plots et logo) + flancs palmaires
    kd_ = out["carenage_dorsal"]
    kd_ = chevrons(kd_, R(55), 2, -L / 2 + 9, L / 2 - 8)
    kd_ = chevrons(kd_, R(128), 2, -L / 2 + 9, L / 2 - 8)
    out["carenage_dorsal"] = kd_
    out["carenage_palmaire"] = chevrons(out["carenage_palmaire"], R(-62), 1, -L / 2 + 12, L / 2 - 12)
    # ================= DEGAGEMENT CINEMATIQUE : serrage (-10 deg) -> ouverture (+60 deg) autour de la charniere.
    # Chaque position de la partie palmaire creuse son passage : rien ne frotte, ni au serrage ni a l'ouverture.
    def rot(m, deg):
        c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return m.transform(np.array([[1, 0, 0, 0], [0, c, -s_, H[0] - c * H[0] + s_ * H[1]],
                                     [0, s_, c, H[1] - s_ * H[0] - c * H[1]]], float))
    angles = [d for d in range(-11, 12) if d != 0] + list(range(12, 62, 2))       # pas fin sur la plage de serrage
    sans_secteur = out["coque_palmaire"] - extrude_x(Point(H).buffer(Rg + 4, 160).difference(Point(H).buffer(Rg - 5, 160)).union(bras2d.buffer(1.0)), -wg / 2 - 1, wg / 2 + 1)
    fixe_c = union([out["coque_dorsale"], out["carenage_dorsal"]])
    out["carenage_palmaire"] = out["carenage_palmaire"] - union([rot(fixe_c, -d) for d in angles])
    out["coque_dorsale"] = out["coque_dorsale"] - union([rot(sans_secteur, d) for d in angles])
    out["carenage_dorsal"] = out["carenage_dorsal"] - union([rot(sans_secteur, d) for d in angles])
    # ================= menage : rien ne s'interpenetre, zero copeau
    out["coque_dorsale"] = out["coque_dorsale"] - out["molette"].__add__(mf.Manifold.cylinder(0.01, 0.01, 0.01, 3))
    for k_, v_ in list(out.items()):
        parts = sorted(v_.decompose(), key=lambda q: -q.volume())
        out[k_] = union([q for q in parts if q.volume() > 0.02 * parts[0].volume()])
    if not p.get("separer_coques"):                    # CHARNIERE IMPRIMEE EN PLACE : les 2 coques = 1 seule impression
        out["coquille_charniere"] = out.pop("coque_dorsale") + out.pop("coque_palmaire")
    info = {"version": "2.5", "poignet_mm": [round(2 * a, 1), round(2 * b, 1)], "tour_poignet": tour, "secteur_dents": z_g, "charniere_yz": [float(H[0]), float(H[1])],
            "quincaillerie": ["AUCUNE VIS : charniere imprimee en place (coquille debout, axe d3.5 jeu 0.4), carenages clipses (bourrelets peripheriques + 10 pions a ailettes), molette tenue par le carenage, modules du port a cran",
                              
                              "4 aimants neodyme 10 x 3 (module plateau)", "Silicone alimentaire (pistes du plateau)",
                              "Film alcantara adhesif 0.8 mm (interieur des 2 coques)", "Tout en PLA, 4 perimetres sur molette, secteur et charniere"],
            "fonctionnement": "Ouvrir (bouton de liberation), poser sur le poignet, refermer : le cliquet verrouille ; regler a la molette."}
    return out, info
