"""VIBE DECK v2 : macropad + ecran, design epure (monobloc arrondi, plaque affleurante, aucune vis visible).

Pieces (generees dans leur ORIENTATION D'IMPRESSION ; "assemblage" = pose de la vue montee) :
  * socle  : monobloc en coin (dessus incline, dessous plat), aretes arrondies continues (enveloppe convexe
             de spheres = conges parfaits), logement de plaque affleurant + joint d'ombre, USB-C, vis par DESSOUS,
             charniere centrale a l'arriere ;
  * plaque : plaque de switchs MX 1.5 mm (decoupes 14.0), fenetre OLED / encodeur, bossages a inserts M3 dessous ;
  * cadre  : cadre de l'ecran Guition JC4827W543 (120 x 70.2, zone active 95.04 x 53.86), bordure reguliere,
             chanfrein "verre" autour de la zone active ;
  * dos    : capot arriere (4 vis dans les trous de la carte), passage de cable, pattes de pivot ;
  * pivot  : a CRANS (roue + languette flexible), par SERVO SG90/MG90S coaxial, ou FIXE.
"""
from __future__ import annotations

import math

import numpy as np
import manifold3d as mf
from shapely.geometry import Point, box as sbox
from shapely.ops import unary_union

from atelier.noyau.c3d import section, vers_trimesh

PAS_MX = 19.05
# JC4827W543 : 120.00 x 70.20 mm, zone active 95.04 x 53.86 mm, trous d3.2 (manuel Guition / ESPHome)
GUITION = {"l": 120.0, "h": 70.2, "actif_l": 95.04, "actif_h": 53.86}
SERVOS = {"sg90": (22.8, 12.3, 22.7, 32.3, 27.8, 5.9), "mg90s": (22.8, 12.4, 22.7, 32.3, 27.8, 5.9)}


# ------------------------------------------------------------------ volumes aux aretes arrondies
def _arc_rect(l, w, R, n=10):
    R = max(0.01, min(R, l / 2 - 0.01, w / 2 - 0.01))
    pts = []
    for cx, cy, a0 in ((l / 2 - R, w / 2 - R, 0), (-l / 2 + R, w / 2 - R, 90), (-l / 2 + R, -w / 2 + R, 180), (l / 2 - R, -w / 2 + R, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
    return pts


def galet(l, w, h_av, h_ar, R=10.0, e=2.5, n=10):
    """Monobloc : coins de rayon R en plan, toutes les aretes arrondies de rayon e, dessus incline de h_av
    (avant, y-) a h_ar (arriere, y+), dessous plat a z = 0."""
    sph = []
    for x, y in _arc_rect(l - 2 * e, w - 2 * e, max(0.01, R - e), n):
        sph.append(mf.Manifold.sphere(e, 24).translate((x, y, e)))
        zt = h_av + (h_ar - h_av) * (y + w / 2) / w - e
        sph.append(mf.Manifold.sphere(e, 24).translate((x, y, zt)))
    s = mf.Manifold.batch_hull(sph)
    return s ^ mf.Manifold.cube((l * 3, w * 3, 400)).translate((-l * 1.5, -w * 1.5, 0))


def dalle(l, w, ep, R=6.0, e=1.2):
    return galet(l, w, ep, ep, R, min(e, ep / 2 - 0.01))


def _rr(l, w, r):
    r = max(0.01, min(r, l / 2 - 0.01, w / 2 - 0.01))
    return sbox(-l / 2, -w / 2, l / 2, w / 2).buffer(-r, join_style=1).buffer(r, join_style=1)


def _T(x, y, z):
    M = np.eye(4); M[:3, 3] = (x, y, z); return M


def _Rx(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]], float)


def _demi_espace(L, W, z0):
    return mf.Manifold.cube((L * 4, W * 4, 400)).translate((-L * 2, -W * 2, z0))


