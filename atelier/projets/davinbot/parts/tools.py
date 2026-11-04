"""Ecosysteme d'outils : tous heritent de la base de couplage standard (effector.tool_base :
queue + 3 ergots, cones femelles, platine 6 pastilles pogo sous la queue, 2 aimants de centrage,
EEPROM I2C d'identification).

P : porte-pinceau passif (pince a serrage + douilles)
A : porte-pinceau ACTIF - MG90S interne, angle d'attaque des poils (SIG = PWM, VCC)
B : buse pneumatique (circuit du mini-compresseur) + support camera endoscopique macro
C : gabarit outils lourds (mini-visseuse / pieces a main Dremel a arbre flexible)
H : DaVinHand - main anthropomorphe sous-actionnee (5 doigts TPU a tendons Kevlar, 5 micro
    moteurs pas-a-pas dans la paume, LiPo 1S + ESP32-C3, filaire pogo OU BLE autonome)
"""
from __future__ import annotations

import math

import cadquery as cq

from ..cad.util import (SCREW, box, cyl, tube, cone, union_all, cut_all, fuse_all, holes,
                        extrude_shapely, rect2d, circle2d)
from .effector import tool_base, MG, PINOUT
from .model import Part

TOOL_IDS = ("P", "A", "B", "C", "H")


def _revolve(profile, z0=0.0):
    pts = [(r, z + z0) for r, z in profile]
    return cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0))


def _clamp_collar(bore, length, z0, tol, gap=2.0, wall=4.0, screw="M3"):
    """Collier fendu a serrage manuel (vis + ecrou captif)."""
    od = bore + 2 * wall
    s = SCREW[screw]
    col = tube(od, bore + 2 * tol, length, z0)
    ear = s["clear"] / 2 + s["nut"] / 2 + 3
    ears = box(od / 2 - 2, od / 2 + 2 * ear, -6, 6, z0 + length / 2 - 6, z0 + length / 2 + 6)
    col = fuse_all([col, ears])
    col = col.cut(box(bore / 2 - 1, od / 2 + 2 * ear + 1, -gap / 2, gap / 2, z0 - 1, z0 + length + 1))
    xs = od / 2 + ear
    screw_c = cyl(s["clear"], 20, -10).rotate((0, 0, 0), (1, 0, 0), 90).translate((xs, 0, z0 + length / 2))
    nut = cq.Workplane("XZ").polygon(6, s["nut"] / math.cos(math.pi / 6) + 0.3).extrude(3).translate(
        (xs, -6 + 3.01, z0 + length / 2))
    return col.cut(screw_c).cut(nut)


def _servo_pocket(cx, cy, zs, axis="y", tol=0.2):
    """Logement MG90S couche (axe de cannelure selon +Y), corps le long de X."""
    return box(cx - MG["L"] / 2 - tol - MG["shaft_off"], cx + MG["L"] / 2 + tol - MG["shaft_off"],
               cy - 12 - 1, cy + 12 - 4.5, zs - MG["W"] / 2 - tol, zs + MG["W"] / 2 + tol)


