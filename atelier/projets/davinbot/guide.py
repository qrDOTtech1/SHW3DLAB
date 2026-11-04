"""Guide de fabrication et de montage « facon Lego », genere depuis le manifeste d'un build.

Principe :
  * sous-ensembles dans l'ordre de montage reel (socle -> J1 -> tourelle -> J2 -> ... -> outils) ;
  * pour chaque sous-ensemble : plateaux d'impression (rangement 2D sur le plateau, TPU a part),
    puis etapes de montage triees selon l'empilement axial (arriere -> avant de l'actionneur) ;
  * impression du sous-ensemble suivant lancee PENDANT le montage du precedent (flux continu).
"""
from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np

ORDER = ["BASE", "J1", "TOURELLE", "J2", "BRAS", "J3", "COUDE", "J4", "AVANT_BRAS", "J5",
         "POIGNET", "CAMERA", "J6", "TETE", "OUTIL_P", "CAPTEURS", "RACK", "OUTIL_A", "OUTIL_B",
         "OUTIL_C", "OUTIL_H"]
TITLES = {"BASE": "Socle", "TOURELLE": "Tourelle (epaule)", "BRAS": "Bras superieur", "COUDE": "Bloc coude",
          "AVANT_BRAS": "Avant-bras", "POIGNET": "Poignet", "CAMERA": "Support camera",
          "TETE": "Tete de changement d'outil", "CAPTEURS": "Boitier capteurs RFP602", "RACK": "Rack d'outils",
          "OUTIL_P": "Outil P - porte-pinceau", "OUTIL_A": "Outil A - pinceau actif", "OUTIL_B": "Outil B - buse",
          "OUTIL_C": "Outil C - gabarit lourd", "OUTIL_H": "Outil H - DaVinHand"}
GAP = 6.0
PRINT_RATE_G_H = 11.0        # debit moyen Ender 3 V3 SE, buse 0.4, couche 0.2 (g/h)


def _title(g):
    if g in TITLES:
        return TITLES[g]
    if g.startswith("J"):
        return f"Actionneur {g}"
    return g


def _material(p):
    return "TPU 95A" if "TPU" in p["name"] or "doigt" in p["id"] and "OUTILH" in p["id"] and False else "PETG"


def pack(parts, bx, by, margin=3.0):
    """Rangement en etageres (plus hautes pieces d'abord), rotation 90 deg autorisee."""
    items = sorted(parts, key=lambda p: -max(p["print_dims"][0], p["print_dims"][1]))
    plates, cur, x, y, shelf = [], [], margin, margin, 0.0
    for p in items:
        w, h = p["print_dims"][0], p["print_dims"][1]
        placed = False
        for (a, b, rot) in ((w, h, 0), (h, w, 90)):
            if x + a + margin <= bx and y + b + margin <= by:
                cur.append({"id": p["id"], "x": x + a / 2, "y": y + b / 2, "rot": rot})
                x += a + GAP
                shelf = max(shelf, b)
                placed = True
                break
        if not placed:
            # nouvelle etagere
            y += shelf + GAP
            x, shelf = margin, 0.0
            for (a, b, rot) in ((w, h, 0), (h, w, 90)):
                if a + 2 * margin <= bx and y + b + margin <= by:
                    cur.append({"id": p["id"], "x": x + a / 2, "y": y + b / 2, "rot": rot})
                    x += a + GAP
                    shelf = b
                    placed = True
                    break
        if not placed:
            if cur:
                plates.append(cur)
            cur, x, y, shelf = [], margin, margin, 0.0
            a, b, rot = (w, h, 0) if w <= bx - 2 * margin else (h, w, 90)
            cur.append({"id": p["id"], "x": x + a / 2, "y": y + b / 2, "rot": rot})
            x += a + GAP
            shelf = b
    if cur:
        plates.append(cur)
    return plates


def _local_z(p):
    T = np.array(p["T"])
    c = p.get("com") or [(p["bbox"][i] + p["bbox"][i + 3]) / 2 for i in range(3)]
    return float((np.linalg.inv(T) @ np.r_[c, 1.0])[2])


def _verb(p):
    n = p["name"].lower()
    if p["kind"] == "vitamin":
        if "roulement" in n:
            return "Emmancher le roulement"
        if "pige" in n or "pions" in n or "axe acier" in n:
            return "Inserer les piges acier"
        if "nema" in n:
            return "Visser le moteur (4 vis M3x8, centrage sur le lamage)"
        if "mks" in n:
            return "Clipser la carte MKS SERVO42C a l'arriere du moteur"
        if "servo" in n:
            return "Loger le servo MG90S (2 vis M2)"
        if "pogo" in n:
            return "Coller le bloc pogo pins (fils vers le tunnel central)"
        if "aimant" in n:
            return "Coller les aimants (respecter la polarite !)"
        if "lipo" in n or "esp32" in n or "camera" in n or "led" in n:
            return "Installer l'electronique"
        return "Poser"
    if "capot" in n or "couvercle" in n:
        return "Fermer avec"
    if "bride" in n:
        return "Visser la bride de sortie (4 vis M3x16)"
    return "Poser"


