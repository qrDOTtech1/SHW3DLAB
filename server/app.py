"""ATELIER-3D : serveur local (FastAPI).

Principe de securite (regle de Steven) : AUCUNE communication avec l'imprimante tant que l'utilisateur
ne l'a pas activee lui-meme dans l'onglet Imprimante (desactivee par defaut, aucun envoi automatique).
"""
from __future__ import annotations

import re
import json
import numpy as np
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ICI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ICI))
DATA = ICI / "data"
JOBS_DIR = ICI / "sortie" / "jobs"
ETAT = DATA / "atelier.json"
DATA.mkdir(exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ATELIER-3D")
_lock = threading.Lock()

# ------------------------------------------------------------------ etat persistant
DEFAUT = {
    "bobines": [
        {"id": "b1", "nom": "PLA noir", "marque": "?", "matiere": "PLA", "couleur": "#151515",
         "restant_g": 700, "initial_g": 1000, "prix_kg": 20.0, "temp": [220, 60]},
        {"id": "b2", "nom": "PLA+ blanc", "marque": "Creality", "matiere": "PLA+", "couleur": "#f4f4f2",
         "restant_g": 250, "initial_g": 1000, "prix_kg": 22.0, "temp": [220, 60]},
    ],
    "couts": {
        "electricite_kwh": 0.2516,        # EUR/kWh (tarif bleu EDF base, a ajuster)
        "puissance_w": 120,               # conso moyenne K2 SE en impression PLA (estimation)
        "machine_prix": 289.0, "machine_vie_h": 3000,     # amortissement
        "buse_eur_h": 0.02,               # usure buse / PTFE / plateau
        "emballage": 0.35, "anneau": 0.12, "colle": 0.03,
        "etsy_annonce": 0.18, "etsy_transaction_pct": 6.5, "etsy_paiement_pct": 4.0, "etsy_paiement_fixe": 0.30,
        "main_oeuvre_h": 12.0, "temps_assemblage_min": 1.5,
        "marge_cible_pct": 55,
        "marche_etsy": [2.74, 9.90],
    },
    "historique": [],
    "imprimante": {"connexion_active": False, "adresse": "192.168.1.81"},
}


def lire():
    if ETAT.exists():
        d = json.loads(ETAT.read_text(encoding="utf8"))
        for k, v in DEFAUT.items():
            d.setdefault(k, v)
        for k, v in DEFAUT["couts"].items():
            d["couts"].setdefault(k, v)
        return d
    ecrire(DEFAUT)
    return json.loads(json.dumps(DEFAUT))


def ecrire(d):
    tmp = ETAT.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")
    tmp.replace(ETAT)


# ------------------------------------------------------------------ jobs en arriere-plan
JOBS: dict = {}


_cao = threading.Lock()       # OpenCascade / CuraEngine : UN calcul lourd a la fois (OCC n'est pas thread-safe)


def _job(fn, *a):
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "etat": "en attente", "progres": 0.0, "log": ["En file d'attente..."], "resultat": None,
                 "debut": time.time()}

    def run():
        j = JOBS[jid]
        try:
            with _cao:
                j["etat"] = "en cours"
                j["resultat"] = fn(j, *a)
            j["etat"] = "termine"
            j["progres"] = 1.0
        except Exception as e:
            j["etat"] = "erreur"
            j["log"].append(f"ERREUR : {e}")
            j["trace"] = traceback.format_exc()[-2000:]
    threading.Thread(target=run, daemon=True).start()
    return jid


def _pur(o):
    """Types numpy -> types Python (serialisation JSON)."""
    import numpy as np
    if isinstance(o, dict):
        return {str(k): _pur(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_pur(v) for v in o]
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


@app.get("/api/job/{jid}")
def job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404)
    j = dict(JOBS[jid])
    j["duree_s"] = round(time.time() - j["debut"], 1)
    return _pur(j)


# ------------------------------------------------------------------ generation
class Commande(BaseModel):
    produit: str = "porte_cle"
    noms: list[str] = ["Steven"]
    police: str = "arial_black"
    hauteur: float = 16.0
    contour: float = 3.2
    jeu: float = 0.12
    mode: str = "2impressions"
    quantite: int = 1
    polices: list[str] = []          # police PAR prenom (alignee sur `noms`) ; vide -> `police`
    crochets: int = 3                # porte-serviette : nombre de crochets
    jeton_d: float = 23.25           # porte-jeton : diametre du jeton (23.25 = 1 EUR / jeton standard)
    couleurs: dict[str, str] = {}    # type d'element -> id de bobine
    jeton_motif: str = "aucun"       # aucun | initiale | qr | logo  (jeton imprime personnalise)
    jeton_texte: str = ""            # QR : contenu ; initiale : lettre (vide -> 1re lettre du prenom)
    jeton_mode: str = "incruste"     # incruste (2 impressions) | pause (changement de filament)
    jeton_image: str = ""            # id d'image televersee (/api/image)
    jeton_seuil: int | None = None
    jeton_inverser: bool | None = None


# ------------------------------------------------------------------ elements -> couleurs -> plateaux
ELEMENTS = {"porte_cle": [("base", "Base"), ("prenom", "Prenom")],
            "porte_jeton": [("corps", "Corps"), ("coulisseau", "Coulisseau"), ("bouton", "Bouton poussoir"),
                            ("prenom", "Prenom"), ("jeton", "Jeton"), ("jeton_motif", "Motif du jeton")],
            "porte_cle_jeton": [("corps", "Corps"), ("coulisseau", "Coulisseau"), ("bouton", "Bouton poussoir"),
                                ("prenom", "Prenom"), ("jeton", "Jeton"), ("jeton_motif", "Motif du jeton")],
            "porte_serviette": [("plaque", "Plaque"), ("crochets", "Crochets"), ("prenom", "Prenom")]}


def _el(out, els, i, typ, mesh, pause_z=None):
    """Enregistre un element A IMPRIMER (orientation d'impression, pose a z=0)."""
    m = mesh.copy()
    m.apply_translation(-m.bounds[0])
    f = f"el_{i:02d}_{typ}_{len(els)}.stl"
    m.export(out / f)
    els.append({"piece": i, "type": typ, "fichier": f, "ext": [round(float(v), 2) for v in m.extents],
                "pause_z": pause_z})


def _couleurs_defaut(produit, couleurs=None):
    d = lire()
    bob = [b["id"] for b in d["bobines"]]
    blanc = next((b["id"] for b in d["bobines"] if re.search("blanc|white", b["nom"], re.I)), bob[0] if bob else "b1")
    noir = next((b["id"] for b in d["bobines"] if re.search("noir|black", b["nom"], re.I)), bob[-1] if bob else "b1")
    res = {}
    for k, (t, _) in enumerate(ELEMENTS.get(produit, [])):
        c = (couleurs or {}).get(t)
        res[t] = c if c in bob else (noir if t in ("prenom", "jeton_motif") else blanc)
    return res


def _emballer(out, couleurs):
    """Range les elements par bobine sur des plateaux 195 x 195 : rangement par EMPREINTES REELLES (rotations,
    petites pieces dans les creux et les trous des grandes) ; plusieurs plateaux seulement si necessaire."""
    import trimesh
    from atelier.emballage import ranger, appliquer
    els = json.loads((out / "elements.json").read_text(encoding="utf8"))
    for f in out.glob("plateau_*.stl"):
        f.unlink()
    W = 195.0
    plats = []
    for bob, pz in sorted({(couleurs.get(e["type"], "b1"), e.get("pause_z")) for e in els}, key=lambda t: (t[0], t[1] or 0)):
        lot = [e for e in els if couleurs.get(e["type"], "b1") == bob and e.get("pause_z") == pz]
        ms = [trimesh.load(out / e["fichier"], force="mesh") for e in lot]
        poses, n = ranger(ms, W, W, 3.0)
        pre = bob + ("p" if pz else "")
        for k in range(n):
            idx = [i for i, ps in enumerate(poses) if ps[0] == k]
            if not idx:
                continue
            pid = f"{pre}_{len([p for p in plats if p['id'].startswith(pre + '_')]) + 1}"
            placees = [appliquer(ms[i], *poses[i][1:]) for i in idx]
            plaque = trimesh.util.concatenate(placees)
            plaque.export(out / f"plateau_{pid}.stl")
            emp = [round(float(x), 1) for x in plaque.bounds[1][:2] - np.minimum(plaque.bounds[0][:2], 0)]
            plats.append({"id": pid, "bobine": bob, "fichier": f"plateau_{pid}.stl", "nb": len(idx),
                          "types": sorted({lot[i]["type"] for i in idx}), "emprise": emp,
                          "tient": emp[0] <= W + 0.5 and emp[1] <= W + 0.5,
                          "pause": {"z": pz, "bobine": couleurs.get("jeton_motif", bob)} if pz else None})
    (out / "couleurs.json").write_text(json.dumps(couleurs), encoding="utf8")
    (out / "plateaux.json").write_text(json.dumps(plats), encoding="utf8")
    return plats


