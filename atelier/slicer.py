"""Tranchage SANS interface : CuraEngine (installe avec UltiMaker Cura 5.10) + definition Creality K2 SE
construite a partir du profil machine OFFICIEL de Creality Print (volume, start/end G-code Klipper,
retraction, z-hop). Trois qualites : rapide / normal / art.

Rien ici ne contacte l'imprimante : on produit un .gcode + ses statistiques (temps, grammes, metres).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

def _cura():
    """Dossier d'UltiMaker Cura : la version installee la plus recente (5.10 de reference)."""
    import re as _re
    cands = sorted(Path(r"C:\Program Files").glob("UltiMaker Cura*"),
                   key=lambda p: [int(x) for x in _re.findall(r"\d+", p.name)] or [0])
    return cands[-1] if cands else Path(r"C:\Program Files\UltiMaker Cura 5.10.0")


CURA = _cura()
ENGINE = CURA / "CuraEngine.exe"
RES = CURA / "share" / "cura" / "resources"
CP_PROFILS = Path(r"C:\Program Files\Creality\Creality Print 7.3\resources\profiles\Creality")
ICI = Path(__file__).resolve().parent.parent
DEFS = ICI / "data" / "cura_defs"

DENSITE = {"PLA": 1.24, "PLA+": 1.24, "PETG": 1.27, "TPU": 1.21, "ABS": 1.04}

# temperatures par defaut (profils Creality K2 SE, ajustables par bobine)
TEMP = {"PLA": (220, 60), "PLA+": (220, 60), "PETG": (240, 70), "TPU": (230, 45), "ABS": (260, 100)}

QUALITES = {
    "rapide": {
        "label": "Rapide", "desc": "0.24 mm, vitesses elevees : prototypes, gros volumes",
        "s": {"layer_height": 0.24, "layer_height_0": 0.24, "wall_line_count": 2, "top_layers": 3,
              "bottom_layers": 3, "infill_sparse_density": 10, "infill_pattern": "grid",
              "speed_print": 250, "speed_wall_0": 180, "speed_wall_x": 250, "speed_topbottom": 200,
              "speed_infill": 300, "speed_travel": 400, "speed_layer_0": 60,
              "acceleration_print": 10000, "acceleration_enabled": True},
    },
    "normal": {
        "label": "Normal", "desc": "0.20 mm, 3 parois : bon compromis vente / temps",
        "s": {"layer_height": 0.20, "layer_height_0": 0.20, "wall_line_count": 3, "top_layers": 4,
              "bottom_layers": 4, "infill_sparse_density": 15, "infill_pattern": "gyroid",
              "speed_print": 180, "speed_wall_0": 120, "speed_wall_x": 180, "speed_topbottom": 150,
              "speed_infill": 220, "speed_travel": 350, "speed_layer_0": 45,
              "acceleration_print": 6000, "acceleration_enabled": True, "z_seam_type": "sharpest_corner",
              "z_seam_corner": "z_seam_corner_inner"},
    },
    "art": {
        "label": "Art", "desc": "0.12 mm, paroi exterieure lente, LISSAGE (ironing) des dessus, joint cache : "
                               "surfaces lisses, zero poncage",
        "s": {"layer_height": 0.12, "layer_height_0": 0.20, "wall_line_count": 4, "top_layers": 8,
              "bottom_layers": 6, "infill_sparse_density": 20, "infill_pattern": "gyroid",
              "speed_print": 90, "speed_wall_0": 35, "speed_wall_x": 70, "speed_topbottom": 50,
              "speed_infill": 120, "speed_travel": 250, "speed_layer_0": 25,
              "acceleration_print": 3000, "acceleration_wall_0": 1500, "acceleration_enabled": True,
              "jerk_enabled": False,
              "ironing_enabled": True, "ironing_only_highest_layer": False, "ironing_pattern": "zigzag",
              "ironing_line_spacing": 0.1, "ironing_flow": 10, "ironing_inset": 0.25, "speed_ironing": 30,
              "roofing_layer_count": 2, "roofing_monotonic": True, "skin_monotonic": True,
              "z_seam_type": "sharpest_corner", "z_seam_corner": "z_seam_corner_inner",
              "outer_inset_first": True, "travel_avoid_other_parts": True, "travel_avoid_supports": True,
              "retraction_combing": "noskin", "wall_0_wipe_dist": 0.2,
              "infill_before_walls": False, "meshfix_maximum_resolution": 0.2,
              "cool_min_layer_time": 8},
    },
}