def build_guide(man: dict) -> dict:
    cfg = man["cfg"]
    bx, by = cfg["bed_x"], cfg["bed_y"]
    parts = [p for p in man["parts"] if p["kind"] != "keepout"]
    groups = OrderedDict((g, []) for g in ORDER)
    for p in parts:
        groups.setdefault(p["group"], []).append(p)
    joints = {j["name"]: j for j in man["joints"]}
    steps = []
    plate_no = 0
    total_h = 0.0
    printed_seen = set()
    order = [g for g, ps in groups.items() if ps]
    plate_plans = {}
    for g in order:
        pr = [p for p in groups[g] if p["kind"] == "print"]
        tpu = [p for p in pr if "TPU" in p["name"]]
        petg = [p for p in pr if p not in tpu]
        plate_plans[g] = [("PETG", pl) for pl in pack(petg, bx, by)] + [("TPU 95A", pl) for pl in pack(tpu, bx, by)]

    def print_steps(g, parallel_with=None):
        nonlocal plate_no, total_h
        out = []
        for mat, pl in plate_plans[g]:
            plate_no += 1
            ids = [it["id"] for it in pl]
            grams = sum(next(p for p in parts if p["id"] == i).get("filament_g", 0) for i in ids)
            hours = grams / PRINT_RATE_G_H
            total_h += hours
            names = [next(p for p in parts if p["id"] == i)["name"].split(" - ", 1)[-1] for i in ids]
            txt = f"Lance l'impression n{plate_no} ({mat}) : " + ", ".join(names) + "."
            if parallel_with:
                txt += f" Pendant qu'elle tourne, continue le montage de : {parallel_with}."
            out.append({"type": "print", "title": f"Impression n{plate_no} - {_title(g)}", "text": txt,
                        "plate": pl, "material": mat, "grams": round(grams), "hours": round(hours, 1),
                        "group": g})
        return out

    # 1er sous-ensemble : impression d'abord
    steps += print_steps(order[0])
    done_ids = []
    for gi, g in enumerate(order):
        ps = groups[g]
        nxt = order[gi + 1] if gi + 1 < len(order) else None
        # l'impression du sous-ensemble suivant est lancee au debut du montage de celui-ci
        if nxt:
            steps += print_steps(nxt, parallel_with=_title(g))
        if g.startswith("J") and g in joints:
            axis = joints[g]["axis"]
            seq = sorted(ps, key=_local_z)
        else:
            axis = [0, 0, 1]
            seq = sorted(ps, key=lambda p: (p["kind"] == "vitamin" and "servo" not in p["name"].lower(),
                                            p["bbox"][2]))
            # coques d'abord, capots a la fin
            seq = sorted(seq, key=lambda p: 2 if ("capot" in p["id"] or "couvercle" in p["id"]) else 0)
        chunk = []
        k = 0
        for p in seq:
            chunk.append(p)
            if len(chunk) >= 3 or p is seq[-1] or (p["kind"] == "print" and len(chunk) >= 2):
                k += 1
                lines = [f"{_verb(q)} : {q['name'].split(' - ', 1)[-1]}" for q in chunk]
                steps.append({"type": "assemble", "title": f"{_title(g)} - etape {k}",
                              "text": " | ".join(lines), "new": [q["id"] for q in chunk],
                              "context": list(done_ids), "axis": axis, "group": g})
                done_ids += [q["id"] for q in chunk]
                chunk = []
        # raccordement au bras
        if g in ("J2", "J3", "J4", "J5", "J6"):
            steps.append({"type": "assemble", "title": f"{_title(g)} - fixation",
                          "text": f"Presenter l'actionneur {g} sur son segment, moteur(s) dans la cavite, "
                                  f"boulons traversants M4 + ecrous, puis visser la bride de sortie au segment suivant.",
                          "new": [], "context": list(done_ids), "axis": axis, "group": g})
    n_print = sum(1 for s in steps if s["type"] == "print")
    return {"steps": steps, "plates": n_print, "print_hours": round(total_h, 1),
            "filament_kg": round(sum(p.get("filament_g", 0) for p in parts) / 1000, 2),
            "bed": [bx, by], "rate_g_h": PRINT_RATE_G_H}
