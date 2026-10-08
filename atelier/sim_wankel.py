"""SIMULATION du compresseur Wankel (cycle reel, pas une formule) :

1. GEOMETRIE : volumes des 3 chambres en fonction de l'angle de l'arbre, CALCULES sur les profils reels
   (stator epitrochoide - rotor, decoupes par les rayons rotor -> sommets), lumieres d'admission et de
   refoulement ouvertes / fermees selon la position des sommets.
2. THERMODYNAMIQUE : chaque chambre suit sa masse d'air ; compression polytropique, remplissage a l'admission,
   refoulement par le clapet a lamelle quand p_chambre > p_reservoir (+ seuil du clapet), FUITES aux sommets
   et aux flancs (debit d'orifice a travers les jeux), frottement des paliers lisses imprimes.
3. RESULTATS : debit d'air libre, couple moyen / maxi a l'arbre, puissance, rendement volumetrique,
   PRESSION MAXI atteignable, diagramme P-V, courbe debit = f(pression), optimisation des lumieres.
"""
from __future__ import annotations

import math

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon

from .wankel import stator_profil, rotor_profil

P_ATM = 101325.0
T0 = 293.0
R_AIR = 287.0


def _sommets_rotor(rotor):
    pts = np.asarray(rotor.exterior.coords)
    d = np.hypot(pts[:, 0], pts[:, 1])
    ang = np.arctan2(pts[:, 1], pts[:, 0])
    s = []
    for k in range(3):
        a0 = 2 * math.pi * k / 3
        m = np.abs(((ang - a0 + math.pi) % (2 * math.pi)) - math.pi) < 0.6
        s.append(pts[np.argmax(np.where(m, d, -1))])
    return np.array(s)


def geometrie(e, R, b, jeu=0.15, n=240):
    """Volumes (m3) des 3 chambres sur un tour de ROTOR (= 3 tours d'arbre), n echantillons.
    Retourne phi_arbre (rad), V[n, 3], angles polaires des sommets[n, 3]."""
    stator = stator_profil(e, R, 1440)
    rotor = rotor_profil(e, R, jeu, 240)
    S0 = _sommets_rotor(rotor)
    V = np.zeros((n, 3))
    A = np.zeros((n, 3))
    phis = np.zeros(n)
    for i in range(n):
        alpha = 2 * math.pi * i / n                     # angle du rotor
        phi = 3 * alpha                                  # angle de l'arbre
        c = np.array([e * math.cos(phi), e * math.sin(phi)])
        Rm = np.array([[math.cos(alpha), -math.sin(alpha)], [math.sin(alpha), math.cos(alpha)]])
        r_ = affinity.translate(affinity.rotate(rotor, alpha, origin=(0, 0), use_radians=True), c[0], c[1])
        S = S0 @ Rm.T + c
        vide = stator.difference(r_)
        for k in range(3):
            a, b_ = S[k], S[(k + 1) % 3]
            secteur = Polygon([tuple(c), tuple(c + (a - c) * 3), tuple(c + (b_ - c) * 3)])
            V[i, k] = vide.intersection(secteur).area * b * 1e-9
            A[i, k] = math.atan2(a[1], a[0])
        phis[i] = phi
    return phis, V, A


def _ouvert(angle_lumiere, a_debut, a_fin, largeur):
    """La lumiere (angle polaire) est-elle entre le sommet de tete et le sommet de queue de la chambre ?"""
    def dans(x, a0, a1):
        return (x - a0) % (2 * math.pi) <= (a1 - a0) % (2 * math.pi)
    return dans(angle_lumiere - largeur / 2, a_debut, a_fin) or dans(angle_lumiere + largeur / 2, a_debut, a_fin)


