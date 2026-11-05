"""Dimensionnement automatique des reducteurs.

Architecture commune (contrainte "axe creux >= 12 mm") : le NEMA 17 ne peut pas etre
coaxial a un reducteur creux. Il est donc deporte parallelement a l'axe et entraine
l'arbre d'entree creux par un etage droit (pignon moteur Zm -> roue d'entree Zi).
Rapport total = (Zi/Zm) x rapport du reducteur principal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

from ..config import BEARINGS
from .cycloid import validity as cyc_validity
from .involute import contact_ratio_external, contact_ratio_internal

HEX_WALL = 2.4        # paroi mini sur un arbre imprime
PINION_MIN_Z = 14     # pignon moteur (arbre 5 mm) : limite la taille de detalonnage


def pick_bearing(min_d: float, series=("6804", "6805", "6806", "6807", "6808", "6810",
                                        "6812", "6814", "6816")) -> str:
    for b in series:
        if BEARINGS[b][0] >= min_d - 1e-6:
            return b
    return series[-1]


def motor_offset_min(cfg: dict) -> float:
    """Entraxe mini moteur <-> axe : le carter moteur ne doit pas obstruer la sortie
    du canal de cables (percage de cloison = canal + 4 mm)."""
    return cfg["motor_body"] / 2 + (cfg["cable_bore"] + 4) / 2 + 1.5


def _prestage_options(cfg: dict, zi_min: int, m: float, a_min: float | None = None,
                      zm_max: int = 30):
    a_min = motor_offset_min(cfg) if a_min is None else a_min
    for zm in range(PINION_MIN_Z, zm_max + 1):
        for zi in range(max(zi_min, zm), 121):
            a = m * (zm + zi) / 2
            if a < a_min:
                continue
            if a > a_min + 14:
                break
            yield zm, zi, a


@dataclass
class PreStage:
    m: float
    zm: int
    zi: int
    a: float
    ratio: float
    contact_ratio: float


@dataclass
class CycloidDesign:
    kind: str = "cycloidal"
    N: int = 0                 # pions de couronne
    lobes: int = 0
    R: float = 0.0             # rayon du cercle des pions
    rp: float = 0.0            # rayon des pions
    e: float = 0.0             # excentricite
    out_pins: int = 0
    out_pin_d: float = 0.0
    Rh: float = 0.0            # rayon du cercle des trous de sortie
    hole_d: float = 0.0        # diametre des trous de sortie du disque
    disc_t: float = 0.0
    brg_in: str = ""           # roulements arbre d'entree (A et B)
    brg_ecc: str = ""          # roulements excentriques (x2)
    brg_out: str = ""          # roulement de sortie
    pre: PreStage | None = None
    main_ratio: float = 0.0
    ratio: float = 0.0
    checks: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        return d


@dataclass
class PlanetaryDesign:
    kind: str = "planetary"
    m: float = 0.0
    zs: int = 0
    zp: int = 0
    zr: int = 0
    n: int = 0
    planet_brg: str = ""
    brg_in: str = ""
    brg_out: str = ""
    pre: PreStage | None = None
    main_ratio: float = 0.0
    ratio: float = 0.0
    carrier_r: float = 0.0
    standoffs: bool = True
    checks: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _journal_bearing(cfg: dict) -> str:
    return pick_bearing(cfg["cable_bore"] + 2 * HEX_WALL + 0.8)


def _output_bearing(cfg: dict) -> str:
    """Moyeu de sortie : loge le roulement d'arbre B + inserts M3 de la bride."""
    b_in = BEARINGS[_journal_bearing(cfg)]
    return pick_bearing(b_in[1] + 2 * 6.5, series=("6808", "6810", "6812", "6814", "6816"))