def build_tools(cfg: dict, g, place: dict) -> tuple[list[Part], list[dict]]:
    """place : {"P": (T4x4, body), ...} position monde de chaque outil (repere outil)."""
    tol = g.tol
    parts, meta = [], []

    def add(tool, pid, label, shape, **kw):
        T, body = place[tool]
        parts.append(Part(id=f"OUTIL{tool}_{pid}", name=f"Outil {tool} - {label}", group=f"OUTIL_{tool}",
                          body=body, shape=shape, T=T, **kw))

    def base_meta(tid, nom, broches, **kw):
        m = {"id": tid, "nom": nom, "eeprom_i2c": "24C02 @0x50", "broches": broches}
        m.update(kw)
        meta.append(m)

    # =========================================================== P : porte-pinceau passif
    base, cutters, Dt, t = tool_base(g, cfg, eeprom=True)
    bd = cfg["brush_d"]
    L = 46.0
    body = fuse_all([base, cone(34.0, bd + 12, 12.0, t), cyl(bd + 12, L - 12, t + 12),
                     _clamp_collar(bd, 18, t + L - 2, tol)])
    body = cut_all(body, cutters + [cyl(bd + 2 * tol, L + 30, t + 4)])
    add("P", "corps", "porte-pinceau passif (pince a serrage)", body, category="tool", print_up=(0, 0, 1))
    Ts, bs = place["P_spares"]
    for i, d in enumerate((4, 6, 8, 10)):
        if d >= bd - 1.5:
            continue
        sl = tube(bd - 2 * tol, d + tol, 30.0, 0).cut(box(-0.8, 0.8, 0, bd, -1, 31))
        sl = fuse_all([sl, tube(bd + 4, d + tol, 2.0, 30.0).cut(box(-0.8, 0.8, 0, bd + 5, 29, 33))])
        parts.append(Part(id=f"OUTILP_douille_{d}", name=f"Outil P - douille de reduction d{d}",
                          group="OUTIL_P", body=bs, shape=sl.translate((i * (bd + 12), 0, 0)), T=Ts,
                          category="tool", print_up=(0, 0, 1)))
    tip_P = t + L + 16 + cfg["brush_bristle"]
    base_meta("P", "Porte-pinceau passif", ["VCC", "GND", "SDA", "SCL"],
              z_offset_pointe_mm=round(tip_P, 1), longueur_poils_mm=cfg["brush_bristle"])

    # =========================================================== A : porte-pinceau actif
    base, cutters, Dt, t = tool_base(g, cfg, eeprom=True)
    hw, hd, hh = 36.0, 24.0, 40.0
    zs = t + hh - 12.0
    body = fuse_all([base, box(-hw / 2, hw / 2, -hd / 2, hd / 2, t, t + hh)])
    body = cut_all(body, cutters + [_servo_pocket(0, 0, zs, tol=0.3), box(-4, 4, -4, 4, t - 3, zs)])
    add("A", "carter", "carter servo MG90S (angle d'attaque)", body, category="tool", print_up=(0, 0, 1),
        notes="Servo alimente en VCC 5 V, commande PWM sur la broche 6 (SIG).")
    arm_len = 34.0
    ya = hd / 2 + 1.0
    yoke = fuse_all([cyl(12, 4, 0), box(-4, 4, -arm_len, 0, 0, 4)])
    yoke = yoke.cut(cyl(MG["spline_d"] - 0.2, 5, -1))
    yoke = yoke.rotate((0, 0, 0), (1, 0, 0), -90).translate((0, ya, zs))
    col_r = 8.0 / 2 + 4.0
    clamp = _clamp_collar(8.0, 14, zs + arm_len - 7, tol).translate((0, ya + 4 + col_r, 0))
    bridge = box(-4, 4, ya, ya + 4 + 1.0, zs + arm_len - 7, zs + arm_len + 7)
    add("A", "bras", "bras orientable + pince pinceau", fuse_all([yoke, bridge, clamp]), category="output",
        print_up=(0, 1, 0), anim={"type": "tool_servo", "center": [0, ya, zs], "axis": [0, 1, 0]})
    sv = box(-MG["L"] / 2 - MG["shaft_off"], MG["L"] / 2 - MG["shaft_off"], -hd / 2 + 1, hd / 2 - 5,
             zs - MG["W"] / 2, zs + MG["W"] / 2)
    add("A", "servo", "servo MG90S (outil)", sv, kind="vitamin", category="motor")
    base_meta("A", "Porte-pinceau actif (angle d'attaque)", ["VCC", "GND", "SDA", "SCL", "SIG"],
              servo="MG90S sur SIG (PWM 50 Hz)", debattement_deg=180)

    # =========================================================== B : buse pneumatique + camera
    base, cutters, Dt, t = tool_base(g, cfg, eeprom=True)
    Ln = 58.0
    air = cfg["air_d"]
    prof = [(0, 0), (17.0, 0), (17.0, 14), (cfg["led_ring_id"] / 2 - 0.5, 34), (5.5, Ln), (0, Ln)]
    noz = _revolve(prof, t)
    ring_z = t + 22.0
    r_ring_in = cfg["led_ring_id"] / 2
    shelf = tube(cfg["led_ring_od"] + 6, 2 * r_ring_in - 1, 6.0, ring_z - 6)
    # support camera endoscopique : tube parallele a la buse, vise la sortie d'air
    cd = cfg["cam_d"]
    cam_x = cfg["led_ring_od"] / 2 + cd / 2 + 6
    cam = fuse_all([tube(cd + 6, cd + 2 * tol, 24.0, t + 10, cam_x, 0),
                    box(10, cam_x, -4, 4, t, t + 30)])
    body = fuse_all([base, noz, shelf, cam])
    ccut = cutters + [
        cyl(4.0, Ln - 6, t + 6),
        cone(4.0, 2.4, 6.2, t + Ln - 6.1),
        cyl(8.0, 4.0, t + 3.0),
        cyl(air + 2 * tol, 30, 0).rotate((0, 0, 0), (0, 1, 0), -90).translate((-1.5, 0, t + 5.0)),
        tube(cfg["led_ring_od"] + 2 * tol, 2 * r_ring_in - 2 * tol, 3.5, ring_z - 3.5 + 0.01),
        cyl(3.2, 12, t + Ln - 16, 0, 3.4),
        cyl(2.5, ring_z - t, t, 0, -8.5),
        cyl(cd + 2 * tol, 40, t + 5, cam_x, 0),
    ]
    add("B", "buse", "buse pneumatique + support camera macro", cut_all(body, ccut), category="tool",
        print_up=(0, 0, 1),
        notes=f"Entree tuyau d{air:g} (mini-compresseur du torse), couronne LED {cfg['led_ring_od']:g} mm, "
              f"sonde NTC, camera endoscopique d{cd:g} parallele a la buse.")
    add("B", "couronne_led", "couronne LED", tube(cfg["led_ring_od"], 2 * r_ring_in, 3.0, ring_z - 3.0),
        kind="vitamin", category="electronics")
    add("B", "camera", "camera endoscopique USB (macro)", cyl(cd, 30, t + 12, cam_x, 0),
        kind="vitamin", category="electronics")
    base_meta("B", "Buse pneumatique + camera macro", ["V+", "VCC", "GND", "SDA", "SCL", "SIG"],
              entree_air_mm=air, camera=f"endoscope USB d{cd:g} (cable separe dans le tunnel)")

    # =========================================================== C : gabarit outils lourds
    base, cutters, Dt, t = tool_base(g, cfg, eeprom=True)
    hdia = cfg["heavy_d"]
    hL = 110.0
    yc = -(hdia / 2 + 10.0)                   # decale vers -y outil = ouverture de la fourche (rack)
    spine = box(-22, 22, -8, 8, t, t + hL)
    spine = spine.cut(box(-14, 14, -9, 9, t + 14, t + hL - 14))       # evidement
    ribs = [box(-3, 3, yc, 8, t, t + 26), box(-3, 3, yc + hdia / 2 - 2, 8, t + hL - 30, t + hL - 6)]
    c1 = _clamp_collar(hdia, 22, t + 8, tol, wall=5.0, screw="M4").translate((0, yc, 0))
    c2 = _clamp_collar(hdia, 22, t + hL - 30, tol, wall=5.0, screw="M4").translate((0, yc, 0))
    body = fuse_all([base, spine, c1, c2] + ribs)
    body = cut_all(body, cutters + [cyl(hdia + 2 * tol, hL + 20, t - 5, 0, yc)])
    add("C", "gabarit", f"gabarit outil lourd d{hdia:g} (2 colliers M4)", body, category="tool",
        print_up=(0, 0, 1),
        notes="Pour mini-visseuse ou piece a main Dremel a arbre flexible. Remplissage >= 60 %, 5 perimetres.")
    base_meta("C", "Gabarit outils lourds", ["V+", "GND", "SIG"],
              diametre_outil_mm=hdia, charge_nominale_kg=3.0,
              avertissement="3 kg depasse la capacite du changeur (1 kg nominal) et la charge du bras : "
                            "usage pres de la base, vitesse reduite, voir onglet Couples.")

    # =========================================================== H : DaVinHand
    from .hand import build_hand
    hp, hm = build_hand(cfg, g, tol)
    for pid, label, shp, kw in hp:
        add("H", pid, label, shp, **kw)
    meta.append(hm)
    return parts, meta


