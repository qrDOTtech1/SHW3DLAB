"""Modes du DaVinBot : comportements autonomes, independants du backend (simulation ou reel).

prendre_outil  : aller au rack, plonger face contre face, verrouiller (bague 90 deg servo),
                 verifier l'identite de l'outil (EEPROM via pogo), sortir par la fourche, remonter.
deposer_outil  : inverse (glisser dans la fourche, remettre en prise, deverrouiller, remonter).
saisir         : prise laterale d'un objet avec la main, comme un humain (paume face a l'objet,
                 pre-ouverture, approche, fermeture en prise cylindrique, levee, verification).
poser          : depose de l'objet tenu a une position, ouverture, degagement.
peindre_cercle : trace au pinceau sur la toile.
mission_atelier: enchainement complet.
"""
from __future__ import annotations

import math

import numpy as np

DOWN = np.array([0.0, 0.0, -1.0])
X = np.array([1.0, 0.0, 0.0])


class ModeError(RuntimeError):
    pass


def _check(ok, msg):
    if not ok:
        raise ModeError(msg)


def _slot(r, tid):
    o = r.info["outils"][tid]
    return (np.array(o["slot"]), np.array(o.get("x", X), float),
            np.array(o.get("sortie", [0, 1, 0]), float) * o.get("course_sortie", 0.11))


def _lifts(r, tid):
    full = r.info["outils"][tid].get("longueur", 0.06) + 0.03
    return [h for h in (full, 0.22, 0.18, 0.14, 0.10, 0.06) if h <= full + 1e-9]


def prendre_outil(r, tid):
    r.say(f"[prendre_outil] {tid}")
    slot, X, S = _slot(r, tid)
    _check(r.mounted is None, "un outil est deja monte")
    ok = False
    for lift in _lifts(r, tid):                   # le plus haut degagement atteignable
        if r.ik_chain([slot + [0, 0, 0.07], slot + [0, 0, 0.004], slot + S, slot + S + [0, 0, lift]],
                      DOWN, X, starts=20) is not None:
            ok = True
            break
    _check(ok and r.move_to_chain([slot + [0, 0, 0.07], slot + [0, 0, 0.004], slot + S, slot + S + [0, 0, lift]],
                                  DOWN, X), "approche du rack impossible")   # tout le geste est suivable
    _check(r.move_linear(slot + [0, 0, 0.004], DOWN, X), "plongee impossible")
    r.move_linear(slot + [0, 0, -0.0005], DOWN, X, dist_step=0.002)       # contact face / face
    res = r.lock()
    r.say(f"  verrou : {res}")
    _check(res["ok"], f"verrouillage refuse ({res})")
    ident = r.read_tool_id()
    r.say(f"  EEPROM : outil {ident['id']} - {ident['nom']}")
    _check(ident and ident["id"] == tid, "outil inattendu")
    off = r.tcp() - r.face_pos()                  # outil monte : le TCP n'est plus la face
    out_y = slot + S + off                         # sortie radiale, vers le robot
    _check(r.move_linear(out_y, DOWN, X), "sortie de fourche impossible")
    # degagement vertical (le plus haut atteignable, retenu a l'approche)
    _check(r.move_linear(out_y + [0, 0, lift], DOWN, X), "degagement impossible")
    return ident


def deposer_outil(r, tid):
    r.say(f"[deposer_outil] {tid}")
    _check(r.mounted == tid, "outil non monte")
    slot, X, S = _slot(r, tid)
    if tid == "H":
        r.grip({"index": 0, "majeur": 0, "annulaire": 0, "auriculaire": 0, "pouce": 0, "opp": 0, "ecart": 0}, 0.5)
    off = r.tcp_offset(DOWN, X)                   # TCP outil par rapport a la face
    lift = next((h for h in _lifts(r, tid) if r.ik_chain([slot + S + [0, 0, h] + off, slot + S + off, slot + off],
                                                        DOWN, X, starts=20) is not None), 0.06)
    _check(r.move_to_chain([slot + S + [0, 0, lift] + off, slot + S + off, slot + off],
                           DOWN, X), "approche du rack impossible")
    _check(r.move_linear(slot + S + off, DOWN, X), "descente impossible")
    _check(r.move_linear(slot + off, DOWN, X), "insertion dans la fourche impossible")
    r.dock(tid)
    r.unlock()
    r.say("  deverrouille, outil en prise dans la fourche")
    _check(r.move_linear(slot + [0, 0, 0.07], DOWN, X), "degagement impossible")   # TCP = face (nue)


