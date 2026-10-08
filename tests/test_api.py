"""Tests de bout en bout de l'API (aucune communication avec l'imprimante).
Les donnees reelles (data/atelier.json : stock de filament) sont sauvegardees puis RESTAUREES."""
import json
import shutil
import sys
import threading
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ICI))
ETAT = ICI / "data" / "atelier.json"
SAUVE = ICI / "data" / "atelier.json.sauvegarde_tests"

from fastapi.testclient import TestClient  # noqa: E402

RES = []


def check(nom, cond, detail=""):
    RES.append((nom, bool(cond), detail))
    print(("OK   " if cond else "ECHEC") + f" {nom} {detail}")


def attendre(c, jid, t_max=900):
    t0 = time.time()
    while time.time() - t0 < t_max:
        j = c.get(f"/api/job/{jid}").json()
        if j["etat"] in ("termine", "erreur"):
            return j
        time.sleep(0.5)
    return {"etat": "timeout"}


def main():
    if ETAT.exists():
        shutil.copy(ETAT, SAUVE)
    try:
        from server.app import app
        c = TestClient(app)
        e = c.get("/api/etat").json()
        check("etat lisible", "bobines" in e, f"{len(e['bobines'])} bobines")
        p = c.get("/api/polices").json()
        check("polices", len(p) >= 15 and "pricedown" in p, f"{len(p)} polices")
        check("pricedown marquee licence perso", p.get("pricedown", {}).get("vente_perso") is False)
        r = c.get("/api/apercu_police/pricedown?texte=GTA")
        check("apercu police (image)", r.status_code == 200 and r.headers["content-type"] == "image/png")
        check("apercu police inconnue -> 404", c.get("/api/apercu_police/xxx").status_code == 404)
        q = c.get("/api/qualites").json()
        check("3 qualites", set(q) == {"rapide", "normal", "art"})
        # --- generation porte-cles
        jid = c.post("/api/generer", json={"noms": ["Steven", "Jean Paul"], "police": "pacifico"}).json()["job"]
        j = attendre(c, jid)
        ok = j["etat"] == "termine" and j["resultat"]["tous_ok"]
        check("generation 2 porte-cles", ok, j["etat"])
        gen = j.get("resultat") or {}
        # --- generations simultanees (file d'attente, pas de crash OCC)
        jids = [c.post("/api/generer", json={"noms": [n], "police": "arial_black"}).json()["job"] for n in ("Lea", "Tom")]
        jjs = [attendre(c, x) for x in jids]
        check("2 generations simultanees", all(x["etat"] == "termine" for x in jjs), str([x["etat"] for x in jjs]))
        # --- porte-jeton
        jid = c.post("/api/generer", json={"produit": "porte_jeton", "quantite": 2, "noms": ["x"]}).json()["job"]
        j2 = attendre(c, jid)
        check("generation porte-jeton", j2["etat"] == "termine" and j2["resultat"]["tous_ok"], j2["etat"])
        if j2["etat"] == "termine":
            sim = j2["resultat"]["simulation"]
            stable = [c_ for c_, v in sim if v == 0 and c_ > 1]
            check("porte-jeton : position sortie stable", any(5 <= x <= 6.5 for x in stable), str(stable))
        # --- refus propres
        check("aucun prenom -> 400", c.post("/api/generer", json={"noms": ["  "]}).status_code == 400)
        jid = c.post("/api/generer", json={"noms": ["\U0001F600"], "police": "arial_black"}).json()["job"]
        jx = attendre(c, jid)
        check("emoji seul -> erreur claire", jx["etat"] == "erreur" and "dessinable" in " ".join(jx["log"]), jx["log"][-1:])
        # --- securite fichiers (traversee de dossier)
        if gen:
            r = c.get(f"/fichier/{gen['job']}/..%2F..%2F..%2Fdata%2Fatelier.json")
            check("traversee de dossier bloquee", r.status_code == 404, str(r.status_code))
        # --- couleur par element -> plateaux
        if gen:
            bids = [b["id"] for b in e["bobines"]]
            r = c.post("/api/plateaux", json={"job": gen["job"], "couleurs": {"base": bids[0], "prenom": bids[0]}}).json()
            check("meme bobine -> 1 plateau", len(r["plateaux"]) == 1, r)
            r = c.post("/api/plateaux", json={"job": gen["job"], "couleurs": {"base": bids[0], "prenom": bids[-1]}}).json()
            check("2 bobines -> 2 plateaux", len(r["plateaux"]) == (1 if len(bids) == 1 else 2), r)
            gen["plateaux"] = r["plateaux"]
            check("plateau invalide refuse", c.post("/api/trancher", json={"job": gen["job"], "plateau": "../x"}).status_code == 400)
        # --- tranchage + controle de securite G-code
        if gen:
            bid = e["bobines"][0]["id"]
            jid = c.post("/api/trancher", json={"job": gen["job"], "plateau": gen["plateaux"][0]["id"], "qualite": "rapide", "bobine": gen["plateaux"][0]["bobine"]}).json()["job"]
            jt = attendre(c, jid)
            ok = jt["etat"] == "termine" and jt["resultat"]["securite"]["ok"]
            check("tranchage + securite G-code", ok, jt["etat"] + " " + str(jt.get("resultat", {}).get("securite", {}).get("zone_extrudee_mm")))
            if ok:
                z = jt["resultat"]["securite"]["zone_extrudee_mm"]
                check("G-code dans le volume K2 SE", z["X"][1] <= 220 and z["Y"][1] <= 215 and z["X"][0] >= 0 and z["Y"][0] >= 0, str(z))
                check("stats tranchage coherentes", jt["resultat"]["filament_g"] > 0 and jt["resultat"]["temps_s"] > 60)
        # --- prix
        r = c.post("/api/prix", json={"cout_impression_piece": 0.3, "quantite": 10}).json()
        check("prix conseille", 2 < r["prix_conseille"] < 15 and abs(r["marge_pct"] - 55) < 1, f"{r['prix_conseille']} EUR, marge {r['marge_pct']}%")
        r = c.post("/api/prix", json={"cout_impression_piece": 0.3, "prix_vente": 1.0}).json()
        check("prix sous le cout -> net negatif signale", r["net_piece"] < 0 and r["position_marche"] == "sous le marche")
        # --- filaments (sur la copie)
        r = c.post("/api/bobines", json={"nom": "TEST", "restant_g": 100, "matiere": "PETG"}).json()
        tid = next(b["id"] for b in r if b["nom"] == "TEST")
        d = c.post("/api/consommer", json={"bobine": tid, "grammes": 250, "libelle": "test"}).json()
        b = next(b for b in d["bobines"] if b["id"] == tid)
        check("consommation > stock -> borne a 0", b["restant_g"] == 0)
        r = c.delete(f"/api/bobines/{tid}").json()
        check("suppression bobine", all(x["id"] != tid for x in r))
        check("consommation bobine inconnue -> 404", c.post("/api/consommer", json={"bobine": "zz", "grammes": 1}).status_code == 404)
        imp = c.get("/api/imprimante").json()
        check("imprimante : connexion desactivee", imp["connexion_active"] is False)
    finally:
        if SAUVE.exists():
            shutil.move(SAUVE, ETAT)
            print("donnees reelles restaurees")
    n_ok = sum(1 for _, o, _ in RES if o)
    print(f"\n{n_ok}/{len(RES)} tests OK")


if __name__ == "__main__":
    main()