def _start_gcode():
    """Start G-code officiel Creality (Orca) traduit en variables Cura."""
    m = json.loads((ICI / "data" / "profils" / "machine.json").read_text(encoding="utf8"))
    g = m["machine_start_gcode"]
    g = (g.replace("[nozzle_temperature_initial_layer]", "{material_print_temperature_layer_0}")
          .replace("[bed_temperature_initial_layer_single]", "{material_bed_temperature_layer_0}")
          .replace("T[initial_no_support_extruder]", "T0"))
    g = re.sub(r"F\{filament_max_volumetric_speed\[initial_extruder\]/0\.3\*60\}", "F1500", g)
    return g


def ecrire_definitions():
    DEFS.mkdir(parents=True, exist_ok=True)
    import shutil
    # CuraEngine (Windows) ignore souvent CURA_ENGINE_SEARCH_PATH : on copie les parents a cote
    for f in ("fdmprinter.def.json", "creality_base.def.json"):
        if not (DEFS / f).exists():
            shutil.copy(RES / "definitions" / f, DEFS / f)
    if not (DEFS / "fdmextruder.def.json").exists():
        shutil.copy(RES / "definitions" / "fdmextruder.def.json", DEFS / "fdmextruder.def.json")
    d = {
        "version": 2, "name": "Creality K2 SE (ATELIER-3D)", "inherits": "creality_base",
        "metadata": {"visible": True, "manufacturer": "Creality3D", "file_formats": "text/x-gcode",
                     "machine_extruder_trains": {"0": "atelier_k2se_extruder_0"}},
        "overrides": {
            "machine_name": {"default_value": "Creality K2 SE"},
            "machine_width": {"default_value": 220}, "machine_depth": {"default_value": 215},
            "machine_height": {"default_value": 245}, "machine_heated_bed": {"default_value": True},
            "machine_gcode_flavor": {"default_value": "RepRap (Marlin/Sprinter)"},
            "machine_start_gcode": {"default_value": _start_gcode()},
            "machine_end_gcode": {"default_value": "END_PRINT"},
            "machine_max_feedrate_x": {"value": 800}, "machine_max_feedrate_y": {"value": 800},
            "machine_max_acceleration_x": {"value": 20000}, "machine_max_acceleration_y": {"value": 20000},
            "retraction_amount": {"value": 0.8}, "retraction_speed": {"value": 30},
            "retraction_hop_enabled": {"value": True}, "retraction_hop": {"value": 0.4},
            "material_diameter": {"value": 1.75},
            "adhesion_type": {"value": "'skirt'"},
        },
    }
    (DEFS / "atelier_k2se.def.json").write_text(json.dumps(d, indent=1), encoding="utf8")
    e = {"version": 2, "name": "Extruder 1", "inherits": "fdmextruder",
         "metadata": {"machine": "atelier_k2se", "position": "0"},
         "overrides": {"extruder_nr": {"default_value": 0}, "machine_nozzle_size": {"default_value": 0.4},
                       "material_diameter": {"default_value": 1.75}}}
    (DEFS / "atelier_k2se_extruder_0.def.json").write_text(json.dumps(e, indent=1), encoding="utf8")


def _stats(gcode: Path, matiere="PLA"):
    txt = gcode.read_text(encoding="utf8", errors="ignore")
    t = re.search(r";TIME:(\d+)", txt)
    fil = re.search(r";Filament used:\s*([\d.]+)m", txt)
    m_ = float(fil.group(1)) if fil else 0.0
    g_ = m_ * 1000 * 3.14159 * (1.75 / 2) ** 2 / 1000 * DENSITE.get(matiere, 1.24)     # m -> g
    lh = re.search(r";Layer height:\s*([\d.]+)", txt)
    layers = re.search(r";LAYER_COUNT:(\d+)", txt)
    return {"temps_s": int(t.group(1)) if t else None, "filament_m": round(m_, 2), "filament_g": round(g_, 1),
            "couches": int(layers.group(1)) if layers else None,
            "hauteur_couche": float(lh.group(1)) if lh else None}


