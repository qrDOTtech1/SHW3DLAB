"""Test de bout en bout des produits via le serveur en marche (stdlib uniquement, aucune imprimante)."""
import json
import time
import urllib.request

B = "http://localhost:8890"


def req(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=data, headers={"Content-Type": "application/json"} if data else {})
    return json.loads(urllib.request.urlopen(r, timeout=60).read())


def attendre(jid):
    while True:
        j = req("/api/job/" + jid)
        if j["etat"] in ("termine", "erreur"):
            return j
        time.sleep(0.5)


j = attendre(req("/api/generer", {"noms": ["Steven", "Léa", "Noah"], "polices": ["pricedown", "pacifico", "bungee"],
                                 "police": "arial_black"})["job"])
print("porte-cles polices mixtes :", j["etat"], [(p["nom"], p["police"], p["controles"]["ok"]) for p in j["resultat"]["pieces"]])
j = attendre(req("/api/generer", {"produit": "porte_serviette", "noms": ["Steven", "Famille Martin"],
                                 "polices": ["pacifico", "lobster"], "crochets": 3})["job"])
print("porte-serviettes :", j["etat"], j["duree_s"], "s", j["log"][-1:] if j["etat"] == "erreur" else "")
if j["etat"] == "termine":
    for p in j["resultat"]["pieces"]:
        c = p["controles"]
        print("  ", p["nom"], p["police"], "ok", c["ok"], c["dimensions_mm"], "entraxe", c["entraxe_vis_mm"],
              "interf", c["interference_crochets_mm3"], "coef crochet", c["crochet_coef"])
    print("   plateau", j["resultat"]["occupation_mm"], "tient", j["resultat"]["tient"])
    t = attendre(req("/api/trancher", {"job": j["resultat"]["job"], "plateau": j["resultat"]["plateaux"][0]["id"], "qualite": "normal", "bobine": j["resultat"]["plateaux"][0]["bobine"]})["job"])
    if t["etat"] == "termine":
        r = t["resultat"]
        print("tranchage plaques :", r["temps_s"] // 60, "min", r["filament_g"], "g", "securite", r["securite"]["ok"],
              r["securite"]["zone_extrudee_mm"])
    else:
        print("tranchage :", t["etat"], t["log"][-1:])
