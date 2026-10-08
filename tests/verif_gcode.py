"""Verification de securite d'un G-code destine a la K2 SE (aucune communication avec l'imprimante)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

LIM = {"X": (0.0, 220.0), "Y": (0.0, 215.0), "Z": (0.0, 245.0)}
T_MAX_BUSE, T_MAX_LIT = 300, 110


def verifier(path):
    p = Path(path)
    pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    mn = {k: 1e9 for k in pos}
    mx = {k: -1e9 for k in pos}
    ext_mn = {k: 1e9 for k in pos}
    ext_mx = {k: -1e9 for k in pos}
    rel_e, e_last = False, 0.0
    temps, lits, problemes = [], [], []
    absolu_xyz = True
    start_ok = False
    n_ext = 0
    for i, line in enumerate(open(p, encoding="utf8", errors="ignore"), 1):
        code = line.split(";")[0].strip()
        if not code:
            continue
        if "{" in code or "[" in code:
            problemes.append(f"ligne {i} : variable non substituee : {code[:80]}")
        w = code.split()
        op = w[0].upper()
        if op == "START_PRINT":
            start_ok = True
            for t in w[1:]:
                if "=" in t:
                    k, v = t.split("=", 1)
                    try:
                        float(v)
                    except ValueError:
                        problemes.append(f"ligne {i} : START_PRINT {k} non numerique ({v})")
        elif op == "G91":
            absolu_xyz = False
            problemes.append(f"ligne {i} : G91 (relatif XYZ) inattendu")
        elif op == "G90":
            absolu_xyz = True
        elif op == "M82":
            rel_e = False
        elif op == "M83":
            rel_e = True
        elif op in ("M104", "M109"):
            for t in w[1:]:
                if t[0] == "S":
                    temps.append(float(t[1:]))
        elif op in ("M140", "M190"):
            for t in w[1:]:
                if t[0] == "S":
                    lits.append(float(t[1:]))
        elif op == "G92":
            for t in w[1:]:
                if t[0] == "E":
                    e_last = float(t[1:])
        elif op in ("G0", "G1"):
            e = None
            for t in w[1:]:
                k = t[0].upper()
                if k in pos:
                    pos[k] = float(t[1:])
                elif k == "E":
                    e = float(t[1:])
            for k in pos:
                mn[k] = min(mn[k], pos[k]); mx[k] = max(mx[k], pos[k])
            if e is not None:
                de = e if rel_e else e - e_last
                if not rel_e:
                    e_last = e
                if de > 0:
                    n_ext += 1
                    for k in pos:
                        ext_mn[k] = min(ext_mn[k], pos[k]); ext_mx[k] = max(ext_mx[k], pos[k])
    for k, (a, b) in LIM.items():
        if mn[k] < a - 0.01 or mx[k] > b + 0.01:
            problemes.append(f"deplacement {k} hors volume : [{mn[k]:.1f}, {mx[k]:.1f}] (limite {a}-{b})")
    if temps and max(temps) > T_MAX_BUSE:
        problemes.append(f"temperature buse {max(temps)} > {T_MAX_BUSE}")
    if lits and max(lits) > T_MAX_LIT:
        problemes.append(f"temperature lit {max(lits)} > {T_MAX_LIT}")
    if not start_ok:
        problemes.append("pas de START_PRINT (sequence de demarrage Creality absente)")
    txt = p.read_text(encoding="utf8", errors="ignore")
    if "END_PRINT" not in txt:
        problemes.append("pas de END_PRINT")
    return {"fichier": p.name, "ok": not problemes, "problemes": problemes,
            "zone_extrudee_mm": {k: [round(ext_mn[k], 1), round(ext_mx[k], 1)] for k in pos},
            "deplacements_mm": {k: [round(mn[k], 1), round(mx[k], 1)] for k in pos},
            "temp_buse": sorted(set(temps)), "temp_lit": sorted(set(lits)), "segments_extrudes": n_ext}


if __name__ == "__main__":
    import json
    for f in sys.argv[1:]:
        print(json.dumps(verifier(f), ensure_ascii=False))