# ------------------------------------------------------------------------------ DaVinHand
FINGERS = [  # nom, x (mm, largeur de paume), longueurs phalanges, largeur
    ("index", -27.0, (24.0, 17.0, 15.0), 17.0),
    ("majeur", -9.0, (26.0, 19.0, 16.0), 17.0),
    ("annulaire", 9.0, (25.0, 18.0, 15.0), 16.0),
    ("auriculaire", 27.0, (20.0, 15.0, 13.0), 15.0),
]


def _finger(lengths, width, thick, tol, hinge=1.3, gap=2.4):
    """Doigt TPU monobloc : phalanges reliees par charnieres souples dorsales,
    canal de tendon palmaire (Kevlar) + canal de rappel dorsal. Repere : base en z=0,
    face palmaire cote -Y."""
    segs = []
    z = 0.0
    for i, Lp in enumerate(lengths):
        w = width - i * 1.0
        seg = box(-w / 2, w / 2, -thick / 2, thick / 2, z, z + Lp)
        segs.append(seg)
        z += Lp
        if i < len(lengths) - 1:
            # charniere : lame mince cote dorsal (+Y) sur l'entrefer
            segs.append(box(-w / 2 + 1, w / 2 - 1, thick / 2 - hinge, thick / 2, z, z + gap))
            z += gap
    total = z
    f = fuse_all(segs)
    # pied de fixation (2 vis M2) + canal de tendon palmaire + canal dorsal
    foot = box(-width / 2, width / 2, -thick / 2, thick / 2, -6.0, 0.0)
    f = fuse_all([foot, f])
    f = cut_all(f, [cyl(1.6, total + 12, -7, 0, -thick / 2 + 2.6),
                    cyl(1.2, total + 12, -7, 0, thick / 2 - 3.2),
                    cyl(2.0, 8, -7, -width / 2 + 3.5, 0), cyl(2.0, 8, -7, width / 2 - 3.5, 0)])
    # bout de doigt arrondi (pulpe) + ancrage du tendon (noeud)
    f = cut_all(f, [cyl(3.0, 3.0, total - 3.0, 0, -thick / 2 + 2.6)])
    return f, total


