"""DaVinBot Base : LE bras a faire evoluer. J1, J2, J3 a 1 NEMA chacun, reducteurs simples, sans ressort, sans carenage.

Le calcul de reference est dans data/bases (instantane). Changer un parametre relance le vrai generateur (10 a 25 min) dans
un processus a part, resultat garde en cache : revenir a un reglage deja calcule est immediat.
"""
from __future__ import annotations

import io
import json
import math
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh

ICI = Path(__file__).resolve().parents[2]
PACK = ICI / "data" / "bases" / "davinbot_base_af1acd2837.zip"
FIXE = {"dsdm_axes": "aucun", "j2_spring": False, "tube_segments": True, "j2_ratio_min": 70, "j2_ratio_max": 80, "j3_ratio_min": 66, "j3_ratio_max": 74, "as5600_renvoi": True, "j2_double": True, "j6_servo": True, "pilote_deporte": True, "mks_len": 12, "mks_d": 44, "motor_torque": 0.385, "motor_torque_leger": 0.40, "payload": 1.0, "tube_prise": 40}
BASE = ["BASE", "J1", "TOURELLE", "J2", "BRAS", "J3", "COUDE"]
POIGNET = ["J4", "AVANT_BRAS", "J5", "POIGNET", "J6", "TETE"]
GROUPES_REGLABLES = ("Fabrication", "Moteurs", "Reducteurs", "Bras", "Tubes")
OPTIONS = ("avec_capots", "avec_poignet", "avec_accessoires")
NOWIN = 0x08000000 if os.name == "nt" else 0


def _sortie() -> Path:
    return Path(os.environ.get("SHW_IA") or ("D:/SHW-IA" if Path("D:/").exists() else ICI / "sortie" / "ia")) / "davinbot"


def champs() -> list:
    """Les parametres de l'ancien logiciel, repris tels quels."""
    from atelier.projets.davinbot.config import PARAMS
    out = [{"k": "avec_capots", "label": "Capots de fermeture", "val": 0, "type": "bool", "groupe": "Pièces", "aide": ""},
           {"k": "avec_poignet", "label": "Avant-bras et poignet (6 moteurs)", "val": 1, "type": "bool", "groupe": "Pièces", "aide": ""}]
    out.append({"k": "avec_accessoires", "label": "Anciens supports GoPro et ultrasons", "val": 0, "type": "bool", "groupe": "Pièces", "aide": ""})
    for groupe, k, label, val, mini, maxi, pas, unite, typ in PARAMS:
        if groupe not in GROUPES_REGLABLES or k in FIXE or typ.startswith("choice") or typ == "bool":
            continue
        out.append({"k": k, "label": f"{label} ({unite})" if unite else label, "val": val, "min": mini, "max": maxi, "pas": pas, "type": "nombre", "options": None, "aide": "", "groupe": groupe})
    return out


def _reglages(p: dict) -> dict:
    from atelier.projets.davinbot.config import DEFAULTS
    r = {}
    for c in champs():
        k = c["k"]
        if k in OPTIONS or p.get(k) in (None, ""):
            continue
        if abs(float(p[k]) - float(DEFAULTS[k])) > 1e-9:
            r[k] = float(p[k])
    return r


SCRIPT = r"""
import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import atelier.projets.davinbot.build as B
B.OUT = Path(sys.argv[2]); B.OUT.mkdir(parents=True, exist_ok=True)
m = B.build(json.loads(sys.argv[3]), lambda s, f=None: None)
print("HASH=" + m["hash"])
"""


def _lecteur(reglages: dict):
    """-> (manifeste, lire(nom) -> octets)"""
    if not reglages:
        z = zipfile.ZipFile(PACK)
        return json.loads(z.read("manifest.json")), z.read
    cfg = {**FIXE, **reglages}
    r = subprocess.run([sys.executable, "-c", SCRIPT, str(ICI), str(_sortie()), json.dumps(cfg)], capture_output=True, text=True,
                       encoding="utf8", errors="replace", creationflags=NOWIN)
    h = [l[5:] for l in r.stdout.splitlines() if l.startswith("HASH=")]
    if not h:
        raise ValueError("Calcul du bras impossible avec ces réglages : " + (r.stderr or r.stdout)[-300:])
    d = _sortie() / h[0]
    return json.loads((d / "manifest.json").read_text(encoding="utf8")), lambda n: (d / n).read_bytes()


def _boite(x, y, z, cx=0.0, cy=0.0, z0=0.0):
    import manifold3d as mf
    return mf.Manifold.cube((x, y, z), True).translate((cx, cy, z0 + z / 2))


