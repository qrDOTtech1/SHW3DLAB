"""DaVinHand : finitions de fabrication (imprimabilite, montage, fiabilite).

* Entrainement de l'opposition : pignon Z10 (moteur) -> couronne Z30 taillee dans le trapeze
  (developpante m0.5, reduction 3:1 en plus du reducteur du moteur). L'axe d'opposition est un
  TUBE acier 3/1.6 : le tendon flechisseur du pouce passe DANS l'axe -> l'opposition ne tire pas
  sur la flexion (decouplage exact).
* Gaines de tendons : conduits d2.2 perces du treuil (poignet) jusqu'au canal de chaque doigt.
* Capots : bossages + inserts M2 (4 par capot), trous et lamages dans les capots.
* Controles : trajet de chaque tendon libre (balayage d1.0 vs toutes les pieces), force de
  serrage calculee (couple moteur x reducteur x rendement / rayon du treuil).
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Polygon

from ..cad.util import SCREW, box, cyl, cut_all, fuse_all, apply_T, frame_z_to, extrude_shapely, to_shape
from ..gears.involute import external_gear

GEAR_M = 0.5
Z_TRAP, Z_PIN = 30, 10


def _seg(p0, p1, d):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    L = float(np.linalg.norm(p1 - p0))
    return apply_T(cyl(d, L + d, -d / 2), frame_z_to((p1 - p0) / L, (1, 0, 0) if abs((p1 - p0)[0]) < 0.9 * L else (0, 1, 0), p0))


def _route_cut(route, d):
    return [_seg(a, b, d) for a, b in zip(route[:-1], route[1:])]


def _rebalance(low, up, touch=0.05):
    """Les morceaux isoles d'une moitie qui touchent le corps principal de l'autre y sont rattaches."""
    import cadquery as cq

    def parts(w):
        return sorted([x for x in to_shape(w).Solids() if x.Volume() > 1.0], key=lambda x: -x.Volume())
    L, U = parts(low), parts(up)
    if not L or not U:
        return low, up
    keepL, keepU = [L[0]], [U[0]]
    for frag in L[1:]:
        (keepU if frag.distance(U[0]) < touch else keepL).append(frag)
    for frag in U[1:]:
        (keepL if frag.distance(L[0]) < touch else keepU).append(frag)

    def fuse(lst):
        w = cq.Workplane("XY").add(lst[0])
        for x in lst[1:]:
            w = w.union(cq.Workplane("XY").add(x))
        return w
    return fuse(keepL), fuse(keepU)


def finish_hand(out, ctx, cfg, tol):
    """Applique les finitions a la liste de pieces `out` [(id, label, shape, kw)]."""
    s = ctx["s"]
    idx = {p[0]: i for i, p in enumerate(out)}

    def get(pid):
        if pid not in idx:                               # piece ajoutee en cours de finition
            idx.update({q[0]: i for i, q in enumerate(out)})
        return out[idx[pid]][2]

    def put(pid, shape):
        get(pid)
        q = out[idx[pid]]
        out[idx[pid]] = (q[0], q[1], shape, q[3])

    report = {}
    # ------------------------------------------------------------ opposition : engrenage
    cmc, a_opp, Fo = ctx["cmc"], ctx["a_opp"], ctx["Fo"]
    ring = Polygon(external_gear(Z_TRAP, GEAR_M, tol, 20, flank_pts=8, arc_pts=3))
    pin = Polygon(external_gear(Z_PIN, GEAR_M, tol, 20, flank_pts=8, arc_pts=3))
    ac = GEAR_M * (Z_TRAP + Z_PIN) / 2
    gz = 5.0 * s
    trap_gear = apply_T(extrude_shapely(ring, gz, 0.0), Fo)
    trap = get("pouce_trapeze")
    trap = cut_all(trap, [apply_T(cyl(16.5 * s, gz + 0.01, -0.005), Fo)])     # ancien disque
    # moyeu de liaison (sous le diametre de pied : n'atteint pas le pignon) : la couronne et le corps
    # du trapeze ne se touchaient que par une face -> piece en 2 morceaux
    r_root = GEAR_M * (Z_TRAP - 2.5) / 2
    trap = fuse_all([trap, trap_gear, apply_T(cyl(2 * r_root - 1.0, 3.0, gz - 1.5), Fo)])
    put("pouce_trapeze", cut_all(trap, [apply_T(cyl(3.0 + tol, 60, -20), Fo)]))
    md, ml = cfg["hand_motor_d"], cfg["hand_motor_l"]
    # moteur deporte (axe // a l'axe d'opposition), pignon dans le plan de la couronne
    mot = apply_T(cyl(md, ml, -ml - 1.0, ac + md / 2 - 2.0, 0), Fo)
    from shapely import affinity
    from .actuator import best_phase

    def mv(ph):
        return affinity.translate(affinity.rotate(pin, ph, origin=(0, 0), use_radians=True), ac, 0)
    ph = best_phase(ring, mv, 2 * math.pi / Z_PIN)
    pinion = apply_T(extrude_shapely(mv(ph), gz, 0.0), Fo)
    mx = ac + md / 2 - 2.0
    # le pignon est coaxial au moteur : on ramene le moteur sous le pignon
    z_mot = -2.5                                       # haut du moteur : epaulement de 1.9 mm sous la poche
    mot = apply_T(cyl(md, ml, z_mot - ml, ac, 0), Fo)
    put("moteur_opposition", mot)
    out.append(("pouce_pignon", f"pouce - pignon d'opposition Z{Z_PIN} m{GEAR_M:g} (sur arbre moteur)",
                cut_all(pinion, [apply_T(cyl(1.5 + tol, 30, -5, ac, 0), Fo)]),
                dict(category="gear", anim={"type": "chain", "joints": []})))
    # ------------------------------------------------------------ nacelle thenar (moulee dans la paume)
    # La coque de la paume est ELARGIE localement : une nacelle pleine enveloppe l'axe, la couronne
    # et le moteur (parois >= 2.4 mm), fusionnee a la paume -> rien a nu, rien de flottant.
    # Montage par le haut : moteur dans son alesage -> pignon sur l'arbre -> tube-axe + trapeze
    # -> capot de pignon visse (2 x M2 + inserts dans la nacelle). Fils moteur par dessous.
    from shapely.geometry import Point
    from .hand import _rot as _hr
    rp = GEAR_M * (Z_PIN + 2) / 2
    R_ring = GEAR_M * (Z_TRAP + 2) / 2
    R1 = R_ring + 1.5 + 2.4                            # autour de l'axe d'opposition
    R2 = md / 2 + tol + 6.0                            # autour du moteur (place pour 2 inserts M2)
    # engrenages NOYES : la nacelle monte jusqu'au-dessus des dents (gz + 0.6) ; couronne, pignon et
    # base du trapeze tournent dans une poche. Plus de capot rapporte (il etait dechiquete par le
    # volume balaye du trapeze, qui passe juste au-dessus du pignon).
    z_bot, z_top = z_mot - ml - 1.0, gz + 0.6
    r_ret = md / 2 + tol + 2.2                          # vis de retenue du moteur (tete sur son bord)
    ret_pts = [(ac + r_ret * math.cos(a_), r_ret * math.sin(a_)) for a_ in (math.radians(60), math.radians(-60))]
    outline = Point(0, 0).buffer(R1, 48).union(Point(ac, 0).buffer(md / 2 + tol + 4.6, 48)).convex_hull
    pod = apply_T(extrude_shapely(outline, z_top - z_bot, z_bot), Fo)
    # volume balaye par le trapeze et le metacarpe (opposition 0..75 x flexion CMC 0..32) :
    # primitives robustes (les enveloppes polyedriques font planter OpenCascade).
    # * trapeze : ne fait que TOURNER autour de l'axe d'opposition -> son volume balaye exact est
    #   un secteur de revolution (profil radial x [angle mini, angle maxi + 75 deg]) ;
    # * metacarpe : cylindre ajuste a son etendue reelle, pose a chacune des 21 positions.
    import cadquery as cq
    ref = np.cross(ctx["a_opp"], [0.0, 0.0, 1.0])
    ref = ref / np.linalg.norm(ref) if np.linalg.norm(ref) > 1e-6 else np.array([1.0, 0, 0])
    ref2 = np.cross(ctx["a_opp"], ref)

    def _pts(shape):
        vs, _ = to_shape(shape).tessellate(0.5)
        return np.array([[v.x, v.y, v.z] for v in vs])

    P = _pts(get("pouce_trapeze")) - cmc
    t = P @ ctx["a_opp"]
    rad = np.linalg.norm(P - np.outer(t, ctx["a_opp"]), axis=1)
    ang = np.degrees(np.arctan2(P @ ref2, P @ ref))
    a0, a1 = float(ang.min()), float(ang.max())
    if a1 - a0 > 300:                                  # trapeze a cheval sur +-180 : on englobe tout
        a0, a1 = -180.0, 180.0 - 75.0
    Fr = np.eye(4)
    Fr[:3, 0], Fr[:3, 1], Fr[:3, 2], Fr[:3, 3] = ref, ref2, ctx["a_opp"], cmc
    # profil radial REEL (rayon maxi par tranche de 1 mm de hauteur, +0.6 mm), pas un rectangle :
    # pres de la base le trapeze n'est que la couronne d16 -> la nacelle reste pleine autour
    edges = np.arange(t.min() - 0.6, t.max() + 1.6, 1.0)
    prof = [(0.0, float(edges[0]))]
    for z0_, z1_ in zip(edges[:-1], edges[1:]):
        m_ = (t >= z0_ - 0.5) & (t <= z1_ + 0.5)
        r_ = float(rad[m_].max()) + 0.6 if m_.any() else 0.6
        prof += [(r_, float(z0_)), (r_, float(z1_))]
    prof.append((0.0, float(edges[-1])))
    ded = [prof[0]]                                    # points consecutifs confondus -> arete nulle
    for q_ in prof[1:]:
        if abs(q_[0] - ded[-1][0]) > 1e-6 or abs(q_[1] - ded[-1][1]) > 1e-6:
            ded.append(q_)
    prof = [q_ for i_, q_ in enumerate(ded) if not (0 < i_ < len(ded) - 1 and
            abs(ded[i_ - 1][0] - q_[0]) < 1e-6 and abs(ded[i_ + 1][0] - q_[0]) < 1e-6)]   # colineaires
    sect = (cq.Workplane("XZ").polyline(prof).close()
            .revolve(min(a1 + 75.0 + 4.0, a0 + 360.0) - (a0 - 4.0), (0, 0, 0), (0, 1, 0)))
    sect = sect.rotate((0, 0, 0), (0, 0, 1), a0 - 4.0)
    sweeps = [apply_T(sect, Fr)]
    Q = _pts(get("pouce_1")) - ctx["pos0"]
    tq = Q @ ctx["dth"]
    rq = np.linalg.norm(Q - np.outer(tq, ctx["dth"]), axis=1).max() + 0.6
    mc_cyl = apply_T(cyl(2 * rq, tq.max() - tq.min() + 1.2, tq.min() - 0.6),
                     frame_z_to(ctx["dth"], (1, 0, 0) if abs(ctx["dth"][0]) < 0.9 else (0, 1, 0), ctx["pos0"]))
    for ang_o in np.linspace(0, 75, 7):
        Ro = np.eye(4)
        Ro[:3, :3] = _hr(ctx["a_opp"], ang_o)
        Ro[:3, 3] = cmc - Ro[:3, :3] @ cmc
        for fl in (0.0, 16.0, 32.0):
            Rf = np.eye(4)
            Rf[:3, :3] = _hr(ctx["hth"], fl)
            Rf[:3, 3] = ctx["pos0"] - Rf[:3, :3] @ ctx["pos0"]
            sweeps.append(apply_T(mc_cyl, Ro @ Rf))
    palm = get("paume")
    palm = fuse_all([palm, pod])
    # moteur insere PAR DESSOUS (cavite dorsale), en butee sur un epaulement ; seul l'arbre monte au pignon
    palm = cut_all(palm, [apply_T(cyl(md + 2 * tol, z_mot - (z_bot - 1.0), z_bot - 1.0, ac, 0), Fo),
                          apply_T(cyl(4.0, 3.0, -1.2, ac, 0), Fo),                          # passage d'arbre
                          apply_T(cyl(3.0 + tol / 2, 40, -25), Fo),                         # tube-axe acier d3
                          apply_T(cyl(2 * rp + 1.2, gz + 3, -0.6, ac, 0), Fo),              # poche du pignon
                          apply_T(cyl(2 * R_ring + 1.5, gz + 3, -0.6), Fo)] +
                 [apply_T(cyl(SCREW["M2"]["insert"], 4.5, z_bot - 0.01, x_, y_), Fo) for x_, y_ in ret_pts] +
                 sweeps)
    report["nacelle_thenar"] = ("engrenages noyes dans la nacelle (aucun capot) ; moteur insere par dessous, "
                                "en butee sur un epaulement de 1.9 mm, retenu par 2 vis M2x5 + rondelles "
                                "(tetes sur son bord) dans des inserts")
    report["opposition"] = {"reduction_engrenage": Z_TRAP / Z_PIN, "entraxe_mm": ac,
                            "axe": "tube acier d3 x 1.6 (le tendon du pouce passe dedans)"}

    # ------------------------------------------------------------ gaines de tendons
    routes = {}
    fT = ctx["fingers_T"]
    motors = ctx["motors"]
    spool_c = [np.array([p[0], p[1] + ml + 4.3, p[2]]) for p in motors]
    order = {"index": 0, "majeur": 1, "annulaire": 2, "auriculaire": 4, "pouce": 3}
    zc_top = ctx["zp0"] - 3.0
    for name, (head, d, lens, w) in fT.items():
        a = math.atan2(d[0], d[2])
        hinge = np.array([math.cos(a), 0.0, -math.sin(a)])
        t_f = ctx["Tp"] * 0.52
        pal = np.cross(d, hinge)                       # +y local du repere phalange
        E = head + d * (-60.0) + pal * (-t_f / 2 + 2.6)
        sc = spool_c[order[name]]
        r0 = sc + np.array([0, 0, 5.0])
        routes[name] = [r0, np.array([r0[0], r0[1], zc_top]), np.array([E[0], E[1], zc_top + 2]), E]
    # pouce : treuil -> dessous de l'axe creux -> dans l'axe -> sortie en tete -> canal du metacarpe
    th_pal = np.cross(ctx["dth"], ctx["hth"])
    E_th = ctx["pos0"] + th_pal * (-ctx["t_th"] / 2 + 2.6)
    ax_bot = cmc - a_opp * 12.0 * s
    ax_top = cmc + a_opp * 4.0 * s                     # sortie de l axe creux sous le metacarpe
    sc = spool_c[order["pouce"]] + np.array([0, 0, 5.0])
    inner = np.array([ax_bot[0], -ctx["Tp"] / 2 + 5.0, zc_top - 6.0])   # cheminement DANS la paume
    routes["pouce"] = [sc, np.array([sc[0], sc[1], zc_top - 6.0]), inner, ax_bot, ax_top,
                       E_th - ctx["dth"] * 7.0, E_th + ctx["dth"] * 3.0]
    cuts = []
    for n, r in routes.items():
        cuts += _route_cut(r, 2.2)
    palm = cut_all(palm, cuts)
    put("pouce_trapeze", cut_all(get("pouce_trapeze"), _route_cut(routes["pouce"][3:6], 2.2)))
    # entree evasee du tendon dans le tenon du metacarpe du pouce
    put("pouce_1", cut_all(get("pouce_1"), _route_cut(routes["pouce"][4:], 2.2)))
    # le trapeze degage le volume balaye par le metacarpe en flexion (CMC 0..30 deg)
    from .hand import _rot as _hrot
    sweep_mc = []
    for ang in np.linspace(0, 32, 5):
        R = np.eye(4)
        R[:3, :3] = _hrot(ctx["hth"], ang)
        R[:3, 3] = ctx["pos0"] - R[:3, :3] @ ctx["pos0"]
        sweep_mc.append(apply_T(get("pouce_1"), R))
    put("pouce_trapeze", cut_all(get("pouce_trapeze"), sweep_mc))
    if "metacarpe_V" in idx:
        put("metacarpe_V", cut_all(get("metacarpe_V"), _route_cut(routes["auriculaire"], 2.2)))

    # ------------------------------------------------------------ capots : bossages + inserts M2
    W, Tp, zp0, L_carpe = ctx["W"], ctx["Tp"], ctx["zp0"], ctx["L_carpe"]
    Wr, Tr, zw0, Hr = ctx["Wr"], ctx["Tr"], ctx["zw0"], ctx["Hr"]
    ins = SCREW["M2"]["insert"]
    pal_pts = [(sx * (W / 2 - 7), zz) for sx in (-1, 1) for zz in (zp0 - 1, zp0 + L_carpe + 1)]
    wr_pts = [(sx * (Wr / 2 - 6.5), zz) for sx in (-1, 1) for zz in (zw0 + 8, zw0 + 36)]
    adds, pc = [], []
    for (x, z), y0, y1 in [(p, -Tp / 2 + 2.4, Tp / 2 - 1.8) for p in pal_pts] + \
                          [(p, -Tr / 2 + 2.4, Tr / 2 - 1.8) for p in wr_pts]:
        adds.append(cyl(6.0, y1 - y0, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, y0, z)))
        pc.append(cyl(ins, 5.0, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, y1 - 4.99, z)))
    palm = cut_all(fuse_all([palm] + adds), pc + cuts)
    # la paume epouse au repos toutes les pieces qui s'y logent (moteurs, treuils, 5e metacarpe...)
    others = [p[2] for p in out if p[0] not in ("paume", "capot_dos", "capot_poignet")]
    palm = cut_all(palm, others)
    put("paume", palm)
    for pid, pts, yT in (("capot_dos", pal_pts, Tp / 2), ("capot_poignet", wr_pts, Tr / 2)):
        hc = []
        for x, z in pts:
            hc.append(cyl(SCREW["M2"]["clear"], 6, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, yT - 3, z)))
            hc.append(cyl(SCREW["M2"]["head"] + 0.4, 1.2, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, yT - 0.61, z)))
        put(pid, cut_all(get(pid), hc))
    report["visserie_capots"] = "2 x 4 vis M2x6 + inserts M2 (bossages d6)"

    # ------------------------------------------------------------ scission poignet / paume
    # (moins de supports, impression optimale de chaque moitie) : 4 vis M3 + inserts, tetes
    # accessibles par la cavite dorsale de la paume
    zs_ = zp0
    pts = [(sx * (Wr / 2 - 5.5), sy * (Tr / 2 - 5.5)) for sx in (-1, 1) for sy in (-1, 1)]
    palm = get("paume")
    palm = fuse_all([palm] + [cyl(8.0, 16.0, zs_ - 8.0, x, y) for x, y in pts])
    palm = cut_all(palm, others + [get("capot_dos"), get("capot_poignet")])
    # cloison de jonction (4 mm) : relie les 4 bossages aux parois (ils flottaient dans la cavite)
    # et rigidifie le joint ; tendons, canal central et fils du moteur d'opposition la traversent
    from .hand import _rounded_box
    floor = _rounded_box(W - 0.4, Tp - 0.4, 4.0, 7).translate((0, 0, zs_))
    floor = floor.intersect(box(-W, W, -Tp, Tp / 2 - 2.2, zs_ - 1, zs_ + 5))       # sous le capot dorsal
    mot_bot = apply_T(cyl(1.0, 0.1, z_bot - 0.05, ac, 0), Fo).val().Center()
    fcut = [cyl(12.0, 8, zs_ - 2, 0, 0), cyl(7.0, 8, zs_ - 2, mot_bot.x, mot_bot.y)]
    for n_, r_ in routes.items():
        fcut += _route_cut(r_, 2.2)
    palm = fuse_all([palm, cut_all(floor, fcut + others + [get("capot_dos"), get("capot_poignet")] + sweeps)])
    # repartition par CONNEXITE : chaque morceau cree par le plan de joint rejoint la piece a
    # laquelle il est reellement attache (ex. pied de la nacelle thenar -> paume)
    low = palm.intersect(box(-500, 500, -500, 500, -500, zs_))
    up = palm.intersect(box(-500, 500, -500, 500, zs_, 500))
    low, up = _rebalance(low, up)
    low = cut_all(low, [cyl(SCREW["M3"]["insert"], 6.0, zs_ - 5.99, x, y) for x, y in pts] +
                  [cyl(3.0, 4.0, zs_ - 3.99, 0, 0)])
    up = cut_all(up, [cyl(SCREW["M3"]["clear"], 20, zs_ - 1, x, y) for x, y in pts] +
                 [cyl(SCREW["M3"]["head"] + 0.4, 12, zs_ + 6, x, y) for x, y in pts])
    put("paume", up)
    out.insert(idx["paume"], ("module_poignet", "module poignet (5 flechisseurs, LiPo, ESP32-C3) + base de couplage",
                              low, dict(category="tool",
                                        notes="Visse sous la paume (4 x M3x12 + inserts). Imprimer base sur le plateau.")))
    idx = {p[0]: i for i, p in enumerate(out)}
    report["scission"] = "module poignet / paume : 4 vis M3x12 + inserts, joint au niveau du carpe"

    # ------------------------------------------------------------ controles : tendons libres
    blocked = {}
    solids = {p[0]: to_shape(p[2]) for p in out}
    for n, r in routes.items():
        sweep = [to_shape(x) for x in _route_cut(r, 1.0)]
        for pid, sh in solids.items():
            if pid.startswith(("moteur", "treuil", "lipo", "esp32")):
                continue
            v = sum(abs(sh.intersect(sw).Volume()) for sw in sweep)
            if v > 0.3:
                blocked.setdefault(n, []).append((pid, round(v, 2)))
    report["tendons"] = {n: ("libre" if n not in blocked else blocked[n]) for n in routes}
    report["tendons_ok"] = not blocked
    report["routes_mm"] = {n: [np.round(p, 1).tolist() for p in r] for n, r in routes.items()}

    # ------------------------------------------------------------ forces
    Tm = cfg["hand_motor_torque"] / 1000.0            # N.m
    gear = cfg["hand_gear"]
    r_sp = 5.0 / 1000.0
    eta = 0.55
    F_t = Tm * gear * eta / r_sp                       # tension du tendon (N)
    lever = (ctx["Tp"] * 0.52 / 2 - 2.6) / 1000.0      # bras de levier du tendon aux articulations
    L_f = sum(fT["index"][2]) / 1000.0
    F_tip = F_t * lever / (0.6 * L_f)                  # effort au bout (doigt fleche a mi-course)
    report["forces"] = {"couple_moteur_mNm": cfg["hand_motor_torque"], "reducteur_moteur": gear,
                        "tension_tendon_N": round(F_t, 1), "effort_bout_de_doigt_N": round(F_tip, 1),
                        "pince_pouce_index_N": round(2 * F_tip * 0.8, 1),
                        "prise_cylindrique_4_doigts_N": round(4 * F_tip, 1),
                        "rupture_Kevlar_0.5_N": 400, "coef_securite_tendon": round(400 / max(F_t, 1e-6), 1)}
    # axes et visserie
    report["axes_acier"] = {"d2 x (largeur+1.5) mm : MCP/PIP/DIP": 12, "d2 : cardans MCP (ecartement)": 4,
                            "d2 : 5e metacarpe": 1, "d2 : pouce (CMC flexion, MCP, IP)": 3,
                            "tube d3/1.6 : axe d'opposition": 1}
    return out, report