def simuler(e, R, b, rpm=1200, p_reservoir_bar=1.0, ang_adm=130, ang_ref=50, largeur_lumiere_deg=14,
            jeu=0.15, jeu_flanc=0.2, apex_etanche=True, n_poly=1.25, seuil_clapet_bar=0.05,
            d_lumiere=5.0, frottement_Nm=0.05, geo=None, tours=3):
    """Simule `tours` tours de rotor (regime etabli au dernier). Retourne un dict de resultats."""
    phis, V, A = geo or geometrie(e, R, b, jeu)
    n = len(phis)
    omega = rpm * 2 * math.pi / 60                     # arbre
    dt = (phis[1] - phis[0]) / omega
    p_res = P_ATM + p_reservoir_bar * 1e5
    a_adm, a_ref, larg = math.radians(ang_adm), math.radians(ang_ref), math.radians(largeur_lumiere_deg)
    # sections de fuite (m2) : sommet (jeu x largeur, reduit si segment d'apex en caoutchouc) + flancs (2 x jeu x longueur ~ 2/3 du flanc)
    s_apex = (jeu * 1e-3) * (b * 1e-3) * (0.15 if apex_etanche else 1.0)
    s_flanc = 2 * (jeu_flanc * 1e-3) * (R * 1.2e-3) * 0.5
    s_lum = math.pi * (d_lumiere * 1e-3 / 2) ** 2
    Cd = 0.62
    m = V[0] * P_ATM / (R_AIR * T0)                     # masse d'air par chambre
    p = np.full(3, P_ATM)
    livre = 0.0
    travail = 0.0
    hist_p = np.zeros((n, 3))
    couple = np.zeros(n)

    def debit(p_amont, p_aval, s):                      # orifice incompressible simplifie (Bernoulli), signe = amont -> aval
        dp = p_amont - p_aval
        rho = max(p_amont, p_aval) / (R_AIR * T0)
        return math.copysign(Cd * s * math.sqrt(2 * rho * abs(dp)), dp)

    for t in range(tours):
        livre_t, travail_t = 0.0, 0.0
        for i in range(n):
            j = (i + 1) % n
            for k in range(3):
                Vk, Vn = V[i, k], V[j, k]
                # compression / detente polytropique de la masse enfermee
                p[k] = p[k] * (Vk / Vn) ** n_poly if Vn > 1e-12 else p[k]
                travail_t += -(p[k] - P_ATM) * (Vn - Vk)           # travail recu par l'air (= fourni par l'arbre)
                tete, queue = A[j, (k + 1) % 3], A[j, k]
                # 2 paires de lumieres symetriques (les 2 points morts : chaque chambre comprime 2 fois par tour de rotor)
                ouv_adm = _ouvert(a_adm, queue, tete, larg) or _ouvert(a_adm + math.pi, queue, tete, larg)
                ouv_ref = _ouvert(a_ref, queue, tete, larg) or _ouvert(a_ref + math.pi, queue, tete, larg)
                # admission (vers l'atmosphere, dans les deux sens)
                if ouv_adm:
                    q = debit(P_ATM, p[k], s_lum) * dt
                    m[k] += q
                # refoulement par clapet (seulement si p > p_res + seuil)
                if ouv_ref and p[k] > p_res + seuil_clapet_bar * 1e5:
                    q = debit(p[k], p_res, s_lum) * dt
                    q = min(q, max(0.0, m[k] - p_res * Vn / (R_AIR * T0)))
                    m[k] -= q
                    livre_t += q
                # fuites vers la chambre voisine (apex) et vers l'interieur (flancs, vers l'admission ~ atmosphere)
                kv = (k + 1) % 3
                qa = debit(p[k], p[kv], s_apex) * dt
                m[k] -= qa
                m[kv] += qa
                qf = debit(p[k], P_ATM, s_flanc) * dt
                m[k] -= qf
            for k in range(3):
                p[k] = max(1000.0, m[k] * R_AIR * T0 / max(V[j, k], 1e-12))
            hist_p[j] = p
            # couple instantane : somme des pressions * dV/dphi
            dphi = phis[1] - phis[0]
            couple[j] = sum((p[k] - P_ATM) * -(V[j, k] - V[i, k]) / dphi for k in range(3)) + frottement_Nm
        livre, travail = livre_t, travail_t
    duree_tour = n * dt                                  # 1 tour de rotor
    debit_libre_Lmin = livre / (P_ATM / (R_AIR * T0)) * 1000 / duree_tour * 60
    puissance = (travail / duree_tour) + frottement_Nm * omega
    vol_balaye = (V.max(axis=0) - V.min(axis=0)).sum()  # par tour de rotor
    eta_v = debit_libre_Lmin / (vol_balaye * 1000 / duree_tour * 60) if vol_balaye > 0 else 0
    return {"rpm": rpm, "p_reservoir_bar": p_reservoir_bar, "debit_libre_L_min": round(debit_libre_Lmin, 2),
            "rendement_volumetrique": round(eta_v, 3), "puissance_W": round(max(puissance, 0), 1),
            "couple_moyen_Nm": round(max(puissance, 0) / omega, 3), "couple_max_Nm": round(float(np.max(couple)), 3),
            "p_chambre_max_bar": round(float((hist_p.max() - P_ATM) / 1e5), 2),
            "pv": {"V_cm3": (V[:, 0] * 1e6).round(3).tolist(), "p_bar": ((hist_p[:, 0] - P_ATM) / 1e5).round(3).tolist()},
            "couple_Nm": couple.round(3).tolist()}