def _finir(out, j, produit, els, cmd, res):
    (out / "elements.json").write_text(json.dumps(els), encoding="utf8")
    c = _couleurs_defaut(produit, cmd.couleurs)
    res["couleurs"] = c
    res["elements"] = [{"type": t, "label": l} for t, l in ELEMENTS[produit]
                       if any(e["type"] == t for e in els) or (t == "jeton_motif" and any(e.get("pause_z") for e in els))]
    res["plateaux"] = _emballer(out, c)
    j["log"].append(f"{len(res['plateaux'])} plateau(x) : " + ", ".join(f"{p['id']} ({p['nb']} el.)" for p in res["plateaux"]))
    res["tient"] = all(p["tient"] for p in res["plateaux"])
    return res


class Couleurs(BaseModel):
    job: str
    couleurs: dict[str, str]


@app.post("/api/plateaux")
def plateaux_api(c: Couleurs):
    out = (JOBS_DIR / c.job).resolve()
    if not str(out).startswith(str(JOBS_DIR.resolve())) or not (out / "elements.json").exists():
        raise HTTPException(404, "job introuvable")
    with _cao:
        return {"plateaux": _emballer(out, c.couleurs)}


def _generer(j, cmd: Commande):
    from atelier.porte_cles import Style, porte_cle
    from atelier.objets import _mesh
    import trimesh
    out = JOBS_DIR / j["id"]
    out.mkdir(parents=True, exist_ok=True)
    from atelier.porte_cles import POLICES
    noms = [n.strip() for n in cmd.noms]
    pols = [(cmd.polices[i] if i < len(cmd.polices) and cmd.polices[i] in POLICES else cmd.police)
            for i in range(len(noms))]
    pieces, bases, prenoms, els = [], [], [], []
    x, y, row_h, ecart, W = 0.0, 0.0, 0.0, 4.0, 195.0          # marge de 12 mm aux bords (jupe, purge)
    lignes = [(n, p) for n, p in zip(noms, pols) if n]
    for i, (nom, pol) in enumerate(lignes):
        j["log"].append(f"Generation : {nom} ({pol})")
        st = Style(police=pol, hauteur=cmd.hauteur, contour=cmd.contour, jeu=cmd.jeu, mode=cmd.mode)
        c, rep = porte_cle(nom, st)
        mb, mp = _mesh(c["base"]), _mesh(c["prenom"])
        w, h = mb.extents[0], mb.extents[1]
        if x + w > W:
            x, y, row_h = 0.0, y + row_h + ecart, 0.0
        d = [x - mb.bounds[0][0], y - mb.bounds[0][1], 0]
        mb.apply_translation(d); mp.apply_translation(d)
        x += w + ecart
        row_h = max(row_h, h)
        f_b, f_p = f"{i:02d}_base.stl", f"{i:02d}_prenom.stl"
        mb.export(out / f_b); mp.export(out / f_p)
        bases.append(mb); prenoms.append(mp)
        _el(out, els, i, "base", mb); _el(out, els, i, "prenom", mp)
        pieces.append({"nom": nom, "police": pol, "base": f_b, "prenom": f_p, "controles": rep["controles"],
                       "volume_base_cm3": round(abs(mb.volume) / 1000, 2),
                       "volume_prenom_cm3": round(abs(mp.volume) / 1000, 2)})
        j["progres"] = 0.9 * (i + 1) / len(lignes)
    occ_y = y + row_h
    return _finir(out, j, "porte_cle", els, cmd, {"job": j["id"], "produit": "porte_cle", "pieces": pieces,
            "occupation_mm": [W, round(occ_y, 1)], "tous_ok": all(p["controles"]["ok"] for p in pieces)})


def _generer_jeton(j, cmd: Commande):
    """Porte-jetons : UN par prenom (police propre) ; sans prenom -> `quantite` porte-jetons simples."""
    from atelier.porte_jeton import porte_jeton, Jeton, Params
    from atelier.sim_jeton import simuler
    from atelier.porte_cles import POLICES
    from atelier.objets import _mesh
    import trimesh
    out = JOBS_DIR / j["id"]
    out.mkdir(parents=True, exist_ok=True)
    noms = [n.strip() for n in cmd.noms if n.strip() and n.strip() != "x"]
    pols = [(cmd.polices[i] if i < len(cmd.polices) and cmd.polices[i] in POLICES else cmd.police)
            for i in range(len(cmd.noms))]
    lignes = [(n, p) for n, p in zip([x.strip() for x in cmd.noms], pols) if n and n != "x"]
    if not lignes:
        lignes = [("", cmd.police)] * max(1, int(cmd.quantite))
    jeton = Jeton(d=float(cmd.jeton_d))
    pieces, plat_c, plat_a, els = [], [], [], []
    sim = None
    x, y, row_h, xa, ya, rowa, W, ec = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 195.0, 4.0
    for i, (nom, pol) in enumerate(lignes):
        j["log"].append(f"Porte-jeton {i + 1} : {nom or '(sans prenom)'} - jeton d{jeton.d}")
        if cmd.produit == "porte_cle_jeton":
            from atelier.porte_cle_jeton import porte_cle_jeton
            pcs, g, rep = porte_cle_jeton(nom, pol, jeton)
        else:
            pcs, g, rep = porte_jeton(jeton, Params(texte=nom, police=pol))
        if sim is None:
            j["log"].append("Simulation de la course du jeton (clipsage a 2 niveaux)")
            sim = simuler(pcs, g)
        ms = {k: _mesh(v) for k, v in pcs.items()}
        jrep = None
        if cmd.jeton_motif != "aucun":
            from atelier.jeton_perso import jeton_perso, E_JETON, EMPREINTE
            img = None
            if cmd.jeton_motif == "logo":
                fi = DATA / "images" / f"{cmd.jeton_image}.img"
                if not re.fullmatch(r"[0-9a-f]{12}", cmd.jeton_image or "") or not fi.exists():
                    raise ValueError("logo : televerse d'abord une image")
                img = fi.read_bytes()
            txt = cmd.jeton_texte.strip() or (nom[:1] if cmd.jeton_motif == "initiale" else "") or "?"
            jp, _, jrep = jeton_perso(jeton.d, cmd.jeton_motif, txt, pol, cmd.jeton_mode, img,
                                      cmd.jeton_seuil, cmd.jeton_inverser)
            j["log"].append(f"  jeton imprime : {cmd.jeton_motif} ({jrep['mode']})" + (f" - {jrep['mode_force']}" if jrep.get("mode_force") else ""))
            mj = _mesh(jp["jeton"])
            _el(out, els, i, "jeton", mj, jrep["pause_z"])
            pv = mj.copy(); pv.apply_translation([0, 0, g["z0"] + 0.16]); pv.export(out / f"{i:02d}_jeton.stl")
            if "jeton_motif" in jp:
                mm = _mesh(jp["jeton_motif"])
                _el(out, els, i, "jeton_motif", mm)
                pv = mm.copy(); pv.apply_translation([0, 0, g["z0"] + 0.16 + E_JETON - EMPREINTE]); pv.export(out / f"{i:02d}_jeton_motif.stl")
        for k, m in ms.items():
            m_ = m.copy()
            if k == "prenom":
                m_.apply_translation([0, 0, g["E"] - g["empreinte"]])     # apercu : prenom dans son empreinte
            m_.export(out / f"{i:02d}_{k}.stl")
        mb = ms["corps"]
        w, h = mb.extents[0], mb.extents[1]
        if x + w > W:
            x, y, row_h = 0.0, y + row_h + ec, 0.0
        m_ = mb.copy(); m_.apply_translation([x - m_.bounds[0][0], y - m_.bounds[0][1], 0]); plat_c.append(m_)
        _el(out, els, i, "corps", mb)
        x += w + ec; row_h = max(row_h, h)
        acc = [ms["coulisseau"], ms["bouton"]] + ([ms["prenom"]] if "prenom" in ms else [])
        for k_, m0 in zip(("coulisseau", "bouton", "prenom"), acc):
            m2 = m0.copy()
            if k_ == "bouton":                     # imprime TETE EN BAS : pas de porte-a-faux
                m2.apply_transform(trimesh.transformations.rotation_matrix(3.14159265, [1, 0, 0]))
            w2, h2 = m2.extents[0], m2.extents[1]
            if xa + w2 > W:
                xa, ya, rowa = 0.0, ya + rowa + ec, 0.0
            m2.apply_translation([xa - m2.bounds[0][0], ya - m2.bounds[0][1], -m2.bounds[0][2]])
            plat_a.append(m2); xa += w2 + ec; rowa = max(rowa, h2)
            _el(out, els, i, k_, m2)
        pieces.append({"nom": nom or f"Porte-jeton {i + 1}", "police": pol if nom else None,
                       "base": f"{i:02d}_corps.stl", "coulisseau": f"{i:02d}_coulisseau.stl",
                       "bouton": f"{i:02d}_bouton.stl", "prenom": f"{i:02d}_prenom.stl" if "prenom" in ms else None,
                       "jeton": f"{i:02d}_jeton.stl" if jrep else None,
                       "jeton_motif": f"{i:02d}_jeton_motif.stl" if jrep and jrep["mode"] == "incruste" else None,
                       "jeton_rep": jrep,
                       "controles": {**rep, "prenom_monobloc": True, "pieces_prenom": 1, "details_a_placer": 0,
                                     "mur_anneau_mm": 4.0}})
        j["progres"] = 0.9 * (i + 1) / len(lignes)
    occ = max(y + row_h, ya + rowa)
    rep0 = pieces[0]["controles"]
    return _finir(out, j, cmd.produit, els, cmd, {"job": j["id"], "produit": cmd.produit, "rapport": rep0,
            "simulation": sim, "pieces": pieces, "occupation_mm": [W, round(occ, 1)],
            "tous_ok": all(p["controles"]["ok"] for p in pieces)})