def _davinhand(cfg, g, tol):
    """Main sous-actionnee : 1 moteur-treuil par doigt ; flexion par tendon, extension
    par l'elasticite des charnieres TPU."""
    base, cutters, Dt, t = tool_base(g, cfg, eeprom=True)
    W, Tp, H = 86.0, 36.0, 92.0                  # paume : largeur X, epaisseur Y, hauteur Z
    wl = 2.4
    md, ml = cfg["hand_motor_d"], cfg["hand_motor_l"]
    bat = (cfg["hand_bat_w"], cfg["hand_bat_l"], cfg["hand_bat_t"])
    z0 = t + 14.0                                # bas de paume
    parts = []
    # poignet (transition base -> paume)
    wrist = fuse_all([cone(Dt - 6, 50.0, 14.0, t)])
    palm = box(-W / 2, W / 2, -Tp / 2, Tp / 2, z0, z0 + H)
    palm = fuse_all([wrist, palm, base])
    inner = box(-W / 2 + wl, W / 2 - wl, -Tp / 2 + wl, Tp / 2 + 1, z0 + wl, z0 + H - wl)   # ouvert dos (+Y)
    # moteurs-treuils : axes selon Y, alignes sous chaque doigt (rangee haute) + pouce
    zm = z0 + H - wl - md / 2 - 3.0
    motor_pts = [(x, zm) for _, x, _, _ in FINGERS]
    thumb_m = (-W / 2 + md / 2 + wl + 2, z0 + 34.0)
    cut = [inner, cyl(18.0, 30, t - 2)]
    # guides de tendons : trous a travers le plafond de paume vers chaque doigt
    for (nm, x, lens, w) in FINGERS:
        cut.append(cyl(1.8, 12, z0 + H - wl - 4, x, -Tp / 2 + 2.6 + 4))
        cut += [cyl(2.0, 8, z0 + H - 5, x - w / 2 + 3.5, 0), cyl(2.0, 8, z0 + H - 5, x + w / 2 - 3.5, 0)]
    # doigts du pouce : face laterale -X
    cut.append(cyl(1.8, 12, 0).rotate((0, 0, 0), (0, 1, 0), -90).translate((-W / 2 + 4, -Tp / 2 + 6.6, z0 + 50)))
    # bossages capot dorsal (inserts M2)
    boss_pts = [(sx * (W / 2 - 5), zz) for sx in (-1, 1) for zz in (z0 + 10, z0 + H - 10)]
    adds = [box(x - 3.5, x + 3.5, Tp / 2 - 8, Tp / 2, z - 3.5, z + 3.5) for x, z in boss_pts]
    # berceaux moteurs (colliers) accroches a la face palmaire interne
    for x, z in motor_pts + [thumb_m]:
        adds.append(tube(md + 4, md + 2 * tol, ml, 0).rotate((0, 0, 0), (1, 0, 0), -90)
                    .translate((x, -Tp / 2 + wl, z)))
    # console du pouce (eminence thenar) : recoit le pied incline du pouce
    adds.append(box(-W / 2 - 4.0, -W / 2 + 0.5, -Tp / 2 + 3, Tp / 2 - 9, z0 + 30, z0 + 52))
    palm = fuse_all([palm] + adds)
    cut += [cyl(SCREW["M2"]["insert"], 6, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, Tp / 2 - 6, z))
            for x, z in boss_pts]
    # passage des fils pogo -> baie electronique
    cut.append(box(-4, 4, -4, 4, t - 1, z0 + wl + 1))
    palm = cut_all(palm, cutters + cut)
    parts.append(("paume", "paume (5 moteurs-treuils, baie LiPo + ESP32-C3)", palm,
                  dict(category="tool", print_up=(0, 0, 1),
                       notes="PETG. Baie : LiPo 1S 500 mAh + ESP32-C3 + chargeur/commutateur d'alimentation.")))
    cover = box(-W / 2, W / 2, Tp / 2, Tp / 2 + wl, z0, z0 + H)
    cover = cut_all(cover, [cyl(SCREW["M2"]["clear"], 6, 0).rotate((0, 0, 0), (1, 0, 0), -90)
                            .translate((x, Tp / 2 - 1, z)) for x, z in boss_pts] +
                    [box(-10, 10, Tp / 2 - 1, Tp / 2 + wl + 1, z0 + 12, z0 + 18)])       # interrupteur/USB-C
    parts.append(("capot", "capot dorsal (acces batterie, USB-C)", cover,
                  dict(category="cap", print_up=(0, -1, 0))))
    # doigts TPU
    thick = 14.0
    for nm, x, lens, w in FINGERS:
        f, tot = _finger(lens, w, thick, tol)
        f = f.translate((x, 0, z0 + H + 6.0))
        parts.append((f"doigt_{nm}", f"doigt {nm} (TPU 95A)", f,
                      dict(category="tool", print_up=(0, 0, 1),
                           notes="TPU 95A, 100 % : charnieres souples, tendon Kevlar 0.5 mm.")))
    th, tot = _finger((20.0, 17.0), 17.0, thick, tol)
    # pouce : pied plaque sur la face laterale -X (pied de 6 mm hors paume), incline de 58 deg
    th = th.translate((0, 0, 6.0)).rotate((0, 0, 0), (0, 1, 0), -58).translate((-W / 2 - 6.0, -2, z0 + 40))
    # la console epouse exactement le pied du pouce (empreinte + jeu)
    i_palm = next(i for i, pp in enumerate(parts) if pp[0] == "paume")
    pid, lab, shp, kw = parts[i_palm]
    parts[i_palm] = (pid, lab, shp.cut(th), kw)
    parts.append(("doigt_pouce", "pouce oppose (TPU 95A)", th,
                  dict(category="tool", print_up=(0, 0, 1))))
    # treuils (bobines) imprimes
    for i, (x, z) in enumerate(motor_pts + [thumb_m]):
        sp = tube(10.0, 3.0 + tol, 7.0, 0).union(tube(14.0, 3.0 + tol, 1.2, 0)).union(tube(14.0, 3.0 + tol, 1.2, 5.8))
        sp = sp.rotate((0, 0, 0), (1, 0, 0), -90).translate((x, -Tp / 2 + wl + ml + 1.0, z))
        parts.append((f"treuil_{i + 1}", f"treuil de tendon {i + 1}", sp, dict(category="output", print_up=(0, 0, 1))))
        mot = cyl(md, ml, 0).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, -Tp / 2 + wl, z))
        parts.append((f"moteur_{i + 1}", f"micro pas-a-pas d{md:g} (doigt {i + 1})", mot,
                      dict(kind="vitamin", category="motor")))
    # batterie + ESP32-C3 (baie basse)
    bz = z0 + wl + 1
    parts.append(("lipo", f"LiPo 1S 500 mAh {bat[0]:g}x{bat[1]:g}x{bat[2]:g}",
                  box(-bat[1] / 2, bat[1] / 2, -Tp / 2 + wl + 1, -Tp / 2 + wl + 1 + bat[2], bz, bz + bat[0]),
                  dict(kind="vitamin", category="electronics")))
    parts.append(("esp32c3", "ESP32-C3 SuperMini (BLE)",
                  box(-11.25, 11.25, 2, 6, bz, bz + 18), dict(kind="vitamin", category="electronics")))
    meta = {"id": "H", "nom": "DaVinHand (main autonome)", "eeprom_i2c": "24C02 @0x50",
            "broches": ["V+", "VCC", "GND", "TX", "RX", "SIG"],
            "doigts": 5, "actionnement": "sous-actionne, 1 treuil par doigt, tendons Kevlar 0.5 mm",
            "moteurs": f"5 micro pas-a-pas d{md:g} + driver DRV8833/ULN, bobines d10",
            "electronique": "ESP32-C3 SuperMini, LiPo 1S 500 mAh, chargeur TP4056, OR de diodes Schottky",
            "mode_filaire": "pogo : V+ alimente + recharge, UART TX/RX vers l'ESP32 du bras",
            "mode_BLE": "detection perte de V+ pogo (GPIO) -> bascule BLE autonome < 50 ms",
            "masse_estimee_g": None}
    return parts, meta
