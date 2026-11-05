"""Parametres du generateur (source unique : l'UI est construite depuis PARAMS)."""
from __future__ import annotations

import copy
import hashlib
import json

# (groupe, cle, libelle, defaut, min, max, pas, unite, type)  type: float|int|bool|choice:<a,b>
PARAMS: list[tuple] = [
    # --- Fabrication ---
    ("Fabrication", "bed_x", "Volume impression X", 220, 100, 400, 1, "mm", "float"),
    ("Fabrication", "bed_y", "Volume impression Y", 220, 100, 400, 1, "mm", "float"),
    ("Fabrication", "bed_z", "Volume impression Z", 250, 100, 400, 1, "mm", "float"),
    ("Fabrication", "bed_margin", "Marge bord de plateau", 3, 0, 20, 0.5, "mm", "float"),
    ("Fabrication", "tol", "Jeu fonctionnel (tolerance 3D)", 0.2, 0.0, 0.8, 0.05, "mm", "float"),
    ("Fabrication", "press_tol", "Jeu logement roulement (serrage)", 0.1, -0.1, 0.5, 0.05, "mm", "float"),
    ("Fabrication", "wall", "Epaisseur de paroi standard", 3.2, 1.6, 8, 0.2, "mm", "float"),
    ("Fabrication", "stl_tol", "Precision maillage STL", 0.03, 0.005, 0.2, 0.005, "mm", "float"),
    # --- Moteurs ---
    ("Moteurs", "motor_body", "NEMA 17 : cote carter", 42.3, 40, 43, 0.1, "mm", "float"),
    ("Moteurs", "motor_len", "NEMA 17 : longueur (17HS19 = 48)", 48, 34, 60, 0.5, "mm", "float"),
    ("Moteurs", "motor_torque", "Couple de maintien", 0.59, 0.2, 1.0, 0.01, "N.m", "float"),
    ("Moteurs", "motor_torque_derate", "Couple utile (fraction du maintien)", 0.6, 0.3, 1.0, 0.05, "", "float"),
    ("Moteurs", "mks_len", "Degagement arriere moteur (MKS : min 25)", 30, 10, 60, 1, "mm", "float"),
    ("Moteurs", "mks_d", "Diametre du degagement MKS", 52, 44, 70, 1, "mm", "float"),
    # --- Reducteurs ---
    ("Reducteurs", "cable_bore", "Canal cables central (min 12)", 14, 12, 24, 0.5, "mm", "float"),
    ("Reducteurs", "cyc_ratio_min", "Cycloidal axes 1-2 : rapport min", 26, 10, 60, 1, ":1", "float"),
    ("Reducteurs", "cyc_ratio_max", "Cycloidal axes 1-2 : rapport max", 35, 10, 80, 1, ":1", "float"),
    ("Reducteurs", "cyc_pin_d", "Cycloidal : diametre des pions de couronne", 4, 3, 6, 0.5, "mm", "float"),
    ("Reducteurs", "cyc_out_pin_d", "Cycloidal : diametre pions de sortie", 5, 3, 8, 0.5, "mm", "float"),
    ("Reducteurs", "cyc_disc_t", "Cycloidal : epaisseur de disque", 7, 4, 14, 0.5, "mm", "float"),
    ("Reducteurs", "cyc_out_pins", "Cycloidal : nombre de pions de sortie", 8, 4, 12, 1, "", "int"),
    ("Reducteurs", "j2_ratio_min", "Cycloidal J2 seul : rapport min (0 = comme J1)", 0, 0, 130, 1, ":1", "float"),
    ("Reducteurs", "j2_ratio_max", "Cycloidal J2 seul : rapport max (0 = comme J1)", 0, 0, 140, 1, ":1", "float"),
    ("Reducteurs", "j3_ratio_max", "Cycloidal J3 : rapport max (0 = planetaire)", 0, 0, 100, 1, ":1", "float"),
    ("Reducteurs", "j3_ratio_min", "Cycloidal J3 : rapport min", 0, 0, 100, 1, ":1", "float"),
    ("Moteurs", "pilote_deporte", "Pilotes deportes (TMC2209, pas de MKS au dos des moteurs)", False, None, None, None, "", "bool"),
    ("Moteurs", "motor_torque_leger", "Couple utile des moteurs legers J1, J4, J5 (0 = comme les autres)", 0, 0, 1.0, 0.01, "N.m", "float"),
    ("Reducteurs", "j2_double", "J2 : 2 moteurs sur le meme reducteur", False, None, None, None, "", "bool"),
    ("Reducteurs", "j6_servo", "J6 : servo MG996R et bride legere (sans changeur d'outil)", False, None, None, None, "", "bool"),
    ("Tubes", "tube_segments", "Bras et avant-bras en 3 tubes alu (triangle) + noeuds imprimes", False, None, None, None, "", "bool"),
    ("Tubes", "tube_d", "Tube : diametre exterieur", 20, 10, 40, 0.5, "mm", "float"),
    ("Tubes", "tube_ep", "Tube : epaisseur de paroi", 1, 0.5, 3, 0.1, "mm", "float"),
    ("Tubes", "tube_prise", "Tube : longueur de prise dans chaque noeud", 35, 20, 60, 1, "mm", "float"),
    ("DSDM", "dsdm_axes", "Axes a double moteur DSDM", "J2+J3", None, None, None, "", "choice:J2+J3,J2,J3,aucun"),
    ("DSDM", "dsdm_m1_min", "M1 muscle couple : rapport min", 80, 20, 120, 1, ":1", "float"),
    ("DSDM", "dsdm_m1_max", "M1 muscle couple : rapport max", 100, 20, 140, 1, ":1", "float"),
    ("DSDM", "dsdm_m2_min", "M2 muscle vitesse : rapport min", 1.0, 0.5, 5, 0.1, ":1", "float"),
    ("DSDM", "dsdm_m2_max", "M2 muscle vitesse : rapport max", 3.0, 0.5, 6, 0.1, ":1", "float"),
    ("DSDM", "dsdm_module", "Module du differentiel", 1.0, 0.8, 2, 0.05, "mm", "float"),
    ("DSDM", "dsdm_wall", "Paroi mini autour du bloc DSDM", 6.0, 6.0, 12, 0.5, "mm", "float"),
    ("DSDM", "dsdm_lock", "Verrou mecanique de M2 (cliquet servo)", True, None, None, None, "", "bool"),
    ("Compensation", "j2_spring", "Ressort de compensation de gravite sur J2", True, None, None, None, "", "bool"),
    ("Compensation", "j2_spring_h", "Ancrage A (potence de tourelle) : profondeur SOUS l'axe J2", 138, 90, 143, 1, "mm", "float"),
    ("Compensation", "j2_spring_r", "Renvoi B (talon du bras) : rayon SOUS l'axe J2", 100, 60, 110, 1, "mm", "float"),
    ("Compensation", "j2_potence_tole", "Potence d'ancrage en tole acier (sinon imprimee, sous-dimensionnee)", True, None, None, None, "", "bool"),
    ("DSDM", "motor_rpm", "Vitesse moteur max utile", 600, 100, 2000, 10, "tr/min", "float"),
    ("Reducteurs", "pl3_ratio_min", "Planetaire axe 3 : rapport min", 15, 3, 40, 0.5, ":1", "float"),
    ("Reducteurs", "pl3_ratio_max", "Planetaire axe 3 : rapport max", 20, 3, 40, 0.5, ":1", "float"),
    ("Reducteurs", "plw_ratio_min", "Planetaire roulis 4 et 6 : rapport min", 16, 2, 40, 0.5, ":1", "float"),
    ("Reducteurs", "plw_ratio_max", "Planetaire roulis 4 et 6 : rapport max", 22, 2, 40, 0.5, ":1", "float"),
    ("Reducteurs", "pl5_ratio_min", "Planetaire axe 5 (tangage poignet) : rapport min", 21, 2, 40, 0.5, ":1", "float"),
    ("Reducteurs", "pl5_ratio_max", "Planetaire axe 5 (tangage poignet) : rapport max", 26, 2, 40, 0.5, ":1", "float"),
    ("Reducteurs", "pl_planets", "Nombre de satellites", 3, 3, 4, 1, "", "int"),
    ("Reducteurs", "pl_module_elbow", "Module planetaire axe 3", 1.25, 0.8, 2, 0.05, "mm", "float"),
    ("Reducteurs", "pl_module_wrist", "Module planetaire poignet", 1.0, 0.8, 2, 0.05, "mm", "float"),
    ("Reducteurs", "pre_module", "Module de l'etage d'entree (moteur deporte)", 1.0, 0.8, 2, 0.05, "mm", "float"),
    ("Reducteurs", "face_width", "Largeur de denture", 10, 5, 20, 0.5, "mm", "float"),
    ("Reducteurs", "pressure_angle", "Angle de pression", 20, 14.5, 25, 0.5, "deg", "float"),
    # --- Geometrie du bras ---
    ("Bras", "base_d", "Diametre socle", 200, 140, 300, 1, "mm", "float"),
    ("Bras", "shoulder_h", "Hauteur epaule au-dessus de l'axe 1", 95, 60, 200, 1, "mm", "float"),
    ("Bras", "upper_len", "Longueur bras (axe 2 -> axe 3)", 260, 120, 500, 1, "mm", "float"),
    ("Bras", "fore_len", "Longueur avant-bras (axe 3 -> axe 5)", 240, 120, 500, 1, "mm", "float"),
    ("Bras", "wrist_len", "Poignet (axe 5 -> bride outil)", 116, 60, 200, 1, "mm", "float"),
    ("Bras", "link_w", "Largeur des segments", 76, 50, 120, 1, "mm", "float"),
    ("Bras", "payload", "Charge utile cible", 1.5, 0.1, 5, 0.1, "kg", "float"),
    ("Bras", "pla_density", "Densite piece imprimee (remplissage inclus)", 0.75, 0.3, 1.3, 0.05, "g/cm3", "float"),
    ("Bras", "variant", "Variante de poignet", "artiste", None, None, None, "", "choice:artiste,assistant"),
    # --- Capteurs & effecteur ---
    ("Capteurs", "rfp_spacing", "RFP602 : entraxe de la matrice carree", 150, 60, 190, 1, "mm", "float"),
    ("Capteurs", "rfp_pad_d", "RFP602 : diametre zone sensible", 10, 5, 20, 0.5, "mm", "float"),
    ("Capteurs", "rfp_len", "RFP602 : longueur totale (queue incluse)", 49, 30, 80, 1, "mm", "float"),
    ("Capteurs", "cam_d", "Camera endoscopique : diametre", 8, 5, 12, 0.1, "mm", "float"),
    ("Capteurs", "cam_angle", "Camera assistant : inclinaison", 45, 20, 70, 1, "deg", "float"),
    ("Capteurs", "led_d", "Flash LED : diametre", 5, 3, 10, 0.5, "mm", "float"),
    ("Capteurs", "air_d", "Tuyau souffleur : diametre", 6, 3, 10, 0.5, "mm", "float"),
    # --- Changeur d'outil actif ---
    ("Outils", "tool_d", "Diametre de la tete de changement", 84, 76, 110, 1, "mm", "float"),
    ("Outils", "tool_max_mass", "Masse outil maxi", 1.0, 0.1, 2, 0.1, "kg", "float"),
    ("Outils", "lock_ring_rot", "Rotation de la bague (servo = 90 deg)", 30, 20, 45, 1, "deg", "float"),
    ("Outils", "pogo_n", "Pogo pins : nombre de broches", 6, 6, 6, 1, "", "int"),
    ("Outils", "pogo_pitch", "Pogo pins : pas", 2.5, 2.0, 3.0, 0.05, "mm", "float"),
    ("Outils", "pogo_w", "Pogo pins : largeur du corps", 6.5, 4, 10, 0.1, "mm", "float"),
    ("Outils", "pogo_depth", "Pogo pins : profondeur du corps", 8, 4, 14, 0.5, "mm", "float"),
    ("Outils", "pogo_travel", "Pogo pins : course du ressort", 1.2, 0.5, 3, 0.1, "mm", "float"),
    ("Outils", "pogo_preload", "Pogo pins : ecrasement au verrouillage", 0.7, 0.2, 2, 0.1, "mm", "float"),
    ("Outils", "pogo_mag_d", "Aimants de centrage pogo : diametre", 6, 3, 10, 0.5, "mm", "float"),
    ("Outils", "pogo_mag_h", "Aimants de centrage pogo : epaisseur", 3, 1, 6, 0.5, "mm", "float"),
    ("Outils", "rack_h", "Rack : hauteur des fourches (outils suspendus)", 300, 200, 450, 5, "mm", "float"),
    ("Outils", "rack_r", "Rack en arc : rayon des fourches autour de J1", 380, 280, 450, 5, "mm", "float"),
    ("Outils", "rack_jeu", "Rack : jeu entre outils voisins (pas = diametre outil + jeu)", 40, 25, 90, 5, "mm", "float"),
    ("Outils", "brush_d", "Outil A : diametre maxi du manche", 12, 6, 16, 0.5, "mm", "float"),
    ("Outils", "brush_bristle", "Outil A : longueur des poils (Z-offset EEPROM)", 35, 5, 80, 1, "mm", "float"),
    ("Outils", "heavy_d", "Outil C : diametre du corps d'outil lourd", 35, 18, 60, 0.5, "mm", "float"),
    ("DaVinHand", "hand_scale", "Echelle de la main (1 = main adulte)", 1.15, 0.9, 1.5, 0.05, "", "float"),
    ("DaVinHand", "hand_motor_torque", "Micro pas-a-pas : couple (sortie moteur)", 4.0, 1, 20, 0.5, "mN.m", "float"),
    ("DaVinHand", "hand_gear", "Micro pas-a-pas : reducteur integre (type GM15BY)", 100, 1, 300, 1, ":1", "float"),
    ("DaVinHand", "hand_motor_d", "Micro pas-a-pas : diametre", 15, 8, 20, 0.5, "mm", "float"),
    ("DaVinHand", "hand_motor_l", "Micro pas-a-pas : longueur", 12, 6, 25, 0.5, "mm", "float"),
    ("DaVinHand", "hand_bat_w", "LiPo 1S : largeur", 30, 15, 40, 0.5, "mm", "float"),
    ("DaVinHand", "hand_bat_l", "LiPo 1S : longueur", 40, 20, 60, 0.5, "mm", "float"),
    ("DaVinHand", "hand_bat_t", "LiPo 1S : epaisseur", 7, 3, 12, 0.5, "mm", "float"),
    ("Outils", "led_ring_od", "Outil C : couronne LED diametre ext.", 32, 20, 50, 0.5, "mm", "float"),
    ("Outils", "led_ring_id", "Outil C : couronne LED diametre int.", 18, 10, 40, 0.5, "mm", "float"),
]

