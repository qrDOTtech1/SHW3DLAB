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
PACK = ICI / "data" / "bases" / "davinbot_base_2a7112407d.zip"
FIXE = {"dsdm_axes": "aucun", "j2_spring": False}
BASE = ["BASE", "J1", "TOURELLE", "J2", "BRAS", "J3", "COUDE"]
POIGNET = ["J4", "AVANT_BRAS", "J5", "POIGNET", "J6", "TETE"]
GROUPES_REGLABLES = ("Fabrication", "Moteurs", "Reducteurs", "Bras")
OPTIONS = ("avec_capots", "avec_poignet")
NOWIN = 0x08000000 if os.name == "nt" else 0


def _sortie() -> Path:
    return Path(os.environ.get("SHW_IA") or ("D:/SHW-IA" if Path("D:/").exists() else ICI / "sortie" / "ia")) / "davinbot"


def champs() -> list:
    """Les parametres de l'ancien logiciel, repris tels quels."""
    from atelier.projets.davinbot.config import PARAMS
    out = [{"k": "avec_capots", "label": "Capots de fermeture", "val": 0, "type": "bool", "groupe": "Pièces", "aide": ""},
           {"k": "avec_poignet", "label": "Avant-bras et poignet (sans moteur)", "val": 0, "type": "bool", "groupe": "Pièces", "aide": ""}]
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
    return out, {"version": "Base", "noms": noms, "assemblage": poses, "couleurs": coul, "build": m["hash"], "pla_g": round(pla),
                 "reglages_modifies": reglages, "couples": m["torque"], "avertissements": m.get("warnings", [])}