def trancher(stl: Path, sortie: Path, qualite="normal", matiere="PLA", temp=None, extra=None, timeout=900):
    """STL -> G-code K2 SE. Renvoie stats. N'envoie rien a l'imprimante."""
    ecrire_definitions()
    q = QUALITES[qualite]["s"].copy()
    tn, tb = temp or TEMP.get(matiere, (220, 60))
    q.update({"material_print_temperature": tn, "material_print_temperature_layer_0": tn + 5,
              "material_bed_temperature": tb, "material_bed_temperature_layer_0": tb})
    if extra:
        q.update(extra)
    args = [str(ENGINE), "slice", "-j", str(DEFS / "atelier_k2se.def.json")]
    for k, v in q.items():
        args += ["-s", f"{k}={str(v).lower() if isinstance(v, bool) else v}"]
    args += ["-e0", "-l", str(stl), "-o", str(sortie)]
    env = dict(os.environ)
    env["CURA_ENGINE_SEARCH_PATH"] = os.pathsep.join([str(DEFS), str(RES / "definitions"), str(RES / "extruders")])
    r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not sortie.exists():
        raise RuntimeError(f"CuraEngine a echoue ({r.returncode}) : {r.stderr[-1500:]}")
    st = _stats(sortie, matiere)
    st.update({"qualite": qualite, "gcode": sortie.name})
    return st


# ------------------------------------------------------------------ definition aplatie (CuraEngine CLI)
def _arbre(d, out):
    for k, v in d.items():
        if isinstance(v, dict) and ("type" in v or "children" in v):
            if "type" in v and v.get("type") != "category":
                out[k] = v
            if "children" in v:
                _arbre(v["children"], out)
    return out


def _charge_def(nom, dossier):
    f = dossier / f"{nom}.def.json"
    if not f.exists():
        f = RES / "definitions" / f"{nom}.def.json"
    if not f.exists():
        f = RES / "extruders" / f"{nom}.def.json"
    d = json.loads(f.read_text(encoding="utf8"))
    base = _charge_def(d["inherits"], dossier) if "inherits" in d else {"settings": {}, "overrides": {}}
    st = dict(base["settings"])
    st.update(_arbre(d.get("settings", {}), {}))
    ov = dict(base["overrides"])
    for k, v in d.get("overrides", {}).items():
        ov[k] = {**ov.get(k, {}), **v}
    return {"settings": st, "overrides": ov}


def aplatir(machine="atelier_k2se", extra=None):
    """Toutes les valeurs (formules Cura evaluees) -> dict cle: valeur."""
    import math
    defn = _charge_def(machine, DEFS)
    ext = _charge_def("atelier_k2se_extruder_0", DEFS)
    S = {**defn["settings"], **ext["settings"]}
    O = {**defn["overrides"]}
    for k, v in ext["overrides"].items():
        O[k] = {**O.get(k, {}), **v}
    vals = {}
    for k, s in S.items():
        o = O.get(k, {})
        if "default_value" in o:
            vals[k] = o["default_value"]
        elif "default_value" in s:
            vals[k] = s["default_value"]
    fixes = dict(extra or {})
    vals.update(fixes)
    exprs = {}
    for k, s in S.items():
        if k in fixes:
            continue
        o = O.get(k, {})
        e = o.get("value", s.get("value") if "default_value" not in o else None)
        if e is not None:
            exprs[k] = e

    class Ns(dict):
        def __missing__(self, key):
            if key in vals:
                return vals[key]
            raise KeyError(key)
    ns = Ns(math=math, max=max, min=min, round=round, int=int, float=float, abs=abs, sum=sum, any=any,
            all=all, len=len, str=str, bool=bool, map=map, list=list, sorted=sorted, set=set)
    ns["resolveOrValue"] = lambda key: vals.get(key)
    ns["extruderValue"] = lambda e, key: vals.get(key)
    ns["extruderValues"] = lambda key: [vals.get(key)]
    ns["defaultExtruderPosition"] = lambda: "0"
    ns["valueFromContainer"] = lambda *a: None
    ns["anyExtruderWithMaterial"] = lambda key: "0"
    ns["anyExtruderNrWithOrDefault"] = lambda key: "0"
    for _ in range(12):                           # passes successives jusqu'a stabilite
        change = False
        for k, e in exprs.items():
            try:
                v = eval(str(e), {"__builtins__": {}}, ns)
            except Exception:
                continue
            if vals.get(k) != v:
                vals[k] = v
                change = True
        if not change:
            break
    return vals