def design_cycloid(cfg: dict, a_min: float | None = None) -> CycloidDesign:
    tol = cfg["tol"]
    bore = cfg["cable_bore"]
    rp = cfg["cyc_pin_d"] / 2
    opd = cfg["cyc_out_pin_d"]
    M = cfg["cyc_out_pins"]
    m_pre = cfg["pre_module"]
    rmin, rmax = cfg["cyc_ratio_min"], cfg["cyc_ratio_max"]
    target = (rmin + rmax) / 2
    brg_in = _journal_bearing(cfg)
    d_in = BEARINGS[brg_in][0]
    hex_corner = d_in / math.cos(math.radians(30))
    zi_min = math.ceil((hex_corner / 2 + 3.0 + 1.25 * m_pre) * 2 / m_pre)

    best = None
    for N in range(12, 62):
        lobes = N - 1
        # excentricite : k1 ~ 0.65, imprimable (>= 0.7 mm), disque sous le pion (e <= rp - 0.5)
        for R in [x / 2 for x in range(50, 141)]:        # 25 .. 70 mm
            e = round(min(0.65 * R / N, rp - 0.5) * 20) / 20
            if e < 0.7:
                continue
            # roulement excentrique : arbre creux autour du canal
            brg_ecc = pick_bearing(bore + 2 * (e + HEX_WALL) + 0.5,
                                   series=("6805", "6806", "6807", "6808", "6810"))
            Dm = BEARINGS[brg_ecc][1]
            hole_r = opd / 2 + e + tol / 2
            r_disc_min = R - rp - e - tol
            Rh_lo = Dm / 2 + 2.6 + hole_r
            Rh_hi = r_disc_min - 3.0 - hole_r
            if Rh_hi < Rh_lo:
                continue
            # epaulement de sortie (porte les pions) tourne dans l'alesage des pions
            Rh_hi = min(Rh_hi, R - rp - 1.0 - 2.0 - opd / 2)
            if Rh_hi < Rh_lo:
                continue
            Rh = (Rh_lo + Rh_hi) / 2
            if 2 * Rh * math.sin(math.pi / M) - 2 * hole_r < 2.5:
                continue
            v = cyc_validity(R, rp, N, e)
            if not v["ok"]:
                continue
            brg_out = _output_bearing(cfg)
            for zm, zi, a in _prestage_options(cfg, zi_min, m_pre, a_min):
                pre_r = zi / zm
                tot = pre_r * lobes
                if not (rmin <= tot <= rmax):
                    continue
                size = R + 0.25 * a
                score = abs(tot - target) * 1.0 + size * 0.35 + pre_r * 0.8
                if best is None or score < best[0]:
                    best = (score, dict(N=N, R=R, e=e, Rh=Rh, hole_r=hole_r, brg_ecc=brg_ecc,
                                        brg_out=brg_out, zm=zm, zi=zi, a=a, v=v))
            break   # plus petit R faisable pour ce N
    if best is None:
        raise ValueError("Aucun reducteur cycloidal faisable avec ces parametres")
    b = best[1]
    pre = PreStage(m_pre, b["zm"], b["zi"], b["a"], b["zi"] / b["zm"],
                   round(contact_ratio_external(b["zm"], b["zi"], m_pre), 3))
    d = CycloidDesign(N=b["N"], lobes=b["N"] - 1, R=b["R"], rp=rp, e=b["e"], out_pins=M,
                      out_pin_d=opd, Rh=round(b["Rh"], 2), hole_d=round(2 * b["hole_r"], 3),
                      disc_t=max(cfg["cyc_disc_t"], BEARINGS[b["brg_ecc"]][2]),
                      brg_in=brg_in, brg_ecc=b["brg_ecc"], brg_out=b["brg_out"], pre=pre,
                      main_ratio=b["N"] - 1, ratio=round(pre.ratio * (b["N"] - 1), 3))
    d.checks = {**b["v"], "rapport_dans_cible": rmin <= d.ratio <= rmax,
                "contact_etage_entree": pre.contact_ratio, "contact_ok": pre.contact_ratio >= 1.2}
    return d


