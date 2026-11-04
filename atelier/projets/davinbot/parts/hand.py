"""DaVinHand - main anthropomorphe a architecture osseuse humaine (echelle reglable).

Anatomie reprise (longueurs osseuses adultes moyennes, mm, echelle 1) :
  doigt        metacarpe  P1   P2   P3
  index           68      40   23   18
  majeur          65      44   27   19
  annulaire       58      41   26   19
  auriculaire     53      33   19   17
  pouce           46      32   --   25   (2 phalanges)
* Metacarpes en eventail (ecartement -9/0/+7/+15 deg) et ARCHE TRANSVERSALE : les tetes
  metacarpiennes de l'annulaire et de l'auriculaire sont abaissees et avancees cote paume.
* Articulations MCP, PIP, DIP : vraies charnieres (tenon/chape + axe acier d2), butees
  mecaniques 0..90 / 0..100 / 0..80 deg.
* Flechisseurs : 1 tendon Kevlar par doigt (canal palmaire continu) -> sous-actionnement
  naturel PIP/DIP ; extension par cordon elastique dorsal.
* POUCE : articulation carpo-metacarpienne (CMC) sur un axe OBLIQUE (trapeze) motorise =
  OPPOSITION, puis flexion MC, MCP et IP par tendon. En opposition la pulpe du pouce
  rejoint la pulpe de l'index / du majeur (pince pulpaire).
* 6 micro pas-a-pas dans la paume (4 flechisseurs + flechisseur du pouce + opposition),
  electronique (LiPo 1S + ESP32-C3) dans le poignet, base de couplage standard (pogo).
Repere outil : +Z vers le bout des doigts, paume (face palmaire) vers -Y, pouce cote -X.
"""
from __future__ import annotations

import math

import cadquery as cq
import numpy as np

from ..cad.util import (SCREW, box, cyl, cone, tube, union_all, cut_all, fuse_all, apply_T,
                        frame_z_to, T as Tm, rot_matrix)
from .effector import tool_base

BONES = {  # nom : (metacarpe, P1, P2, P3, ecartement deg, largeur, hauteur MCP relative, arche)
    "index": (68, 40, 23, 18, -9.0, 17.0, 0.0, 0.0),
    "majeur": (65, 44, 27, 19, 0.0, 17.5, 2.0, 0.0),
    "annulaire": (58, 41, 26, 19, 7.0, 16.5, -3.0, -3.0),
    "auriculaire": (53, 33, 19, 17, 15.0, 14.5, -11.0, -7.0),
}
THUMB = (46, 32, 25)
PIN_D = 2.0
FINGER_MAX = (85, 100, 75)          # MCP, PIP, DIP (deg)
THUMB_MAX = (30, 55, 75)            # CMC flexion, MCP, IP
OPP_MAX = 75.0                      # rotation d'opposition du trapeze
# ecartement (abduction MCP) pour ecart = +1 ; ecart = -1 -> adduction (pince interdigitale)
SPREAD_MAX = {"index": -18.0, "majeur": 0.0, "annulaire": 10.0, "auriculaire": 20.0}


def _rot(axis, deg):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def fk(joints, ctrl, p):
    """Point (pose de repos) apres rotation de la chaine : M = R0 R1 ... Rn (proximal -> distal)."""
    p = np.asarray(p, float)
    for j in reversed(joints):
        v = ctrl.get(j.get("ctrl"), 0.0)
        R = _rot(j["a"], j["max"] * v)
        o = np.asarray(j["o"], float)
        p = o + R @ (p - o)
    return p


def _pad_point(joints, d, L3, t3):
    o = np.asarray(joints[-1]["o"], float)
    h = np.asarray(joints[-1]["a"], float)
    pal = np.cross(h, d)
    return o + d * (L3 - (t3 / 2 - 0.5)) + pal * (t3 / 2)


def thumb_geometry(cmc, s, az, el, gam, target, mcf=0.60):
    """Pouce : pivot d'opposition oblique (gam), direction de repos (az radial, el palmaire)."""
    a_opp = np.array([math.sin(math.radians(gam)) * 0.8, -math.sin(math.radians(gam)) * 0.6,
                      math.cos(math.radians(gam))])
    a_opp /= np.linalg.norm(a_opp)
    d = np.array([-math.sin(math.radians(az)) * math.cos(math.radians(el)), -math.sin(math.radians(el)),
                  math.cos(math.radians(az)) * math.cos(math.radians(el))])
    d /= np.linalg.norm(d)
    pos0 = cmc + a_opp * 8 * s + d * 6 * s
    # flexion vers la paume (sous le majeur) : (h x d) pointe vers la cible
    h = np.cross(d, target - pos0)
    h /= np.linalg.norm(h)
    L = (THUMB[0] * mcf * s, THUMB[1] * s, THUMB[2] * s)
    return {"a_opp": a_opp, "d": d, "h": h, "pos0": pos0, "L": L, "az": az, "el": el, "gam": gam,
            "mcf": mcf, "cmc": cmc}