def _hand_frame(r, target, tilt_deg=0.0, flip=False, yaw_deg=0.0):
    """Orientation de la main pour une prise cylindrique laterale : paume face a l'objet, axe
    long de la main tangent a l'objet (les axes de flexion des doigts restent quasi paralleles
    a l'axe du cylindre -> les doigts s'enroulent autour), incline vers le bas de `tilt_deg`.
    `yaw_deg` fait tourner la direction d'approche autour de l'objet."""
    d = np.asarray(target[:2], float)
    d = d / np.linalg.norm(d)
    a = math.radians(yaw_deg)
    d = np.r_[math.cos(a) * d[0] - math.sin(a) * d[1], math.sin(a) * d[0] + math.cos(a) * d[1], 0.0]
    y = -d                                                 # -y outil = normale de la paume
    t = np.cross(np.array([0, 0, 1.0]), d)
    if flip:
        t = -t
    b = math.radians(tilt_deg)
    z = math.cos(b) * t + math.sin(b) * np.array([0, 0, -1.0])
    z /= np.linalg.norm(z)
    x = np.cross(y, z)
    return d, z, x


def _grasp_plans(r, c, obj, lift=0.08):
    """Cherche l'orientation de main pour laquelle approche, prise et levee sont atteignables
    sans collision (planification complete AVANT de bouger)."""
    cands = [(t, abs(yw), h, f, yw) for t in (0, 10, 20, 30) for yw in (0, -30, 30, -60, 60)
             for h in (0.045, 0.055, 0.035) for f in (True, False)]
    for tilt, _, hz, flip, yaw in sorted(cands, key=lambda c: (c[0], c[1])):
            grip_pt = c + np.array([0, 0, hz])
            d, z, x = _hand_frame(r, c, tilt, flip, yaw)
            pts = [grip_pt - d * 0.09 + [0, 0, 0.03], grip_pt - d * 0.09, grip_pt,
                   grip_pt + [0, 0, lift]]
            q, ok, qs = None, True, []
            for i, p in enumerate(pts):
                r.allow_touch(obj) if i >= 2 else r.allow_touch()      # l'objet n'est touche qu'a la prise
                q = r.ik(p, z, x, q0=q, starts=30 if q is None else 4)
                if q is None or np.min(r.lim - np.abs(q)) < math.radians(10) or                         (qs and not r.path_free(qs[-1], q)):          # garder du debattement
                    ok = False
                    break
                if i == 2:                                            # approche finale : aucun
                    r.allow_touch()                                   # contact avant les derniers
                    q85 = qs[-1] + (q - qs[-1]) * 0.70                # 30 % (~27 mm, marge 15 mm)
                    free = r.path_free(qs[-1], q85)
                    # pose finale main ouverte : elle doit ENVELOPPER l'objet sans le traverser
                    # (sinon un doigt ecarte le renverse avant que la paume n'arrive)
                    cl, r.clearance = r.clearance, 0.0
                    free = free and not r._collides(q, 0.003)
                    r.clearance = cl
                    r.allow_touch(obj)
                    if not free:
                        ok = False
                        break
                qs.append(q)
            r.allow_touch()
            if ok:
                yield (d, z, x, grip_pt, qs,
                       f"hauteur +{hz * 1000:.0f} mm, main inclinee {tilt} deg, approche {yaw:+d} deg"
                       f"{' (pouce en haut)' if flip else ''}")


PRISE_CYL = {"index": 0.62, "majeur": 0.62, "annulaire": 0.62, "auriculaire": 0.62,
             "pouce": 0.55, "opp": 0.85, "ecart": -0.2}