def trancher_plat(stl, sortie, qualite="normal", matiere="PLA", temp=None, extra=None, timeout=900, pause_z=None):
    """Comme trancher(), mais avec TOUS les reglages evalues (CuraEngine CLI ne sait pas evaluer les formules)."""
    ecrire_definitions()
    q = QUALITES[qualite]["s"].copy()
    tn, tb = temp or TEMP.get(matiere, (220, 60))
    q.update({"material_print_temperature": tn, "material_print_temperature_layer_0": tn + 5,
              "material_bed_temperature": tb, "material_bed_temperature_layer_0": tb})
    if extra:
        q.update(extra)
    q.update({"material_print_temp_prepend": False, "material_bed_temp_prepend": False,
              "material_bed_temp_wait": False, "material_print_temp_wait": False})
    vals = aplatir(extra=q)
    # variables du start G-code Creality : substituees ici (CuraEngine CLI ne le fait pas)
    sg = vals.get("machine_start_gcode", "")
    for k_ in ("material_print_temperature_layer_0", "material_bed_temperature_layer_0",
               "material_print_temperature", "material_bed_temperature"):
        sg = sg.replace("{" + k_ + "}", str(int(round(float(vals[k_])))))
    vals["machine_start_gcode"] = sg
    plat = {"version": 2, "name": "K2 SE aplatie", "metadata": {"machine_extruder_trains": {"0": "atelier_plat_e0"}},
            "settings": {"machine_settings": {"label": "m", "type": "category", "children": {
                k: {"label": k, "type": "str", "default_value": v} for k, v in vals.items()}}}}
    (DEFS / "atelier_plat.def.json").write_text(json.dumps(plat), encoding="utf8")
    e0 = {"version": 2, "name": "e0", "metadata": {"machine": "atelier_plat", "position": "0"},
          "settings": {"machine_settings": {"label": "m", "type": "category", "children": {
              k: {"label": k, "type": "str", "default_value": v} for k, v in vals.items()}}}}
    (DEFS / "atelier_plat_e0.def.json").write_text(json.dumps(e0), encoding="utf8")
    # CuraEngine CLI place l'ORIGINE du modele au CENTRE du plateau : on centre donc l'emprise du
    # plateau sur (0, 0) et on pose sa base a Z = 0 (sinon decalage de +110 mm -> hors volume !)
    import trimesh
    m = trimesh.load(str(stl), force="mesh")
    lo, hi = m.bounds
    if (hi[0] - lo[0]) > 220 - 2 * 3 or (hi[1] - lo[1]) > 215 - 2 * 3 or (hi[2] - lo[2]) > 245:
        raise RuntimeError(f"plateau trop grand pour la K2 SE : {hi - lo}")
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    stl_c = Path(sortie).with_suffix(".centre.stl")
    m.export(stl_c)
    args = [str(ENGINE), "slice", "-j", str(DEFS / "atelier_plat.def.json"), "-e0", "-j",
            str(DEFS / "atelier_plat_e0.def.json"), "-l", str(stl_c), "-o", str(sortie)]
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not Path(sortie).exists() or Path(sortie).stat().st_size < 1000:
        raise RuntimeError(f"CuraEngine a echoue ({r.returncode}) : {(r.stdout + r.stderr)[-1500:]}")
    if pause_z is not None:
        st_p = inserer_pause(Path(sortie), float(pause_z))
    st = stats_gcode(Path(sortie), matiere, accel=float(vals.get("acceleration_print", 5000)))
    if pause_z is not None:
        st["pause"] = st_p
    st.update({"qualite": qualite, "gcode": Path(sortie).name, "hauteur_couche": vals.get("layer_height")})
    # controle de securite SYSTEMATIQUE : un G-code hors volume / sans sequence Creality est BLOQUE
    import sys as _sys
    _sys.path.insert(0, str(ICI))
    from tests.verif_gcode import verifier
    v = verifier(sortie)
    st["securite"] = v
    if not v["ok"]:
        bloque = Path(sortie).with_suffix(".BLOQUE.gcode")
        Path(sortie).replace(bloque)
        raise RuntimeError("G-code BLOQUE par le controle de securite : " + "; ".join(v["problemes"]))
    return st