DEFAULTS: dict = {p[1]: p[3] for p in PARAMS}

# Roulements standard (d, D, B) - catalogue ISO
BEARINGS = {
    "6804": (20, 32, 7), "6805": (25, 37, 7), "6806": (30, 42, 7), "6807": (35, 47, 7),
    "6808": (40, 52, 7), "6810": (50, 65, 7), "6812": (60, 78, 10), "6814": (70, 90, 10),
    "6816": (80, 100, 10), "61806": (30, 42, 7), "624": (4, 13, 5), "625": (5, 16, 5),
    "623": (3, 10, 4), "MR84": (4, 8, 3), "6704": (20, 27, 4), "6705": (25, 32, 4),
    "6706": (30, 37, 4), "6708": (40, 50, 6), "6710": (50, 62, 6),
}


def normalize(cfg: dict | None) -> dict:
    """Complete avec les defauts, applique bornes et contraintes du cahier des charges."""
    out = copy.deepcopy(DEFAULTS)
    for p in PARAMS:
        key, typ = p[1], p[8]
        if cfg and key in cfg and cfg[key] is not None:
            v = cfg[key]
            if typ == "float":
                v = float(v)
            elif typ == "int":
                v = int(round(float(v)))
            elif typ == "bool":
                v = bool(v)
            elif typ.startswith("choice:"):
                v = str(v) if str(v) in typ[7:].split(",") else p[3]
            if typ in ("float", "int"):
                v = max(p[4], min(p[5], v))
            out[key] = v
    # contraintes dures du cahier des charges
    out["cable_bore"] = max(12.0, out["cable_bore"])
    out["mks_len"] = max(10.0 if out.get("pilote_deporte") else 25.0, out["mks_len"])
    for a, b in (("cyc_ratio_min", "cyc_ratio_max"), ("dsdm_m1_min", "dsdm_m1_max"),
                 ("dsdm_m2_min", "dsdm_m2_max"), ("pl5_ratio_min", "pl5_ratio_max"), ("pl3_ratio_min", "pl3_ratio_max"),
                 ("plw_ratio_min", "plw_ratio_max")):
        if out[a] > out[b]:
            out[a], out[b] = out[b], out[a]
    return out


def code_version() -> str:
    """Empreinte du code du generateur : un changement de code invalide le cache."""
    from pathlib import Path
    h = hashlib.sha1()
    for f in sorted(Path(__file__).resolve().parent.rglob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:8]


def cfg_hash(cfg: dict) -> str:
    payload = json.dumps(cfg, sort_keys=True) + code_version()
    return hashlib.sha1(payload.encode()).hexdigest()[:10]


def schema() -> list[dict]:
    return [{"group": p[0], "key": p[1], "label": p[2], "default": p[3], "min": p[4],
             "max": p[5], "step": p[6], "unit": p[7], "type": p[8]} for p in PARAMS]