def saisir(r, obj="gobelet", prise=None):
    r.say(f"[saisir] {obj}")
    _check(r.mounted == "H", "la DaVinHand n'est pas montee")
    prise = prise or PRISE_CYL
    gc = r.grasp_center(prise)                    # la ou les doigts se referment reellement
    r.set_tcp("H", gc)
    r.say(f"  centre de prise (repere main) : {np.round(gc * 1000).tolist()} mm")
    r.grip({"index": 0.05, "majeur": 0.05, "annulaire": 0.05, "auriculaire": 0.05, "pouce": 0.0,
            "opp": 0.0, "ecart": 0.3}, 0.6)       # pre-forme : pouce ecarte sur le cote (hors trajectoire)
    tried = 0
    for plan in _grasp_plans(r, r.object_pos(obj), obj):
        if tried >= 4:
            break
        tried += 1
        d, z, x, grip_pt, qs, desc = plan
        r.say(f"  essai {tried} : {desc}")
        r.grasp_frame = (z, x)
        if not r.transit(qs[0]) or not r.move_path(qs[1], speed=0.4):
            r.say("  ! approche non executable, plan suivant")
            continue
        r.allow_touch(obj)
        if not r.move_path(qs[2], speed=0.25):
            r.say("  ! approche finale bloquee, recul")
            r.move_path(qs[1], speed=0.3)
            r.allow_touch()
            continue
        r.grip(prise, 1.2)
        r.wait(0.4)
        touch = r.touching(obj)                         # capteurs de contact (pulpes / phalanges)
        r.say(f"  contacts : {', '.join(sorted(touch)) or 'aucun'}")
        z0 = r.object_pos(obj)[2]
        if "pouce" in touch and len(touch - {"pouce", "paume"}) >= 2:
            r.move_path(qs[3], speed=0.3)
            r.wait(0.5)
            dz = r.object_pos(obj)[2] - z0
            r.say(f"  objet leve de {dz * 1000:.0f} mm")
            if dz > 0.05:
                return {"leve_mm": round(dz * 1000, 1), "essais": tried}
            r.move_linear(r.tcp() - [0, 0, max(dz, 0.0) - 0.002], z, x)   # on repose avant de lacher
        # prise ratee : on rouvre (pouce toujours oppose), on recule, on replanifie
        r.grip({"index": 0.0, "majeur": 0.0, "annulaire": 0.0, "auriculaire": 0.0, "pouce": 0.0,
                "opp": prise["opp"], "ecart": 0.0}, 0.6)
        back = r.ik(r.tcp() - d * 0.09 + [0, 0, 0.04], z, x, q0=r.q(), starts=4)
        if back is not None:
            r.move_path(back, speed=0.3)
        r.allow_touch()
        r.grip({"opp": 0.0, "ecart": 0.3}, 0.5)
        r.say("  prise ratee, nouvel essai")
    raise ModeError(f"saisie impossible apres {tried} essais")


def _plan_chain(r, pts, z, x, obj=None):
    """IK + verification de collision d'une suite de points (orientation fixe), a partir de la
    configuration courante. Renvoie la liste des configurations ou None."""
    q, qs = r.q(), []
    r.allow_touch(*( [obj] if obj else []))
    try:
        for p in pts:
            qn = r.ik(p, z, x, q0=q, starts=4)
            if qn is None or not r.path_free(q, qn):
                return None
            qs.append(qn)
            q = qn
        return qs
    finally:
        r.allow_touch()


def _release_options(t, d):
    return ([t - d * 0.08, t - d * 0.08 + [0, 0, 0.06]],                 # recul puis montee
            [t + [0, 0, 0.03], t + [0, 0, 0.03] - d * 0.08, t - d * 0.08 + [0, 0, 0.08]],
            [t + [0, 0, 0.10]])                                           # sinon : a la verticale