def _generer_ps(j, cmd: Commande):
    """Porte-serviettes : une plaque par prenom (police propre), crochets a plat."""
    from atelier.porte_serviette import porte_serviette, ParamsPS
    from atelier.assemblage_ps import poser_crochets, interferences
    from atelier.porte_cles import POLICES
    from atelier.objets import _mesh
    import trimesh
    out = JOBS_DIR / j["id"]
    out.mkdir(parents=True, exist_ok=True)
    noms = [n.strip() for n in cmd.noms]
    pols = [(cmd.polices[i] if i < len(cmd.polices) and cmd.polices[i] in POLICES else cmd.police)
            for i in range(len(noms))]
    lignes = [(n, p) for n, p in zip(noms, pols) if n]
    pieces, plaques, autres, els = [], [], [], []
    x, y, row_h, ecart, W = 0.0, 0.0, 0.0, 5.0, 195.0
    xa, ya, rowa = 0.0, 0.0, 0.0
    for i, (nom, pol) in enumerate(lignes):
        j["log"].append(f"Porte-serviette : {nom} ({pol}), {cmd.crochets} crochets")
        pcs, rep, g = porte_serviette(nom, pol, ParamsPS(n_crochets=max(1, min(4, cmd.crochets))))
        rep["interference_crochets_mm3"] = interferences(pcs, g)
        rep["ok"] = rep["ok"] and max(rep["interference_crochets_mm3"]) < 0.5
        mp, mn, mc = _mesh(pcs["plaque"]), _mesh(pcs["prenom"]), _mesh(pcs["crochet"])
        # apercu assemble
        mn_a = mn.copy(); mn_a.apply_translation([0, 0, g["E"] - 1.6])
        crs = []
        for T in poser_crochets(pcs, g):
            m_ = mc.copy(); m_.apply_transform(T); crs.append(m_)
        mp.export(out / f"{i:02d}_plaque.stl"); mn_a.export(out / f"{i:02d}_prenom.stl")
        trimesh.util.concatenate(crs).export(out / f"{i:02d}_crochets.stl")
        # plateau des plaques (couleur 1)
        w, h = mp.extents[0], mp.extents[1]
        if x + w > W:
            x, y, row_h = 0.0, y + row_h + ecart, 0.0
        m_ = mp.copy(); m_.apply_translation([x - m_.bounds[0][0], y - m_.bounds[0][1], 0]); plaques.append(m_)
        x += w + ecart; row_h = max(row_h, h)
        _el(out, els, i, "plaque", mp); _el(out, els, i, "prenom", mn)
        for _ in range(len(g["xs"])):
            _el(out, els, i, "crochets", mc)
        # crochets (a plat) sur le MEME plateau que la plaque (couleur 1, meme STL)
        for _ in range(len(g["xs"])):
            mh = mc.copy()
            wh, hh = mh.extents[0], mh.extents[1]
            if x + wh > W:
                x, y, row_h = 0.0, y + row_h + ecart, 0.0
            mh.apply_translation([x - mh.bounds[0][0], y - mh.bounds[0][1], -mh.bounds[0][2]]); plaques.append(mh)
            x += wh + ecart; row_h = max(row_h, hh)
        # plateau couleur 2 : prenom seul
        for m0 in [mn]:
            w2, h2 = m0.extents[0], m0.extents[1]
            if xa + w2 > W:
                xa, ya, rowa = 0.0, ya + rowa + ecart, 0.0
            m2 = m0.copy(); m2.apply_translation([xa - m2.bounds[0][0], ya - m2.bounds[0][1], -m2.bounds[0][2]])
            autres.append(m2); xa += w2 + ecart; rowa = max(rowa, h2)
        pieces.append({"nom": nom, "police": pol, "base": f"{i:02d}_plaque.stl", "prenom": f"{i:02d}_prenom.stl",
                       "crochets": f"{i:02d}_crochets.stl",
                       "controles": {**rep, "prenom_monobloc": True, "pieces_prenom": 1, "details_a_placer": 0,
                                     "mur_anneau_mm": rep["entraxe_vis_mm"]}})
        j["progres"] = 0.9 * (i + 1) / len(lignes)
    occ = max(y + row_h, ya + rowa)
    return _finir(out, j, "porte_serviette", els, cmd, {"job": j["id"], "produit": "porte_serviette", "pieces": pieces,
            "occupation_mm": [W, round(occ, 1)], "tous_ok": all(p["controles"]["ok"] for p in pieces)})


@app.post("/api/generer")
def generer(cmd: Commande):
    if cmd.produit == "porte_serviette":
        if not [n for n in cmd.noms if n.strip()]:
            raise HTTPException(400, "aucun prenom")
        return {"job": _job(_generer_ps, cmd)}
    if cmd.produit == "porte_jeton":
        return {"job": _job(_generer_jeton, cmd)}
    if cmd.produit == "porte_cle_jeton":
        if not [n for n in cmd.noms if n.strip() and n.strip() != "x"]:
            raise HTTPException(400, "aucun prenom")
        return {"job": _job(_generer_jeton, cmd)}
    if not [n for n in cmd.noms if n.strip()]:
        raise HTTPException(400, "aucun prenom")
    return {"job": _job(_generer, cmd)}


@app.get("/api/polices")
def polices():
    from atelier.porte_cles import POLICES, POLICES_INFO
    return {k: {"label": POLICES_INFO[k][1], "licence": POLICES_INFO[k][2], "vente_perso": POLICES_INFO[k][3]}
            for k in POLICES}