def support_ultrason():
    """HC-SR04 (45 x 20 mm, 2 capsules d16 a 26 mm) : la carte se loge par l'arriere, 2 fentes pour colliers plastique."""
    import manifold3d as mf
    b = _boite(53, 28, 2.0) + (_boite(53, 28, 6.0, z0=2) - _boite(46, 21, 7.0, z0=2)) + _boite(53, 40, 2.0)
    for sx in (-13, 13):
        b = b - mf.Manifold.cylinder(4, 8.4, 8.4, 48).translate((sx, 0, -1))
    for sy in (-16.5, 16.5):
        b = b - _boite(16, 3.2, 4, 0, sy, -1)
    return b


def support_gopro():
    """Berceau GoPro (59 x 41 x 30 mm) ouvert devant pour l'objectif ; fentes de colliers dessous et sur les cotes pour la tenir."""
    b = _boite(67, 49, 22) - _boite(60.5, 42.5, 22, z0=3) - _boite(40, 8, 22, 0, -22, 3)
    for sx in (-22, 22):
        b = b - _boite(16, 3.2, 8, sx, 0, -1)                  # fentes du fond : vers le bras
    b = b - _boite(70, 16, 3.2, 0, 8, 10)                       # fente traversante : bloque le boitier
    return b


def accessoires(capots: bool):
    from atelier.noyau.c3d import vers_trimesh
    d = 6.0 if capots else 0.0
    # Z local -> +X monde : la face de mesure regarde devant le bras
    def vers_x(x, y, z):
        R = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]); R[:3, 3] = [x, y, z]; return R
    pose_h = np.eye(4); pose_h[:3, 3] = [-11, -13, 570.5]
    return [("support_ultrason_socle", support_ultrason(), vers_x(100, 0, 44)),
            ("support_ultrason_epaule", support_ultrason(), vers_x(46 + d, 0, 230)),
            ("support_ultrason_coude", support_ultrason(), vers_x(52 + d, -13, 520)),
            ("support_gopro", support_gopro(), pose_h)]


def generer(p: dict):
    from atelier.projets.davinbot.checks import _rot_to_z
    reglages = _reglages(p)
    m, lire = _lecteur(reglages)
    charge = lambda f: trimesh.load(io.BytesIO(lire(f)), file_type="stl", force="mesh")
    groupes = set(BASE) | (set(POIGNET) if p.get("avec_poignet") else set())
    out, noms, poses, coul, pla = [], [], [], {}, 0.0
    for q in m["parts"]:
        if q["kind"] == "keepout" or q["group"] not in groupes or (not p.get("avec_capots") and "capot" in q["id"]):
            continue
        vue = charge(q["view"])
        if q["kind"] == "print" and q.get("print_up"):
            mesh = charge(q["stl"])
            R = np.eye(4); R[:3, :3] = _rot_to_z(tuple(q["print_up"]))
            a = math.radians(q.get("print_rot_z") or 0)
            Rz = np.eye(4); Rz[:2, :2] = [[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]]
            A = np.asarray(q["T"], float) @ np.linalg.inv(Rz @ R)
            t_ = mesh.copy(); t_.apply_transform(A)
            A[:3, 3] += vue.bounds.mean(axis=0) - t_.bounds.mean(axis=0)
            pla += q["masse_g"]
        else:
            mesh = vue.copy(); A = np.eye(4)
            d = -mesh.bounds[0]; mesh.apply_translation(d); A[:3, 3] = -d
        nom = q["id"] if q["kind"] == "print" else f"ACHAT {q['id']}"     # moteurs, roulements, tole : ne s'impriment pas
        out.append(mesh); noms.append(nom); poses.append(A.tolist()); coul[nom] = q["color"]
    if p.get("avec_accessoires", 0):
        from atelier.noyau.c3d import vers_trimesh
        for nom, sol, P in accessoires(bool(p.get("avec_capots"))):
            mesh = vers_trimesh(sol); dz = -mesh.bounds[0]; mesh.apply_translation(dz)
            T = np.eye(4); T[:3, 3] = -dz
            out.append(mesh); noms.append(nom); poses.append((P @ T).tolist()); coul[nom] = "#ff6410"; pla += float(mesh.volume) * 1.24e-3
    return out, {"version": "Base", "noms": noms, "assemblage": poses, "couleurs": coul, "build": m["hash"], "pla_g": round(pla),
                 "reglages_modifies": reglages, "couples": m["torque"], "avertissements": m.get("warnings", [])}