def thumb_joints(th, cmc):
    js = [{"o": cmc, "a": th["a_opp"], "max": OPP_MAX, "ctrl": "opp"}]
    pos = th["pos0"]
    for k, L in enumerate(th["L"]):
        js.append({"o": pos, "a": th["h"], "max": THUMB_MAX[k], "ctrl": "pouce"})
        pos = pos + th["d"] * L
    return js


def tune_thumb(cmc, s, t_th, w_th, finger_chains, Tp):
    """Geometrie du pouce qui reussit le test d'opposition de Kapandji : pulpe du pouce au
    contact de la pulpe de chaque doigt (distance < 4 mm), recherche exhaustive."""
    grid = np.linspace(0, 1, 11)
    target = finger_chains["majeur"][0][0] + np.array([4.0, -Tp * 1.2, -6.0])
    best = None
    fpads, fctl = {}, {}
    for n, ((head, d, lens, w), fj) in finger_chains.items():
        fpad = _pad_point(fj, d, lens[2], Tp * 0.52 - 2.4)
        # tendon sous-actionne : la flexion se repartit librement entre MCP et PIP/DIP
        fjs = [dict(j) for j in fj]
        for j in fjs[-3:]:
            j["ctrl"] = n + "_d"
        fjs[-3]["ctrl"] = n + "_m"
        if len(fjs) == 4:
            fjs[0]["ctrl"] = n + "_m"
        pts, ctl = [], []
        for cm in grid:
            for cd in grid:
                pts.append(fk(fjs, {n + "_m": cm, n + "_d": cd}, fpad))
                ctl.append((cm, cd))
        fpads[n] = np.array(pts)
        fctl[n] = ctl
    import itertools

    def candidates():
        yield from itertools.product((20, 35, 50, 65), (15, 30, 45, 60), (15, 35, 55, 75),
                                     (0.5, 0.65, 0.8), (-6, 4, 14), (0, 10))

    def evaluate(cands):
        nonlocal best
        for az, el, gam, mcf, dz, dx in cands:
                    c0 = cmc + np.array([dx * s, 0.0, dz * s])
                    th = thumb_geometry(c0, s, az, el, gam, target, mcf)
                    js = thumb_joints(th, c0)
                    tpad = _pad_point(js, th["d"], th["L"][2], t_th - 2.0)
                    TP = np.array([[fk(js, {"opp": o, "pouce": c}, tpad) for c in grid] for o in grid])
                    res, score = {}, 0.0
                    for n, FP in fpads.items():
                        D = np.linalg.norm(TP[:, :, None, :] - FP[None, None, :, :], axis=-1)
                        i, j, k = np.unravel_index(np.argmin(D), D.shape)
                        cm, cd = fctl[n][k]
                        res[n] = {"distance_mm": round(float(D[i, j, k]), 1), "opp": float(grid[i]),
                                  "pouce": float(grid[j]), n: float((cm + cd) / 2),
                                  "flexion_MCP": float(cm), "flexion_PIP_DIP": float(cd)}
                        score += (D[i, j, k] < 4.0) * 10 - min(D[i, j, k], 40) * 0.1
                    if best is None or score > best[0]:
                        best = (score, th, res)

    evaluate(candidates())
    step = {"az": 7.5, "el": 7.5, "gam": 10.0, "mcf": 0.075, "dz": 5.0, "dx": 5.0}
    for _ in range(3):
        th0 = best[1]
        c0 = th0["cmc"] - cmc
        base = (th0["az"], th0["el"], th0["gam"], th0["mcf"], c0[2] / s, c0[0] / s)
        grid_l = [(v - st, v, v + st) for v, st in zip(base, step.values())]
        evaluate(itertools.product(*grid_l))
        step = {k: v / 2 for k, v in step.items()}
    return {"th": best[1], "kapandji": best[2]}, best[2]


def _rounded_box(w, t, L, r):
    b = cq.Workplane("XY").box(w, t, L, centered=(True, True, False))
    try:
        b = b.edges("|Z").fillet(min(r, w / 2 - 0.3, t / 2 - 0.3))
    except Exception:
        pass
    return b