@app.get("/api/apercu_police/{cle}")
def apercu_police(cle: str, texte: str = "Steven"):
    """Apercu IMAGE (statique) du texte dans la police : chaque police se presente avec son propre dessin."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    from fastapi.responses import Response
    from atelier.porte_cles import POLICES
    if cle not in POLICES:
        raise HTTPException(404)
    texte = (texte or "Steven")[:24]
    cache = DATA / "apercus"
    cache.mkdir(exist_ok=True)
    f = cache / f"{cle}_{abs(hash(texte)) % 10**10}.png"
    if not f.exists():
        font = ImageFont.truetype(POLICES[cle], 64)
        bb = ImageDraw.Draw(Image.new("L", (10, 10))).textbbox((0, 0), texte, font=font)
        w, h = bb[2] - bb[0] + 24, bb[3] - bb[1] + 20
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((12 - bb[0], 10 - bb[1]), texte, font=font, fill=(240, 240, 244, 255))
        im.thumbnail((360, 90))
        im.save(f)
    return Response(f.read_bytes(), media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/fichier/{jid}/{nom}")
def fichier(jid: str, nom: str):
    f = (JOBS_DIR / jid / nom).resolve()
    if not str(f).startswith(str(JOBS_DIR.resolve())) or not f.exists():
        raise HTTPException(404)
    return FileResponse(f, filename=nom)


# ------------------------------------------------------------------ tranchage (CuraEngine, hors ligne)
class Tranche(BaseModel):
    job: str
    plateau: str            # id de plateau (ex. "b1_1")
    qualite: str = "normal"
    bobine: str = "b1"


def _trancher(j, t: Tranche):
    from atelier.slicer import trancher_plat as trancher
    d = lire()
    b = next(x for x in d["bobines"] if x["id"] == t.bobine)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", t.plateau):
        raise ValueError("plateau invalide")
    stl = JOBS_DIR / t.job / f"plateau_{t.plateau}.stl"
    out = JOBS_DIR / t.job / f"{t.plateau}_{t.qualite}.gcode"
    j["log"].append(f"CuraEngine : {t.plateau}, qualite {t.qualite}, {b['nom']} ({b['matiere']})")
    pz = None
    fp = JOBS_DIR / t.job / "plateaux.json"
    if fp.exists():
        pl = next((x for x in json.loads(fp.read_text(encoding="utf8")) if x["id"] == t.plateau), None)
        if pl and pl.get("pause"):
            pz = pl["pause"]["z"]
            j["log"].append(f"Pause changement de filament a {pz} mm")
    st = trancher(stl, out, t.qualite, b["matiere"], tuple(b.get("temp", (220, 60))), pause_z=pz)
    st["cout"] = cout_impression(st, b, d["couts"])
    st["bobine"] = b["id"]
    st["stock_suffisant"] = b["restant_g"] >= st["filament_g"]
    return st


@app.post("/api/trancher")
def trancher_api(t: Tranche):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", t.plateau):
        raise HTTPException(400, "plateau invalide")
    if not (JOBS_DIR / t.job / f"plateau_{t.plateau}.stl").exists():
        raise HTTPException(404, "plateau introuvable")
    return {"job": _job(_trancher, t)}


class Image_(BaseModel):
    data: str                # base64 (data URL acceptee)


@app.post("/api/image")
def televerser_image(im: Image_):
    """Image -> 3D : on stocke l'image (logo, dessin) ; la vectorisation se fait a la demande."""
    import base64
    raw = base64.b64decode(im.data.split(",", 1)[-1])
    if len(raw) > 12_000_000:
        raise HTTPException(413, "image trop lourde (12 Mo max)")
    from PIL import Image
    import io
    try:
        Image.open(io.BytesIO(raw)).verify()
    except Exception:
        raise HTTPException(400, "fichier image illisible")
    d = DATA / "images"
    d.mkdir(exist_ok=True)
    iid = uuid.uuid4().hex[:12]
    (d / f"{iid}.img").write_bytes(raw)
    return {"id": iid}


@app.get("/api/apercu_motif")
def apercu_motif(motif: str = "initiale", texte: str = "S", police: str = "pacifico", image: str = "",
                 seuil: int | None = None, inverser: bool | None = None, d: float = 23.25, mode: str = "incruste"):
    """Apercu PNG du motif tel qu'il sera imprime sur le jeton (+ rapport en en-tete JSON)."""
    from fastapi.responses import Response
    from atelier.jeton_perso import jeton_perso
    from atelier.image2d import apercu_png
    img = None
    if motif == "logo":
        fi = DATA / "images" / f"{image}.img"
        if not re.fullmatch(r"[0-9a-f]{12}", image or "") or not fi.exists():
            raise HTTPException(404, "image inconnue")
        img = fi.read_bytes()
    try:
        with _cao:
            _, poly, rep = jeton_perso(d, motif, texte or "?", police, mode, img, seuil, inverser)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(apercu_png(poly, cercle_mm=d), media_type="image/png",
                    headers={"X-Rapport": json.dumps(_pur(rep), ensure_ascii=True), "Cache-Control": "no-store"})


@app.get("/api/qualites")
def qualites():
    from atelier.slicer import QUALITES
    return {k: {"label": v["label"], "desc": v["desc"], "couche_mm": v["s"]["layer_height"]} for k, v in QUALITES.items()}


# ------------------------------------------------------------------ couts et prix
def cout_impression(st, bobine, c):
    h = (st.get("temps_s") or 0) / 3600
    mat = st["filament_g"] / 1000 * bobine["prix_kg"]
    elec = h * c["puissance_w"] / 1000 * c["electricite_kwh"]
    amort = h * (c["machine_prix"] / c["machine_vie_h"] + c["buse_eur_h"])
    return {"matiere": round(mat, 3), "electricite": round(elec, 3), "machine": round(amort, 3),
            "total": round(mat + elec + amort, 3), "heures": round(h, 2)}


class Prix(BaseModel):
    cout_impression_piece: float      # part de l'impression (2 plateaux / nb de pieces)
    prix_vente: float | None = None
    quantite: int = 1


@app.post("/api/prix")
def prix(p: Prix):
    c = lire()["couts"]
    fixe = p.cout_impression_piece + c["emballage"] + c["anneau"] + c["colle"] + \
        c["main_oeuvre_h"] * c["temps_assemblage_min"] / 60
    pct = (c["etsy_transaction_pct"] + c["etsy_paiement_pct"]) / 100

    def net(pv):
        frais = c["etsy_annonce"] + pv * pct + c["etsy_paiement_fixe"]
        return pv - frais - fixe, frais
    cible = c["marge_cible_pct"] / 100
    # prix tel que net = cible * prix
    pv_reco = (fixe + c["etsy_annonce"] + c["etsy_paiement_fixe"]) / max(1 - pct - cible, 0.05)
    pv = p.prix_vente if p.prix_vente is not None else round(pv_reco + 0.0049, 2)
    n, frais = net(pv)
    lo, hi = c["marche_etsy"]
    return {"cout_revient": round(fixe, 2), "frais_etsy": round(frais, 2), "prix_conseille": round(pv_reco, 2),
            "prix_vente": pv, "net_piece": round(n, 2), "marge_pct": round(100 * n / pv, 1) if pv else 0,
            "net_total": round(n * p.quantite, 2), "marche_etsy": [lo, hi],
            "position_marche": "sous le marche" if pv < lo else "au-dessus du marche" if pv > hi else "dans le marche",
            "detail": {"impression": round(p.cout_impression_piece, 3), "emballage": c["emballage"],
                       "anneau": c["anneau"], "colle": c["colle"],
                       "main_oeuvre": round(c["main_oeuvre_h"] * c["temps_assemblage_min"] / 60, 2)}}


# ------------------------------------------------------------------ filaments
@app.get("/api/etat")
def etat():
    return lire()


class Bobine(BaseModel):
    id: str | None = None
    nom: str
    marque: str = "?"
    matiere: str = "PLA"
    couleur: str = "#888888"
    restant_g: float
    initial_g: float = 1000
    prix_kg: float = 20.0
    temp: list[int] = [220, 60]


@app.post("/api/bobines")
def maj_bobine(b: Bobine):
    with _lock:
        d = lire()
        b.id = b.id or "b" + uuid.uuid4().hex[:6]
        d["bobines"] = [x for x in d["bobines"] if x["id"] != b.id] + [b.model_dump()]
        ecrire(d)
    return d["bobines"]


@app.delete("/api/bobines/{bid}")
def suppr_bobine(bid: str):
    with _lock:
        d = lire()
        d["bobines"] = [x for x in d["bobines"] if x["id"] != bid]
        ecrire(d)
    return d["bobines"]


class Consommation(BaseModel):
    bobine: str
    grammes: float
    libelle: str = ""


@app.post("/api/consommer")
def consommer(c: Consommation):
    """Deduit le filament d'une impression TERMINEE (declare par l'utilisateur)."""
    with _lock:
        d = lire()
        b = next((x for x in d["bobines"] if x["id"] == c.bobine), None)
        if not b:
            raise HTTPException(404)
        b["restant_g"] = round(max(0.0, b["restant_g"] - c.grammes), 1)
        d["historique"].append({"t": time.strftime("%Y-%m-%d %H:%M"), "bobine": b["nom"], "g": c.grammes,
                                "libelle": c.libelle})
        ecrire(d)
    return d