def design_planetary(cfg: dict, m: float, rmin: float, rmax: float) -> PlanetaryDesign:
    bore = cfg["cable_bore"]
    n = cfg["pl_planets"]
    m_pre = cfg["pre_module"]
    target = (rmin + rmax) / 2
    brg_in = _journal_bearing(cfg)
    d_in = BEARINGS[brg_in][0]
    hex_corner = d_in / math.cos(math.radians(30))
    zi_min = math.ceil((hex_corner / 2 + 3.0 + 1.25 * m_pre) * 2 / m_pre)
    # soleil : integre a l'arbre creux
    zs_min = math.ceil(((bore / 2 + HEX_WALL + 0.6) + 1.25 * m) * 2 / m)
    # satellites : 2 roulements 624 (4x13x5) ou 623 si petit
    best = None
    for planet_brg in ("624", "623"):
        Dp = BEARINGS[planet_brg][1]
        zp_min = math.ceil(((Dp / 2 + 1.4) + 1.25 * m) * 2 / m)
        for zs in range(zs_min, zs_min + 25):
            for zp in range(max(zp_min, 12), zp_min + 30):
                zr = zs + 2 * zp
                if (zs + zr) % n:
                    continue
                ac = m * (zs + zp) / 2
                # interference entre satellites voisins
                if 2 * ac * math.sin(math.pi / n) - 2 * (m * zp / 2 + m) < 1.2:
                    continue
                main = 1 + zr / zs
                for zm, zi, a in _prestage_options(cfg, zi_min, m_pre):
                    tot = main * zi / zm
                    if not (rmin <= tot <= rmax):
                        continue
                    ring_d = m * zr
                    score = abs(tot - target) * 0.8 + ring_d * 0.12 + (zi / zm) * 0.5 + \
                        (0 if planet_brg == "624" else 1.5)
                    if best is None or score < best[0]:
                        best = (score, dict(zs=zs, zp=zp, zr=zr, zm=zm, zi=zi, a=a,
                                            planet_brg=planet_brg, ac=ac))
        if best is not None:
            break
    if best is None:
        raise ValueError(f"Aucun planetaire faisable pour {rmin}-{rmax}:1 (module {m})")
    b = best[1]
    pre = PreStage(m_pre, b["zm"], b["zi"], b["a"], b["zi"] / b["zm"],
                   round(contact_ratio_external(b["zm"], b["zi"], m_pre), 3))
    main = 1 + b["zr"] / b["zs"]
    brg_out = _output_bearing(cfg)
    # entretoises de porte-satellites entre deux satellites voisins ?
    ac = b["ac"]
    gap = 2 * ac * math.sin(math.pi / n) - 2 * (m * b["zp"] / 2 + m)
    d = PlanetaryDesign(m=m, zs=b["zs"], zp=b["zp"], zr=b["zr"], n=n,
                        planet_brg=b["planet_brg"], brg_in=brg_in, brg_out=brg_out, pre=pre,
                        main_ratio=round(main, 4), ratio=round(main * pre.ratio, 3),
                        carrier_r=ac, standoffs=gap >= 9.0)
    d.checks = {
        "assemblage_(zs+zr)%n": (b["zs"] + b["zr"]) % n == 0,
        "rapport_dans_cible": rmin <= d.ratio <= rmax,
        "contact_soleil_satellite": round(contact_ratio_external(b["zs"], b["zp"], m), 3),
        "contact_satellite_couronne": round(contact_ratio_internal(b["zp"], b["zr"], m), 3),
        "contact_etage_entree": pre.contact_ratio,
        "ecart_entre_satellites_mm": round(gap, 2),
        "entretoises_porte_satellites": d.standoffs,
    }
    d.checks["ok"] = all([d.checks["assemblage_(zs+zr)%n"], d.checks["rapport_dans_cible"],
                          d.checks["contact_soleil_satellite"] >= 1.2,
                          d.checks["contact_satellite_couronne"] >= 1.2])
    return d