# ------------------------------------------------------------------ VIBE DECK
def vibe_deck(p: dict):
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    cols, rows = int(g("colonnes", 4)), int(g("rangees", 3))
    ecran = p.get("ecran", "guition_43")
    pivot = p.get("pivot", "crans")
    encodeur = int(g("encodeur", 1))
    angle = g("inclinaison", 7)
    R, e = g("rayon", 10), g("arrondi", 2.5)
    bord = g("bord", 6)
    joint = g("joint_ombre", 0.35)
    h_av = g("hauteur_avant", 16)
    fond = g("fond", 2.2)
    q = []
    # ---------------------------------------------------------------- dimensions
    Lk, Wk = cols * PAS_MX, rows * PAS_MX
    extra = 26.0 if (ecran.startswith("oled") or encodeur) else 0.0
    m_pl = 7.0                                            # marge plaque : les bossages passent loin des switchs
    Lp, Wp = Lk + extra + 2 * m_pl, Wk + 2 * m_pl
    L, W = Lp + 2 * bord, Wp + 2 * bord
    h_ar = h_av + W * math.tan(math.radians(angle))
    ztop = lambda y: h_av + (h_ar - h_av) * (y + W / 2) / W
    socle = galet(L, W, h_av, h_ar, R, e)
    e_pl = 1.5
    Mp = _T(0, 0, ztop(0) - e_pl / math.cos(math.radians(angle))) @ _Rx(angle)     # pose de la plaque (affleurante)
    Rp = max(1.0, R - bord)
    # ---------------------------------------------------------------- creusages : logement + joint d'ombre, cavite
    logement = mf.Manifold.extrude(section(_rr(Lp + 2 * joint, Wp + 2 * joint, Rp + joint)), 30).transform(Mp[:3, :])
    cavite = mf.Manifold.extrude(section(_rr(Lp - 4, Wp - 4, max(0.5, Rp - 2))), 60).translate((0, 0, -60)).transform(Mp[:3, :])
    cavite = cavite ^ _demi_espace(L, W, fond)
    socle = socle - logement - cavite                     # le rebord de 2 mm sous la plaque la porte
    # ---------------------------------------------------------------- plaque (repere propre = repere d'impression)
    x_touches = -Lp / 2 + m_pl + Lk / 2
    x_extra = Lp / 2 - m_pl - extra / 2
    trous = []
    for i in range(cols):
        for j in range(rows):
            x = x_touches - Lk / 2 + PAS_MX * (i + 0.5)
            y = -Wk / 2 + PAS_MX * (j + 0.5)
            trous.append(sbox(x - 7.0, y - 7.0, x + 7.0, y + 7.0))
    if ecran.startswith("oled"):
        fl, fh = (22.0, 11.5) if ecran == "oled_096" else (30.0, 15.5)
        trous.append(sbox(x_extra - fl / 2, Wp / 2 - 6 - fh, x_extra + fl / 2, Wp / 2 - 6))
        q.append("Ecran OLED 0.96\" I2C (SSD1306)" if ecran == "oled_096" else "Ecran OLED 1.3\" I2C (SH1106)")
    if encodeur:
        trous.append(Point(x_extra, -Wp / 2 + 12).buffer(3.6, 32))
        q.append("Encodeur rotatif EC11 + bouton")
    plaque = mf.Manifold.extrude(section(_rr(Lp, Wp, Rp).difference(unary_union(trous))), e_pl)
    bos = [(sx * (Lp / 2 - 5.6), sy * (Wp / 2 - 5.6)) for sx in (-1, 1) for sy in (-1, 1)]   # dans la cavite (rebord 2 mm)
    for x, y in bos:                                      # bossages longs (coupes au fond apres pose)
        plaque = plaque + mf.Manifold.cylinder(60, 3.2, 3.2, 32).translate((x, y, -60 + 0.01))
    plaque_pose = plaque.transform(Mp[:3, :]) ^ _demi_espace(L, W, fond + 0.3)
    for x, y in bos:                                      # inserts M3 a la base de chaque bossage (verticaux)
        P = Mp @ np.array([x, y, 0, 1.0])
        plaque_pose = plaque_pose - mf.Manifold.cylinder(5.5, 2.1, 2.1, 24).translate((P[0], P[1], fond + 0.29))
        socle = socle - mf.Manifold.cylinder(fond + 2, 1.7, 1.7, 24).translate((P[0], P[1], -1)) \
                      - mf.Manifold.cylinder(1.6, 3.3, 1.7, 24).translate((P[0], P[1], -0.01))
    plaque = plaque_pose.transform(np.linalg.inv(Mp)[:3, :])
    # USB-C a l'arriere, sous la plaque
    socle = socle - mf.Manifold.extrude(section(_rr(12.5, 7.0, 2.5)), 30).rotate((-90, 0, 0)).translate((g("usb_x", 0.0), W / 2 - 12, fond + 5.5))
    q += [f"{cols * rows} switchs MX (+ {cols * rows} keycaps : onglet Keycaps)", "4 inserts M3 a chaud (d4 x 5)",
          "4 vis M3x10 tete fraisee (par dessous)", "4 patins silicone 8 mm"]
    pieces = [("socle", socle, np.eye(4)), ("plaque", plaque, Mp)]
    infos = {"touches": cols * rows, "dimensions_socle_mm": [round(L, 1), round(W, 1), round(h_ar, 1)]}
    # ---------------------------------------------------------------- ecran Guition : cadre + dos + pivot central
    if ecran == "guition_43":
        bl, bh = g("ecran_l", GUITION["l"]), g("ecran_h", GUITION["h"])
        al, ah = g("actif_l", GUITION["actif_l"]), g("actif_h", GUITION["actif_h"])
        ax_, ay_ = g("actif_x", 0.0), g("actif_y", 0.0)
        ep_carte = g("ecran_e", 9.0)
        tx, ty = g("trou_x", 3.5), g("trou_y", 3.5)
        bz = g("bordure", 3.0)
        Re = g("rayon_ecran", 7)
        cl, ch = bl + 2 * bz, bh + 2 * bz
        e_av = 2.0
        h_cadre = e_av + ep_carte * 0.6
        cadre = dalle(cl, ch, h_cadre, Re, 1.2)
        cadre = cadre - mf.Manifold.extrude(section(_rr(bl + 0.6, bh + 0.6, 1.5)), 40).translate((0, 0, e_av))
        cadre = cadre - mf.Manifold.extrude(section(_rr(al, ah, 0.8)), 10).translate((ax_, ay_, -1))
        cadre = cadre - mf.Manifold.extrude(section(_rr(al + 2.0, ah + 2.0, 1.8)), 1.0, 0, 0, (al / (al + 2.0), ah / (ah + 2.0))).translate((ax_, ay_, -0.001))
        e_dos = 2.0
        h_dos = ep_carte * 0.4 + e_dos + 1.0
        dos = dalle(cl, ch, h_dos, Re, 1.2)
        dos = dos - mf.Manifold.extrude(section(_rr(bl + 0.6, bh + 0.6, 1.5)), 40).translate((0, 0, e_dos))
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (bl / 2 - tx), sy * (bh / 2 - ty)
                dos = dos + mf.Manifold.cylinder(h_dos - e_dos - 0.5, 3.0, 3.0, 24).translate((x, y, e_dos)) \
                          - mf.Manifold.cylinder(h_dos + 2, 1.7, 1.7, 24).translate((x, y, -1)) \
                          - mf.Manifold.cylinder(1.6, 3.2, 1.7, 24).translate((x, y, -0.01))
        dos = dos - mf.Manifold.extrude(section(_rr(30, 8, 2)), e_dos + 2).translate((0, -bh / 2 + 10, -1))
        q += ["Carte Guition JC4827W543 (ESP32-S3 integre)", "4 vis M3x12 tete fraisee (dos de l'ecran)"]
        infos["a_verifier"] = ("JC4827W543 : 120 x 70.2 et zone active 95.04 x 53.86 = cotes officielles ; "
                               "epaisseur de la carte et position des 4 trous a verifier au pied a coulisse")
        # ---- charniere centrale. Axe le long de X, a l'arriere du socle.
        sp, rp, ep_p = g("largeur_charniere", 34.0), 6.0, 6.0
        AX_Y, AX_Z = W / 2 + rp + 2.3, h_ar + 0.5           # derriere le socle : roue et pattes ne touchent jamais l'arete
        a_ecr = math.radians(g("angle_ecran", 72))
        # repere du DOS : y local = "haut" de l'ecran, z local = vers l'arriere (face exterieure du dos en z=0)
        U = np.array([0, math.cos(a_ecr), math.sin(a_ecr)])
        Zd = np.array([0, math.sin(a_ecr), -math.cos(a_ecr)])
        Zd = -Zd                                          # z local du dos pointe vers l'avant (vers le cadre)
        Rm = np.eye(4); Rm[:3, 1], Rm[:3, 2] = U, Zd; Rm[:3, 0] = np.cross(U, Zd)
        ay, az = -ch / 2 - rp - 2.5, rp                  # axe dans le repere du dos
        xs = [-sp / 2 + ep_p / 2, sp / 2 - ep_p / 2]
        for k, x in enumerate(xs):
            pt = mf.Manifold.hull(mf.Manifold.cylinder(ep_p, rp, rp, 48).rotate((0, 90, 0)).translate((x - ep_p / 2, ay, az))
                                  + mf.Manifold.cube((ep_p, 2, h_dos * 0.8), True).translate((x, -ch / 2 + 6, h_dos * 0.4)))
            pt = pt - mf.Manifold.cylinder(ep_p + 2, 1.7, 1.7, 24).rotate((0, 90, 0)).translate((x - ep_p / 2 - 1, ay, az))
            pt = pt - mf.Manifold.cube((cl, ch, 60)).translate((-cl / 2, -ch / 2, h_dos))      # rien dans l'emprise du cadre
            if pivot == "crans" and k == 0:
                roue = mf.Manifold.cylinder(2.5, rp + 1.5, rp + 1.5, 64)
                for c in range(7):
                    a_ = math.radians(-45 + c * 15)
                    roue = roue - mf.Manifold.cylinder(3.0, 1.1, 1.1, 16).translate(((rp + 1.5) * math.cos(a_), (rp + 1.5) * math.sin(a_), -0.2))
                roue = roue - mf.Manifold.cylinder(4, 1.7, 1.7, 24).translate((0, 0, -1))
                pt = pt + roue.rotate((0, -90, 0)).translate((x - ep_p / 2, ay, az))
            if pivot == "servo" and k == 1:
                croix = mf.Manifold.cube((2.2, 16, 2.0), True) + mf.Manifold.cube((16, 2.2, 2.0), True) + mf.Manifold.cylinder(2.0, 3.6, 3.6, 32, True)
                pt = pt - croix.rotate((0, 90, 0)).translate((x + ep_p / 2 - 0.9, ay, az))
            dos = dos + pt
        pose_dos = _T(0, AX_Y, AX_Z) @ Rm @ _T(0, -ay, -az)
        # cadre : face avant vers l'utilisateur, pose contre le dos (retourne : sa face z=0 vers l'avant)
        pose_cadre = pose_dos @ _T(0, 0, h_dos + h_cadre) @ np.diag([-1.0, 1, -1, 1])
        # ---- cote socle : chapes (sorties d'un bloc arrondi), languette de cran ou logement de servo
        Xs = [(Rm @ _T(0, -ay, -az) @ np.array([x, ay, az, 1.0]))[0] for x in xs]   # position X des pattes apres pose
        sk = [1 if v > 0 else -1 for v in Xs]
        def chape(xc, larg=4.0):
            c_ = mf.Manifold.hull(mf.Manifold.cylinder(larg, rp, rp, 48).rotate((0, 90, 0)).translate((xc - larg / 2, AX_Y, AX_Z))
                                  + mf.Manifold.cube((larg, 8, 1), True).translate((xc, AX_Y - 6, ztop(AX_Y - 6) - 4)))
            c_ = c_ - mf.Manifold.cylinder(larg + 2, 1.7, 1.7, 24).rotate((0, 90, 0)).translate((xc - larg / 2 - 1, AX_Y, AX_Z))
            return c_ - logement                              # ne deborde jamais dans le logement de la plaque
        k_roue = 0
        if pivot in ("fixe", "crans"):
            gap0 = 2.9 if pivot == "crans" else 0.4
            socle = socle + chape(Xs[0] + sk[0] * (ep_p / 2 + gap0 + 2.0)) + chape(Xs[1] + sk[1] * (ep_p / 2 + 0.4 + 2.0))
            if pivot == "crans":
                xl, xg = Xs[k_roue] + sk[k_roue] * (ep_p / 2 + 1.25), Xs[k_roue] + sk[k_roue] * (ep_p / 2 + gap0 + 2.0)
                yl = AX_Y - (rp + 1.5 + 1.4)
                lame = mf.Manifold.cube((2.4, 1.4, 11), True).translate((xl, yl, AX_Z - 3.5))
                pont = mf.Manifold.cube((abs(xl - xg) + 1.5, 1.4, 2.4), True).translate(((xl + xg) / 2, yl, AX_Z - 8))
                bosse = mf.Manifold.sphere(0.9, 16).translate((xl, AX_Y - (rp + 1.5 + 0.45), AX_Z))
                socle = socle + ((lame + pont + bosse) - logement)
            q.append("Axe : 2 vis M3x16 + ecrous nylstop" + (" (serrage doux : les crans tiennent l'angle)" if pivot == "crans" else " (serrer fort)"))
        else:
            socle = socle + chape(Xs[0] + sk[0] * (ep_p / 2 + 2.4))
            sl, sw, sh, sf, se, sd = SERVOS[p.get("servo", "sg90")]
            d0 = abs(Xs[1]) + ep_p / 2 + 3.2
            zc = AX_Z - (sl / 2 - sd)
            bloc = galet(sh + 4, sw + 6, sl + 6, sl + 6, 3, 1.2).translate((d0 + sh / 2, AX_Y, zc - (sl + 6) / 2))
            bloc = bloc - mf.Manifold.cube((sh + 0.6, sw + 0.6, sl + 0.6), True).translate((d0 + sh / 2 + 0.01, AX_Y, zc))
            bloc = bloc - mf.Manifold.cube((3, sw + 0.6, sf + 0.6), True).translate((d0 + 0.5, AX_Y, zc))
            bloc = bloc - mf.Manifold.cylinder(6, 3.5, 3.5, 32).rotate((0, 90, 0)).translate((d0 - 3, AX_Y, AX_Z))
            socle = socle + (bloc.mirror((1, 0, 0)) if sk[1] < 0 else bloc)
            q += [f"Servo {p.get('servo', 'sg90').upper()} + palonnier en croix (coaxial au pivot)", "Axe libre : 1 vis M3x16 + ecrou nylstop"]
        pieces += [("cadre", cadre, pose_cadre), ("dos", dos, pose_dos)]
    else:
        q.append("ESP32 DevKit (ou ESP32-S3 Zero / Super Mini)")
    out, poses, noms = [], [], []
    for nom, s, T in pieces:
        out.append(vers_trimesh(s)); poses.append(T.tolist()); noms.append(nom)
    infos.update({"assemblage": poses, "noms": noms, "quincaillerie": q})
    return out, infos