def phalanx(L, w, t, tol, proximal="tongue", distal="clevis", tip=False, r_prev=None):
    """Phalange dans son repere : z de l'axe proximal (z=0) a l'axe distal (z=L),
    x = axe des charnieres, y dorsal. Tenon proximal / chape distale."""
    r = t / 2 - 0.5
    tongue = w * 0.42
    # le corps pleine largeur commence apres le debattement de la chape precedente
    z0 = max(r, (r_prev if r_prev is not None else r)) + 0.8 if proximal == "tongue" else 0.0
    body = _rounded_box(w, t, max(L - r - z0, 1.0), 2.5).translate((0, 0, z0))
    parts = [body]
    cut = []
    if proximal == "tongue":
        parts.append(box(-tongue / 2, tongue / 2, -t / 2, t / 2, 0, z0 + 0.5))
        parts.append(cyl(t - 1.0, tongue, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((-tongue / 2, 0, 0)))
        cut.append(cyl(PIN_D + tol, w + 2, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((-w / 2 - 1, 0, 0)))
    if distal == "clevis" and not tip:
        cheek = (w - tongue) / 2 - tol
        for sx in (-1, 1):
            x0 = sx * (tongue / 2 + tol)
            x1 = sx * (w / 2)
            parts.append(box(min(x0, x1), max(x0, x1), -t / 2, t / 2, L - r - 0.5, L))
            parts.append(cyl(t - 1.0, abs(x1 - x0), 0).rotate((0, 0, 0), (0, 1, 0), 90)
                         .translate((min(x0, x1), 0, L)))
        cut.append(cyl(PIN_D - 0.1, w + 2, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((-w / 2 - 1, 0, L)))
        # butee dorsale (limite d'hyperextension) : la chape deborde cote dos
        parts.append(box(-w / 2, w / 2, t / 2 - 1.6, t / 2, L - r - 1.5, L - r + 0.5))
    if tip:
        pad = cq.Workplane("XY").sphere(w / 2 - 0.5).translate((0, -0.8, L - r))
        pad = pad.intersect(box(-w, w, -t, t, z0, L + w))      # hors du debattement de la chape
        parts.append(pad)
        # ongle (plat dorsal) + ancrage du tendon (trou transversal)
        cut.append(box(-w / 2, w / 2, t / 2 - 0.6, t, L - r - 4, L + 10))
        cut.append(cyl(1.4, w + 2, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((-w / 2 - 1, -t / 2 + 2.6, L - r - 3)))
    shape = fuse_all(parts)
    # canal flechisseur (palmaire) + canal extenseur (dorsal)
    cut.append(cyl(1.7, L + 4, -2, 0, -t / 2 + 2.6))
    cut.append(cyl(1.3, L + 4, -2, 0, t / 2 - 2.2))
    # espace de rotation de la phalange suivante dans la chape
    if distal == "clevis" and not tip:
        cut.append(box(-tongue / 2 - tol, tongue / 2 + tol, -t, t, L - r - 0.3, L + r + 2))
    return cut_all(shape, cut)


def build_hand(cfg: dict, g, tol: float) -> tuple[list, dict]:
    """Retourne [(id, libelle, forme_repere_outil, kwargs)] et la meta de l'outil H."""
    s = cfg["hand_scale"]
    base, cutters, Dt, t0 = tool_base(g, cfg, eeprom=True)
    out = []
    md, ml = cfg["hand_motor_d"], cfg["hand_motor_l"]
    bat = (cfg["hand_bat_w"], cfg["hand_bat_l"], cfg["hand_bat_t"])

    # ------------------------------------------------------------------ poignet (electronique)
    Wr, Tr = 58.0 * s, 34.0 * s
    Hr = 40.0 + 2 * md + 16.0                      # baie electronique + 5 flechisseurs (3 + 2)
    zw0 = t0
    wrist = _rounded_box(Wr, Tr, Hr, 8).translate((0, 0, zw0))
    wrist = fuse_all([wrist, cone(Dt - 4, Wr * 0.95, 6.0, zw0 - 0.01)])
    bay = box(-Wr / 2 + 2.4, Wr / 2 - 2.4, -Tr / 2 + 2.4, Tr / 2 + 1, zw0 + 3, zw0 + Hr + 1)
    # ------------------------------------------------------------------ paume (carpe + metacarpes)
    W, Tp = 84.0 * s, 30.0 * s
    zp0 = zw0 + Hr                                 # ligne du carpe
    L_carpe = 14.0 * s
    mcp = {}
    xs = {"index": -27.0, "majeur": -8.5, "annulaire": 9.5, "auriculaire": 26.0}
    blocks = [_rounded_box(W, Tp, L_carpe + 1, 7).translate((0, 0, zp0 - 1))]
    fingers_T = {}
    cardans = {}
    mc5 = {"blocks": []}
    for name, (mc, p1, p2, p3, spl, w, dz, arch) in BONES.items():
        w *= s
        x = xs[name] * s
        zc = zp0 + L_carpe
        # tete metacarpienne (MCP) : longueur du metacarpe depuis le carpe, eventail + arche
        a = math.radians(spl)
        head = np.array([x + math.sin(a) * mc * s * 0.55, arch * s, zc + mc * s * 0.55 + dz * s])
        d = np.array([math.sin(a), 0.0, math.cos(a)])
        fingers_T[name] = (head, d, (p1 * s, p2 * s, p3 * s), w)
        # metacarpe : poutre du carpe a la tete, clevis de MCP au bout
        base_pt = np.array([x, 0.0, zc - 2])
        L = float(np.linalg.norm(head - base_pt))
        dirv = (head - base_pt) / L
        F = frame_z_to(dirv, (1, 0, 0), base_pt)
        t_f = Tp * 0.52
        met = _rounded_box(w + 1.5, Tp - 2, L - (t_f / 2 - 0.5), 4)
        dest = mc5["blocks"] if name == "auriculaire" else blocks
        if name == "auriculaire":
            mc5.update(base=base_pt, F=F, L=L, w=w)
        dest.append(apply_T(met, F))
        # chape MCP (2 joues) + butee dorsale
        r = t_f / 2 - 0.5
        tongue = w * 0.42
        FL = frame_z_to(d, (math.cos(a), 0, -math.sin(a)), head)
        # CARDAN MCP (2 ddl) : chape de flexion portee par un moyeu qui pivote sur un axe
        # palmaire (Y) -> ecartement / serrage lateral des doigts
        cparts = []
        for sx in (-1, 1):
            x0, x1 = sx * (tongue / 2 + tol), sx * (w / 2 + 0.75)
            cparts.append(fuse_all([box(min(x0, x1), max(x0, x1), -t_f / 2, t_f / 2, -r - 2, 0),
                                    cyl(t_f - 1.0, abs(x1 - x0), 0).rotate((0, 0, 0), (0, 1, 0), 90)
                                    .translate((min(x0, x1), 0, 0))]))
        cparts.append(box(-w / 2 - 0.75, w / 2 + 0.75, -t_f / 2, t_f / 2, -r - 10, -r - 1.5))
        cparts.append(cyl(9.0, t_f, -t_f / 2).rotate((0, 0, 0), (1, 0, 0), -90).translate((0, 0, -r - 6)))
        o_ab = head - d * (r + 6)
        card = cut_all(fuse_all(cparts), [
            cyl(PIN_D + tol, t_f + 4, -t_f / 2 - 2).rotate((0, 0, 0), (1, 0, 0), -90).translate((0, 0, -r - 6)),
            cyl(PIN_D - 0.1, w + 4, 0).rotate((0, 0, 0), (0, 1, 0), 90).translate((-w / 2 - 2, 0, 0)),
            box(-w * 0.21 - tol, w * 0.21 + tol, -t_f, t_f, -r - 0.5, t_f),
            cyl(1.8, 30, -20, 0, -t_f / 2 + 2.6)])
        cardans[name] = (apply_T(card, FL), o_ab, "mc5" if name == "auriculaire" else "palm", FL, r, t_f, w)
    palm = fuse_all(blocks)
    # eminence thenar : console du trapeze (CMC du pouce), cote radial (-X) et paume (-Y)
    cmc = np.array([-W / 2 + 10 * s, -Tp / 2 - 4 * s, zp0 + 6 * s])
    a_opp = np.array([0.35, -0.25, 0.90])
    a_opp /= np.linalg.norm(a_opp)
    Fo = frame_z_to(a_opp, (1, 0, 0), cmc)
    thenar = apply_T(fuse_all([cyl(20 * s, 12 * s, -12 * s)]), Fo)
    palm = fuse_all([palm, thenar, wrist, base])
    # cavite des 6 moteurs-treuils (dos ouvert, capot) : 2 rangees de 3, axes selon Y
    # MODULE POIGNET : les 6 moteurs-treuils sont dans le poignet (comme les muscles de
    # l'avant-bras) -> paume legere, moment reduit sur l'axe 6, tendons dans des gaines
    motors = []
    for x, z in ((-19.0, zw0 + 40 + md / 2), (0.0, zw0 + 40 + md / 2), (19.0, zw0 + 40 + md / 2),
                 (1.0, zw0 + 44 + 1.5 * md), (18.5, zw0 + 44 + 1.5 * md)):
        motors.append(np.array([x * s, -Tr / 2 + 2.4, z]))
    cav = box(-W / 2 + 3, W / 2 - 3, -Tp / 2 + 2.4, Tp / 2 + 1, zp0 - 6, zp0 + L_carpe + 6)
    pcut = cutters + [bay, cav, cyl(12, 30, zw0 - 5)]
    # axes de charniere MCP + canaux flechisseurs (carpe -> tetes metacarpiennes)
    for name, (head, d, lens, w) in fingers_T.items():
        a = math.atan2(d[0], d[2])
        FL = frame_z_to(d, (math.cos(a), 0, -math.sin(a)), head)
        t_f = Tp * 0.52
        pcut.append(apply_T(cyl(1.8, 70, -60, 0, -t_f / 2 + 2.6), FL))
    # 5e metacarpe : piece separee articulee a sa base (flexion + rotation vers le pouce)
    a5 = np.array([1.0, -0.5, 0.0])
    a5 /= np.linalg.norm(a5)
    F5 = frame_z_to(a5, (0, 0, 1), mc5["base"])
    mc5_part = fuse_all(mc5["blocks"] + [apply_T(cyl(10 * s, mc5["w"] + 2, -(mc5["w"] + 2) / 2), F5)])
    mc5_cut = [pcut[-1], apply_T(cyl(PIN_D + tol, 60, -30), F5)]
    env5 = apply_T(_rounded_box(mc5["w"] + 3.5, Tp + 2, mc5["L"] + 12, 4).translate((0, 0, -6)), mc5["F"])
    pcut.append(env5)
    pcut.append(apply_T(cyl(10 * s + 1.2, mc5["w"] + 3, -(mc5["w"] + 3) / 2), F5))
    mc5_part = cut_all(mc5_part, mc5_cut)
    j_cmc5 = {"o": mc5["base"].round(3).tolist(), "a": a5.round(5).tolist(), "max": 22.0,
              "ctrl": "auriculaire"}
    pcut.append(apply_T(cyl(3.0 + tol, 40, -20), Fo))                       # axe d'opposition d3
    pcut.append(apply_T(cyl(22 * s, 60 * s, 0.01), Fo))                     # debattement du trapeze + pouce
    palm = cut_all(palm, pcut)
    palm = fuse_all([palm, apply_T(cyl(PIN_D + 6, mc5["w"] + 10, -(mc5["w"] + 10) / 2), F5)])
    # le bossage est dans la CAVITE de la paume (creuse) : ses deux extremites ne touchaient rien ->
    # l'axe du 5e metacarpe n'etait tenu par rien. Une jambe d8 relie chaque extremite a la paroi palmaire.
    for sgn in (-1.0, 1.0):
        c_end = (F5 @ np.array([0.0, 0.0, sgn * (mc5["w"] + 6.5) / 2, 1.0]))[:3]
        y_wall = -Tp / 2 + 1.0
        # seulement l'extremite cote CAVITE (l'autre s'appuie deja sur la paroi laterale)
        if abs(c_end[0]) < W / 2 - 10.0 and c_end[1] - y_wall > 1.0:
            leg = cyl(PIN_D + 6, c_end[1] - y_wall + 1.0, 0).rotate((0, 0, 0), (1, 0, 0), -90)                 .translate((c_end[0], y_wall, c_end[2]))
            palm = fuse_all([palm, leg])
    palm = cut_all(palm, [env5, apply_T(cyl(10 * s + 1.2, mc5["w"] + 3, -(mc5["w"] + 3) / 2), F5),
                          apply_T(cyl(PIN_D - 0.1, 60, -30), F5)])
    i_palm = next(i for i, pp in enumerate(out) if pp[0] == "paume") if any(pp[0] == "paume" for pp in out) else None
    out.append(("metacarpe_V", "5e metacarpe articule (hypothenar : creusement de la paume)", mc5_part,
                dict(category="tool", anim={"type": "chain", "joints": [j_cmc5]},
                     notes="Pivote de 22 deg avec l'auriculaire : permet au petit doigt de rejoindre le pouce.")))
    palm = cut_all(palm, [mc5_part])
    for name, (cw, o_ab, host, FLc, rc, tfc, wc) in cardans.items():
        sweep, pin = [], None
        for ang in np.linspace(-abs(SPREAD_MAX[name]) - 3, abs(SPREAD_MAX[name]) + 3, 5):
            R = np.eye(4)
            R[:3, :3] = _rot((0, 1, 0), ang)
            R[:3, 3] = o_ab - R[:3, :3] @ o_ab
            sweep.append(apply_T(cw, R))
        sweep = [apply_T(sh, np.eye(4)) for sh in sweep]
        pin = apply_T(cyl(PIN_D - 0.1, 60, -30), frame_z_to((0, 1, 0), (1, 0, 0), o_ab))
        grow = [apply_T(sh, np.diag([1, 1, 1, 1.0])) for sh in sweep]
        if host == "mc5":
            mc5_part = cut_all(mc5_part, grow + [pin])
        else:
            palm = cut_all(palm, grow + [pin])
        out.append((f"{name}_cardan", f"{name} - cardan MCP (flexion + ecartement)", cw,
                    dict(category="output", anim={"type": "chain", "joints": [dict(j) for j in
                         ([j_cmc5] if name == "auriculaire" else []) + [
                         {"o": o_ab.round(3).tolist(), "a": [0.0, 1.0, 0.0], "max": SPREAD_MAX[name] or 0.001,
                          "ctrl": "ecart"}]]},
                         notes="Axe acier d2 selon la normale a la paume.")))
    i_mc5 = next(i for i, pp in enumerate(out) if pp[0] == "metacarpe_V")
    q = out[i_mc5]
    out[i_mc5] = (q[0], q[1], mc5_part, q[3])
    out.append(("paume", "paume (carpe + metacarpes en eventail, arche transversale)", palm,
                dict(category="tool", notes="PETG 40 %. Module poignet : 6 micro pas-a-pas + LiPo + ESP32-C3.")))
    cover = box(-W / 2 + 3.2, W / 2 - 3.2, Tp / 2 - 1.8, Tp / 2 + 0.6, zp0 - 5, zp0 + L_carpe + 5)
    out.append(("capot_dos", "capot dorsal (poulies de renvoi des tendons)", cover, dict(category="cap")))
    wcover = box(-Wr / 2 + 2.6, Wr / 2 - 2.6, Tr / 2 - 1.8, Tr / 2 + 0.6, zw0 + 4, zw0 + Hr - 7)
    out.append(("capot_poignet", "capot du module poignet (6 moteurs, LiPo, ESP32-C3, USB-C)", wcover,
                dict(category="cap")))

    # ------------------------------------------------------------------ doigts
    chains = {}
    for name, (head, d, (l1, l2, l3), w) in fingers_T.items():
        a = math.atan2(d[0], d[2])
        hinge = np.array([math.cos(a), 0.0, -math.sin(a)])
        t_f = Tp * 0.52
        joints = [dict(j_cmc5)] if name == "auriculaire" else []
        joints.append({"o": cardans[name][1].round(3).tolist(), "a": [0.0, 1.0, 0.0],
                       "max": SPREAD_MAX[name] or 0.001, "ctrl": "ecart"})
        pos = head.copy()
        r_prev = t_f / 2 - 0.5                      # rayon de la chape MCP de la paume
        for k, (L, wk) in enumerate(((l1, w), (l2, w - 1.0), (l3, w - 2.0))):
            tip = k == 2
            tk = t_f - k * 1.2
            ph = phalanx(L, wk, tk, tol, tip=tip, r_prev=r_prev)
            r_prev = tk / 2 - 0.5
            F = frame_z_to(d, hinge, pos)
            joints.append({"o": pos.round(3).tolist(), "a": hinge.round(5).tolist(),
                           "max": FINGER_MAX[k], "ctrl": name})
            out.append((f"{name}_P{k + 1}", f"{name} - phalange {['proximale', 'moyenne', 'distale'][k]}",
                        apply_T(ph, F),
                        dict(category="tool", anim={"type": "chain", "joints": [dict(j) for j in joints]},
                             notes=f"Axe acier d{PIN_D:g}. PETG ou PA-CF.")))
            pos = pos + d * L
        chains[name] = joints

    # ------------------------------------------------------------------ pouce (auto-regle Kapandji)
    t_th = Tp * 0.50
    r_th = t_th / 2 - 0.5
    w_th = (16.5 * s, 15.5 * s, 14.5 * s)
    finger_chains = {n: (fingers_T[n], chains[n]) for n in fingers_T}
    best, kap = tune_thumb(cmc, s, t_th, w_th, finger_chains, Tp)
    th = best["th"]
    cmc = th["cmc"]
    a_opp, dth, hth, pos0 = th["a_opp"], th["d"], th["h"], th["pos0"]
    Fo = frame_z_to(a_opp, (1, 0, 0), cmc)
    j0 = {"o": cmc.round(3).tolist(), "a": a_opp.round(5).tolist(), "max": OPP_MAX, "ctrl": "opp"}
    # trapeze : pivot d'opposition sur l'axe oblique + chape de flexion du metacarpe
    stub = 6.0 * s
    Fst = frame_z_to(dth, hth, pos0 - dth * stub)
    clev = apply_T(phalanx(stub, w_th[0] + 1, t_th, tol, proximal=None, distal="clevis"), Fst)
    base_c = pos0 - dth * stub
    bridge = apply_T(cyl(15 * s, float(np.linalg.norm(base_c - cmc)) + 1, 0),   # pont plein d15 (etait 13)
                     frame_z_to(base_c - cmc, (1, 0, 0), cmc))
    trap = fuse_all([apply_T(cyl(15 * s, 8 * s, 0), Fo), bridge, clev])
    tg = (w_th[0] + 1) * 0.42
    slot = apply_T(box(-tg / 2 - tol, tg / 2 + tol, -t_th, t_th, stub - r_th - 0.3, stub + r_th + 3), Fst)
    trap = cut_all(trap, [apply_T(cyl(3.0 + tol, 40, -5), Fo), slot])
    palm_clear = [apply_T(cyl(17 * s, float(np.linalg.norm(pos0 - cmc)) + 4, -2),
                          frame_z_to(pos0 - cmc, (1, 0, 0), cmc))]
    for ang in np.linspace(0, OPP_MAX, 6):          # volume balaye par le trapeze
        R = np.eye(4)
        R[:3, :3] = _rot(a_opp, ang)
        R[:3, 3] = cmc - R[:3, :3] @ cmc
        palm_clear.append(apply_T(trap, R))
    i_palm = next(i for i, pp in enumerate(out) if pp[0] == "paume")
    pid, lab, shp, kw = out[i_palm]
    out[i_palm] = (pid, lab, cut_all(shp, palm_clear), kw)
    # moteur d'opposition : dans l'eminence thenar, coaxial au pivot (entrainement direct
    # par roue a dents droites sur le trapeze -> precision de la pince)
    mo = apply_T(cyl(md, ml, -ml - 10 * s), Fo)
    out.append(("moteur_opposition", f"micro pas-a-pas d{md:g} (opposition, thenar)", mo,
                dict(kind="vitamin", category="motor")))
    i_palm = next(i for i, pp in enumerate(out) if pp[0] == "paume")
    pid, lab, shp, kw = out[i_palm]
    out[i_palm] = (pid, lab, cut_all(shp, [apply_T(cyl(md + 2 * tol, ml + 1, -ml - 10 * s - 0.5), Fo)]), kw)
    out.append(("pouce_trapeze", "pouce - trapeze (pivot d'opposition CMC)", trap,
                dict(category="output", anim={"type": "chain", "joints": [j0]})))
    jts = [j0]
    r_prev = r_th
    pos = pos0.copy()
    for k, (L, wk, lab) in enumerate(zip(th["L"], w_th, ("metacarpe", "phalange proximale", "phalange distale"))):
        tip = k == 2
        tk = t_th - k * 1.0
        ph = phalanx(L, wk, tk, tol, tip=tip, r_prev=r_prev)
        r_prev = tk / 2 - 0.5
        F = frame_z_to(dth, hth, pos)
        jts.append({"o": pos.round(3).tolist(), "a": hth.round(5).tolist(), "max": THUMB_MAX[k], "ctrl": "pouce"})
        out.append((f"pouce_{k + 1}", f"pouce - {lab}", apply_T(ph, F),
                    dict(category="tool", anim={"type": "chain", "joints": [dict(j) for j in jts]})))
        pos = pos + dth * L
    # pulpes TPU (coussinets souples colles sur les phalanges distales)
    pads = [(n, fingers_T[n][1], fingers_T[n][2][2], fingers_T[n][3] - 2.0, Tp * 0.52 - 2.4, chains[n])
            for n in fingers_T] + [("pouce", dth, th["L"][2], w_th[2], t_th - 2.0, jts)]
    for name, d, L3, wd, td, ch in pads:
        hax = np.array(ch[-1]["a"])
        o = np.array(ch[-1]["o"])
        pal = np.cross(hax, d)
        c = o + d * (L3 - (td / 2 - 0.5) - 1.5) + pal * (td / 2 - 1.2)
        pad = cq.Workplane("XY").sphere(wd / 2 - 1.0)
        pad = pad.intersect(box(-wd, wd, -wd, -0.6, -wd, wd))
        Fp = frame_z_to(d, hax, c)
        padw = apply_T(pad, Fp)
        pid3 = f"{name}_P3" if name != "pouce" else "pouce_3"
        i3 = next(i for i, pp in enumerate(out) if pp[0] == pid3)
        q = out[i3]
        out[i3] = (q[0], q[1], cut_all(q[2], [padw]), q[3])
        out.append((f"{name}_pulpe", f"{name} - pulpe souple (TPU 85A)", padw,
                    dict(category="sensor", anim={"type": "chain", "joints": [dict(j) for j in ch]},
                         notes="TPU 85A 100 % : adherence + conformite (prise de precision).")))
    # ------------------------------------------------------------------ moteurs, treuils, electronique
    for i, p in enumerate(motors):
        mot = cyl(md, ml, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate(tuple(p))
        out.append((f"moteur_{i + 1}", f"micro pas-a-pas d{md:g} n{i + 1}", mot,
                    dict(kind="vitamin", category="motor")))
        sp = fuse_all([tube(10.0, 3.0 + tol, 7.0, 0), tube(14.0, 3.0 + tol, 1.2, 0), tube(14.0, 3.0 + tol, 1.2, 5.8)])
        sp = sp.rotate((0, 0, 0), (1, 0, 0), -90).translate((p[0], p[1] + ml + 0.8, p[2]))
        out.append((f"treuil_{i + 1}", f"treuil de tendon n{i + 1}", sp, dict(category="output")))
    bz = zw0 + 4
    out.append(("lipo", f"LiPo 1S 500 mAh {bat[0]:g}x{bat[1]:g}x{bat[2]:g}",
                box(-bat[1] / 2, bat[1] / 2, -Tr / 2 + 3, -Tr / 2 + 3 + bat[2], bz, bz + bat[0]),
                dict(kind="vitamin", category="electronics")))
    out.append(("esp32c3", "ESP32-C3 SuperMini (BLE)",
                box(-11.25, 11.25, 0.5, 4.5, bz + 2, bz + 20), dict(kind="vitamin", category="electronics")))
    from .hand_dfm import finish_hand
    ctx = dict(s=s, cmc=cmc, a_opp=a_opp, Fo=Fo, fingers_T=fingers_T, motors=motors, zp0=zp0, Tp=Tp,
               dth=dth, hth=hth, pos0=pos0, t_th=t_th, W=W, L_carpe=L_carpe, Wr=Wr, Tr=Tr, zw0=zw0, Hr=Hr)
    out, fab = finish_hand(out, ctx, cfg, tol)
    meta = {"id": "H", "nom": "DaVinHand (main anthropomorphe)", "fabrication": fab, "eeprom_i2c": "24C02 @0x50",
            "broches": ["V+", "VCC", "GND", "TX", "RX", "SIG"],
            "architecture": "4 doigts x 3 phalanges (MCP/PIP/DIP a axe d2) + pouce CMC oblique a opposition",
            "longueurs_mm": {k: [round(v * s) for v in b[:4]] for k, b in BONES.items()} | {"pouce": [round(v * s) for v in THUMB]},
            "echelle": s, "actionneurs": "6 micro pas-a-pas : 4 flechisseurs, flechisseur du pouce, opposition",
            "tendons": "Kevlar 0.5 mm (flexion) + cordon elastique dorsal (extension)",
            "electronique": "ESP32-C3, LiPo 1S 500 mAh, TP4056, OU de diodes Schottky",
            "mode_filaire": "pogo : V+ alimente et recharge, UART TX/RX vers l'ESP32 du bras",
            "mode_BLE": "perte de V+ pogo detectee -> bascule BLE autonome",
            "pouce_regle": {k: (round(float(th[k]), 2)) for k in ("az", "el", "gam", "mcf")},
            "test_kapandji": kap,
            "kapandji_reussis": sum(1 for v in kap.values() if v["distance_mm"] < 4.0)}
    # jeu final : la paume epouse le pouce au repos et le cardan de l'auriculaire (+ jeu)
    i_palm = next(i for i, pp in enumerate(out) if pp[0] == "paume")
    q = out[i_palm]
    extra = [pp[2] for pp in out if pp[0] in ("pouce_1", "auriculaire_cardan")]
    out[i_palm] = (q[0], q[1], cut_all(q[2], extra), q[3])
    # pince interdigitale : ecart entre les phalanges moyennes de l'index et du majeur
    def gap(e):
        pi = fk(chains["index"], {"ecart": e}, np.array(chains["index"][-2]["o"]) + fingers_T["index"][1] * 8)
        pm = fk(chains["majeur"], {"ecart": e}, np.array(chains["majeur"][-2]["o"]) + fingers_T["majeur"][1] * 8)
        return float(np.linalg.norm(pi - pm)) - (fingers_T["index"][3] - 1 + fingers_T["majeur"][3] - 1) / 2
    es = np.linspace(-1, 1, 41)
    gaps = [gap(e) for e in es]
    e_cig = float(es[int(np.argmin([abs(g - 7.0) for g in gaps]))])
    meta["pince_interdigitale"] = {"ecart_repos_mm": round(gap(0), 1), "ecart_min_mm": round(min(gaps), 1),
                                   "ecart_max_mm": round(max(gaps), 1),
                                   "objet_8mm_serre_a": round(e_cig, 2),
                                   "ok": bool(min(gaps) < 6.0 and max(gaps) > 14.0)}
    pres = {"main ouverte": {}, "main ecartee": {"ecart": 1.0},
            "pince interdigitale (cigarette / pinceau)": {"ecart": e_cig, "annulaire": 0.9, "auriculaire": 0.9,
                                                          "pouce": 0.5, "opp": 0.3}, "poing": {n: 1.0 for n in BONES} | {"pouce": 0.7, "opp": 0.35},
            "prise cylindrique": {n: 0.55 for n in BONES} | {"pouce": 0.45, "opp": 0.75},
            "poing": {n: 1.0 for n in BONES} | {"pouce": 0.7, "opp": 0.35}}
    for n, v in kap.items():
        pres[f"pince {n}"] = {k: v[k] for k in ("opp", "pouce", n)}
    meta["prises"] = pres
    return out, meta
