"""SAUVEGARDE DES PROJETS entre postes : GitHub sert de serveur de sauvegarde, sans toucher au code.

Les donnees (data/projets, data/images, data/bases) vivent dans un depot git a part (.git-donnees, branche "donnees" du
meme GitHub) : enregistrer un projet n'est plus une mise a jour de l'application.
Toutes les 2 min et apres chaque enregistrement : commit local, recuperation, envoi. Meme projet modifie sur deux postes :
la version la plus recente gagne, l'autre reste dans l'historique.
A cote, le code (branche main) se met a jour tout seul s'il n'y a aucune modification locale ; l'app propose de recharger.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

ICI = Path(__file__).resolve().parents[2]
DOSSIERS = ["data/projets", "data/images", "data/bases"]
GD = ICI / ".git-donnees"
BRANCHE = "donnees"
NOWIN = 0x08000000 if os.name == "nt" else 0
_verrou = threading.Lock()
_minuteur: threading.Timer | None = None
etat = {"derniere": None, "message": "jamais synchronise", "ok": None, "recus": 0, "envoyes": 0, "code": ""}


def _run(args, timeout=120, env=None):
    try:
        for _ in range(6):
            r = subprocess.run(args, cwd=ICI, capture_output=True, text=True, timeout=timeout, encoding="utf8",
                               errors="replace", creationflags=NOWIN, env=env)
            sortie = (r.stdout + r.stderr).strip()
            if "index.lock" not in sortie:
                break
            time.sleep(2)
        return r.returncode, sortie
    except Exception as e:
        return 1, str(e)


def git(*args, timeout=120):                         # depot du CODE
    return _run(["git", *args], timeout)


def gd(*args, timeout=300):                          # depot des DONNEES
    return _run(["git", f"--git-dir={GD}", f"--work-tree={ICI}", *args], timeout,
                dict(os.environ, GIT_EDITOR="true", GIT_MERGE_AUTOEDIT="no"))


def _poste() -> str:
    c, nom = git("config", "user.name")
    return nom if c == 0 and nom else f"SHW 3DLAB {socket.gethostname()}"


def _ident() -> list[str]:
    return ["-c", f"user.name={_poste()}", "-c", f"user.email=shw3dlab@{socket.gethostname()}.local"]


def _initialiser() -> bool:
    if (GD / "HEAD").exists():
        return True
    c, url = git("remote", "get-url", "origin")
    if c:
        return False
    gd("init", "-q", "-b", BRANCHE)
    gd("remote", "add", "origin", url)
    if gd("fetch", "-q", "origin", BRANCHE)[0] == 0:
        gd("reset", "-q", "--mixed", f"origin/{BRANCHE}")
        gd("checkout-index", "-a")                   # restaure ce qui manque, n'ecrase rien d'existant
    return True


def _date(txt: str) -> float:
    try:
        return float(json.loads(txt).get("date", 0))
    except Exception:
        return 0.0


def _resoudre_conflits():
    _, lst = gd("diff", "--name-only", "--diff-filter=U")
    for f in [l for l in lst.splitlines() if l.strip()]:
        c_l, local = gd("show", f":2:{f}")
        c_a, amont = gd("show", f":3:{f}")
        if c_l and c_a:
            gd("rm", "-q", f)
            continue
        garde_local = (c_a != 0) or (c_l == 0 and _date(local) >= _date(amont))
        gd("checkout", "--ours" if garde_local else "--theirs", "--", f)
        gd("add", "-f", f)


def majour_code():
    """Code : avance tout seul si rien n'est en cours sur ce poste (toi, Hugo, une session Claude)."""
    if git("fetch", "-q", "origin", "main")[0]:
        return
    _, retard = git("rev-list", "--count", "HEAD..origin/main")
    if retard.strip() in ("", "0"):
        etat["code"] = "a jour"
    elif git("status", "--porcelain", "--untracked-files=no")[1].strip() or git("rev-list", "--count", "origin/main..HEAD")[1].strip() != "0":
        etat["code"] = "nouveau code disponible, modifications locales en cours"
    else:
        etat["code"] = "mis a jour" if git("merge", "-q", "--ff-only", "origin/main")[0] == 0 else "mise a jour impossible"


def synchroniser(pousser=True) -> dict:
    with _verrou:
        if not _initialiser():
            return _fin(False, "depot GitHub introuvable", 0, 0)
        gd("add", "-f", "-A", "--", *DOSSIERS)
        _, diff = gd("diff", "--cached", "--name-only")
        envoyes = len([l for l in diff.splitlines() if l.strip()])
        if envoyes:
            gd(*_ident(), "commit", "-q", "-m", f"sauvegarde : {_poste()} ({envoyes} fichier(s))")
        c, out = gd("fetch", "-q", "origin", BRANCHE)
        distant = c == 0
        recus = 0
        if distant:
            _, n = gd("rev-list", "--count", f"HEAD..origin/{BRANCHE}")
            recus = int(n) if n.strip().isdigit() else 0
            if recus:
                c, out = gd(*_ident(), "merge", "--no-edit", "--allow-unrelated-histories", f"origin/{BRANCHE}")
                if c and "CONFLICT" in out:
                    _resoudre_conflits()
                    c, out = gd(*_ident(), "commit", "--no-edit")
                if c:
                    gd("merge", "--abort")
                    return _fin(False, "sauvegarde : fusion impossible : " + out[-160:], 0, 0)
        elif "couldn't find remote ref" not in out:
            return _fin(False, "hors ligne : sauvegarde reportee", 0, 0)
        if pousser:
            a_pousser = gd("rev-list", "--count", f"origin/{BRANCHE}..HEAD")[1] if distant else "1"
            if a_pousser.strip() != "0":
                c, out = gd("push", "-q", "origin", f"HEAD:{BRANCHE}")
                if c:
                    msg = ("pas le droit d'ecrire sur le depot GitHub (demander l'acces collaborateur)"
                           if "403" in out or "denied" in out.lower() or "permission" in out.lower()
                           else "envoi impossible : " + out[-160:])
                    return _fin(False, msg, recus, 0)
        return _fin(True, "a jour", recus, envoyes)


def _fin(ok, msg, recus, envoyes):
    etat.update(ok=ok, message=msg, derniere=time.time(), recus=recus, envoyes=envoyes)
    return dict(etat)


def planifier(delai=8.0):
    global _minuteur
    if _minuteur is not None:
        _minuteur.cancel()
    _minuteur = threading.Timer(delai, synchroniser)
    _minuteur.daemon = True
    _minuteur.start()


def boucle(periode=120.0):
    def tourner():
        while True:
            try:
                synchroniser()
                majour_code()
            except Exception as e:
                _fin(False, f"erreur synchro : {e}", 0, 0)
            time.sleep(periode)
    threading.Thread(target=tourner, daemon=True, name="synchro-projets").start()