class Couts(BaseModel):
    couts: dict


@app.post("/api/couts")
def maj_couts(c: Couts):
    with _lock:
        d = lire()
        d["couts"].update({k: v for k, v in c.couts.items() if k in DEFAUT["couts"]})
        ecrire(d)
    return d["couts"]


# ------------------------------------------------------------------ imprimante (desactivee par defaut)
@app.get("/api/imprimante")
def imprimante():
    d = lire()["imprimante"]
    return {**d, "note": "Aucune communication tant que la connexion n'est pas activee par toi."}


@app.middleware("http")
async def sans_cache(request, call_next):
    """L'interface est rechargee a chaque fois (sinon le navigateur garde une ancienne version des JS/CSS)."""
    r = await call_next(request)
    if not request.url.path.startswith(("/api/apercu_police", "/fichier")):
        r.headers["Cache-Control"] = "no-store, must-revalidate"
    return r



# ================================================================== CREATION 3D (onglet facon Tinkercad)
C3D_DIR = ICI / "sortie" / "c3d"
C3D_DIR.mkdir(parents=True, exist_ok=True)
SCENES_DIR = DATA / "scenes"
SCENES_DIR.mkdir(exist_ok=True)


def _c3d_sauver(m, nom=""):
    fid = uuid.uuid4().hex[:12]
    m.export(C3D_DIR / f"{fid}.stl")                 # pour le navigateur
    m.export(C3D_DIR / f"{fid}.ply")                 # indexe : garde l'identite des sommets (calculs exacts)
    from atelier.c3d import analyser
    return {"fichier": fid, "nom": nom, "analyse": _pur(analyser(m))}


def _c3d_charger(fid, matrice=None):
    import trimesh
    from atelier.c3d import transformer
    if not re.fullmatch(r"[0-9a-f]{12}", fid or ""):
        raise HTTPException(400, "fichier invalide")
    f = C3D_DIR / f"{fid}.ply"
    if not f.exists():
        f = C3D_DIR / f"{fid}.stl"
    if not f.exists():
        raise HTTPException(404, "objet introuvable")
    return transformer(trimesh.load(f, force="mesh", process=False), matrice)


class C3dObj(BaseModel):
    fichier: str
    matrice: list[float] | None = None
    trou: bool = False
    bobine: str = ""
    nom: str = ""


class C3dForme(BaseModel):
    type: str
    params: dict = {}


class C3dImage(BaseModel):
    image: str
    mode: str = "relief"
    params: dict = {}


class C3dOutil(BaseModel):
    outil: str
    objets: list[C3dObj]
    params: dict = {}


class C3dImport(BaseModel):
    data: str
    nom: str = "objet.stl"
    garder: bool = False             # True : garde la position (geometrie deja en coordonnees du plateau)


class C3dScene(BaseModel):
    nom: str
    scene: dict