@dataclass
class DSDMDesign:
    """Actionneur Dual-Speed Dual-Motor : differentiel planetaire a deux entrees.

    M1 (muscle couple) -> etage d'entree -> cycloidal -> COURONNE du differentiel
    M2 (muscle vitesse) -> etage d'entree (1:1 a 3:1) -> SOLAIRE (tube creux central)
    Sortie = PORTE-SATELLITES :  w_out = (Zs.w_sol + Zr.w_cour) / (Zs + Zr)
    """
    kind: str = "dsdm"
    cyc: CycloidDesign | None = None
    m: float = 0.0
    zs: int = 0
    zp: int = 0
    zr: int = 0
    n: int = 0
    planet_brg: str = ""         # "624", "623" ou "bague" (axe acier d3 + bague imprimee)
    pre2: PreStage | None = None
    brg_sun: str = ""            # tube solaire (A arriere, B dans le moyeu de sortie)
    brg_ecc_shaft: str = ""      # arbre excentrique (C cloison, D porte-couronne)
    brg_ring: str = ""           # porte-couronne tournant
    brg_out: str = ""
    k_ring: float = 0.0          # (Zs+Zr)/Zr : couronne -> sortie (soleil bloque)
    i1: float = 0.0              # rapport total M1 -> sortie (soleil verrouille)
    i2: float = 0.0              # rapport total M2 -> sortie (couronne immobile)
    carrier_r: float = 0.0
    standoffs: bool = False
    checks: dict = field(default_factory=dict)
    # compat. avec le reste du pipeline
    pre: PreStage | None = None
    ratio: float = 0.0
    brg_in: str = ""

    def to_dict(self):
        d = asdict(self)
        return d


def design_dsdm(cfg: dict) -> DSDMDesign:
    import copy
    m = cfg["dsdm_module"]
    n = cfg["pl_planets"]
    m_pre = cfg["pre_module"]
    bore = cfg["cable_bore"]
    brg_sun = _journal_bearing(cfg)
    d_tube = BEARINGS[brg_sun][0]
    hex_corner = d_tube / math.cos(math.radians(30))
    zi2_min = math.ceil((hex_corner / 2 + 3.0 + 1.25 * m_pre) * 2 / m_pre)
    zs_min = math.ceil(((bore / 2 + HEX_WALL + 0.6) + 1.25 * m) * 2 / m)
    r2min, r2max = cfg["dsdm_m2_min"], cfg["dsdm_m2_max"]
    t2 = (r2min + r2max) / 2
    best = None
    for zs in range(zs_min, zs_min + 16):
        for zp in range(12, 40):
            zr = zs + 2 * zp
            if (zs + zr) % n:
                continue
            ac = m * (zs + zp) / 2
            if 2 * ac * math.sin(math.pi / n) - 2 * (m * zp / 2 + m) < 1.2:
                continue
            # satellites : roulement si possible, sinon axe d3 + bague
            pb = "bague"
            for cand in ("624", "623"):
                if m * zp / 2 - 1.25 * m >= BEARINGS[cand][1] / 2 + 1.4:
                    pb = cand
                    break
            if pb == "bague" and m * zp / 2 - 1.25 * m < 1.5 + 2.2:
                continue
            ring_od = 2 * (m * (zr / 2 + 1.25) + 3.0)
            brg_ring = pick_bearing(ring_od, ("6810", "6812", "6814", "6816"))
            if BEARINGS[brg_ring][0] < ring_od:
                continue
            diff = 1 + zr / zs
            for zm, zi, a in _prestage_options(cfg, zi2_min, m_pre, zm_max=48):
                pre2 = zi / zm
                if pre2 < 0.5:
                    continue
                i2 = pre2 * diff
                if not (r2min <= i2 <= r2max):
                    continue
                score = abs(i2 - t2) * 2 + BEARINGS[brg_ring][1] * 0.15 + \
                    (0 if pb != "bague" else 1.0) + a * 0.05
                if best is None or score < best[0]:
                    best = (score, dict(zs=zs, zp=zp, zr=zr, zm=zm, zi=zi, a=a, pb=pb,
                                        brg_ring=brg_ring, ac=ac))
    if best is None:
        raise ValueError("Aucun differentiel DSDM faisable (M2 %.1f-%.1f:1)" % (r2min, r2max))
    b = best[1]
    pre2 = PreStage(m_pre, b["zm"], b["zi"], b["a"], b["zi"] / b["zm"],
                    round(contact_ratio_external(b["zm"], b["zi"], m_pre), 3))
    k_ring = (b["zs"] + b["zr"]) / b["zr"]
    # cycloidal du muscle couple : arbre excentrique creux autour du tube solaire
    c2 = copy.deepcopy(cfg)
    c2["cable_bore"] = d_tube + 1.0
    c2["cyc_ratio_min"] = cfg["dsdm_m1_min"] / k_ring
    c2["cyc_ratio_max"] = cfg["dsdm_m1_max"] / k_ring
    r_gear2 = m_pre * b["zi"] / 2 + m_pre
    a1_min = max(motor_offset_min(cfg), r_gear2 + 8.5)
    cyc = design_cycloid(c2, a_min=a1_min)
    d = DSDMDesign(cyc=cyc, m=m, zs=b["zs"], zp=b["zp"], zr=b["zr"], n=n, planet_brg=b["pb"],
                   pre2=pre2, brg_sun=brg_sun, brg_ecc_shaft=cyc.brg_in,
                   brg_ring=b["brg_ring"], brg_out=_output_bearing(cfg), k_ring=round(k_ring, 4),
                   i1=round(cyc.ratio * k_ring, 3), i2=round(pre2.ratio * (1 + b["zr"] / b["zs"]), 3),
                   carrier_r=b["ac"])
    d.pre, d.ratio, d.brg_in = cyc.pre, d.i1, brg_sun
    gap = 2 * b["ac"] * math.sin(math.pi / n) - 2 * (m * b["zp"] / 2 + m)
    d.standoffs = gap >= 9.0
    d.checks = {
        "assemblage_(zs+zr)%n": (b["zs"] + b["zr"]) % n == 0,
        "M1_rapport_dans_cible": cfg["dsdm_m1_min"] <= d.i1 <= cfg["dsdm_m1_max"],
        "M2_rapport_dans_cible": r2min <= d.i2 <= r2max,
        "contact_soleil_satellite": round(contact_ratio_external(b["zs"], b["zp"], m), 3),
        "contact_satellite_couronne": round(contact_ratio_internal(b["zp"], b["zr"], m), 3),
        "cycloidal": cyc.checks,
    }
    d.checks["ok"] = bool(d.checks["assemblage_(zs+zr)%n"] and d.checks["M1_rapport_dans_cible"]
                          and d.checks["M2_rapport_dans_cible"] and cyc.checks.get("ok"))
    return d