def stats_gcode(path, matiere="PLA", accel=None):
    """Filament (E cumule, modes M82/M83, G92) et temps (longueur/vitesse + rampes d'acceleration)."""
    import math
    e_total, t, pos, last_e, rel = 0.0, 0.0, [0.0, 0.0, 0.0], 0.0, False
    f = 1500.0
    a = accel or 5000.0
    z_vals = set()
    for line in open(path, encoding="utf8", errors="ignore"):
        if not line or line[0] == ";":
            continue
        c = line.split(";")[0].split()
        if not c:
            continue
        op = c[0]
        if op == "M82":
            rel = False
        elif op == "M83":
            rel = True
        elif op == "M204":
            for w in c[1:]:
                if w[0] in "SP":
                    try:
                        a = float(w[1:])
                    except ValueError:
                        pass
        elif op == "G92":
            for w in c[1:]:
                if w[0] == "E":
                    last_e = float(w[1:])
        elif op in ("G0", "G1"):
            new = list(pos)
            e = None
            for w in c[1:]:
                k = w[0]
                try:
                    v = float(w[1:])
                except ValueError:
                    continue
                if k in "XYZ":
                    new["XYZ".index(k)] = v
                elif k == "E":
                    e = v
                elif k == "F":
                    f = v
            d = math.dist(pos, new)
            if e is not None:
                de = e if rel else e - last_e
                if not rel:
                    last_e = e
                if de > 0:
                    e_total += de
                if d == 0:
                    t += abs(de) / max(f / 60, 1e-3)
            if d > 0:
                v = max(f / 60.0, 1.0)
                d_acc = v * v / a                        # accelerer + freiner
                t += d / v if d >= d_acc else 2 * math.sqrt(d / a)
                if new[2] != pos[2]:
                    z_vals.add(round(new[2], 3))
            pos = new
    m = e_total / 1000.0
    g = e_total * math.pi * (1.75 / 2) ** 2 / 1000.0 * DENSITE.get(matiere, 1.24)
    return {"temps_s": int(t * 1.08 + 60), "filament_m": round(m, 2), "filament_g": round(g, 2),
            "couches": len(z_vals)}


def inserer_pause(gcode: Path, z_pause: float):
    """Insere une PAUSE (changement de filament) avant la 1re couche qui depose de la matiere AU-DESSUS de
    z_pause. Klipper (K2 SE) : macro PAUSE -> la tete se gare, on change le filament, puis REPRENDRE a l'ecran."""
    lignes = gcode.read_text(encoding="utf8", errors="replace").splitlines()
    import re as _re
    idx_couches = [i for i, l in enumerate(lignes) if l.startswith(";LAYER:")]
    z_prec = None
    for k, i in enumerate(idx_couches):
        fin = idx_couches[k + 1] if k + 1 < len(idx_couches) else len(lignes)
        z = None
        for l in lignes[i:fin]:
            m_ = _re.match(r"G[01] .*Z([0-9.]+)", l)
            if m_:
                z = float(m_.group(1))
                break
        if z is None:
            continue
        ep = z - z_prec if z_prec is not None else z
        z_prec = z
        if z - ep / 2 > z_pause:           # le MILIEU de la couche (la ou elle est tranchee) est au-dessus
            bloc = [f";ATELIER-3D : PAUSE changement de filament (couche {lignes[i][7:]}, Z {z:.2f} mm)",
                    "M400", "PAUSE"]
            lignes[i:i] = bloc
            gcode.write_text("\n".join(lignes) + "\n", encoding="utf8")
            return {"couche": int(lignes[i + len(bloc)][7:]), "z_mm": z, "commande": "PAUSE"}
    raise RuntimeError(f"pause a {z_pause} mm : aucune couche au-dessus (piece trop basse ?)")