def courbe(e, R, b, rpm=1200, p_max=6.0, pas=0.5, **kw):
    """Debit / couple / puissance en fonction de la pression du reservoir + pression maxi atteignable."""
    geo = geometrie(e, R, b, kw.get("jeu", 0.15))
    kw = {k: v for k, v in kw.items() if k in ("ang_adm", "ang_ref", "jeu", "jeu_flanc", "apex_etanche", "n_poly", "seuil_clapet_bar", "d_lumiere", "frottement_Nm")}
    pts = []
    for pr in np.arange(0, p_max + 1e-9, pas):
        r = simuler(e, R, b, rpm, float(pr), geo=geo, **kw)
        pts.append({k: r[k] for k in ("p_reservoir_bar", "debit_libre_L_min", "couple_moyen_Nm", "couple_max_Nm", "puissance_W", "rendement_volumetrique")})
        if r["debit_libre_L_min"] <= 0.05 and pr > 0:
            break
    p_maxi = next((q["p_reservoir_bar"] for q in pts if q["debit_libre_L_min"] <= 0.05 and q["p_reservoir_bar"] > 0), None)
    r0 = simuler(e, R, b, rpm, 1.0, geo=geo, **kw)
    return {"points": pts, "pression_maxi_bar": p_maxi if p_maxi is not None else f"> {p_max}", "cycle_1bar": r0}


def optimiser_lumieres(e, R, b, rpm=1200, p_cible=2.0, **kw):
    """Cherche les angles d'admission / refoulement qui maximisent le debit a la pression cible."""
    geo = geometrie(e, R, b, kw.get("jeu", 0.15))
    kw = {k: v for k, v in kw.items() if k in ("jeu", "jeu_flanc", "apex_etanche", "n_poly")}
    meilleur = None
    # point mort haut a 90 deg : refoulement AVANT (90 - d1), admission APRES (90 + d2)
    # contrainte geometrique : refoulement pres du PMH (d1 < ~25 deg), admission loin derriere (d2 > ~55 deg)
    for d2 in range(40, 121, 5):
        for d1 in range(4, 41, 2):
            a_adm, a_ref = 90 + d2, 90 - d1
            r = simuler(e, R, b, rpm, p_cible, ang_adm=a_adm, ang_ref=a_ref, geo=geo, tours=2, **kw)
            if meilleur is None or r["debit_libre_L_min"] > meilleur[0]:
                meilleur = (r["debit_libre_L_min"], a_adm, a_ref, r["couple_moyen_Nm"])
    return {"debit_L_min": round(meilleur[0], 2), "angle_admission": meilleur[1], "angle_refoulement": meilleur[2], "couple_moyen_Nm": meilleur[3]}