def _place_plan(r, obj, pos):
    """Verifie AVANT de transporter qu'on peut poser a `pos` puis degager la main (IK sans
    collision de chaque etape). Renvoie la cible TCP ou None."""
    c = r.object_pos(obj)
    off = r.tcp() - c
    z, x = r.grasp_frame
    d = -np.cross(z, x)
    d /= np.linalg.norm(d)
    tgt = np.asarray(pos) + off
    r.allow_touch(obj)
    try:
        q = r.ik(tgt + [0, 0, 0.05], z, x, starts=20)
        if q is None:
            return None
        q = r.ik(tgt + [0, 0, 0.004], z, x, q0=q, starts=4)
        if q is None:
            return None
        for pts in _release_options(tgt + [0, 0, 0.004], d):
            qq, ok = q, True
            for p in pts:
                qn = r.ik(p, z, x, q0=qq, starts=4)
                if qn is None or not r.path_free(qq, qn):
                    ok = False
                    break
                qq = qn
            if ok:
                return tgt
        return None
    finally:
        r.allow_touch()


def choisir_depose(r, obj, souhait, rayon=0.10):
    """Comme un humain : si l'endroit voulu est inconfortable, on pose a cote (au plus pres)."""
    souhait = np.asarray(souhait, float)
    cands = [souhait] + [souhait + rr * np.array([math.cos(a), math.sin(a), 0.0])
                         for rr in (0.04, 0.07, rayon) for a in np.radians(np.arange(0, 360, 45))]
    for p in cands:
        if _place_plan(r, obj, p) is not None:
            if np.linalg.norm(p - souhait) > 1e-6:
                r.say(f"  depose decalee de {np.linalg.norm(p - souhait) * 1000:.0f} mm (endroit voulu inatteignable proprement)")
            return p
    return None


def poser(r, obj, pos):
    r.say(f"[poser] {obj}")
    p = choisir_depose(r, obj, pos)
    _check(p is not None, "aucun endroit de depose atteignable autour de la cible")
    c = r.object_pos(obj)
    off = r.tcp() - c
    z, x = r.grasp_frame                                   # on garde l'orientation de la prise
    d = -np.cross(z, x)
    d = d / np.linalg.norm(d)                              # direction paume -> objet
    tgt = p + off
    r.allow_touch(obj)                                     # l'objet tenu voyage avec la main
    # transport comme un humain : on garde la hauteur de levee, on translate, on redescend
    h = max(r.tcp()[2], tgt[2] + 0.05)
    _check(r.move_linear(np.r_[r.tcp()[:2], h], z, x, check=True), "transport impossible (montee)")
    _check(r.move_linear(np.r_[tgt[:2], h], z, x, check=True), "transport impossible")
    _check(r.move_linear(tgt + [0, 0, 0.004], z, x, check=True), "depose impossible")
    r.grip({"index": 0.0, "majeur": 0.0, "annulaire": 0.0, "auriculaire": 0.0, "pouce": 0.0,
            "opp": PRISE_CYL["opp"], "ecart": 0.0}, 0.8)   # doigts ouverts ; le pouce s'etend mais
    #                                                        reste oppose (sinon il balaie l'objet)
    r.wait(0.3)
    for pts in _release_options(r.tcp(), d):
        qs = _plan_chain(r, pts, z, x, obj)
        if qs:
            r.allow_touch(obj)
            for q in qs:
                r.move_path(q, speed=0.4)
            r.allow_touch()
            r.grip({"opp": 0.0}, 0.5)                         # main degagee : pouce remis en repos
            break
    else:
        r.allow_touch()
        raise ModeError("degagement impossible")
    err = np.linalg.norm(r.object_pos(obj)[:2] - np.asarray(pos)[:2]) * 1000
    r.say(f"  objet pose a {err:.0f} mm de l'endroit demande, main degagee")
    return {"ecart_mm": round(err, 1)}