def dsdm_axes(cfg: dict) -> set:
    v = cfg.get("dsdm_axes", "J2+J3")
    return {"J2+J3": {"J2", "J3"}, "J2": {"J2"}, "J3": {"J3"}}.get(v, set())


def design_all(cfg: dict) -> dict:
    cyc = design_cycloid(cfg)
    wrist = design_planetary(cfg, cfg["pl_module_wrist"], cfg["plw_ratio_min"], cfg["plw_ratio_max"])
    axes = dsdm_axes(cfg)
    ds = design_dsdm(cfg) if axes else None
    if (cfg["pl5_ratio_min"], cfg["pl5_ratio_max"]) == (cfg["plw_ratio_min"], cfg["plw_ratio_max"]):
        j5 = wrist
    else:
        j5 = design_planetary(cfg, cfg["pl_module_wrist"], cfg["pl5_ratio_min"], cfg["pl5_ratio_max"])
    out = {"J1": cyc, "J4": wrist, "J5": j5, "J6": wrist}
    cyc2 = cyc
    if cfg.get("j2_ratio_max"):                 # J2 peut etre bien plus demultiplie que J1 (pas de ressort)
        cyc2 = design_cycloid({**cfg, "cyc_ratio_min": cfg["j2_ratio_min"], "cyc_ratio_max": cfg["j2_ratio_max"]})
    out["J2"] = ds if "J2" in axes else cyc2
    out["J3"] = ds if "J3" in axes else design_planetary(
        cfg, cfg["pl_module_elbow"], cfg["pl3_ratio_min"], cfg["pl3_ratio_max"])
    if cfg.get("j3_ratio_max") and "J3" not in axes:     # cycloidal plat au coude : plus de couple, moins de plastique que le gros planetaire
        out["J3"] = design_cycloid({**cfg, "cyc_ratio_min": cfg["j3_ratio_min"], "cyc_ratio_max": cfg["j3_ratio_max"]})
    return out