def _c3d_err(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/c3d/forme")
def c3d_forme(f: C3dForme):
    from atelier.c3d import forme

    def go():
        if f.type == "texte":
            with _cao:                    # le texte passe par OpenCascade (pas thread-safe)
                m = forme(f.type, f.params)
        else:
            m = forme(f.type, f.params)
        return _c3d_sauver(m, f.type)
    return _c3d_err(go)


@app.post("/api/c3d/image")
def c3d_image(im: C3dImage):
    from atelier.c3d import image_3d
    fi = DATA / "images" / f"{im.image}.img"
    if not re.fullmatch(r"[0-9a-f]{12}", im.image or "") or not fi.exists():
        raise HTTPException(404, "image inconnue (televerse-la d'abord)")
    return _c3d_err(lambda: _c3d_sauver(image_3d(fi.read_bytes(), im.mode, im.params), im.mode))


class C3dGen(BaseModel):
    nom: str
    params: dict = {}


class C3dDessin(BaseModel):
    pts: list[list[float]]
    mode: str = "extrusion"
    params: dict = {}


@app.post("/api/c3d/generer")
def c3d_generer(g: C3dGen):
    from atelier.c3d import generer
    return _c3d_err(lambda: {"objets": [_c3d_sauver(m, g.nom) for m in generer(g.nom, g.params)]})


@app.post("/api/c3d/dessin")
def c3d_dessin(d: C3dDessin):
    from atelier.c3d import dessin_extrusion, dessin_revolution
    if len(d.pts) < 3:
        raise HTTPException(400, "il faut au moins 3 points")
    p = d.params

    def go():
        if d.mode == "revolution":
            m = dessin_revolution(d.pts, float(p.get("angle", 360)), bool(p.get("lisse", False)))
        else:
            m = dessin_extrusion(d.pts, float(p.get("h", 10)), bool(p.get("lisse", False)), float(p.get("torsion", 0)),
                                 float(p.get("echelle_haut", 1)), float(p.get("epaisseur", 0)))
        return _c3d_sauver(m, "dessin")
    return _c3d_err(go)


@app.post("/api/c3d/shadowbox")
def c3d_shadowbox(im: C3dImage):
    from atelier.c3d import shadowbox
    fi = DATA / "images" / f"{im.image}.img"
    if not re.fullmatch(r"[0-9a-f]{12}", im.image or "") or not fi.exists():
        raise HTTPException(404, "image inconnue (televerse-la d'abord)")
    p = im.params

    def go():
        ms = shadowbox(fi.read_bytes(), int(p.get("couches", 5)), float(p.get("largeur", 100)), float(p.get("e_couche", 1.2)),
                       float(p.get("cadre", 6)), float(p.get("detail", 0.8)), bool(p.get("inverser", False)))
        return {"objets": [_c3d_sauver(m, f"couche {i + 1}" if i < len(ms) - 1 else "cadre") for i, m in enumerate(ms)]}
    return _c3d_err(go)


@app.post("/api/c3d/importer")
def c3d_importer(i: C3dImport):
    import base64
    from atelier.c3d import charger, reparer
    raw = base64.b64decode(i.data.split(",", 1)[-1])
    if len(raw) > 80_000_000:
        raise HTTPException(413, "fichier trop lourd (80 Mo max)")
    if not re.fullmatch(r"[\w\- .()]+\.(stl|obj|3mf|ply|glb|off)", i.nom, re.I):
        raise HTTPException(400, "format accepte : STL, OBJ, 3MF, PLY, GLB, OFF")

    def go():
        m = charger(raw, i.nom)
        if not m.is_watertight:
            m = reparer(m)
        if not i.garder:
            m.apply_translation([-m.bounds.mean(axis=0)[0], -m.bounds.mean(axis=0)[1], -m.bounds[0][2]])
        return _c3d_sauver(m, i.nom)
    return _c3d_err(go)


def _c3d_lourd(m, outil, params, delai=120):
    """Outil lourd (Minkowski...) dans un PROCESSUS separe : le serveur reste reactif, delai max = arret propre."""
    import subprocess
    import trimesh
    tmp = C3D_DIR / f"tmp_{uuid.uuid4().hex[:8]}"
    e, s_ = tmp.with_suffix(".in.ply"), tmp.with_suffix(".out.ply")
    m.export(e)
    try:
        r = subprocess.run([sys.executable, "-m", "atelier.c3d_worker", str(e), str(s_), outil, json.dumps(params)],
                           cwd=str(ICI), capture_output=True, text=True, timeout=delai, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0 or not s_.exists():
            msg = next((l[7:] for l in r.stdout.splitlines() if l.startswith("ERREUR:")), None)
            raise ValueError(msg or f"{outil} a echoue : {(r.stderr or '')[-300:]}")
        return trimesh.load(s_, force="mesh", process=False)
    except subprocess.TimeoutExpired:
        raise ValueError(f"{outil} : calcul trop long (> {delai} s) sur cette piece - essaie une valeur plus petite, "
                         f"Simplifier d'abord, ou applique-le avant de percer / grouper")
    finally:
        for f in (e, s_):
            f.unlink(missing_ok=True)


@app.post("/api/c3d/outil")
def c3d_outil(o: C3dOutil):
    """Outils : grouper, intersection, couper, decouper_plateau, orienter, reparer, simplifier, coque,
    arrondir, epaissir, lisser, analyser. Les objets arrivent DEJA transformes (matrice de la scene)."""
    from atelier import c3d
    ms = [_c3d_charger(x.fichier, x.matrice) for x in o.objets]
    p = o.params
    if not ms:
        raise HTTPException(400, "aucun objet selectionne")

    def un(fn, *a):                     # outil "une piece" : applique a CHAQUE objet selectionne (sauf percages)
        return [_c3d_sauver(fn(m, *a), x.nom or o.outil) for m, x in zip(ms, o.objets) if not x.trou]

    def go():
        t = o.outil
        if t == "grouper":
            return {"objets": [_c3d_sauver(c3d.grouper([(m, x.trou) for m, x in zip(ms, o.objets)]), "groupe")]}
        if t == "intersection":
            return {"objets": [_c3d_sauver(c3d.intersection(ms), "intersection")]}
        if t == "couper":
            ax = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[p.get("axe", "z")]
            pt = ms[0].bounds.mean(axis=0).copy()
            if p.get("position") is not None:
                pt["xyz".index(p.get("axe", "z"))] = float(p["position"])
            r = c3d.couper(ms[0], ax, pt, bool(p.get("tenons", True)), float(p.get("d_tenon", 4)), float(p.get("l_tenon", 10)),
                           connecteur=p.get("connecteur"))
            return {"objets": [_c3d_sauver(m, "morceau") for m in r["morceaux"]] +
                              [_c3d_sauver(m, "cheville") for m in r["chevilles"]]}
        if t == "decouper_plateau":
            res = []
            for m0 in ms:
                ok, ch = c3d.decouper_plateau(m0)
                res += [_c3d_sauver(m, "morceau") for m in ok] + [_c3d_sauver(m, "cheville") for m in ch]
            return {"objets": res}
        if t == "orienter":
            res, tot = [], 0.0
            for m0, x in zip(ms, o.objets):
                R, sur = c3d.orienter(m0)
                m = m0.copy(); m.apply_transform(R); tot += sur
                res.append(_c3d_sauver(m, x.nom or "oriente"))
            return {"objets": res, "surplombs_mm2": round(tot, 1)}
        if t == "reparer":
            return {"objets": un(c3d.reparer)}
        if t == "simplifier":
            return {"objets": un(c3d.simplifier, float(p.get("ratio", 0.5)))}
        if t == "densifier":                # maillage fin pour les effets de surface (apercu en direct cote navigateur)
            m = c3d._densifier(ms[0], float(p.get("taille", 0.4)), int(min(p.get("max_faces", 500_000), 1_600_000)))
            return {"objets": [_c3d_sauver(m, o.objets[0].nom or "dense")]}
        if t == "ajourer":                  # motif TRAVERSANT (diffuseur RGB, abat-jour, grille)
            from atelier.motifs import ajourer
            q = {k: p[k] for k in ("motif", "taille", "trait", "rotation", "etirement", "alea", "axe", "bas", "haut", "marge", "nettete", "du", "dv", "inverser", "exclure") if k in p}
            return {"objets": [_c3d_sauver(ajourer(m, q), x.nom or "ajoure") for m, x in zip(ms, o.objets) if not x.trou]}
        if t == "arete_info":
            ch = c3d.chaine_arete(ms[0], p["point"])
            return {"segments": ch["segments"], "convexe": ch["convexe"]}
        if t == "arrondir_arete":
            m, _ = c3d.arrondir_arete(ms[0], p["point"], float(p.get("r", 2)), bool(p.get("chanfrein", False)))
            return {"objets": [_c3d_sauver(m, o.objets[0].nom or "arrondi")]}
        if t == "integrer":                 # objets = [motif, cible]
            if len(ms) != 2:
                raise ValueError("integrer : il faut l'objet a integrer puis la surface cible")
            mode = p.get("mode", "relief")
            r = c3d.integrer(ms[0], ms[1], mode, float(p.get("profondeur", 1.0)), p.get("point"), p.get("normale"),
                             bool(p.get("epouser", True)), float(p.get("jeu", 0.12)))
            noms = {"relief": ["relief"], "graver": ["grave"], "coller": [o.objets[1].nom, o.objets[0].nom],
                    "incruster": [o.objets[1].nom or "base", "incrustation"]}[mode]
            return {"objets": [_c3d_sauver(m, n) for m, n in zip(r, noms)]}
        if t == "effet":
            return {"objets": [_c3d_sauver(c3d.effet_surface(m, p.get("effet", "moletage"), float(p.get("amplitude", 0.6)),
                                                             float(p.get("echelle", 3)), p.get("zones", "cotes")), x.nom or "texture")
                               for m, x in zip(ms, o.objets) if not x.trou]}
        if t in ("coque", "arrondir", "epaissir", "lisser"):
            return {"objets": [_c3d_sauver(_c3d_lourd(m, t, p), x.nom or t) for m, x in zip(ms, o.objets) if not x.trou]}
        if t == "analyser":
            d = lire()
            b = next((x for x in d["bobines"] if x["id"] == o.objets[0].bobine), d["bobines"][0] if d["bobines"] else {})
            import trimesh
            tout = trimesh.util.concatenate([m for m, x in zip(ms, o.objets) if not x.trou] or ms)
            prix = float(b.get("prix_kg", 20.0)) if b else 20.0
            return {"analyse": _pur(c3d.analyser(tout, b.get("matiere", "PLA"), prix_kg=prix))}
        raise HTTPException(400, f"outil inconnu : {t}")
    return _c3d_err(go)


@app.post("/api/c3d/exporter")
def c3d_exporter(o: C3dOutil):
    import trimesh
    ms = [_c3d_charger(x.fichier, x.matrice) for x in o.objets if not x.trou]
    if not ms:
        raise HTTPException(400, "rien a exporter")
    r = _c3d_sauver(trimesh.util.concatenate(ms), "export")
    return {"url": f"/c3d/{r['fichier']}.stl"}


def _c3d_imprimer(j, o: C3dOutil):
    out = JOBS_DIR / j["id"]
    out.mkdir(parents=True, exist_ok=True)
    els, couleurs, pieces = [], {}, []
    for k, x in enumerate([x for x in o.objets if not x.trou]):
        m = _c3d_charger(x.fichier, x.matrice)
        t = f"objet{k}"
        _el(out, els, k, t, m)
        couleurs[t] = x.bobine
        pieces.append({"nom": x.nom or t, "controles": {"ok": True}})
        j["progres"] = 0.8 * (k + 1) / len(o.objets)
    if not els:
        raise ValueError("aucun solide a imprimer (les percages ne s'impriment pas)")
    (out / "elements.json").write_text(json.dumps(els), encoding="utf8")
    plats = _emballer(out, couleurs)
    j["log"].append(f"{len(plats)} plateau(x) : " + ", ".join(p["id"] for p in plats))
    return {"job": j["id"], "produit": "creation", "pieces": pieces, "plateaux": plats, "couleurs": couleurs,
            "elements": [{"type": f"objet{k}", "label": p["nom"]} for k, p in enumerate(pieces)],
            "tient": all(p["tient"] for p in plats), "tous_ok": True, "occupation_mm": [195, 0]}


@app.post("/api/c3d/imprimer")
def c3d_imprimer(o: C3dOutil):
    return {"job": _job(_c3d_imprimer, o)}


@app.post("/api/c3d/dense")
def c3d_dense(o: C3dOutil):
    """Maillage FIN indexe en binaire brut (en-tete nv, nf en uint32, puis positions float32, puis indices
    uint32) : l'apercu des effets de surface se calcule dans le navigateur, sans STL ni analyse."""
    import numpy as np
    from fastapi.responses import Response
    from atelier import c3d
    m = _c3d_charger(o.objets[0].fichier, o.objets[0].matrice)
    p = o.params
    d = c3d._densifier(m, float(p.get("taille", 0.25)), int(min(p.get("max_faces", 800_000), 1_600_000)))
    v = np.ascontiguousarray(d.vertices, np.float32)
    f = np.ascontiguousarray(d.faces, np.uint32)
    return Response(np.array([len(v), len(f)], np.uint32).tobytes() + v.tobytes() + f.tobytes(),
                    media_type="application/octet-stream")


@app.post("/api/c3d/geometrie")
async def c3d_geometrie(request: Request):
    """Recoit un maillage indexe binaire (meme format que /api/c3d/dense) -> nouvel objet."""
    import numpy as np
    import trimesh
    raw = await request.body()
    if len(raw) > 200_000_000:
        raise HTTPException(413, "maillage trop lourd")
    nv, nf = np.frombuffer(raw[:8], np.uint32)
    v = np.frombuffer(raw[8:8 + nv * 12], np.float32).reshape(-1, 3).astype(float)
    f = np.frombuffer(raw[8 + nv * 12:8 + nv * 12 + nf * 12], np.uint32).reshape(-1, 3).astype(np.int64)
    if f.max(initial=0) >= nv:
        raise HTTPException(400, "maillage invalide")
    m = trimesh.Trimesh(v, f, process=False)
    nom = request.query_params.get("nom", "texture")[:80]
    return _c3d_sauver(m, nom)


# ================================================================== KEYCAPS (onglet dedie)
class KcTouche(BaseModel):
    params: dict = {}
    image: str = ""


class KcLot(BaseModel):
    items: list[dict] = []           # {nom, clavier, qte, params, image}
    bobines: dict = {}               # role (touche, legende) -> bobine


def _kc_image(iid):
    if not iid:
        return None
    fi = DATA / "images" / f"{iid}.img"
    if not re.fullmatch(r"[0-9a-f]{12}", iid) or not fi.exists():
        raise HTTPException(404, "image inconnue")
    return fi.read_bytes()


@app.get("/api/kc/options")
def kc_options():
    from atelier.keycaps import PROFILS, TIGES
    return {"profils": {k: {"nom": v["nom"], "rangs": v["rangs"], "dish": v["dish"], "creux": v["creux"], "haut": v["haut"]}
                        for k, v in PROFILS.items()}, "tiges": TIGES}


@app.post("/api/kc/touche")
def kc_touche(t: KcTouche):
    from atelier.keycaps import keycap_complet
    img = _kc_image(t.image)

    def go():
        with _cao:                                    # les legendes texte passent par OpenCascade
            pieces, info = keycap_complet(t.params, img)
        return {"objets": [{**_c3d_sauver(m, role), "role": role} for m, role in pieces], "info": _pur(info)}
    return _c3d_err(go)


def _kc_fabriquer(j, k: KcLot, out):
    """Genere chaque touche du lot (x quantite) -> [(maillage, role, nom_fichier)]."""
    from atelier.keycaps import keycap_complet
    res, total = [], sum(max(1, int(it.get("qte", 1))) for it in k.items)
    n = 0
    for it in k.items:
        p = it.get("params", {})
        img = _kc_image(it.get("image", ""))
        nom = re.sub(r"[^\w\-]+", "_", f"{it.get('clavier') or 'clavier'}_{it.get('nom') or p.get('texte') or 'touche'}")[:60]
        pieces, info = keycap_complet(p, img)             # deja sous le verrou _cao (tache de fond)
        for q in range(max(1, int(it.get("qte", 1)))):
            n += 1
            for m, role in pieces:
                res.append((m, role, f"{nom}_{q + 1}_{role}"))
            j["progres"] = 0.85 * n / total
        j["log"].append(f"{it.get('clavier', '')} : {it.get('nom') or p.get('texte')} x{it.get('qte', 1)}")
    return res


def _kc_lot_imprimer(j, k: KcLot):
    out = JOBS_DIR / j["id"]
    out.mkdir(parents=True, exist_ok=True)
    els, pieces = [], []
    for i, (m, role, nom) in enumerate(_kc_fabriquer(j, k, out)):
        _el(out, els, i, role, m)
        if role == "touche":
            pieces.append({"nom": nom, "controles": {"ok": True}})
    (out / "elements.json").write_text(json.dumps(els), encoding="utf8")
    ids = [b["id"] for b in lire()["bobines"]]
    coul = {"touche": k.bobines.get("touche") or (ids[0] if ids else "b1"), "legende": k.bobines.get("legende") or (ids[-1] if ids else "b1")}
    plats = _emballer(out, coul)
    return {"job": j["id"], "produit": "keycaps", "pieces": pieces, "plateaux": plats, "couleurs": coul,
            "elements": [{"type": "touche", "label": "Touches"}, {"type": "legende", "label": "Legendes / inserts"}],
            "tient": all(p["tient"] for p in plats), "tous_ok": True, "occupation_mm": [195, 0]}


def _kc_lot_export(j, k: KcLot):
    """Zip : un STL par touche (et par legende incrustee), + un STL par plateau-couleur pret a trancher ailleurs."""
    import zipfile
    out = JOBS_DIR / j["id"]
    out.mkdir(parents=True, exist_ok=True)
    zp = out / "keycaps.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for m, role, nom in _kc_fabriquer(j, k, out):
            m = m.copy()
            m.apply_translation([-m.bounds.mean(0)[0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
            z.writestr(f"{'legendes' if role == 'legende' else 'touches'}/{nom}.stl", m.export(file_type="stl"))
    return {"zip": f"/fichier/{j['id']}/keycaps.zip", "fichiers": len(zipfile.ZipFile(zp).namelist())}


@app.post("/api/kc/lot/imprimer")
def kc_lot_imprimer(k: KcLot):
    if not k.items:
        raise HTTPException(400, "lot vide")
    if sum(max(1, int(i.get("qte", 1))) for i in k.items) > 200:
        raise HTTPException(400, "200 touches maximum par lot")
    return {"job": _job(_kc_lot_imprimer, k)}


@app.post("/api/kc/lot/export")
def kc_lot_export(k: KcLot):
    if not k.items:
        raise HTTPException(400, "lot vide")
    return {"job": _job(_kc_lot_export, k)}


# ================================================================== SHWORK (conception mecanique)
class MecaPiece(BaseModel):
    nom: str
    params: dict = {}


@app.get("/api/meca/catalogue")
def meca_catalogue():
    from atelier.meca import CATALOGUE
    return {k: {"nom": c["nom"], "cat": c["cat"], "champs": c["champs"]} for k, c in CATALOGUE.items()}


@app.get("/api/modeles")
def modeles():
    """Modeles de PROJET (chacun a sa propre interface de personnalisation, construite depuis son schema)."""
    from atelier.meca import CATALOGUE
    return {k: {"nom": c["nom"], "description": c.get("description", ""), "couleurs": c.get("couleurs", {}), "champs": c["champs"],
                "simulation": c.get("simulation")}
            for k, c in CATALOGUE.items() if c["cat"] == "Projets"}


@app.post("/api/meca/export")
def meca_export(m: MecaPiece):
    """Zip des pieces d'un modele (une par fichier, orientation d'impression)."""
    import zipfile, io
    from fastapi.responses import Response
    from atelier.meca import generer_piece
    def go():
        with _cao:
            ms, info = generer_piece(m.nom, m.params)
        noms = info.get("noms") or [f"piece_{i + 1}" for i in range(len(ms))]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n, x in zip(noms, ms):
                x = x.copy(); x.apply_translation([-x.bounds.mean(0)[0], -x.bounds.mean(0)[1], -x.bounds[0][2]])
                z.writestr(f"{m.nom}_{n}.stl", x.export(file_type="stl"))
            z.writestr("a_acheter.txt", chr(10).join(info.get("quincaillerie", [])))
            # TOUT sur le moins de plateaux possible (meme rangement que l'impression) -> pret a trancher ailleurs
            from atelier.emballage import ranger, appliquer
            import trimesh as _tm
            imp = [x for n, x in zip(noms, ms) if not n.startswith("_")]
            poses, nb = ranger(imp, 195.0, 195.0, 3.0)
            for k in range(nb):
                pl = _tm.util.concatenate([appliquer(x, *ps[1:]) for x, ps in zip(imp, poses) if ps[0] == k])
                z.writestr(f"PLATEAU_{k + 1}_sur_{nb}_{m.nom}.stl", pl.export(file_type="stl"))
        return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{m.nom}.zip"'})
    return _c3d_err(go)


class PerfCompresseur(BaseModel):
    params: dict = {}
    rpm: float = 1200
    optimiser: bool = False


@app.post("/api/compresseur/performances")
def compresseur_perf(c: PerfCompresseur):
    """Simulation du CYCLE REEL du compresseur Wankel (volumes des chambres, lumieres, clapet, fuites)."""
    from atelier import sim_wankel as sw
    from atelier.wankel import compresseur
    def go():
        p = c.params
        compact = p.get("version") == "compact"
        m = float(p.get("module", 0.8 if compact else 1.0)); Zr = int(float(p.get("dents_rotor", 24 if compact else 30))); Zr -= Zr % 3
        e = m * (Zr - Zr * 2 // 3) / 2; R = float(p.get("rapport_K", 7.0)) * e; b = float(p.get("largeur", 10 if compact else 16))
        kw = {"jeu": float(p.get("jeu", 0.15)), "jeu_flanc": float(p.get("jeu_flanc", 0.2)),
              "ang_adm": float(p.get("angle_admission", 205)), "ang_ref": float(p.get("angle_refoulement", 86))}
        opt = None
        if c.optimiser:
            opt = sw.optimiser_lumieres(e, R, b, c.rpm, 2.0, jeu=kw["jeu"], jeu_flanc=kw["jeu_flanc"])
            kw["ang_adm"], kw["ang_ref"] = opt["angle_admission"], opt["angle_refoulement"]
        r = sw.courbe(e, R, b, c.rpm, 6.0, 0.25, **kw)
        return _pur({"rpm": c.rpm, "courbe": r["points"], "pression_maxi_bar": r["pression_maxi_bar"], "cycle": r["cycle_1bar"], "optimum": opt,
                     "geometrie": {"e": e, "R": R, "b": b}})
    return _c3d_err(go)


@app.post("/api/meca/piece")
def meca_piece(m: MecaPiece):
    from atelier.meca import generer_piece
    def go():
        ms, info = generer_piece(m.nom, m.params)
        return {"objets": [_c3d_sauver(x, m.nom) for x in ms], "info": _pur(info)}
    return _c3d_err(go)


# ================================================================== PROJETS (chaque projet : type + donnees + miniature)
PROJETS_DIR = DATA / "projets"
PROJETS_DIR.mkdir(exist_ok=True)
(PROJETS_DIR / "corbeille").mkdir(exist_ok=True)


class Projet(BaseModel):
    id: str = ""
    nom: str
    type: str                        # creation3d | keycaps | swork | ...
    donnees: dict = {}
    miniature: str = ""              # data:image/png;base64,...
    description: str = ""


def _pid_ok(pid):
    if not re.fullmatch(r"[0-9a-f]{12}", pid or ""):
        raise HTTPException(400, "identifiant de projet invalide")
    return pid


def _migrer_scenes():
    """Les scenes enregistrees avant l'onglet Projets deviennent des projets Creation 3D (une seule fois)."""
    for f in SCENES_DIR.glob("*.json"):
        marque = f.with_suffix(".migre")
        if marque.exists():
            continue
        pid = uuid.uuid4().hex[:12]
        d = {"id": pid, "nom": f.stem, "type": "creation3d", "donnees": json.loads(f.read_text(encoding="utf8")),
             "miniature": "", "description": "importe de Creation 3D", "date": f.stat().st_mtime, "cree": f.stat().st_mtime}
        (PROJETS_DIR / f"{pid}.json").write_text(json.dumps(d), encoding="utf8")
        marque.write_text(pid, encoding="utf8")


@app.get("/api/projets")
def projets_liste():
    _migrer_scenes()
    out = []
    for f in PROJETS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf8"))
            out.append({k: d.get(k) for k in ("id", "nom", "type", "date", "cree", "description")} |
                       {"miniature": bool(d.get("miniature")), "taille": len(d.get("donnees", {}).get("objets", []) or [])})
        except Exception:
            continue
    return sorted(out, key=lambda x: -(x.get("date") or 0))


@app.get("/api/projets/{pid}")
def projet_lire(pid: str):
    f = PROJETS_DIR / f"{_pid_ok(pid)}.json"
    if not f.exists():
        raise HTTPException(404, "projet introuvable")
    return json.loads(f.read_text(encoding="utf8"))


@app.get("/api/projets/{pid}/miniature")
def projet_miniature(pid: str):
    import base64
    from fastapi.responses import Response
    d = projet_lire(pid)
    m = d.get("miniature") or ""
    if not m.startswith("data:image"):
        raise HTTPException(404)
    return Response(base64.b64decode(m.split(",", 1)[1]), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/projets")
def projet_ecrire(p: Projet):
    if not p.nom.strip() or len(p.nom) > 80:
        raise HTTPException(400, "nom de projet requis (80 caracteres max)")
    pid = p.id or uuid.uuid4().hex[:12]
    _pid_ok(pid)
    f = PROJETS_DIR / f"{pid}.json"
    ancien = json.loads(f.read_text(encoding="utf8")) if f.exists() else {}
    d = {"id": pid, "nom": p.nom.strip(), "type": p.type, "donnees": p.donnees, "description": p.description,
         "miniature": p.miniature or ancien.get("miniature", ""), "date": time.time(), "cree": ancien.get("cree", time.time())}
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf8")
    tmp.replace(f)
    return {"id": pid}


@app.post("/api/projets/{pid}/dupliquer")
def projet_dupliquer(pid: str):
    d = projet_lire(pid)
    d["id"] = uuid.uuid4().hex[:12]
    d["nom"] = (d["nom"] + " (copie)")[:80]
    d["date"] = d["cree"] = time.time()
    (PROJETS_DIR / f"{d['id']}.json").write_text(json.dumps(d), encoding="utf8")
    return {"id": d["id"]}


@app.delete("/api/projets/{pid}")
def projet_supprimer(pid: str):
    """Pas d'effacement definitif : le projet part dans data/projets/corbeille (recuperable)."""
    f = PROJETS_DIR / f"{_pid_ok(pid)}.json"
    if not f.exists():
        raise HTTPException(404)
    f.replace(PROJETS_DIR / "corbeille" / f.name)
    return {"ok": True}


@app.get("/c3d/{nom}")
def c3d_fichier(nom: str):
    if not re.fullmatch(r"[0-9a-f]{12}\.stl", nom):
        raise HTTPException(404)
    f = C3D_DIR / nom
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, filename=nom, headers={"Cache-Control": "max-age=86400"})


@app.get("/api/c3d/scenes")
def c3d_scenes():
    return sorted([{"nom": f.stem, "date": f.stat().st_mtime} for f in SCENES_DIR.glob("*.json")], key=lambda x: -x["date"])


@app.get("/api/c3d/scene/{nom}")
def c3d_scene_lire(nom: str):
    f = SCENES_DIR / f"{nom}.json"
    if not re.fullmatch(r"[\w\- ]{1,60}", nom) or not f.exists():
        raise HTTPException(404)
    return json.loads(f.read_text(encoding="utf8"))


@app.post("/api/c3d/scene")
def c3d_scene_ecrire(s: C3dScene):
    if not re.fullmatch(r"[\w\- ]{1,60}", s.nom):
        raise HTTPException(400, "nom de projet : lettres, chiffres, espaces, - et _")
    (SCENES_DIR / f"{s.nom}.json").write_text(json.dumps(s.scene), encoding="utf8")
    return {"ok": True}




class C3dZip(BaseModel):
    pieces: list[dict]          # [{fichier, nom}]
    nom: str = "pieces"


@app.post("/api/c3d/zip")
def c3d_zip(z: C3dZip):
    """Lot de pieces -> ZIP de STL separes (1 fichier par piece, nomme d'apres la piece)."""
    import io, zipfile
    from fastapi.responses import Response
    buf = io.BytesIO()
    vus = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in z.pieces:
            f = str(p.get("fichier", ""))
            if not re.fullmatch(r"[0-9a-f]{12}", f) or not (C3D_DIR / f"{f}.stl").exists():
                continue
            n = re.sub(r"[^\w\-]+", "_", str(p.get("nom") or f))[:60]
            vus[n] = vus.get(n, 0) + 1
            zf.write(C3D_DIR / f"{f}.stl", f"{n}{'_' + str(vus[n]) if vus[n] > 1 else ''}.stl")
    nom = re.sub(r"[^\w\-]+", "_", z.nom)[:40] or "pieces"
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nom}.zip"'})


@app.post("/api/c3d/logo")
def c3d_logo(p: dict):
    """Logo SHWork vectorise, en relief (pour l'apposer sur une surface avec Integrer)."""
    from atelier.logo import logo_3d
    def f():
        m = logo_3d(float(p.get("largeur", 40)), float(p.get("epaisseur", 1.2)), p.get("partie", "mot"), float(p.get("socle", 0)))
        return _c3d_sauver(m, "logo_shwork")
    return _c3d_err(f)


# le site statique EN DERNIER (sinon il masque les routes declarees apres lui)
app.mount("/", StaticFiles(directory=str(ICI / "web"), html=True), name="web")