def peindre_cercle(r, center, rayon=0.03, z_surf=0.03, inclinaison=12.0):
    """Trace au pinceau. Pinceau tenu legerement incline (comme un peintre) : pinceau vertical =
    J5 ~ 0 = singularite du poignet (J4 et J6 alignes). Orientation figee sur tout le trace."""
    r.say("[peindre_cercle]")
    _check(r.mounted == "P", "le porte-pinceau n'est pas monte")
    c = np.asarray(center, float)
    radial = np.r_[c[:2] / np.linalg.norm(c[:2]), 0.0]
    tang = np.cross(np.array([0, 0, 1.0]), radial)
    p0 = np.r_[c[:2] + [rayon, 0], z_surf + 0.002]
    trace = [np.r_[c[:2] + rayon * np.array([math.cos(t), math.sin(t)]), z_surf + 0.002]
             for t in np.linspace(0, 2 * math.pi, 25)[1:]]
    zt = xt = None
    for v, nom in ((-radial, "pointe vers l'exterieur"), (tang, "de cote"), (radial, "pointe vers la base")):
        for deg in (inclinaison, 20.0, 8.0, 30.0):
            a = math.radians(deg)
            z_ = math.cos(a) * DOWN + math.sin(a) * v
            x_ = tang - np.dot(tang, z_) * z_
            if np.linalg.norm(x_) < 0.3:
                x_ = radial - np.dot(radial, z_) * z_
            x_ /= np.linalg.norm(x_)
            if r.ik_chain([p0 + [0, 0, 0.04], p0] + trace, z_, x_, starts=20) is not None:
                zt, xt = z_, x_
                r.say(f"  pinceau incline de {deg:.0f} deg, {nom}")
                break
        if zt is not None:
            break
    _check(zt is not None, "aucune orientation du pinceau ne permet le trace complet")
    _check(r.move_to_chain([p0 + [0, 0, 0.04], p0] + trace, zt, xt), "approche de la toile impossible")
    r.move_linear(p0, zt, xt)
    errs, rates = [], 0
    for t in np.linspace(0, 2 * math.pi, 72):
        p = np.r_[c[:2] + rayon * np.array([math.cos(t), math.sin(t)]), z_surf + 0.002]
        if not r.move_linear(p, zt, xt, dist_step=0.004):
            rates += 1
        tcp = r.tcp()
        errs.append(np.linalg.norm(tcp[:2] - p[:2]))              # ecart a la CONSIGNE du point
    r.move_linear(r.tcp() + [0, 0, 0.05], zt, xt)
    rms = float(np.sqrt(np.mean(np.square(errs)))) * 1000
    r.say(f"  cercle trace : {72 - rates}/72 points atteints, erreur RMS {rms:.2f} mm")
    return {"rms_mm": round(rms, 2), "points_atteints": 72 - rates}


def repos(r):
    r.say("[repos]")
    r.transit(np.zeros(6))


def mission_atelier(r):
    """Prend la main, deplace le gobelet sur la toile, range la main, prend le pinceau,
    trace un cercle, range le pinceau, retour au repos."""
    res = {}
    gob0 = r.object_pos("gobelet").copy()                 # position de repos (sur la table)
    canvas = np.array(r.info.get("present", [0.3, 0, 0.3]))
    toile = np.array([r.info["board"][0] - 0.02, -0.06, r.info["board"][2]])
    steps = [
        ("prendre la main", lambda: prendre_outil(r, "H")),
        ("saisir le gobelet", lambda: saisir(r, "gobelet")),
        ("poser le gobelet", lambda: poser(r, "gobelet", gob0 + [0.0, -0.12, 0.0])),
        ("ranger la main", lambda: deposer_outil(r, "H")),
        ("prendre le pinceau", lambda: prendre_outil(r, "P")),
        ("peindre", lambda: peindre_cercle(r, r.info["canvas_center"] if "canvas_center" in r.info else toile[:2],
                                           z_surf=r.info.get("surface_z", 0.03))),
        ("ranger le pinceau", lambda: deposer_outil(r, "P")),
        ("repos", lambda: repos(r)),
    ]
    for name, fn in steps:
        r.stage = name
        try:
            res[name] = fn() or "ok"
        except ModeError as e:
            r.say(f"  ECHEC : {e}")
            res[name] = f"ECHEC : {e}"
            break
    return res
