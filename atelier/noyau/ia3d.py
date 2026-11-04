"""IA LOCALE (image vers 3D niveau 2) : detection de la carte graphique au demarrage, installation automatique si elle suffit."""
from __future__ import annotations

import subprocess
import threading

NOWIN = 0x08000000
VRAM_MINI_MO = 7500                                   # TripoSG a mesure 6.1 Go de pic : il faut une carte 8 Go
etat = {"dispo": False, "carte": "", "vram_go": 0, "raison": "", "installation": "attente"}


def detecter() -> dict:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True,
                           text=True, timeout=15, creationflags=NOWIN)
        cartes = [l.rsplit(",", 1) for l in r.stdout.strip().splitlines() if "," in l]
    except Exception:
        cartes = []
    if not cartes:
        etat.update(dispo=False, raison="aucune carte graphique NVIDIA detectee", installation="sans objet")
        return etat
    nom, mo = max(cartes, key=lambda c: float(c[1]))
    etat.update(carte=nom.strip(), vram_go=round(float(mo) / 1024, 1))
    if float(mo) < VRAM_MINI_MO:
        etat.update(dispo=False, raison=f"{nom.strip()} : {etat['vram_go']} Go de memoire graphique, il en faut 8", installation="sans objet")
    else:
        etat.update(dispo=True, raison="")
    return etat


def preparer():
    """Au demarrage du serveur, en tache de fond. Plusieurs Go la premiere fois, rien les fois suivantes."""
    def tourner():
        detecter()
        if not etat["dispo"]:
            return
        etat["installation"] = "en cours"
        try:
            from atelier.produits.figurine import _installer, telecharger_poids
            racine, exe = _installer()
            telecharger_poids(racine, exe)
            etat["installation"] = "pret"
        except Exception as e:
            etat["installation"] = f"echec : {str(e)[:200]}"
    threading.Thread(target=tourner, daemon=True, name="ia3d").start()
